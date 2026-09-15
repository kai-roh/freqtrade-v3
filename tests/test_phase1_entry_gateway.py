import copy
import json
import os
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest

from v3.phase1.dispatch import DispatchJournal
from v3.phase1.entry_gateway import (
    EntryGatewayRequest,
    EntryLeg,
    WalletPreflight,
    submit_phase1_entry,
)
from v3.phase1.policy import load_phase1_policy
from v3.phase1.postgres import PostgresPhase1Ledger, apply_migrations
from v3.phase1.risk_service import Phase1RiskService, file_sha256
from v3.reproducibility import RunManifest, TimeRange

ROOT = Path(__file__).resolve().parents[1]


@contextmanager
def _isolated_database(dsn):
    import psycopg
    from psycopg import sql

    schema = "test_gateway_" + uuid4().hex
    with psycopg.connect(dsn, autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        try:
            connection.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(schema)))
            yield connection
        finally:
            connection.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


class FakeStrategy:
    orders_enabled = False

    def __init__(self, *, fail_on_submit: int | None = None):
        self.fail_on_submit = fail_on_submit
        self.prepared = []
        self.submitted = []

    def prepare_limit(self, **kwargs):
        self.prepared.append(kwargs)
        return dict(kwargs)

    def submit_prepared(self, order):
        if self.fail_on_submit == len(self.submitted) + 1:
            raise TimeoutError("lost submit result")
        self.submitted.append(order)


def _manifest(*, config_sha256: str = "d" * 64, dirty: bool = False) -> RunManifest:
    now = datetime.now(UTC)
    return RunManifest(
        "a" * 40,
        "sha256:" + "b" * 64,
        "c" * 64,
        config_sha256,
        "e" * 64,
        "fixture",
        TimeRange(now - timedelta(minutes=5), now),
        now,
        source_dirty=dirty,
    )


def _policy_path(tmp_path: Path) -> Path:
    raw = json.loads((ROOT / "configs/phase1-policy.json").read_text())
    measured = copy.deepcopy(raw)
    measured["sla"]["maximum_quote_age_ms"] = 1000
    measured["reconciliation"]["maximum_unexplained_residual_usdt"] = "0.05"
    measured["reconciliation"]["maximum_unclassified_hours"] = "2"
    measured["cost_model"]["snapshot_captured_at"] = datetime.now(UTC).isoformat()
    path = tmp_path / "phase1-policy-measured.json"
    path.write_text(json.dumps(measured, sort_keys=True))
    return path


def _request(**overrides) -> EntryGatewayRequest:
    values = {
        "intent_fields": {
            "entry_reason": "positive funding fixture",
            "target_position": "long spot short perp",
            "normal_exit": "funding convergence",
            "risk_exit": "delta drift",
            "max_holding_or_review_at": (datetime.now(UTC) + timedelta(hours=72)).isoformat(),
            "cost_and_risk_budget": "credentialed mainnet fee fixture",
        },
        "cost_ledger_complete": True,
        "leverage_by_instrument": {
            "BTCUSDT.BINANCE": "1",
            "BTCUSDT-PERP.BINANCE": "2",
        },
        "quote_age_ms": 50,
        "leg_notional": Decimal("300"),
        "minimum_notional_by_instrument": {
            "BTCUSDT.BINANCE": "10",
            "BTCUSDT-PERP.BINANCE": "5",
        },
        "local_positions_match_venue": True,
        "unexplained_residual_usdt": Decimal("0"),
        "residual_unclassified_hours": Decimal("0"),
        "daily_loss_usdt": Decimal("0"),
        "monthly_abort_cost_usdt": Decimal("0"),
        "abort_attempts_this_month": 0,
        "consecutive_aborts": 0,
        "spot": EntryLeg("spot", Decimal("0.005"), Decimal("60000")),
        "perp": EntryLeg("perp", Decimal("0.005"), Decimal("60000")),
        "wallet_preflight": WalletPreflight(
            wallets_sufficient=True,
            transfer_capability_verified=False,
            transfer_authorized=False,
        ),
        "evaluated_at": datetime.now(UTC),
    }
    values.update(overrides)
    return EntryGatewayRequest(**values)


def test_dirty_manifest_blocks_before_any_gateway_io():
    with pytest.raises(ValueError, match="dirty"):
        submit_phase1_entry(
            request=_request(),
            manifest=_manifest(dirty=True),
            policy=load_phase1_policy(ROOT / "configs/phase1-policy.json"),
            ledger=None,
            risk_service=None,
            dispatch=None,
            runtime=FakeStrategy(),
            allow_test_transport=True,
        )


def test_unmeasured_policy_denies_without_sending_orders():
    dsn = os.environ.get("PHASE1_TEST_DATABASE_DSN")
    if not dsn:
        pytest.skip("PHASE1_TEST_DATABASE_DSN not set")
    with _isolated_database(dsn) as connection:
        apply_migrations(connection)
        policy_path = ROOT / "configs/phase1-policy.json"
        strategy = FakeStrategy()
        with Phase1RiskService(policy_path=policy_path, timeout_seconds=3) as service:
            result = submit_phase1_entry(
                request=_request(),
                manifest=_manifest(config_sha256=file_sha256(policy_path)),
                policy=load_phase1_policy(policy_path),
                ledger=PostgresPhase1Ledger(connection),
                risk_service=service,
                dispatch=DispatchJournal(connection),
                runtime=strategy,
                allow_test_transport=True,
            )
        assert result.approved is False
        assert "quote-age SLA is unmeasured" in result.reasons
        assert strategy.submitted == []
        assert connection.execute("SELECT count(*) FROM order_commands").fetchone()[0] == 0


def test_approved_gateway_records_commands_and_enqueues_only_first_leg(tmp_path):
    dsn = os.environ.get("PHASE1_TEST_DATABASE_DSN")
    if not dsn:
        pytest.skip("PHASE1_TEST_DATABASE_DSN not set")
    with _isolated_database(dsn) as connection:
        apply_migrations(connection)
        policy_path = _policy_path(tmp_path)
        strategy = FakeStrategy()
        with Phase1RiskService(policy_path=policy_path, timeout_seconds=3) as service:
            result = submit_phase1_entry(
                request=_request(),
                manifest=_manifest(config_sha256=file_sha256(policy_path)),
                policy=load_phase1_policy(policy_path),
                ledger=PostgresPhase1Ledger(connection),
                risk_service=service,
                dispatch=DispatchJournal(connection),
                runtime=strategy,
                allow_test_transport=True,
                maximum_decision_age_ms=5000,
            )
        assert result.approved is True
        assert len(result.submitted_command_ids) == 1
        assert result.unknown_command_ids == ()
        assert len(result.pending_command_ids) == 1
        assert [order["canonical"] for order in strategy.submitted] == ["BTCUSDT.BINANCE"]
        assert [order["side"] for order in strategy.submitted] == ["buy"]
        assert all(order["post_only"] for order in strategy.submitted)
        assert strategy.orders_enabled is False
        assert (
            connection.execute(
                "SELECT count(*) FROM order_dispatches WHERE status='ENQUEUED'"
            ).fetchone()[0]
            == 1
        )
        assert (
            connection.execute(
                "SELECT leg FROM order_commands WHERE id=%s",
                (result.pending_command_ids[0],),
            ).fetchone()[0]
            == "perp"
        )


def test_post_enqueue_exception_is_unknown_and_blocks_replay(tmp_path):
    dsn = os.environ.get("PHASE1_TEST_DATABASE_DSN")
    if not dsn:
        pytest.skip("PHASE1_TEST_DATABASE_DSN not set")
    with _isolated_database(dsn) as connection:
        apply_migrations(connection)
        policy_path = _policy_path(tmp_path)
        strategy = FakeStrategy(fail_on_submit=1)
        with Phase1RiskService(policy_path=policy_path, timeout_seconds=3) as service:
            result = submit_phase1_entry(
                request=_request(),
                manifest=_manifest(config_sha256=file_sha256(policy_path)),
                policy=load_phase1_policy(policy_path),
                ledger=PostgresPhase1Ledger(connection),
                risk_service=service,
                dispatch=DispatchJournal(connection),
                runtime=strategy,
                allow_test_transport=True,
                maximum_decision_age_ms=5000,
            )
        assert result.submitted_command_ids == ()
        assert len(result.unknown_command_ids) == 1
        assert len(result.pending_command_ids) == 1
        assert strategy.orders_enabled is False
        assert (
            connection.execute(
                "SELECT count(*) FROM order_dispatches WHERE status='UNKNOWN'"
            ).fetchone()[0]
            == 1
        )
        with pytest.raises(ValueError, match="SUBMITTING intent"):
            DispatchJournal(connection).claim(
                result.unknown_command_ids[0],
                result.risk_decision_id,
                maximum_quote_age_ms=1000,
                maximum_decision_age_ms=5000,
            )


def test_changed_payload_refused_before_risk_service():
    with pytest.raises(ValueError, match="base quantities"):
        _request(spot=EntryLeg("spot", Decimal("0.004"), Decimal("60000")))


def test_equal_base_qty_allows_unequal_prices_with_risk_max_notional():
    request = _request(
        leg_notional=Decimal("305"),
        spot=EntryLeg("spot", Decimal("0.005"), Decimal("60000")),
        perp=EntryLeg("perp", Decimal("0.005"), Decimal("61000")),
    )

    assert request.leg_notional == request.perp.notional


def test_invalid_review_timestamp_is_rejected_before_risk_service(tmp_path):
    dsn = os.environ.get("PHASE1_TEST_DATABASE_DSN")
    if not dsn:
        pytest.skip("PHASE1_TEST_DATABASE_DSN not set")
    with _isolated_database(dsn) as connection:
        apply_migrations(connection)
        policy_path = _policy_path(tmp_path)
        fields = dict(_request().intent_fields, max_holding_or_review_at="not-a-date")
        with Phase1RiskService(policy_path=policy_path, timeout_seconds=3) as service:
            with pytest.raises(ValueError, match="valid ISO timestamp"):
                submit_phase1_entry(
                    request=_request(intent_fields=fields),
                    manifest=_manifest(config_sha256=file_sha256(policy_path)),
                    policy=load_phase1_policy(policy_path),
                    ledger=PostgresPhase1Ledger(connection),
                    risk_service=service,
                    dispatch=DispatchJournal(connection),
                    runtime=FakeStrategy(),
                    allow_test_transport=True,
                )
        assert connection.execute("SELECT count(*) FROM intents").fetchone()[0] == 0


def test_wallet_preflight_blocks_without_fabricating_sufficiency(tmp_path):
    dsn = os.environ.get("PHASE1_TEST_DATABASE_DSN")
    if not dsn:
        pytest.skip("PHASE1_TEST_DATABASE_DSN not set")
    with _isolated_database(dsn) as connection:
        apply_migrations(connection)
        policy_path = _policy_path(tmp_path)
        strategy = FakeStrategy()
        wallet_preflight = WalletPreflight(
            wallets_sufficient=False,
            transfer_capability_verified=False,
            transfer_authorized=False,
        )
        with Phase1RiskService(policy_path=policy_path, timeout_seconds=3) as service:
            result = submit_phase1_entry(
                request=_request(wallet_preflight=wallet_preflight),
                manifest=_manifest(config_sha256=file_sha256(policy_path)),
                policy=load_phase1_policy(policy_path),
                ledger=PostgresPhase1Ledger(connection),
                risk_service=service,
                dispatch=DispatchJournal(connection),
                runtime=strategy,
                allow_test_transport=True,
                maximum_decision_age_ms=5000,
            )
        assert result.approved is False
        assert "wallet balance is insufficient" in result.reasons[0]
        assert strategy.submitted == []
        assert connection.execute("SELECT count(*) FROM order_commands").fetchone()[0] == 0


def test_manifest_policy_hash_mismatch_blocks_before_gateway_io(tmp_path):
    dsn = os.environ.get("PHASE1_TEST_DATABASE_DSN")
    if not dsn:
        pytest.skip("PHASE1_TEST_DATABASE_DSN not set")
    with _isolated_database(dsn) as connection:
        apply_migrations(connection)
        policy_path = _policy_path(tmp_path)
        with Phase1RiskService(policy_path=policy_path, timeout_seconds=3) as service:
            with pytest.raises(ValueError, match="config hash"):
                submit_phase1_entry(
                    request=_request(),
                    manifest=_manifest(config_sha256="f" * 64),
                    policy=load_phase1_policy(policy_path),
                    ledger=PostgresPhase1Ledger(connection),
                    risk_service=service,
                    dispatch=DispatchJournal(connection),
                    runtime=FakeStrategy(),
                    allow_test_transport=True,
                )
        assert connection.execute("SELECT count(*) FROM intents").fetchone()[0] == 0


def test_fake_transport_requires_explicit_test_boundary(tmp_path):
    dsn = os.environ.get("PHASE1_TEST_DATABASE_DSN")
    if not dsn:
        pytest.skip("PHASE1_TEST_DATABASE_DSN not set")
    with _isolated_database(dsn) as connection:
        apply_migrations(connection)
        policy_path = _policy_path(tmp_path)
        with Phase1RiskService(policy_path=policy_path, timeout_seconds=3) as service:
            with pytest.raises(ValueError, match="pinned DemoNode"):
                submit_phase1_entry(
                    request=_request(),
                    manifest=_manifest(config_sha256=file_sha256(policy_path)),
                    policy=load_phase1_policy(policy_path),
                    ledger=PostgresPhase1Ledger(connection),
                    risk_service=service,
                    dispatch=DispatchJournal(connection),
                    runtime=FakeStrategy(),
                )
