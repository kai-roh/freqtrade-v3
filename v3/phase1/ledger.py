"""Deterministic Phase 1 ledger contracts used by simulation and adapters."""

from __future__ import annotations

import copy
import hashlib
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from v3.costs import DecimalInput, as_decimal


def _utc(value: datetime, *, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must include a timezone")
    return value.astimezone(UTC)


def command_idempotency_key(
    *,
    intent_id: str,
    leg: str,
    attempt: int,
    quantity: DecimalInput,
    price: DecimalInput,
) -> str:
    if not intent_id.strip() or leg not in {"spot", "perp"}:
        raise ValueError("valid intent_id and leg are required")
    if attempt < 0:
        raise ValueError("attempt must be non-negative")
    exact_quantity = as_decimal(quantity, field_name="quantity")
    exact_price = as_decimal(price, field_name="price")
    if exact_quantity <= 0 or exact_price <= 0:
        raise ValueError("quantity and price must be positive")
    payload = f"{intent_id}:{leg}:{attempt}:{exact_quantity}:{exact_price}"
    return hashlib.sha256(payload.encode()).hexdigest()[:32]


@dataclass(frozen=True)
class IntentRow:
    intent_id: str
    run_manifest_id: str
    cost_ledger_id: str
    target_notional: DecimalInput
    fields: dict[str, str]
    created_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "target_notional", as_decimal(self.target_notional, field_name="target_notional")
        )
        object.__setattr__(self, "created_at", _utc(self.created_at, field_name="created_at"))
        for name in ("intent_id", "run_manifest_id", "cost_ledger_id"):
            if not getattr(self, name).strip():
                raise ValueError(f"{name} is required")
        if self.target_notional <= 0:
            raise ValueError("target_notional must be positive")


@dataclass(frozen=True)
class RiskDecisionRow:
    decision_id: str
    intent_id: str
    approved: bool
    reasons: tuple[str, ...]
    quote_age_ms: int | None
    decided_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "decided_at", _utc(self.decided_at, field_name="decided_at"))
        if self.quote_age_ms is not None and self.quote_age_ms < 0:
            raise ValueError("quote_age_ms must be non-negative")


@dataclass(frozen=True)
class CostLedgerEntryRow:
    entry_id: str
    intent_id: str
    cost_ledger_id: str
    category: str
    expected_amount: DecimalInput | None
    realized_amount: DecimalInput | None
    currency: str
    basis: str
    source: str
    observed_at: datetime | None
    metadata: dict[str, Any]

    def __post_init__(self) -> None:
        for name in ("entry_id", "intent_id", "cost_ledger_id", "category", "currency", "basis"):
            if not getattr(self, name).strip():
                raise ValueError(f"{name} is required")
        for name in ("expected_amount", "realized_amount"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, as_decimal(value, field_name=name))
        if self.observed_at is not None:
            object.__setattr__(
                self, "observed_at", _utc(self.observed_at, field_name="observed_at")
            )


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
        for name in ("snapshot_id", "venue", "instrument_id", "raw_symbol", "status"):
            if not getattr(self, name).strip():
                raise ValueError(f"{name} is required")
        for name in ("minimum_notional", "tick_size", "lot_size"):
            object.__setattr__(self, name, as_decimal(getattr(self, name), field_name=name))
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} must be positive")
        if self.price_precision < 0 or self.size_precision < 0:
            raise ValueError("precision values must be non-negative")
        if len(self.content_hash) != 64:
            raise ValueError("content_hash must be a SHA-256 hex digest")
        object.__setattr__(self, "observed_at", _utc(self.observed_at, field_name="observed_at"))


@dataclass(frozen=True)
class QuoteObservationRow:
    quote_id: str
    instrument_snapshot_id: str
    bid: DecimalInput
    ask: DecimalInput
    venue_timestamp: datetime
    received_at: datetime
    age_ms: int
    collection_mode: str

    def __post_init__(self) -> None:
        for name in ("quote_id", "instrument_snapshot_id"):
            if not getattr(self, name).strip():
                raise ValueError(f"{name} is required")
        object.__setattr__(self, "bid", as_decimal(self.bid, field_name="bid"))
        object.__setattr__(self, "ask", as_decimal(self.ask, field_name="ask"))
        if self.bid <= 0 or self.ask < self.bid:
            raise ValueError("quote bid/ask are invalid")
        if self.age_ms < 0:
            raise ValueError("age_ms must be non-negative")
        if self.collection_mode not in {"risk_decision", "phase1e_sample"}:
            raise ValueError("invalid quote collection mode")
        object.__setattr__(
            self, "venue_timestamp", _utc(self.venue_timestamp, field_name="venue_timestamp")
        )
        object.__setattr__(self, "received_at", _utc(self.received_at, field_name="received_at"))


@dataclass
class OrderCommandRow:
    command_id: str
    intent_id: str
    leg: str
    idempotency_key: str
    quantity: DecimalInput
    price: DecimalInput
    active: bool = True

    def __post_init__(self) -> None:
        self.quantity = as_decimal(self.quantity, field_name="quantity")
        self.price = as_decimal(self.price, field_name="price")
        if self.leg not in {"spot", "perp"}:
            raise ValueError("leg must be spot or perp")
        if self.quantity <= 0 or self.price <= 0:
            raise ValueError("quantity and price must be positive")


@dataclass(frozen=True)
class FillRow:
    fill_id: str
    venue: str
    venue_fill_id: str
    command_id: str
    quantity: DecimalInput
    price: DecimalInput
    filled_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "quantity", as_decimal(self.quantity, field_name="quantity"))
        object.__setattr__(self, "price", as_decimal(self.price, field_name="price"))
        object.__setattr__(self, "filled_at", _utc(self.filled_at, field_name="filled_at"))
        if self.quantity <= 0 or self.price <= 0:
            raise ValueError("fill quantity and price must be positive")


@dataclass(frozen=True)
class InternalTransferRow:
    transfer_id: str
    intent_id: str
    asset: str
    amount: DecimalInput
    from_wallet: str
    to_wallet: str
    idempotency_key: str
    status: str
    requested_at: datetime
    confirmed_at: datetime | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "amount", as_decimal(self.amount, field_name="amount"))
        object.__setattr__(self, "requested_at", _utc(self.requested_at, field_name="requested_at"))
        if self.confirmed_at is not None:
            object.__setattr__(
                self, "confirmed_at", _utc(self.confirmed_at, field_name="confirmed_at")
            )
        if self.amount <= 0:
            raise ValueError("transfer amount must be positive")
        if self.status not in {"requested", "confirmed", "failed"}:
            raise ValueError("invalid transfer status")


@dataclass(frozen=True)
class TransitionRow:
    transition_id: str
    intent_id: str
    from_state: str | None
    to_state: str
    trigger: str
    guards: dict[str, bool]
    accepted: bool
    recorded_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "recorded_at", _utc(self.recorded_at, field_name="recorded_at"))


@dataclass(frozen=True)
class IncidentRow:
    incident_id: str
    intent_id: str | None
    category: str
    severity: str
    detail: str
    opened_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "opened_at", _utc(self.opened_at, field_name="opened_at"))


@dataclass
class InMemoryPhase1Ledger:
    """Strict in-memory repository for fixtures; production schema is PostgreSQL."""

    intents: dict[str, IntentRow] = field(default_factory=dict)
    risk_decisions: dict[str, RiskDecisionRow] = field(default_factory=dict)
    cost_entries: dict[str, CostLedgerEntryRow] = field(default_factory=dict)
    instrument_snapshots: dict[str, InstrumentSnapshotRow] = field(default_factory=dict)
    quote_observations: dict[str, QuoteObservationRow] = field(default_factory=dict)
    commands: dict[str, OrderCommandRow] = field(default_factory=dict)
    fills: dict[str, FillRow] = field(default_factory=dict)
    transfers: dict[str, InternalTransferRow] = field(default_factory=dict)
    transitions: list[TransitionRow] = field(default_factory=list)
    incidents: dict[str, IncidentRow] = field(default_factory=dict)

    def add_intent(self, row: IntentRow) -> None:
        if row.intent_id in self.intents:
            raise ValueError("duplicate intent_id")
        self.intents[row.intent_id] = row

    def add_risk_decision(self, row: RiskDecisionRow) -> None:
        self._require_intent(row.intent_id)
        if row.decision_id in self.risk_decisions:
            raise ValueError("duplicate decision_id")
        self.risk_decisions[row.decision_id] = row

    def add_cost_entry(self, row: CostLedgerEntryRow) -> None:
        self._require_intent(row.intent_id)
        if row.entry_id in self.cost_entries:
            raise ValueError("duplicate cost entry")
        self.cost_entries[row.entry_id] = row

    def add_instrument_snapshot(self, row: InstrumentSnapshotRow) -> None:
        if row.snapshot_id in self.instrument_snapshots:
            raise ValueError("duplicate instrument snapshot")
        unique_key = (row.venue, row.instrument_id, row.content_hash)
        if any(
            (snapshot.venue, snapshot.instrument_id, snapshot.content_hash) == unique_key
            for snapshot in self.instrument_snapshots.values()
        ):
            raise ValueError("duplicate instrument content snapshot")
        self.instrument_snapshots[row.snapshot_id] = row

    def add_quote_observation(self, row: QuoteObservationRow) -> None:
        if row.instrument_snapshot_id not in self.instrument_snapshots:
            raise ValueError("quote references an unknown instrument snapshot")
        if row.quote_id in self.quote_observations:
            raise ValueError("duplicate quote observation")
        self.quote_observations[row.quote_id] = row

    def add_command(self, row: OrderCommandRow) -> None:
        self._require_intent(row.intent_id)
        if row.command_id in self.commands:
            raise ValueError("duplicate command_id")
        if any(
            command.idempotency_key == row.idempotency_key for command in self.commands.values()
        ):
            raise ValueError("duplicate idempotency_key")
        if any(
            command.intent_id == row.intent_id and command.leg == row.leg and command.active
            for command in self.commands.values()
        ):
            raise ValueError("intent already has an active command for this leg")
        self.commands[row.command_id] = row

    def deactivate_command(self, command_id: str) -> None:
        self.commands[command_id].active = False

    def add_fill(self, row: FillRow) -> None:
        if row.command_id not in self.commands:
            raise ValueError("fill references an unknown command")
        key = (row.venue, row.venue_fill_id)
        if any((fill.venue, fill.venue_fill_id) == key for fill in self.fills.values()):
            raise ValueError("duplicate venue fill ID")
        if row.fill_id in self.fills:
            raise ValueError("duplicate fill_id")
        self.fills[row.fill_id] = row

    def add_transfer(self, row: InternalTransferRow) -> None:
        self._require_intent(row.intent_id)
        if row.transfer_id in self.transfers:
            raise ValueError("duplicate transfer_id")
        if any(
            transfer.idempotency_key == row.idempotency_key for transfer in self.transfers.values()
        ):
            raise ValueError("duplicate transfer idempotency_key")
        self.transfers[row.transfer_id] = row

    def add_transition(self, row: TransitionRow) -> None:
        self._require_intent(row.intent_id)
        self.transitions.append(row)

    def add_incident(self, row: IncidentRow) -> None:
        if row.incident_id in self.incidents:
            raise ValueError("duplicate incident_id")
        if row.intent_id is not None:
            self._require_intent(row.intent_id)
        self.incidents[row.incident_id] = row

    def has_approved_risk_decision(self, intent_id: str) -> bool:
        return any(
            decision.intent_id == intent_id and decision.approved
            for decision in self.risk_decisions.values()
        )

    def active_commands(self, intent_id: str) -> tuple[OrderCommandRow, ...]:
        return tuple(
            command
            for command in self.commands.values()
            if command.intent_id == intent_id and command.active
        )

    def snapshot(self) -> dict[str, Any]:
        return copy.deepcopy(self.__dict__)

    @classmethod
    def restore(cls, snapshot: dict[str, Any]) -> InMemoryPhase1Ledger:
        restored = cls()
        for name in restored.__dict__:
            setattr(restored, name, copy.deepcopy(snapshot[name]))
        return restored

    def _require_intent(self, intent_id: str) -> None:
        if intent_id not in self.intents:
            raise ValueError("unknown intent_id")


class PostgresPhase1Ledger:
    """Small psycopg-compatible repository for the Phase 1 persistent audit ledger."""

    def __init__(self, connection: Any) -> None:
        self.connection = connection

    def add_intent(self, row: IntentRow) -> None:
        self.connection.execute(
            """
            INSERT INTO intents (
                id, run_manifest_id, cost_ledger_id, strategy_id, target_notional, state,
                entry_reason, target_position, normal_exit, risk_exit,
                max_holding_or_review_at, cost_and_risk_budget, created_at
            )
            VALUES (
                %(id)s, %(run_manifest_id)s, %(cost_ledger_id)s, %(strategy_id)s,
                %(target_notional)s, %(state)s, %(entry_reason)s, %(target_position)s,
                %(normal_exit)s, %(risk_exit)s, %(max_holding_or_review_at)s,
                %(cost_and_risk_budget)s, %(created_at)s
            )
            """,
            {
                "id": row.intent_id,
                "run_manifest_id": row.run_manifest_id,
                "cost_ledger_id": row.cost_ledger_id,
                "strategy_id": row.fields.get("strategy_id", "phase1_carry"),
                "target_notional": row.target_notional,
                "state": row.fields.get("state", "PLANNED"),
                "entry_reason": row.fields["entry_reason"],
                "target_position": row.fields["target_position"],
                "normal_exit": row.fields["normal_exit"],
                "risk_exit": row.fields["risk_exit"],
                "max_holding_or_review_at": row.fields["max_holding_or_review_at"],
                "cost_and_risk_budget": row.fields["cost_and_risk_budget"],
                "created_at": row.created_at,
            },
        )

    def add_cost_entry(self, row: CostLedgerEntryRow) -> None:
        self.connection.execute(
            """
            INSERT INTO cost_ledger_entries (
                id, intent_id, cost_ledger_id, category, expected_amount, realized_amount,
                currency, basis, source, observed_at, metadata
            )
            VALUES (
                %(id)s, %(intent_id)s, %(cost_ledger_id)s, %(category)s,
                %(expected_amount)s, %(realized_amount)s, %(currency)s, %(basis)s,
                %(source)s, %(observed_at)s, %(metadata)s
            )
            """,
            _row_dict(row, "entry_id", "id"),
        )

    def add_risk_decision(
        self,
        row: RiskDecisionRow,
        *,
        observed_leverage: dict[str, str],
        exposure_before: DecimalInput,
        exposure_after: DecimalInput,
        decision_latency_ms: int,
    ) -> None:
        if decision_latency_ms < 0:
            raise ValueError("decision_latency_ms must be non-negative")
        self.connection.execute(
            """
            INSERT INTO risk_decisions (
                id, intent_id, approved, reasons, observed_leverage, quote_age_ms,
                exposure_before, exposure_after, decision_latency_ms, decided_at
            )
            VALUES (
                %(id)s, %(intent_id)s, %(approved)s, %(reasons)s, %(observed_leverage)s,
                %(quote_age_ms)s, %(exposure_before)s, %(exposure_after)s,
                %(decision_latency_ms)s, %(decided_at)s
            )
            """,
            {
                "id": row.decision_id,
                "intent_id": row.intent_id,
                "approved": row.approved,
                "reasons": list(row.reasons),
                "observed_leverage": dict(observed_leverage),
                "quote_age_ms": row.quote_age_ms,
                "exposure_before": as_decimal(exposure_before, field_name="exposure_before"),
                "exposure_after": as_decimal(exposure_after, field_name="exposure_after"),
                "decision_latency_ms": decision_latency_ms,
                "decided_at": row.decided_at,
            },
        )

    def add_instrument_snapshot(self, row: InstrumentSnapshotRow) -> None:
        self.connection.execute(
            """
            INSERT INTO instrument_snapshots (
                id, venue, instrument_id, raw_symbol, price_precision, size_precision,
                minimum_notional, tick_size, lot_size, status, content_hash, observed_at
            )
            VALUES (
                %(id)s, %(venue)s, %(instrument_id)s, %(raw_symbol)s, %(price_precision)s,
                %(size_precision)s, %(minimum_notional)s, %(tick_size)s, %(lot_size)s,
                %(status)s, %(content_hash)s, %(observed_at)s
            )
            """,
            _row_dict(row, "snapshot_id", "id"),
        )

    def add_quote_observation(self, row: QuoteObservationRow) -> None:
        self.connection.execute(
            """
            INSERT INTO quote_observations (
                id, instrument_snapshot_id, bid, ask, venue_timestamp, received_at, age_ms,
                collection_mode
            )
            VALUES (
                %(id)s, %(instrument_snapshot_id)s, %(bid)s, %(ask)s, %(venue_timestamp)s,
                %(received_at)s, %(age_ms)s, %(collection_mode)s
            )
            """,
            _row_dict(row, "quote_id", "id"),
        )


def _row_dict(row: Any, source_name: str, target_name: str) -> dict[str, Any]:
    values = dict(row.__dict__)
    values[target_name] = values.pop(source_name)
    return values
