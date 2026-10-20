from v3.phase1.recovery import RecoveryInput, recover_without_submission
from v3.phase1.state_machine import IntentState, InvariantSnapshot


def _invariants(**overrides):
    values = {
        "state": IntentState.HEDGED,
        "active_commands_by_leg": {"spot": 1, "perp": 1},
        "spot_notional": "100",
        "perp_notional": "100",
        "maximum_delta_drift_fraction": "0.05",
        "local_positions": {"spot": "1", "perp": "-1"},
        "venue_positions": {"spot": "1", "perp": "-1"},
        "rounding_tolerance": "0.001",
        "known_order_ids": frozenset({"o1", "o2"}),
        "fill_order_ids": ("o1", "o2"),
        "venue_fill_keys": (("binance", "f1"), ("binance", "f2")),
        "has_approved_risk_decision": True,
        "unhedged_notional_milliseconds": "0",
        "maximum_unhedged_notional_milliseconds": "1000",
    }
    values.update(overrides)
    return InvariantSnapshot(**values)


def test_three_restart_recoveries_preserve_hedged_state_without_enabling_orders():
    for missing_fill_count in (0, 1, 2):
        result = recover_without_submission(
            RecoveryInput(True, missing_fill_count, 0, False, False, _invariants())
        )
        assert result.state == IntentState.HEDGED
        assert not result.order_submission_enabled
        assert not result.violations


def test_recovery_blocks_on_incomplete_exchange_snapshot_or_invariant_failure():
    result = recover_without_submission(
        RecoveryInput(
            False,
            0,
            1,
            False,
            False,
            _invariants(has_approved_risk_decision=False),
        )
    )

    assert result.state == IntentState.RECONCILIATION_BLOCKED
    assert result.incident_required
    assert len(result.violations) == 2
