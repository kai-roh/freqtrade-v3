import json
import os
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import NAMESPACE_URL, uuid4, uuid5

import pytest

from v3.phase1.dispatch import DispatchJournal
from v3.phase1.ledger import IntentRow, OrderCommandRow, RiskDecisionRow
from v3.phase1.postgres import PostgresPhase1Ledger, apply_migrations
from v3.phase1.rest_recovery import (
    RestFillSnapshot,
    RestOrderSnapshot,
    apply_rest_recovery,
    recover_tracked_order,
    unresolved_recovery_count,
)
from v3.phase1.state_machine import CarryStateMachine, IntentState


@contextmanager
def _isolated_database(dsn):
    import psycopg
    from psycopg import sql

    schema = "test_recovery_" + uuid4().hex
    with psycopg.connect(dsn, autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        try:
            connection.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(schema)))
            yield connection
        finally:
            connection.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


def _ready_command(connection, *, leg="spot"):
    now = datetime.now(UTC)
    ledger = PostgresPhase1Ledger(connection)
    intent_id = str(uuid4())
    decision_id = str(uuid4())
    command_id = str(uuid4())
    client_id = f"client-{leg}-r1"
    ledger.add_intent(
        IntentRow(
            intent_id,
            "a" * 64,
            "b" * 64,
            "300",
            {
                "entry_reason": "fixture",
                "target_position": "long spot short perp",
                "normal_exit": "time",
                "risk_exit": "delta",
                "max_holding_or_review_at": (now + timedelta(hours=1)).isoformat(),
                "cost_and_risk_budget": "fixture",
            },
            now,
        )
    )
    ledger.add_risk_decision(
        RiskDecisionRow(decision_id, intent_id, True, (), 10, now),
        observed_leverage={"BTCUSDT-PERP.BINANCE": "2"},
    )
    machine = CarryStateMachine(intent_id, ledger)
    machine.transition(IntentState.PLANNED, trigger="fixture", guards={"persisted": True})
    machine.transition(IntentState.RISK_APPROVED, trigger="fixture", guards={"approved": True})
    machine.transition(
        IntentState.SUBMITTING,
        trigger="fixture",
        guards={"wallets_sufficient": True, "commands_recorded": True},
    )
    ledger.add_command(
        OrderCommandRow(command_id, intent_id, leg, client_id, "0.1", "100"),
        instrument_id="BTCUSDT-PERP.BINANCE" if leg == "perp" else "BTCUSDT.BINANCE",
        side="sell" if leg == "perp" else "buy",
        order_type="GTX" if leg == "perp" else "LIMIT_MAKER",
    )
    return ledger, command_id, decision_id


class _FailingInspector:
    def order(self, _leg, _client_id):
        raise RuntimeError("remote unavailable")


class _PerpInspector:
    def get(self, leg, path, params):
        assert path == "/fapi/v1/order" and str(params["orderId"]) == "987654"
        return self.order(leg, "client-perp-r1")

    def order(self, leg, client_id):
        assert leg == "perp"
        assert client_id == "client-perp-r1"
        return {
            "symbol": "BTCUSDT",
            "clientOrderId": client_id,
            "orderId": 987654,
            "side": "SELL",
            "origQty": "0.1",
            "price": "100",
            "executedQty": "0.1",
            "status": "FILLED",
            "updateTime": 1_700_000_000_000,
        }

    def fills(self, leg, order_id):
        assert leg == "perp"
        assert order_id == "987654"
        return [
            {
                "id": 123,
                "orderId": 987654,
                "symbol": "BTCUSDT",
                "side": "SELL",
                "buyer": False,
                "maker": True,
                "qty": "0.1",
                "price": "100",
                "commission": "0.002",
                "commissionAsset": "USDT",
                "time": 1_700_000_000_000,
            }
        ]


@pytest.mark.parametrize("damage", [None, "no_inbox_proof", "fee_conflict"])
def test_legacy_microsecond_repair_requires_raw_proof_and_identical_trade(damage):
    dsn = os.environ.get("PHASE1_TEST_DATABASE_DSN")
    if not dsn:
        pytest.skip("PHASE1_TEST_DATABASE_DSN not set")
    with _isolated_database(dsn) as db:
        apply_migrations(db)
        _, command, _ = _ready_command(db, leg="perp")
        assert recover_tracked_order(db, _PerpInspector(), command)["status"] == "APPLIED"
        db.execute("UPDATE fills SET filled_at=filled_at-interval '1 microsecond'")
        if damage == "fee_conflict":
            db.execute("UPDATE fills SET fee_amount=1")
        if damage != "no_inbox_proof":
            db.execute(
                "INSERT INTO fill_event_inbox(id,payload,status) VALUES (%s,%s::jsonb,'APPLIED')",
                (
                    str(uuid4()),
                    json.dumps(
                        dict(
                            client_order_id="client-perp-r1",
                            trade_id="123",
                            ts_event=1700000000000000000 - 64,
                        )
                    ),
                ),
            )
        result = recover_tracked_order(db, _PerpInspector(), command)
        assert result["status"] == ("APPLIED" if damage is None else "BLOCKED")
        timestamp = db.execute("SELECT filled_at FROM fills").fetchone()[0]
        assert timestamp.microsecond == (0 if damage is None else 999999)
        repaired = db.execute(
            "SELECT snapshot ? 'timestamp_normalization' FROM order_recovery_checks WHERE id=%s",
            (result["check_id"],),
        ).fetchone()[0]
        assert repaired is (damage is None)


@pytest.mark.parametrize(
    "damage",
    ["missing_fee", "string_maker", "missing_fill", "duplicate", "moving_order", "wrong_side"],
)
def test_incomplete_or_inconsistent_remote_evidence_stays_blocked(damage):
    dsn = os.environ.get("PHASE1_TEST_DATABASE_DSN")
    if not dsn:
        pytest.skip("PHASE1_TEST_DATABASE_DSN not set")

    class Inspector(_PerpInspector):
        reads = 0

        def order(self, leg, client_id):
            self.reads += 1
            row = super().order(leg, client_id)
            if damage == "moving_order" and self.reads > 1:
                row["updateTime"] += 1
            return row

        def fills(self, leg, order_id):
            rows = super().fills(leg, order_id)
            if damage == "missing_fee":
                del rows[0]["commission"]
            if damage == "string_maker":
                rows[0]["maker"] = "false"
            if damage == "missing_fill":
                rows = []
            if damage == "duplicate":
                rows += rows[:]
            if damage == "wrong_side":
                rows[0]["side"] = "BUY"
            return rows

    with _isolated_database(dsn) as connection:
        apply_migrations(connection)
        _, command_id, _ = _ready_command(connection, leg="perp")
        result = recover_tracked_order(connection, Inspector(), command_id)
        assert result["status"] == "BLOCKED"
        assert connection.execute("SELECT count(*) FROM fills").fetchone()[0] == 0
        assert connection.execute("SELECT count(*) FROM orders").fetchone()[0] == 0
        assert connection.execute("SELECT active FROM order_commands").fetchone()[0]
        # A later complete read resolves, not deletes, the original failure.
        assert (
            recover_tracked_order(connection, _PerpInspector(), command_id)["status"] == "APPLIED"
        )
        assert (
            connection.execute(
                "SELECT count(*) FROM order_recovery_checks WHERE status='RESOLVED' AND error_type IS NOT NULL"
            ).fetchone()[0]
            == 1
        )
        assert (
            recover_tracked_order(connection, _PerpInspector(), command_id)["status"] == "APPLIED"
        )
        assert connection.execute("SELECT count(*) FROM fills").fetchone()[0] == 1


def test_missing_rest_snapshot_blocks_future_dispatch_until_resolved():
    dsn = os.environ.get("PHASE1_TEST_DATABASE_DSN")
    if not dsn:
        pytest.skip("PHASE1_TEST_DATABASE_DSN not set")
    with _isolated_database(dsn) as connection:
        apply_migrations(connection)
        ledger, command_id, decision_id = _ready_command(connection)
        result = apply_rest_recovery(ledger, command_id=command_id, snapshot=None)
        assert result["status"] == "BLOCKED"
        assert unresolved_recovery_count(connection) == 1
        with pytest.raises(ValueError, match="order recovery"):
            DispatchJournal(connection).claim(
                command_id,
                decision_id,
                maximum_quote_age_ms=1000,
                maximum_decision_age_ms=5000,
            )

        resolved = apply_rest_recovery(
            ledger,
            command_id=command_id,
            snapshot=RestOrderSnapshot(
                venue="BINANCE_SPOT_DEMO",
                client_order_id="client-spot-r1",
                status="CANCELED",
                venue_order_id="venue-r1",
                filled_quantity=Decimal("0"),
                average_price=None,
                updated_at=datetime.now(UTC),
            ),
        )
        assert resolved["status"] == "APPLIED"
        assert unresolved_recovery_count(connection) == 0


def test_rest_recovery_applies_order_and_fills_atomically():
    dsn = os.environ.get("PHASE1_TEST_DATABASE_DSN")
    if not dsn:
        pytest.skip("PHASE1_TEST_DATABASE_DSN not set")
    with _isolated_database(dsn) as connection:
        apply_migrations(connection)
        ledger, command_id, _decision_id = _ready_command(connection)
        result = apply_rest_recovery(
            ledger,
            command_id=command_id,
            snapshot=RestOrderSnapshot(
                venue="BINANCE_SPOT_DEMO",
                client_order_id="client-spot-r1",
                status="FILLED",
                venue_order_id="venue-r1",
                filled_quantity=Decimal("0.1"),
                average_price=Decimal("100"),
                updated_at=datetime.now(UTC),
                fills=(
                    RestFillSnapshot(
                        "fill-r1",
                        Decimal("0.1"),
                        Decimal("100"),
                        datetime.now(UTC) - timedelta(seconds=1),
                        Decimal("0.01"),
                        "USDT",
                        "MAKER",
                    ),
                ),
            ),
        )
        assert result["status"] == "APPLIED"
        assert connection.execute("SELECT status,filled_quantity FROM orders").fetchone() == (
            "FILLED",
            Decimal("0.1"),
        )
        assert connection.execute("SELECT count(*) FROM fills").fetchone()[0] == 1


def test_recover_tracked_order_preserves_pending_receipt_when_remote_read_fails():
    dsn = os.environ.get("PHASE1_TEST_DATABASE_DSN")
    if not dsn:
        pytest.skip("PHASE1_TEST_DATABASE_DSN not set")
    with _isolated_database(dsn) as connection:
        apply_migrations(connection)
        _ledger, command_id, _decision_id = _ready_command(connection)
        result = recover_tracked_order(connection, _FailingInspector(), command_id)
        assert result["orders_submitted"] is False
        assert result["status"] == "BLOCKED"
        assert unresolved_recovery_count(connection) == 1
        assert connection.execute(
            "SELECT status,error_type,snapshot->'request'->>'client_order_id' "
            "FROM order_recovery_checks WHERE command_id=%s",
            (command_id,),
        ).fetchone() == ("BLOCKED", "RuntimeError", "client-spot-r1")
        assert connection.execute("SELECT count(*) FROM orders").fetchone()[0] == 0


def test_recover_tracked_order_maps_futures_trade_fields_and_deterministic_ids():
    dsn = os.environ.get("PHASE1_TEST_DATABASE_DSN")
    if not dsn:
        pytest.skip("PHASE1_TEST_DATABASE_DSN not set")
    with _isolated_database(dsn) as connection:
        apply_migrations(connection)
        _ledger, command_id, _decision_id = _ready_command(connection, leg="perp")
        result = recover_tracked_order(connection, _PerpInspector(), command_id)
        assert result["status"] == "APPLIED"
        order = connection.execute(
            "SELECT id,venue,status,filled_quantity FROM orders WHERE command_id=%s",
            (command_id,),
        ).fetchone()
        assert str(order[0]) == str(uuid5(NAMESPACE_URL, f"v3-order:{command_id}"))
        assert order[1:] == ("BINANCE_USDM_DEMO", "FILLED", Decimal("0.1"))
        fill = connection.execute(
            "SELECT id,venue,venue_fill_id,liquidity_side FROM fills"
        ).fetchone()
        assert fill[1:] == (
            "BINANCE_USDM_DEMO",
            "BTCUSDT-PERP.BINANCE:123",
            "MAKER",
        )
        assert (
            connection.execute(
                "SELECT active FROM order_commands WHERE id=%s", (command_id,)
            ).fetchone()[0]
            is False
        )


def test_nonterminal_recovery_does_not_deactivate_command():
    dsn = os.environ.get("PHASE1_TEST_DATABASE_DSN")
    if not dsn:
        pytest.skip("PHASE1_TEST_DATABASE_DSN not set")
    with _isolated_database(dsn) as connection:
        apply_migrations(connection)
        ledger, command_id, _decision_id = _ready_command(connection)
        result = apply_rest_recovery(
            ledger,
            command_id=command_id,
            snapshot=RestOrderSnapshot(
                venue="BINANCE_SPOT_DEMO",
                client_order_id="client-spot-r1",
                status="NEW",
                venue_order_id="venue-r1",
                filled_quantity=Decimal("0"),
                average_price=None,
                updated_at=datetime.now(UTC),
            ),
        )
        assert result["status"] == "APPLIED"
        assert (
            connection.execute(
                "SELECT active FROM order_commands WHERE id=%s", (command_id,)
            ).fetchone()[0]
            is True
        )


def test_invalid_snapshot_blocks_without_partial_order_or_fill_writes():
    dsn = os.environ.get("PHASE1_TEST_DATABASE_DSN")
    if not dsn:
        pytest.skip("PHASE1_TEST_DATABASE_DSN not set")
    with _isolated_database(dsn) as connection:
        apply_migrations(connection)
        ledger, command_id, _decision_id = _ready_command(connection)
        result = apply_rest_recovery(
            ledger,
            command_id=command_id,
            snapshot=RestOrderSnapshot(
                venue="BINANCE_USDM_DEMO",
                client_order_id="client-spot-r1",
                status="FILLED",
                venue_order_id="venue-r1",
                filled_quantity=Decimal("0.1"),
                average_price=Decimal("100"),
                updated_at=datetime.now(UTC),
                fills=(
                    RestFillSnapshot(
                        "fill-r1",
                        Decimal("0.1"),
                        Decimal("100"),
                        datetime.now(UTC),
                    ),
                ),
            ),
        )
        assert result["status"] == "BLOCKED"
        assert connection.execute("SELECT count(*) FROM orders").fetchone()[0] == 0
        assert connection.execute("SELECT count(*) FROM fills").fetchone()[0] == 0
