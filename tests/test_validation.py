import pandas as pd
import pytest

from v3.validation import (
    PromotionConfig,
    WalkForwardConfig,
    evaluate_promotion,
    make_purged_walk_forward_folds,
)


def market_frame(periods=30):
    index = pd.date_range("2026-01-01", periods=periods, freq="D")
    return pd.DataFrame({"close": range(periods)}, index=index)


def trade_frame(pnls, pair="BTC/USDT", notional=1.0):
    return pd.DataFrame(
        {
            "pnl": pnls,
            "pair": [pair] * len(pnls),
            "side": ["long"] * len(pnls),
            "notional": [notional] * len(pnls),
        }
    )


def test_purged_walk_forward_folds_respect_label_horizon_embargo():
    config = WalkForwardConfig(
        train_duration="5D",
        validation_duration="2D",
        fold_count=3,
        label_horizon="2D",
        embargo="1D",
    )

    folds = make_purged_walk_forward_folds(market_frame(), config)

    assert len(folds) == 3
    assert folds[0].train_start == pd.Timestamp("2026-01-01")
    assert folds[0].train_end == pd.Timestamp("2026-01-06")
    assert folds[0].validation_start == pd.Timestamp("2026-01-08")
    assert folds[0].validation_end == pd.Timestamp("2026-01-10")
    for fold in folds:
        assert fold.train_end + pd.Timedelta("2D") <= fold.validation_start
        assert set(fold.train_indices).isdisjoint(fold.validation_indices)
        assert max(fold.train_indices) < min(fold.validation_indices)


def test_walk_forward_folds_are_reproducible():
    config = WalkForwardConfig("4D", "2D", 4, "1D")

    assert make_purged_walk_forward_folds(market_frame(), config) == (
        make_purged_walk_forward_folds(market_frame(), config)
    )


def test_walk_forward_fails_closed_for_unsorted_or_insufficient_data():
    config = WalkForwardConfig("5D", "2D", 4, "2D")
    unsorted = market_frame().sample(frac=1.0, random_state=7)

    with pytest.raises(ValueError, match="sorted chronologically"):
        make_purged_walk_forward_folds(unsorted, config)

    with pytest.raises(ValueError, match="insufficient data"):
        make_purged_walk_forward_folds(market_frame(periods=8), config)


def test_promotion_passes_with_six_balanced_profitable_folds():
    folds = [
        trade_frame([0.10, -0.02], pair="BTC/USDT"),
        trade_frame([0.08, -0.01], pair="ETH/USDT"),
        trade_frame([0.07, -0.01], pair="SOL/USDT"),
        trade_frame([0.06, -0.01], pair="ADA/USDT"),
        trade_frame([-0.01, 0.04], pair="XRP/USDT"),
        trade_frame([-0.02, 0.03], pair="DOT/USDT"),
    ]

    result = evaluate_promotion(folds)

    assert result.passed
    assert result.reasons == ()
    assert result.positive_folds == 6
    assert result.aggregate_metrics.profit_factor >= 1.15
    assert result.max_fold_contribution <= 0.50
    assert result.max_pair_contribution <= 0.50


def test_promotion_rejects_negative_candidates_and_missing_folds():
    result = evaluate_promotion([trade_frame([-0.05])] * 6)

    assert not result.passed
    assert any("profit factor" in reason for reason in result.reasons)
    assert "expectancy is not positive" in result.reasons
    assert any("positive folds" in reason for reason in result.reasons)

    missing = evaluate_promotion([trade_frame([0.1])] * 5)
    assert not missing.passed
    assert missing.reasons == ("expected 6 folds, got 5",)


def test_promotion_rejects_no_trades_and_concentration():
    no_trades = evaluate_promotion([trade_frame([])] * 6)
    assert not no_trades.passed
    assert "no trades" in no_trades.reasons

    concentrated_fold = evaluate_promotion(
        [
            trade_frame([0.51], pair="BTC/USDT"),
            trade_frame([0.10], pair="ETH/USDT"),
            trade_frame([0.10], pair="SOL/USDT"),
            trade_frame([0.10], pair="ADA/USDT"),
            trade_frame([0.10], pair="XRP/USDT"),
            trade_frame([0.09], pair="DOT/USDT"),
        ]
    )
    assert not concentrated_fold.passed
    assert any("single fold contribution" in reason for reason in concentrated_fold.reasons)

    concentrated_pair = evaluate_promotion(
        [
            trade_frame([0.11], pair="BTC/USDT"),
            trade_frame([0.11], pair="BTC/USDT"),
            trade_frame([0.11], pair="BTC/USDT"),
            trade_frame([0.09], pair="ETH/USDT"),
            trade_frame([0.09], pair="SOL/USDT"),
            trade_frame([0.09], pair="ADA/USDT"),
        ]
    )
    assert not concentrated_pair.passed
    assert any("single pair contribution" in reason for reason in concentrated_pair.reasons)


def test_cost_stress_can_flip_promotion_to_rejection():
    folds = [trade_frame([0.02], pair=f"PAIR{i}", notional=10.0) for i in range(6)]

    unstressed = evaluate_promotion(folds, PromotionConfig(cost_stress=0.0))
    stressed = evaluate_promotion(folds, PromotionConfig(cost_stress=0.003))

    assert unstressed.passed
    assert not stressed.passed
    assert "expectancy is not positive" in stressed.reasons


def test_promotion_propagates_initial_capital_to_drawdown_gate():
    folds = [
        trade_frame([0.05, -0.03], pair="BTC/USDT"),
        trade_frame([0.05, -0.03], pair="ETH/USDT"),
        trade_frame([0.05, -0.03], pair="SOL/USDT"),
        trade_frame([0.05, -0.03], pair="ADA/USDT"),
        trade_frame([0.05, -0.03], pair="XRP/USDT"),
        trade_frame([0.05, -0.03], pair="DOT/USDT"),
    ]

    tight_capital = evaluate_promotion(folds, PromotionConfig(initial_capital=0.20))
    larger_capital = evaluate_promotion(folds, PromotionConfig(initial_capital=1.0))

    assert not tight_capital.passed
    assert any("drawdown" in reason for reason in tight_capital.reasons)
    assert larger_capital.passed


def test_embargo_check_inspects_actual_rows_not_only_configured_boundaries():
    from v3.validation import _assert_row_embargo

    times = pd.Series(pd.date_range("2026-01-01", periods=10, freq="D"))
    train = times < pd.Timestamp("2026-01-05")
    validation = times >= pd.Timestamp("2026-01-07")
    _assert_row_embargo(times, train, validation, "2D", 0)
    with pytest.raises(ValueError, match="violates embargo"):
        _assert_row_embargo(times, train, validation, "4D", 0)
    # A mask that leaks a train row into the embargo window is caught even if the
    # configured boundaries look correct.
    leaking_train = times < pd.Timestamp("2026-01-07")
    with pytest.raises(ValueError, match="violates embargo"):
        _assert_row_embargo(times, leaking_train, validation, "2D", 1)
