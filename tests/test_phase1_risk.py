import copy
from pathlib import Path

from v3.phase1.policy import load_phase1_policy, policy_from_mapping
from v3.phase1.risk import CarryRiskContext, evaluate_carry_risk

ROOT = Path(__file__).resolve().parents[1]


def _measured_policy():
    import json

    raw = json.loads((ROOT / "configs" / "phase1-policy.json").read_text())
    measured = copy.deepcopy(raw)
    measured["sla"]["maximum_quote_age_ms"] = 1000
    measured["reconciliation"]["maximum_unexplained_residual_usdt"] = "0.05"
    measured["reconciliation"]["maximum_unclassified_hours"] = "2"
    measured["cost_model"].update(
        {
            "spot_maker_bps": "10",
            "spot_taker_bps": "10",
            "perp_maker_bps": "2",
            "perp_taker_bps": "5",
            "bnb_discount_applied": False,
            "normal_entry_cost_bps": "12",
            "normal_round_trip_cost_bps": "24",
        }
    )
    return policy_from_mapping(measured)


def _context(**overrides):
    values = {
        "intent_fields": {
            "entry_reason": "positive funding",
            "target_position": "long spot short perp",
            "normal_exit": "funding convergence",
            "risk_exit": "delta drift",
            "max_holding_or_review_at": "720h",
            "cost_and_risk_budget": "policy-v2",
        },
        "cost_ledger_complete": True,
        "leverage_by_instrument": {
            "BTCUSDT.BINANCE": "1",
            "BTCUSDT-PERP.BINANCE": "2",
        },
        "quote_age_ms": 100,
        "leg_notional": "300",
        "minimum_notional_by_instrument": {
            "BTCUSDT.BINANCE": "10",
            "BTCUSDT-PERP.BINANCE": "5",
        },
        "local_positions_match_venue": True,
        "unexplained_residual_usdt": "0",
        "residual_unclassified_hours": "0",
        "daily_loss_usdt": "0",
        "monthly_abort_cost_usdt": "0",
        "abort_attempts_this_month": 0,
        "consecutive_aborts": 0,
        "idempotency_key_is_new": True,
        "environment": "demo",
        "live_orders": False,
        "real_capital": False,
    }
    values.update(overrides)
    return CarryRiskContext(**values)


def test_measured_safe_context_is_approved():
    decision = evaluate_carry_risk(_context(), _measured_policy())

    assert decision.approved
    assert not decision.reasons


def test_unmeasured_fee_and_quote_sla_fail_closed():
    policy = load_phase1_policy(ROOT / "configs" / "phase1-policy.json")

    decision = evaluate_carry_risk(_context(), policy)

    assert not decision.approved
    assert "credentialed mainnet fee schedule is incomplete" in decision.reasons
    assert "quote-age SLA is unmeasured" in decision.reasons


def test_risk_rejects_leverage_budget_duplicate_and_live_boundary():
    policy = _measured_policy()
    decision = evaluate_carry_risk(
        _context(
            leverage_by_instrument={
                "BTCUSDT.BINANCE": "1",
                "BTCUSDT-PERP.BINANCE": "3",
            },
            monthly_abort_cost_usdt=policy.monthly_abort_budget,
            abort_attempts_this_month=3,
            consecutive_aborts=2,
            idempotency_key_is_new=False,
            environment="live",
            live_orders=True,
            real_capital=True,
            leg_notional="301",
        ),
        policy,
    )

    assert not decision.approved
    joined = " | ".join(decision.reasons)
    assert "leverage exceeds" in joined
    assert "monthly abort budget" in joined
    assert "monthly abort attempt" in joined
    assert "consecutive abort" in joined
    assert "idempotency" in joined
    assert "authorization" in joined
    assert "collateral boundary" in joined


def test_risk_context_rejects_negative_loss_or_residual_accounting():
    import pytest

    with pytest.raises(ValueError, match="daily_loss_usdt"):
        _context(daily_loss_usdt="-1")
    with pytest.raises(ValueError, match="unexplained_residual_usdt"):
        _context(unexplained_residual_usdt="-0.01")


def test_risk_uses_observed_perp_leverage_for_collateral_boundary():
    decision = evaluate_carry_risk(
        _context(
            leverage_by_instrument={
                "BTCUSDT.BINANCE": "1",
                "BTCUSDT-PERP.BINANCE": "1",
            }
        ),
        _measured_policy(),
    )

    assert not decision.approved
    assert "leg notional exceeds collateral available at observed leverage" in decision.reasons


def test_small_zero_residual_is_allowed_without_measured_residual_threshold():
    policy = _measured_policy()
    raw = copy.deepcopy(dict(policy.raw))
    raw["reconciliation"] = dict(raw["reconciliation"])
    raw["reconciliation"]["maximum_unexplained_residual_usdt"] = None
    raw["reconciliation"]["maximum_unclassified_hours"] = None
    policy = policy_from_mapping(raw)

    assert evaluate_carry_risk(_context(unexplained_residual_usdt="0"), policy).approved
    blocked = evaluate_carry_risk(_context(unexplained_residual_usdt="0.01"), policy)
    assert "reconciliation thresholds are unmeasured" in blocked.reasons
