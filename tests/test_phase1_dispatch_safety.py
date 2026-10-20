import os
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal
from threading import Barrier
from uuid import uuid4

import pytest
from test_phase1_dispatch import _isolated_database, _ready_submit_intent

from v3.phase1.dispatch import DispatchJournal, DispatchOrder
from v3.phase1.ledger import OrderCommandRow, RiskDecisionRow
from v3.phase1.postgres import apply_migrations


@pytest.fixture
def ready():
    dsn = os.environ.get("PHASE1_TEST_DATABASE_DSN")
    if not dsn:
        pytest.skip("PHASE1_TEST_DATABASE_DSN not set")
    with _isolated_database(dsn) as db:
        apply_migrations(db)
        ledger, intent, decision, command = _ready_submit_intent(db)
        # Database time is authoritative; local Docker clock need not equal host.
        db.execute("UPDATE risk_decisions SET decided_at=clock_timestamp()")
        yield db, ledger, intent, decision, command


def test_exception_keeps_unknown_and_does_not_store_sensitive_message(ready):
    db, _, _, decision, command = ready
    journal = DispatchJournal(db)
    journal.claim(command, decision, maximum_quote_age_ms=5000)
    assert db.info.transaction_status.name == "IDLE"
    journal.record_enqueue_result(command, error=TimeoutError("sensitive fixture"))
    assert db.execute("SELECT status,error_type FROM order_dispatches").fetchone() == (
        "UNKNOWN",
        "TimeoutError",
    )
    assert not journal.reconcile_from_recorded_order(command)
    with pytest.raises(ValueError, match="already claimed"):
        DispatchJournal(db).claim(command, decision, maximum_quote_age_ms=5000)


@pytest.mark.parametrize(
    "age,quote,limit", [(6000, 10, 10000), (-6000, 10, 10000), (100, 999, 1000), (0, None, 1000)]
)
def test_stale_future_or_unmeasured_decision_never_claims(ready, age, quote, limit):
    db, _, _, decision, command = ready
    at = db.execute("SELECT clock_timestamp()").fetchone()[0] - timedelta(milliseconds=age)
    db.execute("UPDATE risk_decisions SET decided_at=%s,quote_age_ms=%s", (at, quote))
    with pytest.raises(ValueError):
        DispatchJournal(db).claim(command, decision, maximum_quote_age_ms=limit)
    assert db.execute("SELECT count(*) FROM order_dispatches").fetchone()[0] == 0


def test_new_denial_wins(ready):
    db, ledger, intent, decision, command = ready
    at = db.execute("SELECT clock_timestamp()").fetchone()[0]
    ledger.add_risk_decision(RiskDecisionRow(str(uuid4()), intent, False, ("halt",), 0, at))
    with pytest.raises(ValueError, match="latest matching"):
        DispatchJournal(db).claim(command, decision, maximum_quote_age_ms=5000)


def test_no_external_call_can_escape_uncommitted_claim(ready):
    db, _, _, decision, command = ready
    with db.transaction():
        with pytest.raises(ValueError, match="idle dedicated"):
            DispatchJournal(db).claim(command, decision, maximum_quote_age_ms=5000)


@pytest.mark.parametrize("error", [None, TimeoutError()])
def test_unobserved_first_leg_blocks_second_leg(ready, error):
    db, ledger, intent, decision, command = ready
    journal = DispatchJournal(db)
    journal.claim(command, decision, maximum_quote_age_ms=5000)
    journal.record_enqueue_result(command, error=error)
    second = str(uuid4())
    ledger.add_command(
        OrderCommandRow(second, intent, "perp", uuid4().hex, "0.003", "100000"),
        instrument_id="BTCUSDT-PERP.BINANCE",
        side="sell",
        order_type="GTX",
    )
    with pytest.raises(ValueError, match="unresolved dispatch"):
        journal.claim(second, decision, maximum_quote_age_ms=5000)


def test_evidence_cannot_be_dropped_by_down_migration(ready):
    db, _, _, decision, command = ready
    DispatchJournal(db).claim(command, decision, maximum_quote_age_ms=5000)
    with pytest.raises(Exception, match="archive and reconcile"):
        apply_migrations(db, direction="down")
    assert db.execute("SELECT count(*) FROM order_dispatches").fetchone()[0] == 1


def test_two_independent_connections_can_claim_only_once(ready):
    import psycopg
    from psycopg import sql

    db, _, _, decision, command = ready
    schema = db.execute("SELECT current_schema()").fetchone()[0]
    barrier = Barrier(2)

    def attempt():
        with psycopg.connect(os.environ["PHASE1_TEST_DATABASE_DSN"], autocommit=True) as other:
            other.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(schema)))
            barrier.wait(timeout=5)
            try:
                DispatchJournal(other).claim(
                    command, decision, maximum_quote_age_ms=5000, maximum_decision_age_ms=5000
                )
                return "claimed"
            except ValueError as exc:
                return str(exc)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: attempt(), range(2)))
    assert results.count("claimed") == 1
    assert any("already claimed" in value for value in results)


@pytest.mark.parametrize("leg", ["spot", "perp"])
def test_pinned_factory_preserves_post_only_and_command_identity(leg):
    from nautilus_trader.common.component import TestClock
    from nautilus_trader.common.factories import OrderFactory
    from nautilus_trader.model.identifiers import StrategyId, TraderId

    factory = OrderFactory(TraderId("TEST-001"), StrategyId("CARRY-001"), TestClock())
    instrument = "BTCUSDT.BINANCE" if leg == "spot" else "BTCUSDT-PERP.BINANCE"
    spec = DispatchOrder(
        str(uuid4()),
        uuid4().hex,
        instrument,
        leg,
        "buy" if leg == "spot" else "sell",
        Decimal("0.001"),
        Decimal("60000.0"),
    )
    order = spec.to_nautilus(factory)
    assert str(order.client_order_id) == spec.client_order_id
    assert order.is_post_only
    assert order.quantity.as_decimal() == spec.quantity
    assert order.price.as_decimal() == spec.price
    assert str(order.instrument_id).endswith("_DEMO")
