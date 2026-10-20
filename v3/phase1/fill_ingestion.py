"""Atomic ingestion of pinned Nautilus fills; no order submission or state promotion."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import NAMESPACE_URL, uuid5

from psycopg.rows import dict_row

from .adapters import canonical_instrument_id
from .ledger import FillRow
from .postgres import PostgresPhase1Ledger


def binance_event_time(nanoseconds):
    # Pinned millis_to_nanos uses float conversion: epoch milliseconds can
    # acquire <=256 ns of rounding error. Preserve finer times otherwise.
    milliseconds = (nanoseconds + 500_000) // 1_000_000
    if abs(nanoseconds - milliseconds * 1_000_000) <= 256:
        return datetime(1970, 1, 1, tzinfo=UTC) + timedelta(milliseconds=milliseconds)
    return datetime(1970, 1, 1, tzinfo=UTC) + timedelta(microseconds=nanoseconds // 1000)


def record_nautilus_fill(ledger: PostgresPhase1Ledger, event) -> str:
    """Record venue evidence even while new orders are halted.

    Demo commissions are preserved as observed evidence, never substituted for
    the mainnet economic cost model. Unknown commands require reconciliation.
    """
    from nautilus_trader.model.events import OrderFilled

    if not isinstance(event, OrderFilled):
        raise ValueError("an OrderFilled event is required")
    runtime_id = str(event.instrument_id)
    canonical = canonical_instrument_id(runtime_id)
    venue = runtime_id.rsplit(".", 1)[1]
    if str(event.account_id).split("-", 1)[0] != venue:
        raise ValueError("fill account issuer does not match instrument venue")
    at = binance_event_time(event.ts_event)
    quantity, price = event.last_qty.as_decimal(), event.last_px.as_decimal()
    # Binance trade IDs are symbol scoped, not globally unique for a product.
    venue_fill_id = f"{canonical}:{event.trade_id}"
    with ledger.connection.transaction(), ledger.connection.cursor(row_factory=dict_row) as cursor:
        command = cursor.execute(
            "SELECT * FROM order_commands WHERE idempotency_key=%s FOR UPDATE",
            (str(event.client_order_id),),
        ).fetchone()
        if not command or command["instrument_id"] != canonical:
            raise ValueError("fill has no matching canonical command")
        side = "BUY" if command["side"] == "buy" else "SELL"
        if event.order_side.name != side:
            raise ValueError("fill side does not match command")
        command_id = str(command["id"])
        current = cursor.execute(
            "SELECT * FROM orders WHERE command_id=%s FOR UPDATE", (command_id,)
        ).fetchone()
        order_id = (
            str(current["id"]) if current else str(uuid5(NAMESPACE_URL, f"v3-order:{command_id}"))
        )
        ledger.record_order(
            order_id=order_id,
            command_id=command_id,
            venue=venue,
            client_order_id=str(event.client_order_id),
            venue_order_id=str(event.venue_order_id),
            status=current["status"] if current else "NEW",
            filled_quantity=current["filled_quantity"] if current else "0",
            average_price=current["average_price"] if current else None,
            updated_at=max(at, current["updated_at"]) if current else at,
        )
        ledger.add_fill(
            FillRow(
                str(uuid5(NAMESPACE_URL, f"v3-fill:{venue}:{venue_fill_id}")),
                venue,
                venue_fill_id,
                command_id,
                quantity,
                price,
                at,
            ),
            fee_amount=event.commission.as_decimal(),
            fee_token=str(event.commission.currency),
            liquidity_side=event.liquidity_side.name,
        )
        totals = cursor.execute(
            "SELECT SUM(quantity) AS quantity,SUM(quantity*price) AS value FROM fills WHERE order_id=%s",
            (order_id,),
        ).fetchone()
        total = totals["quantity"] or Decimal(0)
        if total > command["quantity"]:
            raise ValueError("aggregate fills exceed commanded quantity; reconciliation required")
        if current and total < current["filled_quantity"]:
            # Existing order snapshots may precede the arrival of missing fill details.
            return command_id
        status = "FILLED" if total == command["quantity"] else "PARTIALLY_FILLED"
        if (
            current
            and current["status"] in {"CANCELED", "CANCELLED", "EXPIRED"}
            and status != "FILLED"
        ):
            status = current["status"]
        ledger.record_order(
            order_id=order_id,
            command_id=command_id,
            venue=venue,
            client_order_id=str(event.client_order_id),
            venue_order_id=str(event.venue_order_id),
            status=status,
            filled_quantity=total,
            average_price=totals["value"] / total,
            updated_at=max(at, current["updated_at"]) if current else at,
        )
        return command_id
