"""Frozen candle-scalping research. No exchange access; OHLC fills are proxies."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

from v3.divergence import _validate, _wilder


@dataclass(frozen=True)
class ScalpingConfig:
    strategy: str
    averaging: bool = False
    stress: bool = False
    initial_equity: float = 500.0
    max_notional: float = 500.0
    risk_usdt: float = 5.0
    lot_step: float = 0.001
    min_notional: float = 100.0


@dataclass
class BacktestResult:
    trades: pd.DataFrame
    fills: pd.DataFrame
    equity: pd.DataFrame
    summary: dict


def _candles(bars, frequency, count):
    grouped = bars.resample(frequency, closed="left", label="left")
    out = grouped.agg(dict(open="first", high="max", low="min", close="last", volume="sum"))
    out = out[grouped.close.count() == count].copy()
    out.index += pd.Timedelta(frequency)
    previous = out.close.shift()
    tr = pd.concat(
        [out.high - out.low, (out.high - previous).abs(), (out.low - previous).abs()], axis=1
    ).max(axis=1)
    out["atr"] = _wilder(tr)
    out["ema20"] = out.close.ewm(span=20, adjust=False, min_periods=20).mean()
    out["ema50"] = out.close.ewm(span=50, adjust=False, min_periods=50).mean()
    return out


def prepare_signals(minute_bars: pd.DataFrame, strategy: str) -> pd.DataFrame:
    """Emit only completed candles, indexed at their availability (close) time."""
    if _validate(minute_bars) != pd.Timedelta(minutes=1):
        raise ValueError("One-minute candles required")
    if strategy not in ("pullback", "range", "breakout"):
        raise ValueError("Unknown strategy")
    out = _candles(minute_bars, "30min", 30)
    hourly = _candles(minute_bars, "1h", 60).reindex(out.index, method="ffill")
    four = _candles(minute_bars, "4h", 240).reindex(out.index, method="ffill")
    trend = (hourly.ema20 > hourly.ema50) & (four.ema20 > four.ema50)
    delta = out.close.diff()
    gain, loss = _wilder(delta.clip(lower=0)), _wilder(-delta.clip(upper=0))
    out["rsi"] = 100 - 100 / (1 + gain / loss)
    out.loc[(gain == 0) & (loss == 0), "rsi"] = 50
    out["bearish"] = out.close < out.open
    volume = out.volume >= out.volume.shift().rolling(20).mean()
    big_bear = out.open - out.close >= 0.5 * out.atr
    out["breakout_level"] = out.high.shift().rolling(20).max()
    if strategy == "pullback":
        signal = trend & big_bear & big_bear.shift(fill_value=False) & (out.rsi <= 45) & volume
    elif strategy == "range":
        upper, lower = out.high.shift().rolling(48).max(), out.low.shift().rolling(48).min()
        width = (upper - lower) / ((upper + lower) / 2)
        signal = (
            width.between(0.01, 0.06)
            & out.close.between(lower, lower + 0.2 * (upper - lower))
            & (out.rsi <= 40)
            & ((hourly.ema20 - hourly.ema50).abs() <= 0.5 * hourly.atr)
            & volume
        )
    else:
        signal = (
            trend
            & (out.close > out.breakout_level + 0.1 * out.atr)
            & (out.close - out.open >= 0.5 * out.atr)
            & (out.volume >= 1.5 * out.volume.shift().rolling(20).mean())
        )
    out["entry_signal"] = signal.fillna(False)
    return out


def backtest(minute_bars, signals, config: ScalpingConfig, funding=None):
    """Simulate separate 1x sleeve, conservative passive fills and fixed-stop adds.

    Funding requires actual settlement marks. Limits model neither queue priority
    nor historical exchange filters; minute OHLC cannot recover execution ordering.
    Campaign max_exposure is an OHLC-high upper bound, not observed tick exposure.
    filled_notional_peak retains actual filled cost held intraminute, even if
    protection closes the entire campaign before the minute-close equity sample.
    """
    if _validate(minute_bars) != pd.Timedelta(minutes=1):
        raise ValueError("One-minute candles required")
    cfg = config
    if cfg.strategy not in ("pullback", "range", "breakout"):
        raise ValueError("Unknown strategy")
    if min(cfg.initial_equity, cfg.max_notional, cfg.risk_usdt, cfg.lot_step) <= 0:
        raise ValueError("Invalid configuration")
    if cfg.min_notional < 0:
        raise ValueError("Invalid minimum notional")
    if not isinstance(signals.index, pd.DatetimeIndex) or signals.index.tz is None:
        raise ValueError("Signals require timezone-aware close times")
    if signals.index.has_duplicates or not signals.index.is_monotonic_increasing:
        raise ValueError("Signals require unique increasing times")
    if funding is not None:
        if (
            not isinstance(funding.index, pd.DatetimeIndex)
            or funding.index.tz is None
            or funding.index.has_duplicates
        ):
            raise ValueError("Funding requires unique timezone-aware timestamps")
        if not np.isfinite(funding[["funding_rate", "mark_price"]].to_numpy()).all():
            raise ValueError("Funding must be finite")
        if (funding.mark_price <= 0).any():
            raise ValueError("Funding marks must be positive")
    index = minute_bars.index
    opens, highs, lows, closes = (
        minute_bars[x].to_numpy() for x in ("open", "high", "low", "close")
    )
    sigmap = {t.value: row for t, row in signals.iterrows()}
    events = [] if funding is None else list(funding.sort_index().itertuples())
    cursor = 0
    maker, taker = 0.0002, 0.0005
    slip = 0.0005 if cfg.stress else 0.0002
    through = slip
    cash, position, pending = cfg.initial_equity, None, None
    halted, paused, day = False, False, None
    reference, previous_equity = cfg.initial_equity, cfg.initial_equity
    trades, fills = [], []
    values = np.empty((len(index), 5))
    counts = dict(
        passive_rejections=0,
        unfilled_orders=0,
        rounding_refusals=0,
        risk_refusals=0,
        daily_halts=0,
        account_halts=0,
        entry_fills=0,
        add_fills=0,
    )

    def marked(price):
        return cash if position is None else cash + position["quantity"] * price - position["cost"]

    def close_position(raw, timestamp, reason, passive=False):
        nonlocal cash, position, pending
        p = position
        price = raw if passive else raw * (1 - slip)
        fee = p["quantity"] * price * (maker if passive else taker)
        price_pnl = p["quantity"] * raw - p["cost"]
        slippage = p["quantity"] * (raw - price)
        cash += price_pnl - slippage - fee
        totalfees = p["fees"] + fee
        trades.append(
            dict(
                entry_time=p["entry_time"],
                exit_time=timestamp,
                net_pnl=price_pnl - slippage - totalfees + p["funding_pnl"],
                price_pnl=price_pnl,
                fees=totalfees,
                slippage_cost=slippage,
                funding_pnl=p["funding_pnl"],
                adds=p["adds"],
                exit_reason=reason,
                stop=p["stop"],
                quantity=p["quantity"],
                entry_price=p["cost"] / p["quantity"],
                exit_price=price,
                max_exposure=p["max_exposure"],
                holding_minutes=(timestamp - p["entry_time"]).total_seconds() / 60,
            )
        )
        fills.append(
            dict(
                timestamp=timestamp,
                kind="exit",
                quantity=p["quantity"],
                price=price,
                fee=fee,
                reason=reason,
                campaign_id=p["campaign"],
            )
        )
        position, pending = None, None

    def protect(price, timestamp):
        nonlocal halted, paused, pending
        equity = marked(price)
        if equity <= cfg.initial_equity * 0.9:
            if not halted:
                counts["account_halts"] += 1
            halted = True
            pending = None
            if position is not None:
                close_position(price, timestamp, "account_halt")
        elif equity <= reference - 10 and not paused:
            paused = True
            counts["daily_halts"] += 1
            pending = None
            if position is not None:
                close_position(price, timestamp, "daily_halt")

    for i, timestamp in enumerate(index):
        o, h, low, c = opens[i], highs[i], lows[i], closes[i]
        filled_notional_peak = 0.0 if position is None else position["cost"]
        current_day = timestamp.date()
        if day != current_day:
            day, reference, paused = current_day, previous_equity, False
        while cursor < len(events) and events[cursor].Index <= timestamp:
            event = events[cursor]
            if position is not None and event.Index > position["entry_time"]:
                payment = position["quantity"] * event.mark_price * event.funding_rate
                cash -= payment
                position["funding_pnl"] -= payment
            cursor += 1
        protect(o, timestamp)
        exited = False
        s = sigmap.get(timestamp.value)
        if position is not None:
            if o <= position["stop"]:
                close_position(o, timestamp, "stop")
                exited = True
            elif (
                s is not None
                and cfg.strategy == "breakout"
                and s.close < position["breakout_level"]
            ):
                close_position(min(o, position["target"]), timestamp, "breakout_failure")
                exited = True
            elif i - position["entry_bar"] >= 240:
                close_position(min(o, position["target"]), timestamp, "timeout")
                exited = True
        if position is not None and low <= position["stop"]:
            close_position(position["stop"], timestamp + pd.Timedelta(minutes=1), "stop")
            exited = True
        if pending is not None and i >= pending["expires"]:
            pending = None
            counts["unfilled_orders"] += 1
        if not halted and not paused and not exited and pending is None and s is not None:
            kind = None
            if position is None and s.entry_signal and np.isfinite(s.atr) and s.atr > 0:
                kind = "entry"
            elif position is not None and cfg.averaging and position["adds"] < 2:
                threshold = position["first_price"] - (position["adds"] + 1) * 0.5 * position["atr"]
                if (
                    s.bearish
                    and s.close < threshold
                    and s.close < position["cost"] / position["quantity"]
                ):
                    kind = "add"
            if kind is not None:
                limit = s.close * (1 - 0.0002)
                stop = limit - 1.5 * s.atr if position is None else position["stop"]
                if limit >= o:
                    counts["passive_rejections"] += 1
                elif stop <= 0 or limit <= stop:
                    counts["risk_refusals"] += 1
                else:
                    pending = dict(
                        kind=kind,
                        limit=limit,
                        stop=stop,
                        atr=s.atr,
                        breakout_level=s.breakout_level,
                        expires=i + 5,
                    )
        filled = False
        if pending is not None and low < pending["limit"] * (1 - through):
            order, pending = pending, None
            price, stop = order["limit"], order["stop"]
            p = position
            cost, qty, paidfees, funding_paid = (
                (0.0, 0.0, 0.0, 0.0)
                if p is None
                else (p["cost"], p["quantity"], p["fees"], -p["funding_pnl"])
            )
            # Conservative equity at the worse of open/fill; include new maker fee.
            equity = min(marked(o), marked(price))
            cap = min(cfg.max_notional, equity)
            unitrisk = price - stop * (1 - slip) + price * maker + stop * (1 - slip) * taker
            existing_risk = (
                cost
                - qty * stop * (1 - slip)
                + paidfees
                + qty * stop * (1 - slip) * taker
                + funding_paid
            )
            allowed = min(
                (200 if p is None else 150) / price,
                (cap - cost) / (price * (1 + maker)),
                (cfg.risk_usdt - existing_risk) / unitrisk,
            )
            quantity = max(0, math.floor((allowed + 1e-12) / cfg.lot_step) * cfg.lot_step)
            if quantity <= 0 or quantity * price < cfg.min_notional:
                counts["rounding_refusals" if allowed > 0 else "risk_refusals"] += 1
            else:
                fee = quantity * price * maker
                cash -= fee
                if p is None:
                    position = dict(
                        entry_time=timestamp,
                        entry_bar=i,
                        quantity=0.0,
                        cost=0.0,
                        fees=0.0,
                        funding_pnl=0.0,
                        adds=0,
                        first_price=price,
                        atr=order["atr"],
                        stop=stop,
                        breakout_level=order["breakout_level"],
                        campaign=len(trades),
                        max_exposure=0.0,
                    )
                    p = position
                else:
                    p["adds"] += 1
                p["quantity"] += quantity
                p["cost"] += quantity * price
                filled_notional_peak = max(filled_notional_peak, p["cost"])
                p["fees"] += fee
                p["target"] = p["cost"] / p["quantity"] * 1.003
                fills.append(
                    dict(
                        timestamp=timestamp,
                        kind=order["kind"],
                        quantity=quantity,
                        price=price,
                        fee=fee,
                        reason="passive",
                        campaign_id=p["campaign"],
                    )
                )
                counts["entry_fills" if order["kind"] == "entry" else "add_fills"] += 1
                filled = True
        if position is not None:
            position["max_exposure"] = max(position["max_exposure"], position["quantity"] * h)
            if low <= position["stop"]:
                close_position(
                    min(o, position["stop"]), timestamp + pd.Timedelta(minutes=1), "stop"
                )
            elif not filled and h > position["target"] * (1 + through):
                close_position(
                    position["target"], timestamp + pd.Timedelta(minutes=1), "target", True
                )
        endtime = timestamp + pd.Timedelta(minutes=1)
        protect(c, endtime)
        if i == len(index) - 1 and position is not None:
            close_position(c, endtime, "end")
        equity = marked(c)
        exposure = 0.0 if position is None else position["quantity"] * c
        values[i] = equity, cash, equity - cash, exposure, filled_notional_peak
        previous_equity = equity
    if pending is not None:
        counts["unfilled_orders"] += 1
    eq = pd.DataFrame(
        values,
        index=index + pd.Timedelta(minutes=1),
        columns=["equity", "cash", "unrealized_pnl", "exposure", "filled_notional_peak"],
    )
    tf = pd.DataFrame(
        trades,
        columns=[
            "entry_time",
            "exit_time",
            "net_pnl",
            "price_pnl",
            "fees",
            "slippage_cost",
            "funding_pnl",
            "adds",
            "exit_reason",
            "stop",
            "quantity",
            "entry_price",
            "exit_price",
            "max_exposure",
            "holding_minutes",
        ],
    )
    ff = pd.DataFrame(
        fills, columns=["timestamp", "kind", "quantity", "price", "fee", "reason", "campaign_id"]
    )
    path = np.r_[cfg.initial_equity, eq.equity.to_numpy()]
    pnl = tf.net_pnl
    losses, gains = -pnl[pnl < 0].sum(), pnl[pnl > 0].sum()
    summary = dict(
        initial_equity=cfg.initial_equity,
        final_equity=float(path[-1]),
        net_pnl=float(path[-1] - cfg.initial_equity),
        trades=len(tf),
        return_pct=float((path[-1] / cfg.initial_equity - 1) * 100),
        max_drawdown_pct=float((path / np.maximum.accumulate(path) - 1).min() * 100),
        win_rate=float((pnl > 0).mean()) if len(tf) else 0.0,
        profit_factor=float(gains / losses) if losses else None,
        max_exposure=float(eq.exposure.max()),
        max_filled_notional=float(eq.filled_notional_peak.max()),
        average_exposure=float(eq.exposure.mean()),
        worst_campaign=float(pnl.min()) if len(tf) else 0.0,
        max_holding_minutes=float(tf.holding_minutes.max()) if len(tf) else 0.0,
        **{
            key: float(tf[key].sum())
            for key in ("price_pnl", "fees", "slippage_cost", "funding_pnl")
        },
        diagnostics=counts.copy(),
        **counts,
    )
    return BacktestResult(tf, ff, eq, summary)
