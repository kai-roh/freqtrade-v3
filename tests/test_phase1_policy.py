import json
from decimal import Decimal
from pathlib import Path

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


def test_phase1_policy_freezes_source_and_risk_guards():
    policy = _policy()

    assert all(policy["source"].values())
    assert Decimal(policy["risk"]["maximum_leverage"]) <= 2
    assert Decimal(policy["risk"]["minimum_notional_headroom"]) >= 3
    assert Decimal(policy["risk"]["maximum_delta_drift_fraction"]) <= Decimal("0.05")
    assert policy["bootstrap_scope"]["gates_phase1_simulation"] is False
