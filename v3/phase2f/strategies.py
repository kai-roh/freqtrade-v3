"""Phase 2f strategy families and the registered grid (PHASE2F_PREREGISTRATION.md §5).

All run on USD-M perpetuals with the Phase 2d engine (gross exposure at most 1).

- R1: regime long/short on BTC and ETH, asymmetric sizing in up and down regimes.
- R2: regime-conditional cross-section: long strength in up regimes, short the
  weakest alts in down regimes.
- P1..P4: market-neutral cross-sections on positioning and flow data.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from itertools import product

import numpy as np
import pandas as pd

from v3.phase2d.engine import Market, WeightFn
from v3.phase2d.strategies import _top

BTC = "BTCUSDT"
ETH = "ETHUSDT"
UNIVERSE = 20  # top-N liquid perpetuals for R2 and P families
TRIALS_BEFORE = 121  # Phase 2d (120) + Phase 2e (1), counted in the deflated Sharpe


@dataclass(frozen=True)
class Config:
    family: str  # R1, R2, P1..P4
    sma: int = 0  # regime SMA length (R1, R2)
    up: float = 0.0  # R1 weight per regime (fraction of gross 1) when up
    down: float = 0.0  # R1 short weight when down (positive number)
    source: str = ""  # R1: "own" (each asset's own SMA) or "btc" (BTC regime for both)
    lookback: int = 0  # momentum (R2) or signal smoothing (P) days
    k: int = 0  # names per side
    up_mode: str = ""  # R2: "topk" (long top-K momentum) or "btc" (long BTC)

    @property
    def every(self) -> int:
        return 1 if self.family == "R1" else 7

    def label(self) -> str:
        parts = [self.family]
        if self.sma:
            parts.append(f"S{self.sma}")
        if self.family == "R1":
            parts += [f"U{self.up:g}", f"D{self.down:g}", self.source]
        if self.lookback:
            parts.append(f"L{self.lookback}")
        if self.k:
            parts.append(f"K{self.k}")
        if self.up_mode:
            parts.append(self.up_mode)
        return "-".join(parts)

    def to_json(self) -> dict:
        return {**asdict(self), "label": self.label()}


R1_SIZING = ((1.0, 1.0), (0.5, 1.0), (1.0, 0.5))


def registered_grid() -> list[Config]:
    grid: list[Config] = []
    for sma, (up, down), source in product((50, 100, 200), R1_SIZING, ("own", "btc")):
        grid.append(Config("R1", sma=sma, up=up, down=down, source=source))
    for sma, lb, k, mode in product((100, 200), (14, 30, 60), (3, 5), ("topk", "btc")):
        grid.append(Config("R2", sma=sma, lookback=lb, k=k, up_mode=mode))
    for fam, lb, k in product(("P1", "P2", "P3", "P4"), (3, 7, 14), (3, 5)):
        grid.append(Config(fam, lookback=lb, k=k))
    return grid


@dataclass
class Signals:
    """Daily positioning panels aligned to the market (days x symbols)."""

    top_ls: pd.DataFrame
    acct_ls: pd.DataFrame
    oi_value: pd.DataFrame
    taker_share: pd.DataFrame


def _score(config: Config, market: Market, signals: Signals) -> np.ndarray:
    """Higher score = long. Each uses only data through the decision day's close."""
    lb = config.lookback
    if config.family == "P1":  # crowded top traders -> fade
        return -signals.top_ls.rolling(lb, min_periods=lb).mean().to_numpy(float)
    if config.family == "P2":  # crowded accounts -> fade
        return -signals.acct_ls.rolling(lb, min_periods=lb).mean().to_numpy(float)
    if config.family == "P3":  # persistent taker buying -> follow
        return signals.taker_share.rolling(lb, min_periods=lb).mean().to_numpy(float)
    if config.family == "P4":  # open interest built faster than price -> fade
        close = market.panel.close
        oi = signals.oi_value.where(signals.oi_value > 0)
        oi_chg = (oi / oi.shift(lb) - 1.0).to_numpy(float)
        ret = (close / close.shift(lb) - 1.0).to_numpy(float)
        return -(oi_chg - ret)
    raise ValueError(config.family)


def weight_fn(config: Config, market: Market, signals: Signals | None = None) -> WeightFn:
    c = config
    btc = market.symbols.index(BTC)
    eth = market.symbols.index(ETH)

    if c.family == "R1":
        smas = market.sma(c.sma)

        def regime(i: int, j: int) -> int:
            src = btc if c.source == "btc" else j
            close, avg = market.close[i, src], smas[i, src]
            if np.isnan(close) or np.isnan(avg):
                return 0
            return 1 if close > avg else -1

        def r1(m: Market, i: int) -> dict[int, float]:
            out = {}
            for j in (btc, eth):
                s = regime(i, j)
                if s and not np.isnan(m.close[i, j]):
                    out[j] = 0.5 * (c.up if s > 0 else -c.down)
            return out

        return r1

    if c.family == "R2":
        mom = market.momentum(c.lookback)
        btc_sma = market.sma(c.sma)

        def r2(m: Market, i: int) -> dict[int, float]:
            if np.isnan(btc_sma[i, btc]):
                return {}
            cols = m.universe(i, UNIVERSE)
            if m.close[i, btc] > btc_sma[i, btc]:
                if c.up_mode == "btc":
                    return {btc: 1.0}
                chosen = _top(mom[i], cols, c.k)
                return {int(j): 1.0 / c.k for j in chosen}
            chosen = _top(mom[i], cols, c.k, largest=False)
            return {int(j): -1.0 / c.k for j in chosen}

        return r2

    if c.family in {"P1", "P2", "P3", "P4"}:
        if signals is None:
            raise ValueError("positioning families need signals")
        score = _score(c, market, signals)

        def p(m: Market, i: int) -> dict[int, float]:
            cols = m.universe(i, UNIVERSE)
            ok = cols[np.isfinite(score[i, cols])]
            if ok.size < 2 * c.k:
                return {}
            longs = _top(score[i], ok, c.k)
            shorts = _top(score[i], ok, c.k, largest=False)
            out = {int(j): 0.5 / c.k for j in longs}
            out.update({int(j): -0.5 / c.k for j in shorts})
            return out

        return p

    raise ValueError(f"unknown family {c.family}")


T1_MEMBERS = tuple(Config("P3", lookback=lb, k=k) for lb in (3, 7, 14) for k in (3, 5))


def ensemble_fn(members: tuple[Config, ...], market: Market, signals: Signals) -> WeightFn:
    """Phase 2g T1: the simple average of the members' target weights."""
    fns = [weight_fn(c, market, signals) for c in members]

    def combined(m: Market, i: int) -> dict[int, float]:
        total: dict[int, float] = {}
        for fn in fns:
            for j, w in fn(m, i).items():
                total[j] = total.get(j, 0.0) + w / len(fns)
        return total

    return combined
