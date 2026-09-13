# Imported pytest fixtures are injected by name, not ordinary local redefinitions.
# ruff: noqa: F811
from decimal import Decimal

import pytest
from test_phase1_dispatch_safety import ready  # noqa: F401

from v3.phase1.fill_ingestion import record_nautilus_fill


def fill(trade="1", quantity="0.001", timestamp=1000000000, fee="0.01", **overrides):
    from nautilus_trader.core.uuid import UUID4
    from nautilus_trader.model.currencies import USDT
    from nautilus_trader.model.enums import LiquiditySide, OrderSide, OrderType
    from nautilus_trader.model.events import OrderFilled
    from nautilus_trader.model.identifiers import (
        AccountId,
        ClientOrderId,
        InstrumentId,
        StrategyId,
        TradeId,
        TraderId,
        VenueOrderId,
    )
    from nautilus_trader.model.objects import Money, Price, Quantity

    values = dict(
        trader_id=TraderId("TEST-001"),
        strategy_id=StrategyId("CARRY-001"),
        instrument_id=InstrumentId.from_str("BTCUSDT.BINANCE_SPOT_DEMO"),
        client_order_id=ClientOrderId("client-order-1"),
        venue_order_id=VenueOrderId("1"),
        account_id=AccountId("BINANCE_SPOT_DEMO-001"),
        trade_id=TradeId(trade),
        position_id=None,
        order_side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        last_qty=Quantity.from_str(quantity),
        last_px=Price.from_str("100000"),
        currency=USDT,
        commission=Money.from_str(f"{fee} USDT"),
        liquidity_side=LiquiditySide.MAKER,
        event_id=UUID4(),
        ts_event=timestamp,
        ts_init=timestamp,
    )
    values.update(overrides)
    return OrderFilled(**values)


def test_real_nautilus_partial_duplicate_and_out_of_order_fills_are_atomic(ready):
    db, ledger, _, _, command = ready
    later = fill("2", timestamp=2000000000)
    assert record_nautilus_fill(ledger, later) == command
    record_nautilus_fill(ledger, later)
    record_nautilus_fill(ledger, fill("1"))
    assert db.execute("SELECT status,filled_quantity FROM orders").fetchone() == (
        "PARTIALLY_FILLED",
        Decimal("0.002"),
    )
    record_nautilus_fill(ledger, fill("3", timestamp=3000000000))
    assert db.execute("SELECT status,filled_quantity FROM orders").fetchone() == (
        "FILLED",
        Decimal("0.003"),
    )
    assert db.execute("SELECT count(*),SUM(fee_amount) FROM fills").fetchone() == (
        3,
        Decimal("0.03"),
    )


def test_conflicting_duplicate_and_overfill_roll_back(ready):
    db, ledger, _, _, _ = ready
    record_nautilus_fill(ledger, fill("1", quantity="0.003"))
    with pytest.raises(ValueError, match="duplicate fill conflicts"):
        record_nautilus_fill(ledger, fill("1", quantity="0.003", fee="0.02"))
    with pytest.raises(ValueError, match="aggregate fills"):
        record_nautilus_fill(ledger, fill("2"))
    assert db.execute("SELECT count(*) FROM fills").fetchone()[0] == 1
    assert db.execute("SELECT filled_quantity FROM orders").fetchone()[0] == Decimal("0.003")


def test_wrong_account_or_unknown_command_never_changes_ledger(ready):
    from nautilus_trader.model.identifiers import AccountId, ClientOrderId

    db, ledger, _, _, _ = ready
    with pytest.raises(ValueError, match="issuer"):
        record_nautilus_fill(ledger, fill(account_id=AccountId("BINANCE_USDM_DEMO-001")))
    with pytest.raises(ValueError, match="matching canonical command"):
        record_nautilus_fill(ledger, fill(client_order_id=ClientOrderId("unknown")))
    assert db.execute("SELECT count(*) FROM orders").fetchone()[0] == 0


def test_late_partial_fill_does_not_reopen_cancelled_order(ready):
    db, ledger, _, _, command = ready
    record_nautilus_fill(ledger, fill("2", timestamp=2000000000))
    oid = str(db.execute("SELECT id FROM orders").fetchone()[0])
    ledger.record_order(
        order_id=oid,
        command_id=command,
        venue="BINANCE_SPOT_DEMO",
        client_order_id="client-order-1",
        venue_order_id="1",
        status="CANCELED",
        filled_quantity="0.001",
    )
    record_nautilus_fill(ledger, fill("1"))
    assert db.execute("SELECT status,filled_quantity FROM orders").fetchone() == (
        "CANCELED",
        Decimal("0.002"),
    )
