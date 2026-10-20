"""Deterministic Phase 1 fault-replay contract.

This suite validates orchestration and audit behavior only. It does not claim
to measure live fill quality, adverse selection, or a live abort probability.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from .ledger import IncidentRow, InMemoryPhase1Ledger, IntentRow
from .state_machine import CarryStateMachine, IntentState

FIXTURE_TIME = datetime(2026, 8, 25, tzinfo=UTC)


@dataclass(frozen=True)
class FaultScenario:
    name: str
    states: tuple[IntentState, ...]
    submitted_order_count: int
    incident_category: str | None = None
    orphan_fill_count: int = 0
    unexplained_residual: str = "0"


@dataclass(frozen=True)
class FaultResult:
    name: str
    final_state: IntentState
    transition_count: int
    submitted_order_count: int
    orphan_fill_count: int
    unexplained_residual: str
    incident_count: int

    @property
    def passed(self) -> bool:
        return self.orphan_fill_count == 0 and self.unexplained_residual == "0"

    def to_dict(self) -> dict[str, str | int | bool]:
        return {
            "name": self.name,
            "final_state": self.final_state.value,
            "transition_count": self.transition_count,
            "submitted_order_count": self.submitted_order_count,
            "orphan_fill_count": self.orphan_fill_count,
            "unexplained_residual": self.unexplained_residual,
            "incident_count": self.incident_count,
            "passed": self.passed,
        }


def _path(*states: IntentState) -> tuple[IntentState, ...]:
    return states


FAULT_SCENARIOS = (
    FaultScenario(
        "first_leg_only",
        _path(
            IntentState.PLANNED,
            IntentState.RISK_APPROVED,
            IntentState.SUBMITTING,
            IntentState.PARTIALLY_HEDGED,
            IntentState.HEDGE_REQUIRED,
            IntentState.HEDGED,
        ),
        3,
        "hedge_sla",
    ),
    FaultScenario(
        "partial_fill_then_websocket_disconnect",
        _path(
            IntentState.PLANNED,
            IntentState.RISK_APPROVED,
            IntentState.SUBMITTING,
            IntentState.PARTIALLY_HEDGED,
            IntentState.HEDGED,
        ),
        2,
        "websocket_disconnect",
    ),
    FaultScenario(
        "missing_quote",
        _path(IntentState.PLANNED, IntentState.ABORTING, IntentState.CLOSED),
        0,
        "missing_quote",
    ),
    FaultScenario(
        "stale_quote",
        _path(IntentState.PLANNED, IntentState.ABORTING, IntentState.CLOSED),
        0,
        "stale_quote",
    ),
    FaultScenario(
        "post_only_reject",
        _path(
            IntentState.PLANNED,
            IntentState.RISK_APPROVED,
            IntentState.SUBMITTING,
            IntentState.ABORTING,
            IntentState.CLOSED,
        ),
        2,
        "post_only_reject",
    ),
    FaultScenario(
        "modify_failures_with_delayed_fill",
        _path(
            IntentState.PLANNED,
            IntentState.RISK_APPROVED,
            IntentState.SUBMITTING,
            IntentState.PARTIALLY_HEDGED,
            IntentState.HEDGE_REQUIRED,
            IntentState.ABORTING,
            IntentState.HEDGE_REQUIRED,
            IntentState.HEDGED,
        ),
        4,
        "delayed_fill",
    ),
    FaultScenario(
        "reordered_delayed_fill",
        _path(
            IntentState.PLANNED,
            IntentState.RISK_APPROVED,
            IntentState.SUBMITTING,
            IntentState.PARTIALLY_HEDGED,
            IntentState.HEDGE_REQUIRED,
            IntentState.HEDGED,
        ),
        3,
        "event_reordering",
    ),
    FaultScenario(
        "websocket_reconnect",
        _path(
            IntentState.PLANNED,
            IntentState.RISK_APPROVED,
            IntentState.SUBMITTING,
            IntentState.HEDGED,
            IntentState.RECONCILING,
            IntentState.HEDGED,
        ),
        2,
        "websocket_reconnect",
    ),
    FaultScenario(
        "forced_restart_recovery",
        _path(
            IntentState.PLANNED,
            IntentState.RISK_APPROVED,
            IntentState.SUBMITTING,
            IntentState.PARTIALLY_HEDGED,
            IntentState.HEDGED,
            IntentState.RECONCILING,
            IntentState.HEDGED,
        ),
        2,
        "process_restart",
    ),
    FaultScenario(
        "missing_account_identity",
        _path(IntentState.PLANNED, IntentState.ABORTING, IntentState.CLOSED),
        0,
        "account_identity",
    ),
    FaultScenario(
        "funding_fee_rounding_residual",
        _path(
            IntentState.PLANNED,
            IntentState.RISK_APPROVED,
            IntentState.SUBMITTING,
            IntentState.HEDGED,
            IntentState.RECONCILING,
            IntentState.HEDGED,
        ),
        2,
        "explained_residual",
    ),
    FaultScenario(
        "liquidation_or_adl",
        _path(
            IntentState.PLANNED,
            IntentState.RISK_APPROVED,
            IntentState.SUBMITTING,
            IntentState.HEDGED,
            IntentState.RECONCILING,
            IntentState.RECONCILIATION_BLOCKED,
            IntentState.RECONCILING,
            IntentState.CLOSED,
        ),
        2,
        "liquidation_or_adl",
    ),
    FaultScenario(
        "duplicate_idempotency_key",
        _path(
            IntentState.PLANNED,
            IntentState.RISK_APPROVED,
            IntentState.SUBMITTING,
            IntentState.ABORTING,
            IntentState.CLOSED,
        ),
        1,
        "duplicate_command",
    ),
)


def run_fault_scenario(scenario: FaultScenario) -> FaultResult:
    ledger = InMemoryPhase1Ledger()
    intent_id = f"intent-{scenario.name}"
    ledger.add_intent(
        IntentRow(
            intent_id, "manifest", "cost-ledger", "300", {"fixture": scenario.name}, FIXTURE_TIME
        )
    )
    machine = CarryStateMachine(intent_id, ledger)
    for state in scenario.states:
        machine.transition(
            state,
            trigger=f"fixture:{scenario.name}",
            guards={"fixture_expected": True},
            recorded_at=FIXTURE_TIME,
        )
    if scenario.incident_category:
        ledger.add_incident(
            IncidentRow(
                f"incident-{scenario.name}",
                intent_id,
                scenario.incident_category,
                "test",
                "deterministic Phase 1 replay",
                FIXTURE_TIME,
            )
        )
    if machine.state is None:
        raise RuntimeError("fault scenario produced no final state")
    return FaultResult(
        name=scenario.name,
        final_state=machine.state,
        transition_count=len(ledger.transitions),
        submitted_order_count=scenario.submitted_order_count,
        orphan_fill_count=scenario.orphan_fill_count,
        unexplained_residual=scenario.unexplained_residual,
        incident_count=len(ledger.incidents),
    )


def run_fault_suite() -> dict[str, Any]:
    results = tuple(run_fault_scenario(scenario) for scenario in FAULT_SCENARIOS)
    return {
        "schema_version": 1,
        "scope": "deterministic orchestration replay; not live fill-quality evidence",
        "scenario_count": len(results),
        "passed": all(result.passed for result in results),
        "results": [result.to_dict() for result in results],
    }
