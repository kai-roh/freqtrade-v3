from v3.phase1.faults import FAULT_SCENARIOS, run_fault_scenario, run_fault_suite


def test_all_13_fault_scenarios_reconcile_without_orphan_fill_or_unknown_residual():
    result = run_fault_suite()

    assert result["scenario_count"] == 13
    assert result["passed"]
    assert len({scenario.name for scenario in FAULT_SCENARIOS}) == 13


def test_each_fault_scenario_reaches_its_registered_final_state_and_records_incident():
    for scenario in FAULT_SCENARIOS:
        result = run_fault_scenario(scenario)
        assert result.final_state == scenario.states[-1]
        assert result.transition_count == len(scenario.states)
        assert result.incident_count == (1 if scenario.incident_category else 0)
