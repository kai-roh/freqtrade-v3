"""Combinatorially symmetric cross-validation (CSCV) probability of backtest overfitting.

Input: a T x N matrix of daily net returns for the N grid points of one
hypothesis. Rows are split into S contiguous blocks; every choice of S/2 blocks
forms an in-sample set and the rest the out-of-sample set. For each split the
in-sample best strategy's out-of-sample relative rank is recorded; PBO is the
share of splits where that rank is at or below the median. It is a diagnostic
of selection overfitting, not a forecast of future profit.
"""

from __future__ import annotations

from itertools import combinations
from math import comb

import numpy as np
import pandas as pd


def sharpe(returns: np.ndarray) -> np.ndarray:
    """Annualised daily Sharpe per column; zero variance yields 0."""
    mean = returns.mean(axis=0)
    std = returns.std(axis=0, ddof=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = np.where(std > 0, mean / std, 0.0)
    return ratio * np.sqrt(365.0)


def probability_of_backtest_overfitting(
    matrix: pd.DataFrame, *, partitions: int = 16
) -> dict[str, float | int]:
    if partitions < 2 or partitions % 2:
        raise ValueError("partitions must be an even integer >= 2")
    values = matrix.to_numpy(dtype=float)
    rows, count = values.shape
    if count < 2:
        raise ValueError("at least two strategies are required")
    if rows < partitions * 2:
        raise ValueError("too few rows for the requested partitions")
    if not np.isfinite(values).all():
        raise ValueError("returns must be finite")
    blocks = np.array_split(np.arange(rows), partitions)
    half = partitions // 2
    logits = []
    for chosen in combinations(range(partitions), half):
        in_rows = np.concatenate([blocks[i] for i in chosen])
        out_rows = np.concatenate([blocks[i] for i in range(partitions) if i not in chosen])
        best = int(np.argmax(sharpe(values[in_rows])))
        oos = sharpe(values[out_rows])
        rank = (oos < oos[best]).sum() + 0.5 * ((oos == oos[best]).sum() - 1) + 1
        omega = rank / (count + 1)
        logits.append(float(np.log(omega / (1 - omega))))
    logits_array = np.asarray(logits)
    return {
        "pbo": float((logits_array <= 0).mean()),
        "splits": int(comb(partitions, half)),
        "strategies": int(count),
        "rows": int(rows),
        "median_logit": float(np.median(logits_array)),
    }
