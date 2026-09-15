import copy
import json
from decimal import Decimal
from pathlib import Path

import pytest

from v3.phase1.policy import EXPECTED_INTENT_FIELDS, load_phase1_policy, policy_from_mapping

ROOT = Path(__file__).resolve().parents[1]


def _policy() -> dict:
    return json.loads((ROOT / "configs" / "phase1-policy.json").read_text())


def test_phase1_policy_is_binance_demo_only_and_cannot_authorize_live_orders():
    policy = _policy()

    assert policy["execution"] == {
        "engine": "nautilus_trader",
        "environment": "demo",
        "primary_venue": "binance",
        "product_types": ["spot", "usd_m"],
    }
    assert policy["authorization"] == {
        "live_orders": False,
        "real_capital": False,
    }
    assert policy["instruments"] == {
        "perp": "BTCUSDT-PERP.BINANCE",
        "spot": "BTCUSDT.BINANCE",
    }
    assert "live" not in policy["synthetic_target"]["allowed_environments"]
    assert policy["synthetic_target"]["forbidden_when_live_authorized"] is True
    assert policy["order_types"] == {
        "emergency_hedge": "IOC_LIMIT",
        "perp_post_only": "GTX",
        "spot_post_only": "LIMIT_MAKER",
    }


def test_phase1_policy_freezes_source_and_risk_guards():
    policy = _policy()

    assert all(policy["source"].values())
    assert Decimal(policy["risk"]["maximum_leverage"]) <= 2
    assert Decimal(policy["risk"]["minimum_notional_headroom"]) >= 3
    assert Decimal(policy["risk"]["maximum_delta_drift_fraction"]) <= Decimal("0.05")
    assert policy["bootstrap_scope"]["gates_phase1_simulation"] is False
    assert policy["risk"]["abort_budget_scope"] == "per_month"
    assert "daily_abort_budget_fraction_of_carry_sleeve" not in policy["risk"]
    assert policy["scanner"]["replace_prior_after_phase"] == "3"
    assert policy["scanner"]["phase1e_measurement_use"] == "demo_lower_bound_only"
    assert policy["sla"]["unmeasured_behavior"] == "deny"
    assert policy["cost_model"]["demo_fee_treatment"] == "ignore"
    assert policy["cost_model"]["include_exit_cost"] is True


def test_phase1_policy_allocations_and_derived_abort_budget_are_exact():
    policy = load_phase1_policy(ROOT / "configs" / "phase1-policy.json")

    assert policy.total_capital == Decimal("1000")
    assert policy.carry_sleeve_capital == Decimal("450.00")
    assert policy.maximum_carry_leg_notional == Decimal("300.0")
    assert policy.monthly_abort_budget == Decimal("2.25000")
    assert policy.required_intent_fields == EXPECTED_INTENT_FIELDS
    assert policy.fee_schedule.complete is True
    assert policy.fee_schedule.maker_round_trip_bps == Decimal("24")


def test_measured_fee_schedule_is_complete_and_conservative():
    policy = _policy()

    assert policy["cost_model"]["unmeasured_behavior"] == "observe_only"
    assert policy["cost_model"]["bnb_discount_applied"] is False
    assert policy["cost_model"]["normal_entry_cost_bps"] == "12"
    assert policy["cost_model"]["normal_round_trip_cost_bps"] == "24"
    assert policy["cost_model"]["snapshot_maximum_age_hours"] == 24


def test_fee_schedule_can_only_be_cleared_as_one_fail_closed_unit():
    policy = _policy()
    for key in (
        "spot_maker_bps",
        "spot_taker_bps",
        "perp_maker_bps",
        "perp_taker_bps",
        "normal_entry_cost_bps",
        "normal_round_trip_cost_bps",
        "bnb_discount_applied",
        "snapshot_captured_at",
        "snapshot_evidence",
        "snapshot_maximum_age_hours",
    ):
        policy["cost_model"][key] = None

    parsed = policy_from_mapping(policy)

    assert not parsed.fee_schedule.complete
    assert parsed.fee_schedule.maker_round_trip_bps is None


@pytest.mark.parametrize(
    ("environment", "live_orders", "real_capital"),
    [("live", False, False), ("demo", True, False), ("demo", False, True)],
)
def test_synthetic_target_is_rejected_outside_simulation_boundary(
    environment, live_orders, real_capital
):
    policy = load_phase1_policy(ROOT / "configs" / "phase1-policy.json")

    assert policy.synthetic_target_reasons(
        environment=environment,
        live_orders=live_orders,
        real_capital=real_capital,
    )


def test_policy_parser_rejects_capital_drift_or_phase1e_abort_prior_replacement():
    policy = _policy()
    bad_allocation = copy.deepcopy(policy)
    bad_allocation["capital"]["reserve_fraction"] = "0.06"
    with pytest.raises(ValueError, match="sum to 1"):
        policy_from_mapping(bad_allocation)

    bad_prior = copy.deepcopy(policy)
    bad_prior["scanner"]["replace_prior_after_phase"] = "1E"
    with pytest.raises(ValueError, match="before Phase 3"):
        policy_from_mapping(bad_prior)


def test_policy_parser_rejects_unsafe_types_order_contract_or_missing_exit_cost():
    policy = _policy()

    string_authorization = copy.deepcopy(policy)
    string_authorization["authorization"]["live_orders"] = "false"
    with pytest.raises(ValueError, match="explicit JSON false"):
        policy_from_mapping(string_authorization)

    unsafe_order_type = copy.deepcopy(policy)
    unsafe_order_type["order_types"]["spot_post_only"] = "LIMIT"
    with pytest.raises(ValueError, match="order types"):
        policy_from_mapping(unsafe_order_type)

    missing_exit_cost = copy.deepcopy(policy)
    missing_exit_cost["cost_model"]["include_exit_cost"] = False
    with pytest.raises(ValueError, match="include exit cost"):
        policy_from_mapping(missing_exit_cost)

    inconsistent_cost = copy.deepcopy(policy)
    inconsistent_cost["cost_model"]["normal_round_trip_cost_bps"] = "12"
    with pytest.raises(ValueError, match="declared normal costs"):
        policy_from_mapping(inconsistent_cost)


def test_policy_requires_conservative_funding_projection_and_reversal_exit():
    policy = _policy()
    assert policy["scanner"]["funding_projection"]["method"] == "min_of_current_and_trailing_mean"
    assert policy["scanner"]["funding_projection"]["trailing_intervals"] >= 3
    assert policy["scanner"]["funding_projection"]["require_trailing_history"] is True
    assert policy["scanner"]["funding_reversal_exit"]["consecutive_nonpositive_intervals"] >= 1
    loaded = policy_from_mapping(policy)
    assert loaded.funding_projection_intervals == 21
    assert loaded.funding_reversal_consecutive_intervals == 2

    optimistic = copy.deepcopy(policy)
    optimistic["scanner"]["funding_projection"]["method"] = "current_rate"
    with pytest.raises(ValueError, match="min_of_current_and_trailing_mean"):
        policy_from_mapping(optimistic)
    no_history = copy.deepcopy(policy)
    no_history["scanner"]["funding_projection"]["require_trailing_history"] = False
    with pytest.raises(ValueError, match="require trailing history"):
        policy_from_mapping(no_history)
    short = copy.deepcopy(policy)
    short["scanner"]["funding_projection"]["trailing_intervals"] = 2
    with pytest.raises(ValueError, match="three trailing"):
        policy_from_mapping(short)
