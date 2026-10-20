import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql

from v3.phase1.connected_flow import record_observation_cycle
from v3.phase1.observations import (
    FundingObservationRecord,
    InstrumentSnapshotRecord,
    Phase1CarryMarketObservation,
    QuoteObservationRecord,
)
from v3.phase1.policy import load_phase1_policy
from v3.phase1.postgres import PostgresPhase1Ledger, apply_migrations
from v3.phase1.risk_service import Phase1RiskService
from v3.reproducibility import RunManifest, TimeRange

ROOT = Path(__file__).resolve().parents[1]


def market_fixture():
    now = datetime.now(UTC)
    instruments = [
        InstrumentSnapshotRecord(
            str(uuid4()),
            "binance",
            name,
            "BTCUSDT",
            2,
            5,
            Decimal(minimum),
            Decimal("0.01"),
            Decimal("0.00001"),
            "TRADING",
            digest * 64,
            now,
        )
        for name, minimum, digest in (
            ("BTCUSDT.BINANCE", "5", "a"),
            ("BTCUSDT-PERP.BINANCE", "50", "b"),
        )
    ]
    quotes = [
        QuoteObservationRecord(
            str(uuid4()),
            instrument.id,
            Decimal("60000"),
            Decimal("60001"),
            None,
            now,
            None,
            15,
            "risk_decision",
            "demo",
        )
        for instrument in instruments
    ]
    return Phase1CarryMarketObservation(
        *instruments,
        *quotes,
        FundingObservationRecord(
            "BTCUSDT", Decimal("0.0001"), 480, now, "mainnet_public_usdm", "fundingRate_history"
        ),
        now,
    )


def manifest_fixture(*, dirty=False):
    now = datetime.now(UTC)
    return RunManifest(
        "a" * 40,
        "sha256:" + "b" * 64,
        "c" * 64,
        "d" * 64,
        "e" * 64,
        "fixture-only",
        TimeRange(now - timedelta(days=1), now),
        now,
        source_dirty=dirty,
    )


def test_connected_cycle_rejects_dirty_manifest_before_any_io():
    with pytest.raises(ValueError, match="dirty"):
        record_observation_cycle(
            market=market_fixture(),
            policy=None,
            manifest=manifest_fixture(dirty=True),
            ledger=None,
            risk_service=None,
            leverage=2,
        )


def test_connected_cycle_persists_denial_without_commands():
    dsn = os.environ.get("PHASE1_TEST_DATABASE_DSN")
    if not dsn:
        pytest.skip("PHASE1_TEST_DATABASE_DSN not set")
    schema = "test_connected_" + uuid4().hex
    policy_path = ROOT / "configs/phase1-policy.json"
    with psycopg.connect(dsn, autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        try:
            connection.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(schema)))
            apply_migrations(connection)
            with Phase1RiskService(policy_path=policy_path, timeout_seconds=3) as service:
                result = record_observation_cycle(
                    market=market_fixture(),
                    policy=load_phase1_policy(policy_path),
                    manifest=manifest_fixture(),
                    ledger=PostgresPhase1Ledger(connection),
                    risk_service=service,
                    leverage=2,
                )
            assert result["risk"]["approved"] is False
            assert result["orders_submitted"] is False
            assert result["final_state"] == "CLOSED"
            assert connection.execute("SELECT count(*) FROM order_commands").fetchone()[0] == 0
            assert connection.execute("SELECT count(*) FROM cost_ledger_entries").fetchone()[0] == 7
            assert connection.execute("SELECT count(*) FROM state_transitions").fetchone()[0] == 3
            assert (
                connection.execute(
                    "SELECT count(*) FROM quote_observations WHERE age_ms IS NULL"
                ).fetchone()[0]
                == 2
            )
            assert connection.execute("SELECT state FROM intents").fetchone()[0] == "CLOSED"
        finally:
            connection.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))
