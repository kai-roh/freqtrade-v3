import copy
from datetime import UTC, datetime, timedelta
from pathlib import Path

from v3.phase1.policy import load_phase1_policy, policy_from_mapping
from v3.phase1.risk import CarryRiskContext, evaluate_carry_risk

ROOT = Path(__file__).resolve().parents[1]
CAPTURED_AT = datetime(2026, 9, 3, 2, 27, 4, 465026, tzinfo=UTC)


def _measured_policy():
    import json

    raw = json.loads((ROOT / "configs" / "phase1-policy.json").read_text())
    measured = copy.deepcopy(raw)
    measured["sla"]["maximum_quote_age_ms"] = 1000
    measured["sla"]["quote_age_p99_ms"] = "500"
    measured["sla"]["quote_age_sample_count"] = 50
    measured["sla"]["quote_age_evidence"] = "evidence/phase1/fixture.json"
    measured["sla"]["quote_age_measured_at"] = "2026-09-15T00:00:00+00:00"
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
        "evaluated_at": CAPTURED_AT,
    }
    values.update(overrides)
    return CarryRiskContext(**values)


def test_measured_safe_context_is_approved():
    decision = evaluate_carry_risk(_context(), _measured_policy())

    assert decision.approved
    assert not decision.reasons


def _unmeasured_policy():
    import json

    raw = json.loads((ROOT / "configs" / "phase1-policy.json").read_text())
    unmeasured = copy.deepcopy(raw)
    for key in (
        "maximum_quote_age_ms",
        "quote_age_evidence",
        "quote_age_measured_at",
        "quote_age_p99_ms",
        "quote_age_sample_count",
    ):
        unmeasured["sla"][key] = None
    return policy_from_mapping(unmeasured)


def test_unmeasured_quote_sla_fails_closed_after_fee_measurement():
    decision = evaluate_carry_risk(_context(), _unmeasured_policy())

    assert not decision.approved
    assert "quote-age SLA is unmeasured" in decision.reasons


def test_committed_policy_enforces_the_measured_96ms_quote_sla():
    policy = load_phase1_policy(ROOT / "configs" / "phase1-policy.json")
    assert policy.maximum_quote_age_ms == 96

    stale = evaluate_carry_risk(_context(quote_age_ms=97), policy)
    assert "quote is stale" in stale.reasons
    fresh = evaluate_carry_risk(_context(quote_age_ms=96), policy)
    assert "quote is stale" not in fresh.reasons
    assert "quote-age SLA is unmeasured" not in fresh.reasons


def test_stale_fee_snapshot_fails_closed():
    decision = evaluate_carry_risk(
        _context(evaluated_at=CAPTURED_AT + timedelta(hours=25)),
        _measured_policy(),
    )

    assert not decision.approved
    assert "credentialed mainnet fee schedule is stale" in decision.reasons


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
