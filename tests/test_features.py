import numpy as np
import pandas as pd

from v3.features import build_15m_features


def _market(rows=120):
    index = pd.date_range("2026-01-01", periods=rows, freq="15min")
    close = pd.Series(100 + np.sin(np.arange(rows) / 6) + np.arange(rows) * 0.03, index=index)
    return pd.DataFrame(
        {
            "open": close.shift(1).fillna(close.iloc[0]),
            "high": close + 0.8,
            "low": close - 0.8,
            "close": close,
            "volume": 1000 + (np.arange(rows) % 7) * 25,
        },
        index=index,
    )


def test_features_are_stationary_and_exclude_raw_price_volume():
    features = build_15m_features(_market())

    assert "close" not in features.columns
    assert "volume" not in features.columns
    assert {"ret_1", "atr", "atr_norm", "ema_fast_atr_dist", "vol_surprise"}.issubset(
        features.columns
    )
    assert features["atr"].dropna().gt(0).all()
    assert features["atr_norm"].dropna().lt(0.1).all()


def test_features_are_causal_when_future_data_changes():
    market = _market()
    baseline = build_15m_features(market)
    changed_future = market.copy()
    changed_future.loc[changed_future.index[80] :, ["open", "high", "low", "close", "volume"]] *= 5

    changed = build_15m_features(changed_future)

    pd.testing.assert_frame_equal(baseline.iloc[:79], changed.iloc[:79])


def test_hourly_regime_uses_prior_completed_hour():
    market = _market()
    hourly = market.resample("1h", label="left", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    )
    features = build_15m_features(market, df_1h=hourly, atr_window=2, hourly_ema_span=2)

    first_hour_with_signal = features["regime_1h_ret"].first_valid_index()
    assert first_hour_with_signal is not None
    assert first_hour_with_signal.minute == 0
    assert first_hour_with_signal >= market.index[8]
