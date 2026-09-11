from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from psycopg.errors import UniqueViolation

from v3.phase1.ledger import (
    FillRow,
    IntentRow,
    OrderCommandRow,
    RiskDecisionRow,
)
from v3.phase1.postgres import (
    InstrumentSnapshotRow,
    PostgresPhase1Ledger,
    QuoteObservationRow,
)

NOW = datetime(2026, 9, 8, tzinfo=UTC)


@contextmanager
def _isolated_database(dsn):
    import psycopg
    from psycopg import sql

    schema = "test_ledger_" + uuid4().hex
    with psycopg.connect(dsn, autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        try:
            connection.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(schema)))
            yield connection
        finally:
            connection.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


def _intent(intent_id: str) -> IntentRow:
    return IntentRow(
        intent_id=intent_id,
        run_manifest_id="a" * 64,
        cost_ledger_id="b" * 64,
        target_notional="300",
        fields={
            "entry_reason": "positive funding fixture",
            "target_position": "long spot short perp",
            "normal_exit": "time exit",
            "risk_exit": "delta drift",
            "max_holding_or_review_at": "2026-09-09T00:00:00+00:00",
            "cost_and_risk_budget": "fee schedule fixture",
        },
        created_at=NOW,
    )


def test_rest_quote_observation_does_not_claim_exchange_age():
    quote = QuoteObservationRow(
        quote_id=str(uuid4()),
        instrument_snapshot_id=str(uuid4()),
        bid="100",
        ask="101",
        received_at=NOW,
        collection_mode="phase1e_sample",
        transport_rtt_ms=32,
        timestamp_source="rest_received_at",
    )

    assert quote.venue_timestamp is None
    assert quote.age_ms is None
    assert quote.transport_rtt_ms == 32


def test_exchange_quote_requires_real_venue_timestamp_and_age():
    with pytest.raises(ValueError, match="require venue_timestamp"):
        QuoteObservationRow(
            quote_id=str(uuid4()),
            instrument_snapshot_id=str(uuid4()),
            bid="100",
            ask="101",
            received_at=NOW,
            collection_mode="risk_decision",
        )


def test_postgres_repository_enforces_idempotency_when_dsn_is_available():
    pytest.importorskip("psycopg")
    import os

    dsn = os.environ.get("PHASE1_TEST_DATABASE_DSN")
    if not dsn:
        pytest.skip("PHASE1_TEST_DATABASE_DSN not set")

    from v3.phase1.postgres import apply_migrations

    with _isolated_database(dsn) as connection:
        apply_migrations(connection, direction="up")
        assert apply_migrations(connection) == ()
        ledger = PostgresPhase1Ledger(connection)
        intent_id = str(uuid4())
        command_id = str(uuid4())
        snapshot_id = str(uuid4())
        ledger.add_intent(_intent(intent_id))
        ledger.add_risk_decision(
            RiskDecisionRow(str(uuid4()), intent_id, True, (), 10, NOW),
            observed_leverage={"BTCUSDT-PERP.BINANCE": "2"},
        )
        ledger.add_instrument_snapshot(
            InstrumentSnapshotRow(
                snapshot_id,
                "binance",
                "BTCUSDT.BINANCE",
                "BTCUSDT",
                2,
                5,
                "5",
                "0.01",
                "0.00001",
                "TRADING",
                "c" * 64,
                NOW,
            )
        )
        ledger.add_quote_observation(
            QuoteObservationRow(
                str(uuid4()),
                snapshot_id,
                "100",
                "101",
                NOW,
                "phase1e_sample",
                transport_rtt_ms=1,
                timestamp_source="rest_received_at",
            )
        )
        ledger.add_command(OrderCommandRow(command_id, intent_id, "spot", "k" * 32, "0.1", "100"))
        ledger.record_order(
            order_id=str(uuid4()),
            command_id=command_id,
            venue="binance",
            client_order_id="k" * 32,
            status="NEW",
        )
        ledger.add_fill(
            FillRow(str(uuid4()), "binance", "venue-fill-1", command_id, "0.1", "100", NOW)
        )
        ledger.add_fill(
            FillRow(str(uuid4()), "binance", "venue-fill-1", command_id, "0.1", "100", NOW)
        )
        assert connection.execute("SELECT count(*) FROM fills").fetchone()[0] == 1
        with pytest.raises(ValueError, match="conflicts"):
            ledger.add_fill(
                FillRow(str(uuid4()), "binance", "venue-fill-1", command_id, "0.2", "100", NOW)
            )

        ledger.record_order(
            order_id=str(uuid4()),
            command_id=command_id,
            venue="binance",
            client_order_id="k" * 32,
            status="FILLED",
            filled_quantity="0.1",
            updated_at=NOW + timedelta(days=365),
        )
        ledger.record_order(
            order_id=str(uuid4()),
            command_id=command_id,
            venue="binance",
            client_order_id="k" * 32,
            status="NEW",
            updated_at=NOW,
        )
        assert connection.execute("SELECT status FROM orders").fetchone()[0] == "FILLED"

        assert ledger.has_approved_risk_decision(intent_id)
        assert len(ledger.active_commands(intent_id)) == 1
        with pytest.raises(UniqueViolation):
            ledger.add_command(
                OrderCommandRow(str(uuid4()), intent_id, "spot", "z" * 32, "0.1", "101")
            )
        ledger.add_risk_decision(
            RiskDecisionRow(
                str(uuid4()), intent_id, False, ("new denial",), 10, NOW + timedelta(seconds=1)
            )
        )
        assert not ledger.has_approved_risk_decision(intent_id)
        with pytest.raises(ValueError, match="latest approved"):
            ledger.add_command(
                OrderCommandRow(str(uuid4()), intent_id, "perp", "j" * 32, "0.1", "100"),
                instrument_id="BTCUSDT-PERP.BINANCE",
            )
