from pathlib import Path

from v3.phase1.adapters import BinanceClientSpec, phase1_binance_client_specs
from v3.phase1.policy import load_phase1_policy
from v3.phase1.runtime import ExecutionRuntimeFacts, validate_execution_runtime

ROOT = Path(__file__).resolve().parents[1]


def _facts(**overrides):
    values = {
        "git_sha": "a" * 40,
        "source_dirty": False,
        "image_digest": "sha256:" + "b" * 64,
        "dependency_lock_sha256": "c" * 64,
        "environment": "demo",
        "live_orders": False,
        "real_capital": False,
        "spot_client_id": "BINANCE_SPOT_DEMO",
        "perp_client_id": "BINANCE_USDM_DEMO",
        "instruments": frozenset({"BTCUSDT.BINANCE", "BTCUSDT-PERP.BINANCE"}),
        "leverage_by_instrument": {
            "BTCUSDT.BINANCE": "1",
            "BTCUSDT-PERP.BINANCE": "2",
        },
    }
    values.update(overrides)
    return ExecutionRuntimeFacts(**values)


def test_phase1_runtime_accepts_only_complete_order_free_demo_facts():
    policy = load_phase1_policy(ROOT / "configs" / "phase1-policy.json")

    result = validate_execution_runtime(_facts(), policy)

    assert result.passed
    assert len(result.checks) == 10


def test_phase1_runtime_rejects_dirty_live_same_client_or_unknown_leverage():
    policy = load_phase1_policy(ROOT / "configs" / "phase1-policy.json")
    facts = _facts(
        source_dirty=True,
        environment="live",
        live_orders=True,
        order_submission_enabled=True,
        perp_client_id="BINANCE_SPOT_DEMO",
        leverage_by_instrument={"BTCUSDT.BINANCE": "1"},
    )

    result = validate_execution_runtime(facts, policy)
    failures = {check.code for check in result.checks if not check.passed}

    assert {"clean_tree", "environment", "authorization", "submission_mode"}.issubset(failures)
    assert {"client_identity", "leverage"}.issubset(failures)


def test_client_specs_are_distinct_demo_accounts_and_cannot_enable_submission():
    spot, perp = phase1_binance_client_specs()

    assert spot.client_id != perp.client_id
    assert {spot.account_type, perp.account_type} == {"SPOT", "USDT_FUTURES"}
    assert not spot.order_submission_enabled
    try:
        BinanceClientSpec(client_id="unsafe", account_type="SPOT", order_submission_enabled=True)
    except ValueError as exc:
        assert "order-free" in str(exc)
    else:
        raise AssertionError("unsafe client spec was accepted")
