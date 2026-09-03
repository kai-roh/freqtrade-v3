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
