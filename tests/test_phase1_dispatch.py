import os
from contextlib import contextmanager
from datetime import datetime, timedelta
from uuid import uuid4

import pytest

from v3.phase1.dispatch import DispatchJournal
from v3.phase1.ledger import IntentRow, OrderCommandRow, RiskDecisionRow
from v3.phase1.postgres import PostgresPhase1Ledger, apply_migrations
from v3.phase1.state_machine import CarryStateMachine, IntentState


@contextmanager
def _isolated_database(dsn):
    import psycopg
    from psycopg import sql

    schema = "test_dispatch_" + uuid4().hex
    with psycopg.connect(dsn, autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        try:
            connection.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(schema)))
            yield connection
        finally:
            connection.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


def _intent(intent_id: str, at: datetime) -> IntentRow:
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
            "max_holding_or_review_at": (at + timedelta(days=1)).isoformat(),
            "cost_and_risk_budget": "fee schedule fixture",
        },
        created_at=at,
    )


def _ready_submit_intent(connection):
    now = connection.execute("SELECT clock_timestamp()").fetchone()[0]
    ledger = PostgresPhase1Ledger(connection)
    intent_id = str(uuid4())
    risk_decision_id = str(uuid4())
    command_id = str(uuid4())
    ledger.add_intent(_intent(intent_id, now))
    ledger.add_risk_decision(
        RiskDecisionRow(risk_decision_id, intent_id, True, (), 10, now),
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
        OrderCommandRow(command_id, intent_id, "spot", "client-order-1", "0.003", "100000")
    )
    return ledger, intent_id, risk_decision_id, command_id


def test_dispatch_claim_commits_before_external_io_and_reconciles_only_with_order_evidence():
    dsn = os.environ.get("PHASE1_TEST_DATABASE_DSN")
    if not dsn:
        pytest.skip("PHASE1_TEST_DATABASE_DSN not set")

    with _isolated_database(dsn) as connection:
        apply_migrations(connection)
        ledger, _intent_id, risk_decision_id, command_id = _ready_submit_intent(connection)
        journal = DispatchJournal(connection)

        order = journal.claim(
            command_id, risk_decision_id, maximum_quote_age_ms=1000, maximum_decision_age_ms=5000
        )
        assert order.client_order_id == "client-order-1"
        assert order.instrument_id == "BTCUSDT.BINANCE"
        assert journal.unresolved()[0]["status"] == "CLAIMED"

        with pytest.raises(ValueError, match="already claimed"):
            journal.claim(
                command_id,
                risk_decision_id,
                maximum_quote_age_ms=1000,
                maximum_decision_age_ms=5000,
            )

        journal.record_enqueue_result(command_id)
        assert journal.unresolved()[0]["status"] == "ENQUEUED"
        assert not journal.reconcile_from_recorded_order(command_id)
        ledger.record_order(
            order_id=str(uuid4()),
            command_id=command_id,
            venue="BINANCE_SPOT_DEMO",
            venue_order_id="venue-order-1",
            client_order_id="client-order-1",
            status="NEW",
        )
        assert journal.reconcile_from_recorded_order(command_id)
        assert journal.unresolved() == ()


def test_dispatch_requires_fresh_latest_approved_risk_decision_and_measured_quote_age_limit():
    dsn = os.environ.get("PHASE1_TEST_DATABASE_DSN")
    if not dsn:
        pytest.skip("PHASE1_TEST_DATABASE_DSN not set")

    with _isolated_database(dsn) as connection:
        apply_migrations(connection)
        _ledger, _intent_id, risk_decision_id, command_id = _ready_submit_intent(connection)
        journal = DispatchJournal(connection)

        with pytest.raises(ValueError, match="quote-age limit"):
            journal.claim(command_id, risk_decision_id, maximum_quote_age_ms=None)
        with pytest.raises(ValueError, match="latest matching"):
            journal.claim(command_id, str(uuid4()), maximum_quote_age_ms=1000)
        with pytest.raises(ValueError, match="quote expired"):
            journal.claim(command_id, risk_decision_id, maximum_quote_age_ms=5)
