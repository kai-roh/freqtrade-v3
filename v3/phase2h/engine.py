"""Phase 2h walk-forward model and hourly simulator (PHASE2H_PREREGISTRATION.md §3).

Model: pooled ridge on cross-sectionally ranked features, predicting each symbol's
h-hour open-to-open return minus the universe mean. Refit on the first of every
month with every sample whose target was known before that month.

Simulator, per hour:

1. At the open of bar t, after a decision at the end of bar t-1, trade to the target
   book: conviction-sized, with hysteresis, market neutral, and a per-name cap.
2. During bar t, per-name volatility stops are checked against the bar's high/low.
3. Positions are marked to the close; funding settled at the end of the bar is paid.
4. The daily loss limit is checked at the close. A breach flattens at the next open,
   and there is no trading until the next UTC day.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .features import HourlyPanel, ranked

FEE_BPS = 5.0
NAME_CAP = 0.10
SIZE_PER_Z = 0.04
SIDE_CAP = 0.5
STOP_SIGMA = 2.5
DAILY_LOSS = 0.02
MIN_TRADE = 0.01  # weight change below this is not traded (except to or from zero)
TRAIN_START = pd.Timestamp("2022-01-01", tz="UTC")


@dataclass(frozen=True)
class Config:
    horizon: int  # hours between decisions and prediction horizon
    features: str  # "A" or "B"
    z_in: float
    hold_frac: float = 0.5  # keep a position while same-sign |z| >= hold_frac * z_in
    min_trade: float = MIN_TRADE
    smooth: int = 0  # EMA half-life of the predictions, in decisions (0 = none)
    stop_sigma: float = STOP_SIGMA

    def label(self) -> str:
        return f"H{self.horizon}-{self.features}-Z{self.z_in:g}"


def registered_grid() -> list[Config]:
    return [Config(h, f, z) for h in (1, 4) for f in ("A", "B") for z in (1.0, 1.5)]


def design(panel: HourlyPanel, names: tuple[str, ...]) -> np.ndarray:
    """Ranked features stacked as (T, S, K) float32."""
    return np.stack([ranked(panel.features[n], panel.universe) for n in names], axis=-1)


def targets(panel: HourlyPanel, horizon: int) -> np.ndarray:
    """h-hour open-to-open return from the open of t+1, minus the universe mean."""
    o = panel.open
    fwd = np.full_like(o, np.nan)
    fwd[: -(horizon + 1)] = o[horizon + 1 :] / o[1:-horizon] - 1
    fwd = np.where(panel.universe, fwd, np.nan)
    mean = np.nanmean(np.where(np.isfinite(fwd), fwd, np.nan), axis=1, keepdims=True)
    return fwd - mean


def walk_forward(
    panel: HourlyPanel, X: np.ndarray, y: np.ndarray, horizon: int, oos_start: pd.Timestamp,
    oos_end: pd.Timestamp,
) -> np.ndarray:  # fmt: skip
    """Out-of-sample predictions (T, S) at decision bars; NaN elsewhere."""
    index = panel.index
    pred = np.full(y.shape, np.nan, dtype=np.float32)
    decision = (index.hour % horizon) == 0
    months = pd.date_range(oos_start, oos_end, freq="MS", tz="UTC")
    t_index = np.arange(len(index))
    for m0 in months:
        m1 = m0 + pd.offsets.MonthBegin(1)
        start_bar = index.get_indexer([m0])[0]
        # A target on bar t is known at the open of bar t+1+h.
        known = (t_index + 1 + horizon) < start_bar
        rows = decision & known & (index >= TRAIN_START)
        Xt = X[rows]
        yt = y[rows]
        mask = panel.universe[rows] & np.isfinite(yt)
        Xf, yf = Xt[mask].astype(np.float64), yt[mask].astype(np.float64)
        lo, hi = np.quantile(yf, [0.01, 0.99])
        yf = np.clip(yf, lo, hi)
        lam = 1e-3 * len(yf)
        beta = np.linalg.solve(Xf.T @ Xf + lam * np.eye(Xf.shape[1]), Xf.T @ yf)
        target_rows = decision & (index >= m0) & (index < m1) & (index <= oos_end)
        p = X[target_rows] @ beta.astype(np.float32)
        p = np.where(panel.universe[target_rows], p, np.nan)
        pred[target_rows] = p
    return pred


def smooth_predictions(
    pred: np.ndarray, panel: HourlyPanel, horizon: int, halflife: int
) -> np.ndarray:
    """EMA of each symbol's predictions across decision bars (known values only)."""
    if halflife <= 0:
        return pred
    rows = np.flatnonzero((panel.index.hour % horizon) == 0)
    frame = pd.DataFrame(pred[rows])
    smoothed = frame.ewm(halflife=halflife, ignore_na=True).mean().to_numpy(np.float32)
    out = np.full_like(pred, np.nan)
    out[rows] = np.where(np.isfinite(pred[rows]), smoothed, np.nan)
    return out


@dataclass
class Result:
    hourly_equity: pd.Series
    daily_returns: pd.Series
    turnover: float = 0.0
    costs: float = 0.0
    funding: float = 0.0
    stops: int = 0
    loss_limits: int = 0
    hours_invested: int = 0
    gross_sum: float = 0.0
    hours: int = 0
    trades: int = 0
    extra: dict = field(default_factory=dict)


def target_book(
    z: np.ndarray, held: np.ndarray, z_in: float, blocked: np.ndarray, hold_frac: float = 0.5
) -> np.ndarray:
    """Conviction-sized, hysteresis, market-neutral target weights."""
    w = np.zeros_like(z)
    ok = np.isfinite(z) & ~blocked
    enter = ok & (np.abs(z) >= z_in)
    keep = ok & (held != 0) & (np.sign(z) == np.sign(held)) & (np.abs(z) >= z_in * hold_frac)
    chosen = enter | keep
    w[chosen] = np.sign(z[chosen]) * np.minimum(NAME_CAP, SIZE_PER_Z * np.abs(z[chosen]))
    longs, shorts = w[w > 0].sum(), -w[w < 0].sum()
    if longs <= 0 or shorts <= 0:
        return np.zeros_like(z)
    side = min(longs, shorts, SIDE_CAP)
    w[w > 0] *= side / longs
    w[w < 0] *= side / shorts
    return w


def simulate(
    panel: HourlyPanel, pred: np.ndarray, config: Config, start: pd.Timestamp,
    end: pd.Timestamp, cost_multiplier: float = 1.0,
) -> Result:  # fmt: skip
    index = panel.index
    t0 = index.get_indexer([start])[0]
    t1 = index.get_indexer([end + pd.Timedelta(hours=23)])[0]
    o, hi, lo, c = panel.open, panel.high, panel.low, panel.close
    S = o.shape[1]
    r1 = np.vstack([np.full((1, S), np.nan), c[1:] / c[:-1] - 1])
    sigma1 = pd.DataFrame(r1).rolling(168, min_periods=120).std().to_numpy()
    values = np.zeros(S)  # signed notional, marked at the last close (equity units)
    entry = np.zeros(S)
    stop_px = np.full(S, np.nan)
    cash = 1.0
    blocked = np.zeros(S, dtype=bool)
    flatten_next = False
    halted_day = None
    day_start_equity = 1.0
    current_day = None
    res = Result(pd.Series(dtype=float), pd.Series(dtype=float))
    equity_marks = np.zeros(t1 - t0 + 1)
    bps = (FEE_BPS + panel.tier_bps) / 10_000 * cost_multiplier

    def trade(t: int, new_values: np.ndarray, price: np.ndarray) -> float:
        nonlocal cash
        delta = new_values - values
        cost = float(np.nansum(np.abs(delta) * bps[t]))
        res.turnover += float(np.abs(delta).sum())
        res.costs += cost
        res.trades += int((np.abs(delta) > 0).sum())
        cash -= cost
        cash -= float(delta.sum())  # buying notional uses cash; selling returns it
        return cost

    for k, t in enumerate(range(t0, t1 + 1)):
        day = index[t].normalize()
        # Gap from the previous close to this open.
        gap = np.where(
            np.isfinite(o[t]) & np.isfinite(c[t - 1]) & (values != 0), o[t] / c[t - 1], 1.0
        )
        values = values * gap
        # Delisted / missing bar: exit at the last close.
        missing = (values != 0) & ~np.isfinite(o[t])
        if missing.any():
            new = values.copy()
            new[missing] = 0.0
            trade(t, new, o[t])
            values[missing] = 0.0
            stop_px[missing] = np.nan
        equity_open = cash + values.sum()
        if day != current_day:
            current_day = day
            day_start_equity = equity_open
        decision_due = (index[t - 1].hour % config.horizon) == 0
        if flatten_next:
            if np.any(values != 0):
                trade(t, np.zeros(S), o[t])
                values[:] = 0.0
                stop_px[:] = np.nan
            flatten_next = False
        elif decision_due and halted_day != day:
            blocked[:] = False
            z_raw = pred[t - 1]
            mu = np.nanmean(z_raw) if np.isfinite(z_raw).sum() >= 2 else np.nan
            sd = np.nanstd(z_raw) if np.isfinite(z_raw).sum() >= 2 else np.nan
            if np.isfinite(sd) and sd > 0:
                z = (z_raw - mu) / sd
                held_w = values / equity_open if equity_open > 0 else values * 0
                w = target_book(z, held_w, config.z_in, ~np.isfinite(o[t]), config.hold_frac)
                new = w * equity_open
                change = np.abs(new / equity_open - held_w)
                small = (
                    (change < config.min_trade)
                    & (new != 0)
                    & (values != 0)
                    & (np.sign(new) == np.sign(values))
                )
                new[small] = values[small]
                opened = (new != 0) & (
                    (values == 0)
                    | (np.sign(new) != np.sign(values))
                    | (np.abs(new) > np.abs(values))
                )
                trade(t, new, o[t])
                # Entry price / stop: reset on new or flipped positions; increases re-anchor.
                for j in np.flatnonzero(opened):
                    entry[j] = o[t, j]
                    s = sigma1[t - 1, j] * np.sqrt(config.horizon)
                    if np.isfinite(s) and s > 0:
                        stop_px[j] = o[t, j] * (1 - config.stop_sigma * s * np.sign(new[j]))
                    else:
                        stop_px[j] = np.nan
                values = new
                stop_px[values == 0] = np.nan
        # Intrabar stops.
        active = np.flatnonzero(values != 0)
        if active.size:
            for j in active:
                sp = stop_px[j]
                if not np.isfinite(sp):
                    continue
                if values[j] > 0 and lo[t, j] <= sp:
                    fill = min(o[t, j], sp)
                elif values[j] < 0 and hi[t, j] >= sp:
                    fill = max(o[t, j], sp)
                else:
                    continue
                exit_value = values[j] * fill / o[t, j]
                cost = abs(exit_value) * bps[t, j]
                cash += exit_value - cost
                res.costs += cost
                res.turnover += abs(exit_value)
                res.trades += 1
                res.stops += 1
                values[j] = 0.0
                stop_px[j] = np.nan
                blocked[j] = True
        # Mark to close.
        move = np.where((values != 0) & np.isfinite(c[t]) & np.isfinite(o[t]), c[t] / o[t], 1.0)
        values = values * move
        # Funding settled at the end of this bar (a long pays a positive rate).
        fund = float(np.nansum(values * panel.funding_end[t]))
        cash -= fund
        res.funding += fund
        equity = cash + values.sum()
        equity_marks[k] = equity
        gross = np.abs(values).sum() / equity if equity > 0 else 0
        res.gross_sum += gross
        res.hours += 1
        res.hours_invested += int(gross > 0)
        if halted_day != day and equity / day_start_equity - 1 <= -DAILY_LOSS and gross > 0:
            flatten_next = True
            halted_day = day
            res.loss_limits += 1
        if equity <= 0:
            equity_marks[k:] = 0
            break
    eq = pd.Series(equity_marks, index=index[t0 : t1 + 1])
    daily = eq.groupby(eq.index.normalize()).last()
    prev = daily.shift(1).fillna(1.0)
    res.hourly_equity = eq
    res.daily_returns = daily / prev - 1
    return res


def consistency(daily: pd.Series) -> dict:
    """Hit rates, worst week, concentration, yearly results (PHASE2H §6)."""
    r = daily.fillna(0.0)
    eq = (1 + r).cumprod()
    weeks = (1 + r).groupby(pd.Grouper(freq="W-SUN")).prod() - 1
    months = (1 + r).groupby(pd.Grouper(freq="ME")).prod() - 1
    years = (1 + r).groupby(r.index.year).prod() - 1
    lw = np.log1p(weeks).sort_values(ascending=False)
    top = int(np.ceil(0.10 * len(lw)))
    total_log = float(lw.sum())
    sd = float(r.std())
    return {
        "total": float(eq.iloc[-1] - 1),
        "cagr": float(eq.iloc[-1] ** (365 / len(r)) - 1) if eq.iloc[-1] > 0 else -1.0,
        "sharpe": float(r.mean() / sd * np.sqrt(365)) if sd > 0 else 0.0,
        "mdd": float((1 - eq / eq.cummax()).max()),
        "day_hit": float((r > 0).mean()),
        "week_hit": float((weeks > 0).mean()),
        "month_hit": float((months > 0).mean()),
        "median_week": float(weeks.median()),
        "worst_week": float(weeks.min()),
        "best_week": float(weeks.max()),
        "log_total": total_log,
        "log_without_top10pct_weeks": float(lw.iloc[top:].sum()),
        "concentration_share_kept": float(lw.iloc[top:].sum() / total_log)
        if total_log > 0
        else float("-inf"),
        "yearly": {int(y): float(v) for y, v in years.items()},
        "weeks": int(len(weeks)),
    }
