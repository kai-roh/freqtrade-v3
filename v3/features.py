"""Deterministic stationary feature engineering for 15m OHLCV research data."""

from __future__ import annotations

import numpy as np
import pandas as pd

OHLCV_COLUMNS = ("open", "high", "low", "close", "volume")


def _require_ohlcv(df: pd.DataFrame) -> None:
    missing = [col for col in OHLCV_COLUMNS if col not in df.columns]
    if missing:
        raise ValueError(f"missing OHLCV columns: {missing}")
    if not isinstance(df.index, pd.DatetimeIndex):
        raise TypeError("OHLCV dataframe must use a DatetimeIndex")
    if not df.index.is_monotonic_increasing:
        raise ValueError("OHLCV dataframe index must be sorted ascending")


def true_range(df: pd.DataFrame) -> pd.Series:
    """Return Wilder true range using only the current bar and previous close."""
    _require_ohlcv(df)
    prev_close = df["close"].shift(1)
    ranges = pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - prev_close).abs(),
            (df["low"] - prev_close).abs(),
        ],
        axis=1,
    )
    return ranges.max(axis=1)


def atr(df: pd.DataFrame, window: int = 14) -> pd.Series:
    """Simple rolling ATR; deterministic and causal."""
    if window <= 0:
        raise ValueError("window must be positive")
    return true_range(df).rolling(window, min_periods=window).mean()


def _hourly_ohlcv_from_15m(df_15m: pd.DataFrame) -> pd.DataFrame:
    hourly = df_15m.resample("1h", label="left", closed="left").agg(
        {
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum",
        }
    )
    return hourly.dropna(subset=["open", "high", "low", "close"])


def _hourly_regime(hourly: pd.DataFrame, atr_window: int, ema_span: int) -> pd.DataFrame:
    _require_ohlcv(hourly)
    hourly_atr = atr(hourly, atr_window)
    ema = hourly["close"].ewm(span=ema_span, adjust=False, min_periods=ema_span).mean()
    regime = pd.DataFrame(index=hourly.index)
    regime["regime_1h_ret"] = hourly["close"].pct_change()
    regime["regime_1h_ema_atr_dist"] = (hourly["close"] - ema) / hourly_atr.replace(0.0, np.nan)
    regime["regime_1h_trend"] = np.sign(regime["regime_1h_ema_atr_dist"]).replace(0.0, np.nan)
    return regime.shift(1)


def build_15m_features(
    df_15m: pd.DataFrame,
    *,
    df_1h: pd.DataFrame | None = None,
    atr_window: int = 14,
    ema_fast_span: int = 12,
    ema_slow_span: int = 48,
    volume_window: int = 48,
    hourly_ema_span: int = 12,
) -> pd.DataFrame:
    """Build causal stationary 15m features.

    The output intentionally excludes raw price and volume columns. If 1h data is
    supplied, its completed hourly bars are shifted before joining to 15m rows.
    """
    _require_ohlcv(df_15m)
    if min(atr_window, ema_fast_span, ema_slow_span, volume_window, hourly_ema_span) <= 0:
        raise ValueError("all windows/spans must be positive")

    close = df_15m["close"]
    current_atr = atr(df_15m, atr_window)
    safe_atr = current_atr.replace(0.0, np.nan)
    ema_fast = close.ewm(span=ema_fast_span, adjust=False, min_periods=ema_fast_span).mean()
    ema_slow = close.ewm(span=ema_slow_span, adjust=False, min_periods=ema_slow_span).mean()
    past_volume_mean = (
        df_15m["volume"].shift(1).rolling(volume_window, min_periods=volume_window).mean()
    )

    features = pd.DataFrame(index=df_15m.index)
    features["ret_1"] = close.pct_change(1)
    features["ret_4"] = close.pct_change(4)
    features["ret_16"] = close.pct_change(16)
    features["atr"] = current_atr
    features["atr_norm"] = current_atr / close.replace(0.0, np.nan)
    features["ema_fast_atr_dist"] = (close - ema_fast) / safe_atr
    features["ema_slow_atr_dist"] = (close - ema_slow) / safe_atr
    features["vol_surprise"] = df_15m["volume"] / past_volume_mean.replace(0.0, np.nan) - 1.0

    hourly_source = df_1h if df_1h is not None else _hourly_ohlcv_from_15m(df_15m)
    regime = _hourly_regime(hourly_source, atr_window=atr_window, ema_span=hourly_ema_span)
    joined_regime = pd.merge_asof(
        pd.DataFrame(index=features.index),
        regime.sort_index(),
        left_index=True,
        right_index=True,
        direction="backward",
    )
    for column in joined_regime.columns:
        features[column] = joined_regime[column]

    return features.replace([np.inf, -np.inf], np.nan)
