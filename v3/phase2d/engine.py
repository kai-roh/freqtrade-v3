"""Phase 2d daily portfolio engine (docs/PHASE2D_PREREGISTRATION.md §4).

Decisions use data up to day t's close; orders fill at day t+1's open; returns are
open-to-open. Between rebalances the weights drift with prices. Costs are one-way
fee plus liquidity-tiered slippage on every weight change; perpetual positions pay
the day's summed funding rate (a long pays a positive rate).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .data import DailyPanel

REUSE_GAP_DAYS = 14
MIN_HISTORY_DAYS = 90
LIQUIDITY_WINDOW = 30
SPOT_FEE_BPS = 10.0
PERP_FEE_BPS = 5.0


def slippage_bps(rank: float) -> float:
    if rank <= 10:
        return 5.0
    if rank <= 20:
        return 10.0
    return 20.0


def split_reused_symbols(panel: DailyPanel, gap: int = REUSE_GAP_DAYS) -> DailyPanel:
    """Split a symbol's series at every run of ``gap``+ missing days (a relisted ticker)."""
    columns: dict[str, dict[str, pd.Series]] = {"open": {}, "close": {}, "quote_volume": {}}
    funding: dict[str, pd.Series] = {}
    for symbol in panel.close.columns:
        valid = panel.close[symbol].notna()
        if not valid.any():
            continue
        days = valid[valid].index
        breaks = np.flatnonzero(np.diff(days) > pd.Timedelta(days=gap)) + 1
        starts = [days[0], *days[breaks]]
        ends = [*days[breaks - 1], days[-1]]
        for n, (a, b) in enumerate(zip(starts, ends, strict=True)):
            name = symbol if n == 0 else f"{symbol}#{n + 1}"
            mask = (panel.close.index >= a) & (panel.close.index <= b)
            for f in columns:
                columns[f][name] = getattr(panel, f)[symbol].where(mask)
            if panel.funding is not None:
                funding[name] = panel.funding[symbol].where(mask, 0.0)
    return DailyPanel(
        open=pd.DataFrame(columns["open"]),
        close=pd.DataFrame(columns["close"]),
        quote_volume=pd.DataFrame(columns["quote_volume"]),
        funding=pd.DataFrame(funding) if panel.funding is not None else None,
    )


@dataclass
class Market:
    """Arrays and point-in-time features shared by every strategy on one venue."""

    panel: DailyPanel
    kind: str  # "spot" or "perp"
    days: pd.DatetimeIndex = field(init=False)
    symbols: list[str] = field(init=False)
    open: np.ndarray = field(init=False)
    close: np.ndarray = field(init=False)
    funding: np.ndarray = field(init=False)
    rank: np.ndarray = field(init=False)  # liquidity rank among eligible (1 = most liquid)

    def __post_init__(self) -> None:
        p = self.panel
        self.days = p.close.index
        self.symbols = list(p.close.columns)
        self.open = p.open.to_numpy(float)
        self.close = p.close.to_numpy(float)
        self.funding = (
            p.funding.reindex(columns=self.symbols).fillna(0.0).to_numpy(float)
            if p.funding is not None
            else np.zeros_like(self.close)
        )
        age = p.close.notna().cumsum().where(p.close.notna())
        liquidity = p.quote_volume.rolling(LIQUIDITY_WINDOW, min_periods=20).median()
        eligible = (age >= MIN_HISTORY_DAYS) & p.close.notna() & liquidity.notna()
        self.rank = liquidity.where(eligible).rank(axis=1, ascending=False).to_numpy(float)
        self._cache: dict[tuple, np.ndarray] = {}

    def index_of(self, day: pd.Timestamp) -> int:
        return int(self.days.get_indexer([day])[0])

    def momentum(self, lookback: int) -> np.ndarray:
        key = ("mom", lookback)
        if key not in self._cache:
            c = self.panel.close
            self._cache[key] = (c / c.shift(lookback) - 1.0).to_numpy(float)
        return self._cache[key]

    def sma(self, length: int) -> np.ndarray:
        key = ("sma", length)
        if key not in self._cache:
            self._cache[key] = (
                self.panel.close.rolling(length, min_periods=length).mean().to_numpy(float)
            )
        return self._cache[key]

    def volatility(self, length: int = 60) -> np.ndarray:
        key = ("vol", length)
        if key not in self._cache:
            r = np.log(self.panel.close).diff()
            self._cache[key] = r.rolling(length, min_periods=length // 2).std().to_numpy(float)
        return self._cache[key]

    def universe(self, i: int, n: int) -> np.ndarray:
        """Column indices of the top-``n`` liquid eligible symbols on day ``i``."""
        r = self.rank[i]
        return np.flatnonzero(r <= n)


# A strategy maps (market, decision-day index) to target weights {column: weight}.
WeightFn = Callable[[Market, int], dict[int, float]]


@dataclass(frozen=True)
class Result:
    returns: pd.Series  # daily net returns, indexed by the day the return is earned
    turnover: float  # sum of |weight change| over the run
    costs: float  # sum of cost fractions charged
    funding: float  # sum of funding fractions paid (positive = paid)


def simulate(
    market: Market,
    weights: WeightFn,
    *,
    start: pd.Timestamp,
    end: pd.Timestamp,
    every: int = 7,
    anchor: pd.Timestamp = pd.Timestamp("2017-12-31", tz="UTC"),
    cost_multiplier: float = 1.0,
) -> Result:
    """Run one account from flat over days [start, end] (returns earned on those days).

    A decision is taken at the close of day t when (t - anchor) is a multiple of
    ``every`` days; it fills at the open of t+1. Day d's return is open(d) -> open(d+1).
    """
    fee = PERP_FEE_BPS if market.kind == "perp" else SPOT_FEE_BPS
    i0, i1 = market.index_of(start), market.index_of(end)
    if i0 < 1 or i1 < 0 or i1 + 1 >= len(market.days):
        raise ValueError("window must leave one day before start and one after end")
    held = np.zeros(len(market.symbols))
    out = np.zeros(i1 - i0 + 1)
    turnover = costs = funding_paid = 0.0
    for k, i in enumerate(range(i0, i1 + 1)):
        decision = i - 1
        if (market.days[decision] - anchor).days % every == 0:
            target = np.zeros_like(held)
            for j, w in weights(market, decision).items():
                target[j] = w
            # Orders that cannot fill (no open today) leave that slot in cash.
            no_open = np.isnan(market.open[i])
            target[no_open & (held == 0)] = 0.0
            target[no_open & (held != 0)] = held[no_open & (held != 0)]
            delta = target - held
            changed = np.flatnonzero(np.abs(delta) > 1e-12)
            if changed.size:
                ranks = market.rank[decision, changed]
                bps = np.array([fee + slippage_bps(r if not np.isnan(r) else 99) for r in ranks])
                cost = float(np.sum(np.abs(delta[changed]) * bps)) / 10_000 * cost_multiplier
                turnover += float(np.sum(np.abs(delta[changed])))
                costs += cost
            else:
                cost = 0.0
            held = target
        else:
            cost = 0.0
        # Values as fractions of the equity at today's open, after paying today's trade cost.
        base = 1.0 - cost
        active = np.flatnonzero(held != 0)
        values = held[active] * base
        cash = base - float(np.sum(values))
        o0 = market.open[i, active]
        o1 = market.open[i + 1, active]
        c0 = market.close[i, active]
        # Delisted/gapped tomorrow: exit at today's close.
        exit_now = np.isnan(o1)
        price_next = np.where(exit_now, c0, o1)
        r = np.where(np.isnan(price_next) | np.isnan(o0), 0.0, price_next / o0 - 1.0)
        fund = float(np.sum(values * market.funding[i, active]))
        cash -= fund
        values = values * (1.0 + r)
        if exit_now.any():
            exits = np.flatnonzero(exit_now)
            ranks = market.rank[i, active[exits]]
            bps = np.array([fee + slippage_bps(rr if not np.isnan(rr) else 99) for rr in ranks])
            exit_cost = float(np.sum(np.abs(values[exits]) * bps)) / 10_000 * cost_multiplier
            cash += float(np.sum(values[exits])) - exit_cost
            values[exits] = 0.0
            costs += exit_cost
        equity = cash + float(np.sum(values))
        out[k] = equity - 1.0
        funding_paid += fund
        if equity <= 0:
            out[k] = -1.0
            break
        held[active] = values / equity
    return Result(
        returns=pd.Series(out, index=market.days[i0 : i1 + 1]),
        turnover=turnover,
        costs=costs,
        funding=funding_paid,
    )


def metrics(returns: pd.Series) -> dict[str, float]:
    r = returns.fillna(0.0)
    equity = (1.0 + r).cumprod()
    years = len(r) / 365.0
    total = float(equity.iloc[-1] - 1.0)
    cagr = float(equity.iloc[-1] ** (1 / years) - 1.0) if equity.iloc[-1] > 0 else -1.0
    sd = float(r.std())
    sharpe = float(r.mean() / sd * np.sqrt(365)) if sd > 0 else 0.0
    mdd = float((1 - equity / equity.cummax()).max())
    yearly = (1.0 + r).groupby(r.index.year).prod() - 1.0
    return {
        "total": total,
        "cagr": cagr,
        "sharpe": sharpe,
        "mdd": mdd,
        "vol": sd * np.sqrt(365),
        "years_positive": int((yearly > 0).sum()),
        "years": int(len(yearly)),
        "yearly": {int(y): float(v) for y, v in yearly.items()},
    }
