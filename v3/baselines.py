"""Deterministic baseline strategies and no-lookahead event backtester."""

from __future__ import annotations

import numpy as np
import pandas as pd

from v3.risk import RiskConfig, build_risk_contract, gross_return, net_return, turnover


def no_trade(
    features: pd.DataFrame, *, allow_long: bool = True, allow_short: bool = True
) -> pd.DataFrame:
    return pd.DataFrame(False, index=features.index, columns=["long", "short"])


def trend_pullback(
    features: pd.DataFrame,
    *,
    allow_long: bool = True,
    allow_short: bool = True,
    pullback_threshold: float = 0.25,
) -> pd.DataFrame:
    signals = no_trade(features)
    valid = features[["regime_1h_trend", "ema_fast_atr_dist", "ret_1"]].notna().all(axis=1)
    if allow_long:
        signals["long"] = (
            valid
            & (features["regime_1h_trend"] > 0)
            & (features["ema_fast_atr_dist"] <= -pullback_threshold)
            & (features["ret_1"] > 0)
        )
    if allow_short:
        signals["short"] = (
            valid
            & (features["regime_1h_trend"] < 0)
            & (features["ema_fast_atr_dist"] >= pullback_threshold)
            & (features["ret_1"] < 0)
        )
    return signals


def volatility_breakout(
    features: pd.DataFrame,
    *,
    allow_long: bool = True,
    allow_short: bool = True,
    breakout_threshold: float = 1.0,
    min_vol_surprise: float = 0.0,
) -> pd.DataFrame:
    signals = no_trade(features)
    valid = features[["regime_1h_trend", "ema_fast_atr_dist", "vol_surprise"]].notna().all(axis=1)
    active_volume = features["vol_surprise"] >= min_vol_surprise
    if allow_long:
        signals["long"] = (
            valid
            & active_volume
            & (features["regime_1h_trend"] > 0)
            & (features["ema_fast_atr_dist"] >= breakout_threshold)
        )
    if allow_short:
        signals["short"] = (
            valid
            & active_volume
            & (features["regime_1h_trend"] < 0)
            & (features["ema_fast_atr_dist"] <= -breakout_threshold)
        )
    return signals


def _validate_market(market: pd.DataFrame) -> None:
    missing = [col for col in ("open", "high", "low", "close") if col not in market.columns]
    if missing:
        raise ValueError(f"missing market columns: {missing}")
    if not isinstance(market.index, pd.DatetimeIndex):
        raise TypeError("market dataframe must use a DatetimeIndex")
    if not market.index.is_monotonic_increasing:
        raise ValueError("market dataframe index must be sorted ascending")


def _validate_signals(signals: pd.DataFrame) -> None:
    missing = [col for col in ("long", "short") if col not in signals.columns]
    if missing:
        raise ValueError(f"missing signal columns: {missing}")


def backtest_events(
    market: pd.DataFrame,
    features: pd.DataFrame,
    signals: pd.DataFrame,
    *,
    pair: str,
    risk_config: RiskConfig | None = None,
) -> pd.DataFrame:
    """Simulate non-overlapping next-open entries from close-known signals.

    Signals at row ``i`` can only enter at row ``i + 1`` open. Stop/target checks
    then run from the entry candle onward. If both are touched on the same candle,
    the stop wins.
    """
    _validate_market(market)
    _validate_signals(signals)
    risk_config = risk_config or RiskConfig()

    aligned_index = market.index.intersection(features.index).intersection(signals.index)
    market = market.loc[aligned_index]
    features = features.loc[aligned_index]
    signals = signals.loc[aligned_index].astype(bool)

    rows: list[dict[str, object]] = []
    i = 0
    while i < len(market) - 1:
        signal_row = signals.iloc[i]
        if bool(signal_row["long"]) and bool(signal_row["short"]):
            i += 1
            continue
        side = (
            "long" if bool(signal_row["long"]) else "short" if bool(signal_row["short"]) else None
        )
        if side is None:
            i += 1
            continue

        entry_i = i + 1
        entry_time = market.index[entry_i]
        entry_price = float(market["open"].iloc[entry_i])
        atr_value = float(features["atr"].iloc[i])
        if (
            not np.isfinite(atr_value)
            or atr_value <= 0
            or not np.isfinite(entry_price)
            or entry_price <= 0
        ):
            i += 1
            continue

        contract = build_risk_contract(entry_price, atr_value, side, risk_config)
        exit_i = entry_i
        exit_price = float(market["close"].iloc[entry_i])
        exit_reason = "end"

        last_i = min(entry_i + contract.max_holding_candles - 1, len(market) - 1)
        for j in range(entry_i, last_i + 1):
            high = float(market["high"].iloc[j])
            low = float(market["low"].iloc[j])
            close = float(market["close"].iloc[j])
            exit_i = j
            if side == "long":
                if low <= contract.stop_price:
                    exit_price = contract.stop_price
                    exit_reason = "stop"
                    break
                if high >= contract.target_price:
                    exit_price = contract.target_price
                    exit_reason = "target"
                    break
            else:
                if high >= contract.stop_price:
                    exit_price = contract.stop_price
                    exit_reason = "stop"
                    break
                if low <= contract.target_price:
                    exit_price = contract.target_price
                    exit_reason = "target"
                    break
            exit_price = close
            exit_reason = "time" if j == last_i else "end"

        gross = gross_return(side, entry_price, exit_price)
        rows.append(
            {
                "pair": pair,
                "side": side,
                "signal_time": market.index[i],
                "entry_time": entry_time,
                "exit_time": market.index[exit_i],
                "entry_price": entry_price,
                "exit_price": exit_price,
                "gross_return": gross,
                "net_return": net_return(gross, contract.round_trip_cost_bps),
                "turnover": turnover(contract.leverage),
                "exit_reason": exit_reason,
            }
        )
        i = exit_i + 1

    return pd.DataFrame(
        rows,
        columns=[
            "pair",
            "side",
            "signal_time",
            "entry_time",
            "exit_time",
            "entry_price",
            "exit_price",
            "gross_return",
            "net_return",
            "turnover",
            "exit_reason",
        ],
    )
