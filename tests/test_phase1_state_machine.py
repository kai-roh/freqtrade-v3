from datetime import UTC, datetime

import pytest

from v3.phase1.ledger import InMemoryPhase1Ledger, IntentRow
from v3.phase1.state_machine import (
    ALLOWED_TRANSITIONS,
    CarryStateMachine,
    IntentState,
    InvariantSnapshot,
    TransitionRejected,
    invariant_violations,
)

NOW = datetime(2026, 8, 25, tzinfo=UTC)


def _machine():
    ledger = InMemoryPhase1Ledger()
    ledger.add_intent(IntentRow("intent-1", "manifest", "cost", "300", {}, NOW))
    return CarryStateMachine("intent-1", ledger), ledger


def test_transition_contract_contains_21_paths_including_direct_and_transfer_routes():
    assert len(ALLOWED_TRANSITIONS) == 21
    assert (IntentState.RISK_APPROVED, IntentState.SUBMITTING) in ALLOWED_TRANSITIONS
    assert (IntentState.RISK_APPROVED, IntentState.TRANSFERRING) in ALLOWED_TRANSITIONS
    assert (IntentState.TRANSFERRING, IntentState.SUBMITTING) in ALLOWED_TRANSITIONS
    assert (IntentState.TRANSFERRING, IntentState.ABORTING) in ALLOWED_TRANSITIONS


@pytest.mark.parametrize("source,target", sorted(ALLOWED_TRANSITIONS, key=str))
def test_every_registered_transition_is_accepted(source, target):
    machine, ledger = _machine()
    machine.state = source

    assert machine.transition(target, trigger="fixture", guards={"fixture": True}) == target
    assert ledger.transitions[-1].accepted


def test_invalid_or_failed_guard_transition_is_recorded_before_rejection():
    machine, ledger = _machine()
    machine.state = IntentState.PLANNED

    with pytest.raises(TransitionRejected):
        machine.transition(IntentState.HEDGED, trigger="skip", guards={"risk": True})
    assert not ledger.transitions[-1].accepted

    with pytest.raises(TransitionRejected, match="failed guards=balance"):
        machine.transition(
            IntentState.RISK_APPROVED,
            trigger="risk",
            guards={"balance": False},
        )
    assert len(ledger.transitions) == 2


def _snapshot(**overrides):
    values = {
        "state": IntentState.HEDGED,
        "active_commands_by_leg": {"spot": 1, "perp": 1},
        "spot_notional": "100",
        "perp_notional": "98",
        "maximum_delta_drift_fraction": "0.05",
        "local_positions": {"spot": "1", "perp": "-1"},
        "venue_positions": {"spot": "1", "perp": "-1"},
        "rounding_tolerance": "0.001",
        "known_order_ids": frozenset({"order-1", "order-2"}),
        "fill_order_ids": ("order-1", "order-2"),
        "venue_fill_keys": (("binance", "fill-1"), ("binance", "fill-2")),
        "has_approved_risk_decision": True,
        "unhedged_notional_milliseconds": "1000",
        "maximum_unhedged_notional_milliseconds": "2000",
    }
    values.update(overrides)
    return InvariantSnapshot(**values)


def test_all_six_invariants_pass_for_a_consistent_hedged_snapshot():
    assert not invariant_violations(_snapshot())


def test_invariant_checker_reports_command_delta_position_fill_risk_and_duration():
    violations = invariant_violations(
        _snapshot(
            active_commands_by_leg={"spot": 2, "perp": 1},
            perp_notional="80",
            venue_positions={"spot": "0.5", "perp": "-1"},
            fill_order_ids=("missing",),
            venue_fill_keys=(("binance", "same"), ("binance", "same")),
            has_approved_risk_decision=False,
            unhedged_notional_milliseconds="3000",
        )
    )

    assert len(violations) == 7
