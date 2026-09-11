"""Durable PostgreSQL repository for Phase 1 execution evidence."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import psycopg
from psycopg import Connection
from psycopg.rows import dict_row

from v3.costs import DecimalInput, as_decimal

from .ledger import (
    CostLedgerEntryRow,
    FillRow,
    IncidentRow,
    IntentRow,
    InternalTransferRow,
    OrderCommandRow,
    RiskDecisionRow,
    TransitionRow,
)

MIGRATION_ROOT = Path(__file__).resolve().parent / "migrations"


def _utc(value: datetime, *, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must include a timezone")
    return value.astimezone(UTC)


def _json(value: Mapping[str, Any] | Iterable[Any]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _uuidish(value: str) -> str:
    if not value.strip():
        raise ValueError("ID values must be non-empty")
    return value


@dataclass(frozen=True)
class InstrumentSnapshotRow:
    snapshot_id: str
    venue: str
    instrument_id: str
    raw_symbol: str
    price_precision: int
    size_precision: int
    minimum_notional: DecimalInput
    tick_size: DecimalInput
    lot_size: DecimalInput
    status: str
    content_hash: str
    observed_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "minimum_notional",
            as_decimal(self.minimum_notional, field_name="minimum_notional"),
        )
        object.__setattr__(self, "tick_size", as_decimal(self.tick_size, field_name="tick_size"))
        object.__setattr__(self, "lot_size", as_decimal(self.lot_size, field_name="lot_size"))
        object.__setattr__(self, "observed_at", _utc(self.observed_at, field_name="observed_at"))
        if self.minimum_notional <= 0 or self.tick_size <= 0 or self.lot_size <= 0:
            raise ValueError("instrument numeric constraints must be positive")
        if len(self.content_hash) != 64:
            raise ValueError("content_hash must be a SHA-256 hex digest")


@dataclass(frozen=True)
class QuoteObservationRow:
    quote_id: str
    instrument_snapshot_id: str
    bid: DecimalInput
    ask: DecimalInput
    received_at: datetime
    collection_mode: str
    venue_timestamp: datetime | None = None
    age_ms: int | None = None
    transport_rtt_ms: int | None = None
    timestamp_source: str = "exchange_event"

    def __post_init__(self) -> None:
        object.__setattr__(self, "bid", as_decimal(self.bid, field_name="bid"))
        object.__setattr__(self, "ask", as_decimal(self.ask, field_name="ask"))
        object.__setattr__(self, "received_at", _utc(self.received_at, field_name="received_at"))
        if self.venue_timestamp is not None:
            object.__setattr__(
                self, "venue_timestamp", _utc(self.venue_timestamp, field_name="venue_timestamp")
            )
        if self.bid <= 0 or self.ask < self.bid:
            raise ValueError("quote bid/ask are invalid")
        if self.collection_mode not in {"risk_decision", "phase1e_sample"}:
            raise ValueError("invalid quote collection_mode")
        if self.timestamp_source not in {"exchange_event", "rest_received_at", "unavailable"}:
            raise ValueError("invalid quote timestamp_source")
        if self.timestamp_source == "exchange_event":
            if self.venue_timestamp is None or self.age_ms is None:
                raise ValueError("exchange_event quotes require venue_timestamp and age_ms")
        elif self.venue_timestamp is not None or self.age_ms is not None:
            raise ValueError("REST/unavailable quotes cannot claim exchange quote age")
        if self.age_ms is not None and self.age_ms < 0:
            raise ValueError("age_ms must be non-negative")
        if self.transport_rtt_ms is not None and self.transport_rtt_ms < 0:
            raise ValueError("transport_rtt_ms must be non-negative")


class PostgresPhase1Ledger:
    """Small repository matching the in-memory Phase 1 ledger contracts."""

    def __init__(self, connection: Connection[Any]) -> None:
        self.connection = connection

    @classmethod
    def connect(cls, dsn: str) -> PostgresPhase1Ledger:
        return cls(psycopg.connect(dsn))

    def close(self) -> None:
        self.connection.close()

    def add_cost_entry(self, row: CostLedgerEntryRow) -> None:
        with self.connection.transaction():
            self.connection.execute(
                """INSERT INTO cost_ledger_entries
                (id,intent_id,cost_ledger_id,category,expected_amount,realized_amount,
                 currency,basis,source,observed_at,metadata)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)""",
                (
                    row.entry_id,
                    row.intent_id,
                    row.cost_ledger_id,
                    row.category,
                    row.expected_amount,
                    row.realized_amount,
                    row.currency,
                    row.basis,
                    row.source,
                    row.observed_at,
                    _json(row.metadata),
                ),
            )

    def add_intent(
        self, row: IntentRow, *, strategy_id: str = "phase1_carry", state: str = "PLANNED"
    ) -> None:
        required = {
            "entry_reason",
            "target_position",
            "normal_exit",
            "risk_exit",
            "max_holding_or_review_at",
            "cost_and_risk_budget",
        }
        missing = required - set(row.fields)
        if missing:
            raise ValueError(f"intent fields missing: {', '.join(sorted(missing))}")
        with self.connection.transaction():
            self.connection.execute(
                """
                INSERT INTO intents (
                    id, run_manifest_id, cost_ledger_id, strategy_id, target_notional, state,
                    entry_reason, target_position, normal_exit, risk_exit,
                    max_holding_or_review_at, cost_and_risk_budget, created_at
                )
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s)
                """,
                (
                    _uuidish(row.intent_id),
                    row.run_manifest_id,
                    row.cost_ledger_id,
                    strategy_id,
                    row.target_notional,
                    state,
                    row.fields["entry_reason"],
                    row.fields["target_position"],
                    row.fields["normal_exit"],
                    row.fields["risk_exit"],
                    datetime.fromisoformat(row.fields["max_holding_or_review_at"]),
                    _json({"value": row.fields["cost_and_risk_budget"]}),
                    row.created_at,
                ),
            )

    def add_risk_decision(
        self,
        row: RiskDecisionRow,
        *,
        observed_leverage: Mapping[str, str] | None = None,
        exposure_before: DecimalInput = "0",
        exposure_after: DecimalInput = "0",
        decision_latency_ms: int = 0,
    ) -> None:
        with self.connection.transaction():
            self.connection.execute(
                "SELECT id FROM intents WHERE id=%s FOR UPDATE", (row.intent_id,)
            )
            self.connection.execute(
                """
                INSERT INTO risk_decisions (
                    id, intent_id, approved, reasons, observed_leverage, quote_age_ms,
                    exposure_before, exposure_after, decision_latency_ms, decided_at
                )
                VALUES (%s,%s,%s,%s::jsonb,%s::jsonb,%s,%s,%s,%s,%s)
                """,
                (
                    _uuidish(row.decision_id),
                    _uuidish(row.intent_id),
                    row.approved,
                    _json(list(row.reasons)),
                    _json(dict(observed_leverage or {})),
                    row.quote_age_ms,
                    as_decimal(exposure_before, field_name="exposure_before"),
                    as_decimal(exposure_after, field_name="exposure_after"),
                    decision_latency_ms,
                    row.decided_at,
                ),
            )

    def add_instrument_snapshot(self, row: InstrumentSnapshotRow) -> None:
        with self.connection.transaction():
            self.connection.execute(
                """
                INSERT INTO instrument_snapshots (
                    id, venue, instrument_id, raw_symbol, price_precision, size_precision,
                    minimum_notional, tick_size, lot_size, status, content_hash, observed_at
                )
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (venue, instrument_id, content_hash) DO NOTHING
                """,
                (
                    _uuidish(row.snapshot_id),
                    row.venue,
                    row.instrument_id,
                    row.raw_symbol,
                    row.price_precision,
                    row.size_precision,
                    row.minimum_notional,
                    row.tick_size,
                    row.lot_size,
                    row.status,
                    row.content_hash,
                    row.observed_at,
                ),
            )

    def add_quote_observation(self, row: QuoteObservationRow) -> None:
        with self.connection.transaction():
            self.connection.execute(
                """
                INSERT INTO quote_observations (
                    id, instrument_snapshot_id, bid, ask, venue_timestamp, received_at,
                    age_ms, collection_mode, transport_rtt_ms, timestamp_source
                )
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    _uuidish(row.quote_id),
                    _uuidish(row.instrument_snapshot_id),
                    row.bid,
                    row.ask,
                    row.venue_timestamp,
                    row.received_at,
                    row.age_ms,
                    row.collection_mode,
                    row.transport_rtt_ms,
                    row.timestamp_source,
                ),
            )

    def add_command(
        self,
        row: OrderCommandRow,
        *,
        attempt: int = 0,
        instrument_id: str = "BTCUSDT.BINANCE",
        side: str = "buy",
        order_type: str = "LIMIT_MAKER",
    ) -> None:
        with self.connection.transaction():
            # Serialize admissions per intent so two workers cannot race the latest
            # approval or the unique active-leg constraint.
            self.connection.execute(
                "SELECT id FROM intents WHERE id=%s FOR UPDATE", (row.intent_id,)
            )
            if not self.has_approved_risk_decision(row.intent_id):
                raise ValueError("a latest approved risk decision is required before a command")
            expected_instrument = "BTCUSDT.BINANCE" if row.leg == "spot" else "BTCUSDT-PERP.BINANCE"
            if instrument_id != expected_instrument:
                raise ValueError("command instrument does not match leg")
            self.connection.execute(
                """
                INSERT INTO order_commands (
                    id, intent_id, leg, attempt, idempotency_key, instrument_id, side,
                    order_type, quantity, price, active, created_at
                )
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    _uuidish(row.command_id),
                    _uuidish(row.intent_id),
                    row.leg,
                    attempt,
                    row.idempotency_key,
                    instrument_id,
                    side,
                    order_type,
                    row.quantity,
                    row.price,
                    row.active,
                    datetime.now(UTC),
                ),
            )

    def deactivate_command(self, command_id: str) -> None:
        with self.connection.transaction():
            self.connection.execute(
                "UPDATE order_commands SET active = FALSE WHERE id = %s", (_uuidish(command_id),)
            )

    def record_order(
        self,
        *,
        order_id: str,
        command_id: str,
        venue: str,
        client_order_id: str,
        status: str,
        venue_order_id: str | None = None,
        filled_quantity: DecimalInput = "0",
        average_price: DecimalInput | None = None,
        reject_code: str | None = None,
        updated_at: datetime | None = None,
    ) -> None:
        with self.connection.transaction():
            current = self.connection.execute(
                "SELECT venue,client_order_id,filled_quantity,status,updated_at,venue_order_id FROM orders WHERE command_id=%s FOR UPDATE",
                (command_id,),
            ).fetchone()
            quantity = as_decimal(filled_quantity, field_name="filled_quantity")
            timestamp = _utc(updated_at or datetime.now(UTC), field_name="updated_at")
            if quantity < 0:
                raise ValueError("filled_quantity cannot be negative")
            if current:
                if (
                    current[0] != venue
                    or current[1] != client_order_id
                    or (current[5] is not None and venue_order_id not in (None, current[5]))
                ):
                    raise ValueError("order identity cannot change")
                if timestamp < current[4] or quantity < current[2]:
                    return  # Stale/reordered event must not undo newer venue evidence.
                terminal = {"FILLED", "CANCELED", "CANCELLED", "REJECTED", "EXPIRED"}
                if current[3] in terminal and status not in terminal:
                    raise ValueError("terminal order cannot become active again")
            self.connection.execute(
                """
                INSERT INTO orders (
                    id, command_id, venue, venue_order_id, client_order_id, status,
                    filled_quantity, average_price, reject_code, updated_at
                )
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (command_id) DO UPDATE SET
                    venue_order_id = COALESCE(EXCLUDED.venue_order_id, orders.venue_order_id),
                    status = EXCLUDED.status,
                    filled_quantity = EXCLUDED.filled_quantity,
                    average_price = EXCLUDED.average_price,
                    reject_code = EXCLUDED.reject_code,
                    updated_at = EXCLUDED.updated_at
                """,
                (
                    _uuidish(order_id),
                    _uuidish(command_id),
                    venue,
                    venue_order_id,
                    client_order_id,
                    status,
                    quantity,
                    as_decimal(average_price, field_name="average_price")
                    if average_price is not None
                    else None,
                    reject_code,
                    timestamp,
                ),
            )

    def add_fill(
        self,
        row: FillRow,
        *,
        order_id: str | None = None,
        fee_amount: DecimalInput = "0",
        fee_token: str = "USDT",
        liquidity_side: str | None = None,
        liquidation_type: str | None = None,
    ) -> None:
        with self.connection.transaction():
            resolved_order_id = self._order_id_for_command(row.command_id)
            if order_id is not None and order_id != resolved_order_id:
                raise ValueError("fill order_id does not match its command")
            self.connection.execute(
                "SELECT id FROM orders WHERE id=%s FOR UPDATE", (resolved_order_id,)
            )
            existing = self.connection.execute(
                "SELECT order_id,quantity,price,fee_amount,fee_token,liquidity_side,liquidation_type,filled_at FROM fills WHERE venue=%s AND venue_fill_id=%s",
                (row.venue, row.venue_fill_id),
            ).fetchone()
            expected = (
                resolved_order_id,
                row.quantity,
                row.price,
                as_decimal(fee_amount, field_name="fee_amount"),
                fee_token,
                liquidity_side,
                liquidation_type,
                row.filled_at,
            )
            if existing:
                if (str(existing[0]), *existing[1:]) != expected:
                    raise ValueError("duplicate fill conflicts with durable evidence")
                return
            self.connection.execute(
                """
                INSERT INTO fills (
                    id, order_id, venue, venue_fill_id, quantity, price, fee_amount,
                    fee_token, liquidity_side, liquidation_type, filled_at
                )
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    _uuidish(row.fill_id),
                    _uuidish(resolved_order_id),
                    row.venue,
                    row.venue_fill_id,
                    row.quantity,
                    row.price,
                    as_decimal(fee_amount, field_name="fee_amount"),
                    fee_token,
                    liquidity_side,
                    liquidation_type,
                    row.filled_at,
                ),
            )

    def add_transition(self, row: TransitionRow) -> None:
        with self.connection.transaction():
            if row.accepted:
                from .state_machine import ALLOWED_TRANSITIONS

                if (row.from_state, row.to_state) not in ALLOWED_TRANSITIONS or not all(
                    row.guards.values()
                ):
                    raise ValueError("invalid accepted transition")
                current = self.connection.execute(
                    "SELECT state FROM intents WHERE id=%s FOR UPDATE", (row.intent_id,)
                ).fetchone()
                expected_from = row.from_state or "PLANNED"
                if current is None or current[0] != expected_from:
                    raise ValueError("concurrent or stale transition")
                self.connection.execute(
                    "UPDATE intents SET state=%s WHERE id=%s", (row.to_state, row.intent_id)
                )
            self.connection.execute(
                """
                INSERT INTO state_transitions (
                    id, intent_id, from_state, to_state, trigger, guard_results, accepted, recorded_at
                )
                VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s,%s)
                """,
                (
                    _uuidish(row.transition_id),
                    _uuidish(row.intent_id),
                    row.from_state,
                    row.to_state,
                    row.trigger,
                    _json(row.guards),
                    row.accepted,
                    row.recorded_at,
                ),
            )

    def add_transfer(self, row: InternalTransferRow) -> None:
        with self.connection.transaction():
            self.connection.execute(
                """
                INSERT INTO internal_transfers (
                    id, intent_id, asset, amount, from_wallet, to_wallet,
                    idempotency_key, requested_at, confirmed_at, status
                )
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    _uuidish(row.transfer_id),
                    _uuidish(row.intent_id),
                    row.asset,
                    row.amount,
                    row.from_wallet,
                    row.to_wallet,
                    row.idempotency_key,
                    row.requested_at,
                    row.confirmed_at,
                    row.status,
                ),
            )

    def add_incident(self, row: IncidentRow, *, status: str = "open") -> None:
        with self.connection.transaction():
            self.connection.execute(
                """
                INSERT INTO incidents (id, intent_id, category, severity, status, detail, opened_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    _uuidish(row.incident_id),
                    row.intent_id,
                    row.category,
                    row.severity,
                    status,
                    row.detail,
                    row.opened_at,
                ),
            )

    def record_reconciliation(
        self,
        *,
        run_id: str,
        intent_id: str | None,
        explained_residual: DecimalInput,
        unexplained_residual: DecimalInput,
        currency: str,
        result: str,
        detail: Mapping[str, Any],
        started_at: datetime,
        completed_at: datetime | None = None,
    ) -> None:
        with self.connection.transaction():
            self.connection.execute(
                """
                INSERT INTO reconciliation_runs (
                    id, intent_id, explained_residual, unexplained_residual, currency,
                    result, detail, started_at, completed_at
                )
                VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s)
                """,
                (
                    _uuidish(run_id),
                    intent_id,
                    as_decimal(explained_residual, field_name="explained_residual"),
                    as_decimal(unexplained_residual, field_name="unexplained_residual"),
                    currency,
                    result,
                    _json(dict(detail)),
                    _utc(started_at, field_name="started_at"),
                    _utc(completed_at, field_name="completed_at") if completed_at else None,
                ),
            )

    def has_approved_risk_decision(self, intent_id: str) -> bool:
        with self.connection.cursor(row_factory=dict_row) as cursor:
            row = cursor.execute(
                "SELECT approved FROM risk_decisions WHERE intent_id = %s ORDER BY decided_at DESC, id DESC LIMIT 1",
                (_uuidish(intent_id),),
            ).fetchone()
        return bool(row and row["approved"])

    def active_commands(self, intent_id: str) -> tuple[dict[str, Any], ...]:
        with self.connection.cursor(row_factory=dict_row) as cursor:
            rows = cursor.execute(
                """
                SELECT id, intent_id, leg, idempotency_key, quantity, price, active
                FROM order_commands
                WHERE intent_id = %s AND active
                ORDER BY leg
                """,
                (_uuidish(intent_id),),
            ).fetchall()
        return tuple(dict(row) for row in rows)

    def _order_id_for_command(self, command_id: str) -> str:
        with self.connection.cursor(row_factory=dict_row) as cursor:
            row = cursor.execute(
                "SELECT id FROM orders WHERE command_id = %s",
                (_uuidish(command_id),),
            ).fetchone()
        if row is None:
            raise ValueError("fill references a command with no recorded order")
        return str(row["id"])


def migration_paths(direction: str = "up") -> tuple[Path, ...]:
    if direction not in {"up", "down"}:
        raise ValueError("direction must be up or down")
    paths = sorted(MIGRATION_ROOT.glob(f"*.{direction}.sql"))
    return tuple(paths if direction == "up" else reversed(paths))


def apply_migrations(connection: Connection[Any], *, direction: str = "up") -> tuple[str, ...]:
    paths = migration_paths(direction)
    applied: list[str] = []
    with connection.transaction():
        connection.execute("SELECT pg_advisory_xact_lock(31092026)")
        connection.execute("""CREATE TABLE IF NOT EXISTS phase1_schema_migrations
            (name TEXT PRIMARY KEY, sha256 CHAR(64) NOT NULL)""")
        for path in paths:
            up_name = path.name.replace(".down.sql", ".up.sql")
            digest = hashlib.sha256((MIGRATION_ROOT / up_name).read_bytes()).hexdigest()
            existing = connection.execute(
                "SELECT sha256 FROM phase1_schema_migrations WHERE name=%s", (up_name,)
            ).fetchone()
            if existing and existing[0] != digest:
                raise ValueError("applied migration checksum changed")
            if (direction == "up" and existing) or (direction == "down" and not existing):
                continue
            sql = path.read_text().strip().removeprefix("BEGIN;").removesuffix("COMMIT;")
            connection.execute(sql)
            if direction == "up":
                connection.execute(
                    "INSERT INTO phase1_schema_migrations VALUES (%s,%s)", (up_name, digest)
                )
            else:
                connection.execute("DELETE FROM phase1_schema_migrations WHERE name=%s", (up_name,))
            applied.append(path.name)
    return tuple(applied)
