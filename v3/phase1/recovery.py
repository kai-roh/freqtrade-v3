"""Order-free restart recovery and invariant enforcement."""

from __future__ import annotations

from dataclasses import dataclass

from .state_machine import IntentState, InvariantSnapshot, invariant_violations


@dataclass(frozen=True)
class RecoveryInput:
    exchange_snapshot_complete: bool
    missing_fills_applied: int
    open_order_count: int
    spot_notional_is_zero: bool
    perp_notional_is_zero: bool
    invariants: InvariantSnapshot


@dataclass(frozen=True)
class RecoveryResult:
    state: IntentState
    order_submission_enabled: bool
    missing_fills_applied: int
    violations: tuple[str, ...]
    incident_required: bool


def recover_without_submission(recovery: RecoveryInput) -> RecoveryResult:
    violations = list(invariant_violations(recovery.invariants))
    if not recovery.exchange_snapshot_complete:
        violations.append("exchange recovery snapshot is incomplete")
    if recovery.missing_fills_applied < 0 or recovery.open_order_count < 0:
        violations.append("recovery counts must be non-negative")

    if violations:
        state = IntentState.RECONCILIATION_BLOCKED
    elif (
        recovery.open_order_count == 0
        and recovery.spot_notional_is_zero
        and recovery.perp_notional_is_zero
    ):
        state = IntentState.CLOSED
    elif recovery.invariants.state == IntentState.HEDGED:
        state = IntentState.HEDGED
    else:
        state = IntentState.RECONCILING
    return RecoveryResult(
        state=state,
        order_submission_enabled=False,
        missing_fills_applied=recovery.missing_fills_applied,
        violations=tuple(violations),
        incident_required=bool(violations),
    )
