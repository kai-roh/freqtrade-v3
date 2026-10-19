"""Phase 2d selection statistics and gates (PHASE2D_PREREGISTRATION.md §6)."""

from __future__ import annotations

from itertools import combinations
from math import comb
from statistics import NormalDist

import numpy as np
import pandas as pd

EULER_GAMMA = 0.5772156649015329
NORMAL = NormalDist()
TRIALS = 120
PBO_BLOCKS = 16


def pbo_cscv(returns: pd.DataFrame, blocks: int = PBO_BLOCKS) -> float:
    """Probability of backtest overfitting by combinatorially symmetric cross-validation.

    ``returns``: daily returns, one column per configuration. The window is split into
    ``blocks`` contiguous blocks; for every half/half split the in-sample Sharpe winner's
    out-of-sample relative rank is recorded. PBO is the share of splits where that rank
    is at or below the median (logit <= 0).
    """
    values = returns.fillna(0.0).to_numpy(float)
    n_configs = values.shape[1]
    if n_configs < 2:
        return float("nan")
    edges = np.linspace(0, len(values), blocks + 1).astype(int)
    parts = [values[a:b] for a, b in zip(edges[:-1], edges[1:], strict=True)]
    sums = np.array([p.sum(axis=0) for p in parts])
    sq = np.array([(p**2).sum(axis=0) for p in parts])
    counts = np.array([len(p) for p in parts], dtype=float)
    below = 0
    total = 0
    for chosen in combinations(range(blocks), blocks // 2):
        mask = np.zeros(blocks, dtype=bool)
        mask[list(chosen)] = True
        sharpe = []
        for m in (mask, ~mask):
            n = counts[m].sum()
            mean = sums[m].sum(axis=0) / n
            var = sq[m].sum(axis=0) / n - mean**2
            sharpe.append(mean / np.sqrt(np.where(var > 0, var, np.nan)))
        is_sr, oos_sr = sharpe
        best = int(np.nanargmax(is_sr))
        oos = oos_sr[~np.isnan(oos_sr)]
        rank = (oos < oos_sr[best]).sum() + 0.5 * ((oos == oos_sr[best]).sum() - 1)
        relative = (rank + 1) / (len(oos) + 1)
        below += relative <= 0.5
        total += 1
    assert total == comb(blocks, blocks // 2)
    return below / total


def deflated_sharpe(returns: pd.Series, trial_sharpes: np.ndarray, trials: int = TRIALS) -> float:
    """Bailey & Lopez de Prado DSR with per-period (daily) Sharpe ratios."""
    r = returns.fillna(0.0).to_numpy(float)
    t = len(r)
    sd = r.std(ddof=1)
    if sd == 0 or t < 3:
        return 0.0
    sr = r.mean() / sd
    skew = float(((r - r.mean()) ** 3).mean() / sd**3)
    kurt = float(((r - r.mean()) ** 4).mean() / sd**4)
    v = float(np.var(trial_sharpes, ddof=1))
    sr0 = np.sqrt(v) * (
        (1 - EULER_GAMMA) * NORMAL.inv_cdf(1 - 1 / trials)
        + EULER_GAMMA * NORMAL.inv_cdf(1 - 1 / (trials * np.e))
    )
    denom = np.sqrt(max(1e-12, 1 - skew * sr + (kurt - 1) / 4 * sr**2))
    return float(NORMAL.cdf((sr - sr0) * np.sqrt(t - 1) / denom))


def daily_sharpe(returns: pd.Series) -> float:
    r = returns.fillna(0.0)
    sd = r.std()
    return float(r.mean() / sd) if sd > 0 else 0.0
