import pandas as pd
import pytest

from v3.bootstrap import BootstrapSpec, block_bootstrap_mean


def test_bootstrap_spec_rejects_trade_level_resampling_for_dependent_trades():
    with pytest.raises(ValueError, match="individual_trade"):
        BootstrapSpec(sample_unit="individual_trade", block_length=2, iterations=100, seed=7)


def test_block_bootstrap_mean_is_deterministic_for_registered_seed():
    returns = pd.Series(
        [-0.002, 0.001, -0.004, 0.002, -0.003, -0.001],
        index=pd.date_range("2026-01-01", periods=6, freq="D"),
    )
    spec = BootstrapSpec(sample_unit="daily_portfolio_pnl", block_length=2, iterations=200, seed=42)

    first = block_bootstrap_mean(returns, spec)
    second = block_bootstrap_mean(returns, spec)

    assert first == second
    assert first.observed_mean == pytest.approx(returns.mean())
    assert first.iterations == 200
    assert first.ci_low <= first.observed_mean <= first.ci_high


def test_block_bootstrap_requires_enough_ordered_periods():
    spec = BootstrapSpec(sample_unit="exposure_cluster", block_length=3, iterations=100, seed=1)

    with pytest.raises(ValueError, match="at least block_length"):
        block_bootstrap_mean(pd.Series([0.1, -0.1]), spec)

    unsorted = pd.Series(
        [0.1, -0.1, 0.2],
        index=pd.to_datetime(["2026-01-03", "2026-01-01", "2026-01-02"]),
    )
    with pytest.raises(ValueError, match="chronologically ordered"):
        block_bootstrap_mean(unsorted, spec)


def test_bootstrap_result_preserves_all_preregistered_choices():
    returns = pd.Series(
        [-0.01, 0.01, -0.02, 0.02],
        index=pd.date_range("2026-01-01", periods=4, freq="D"),
    )
    spec = BootstrapSpec(
        sample_unit="daily_portfolio_pnl",
        block_length=2,
        iterations=50,
        seed=20260819,
    )

    result = block_bootstrap_mean(returns, spec).to_dict()

    assert result["direction"] == "two-sided"
    assert result["block_definition"] == "moving_contiguous_periods"
    assert result["seed"] == 20260819
