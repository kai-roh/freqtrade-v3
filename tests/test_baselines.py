import pandas as pd
import pytest

from v3.baselines import backtest_events, no_trade, trend_pullback, volatility_breakout
from v3.risk import RiskConfig


def _index(rows=8):
    return pd.date_range("2026-01-01", periods=rows, freq="15min")


def _market():
    index = _index()
    return pd.DataFrame(
        {
            "open": [100, 100, 101, 102, 103, 104, 105, 106],
            "high": [101, 110, 103, 104, 105, 106, 107, 108],
            "low": [99, 95, 100, 101, 102, 103, 104, 105],
            "close": [100, 101, 102, 103, 104, 105, 106, 107],
        },
        index=index,
    )


def _features():
    return pd.DataFrame(
        {
            "atr": [2.0] * 8,
            "regime_1h_trend": [1, 1, -1, -1, 1, 1, -1, -1],
            "ema_fast_atr_dist": [-0.4, 1.2, 0.4, -1.2, -0.1, 0.1, 0.2, -0.2],
            "ret_1": [0.01, 0.02, -0.01, -0.02, 0.01, -0.01, 0.01, -0.01],
            "vol_surprise": [0.5] * 8,
        },
        index=_index(),
    )


def test_baseline_signal_toggles():
    features = _features()

    assert not no_trade(features).any().any()
    pullback = trend_pullback(features, allow_short=False)
    breakout = volatility_breakout(features, allow_long=False, breakout_threshold=1.0)

    assert pullback["long"].iloc[0]
    assert not pullback["short"].any()
    assert not breakout["long"].any()
    assert breakout["short"].iloc[3]


def test_volatility_breakout_requires_matching_hourly_regime():
    features = _features()
    features.loc[features.index[1], "regime_1h_trend"] = -1
    features.loc[features.index[3], "regime_1h_trend"] = 1

    signals = volatility_breakout(features, breakout_threshold=1.0)

    assert not signals["long"].iloc[1]
    assert not signals["short"].iloc[3]


def test_backtest_enters_next_open_and_resolves_same_candle_stop_first():
    market = _market()
    features = _features()
    signals = no_trade(features)
    signals.loc[signals.index[0], "long"] = True

    trades = backtest_events(
        market,
        features,
        signals,
        pair="BTC/USDT",
        risk_config=RiskConfig(
            stop_atr=2, target_atr=2, max_holding_candles=4, round_trip_cost_bps=10
        ),
    )

    trade = trades.iloc[0]
    assert trade["entry_time"] == market.index[1]
    assert trade["entry_price"] == 100
    assert trade["exit_price"] == 96
    assert trade["exit_reason"] == "stop"
    assert trade["gross_return"] == pytest.approx(-0.04)
    assert trade["net_return"] == pytest.approx(-0.041)
    assert trade["turnover"] == 2.0


def test_backtest_prevents_overlapping_positions_and_uses_time_exit():
    market = _market()
    features = _features()
    signals = no_trade(features)
    signals.loc[signals.index[0:3], "long"] = True

    trades = backtest_events(
        market,
        features,
        signals,
        pair="ETH/USDT",
        risk_config=RiskConfig(
            stop_atr=10, target_atr=10, max_holding_candles=3, round_trip_cost_bps=0
        ),
    )

    assert len(trades) == 1
    assert trades.iloc[0]["signal_time"] == market.index[0]
    assert trades.iloc[0]["entry_time"] == market.index[1]
    assert trades.iloc[0]["exit_time"] == market.index[3]
    assert trades.iloc[0]["exit_reason"] == "time"


def test_backtest_short_target_and_conflicting_signals_are_deterministic():
    market = _market()
    features = _features()
    signals = no_trade(features)
    signals.loc[signals.index[0], ["long", "short"]] = True
    signals.loc[signals.index[1], "short"] = True

    trades = backtest_events(
        market,
        features,
        signals,
        pair="SOL/USDT",
        risk_config=RiskConfig(
            stop_atr=10, target_atr=0.5, max_holding_candles=4, round_trip_cost_bps=0
        ),
    )

    assert len(trades) == 1
    assert trades.iloc[0]["side"] == "short"
    assert trades.iloc[0]["entry_time"] == market.index[2]
    assert trades.iloc[0]["exit_reason"] == "target"
