"""Read-only REST recovery for uncertain Phase 1 Demo dispatches.

Recovery is evidence intake only. It creates a durable PENDING receipt before
any remote read, never submits/cancels orders, and never treats absence of venue
evidence as permission to replay a command.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import NAMESPACE_URL, uuid4, uuid5

from psycopg.pq import TransactionStatus
from psycopg.rows import dict_row

from .ledger import FillRow
from .postgres import PostgresPhase1Ledger

RECOVERY_DISPATCH_LOCK_KEY = 31092028
TERMINAL_ORDER_STATUSES = {"FILLED", "CANCELED", "CANCELLED", "REJECTED", "EXPIRED"}


@dataclass(frozen=True)
class RestFillSnapshot:
    venue_fill_id: str
    quantity: Decimal
    price: Decimal
    filled_at: datetime
    fee_amount: Decimal = Decimal("0")
    fee_token: str = "USDT"
    liquidity_side: str | None = None


@dataclass(frozen=True)
class RestOrderSnapshot:
    venue: str
    client_order_id: str
    status: str
    venue_order_id: str | None
    filled_quantity: Decimal
    average_price: Decimal | None
    updated_at: datetime
    fills: tuple[RestFillSnapshot, ...] = ()


def unresolved_recovery_count(connection) -> int:
    with connection.cursor(row_factory=dict_row) as cursor:
        row = cursor.execute(
            "SELECT count(*) AS count FROM order_recovery_checks "
            "WHERE status IN ('PENDING','BLOCKED')"
        ).fetchone()
    return int(row["count"])


def apply_rest_recovery(
    ledger: PostgresPhase1Ledger,
    *,
    command_id: str,
    snapshot: RestOrderSnapshot | None,
) -> dict[str, Any]:
    """Apply one exchange snapshot without submitting or canceling any order."""

    connection = ledger.connection
    check_id = _open_pending_check(connection, command_id, _snapshot_payload(snapshot))
    if snapshot is None:
        return _block_recovery(connection, check_id, "missing_order_snapshot")
    return _apply_snapshot(connection, check_id, command_id, snapshot)


def recover_tracked_order(connection, inspector, command_id: str) -> dict[str, Any]:
    """Read one tracked Demo order and apply its fills without venue mutation."""

    _require_idle(connection)
    command = _load_command(connection, command_id)
    check_id = _open_pending_check(
        connection,
        command_id,
        {
            "request": {
                "leg": command["leg"],
                "client_order_id": command["idempotency_key"],
            }
        },
    )
    try:

        def read_order():
            if command["known_venue_order_id"] is None:
                return inspector.order(command["leg"], command["idempotency_key"])
            prefix = "/api/v3" if command["leg"] == "spot" else "/fapi/v1"
            return inspector.get(
                command["leg"],
                prefix + "/order",
                {"symbol": "BTCUSDT", "orderId": command["known_venue_order_id"]},
            )

        order = read_order()
        venue_order_id = str(order["orderId"])
        trades = inspector.fills(command["leg"], venue_order_id)
        rechecked = read_order()
    except Exception as exc:
        return _block_recovery(connection, check_id, type(exc).__name__)

    payload = {"order": order, "trades": trades, "rechecked_order": rechecked}
    _update_check_snapshot(connection, check_id, payload)
    try:
        if order != rechecked:
            raise ValueError("order changed during recovery; a fresh snapshot is required")
        snapshot = _validated_rest_snapshot(command, order, trades)
    except Exception as exc:
        return _block_recovery(connection, check_id, type(exc).__name__)

    result = _apply_snapshot(connection, check_id, command_id, snapshot)
    if result["status"] != "APPLIED":
        return result | {"orders_submitted": False}

    from .dispatch import DispatchJournal

    DispatchJournal(connection).reconcile_from_recorded_order(command_id)
    return {
        "orders_submitted": False,
        "status": result["status"],
        "check_id": result["check_id"],
        "filled_quantity": str(snapshot.filled_quantity),
        "fill_count": len(snapshot.fills),
    }


def _require_idle(connection) -> None:
    if connection.info.transaction_status != TransactionStatus.IDLE:
        raise ValueError("REST recovery requires an idle dedicated connection")


def _load_command(connection, command_id: str) -> dict[str, Any]:
    with connection.transaction(), connection.cursor(row_factory=dict_row) as cursor:
        command = cursor.execute(
            """
            SELECT c.*,o.venue_order_id AS known_venue_order_id
            FROM order_commands c LEFT JOIN orders o ON o.command_id=c.id
            WHERE c.id=%s
            """,
            (command_id,),
        ).fetchone()
    if command is None:
        raise ValueError("recovery command is unknown")
    return dict(command)


def _open_pending_check(connection, command_id: str, snapshot: dict[str, Any]) -> str:
    _require_idle(connection)
    check_id = str(uuid4())
    with connection.transaction():
        connection.execute("SELECT pg_advisory_xact_lock(%s)", (RECOVERY_DISPATCH_LOCK_KEY,))
        if (
            connection.execute(
                "SELECT 1 FROM order_commands WHERE id=%s FOR UPDATE", (command_id,)
            ).fetchone()
            is None
        ):
            raise ValueError("recovery command is unknown")
        connection.execute(
            "INSERT INTO order_recovery_checks(id,command_id,status,snapshot,created_at) "
            "VALUES (%s,%s,'PENDING',%s::jsonb,%s)",
            (check_id, command_id, json.dumps(snapshot), datetime.now(UTC)),
        )
    return check_id


def _apply_snapshot(
    connection, check_id: str, command_id: str, snapshot: RestOrderSnapshot
) -> dict[str, Any]:
    ledger = PostgresPhase1Ledger(connection)
    try:
        with connection.transaction():
            connection.execute("SELECT pg_advisory_xact_lock(%s)", (RECOVERY_DISPATCH_LOCK_KEY,))
            command = _lock_command(connection, command_id)
            _validate_snapshot_against_command(command, snapshot)
            order_id = str(uuid5(NAMESPACE_URL, f"v3-order:{command_id}"))
            ledger.record_order(
                order_id=order_id,
                command_id=command_id,
                venue=snapshot.venue,
                venue_order_id=snapshot.venue_order_id,
                client_order_id=snapshot.client_order_id,
                status=snapshot.status,
                filled_quantity=snapshot.filled_quantity,
                average_price=snapshot.average_price,
                updated_at=snapshot.updated_at,
            )
            for fill in snapshot.fills:
                venue_fill_id = _canonical_rest_fill_id(command, fill.venue_fill_id)
                _normalize_legacy_stream_time(
                    connection, command, snapshot, fill, venue_fill_id, check_id
                )
                ledger.add_fill(
                    FillRow(
                        str(uuid5(NAMESPACE_URL, f"v3-fill:{snapshot.venue}:{venue_fill_id}")),
                        snapshot.venue,
                        venue_fill_id,
                        command_id,
                        fill.quantity,
                        fill.price,
                        fill.filled_at,
                    ),
                    fee_amount=fill.fee_amount,
                    fee_token=fill.fee_token,
                    liquidity_side=fill.liquidity_side,
                )
            _ensure_recovery_complete(connection, command_id, order_id, snapshot)
            if snapshot.status in TERMINAL_ORDER_STATUSES:
                ledger.deactivate_command(command_id)
            connection.execute(
                "UPDATE order_recovery_checks SET status='RESOLVED',"
                "snapshot=snapshot || %s::jsonb,completed_at=clock_timestamp() "
                "WHERE command_id=%s AND status='BLOCKED' AND id<>%s",
                (json.dumps({"resolved_by": check_id}), command_id, check_id),
            )
            connection.execute(
                "UPDATE order_recovery_checks SET status='APPLIED',completed_at=clock_timestamp(),"
                "error_type=NULL WHERE id=%s",
                (check_id,),
            )
    except Exception as exc:
        return _block_recovery(connection, check_id, type(exc).__name__)
    return {"check_id": check_id, "status": "APPLIED"}


def _normalize_legacy_stream_time(connection, command, snapshot, fill, venue_fill_id, check_id):
    """Repair only a proven 1us truncation, retaining raw inbox and audit receipt.

    All other duplicate fields are still checked by add_fill in this same atomic
    transaction; any mismatch rolls back the correction too.
    """
    from .fill_ingestion import binance_event_time

    existing = connection.execute(
        "SELECT id,filled_at FROM fills WHERE venue=%s AND venue_fill_id=%s FOR UPDATE",
        (snapshot.venue, venue_fill_id),
    ).fetchone()
    if not existing or fill.filled_at - existing[1] != timedelta(microseconds=1):
        return
    raw = connection.execute(
        "SELECT payload FROM fill_event_inbox WHERE status='APPLIED' "
        "AND payload->>'client_order_id'=%s AND payload->>'trade_id'=%s",
        (command["idempotency_key"], venue_fill_id.rsplit(":", 1)[-1]),
    ).fetchall()
    epoch = datetime(1970, 1, 1, tzinfo=UTC)
    if not any(
        binance_event_time(row[0]["ts_event"]) == fill.filled_at
        and epoch + timedelta(microseconds=row[0]["ts_event"] // 1000) == existing[1]
        for row in raw
    ):
        return
    connection.execute("UPDATE fills SET filled_at=%s WHERE id=%s", (fill.filled_at, existing[0]))
    connection.execute(
        "UPDATE order_recovery_checks SET snapshot=snapshot || %s::jsonb WHERE id=%s",
        (
            json.dumps(
                {
                    "timestamp_normalization": {
                        "fill_id": str(existing[0]),
                        "previous": existing[1].isoformat(),
                        "canonical": fill.filled_at.isoformat(),
                        "basis": "raw inbox nanos and identical REST trade; pinned float conversion",
                    }
                }
            ),
            check_id,
        ),
    )


def _lock_command(connection, command_id: str) -> dict[str, Any]:
    with connection.cursor(row_factory=dict_row) as cursor:
        command = cursor.execute(
            """
            SELECT id,intent_id,leg,idempotency_key,instrument_id,side,order_type,quantity,price,active
            FROM order_commands
            WHERE id=%s
            FOR UPDATE
            """,
            (command_id,),
        ).fetchone()
    if command is None:
        raise ValueError("recovery command is unknown")
    return dict(command)


def _validate_snapshot_against_command(
    command: dict[str, Any], snapshot: RestOrderSnapshot
) -> None:
    expected_venue = _expected_venue(command["leg"])
    if snapshot.venue != expected_venue:
        raise ValueError("order venue mismatch")
    if snapshot.client_order_id != command["idempotency_key"]:
        raise ValueError("client_order_id_mismatch")
    if snapshot.venue_order_id is None:
        raise ValueError("venue_order_id is required for positive order evidence")
    if snapshot.filled_quantity < 0 or snapshot.filled_quantity > command["quantity"]:
        raise ValueError("filled quantity is outside command bounds")
    if snapshot.status not in {
        "NEW",
        "ACCEPTED",
        "PARTIALLY_FILLED",
        "FILLED",
        "CANCELED",
        "CANCELLED",
        "REJECTED",
        "EXPIRED",
    }:
        raise ValueError("unsupported order status")
    if snapshot.filled_quantity == 0 and snapshot.fills:
        raise ValueError("zero-filled snapshot cannot include fills")
    if snapshot.filled_quantity > 0 and snapshot.average_price is None:
        raise ValueError("filled snapshot requires average_price")
    if not snapshot.filled_quantity.is_finite():
        raise ValueError("nonfinite filled quantity")
    if snapshot.status == "FILLED" and snapshot.filled_quantity != command["quantity"]:
        raise ValueError("FILLED requires the complete command quantity")
    if snapshot.status in {"NEW", "ACCEPTED", "REJECTED"} and snapshot.filled_quantity != 0:
        raise ValueError("order status contradicts its fills")
    _validate_time(snapshot.updated_at)
    seen = set()
    for fill in snapshot.fills:
        key = _canonical_rest_fill_id(command, fill.venue_fill_id)
        if key in seen:
            raise ValueError("duplicate fill identifier")
        seen.add(key)
        if any(not value.is_finite() for value in (fill.quantity, fill.price, fill.fee_amount)):
            raise ValueError("nonfinite fill values")
        if fill.quantity <= 0 or fill.price <= 0 or fill.fee_amount < 0:
            raise ValueError("invalid fill values")
        if not re.fullmatch(r"[A-Z0-9]{1,20}", fill.fee_token):
            raise ValueError("invalid commission asset")
        if fill.liquidity_side not in {"MAKER", "TAKER"}:
            raise ValueError("missing liquidity classification")
        _validate_time(fill.filled_at)
        if fill.filled_at > snapshot.updated_at:
            raise ValueError("fill is newer than order evidence")
    if sum((fill.quantity for fill in snapshot.fills), Decimal(0)) != snapshot.filled_quantity:
        raise ValueError("snapshot must contain the complete fill history")


def _ensure_recovery_complete(
    connection, command_id: str, order_id: str, snapshot: RestOrderSnapshot
) -> None:
    with connection.cursor(row_factory=dict_row) as cursor:
        order = cursor.execute(
            """
            SELECT venue,venue_order_id,client_order_id,status,filled_quantity,average_price
            FROM orders
            WHERE command_id=%s
            FOR UPDATE
            """,
            (command_id,),
        ).fetchone()
        if order is None:
            raise ValueError("order recovery did not persist order evidence")
        if (
            order["venue"] != snapshot.venue
            or str(order["venue_order_id"]) != str(snapshot.venue_order_id)
            or order["client_order_id"] != snapshot.client_order_id
            or order["filled_quantity"] != snapshot.filled_quantity
        ):
            raise ValueError("persisted order does not match REST evidence")
        fill_totals = cursor.execute(
            """
            SELECT COALESCE(SUM(quantity),0) AS quantity,COUNT(*) AS count
            FROM fills
            WHERE order_id=%s
            """,
            (order_id,),
        ).fetchone()
        if fill_totals["quantity"] != snapshot.filled_quantity:
            raise ValueError("persisted REST fills are incomplete")


def _block_recovery(connection, check_id: str, error_type: str) -> dict[str, Any]:
    _require_idle(connection)
    with connection.transaction():
        connection.execute("SELECT pg_advisory_xact_lock(%s)", (RECOVERY_DISPATCH_LOCK_KEY,))
        connection.execute(
            "UPDATE order_recovery_checks SET status='BLOCKED',error_type=%s,"
            "completed_at=clock_timestamp() WHERE id=%s AND status='PENDING'",
            (error_type, check_id),
        )
    return {
        "check_id": check_id,
        "status": "BLOCKED",
        "error_type": error_type,
        "orders_submitted": False,
    }


def _update_check_snapshot(connection, check_id: str, payload: dict[str, Any]) -> None:
    _require_idle(connection)
    with connection.transaction():
        connection.execute("SELECT pg_advisory_xact_lock(%s)", (RECOVERY_DISPATCH_LOCK_KEY,))
        connection.execute(
            "UPDATE order_recovery_checks SET snapshot=%s::jsonb WHERE id=%s AND status='PENDING'",
            (json.dumps(payload), check_id),
        )


def _validated_rest_snapshot(
    command: dict[str, Any], order: dict[str, Any], trades: list[dict[str, Any]]
):
    expected_side = "BUY" if command["side"] == "buy" else "SELL"
    expected_buyer = command["side"] == "buy"
    known_id = command.get("known_venue_order_id")
    identity_matches = (
        str(order.get("orderId")) == str(known_id)
        if known_id is not None
        else order.get("clientOrderId") == command["idempotency_key"]
    )
    if order.get("symbol") != "BTCUSDT" or not identity_matches:
        raise ValueError("order identity mismatch")
    if order.get("side") != expected_side:
        raise ValueError("order side mismatch")
    if (
        Decimal(order["origQty"]) != command["quantity"]
        or Decimal(order["price"]) != command["price"]
    ):
        raise ValueError("order payload mismatch")
    executed = Decimal(order["executedQty"])
    if executed < 0 or executed > command["quantity"]:
        raise ValueError("executed quantity is outside command bounds")
    seen: set[str] = set()
    fills: list[RestFillSnapshot] = []
    total = Decimal("0")
    notional = Decimal("0")
    for trade in trades:
        trade_id = str(trade["id"])
        if trade_id in seen:
            raise ValueError("duplicate trade identifier")
        seen.add(trade_id)
        if str(trade["orderId"]) != str(order["orderId"]) or trade.get("symbol") != "BTCUSDT":
            raise ValueError("trade identity mismatch")
        if _trade_is_buyer(trade) is not expected_buyer:
            raise ValueError("trade side mismatch")
        if "side" in trade and trade["side"] != expected_side:
            raise ValueError("trade side mismatch")
        quantity = Decimal(trade["qty"])
        price = Decimal(trade["price"])
        fee = Decimal(trade["commission"])
        if quantity <= 0 or price <= 0 or fee < 0:
            raise ValueError("trade numeric values are invalid")
        total += quantity
        notional += quantity * price
        fills.append(
            RestFillSnapshot(
                venue_fill_id=trade_id,
                quantity=quantity,
                price=price,
                filled_at=_milliseconds(trade["time"]),
                fee_amount=fee,
                fee_token=trade["commissionAsset"],
                liquidity_side="MAKER" if _trade_is_maker(trade) else "TAKER",
            )
        )
    if total != executed:
        raise ValueError("REST fills do not match executed quantity")
    average = (notional / total) if total > 0 else None
    return RestOrderSnapshot(
        venue=_expected_venue(command["leg"]),
        client_order_id=command["idempotency_key"],
        status=order["status"],
        venue_order_id=str(order["orderId"]),
        filled_quantity=executed,
        average_price=average,
        updated_at=_milliseconds(order["updateTime"]),
        fills=tuple(fills),
    )


def _trade_is_buyer(trade: dict[str, Any]) -> bool:
    if "isBuyer" in trade:
        return _boolean(trade["isBuyer"])
    if "buyer" in trade:
        return _boolean(trade["buyer"])
    raise ValueError("trade buyer flag is missing")


def _trade_is_maker(trade: dict[str, Any]) -> bool:
    if "isMaker" in trade:
        return _boolean(trade["isMaker"])
    if "maker" in trade:
        return _boolean(trade["maker"])
    raise ValueError("trade maker flag is missing")


def _boolean(value):
    if type(value) is not bool:
        raise ValueError("trade classification must be a boolean")
    return value


def _validate_time(value):
    if value.tzinfo is None or value.utcoffset() is None or value > datetime.now(UTC):
        raise ValueError("invalid evidence timestamp")


def _milliseconds(value):
    if type(value) is not int or value <= 0:
        raise ValueError("invalid exchange timestamp")
    return datetime(1970, 1, 1, tzinfo=UTC) + timedelta(milliseconds=value)


def _expected_venue(leg: str) -> str:
    if leg == "spot":
        return "BINANCE_SPOT_DEMO"
    if leg == "perp":
        return "BINANCE_USDM_DEMO"
    raise ValueError("unknown command leg")


def _canonical_rest_fill_id(command: dict[str, Any], venue_fill_id: str) -> str:
    prefix = f"{command['instrument_id']}:"
    if venue_fill_id.startswith(prefix):
        return venue_fill_id
    return f"{prefix}{venue_fill_id}"


def _snapshot_payload(snapshot: RestOrderSnapshot | None) -> dict[str, Any]:
    if snapshot is None:
        return {"present": False}
    return {
        "present": True,
        "venue": snapshot.venue,
        "client_order_id": snapshot.client_order_id,
        "status": snapshot.status,
        "venue_order_id": snapshot.venue_order_id,
        "filled_quantity": str(snapshot.filled_quantity),
        "average_price": str(snapshot.average_price)
        if snapshot.average_price is not None
        else None,
        "updated_at": snapshot.updated_at.isoformat(),
        "trades": [
            {
                "venue_fill_id": fill.venue_fill_id,
                "quantity": str(fill.quantity),
                "price": str(fill.price),
                "filled_at": fill.filled_at.isoformat(),
                "fee_amount": str(fill.fee_amount),
                "fee_token": fill.fee_token,
                "liquidity_side": fill.liquidity_side,
            }
            for fill in snapshot.fills
        ],
    }
