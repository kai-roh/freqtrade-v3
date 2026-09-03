"""Two-leg carry aggregate with an explicit, audited transition graph."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from v3.costs import DecimalInput, as_decimal

from .ledger import InMemoryPhase1Ledger, TransitionRow


class IntentState(StrEnum):
    PLANNED = "PLANNED"
    RISK_APPROVED = "RISK_APPROVED"
    TRANSFERRING = "TRANSFERRING"
    SUBMITTING = "SUBMITTING"
    PARTIALLY_HEDGED = "PARTIALLY_HEDGED"
    HEDGE_REQUIRED = "HEDGE_REQUIRED"
    HEDGED = "HEDGED"
    RECONCILING = "RECONCILING"
    RECONCILIATION_BLOCKED = "RECONCILIATION_BLOCKED"
    ABORTING = "ABORTING"
    CLOSED = "CLOSED"


ALLOWED_TRANSITIONS = frozenset(
    {
        (None, IntentState.PLANNED),
        (IntentState.PLANNED, IntentState.RISK_APPROVED),
        (IntentState.PLANNED, IntentState.ABORTING),
        (IntentState.RISK_APPROVED, IntentState.SUBMITTING),
        (IntentState.RISK_APPROVED, IntentState.TRANSFERRING),
        (IntentState.TRANSFERRING, IntentState.SUBMITTING),
        (IntentState.TRANSFERRING, IntentState.ABORTING),
        (IntentState.SUBMITTING, IntentState.PARTIALLY_HEDGED),
        (IntentState.SUBMITTING, IntentState.HEDGED),
        (IntentState.SUBMITTING, IntentState.ABORTING),
        (IntentState.PARTIALLY_HEDGED, IntentState.HEDGED),
        (IntentState.PARTIALLY_HEDGED, IntentState.HEDGE_REQUIRED),
        (IntentState.HEDGE_REQUIRED, IntentState.HEDGED),
        (IntentState.HEDGE_REQUIRED, IntentState.ABORTING),
        (IntentState.HEDGED, IntentState.RECONCILING),
        (IntentState.RECONCILING, IntentState.HEDGED),
        (IntentState.RECONCILING, IntentState.RECONCILIATION_BLOCKED),
        (IntentState.RECONCILING, IntentState.CLOSED),
        (IntentState.ABORTING, IntentState.CLOSED),
        (IntentState.ABORTING, IntentState.HEDGE_REQUIRED),
        (IntentState.RECONCILIATION_BLOCKED, IntentState.RECONCILING),
    }
)


class TransitionRejected(ValueError):
    pass


@dataclass
class CarryStateMachine:
    intent_id: str
    ledger: InMemoryPhase1Ledger
    state: IntentState | None = None

    def transition(
        self,
        to_state: IntentState,
        *,
        trigger: str,
        guards: dict[str, bool],
        recorded_at: datetime | None = None,
    ) -> IntentState:
        if not trigger.strip():
            raise ValueError("transition trigger is required")
        accepted = (self.state, to_state) in ALLOWED_TRANSITIONS and all(guards.values())
        row = TransitionRow(
            transition_id=str(uuid.uuid4()),
            intent_id=self.intent_id,
            from_state=self.state.value if self.state is not None else None,
            to_state=to_state.value,
            trigger=trigger,
            guards=dict(guards),
            accepted=accepted,
            recorded_at=recorded_at or datetime.now(UTC),
        )
        self.ledger.add_transition(row)
        if not accepted:
            failed = [name for name, passed in guards.items() if not passed]
            detail = f"; failed guards={','.join(failed)}" if failed else ""
            raise TransitionRejected(
                f"transition {self.state!s}->{to_state.value} is not allowed{detail}"
            )
        self.state = to_state
        return self.state


@dataclass(frozen=True)
class InvariantSnapshot:
    state: IntentState
    active_commands_by_leg: dict[str, int]
    spot_notional: DecimalInput
    perp_notional: DecimalInput
    maximum_delta_drift_fraction: DecimalInput
    local_positions: dict[str, DecimalInput]
    venue_positions: dict[str, DecimalInput]
    rounding_tolerance: DecimalInput
    known_order_ids: frozenset[str]
    fill_order_ids: tuple[str, ...]
    venue_fill_keys: tuple[tuple[str, str], ...]
    has_approved_risk_decision: bool
    unhedged_notional_milliseconds: DecimalInput
    maximum_unhedged_notional_milliseconds: DecimalInput

    def __post_init__(self) -> None:
        for name in (
            "spot_notional",
            "perp_notional",
            "maximum_delta_drift_fraction",
            "rounding_tolerance",
            "unhedged_notional_milliseconds",
            "maximum_unhedged_notional_milliseconds",
        ):
            object.__setattr__(self, name, as_decimal(getattr(self, name), field_name=name))


def invariant_violations(snapshot: InvariantSnapshot) -> tuple[str, ...]:
    violations: list[str] = []
    if any(count > 1 for count in snapshot.active_commands_by_leg.values()):
        violations.append("more than one active command exists for an intent leg")

    if snapshot.state == IntentState.HEDGED:
        larger = max(abs(snapshot.spot_notional), abs(snapshot.perp_notional))
        drift = abs(abs(snapshot.spot_notional) - abs(snapshot.perp_notional))
        if larger == 0 or drift / larger > snapshot.maximum_delta_drift_fraction:
            violations.append("hedged notional drift exceeds policy")

    instruments = set(snapshot.local_positions) | set(snapshot.venue_positions)
    for instrument in instruments:
        local = as_decimal(snapshot.local_positions.get(instrument, 0), field_name="local_position")
        venue = as_decimal(snapshot.venue_positions.get(instrument, 0), field_name="venue_position")
        if abs(local - venue) > snapshot.rounding_tolerance:
            violations.append(f"position mismatch for {instrument}")

    if any(order_id not in snapshot.known_order_ids for order_id in snapshot.fill_order_ids):
        violations.append("fill references an unknown order")
    if len(set(snapshot.venue_fill_keys)) != len(snapshot.venue_fill_keys):
        violations.append("duplicate venue fill ID")
    if (
        snapshot.state
        in {
            IntentState.SUBMITTING,
            IntentState.PARTIALLY_HEDGED,
            IntentState.HEDGE_REQUIRED,
            IntentState.HEDGED,
        }
        and not snapshot.has_approved_risk_decision
    ):
        violations.append("submitting state has no approved risk decision")
    if snapshot.unhedged_notional_milliseconds > snapshot.maximum_unhedged_notional_milliseconds:
        violations.append("unhedged notional-duration budget exceeded")
    return tuple(violations)


def transition_contract() -> list[dict[str, Any]]:
    return [
        {
            "from": source.value if source is not None else None,
            "to": target.value,
        }
        for source, target in sorted(
            ALLOWED_TRANSITIONS,
            key=lambda pair: ((pair[0].value if pair[0] is not None else ""), pair[1].value),
        )
    ]
