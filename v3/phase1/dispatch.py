"""Durable at-most-once local dispatch attempts, not exactly-once venue execution.

No runner or network transport is enabled here. A returned submit call means local
enqueue only. Crashes, exceptions and absent venue orders never authorize replay.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from psycopg.pq import TransactionStatus
from psycopg.rows import dict_row

from .adapters import NAUTILUS_INSTRUMENT_IDS


@dataclass(frozen=True)
class DispatchOrder:
    command_id: str
    client_order_id: str
    instrument_id: str
    leg: str
    side: str
    quantity: Decimal
    price: Decimal

    def __post_init__(self):
        expected = (
            ("BTCUSDT.BINANCE", "buy") if self.leg == "spot" else ("BTCUSDT-PERP.BINANCE", "sell")
        )
        if self.leg not in {"spot", "perp"} or (self.instrument_id, self.side) != expected:
            raise ValueError("only canonical carry entry legs are supported")
        if not re.fullmatch(r"[a-zA-Z0-9_-]{1,32}", self.client_order_id):
            raise ValueError("invalid client order ID")
        if any(not value.is_finite() or value <= 0 for value in (self.quantity, self.price)):
            raise ValueError("finite positive order values are required")

    def to_nautilus(self, factory):
        """Construct a post-only entry using pinned Nautilus; never submit it."""
        from nautilus_trader.model.enums import OrderSide, TimeInForce
        from nautilus_trader.model.identifiers import ClientOrderId, InstrumentId
        from nautilus_trader.model.objects import Price, Quantity

        return factory.limit(
            instrument_id=InstrumentId.from_str(NAUTILUS_INSTRUMENT_IDS[self.instrument_id]),
            order_side=OrderSide.BUY if self.side == "buy" else OrderSide.SELL,
            quantity=Quantity.from_str(str(self.quantity)),
            price=Price.from_str(str(self.price)),
            time_in_force=TimeInForce.GTC,
            post_only=True,
            client_order_id=ClientOrderId(self.client_order_id),
        )


class DispatchJournal:
    """Requires a dedicated idle connection so claim commit precedes external I/O.

    This is a persistence primitive, NOT an execution authorization gateway.
    Caller must enforce deployment, fee, instrument, wallet and independent risk
    checks. It cannot be used to bypass the currently order-free runtime gate.
    """

    def __init__(self, connection):
        self.connection = connection

    def _require_idle(self):
        if self.connection.info.transaction_status != TransactionStatus.IDLE:
            raise ValueError("dispatch requires an idle dedicated connection")

    def claim(
        self,
        command_id: str,
        risk_decision_id: str,
        *,
        maximum_quote_age_ms: int | None,
        maximum_decision_age_ms: int = 1000,
    ) -> DispatchOrder:
        self._require_idle()
        if type(maximum_quote_age_ms) is not int or maximum_quote_age_ms <= 0:
            raise ValueError("measured quote-age limit is required")
        if type(maximum_decision_age_ms) is not int or not 0 < maximum_decision_age_ms <= 5000:
            raise ValueError("decision age limit must be in 1..5000ms")
        with self.connection.transaction(), self.connection.cursor(row_factory=dict_row) as cursor:
            # Serialize receipt admission with recovery before inspecting its gate.
            cursor.execute("SELECT pg_advisory_xact_lock(31092028)")
            if cursor.execute(
                "SELECT 1 FROM fill_event_inbox WHERE status <> 'APPLIED' LIMIT 1"
            ).fetchone():
                raise ValueError("unprocessed fill evidence blocks new dispatch")
            if cursor.execute(
                "SELECT 1 FROM order_recovery_checks WHERE status IN ('PENDING','BLOCKED') LIMIT 1"
            ).fetchone():
                raise ValueError("unresolved order recovery blocks new dispatch")
            # Match the parent-first lock order used by risk decision admission.
            intent = cursor.execute(
                "SELECT i.id, i.state FROM intents i JOIN order_commands c ON c.intent_id=i.id "
                "WHERE c.id=%s FOR UPDATE OF i",
                (command_id,),
            ).fetchone()
            if not intent or intent["state"] != "SUBMITTING":
                raise ValueError("dispatch requires an existing SUBMITTING intent")
            command = cursor.execute(
                "SELECT * FROM order_commands WHERE id=%s FOR UPDATE", (command_id,)
            ).fetchone()
            if not command["active"]:
                raise ValueError("inactive command cannot dispatch")
            if cursor.execute(
                "SELECT 1 FROM order_dispatches WHERE command_id=%s", (command_id,)
            ).fetchone():
                raise ValueError("dispatch already claimed; reconcile, never replay")
            if cursor.execute("SELECT 1 FROM orders WHERE command_id=%s", (command_id,)).fetchone():
                raise ValueError("existing venue evidence forbids dispatch")
            if cursor.execute(
                "SELECT 1 FROM order_dispatches d JOIN order_commands c ON c.id=d.command_id "
                "WHERE c.intent_id=%s AND d.status IN ('CLAIMED','ENQUEUED','UNKNOWN')",
                (intent["id"],),
            ).fetchone():
                raise ValueError("unresolved dispatch requires reconciliation")
            decision = cursor.execute(
                "SELECT * FROM risk_decisions WHERE intent_id=%s "
                "ORDER BY decided_at DESC,id DESC LIMIT 1",
                (intent["id"],),
            ).fetchone()
            now = cursor.execute("SELECT clock_timestamp() AS now").fetchone()["now"]
            if (
                not decision
                or str(decision["id"]) != risk_decision_id
                or not decision["approved"]
                or decision["reasons"]
            ):
                raise ValueError("latest matching approved risk decision is required")
            age_ms = (now - decision["decided_at"]).total_seconds() * 1000
            if not 0 <= age_ms <= maximum_decision_age_ms:
                raise ValueError("risk decision is stale or future dated")
            quote_age = decision["quote_age_ms"]
            if quote_age is None or quote_age < 0 or quote_age + age_ms > maximum_quote_age_ms:
                raise ValueError("quote expired since risk approval")
            leg = command["leg"]
            expected = (
                ("BTCUSDT.BINANCE", "buy", "LIMIT_MAKER")
                if leg == "spot"
                else ("BTCUSDT-PERP.BINANCE", "sell", "GTX")
            )
            if (command["instrument_id"], command["side"], command["order_type"]) != expected:
                raise ValueError("only canonical post-only carry entry commands are supported")
            if not re.fullmatch(r"[a-zA-Z0-9_-]{1,32}", command["idempotency_key"]):
                raise ValueError("invalid client order ID")
            if command["price"] is None or command["price"] <= 0:
                raise ValueError("entry limit price is required")
            order = DispatchOrder(
                command_id,
                command["idempotency_key"],
                command["instrument_id"],
                leg,
                command["side"],
                command["quantity"],
                command["price"],
            )
            payload = {key: str(value) for key, value in vars(order).items()}
            cursor.execute(
                "INSERT INTO order_dispatches "
                "(command_id,risk_decision_id,client_order_id,payload,status,claimed_at,updated_at) "
                "VALUES (%s,%s,%s,%s::jsonb,'CLAIMED',%s,%s)",
                (
                    command_id,
                    risk_decision_id,
                    order.client_order_id,
                    json.dumps(payload),
                    now,
                    now,
                ),
            )
        return order  # Transaction committed before caller can perform any external I/O.

    def record_enqueue_result(self, command_id: str, *, error: Exception | None = None):
        self._require_idle()
        with self.connection.transaction():
            row = self.connection.execute(
                "UPDATE order_dispatches SET status=%s,error_type=%s,updated_at=%s "
                "WHERE command_id=%s AND status='CLAIMED' RETURNING command_id",
                (
                    "UNKNOWN" if error else "ENQUEUED",
                    type(error).__name__ if error else None,
                    datetime.now(UTC),
                    command_id,
                ),
            ).fetchone()
            if row is None:
                raise ValueError("only a claimed attempt can record an enqueue result")

    def unresolved(self) -> tuple[dict, ...]:
        self._require_idle()
        with self.connection.transaction(), self.connection.cursor(row_factory=dict_row) as cursor:
            return tuple(
                cursor.execute(
                    "SELECT command_id,client_order_id,status,payload FROM order_dispatches "
                    "WHERE status <> 'OBSERVED' ORDER BY claimed_at,command_id"
                ).fetchall()
            )

    def reconcile_from_recorded_order(self, command_id: str) -> bool:
        """Only positive persisted order evidence resolves a dispatch; absence never does."""
        self._require_idle()
        with self.connection.transaction():
            row = self.connection.execute(
                "UPDATE order_dispatches d SET status='OBSERVED',updated_at=clock_timestamp() "
                "FROM orders o,order_commands c WHERE d.command_id=%s AND o.command_id=d.command_id "
                "AND c.id=d.command_id AND o.client_order_id=d.client_order_id "
                "AND o.venue_order_id IS NOT NULL AND o.status IN "
                "('NEW','ACCEPTED','PARTIALLY_FILLED','FILLED','CANCELED','CANCELLED','EXPIRED') "
                "AND o.venue=CASE WHEN c.leg='spot' THEN 'BINANCE_SPOT_DEMO' ELSE 'BINANCE_USDM_DEMO' END "
                "RETURNING d.command_id",
                (command_id,),
            ).fetchone()
            return row is not None
