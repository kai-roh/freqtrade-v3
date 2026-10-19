"""Phase 2d strategy families and the registered grid (PHASE2D_PREREGISTRATION.md §5)."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from itertools import product

import numpy as np

from .engine import Market, WeightFn

BTC = "BTCUSDT"


@dataclass(frozen=True)
class Config:
    family: str  # F1..F6 or a benchmark name
    n: int = 10  # universe size
    lookback: int = 0  # momentum / reversal / SMA length
    k: int = 0  # names held per side
    market_filter: bool = False  # F1: invest only when BTC close > SMA100
    trend: int = 0  # F3: SMA length of the trend gate
    weighting: str = "equal"  # F2: "equal" or "invvol"

    @property
    def venue(self) -> str:
        return "perp" if self.family in {"F4", "F5"} else "spot"

    @property
    def every(self) -> int:
        if self.family == "F6":
            return self.lookback
        if self.family in {"EW10", "BTCETH"}:
            return 30
        if self.family == "BTC":
            return 100_000  # bought once at the start
        return 7

    def label(self) -> str:
        parts = [self.family, f"N{self.n}"]
        if self.lookback:
            parts.append(f"L{self.lookback}")
        if self.k:
            parts.append(f"K{self.k}")
        if self.trend:
            parts.append(f"T{self.trend}")
        if self.market_filter:
            parts.append("btcF")
        if self.family == "F2":
            parts.append(self.weighting)
        return "-".join(parts)

    def to_json(self) -> dict:
        return {**asdict(self), "label": self.label()}


def registered_grid() -> list[Config]:
    grid: list[Config] = []
    for n, lb, k, f in product((10, 30), (7, 14, 30, 60, 90), (3, 5), (False, True)):
        grid.append(Config("F1", n=n, lookback=lb, k=k, market_filter=f))
    for n, lb, w in product((10, 30), (20, 50, 100, 200), ("equal", "invvol")):
        grid.append(Config("F2", n=n, lookback=lb, weighting=w))
    for n, lb, t, k in product((10, 30), (14, 30, 60), (50, 100), (3, 5)):
        grid.append(Config("F3", n=n, lookback=lb, trend=t, k=k))
    for n, lb, k in product((10, 30), (7, 14, 30, 60, 90), (3, 5)):
        grid.append(Config("F4", n=n, lookback=lb, k=k))
    for n, lb in product((10, 30), (20, 50, 100, 200)):
        grid.append(Config("F5", n=n, lookback=lb))
    for n, lb, k in product((10, 30), (1, 3, 7), (3, 5)):
        grid.append(Config("F6", n=n, lookback=lb, k=k))
    return grid


BENCHMARKS = (Config("BTC", n=1), Config("BTCETH", n=2), Config("EW10", n=10))


def _top(values: np.ndarray, cols: np.ndarray, k: int, largest: bool = True) -> np.ndarray:
    ok = cols[~np.isnan(values[cols])]
    if ok.size == 0:
        return ok
    order = np.argsort(values[ok], kind="stable")
    chosen = order[::-1][:k] if largest else order[:k]
    return ok[chosen]


def weight_fn(config: Config, market: Market) -> WeightFn:
    c = config
    btc = market.symbols.index(BTC) if BTC in market.symbols else None

    if c.family == "BTC":
        return lambda m, i: {btc: 1.0}
    if c.family == "BTCETH":
        eth = market.symbols.index("ETHUSDT")
        return lambda m, i: {btc: 0.5, eth: 0.5}
    if c.family == "EW10":

        def ew(m: Market, i: int) -> dict[int, float]:
            cols = m.universe(i, 10)
            return {int(j): 1.0 / len(cols) for j in cols} if len(cols) else {}

        return ew

    if c.family == "F1":
        mom = market.momentum(c.lookback)
        btc_sma = market.sma(100)

        def f1(m: Market, i: int) -> dict[int, float]:
            if c.market_filter and not (m.close[i, btc] > btc_sma[i, btc]):
                return {}
            chosen = _top(mom[i], m.universe(i, c.n), c.k)
            return {int(j): 1.0 / c.k for j in chosen}

        return f1

    if c.family == "F2":
        sma = market.sma(c.lookback)
        vol = market.volatility(60)

        def f2(m: Market, i: int) -> dict[int, float]:
            cols = m.universe(i, c.n)
            if cols.size == 0:
                return {}
            up = cols[m.close[i, cols] > sma[i, cols]]
            if c.weighting == "equal":
                return {int(j): 1.0 / c.n for j in up}
            inv = 1.0 / vol[i, cols]
            inv = np.where(np.isfinite(inv), inv, 0.0)
            total = inv.sum()
            if total <= 0:
                return {}
            share = dict(zip(cols.tolist(), (inv / total).tolist(), strict=True))
            return {int(j): share[int(j)] for j in up if share[int(j)] > 0}

        return f2

    if c.family == "F3":
        mom = market.momentum(c.lookback)
        sma = market.sma(c.trend)

        def f3(m: Market, i: int) -> dict[int, float]:
            cols = m.universe(i, c.n)
            up = cols[m.close[i, cols] > sma[i, cols]]
            chosen = _top(mom[i], up, c.k)
            return {int(j): 1.0 / c.k for j in chosen}

        return f3

    if c.family == "F4":
        mom = market.momentum(c.lookback)

        def f4(m: Market, i: int) -> dict[int, float]:
            cols = m.universe(i, c.n)
            ok = cols[~np.isnan(mom[i, cols])]
            if ok.size < 2 * c.k:
                return {}
            longs = _top(mom[i], ok, c.k)
            shorts = _top(mom[i], ok, c.k, largest=False)
            out = {int(j): 0.5 / c.k for j in longs}
            out.update({int(j): -0.5 / c.k for j in shorts})
            return out

        return f4

    if c.family == "F5":
        sma = market.sma(c.lookback)

        def f5(m: Market, i: int) -> dict[int, float]:
            cols = m.universe(i, c.n)
            ok = cols[~np.isnan(sma[i, cols])]
            return {int(j): (1.0 if m.close[i, j] > sma[i, j] else -1.0) / c.n for j in ok}

        return f5

    if c.family == "F6":
        mom = market.momentum(c.lookback)

        def f6(m: Market, i: int) -> dict[int, float]:
            chosen = _top(mom[i], m.universe(i, c.n), c.k, largest=False)
            return {int(j): 1.0 / c.k for j in chosen}

        return f6

    raise ValueError(f"unknown family {c.family}")
