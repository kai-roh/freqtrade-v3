"""Isolated, causal RSI-divergence research; never submits exchange orders.

Input timestamps are candle OPEN times. Signals exist only at candle close;
execution is at the following candle open. Funding rates are settled observations.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class DivergenceConfig:
    initial_equity: float = 500.0
    max_notional: float = 500.0
    risk_usdt: float = 2.5
    fee_bps: float = 5.0
    slippage_bps: float = 2.0
    lot_step: float = 0.001
    min_notional: float = 100.0
    max_holding_bars: int = 10


@dataclass
class BacktestResult:
    trades: pd.DataFrame
    equity: pd.DataFrame
    summary: dict


def _validate(bars: pd.DataFrame) -> pd.Timedelta:
    if len(bars) < 2 or not isinstance(bars.index, pd.DatetimeIndex):
        raise ValueError("At least two timestamp-indexed candles are required")
    if bars.index.tz is None:
        raise ValueError("Candle timestamps must be timezone-aware")
    if not bars.index.is_monotonic_increasing or bars.index.has_duplicates:
        raise ValueError("Candles must have unique increasing timestamps")
    differences = bars.index.to_series().diff().dropna()
    interval = differences.iloc[0]
    if interval not in (pd.Timedelta(minutes=1), pd.Timedelta(minutes=5)):
        raise ValueError("Only 1m and 5m candles are supported")
    if not (differences == interval).all():
        raise ValueError("Missing candles: split or repair the data before backtesting")
    values = bars[["open", "high", "low", "close", "volume"]]
    if not np.isfinite(values.to_numpy()).all() or (values.iloc[:, :4] <= 0).any().any():
        raise ValueError("OHLCV must be finite and prices positive")
    if (
        (bars.high < bars[["open", "close", "low"]].max(axis=1))
        | (bars.low > bars[["open", "close", "high"]].min(axis=1))
        | (bars.volume < 0)
    ).any():
        raise ValueError("Invalid OHLCV candle")
    return interval


def _wilder(series: pd.Series, period: int = 14) -> pd.Series:
    seed = series.rolling(period, min_periods=period).mean()
    valid = np.flatnonzero(seed.notna().to_numpy())
    if not len(valid):
        return seed
    start = valid[0]
    source = series.copy()
    source.iloc[:start] = np.nan
    source.iloc[start] = seed.iloc[start]
    return source.ewm(alpha=1 / period, adjust=False, min_periods=1).mean()


def prepare_signals(bars: pd.DataFrame) -> pd.DataFrame:
    """Frozen rule set, with pivot information emitted at confirmation, never backdated."""
    interval = _validate(bars)
    out = bars.copy()
    delta = out.close.diff()
    gain, loss = _wilder(delta.clip(lower=0)), _wilder(-delta.clip(upper=0))
    out["rsi"] = 100 - 100 / (1 + gain / loss)
    out.loc[(gain == 0) & (loss == 0), "rsi"] = 50.0
    previous = out.close.shift()
    tr = pd.concat(
        [out.high - out.low, (out.high - previous).abs(), (out.low - previous).abs()], axis=1
    ).max(axis=1)
    out["atr"] = _wilder(tr)
    hourly = out.resample("1h").agg({"close": "last", "open": "count"})
    hourly = hourly[hourly.open == int(pd.Timedelta(hours=1) / interval)]
    fast = hourly.close.ewm(span=50, adjust=False, min_periods=200).mean()
    slow = hourly.close.ewm(span=200, adjust=False, min_periods=200).mean()
    trend = (fast > slow) & (fast > fast.shift(3))
    trend.index = trend.index + pd.Timedelta(hours=1)
    out["trend"] = trend.reindex(out.index + interval, method="ffill").fillna(False).to_numpy()
    out["volume_ok"] = out.volume >= 1.2 * out.volume.shift().rolling(20).mean()
    low, high = out.low, out.high
    low_pivot = pd.Series(True, index=out.index)
    high_pivot = low_pivot.copy()
    for distance in (1, 2):
        low_pivot &= (low < low.shift(distance)) & (low < low.shift(-distance))
        high_pivot &= (high > high.shift(distance)) & (high > high.shift(-distance))
    out["low_confirmed"] = low_pivot.shift(2, fill_value=False)
    out["high_confirmed"] = high_pivot.shift(2, fill_value=False)
    n = len(out)
    signal = np.zeros(n, dtype=bool)
    veto = np.zeros(n, dtype=bool)
    stops, targets = np.full(n, np.nan), np.full(n, np.nan)
    lows, highs, rsi = low.to_numpy(), high.to_numpy(), out.rsi.to_numpy()
    atr = out.atr.to_numpy()
    target_history = high.shift().rolling(20).max().to_numpy()
    previous_low = previous_high = None
    hidden_at = None
    hidden = False
    lc, hc = out.low_confirmed.to_numpy(), out.high_confirmed.to_numpy()
    eligible = (out.trend & out.volume_ok).to_numpy()
    for i in range(n):
        p = i - 2
        if hc[i]:
            hidden = (
                previous_high is not None
                and 5 <= p - previous_high <= 60
                and highs[p] <= highs[previous_high] * 0.9995
                and rsi[p] >= rsi[previous_high] + 3
            )
            hidden_at = p
            previous_high = p
        veto[i] = bool(hidden and hidden_at is not None and i - hidden_at <= 30)
        if lc[i]:
            if (
                previous_low is not None
                and 5 <= p - previous_low <= 60
                and lows[p] <= lows[previous_low] * 0.9995
                and rsi[p] >= rsi[previous_low] + 3
                and eligible[i]
                and not veto[i]
            ):
                signal[i] = True
                stops[i] = lows[p] - 0.25 * atr[i]
                targets[i] = target_history[p]
            previous_low = p
    out["hidden_bearish_veto"] = veto
    out["entry_signal"], out["stop"], out["target"] = signal, stops, targets
    return out


def backtest(
    bars: pd.DataFrame,
    config: DivergenceConfig | None = None,
    funding: pd.DataFrame | None = None,
    *,
    prepared: bool = False,
) -> BacktestResult:
    """Cash plus marked PnL equity, adverse fills, conservative same-bar exits.

    ``prepared`` accepts frozen externally prepared signals (also useful for audits).
    Funding is charged before open-time entries, to positions already open only.
    """
    cfg = config or DivergenceConfig()
    interval = _validate(bars)
    if (
        min(cfg.initial_equity, cfg.max_notional, cfg.risk_usdt, cfg.lot_step, cfg.max_holding_bars)
        <= 0
        or min(cfg.fee_bps, cfg.slippage_bps, cfg.min_notional) < 0
    ):
        raise ValueError("Invalid backtest configuration")
    frame = bars if prepared else prepare_signals(bars)
    fee, slip = cfg.fee_bps / 10000, cfg.slippage_bps / 10000
    cash = cfg.initial_equity
    position = None
    trades, equities = [], []
    if funding is not None:
        if not isinstance(funding.index, pd.DatetimeIndex) or funding.index.tz is None:
            raise ValueError("Funding timestamps must be timezone-aware")
        if funding.index.has_duplicates:
            raise ValueError("Funding timestamps must be unique")
        if not np.isfinite(funding["funding_rate"].to_numpy()).all():
            raise ValueError("Funding rates must be finite")
        if "mark_price" in funding and (
            not np.isfinite(funding.mark_price).all() or (funding.mark_price <= 0).any()
        ):
            raise ValueError("Funding marks must be finite and positive")
    funding_events = [] if funding is None else list(funding.sort_index().iterrows())
    funding_cursor = 0
    arrays = {
        name: frame[name].to_numpy()
        for name in ("open", "high", "low", "close", "entry_signal", "stop", "target")
    }
    timestamps = frame.index
    skipped = 0

    def close_position(raw_price, timestamp, reason):
        nonlocal cash, position
        fill = raw_price * (1 - slip)
        gross = position["quantity"] * (fill - position["entry_price"])
        exit_fee = position["quantity"] * fill * fee
        cash += gross - exit_fee
        trade = dict(position)
        price_pnl = position["quantity"] * (raw_price - position["raw_entry_price"])
        slippage_cost = position["quantity"] * (
            position["entry_price"] - position["raw_entry_price"] + raw_price - fill
        )
        trade.update(
            exit_time=timestamp,
            exit_price=fill,
            raw_exit_price=raw_price,
            price_pnl=price_pnl,
            slippage_cost=slippage_cost,
            exit_reason=reason,
            gross_pnl=gross,
            exit_fee=exit_fee,
            net_pnl=gross - position["entry_fee"] - exit_fee - position["funding"],
        )
        trades.append(trade)
        position = None

    for i, timestamp in enumerate(timestamps):
        open_, high, low, close = (arrays[name][i] for name in ("open", "high", "low", "close"))
        while (
            funding_cursor < len(funding_events) and funding_events[funding_cursor][0] <= timestamp
        ):
            settled_at, event = funding_events[funding_cursor]
            if position is not None and settled_at > position["entry_time"]:
                mark = event.get("mark_price", arrays["close"][max(i - 1, 0)])
                payment = position["quantity"] * mark * event["funding_rate"]
                cash -= payment
                position["funding"] += payment
            funding_cursor += 1
        exited = False
        if position is not None and i - position["entry_bar"] >= cfg.max_holding_bars:
            # Resting target still caps execution at the timeout open.
            # A downside gap keeps its adverse open rather than the stop price.
            close_position(min(open_, position["target"]), timestamp, "timeout")
            exited = True
        if position is None and not exited and i > 0 and arrays["entry_signal"][i - 1]:
            entry = open_ * (1 + slip)
            stop, target = arrays["stop"][i - 1], arrays["target"][i - 1]
            distance = entry - stop
            # Budget includes entry/stop fees and adverse stop execution.
            unit_risk = entry - stop * (1 - slip) + fee * (entry + stop * (1 - slip))
            if (
                np.isfinite([stop, target]).all()
                and stop > 0
                and distance > 0
                and target - entry >= max(distance, entry * 0.002)
                and cash > 0
            ):
                size = min(
                    cfg.max_notional / entry, cash / (entry * (1 + fee)), cfg.risk_usdt / unit_risk
                )
                quantity = math.floor(size / cfg.lot_step) * cfg.lot_step
                if quantity > 0 and quantity * entry >= cfg.min_notional:
                    entry_fee = quantity * entry * fee
                    cash -= entry_fee
                    position = dict(
                        entry_time=timestamp,
                        entry_bar=i,
                        entry_price=entry,
                        raw_entry_price=open_,
                        quantity=quantity,
                        stop=stop,
                        target=target,
                        entry_fee=entry_fee,
                        funding=0.0,
                    )
                else:
                    skipped += 1
            else:
                skipped += 1
        if position is not None:
            if low <= position["stop"]:
                close_position(min(open_, position["stop"]), timestamp + interval, "stop")
            elif high >= position["target"]:
                close_position(position["target"], timestamp + interval, "target")
            elif i == len(frame) - 1:
                close_position(close, timestamp + interval, "end")
        unrealized = (
            0 if position is None else position["quantity"] * (close - position["entry_price"])
        )
        equities.append((timestamp + interval, cash + unrealized, cash, unrealized))
    equity = pd.DataFrame(
        equities, columns=["timestamp", "equity", "cash", "unrealized_pnl"]
    ).set_index("timestamp")
    trade_frame = pd.DataFrame(trades)
    values = np.r_[cfg.initial_equity, equity.equity.to_numpy()]
    drawdown = values / np.maximum.accumulate(values) - 1
    pnl = trade_frame.net_pnl if len(trade_frame) else pd.Series(dtype=float)
    losses, gains = -pnl[pnl < 0].sum(), pnl[pnl > 0].sum()
    summary = dict(
        initial_equity=cfg.initial_equity,
        final_equity=float(values[-1]),
        net_pnl=float(values[-1] - cfg.initial_equity),
        return_pct=float((values[-1] / cfg.initial_equity - 1) * 100),
        max_drawdown_pct=float(drawdown.min() * 100),
        trades=len(trades),
        win_rate=float((pnl > 0).mean()) if len(pnl) else 0.0,
        profit_factor=float(gains / losses) if losses else None,
        average_net_pnl=float(pnl.mean()) if len(pnl) else 0.0,
        skipped_signals=skipped,
        fees=float((trade_frame.entry_fee + trade_frame.exit_fee).sum()) if len(trades) else 0.0,
        price_pnl=float(trade_frame.price_pnl.sum()) if len(trades) else 0.0,
        slippage_cost=float(trade_frame.slippage_cost.sum()) if len(trades) else 0.0,
        funding_pnl=float(-trade_frame.funding.sum()) if len(trades) else 0.0,
    )
    return BacktestResult(trade_frame, equity, summary)
