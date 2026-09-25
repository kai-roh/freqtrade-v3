"""Block bootstrap validation helpers for dependent strategy returns."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class BootstrapSpec:
    sample_unit: str
    block_length: int
    iterations: int
    seed: int
    alpha: float = 0.05
    direction: str = "two-sided"
    block_definition: str = "moving_contiguous_periods"

    def __post_init__(self) -> None:
        if self.sample_unit == "individual_trade":
            raise ValueError("individual_trade resampling is not allowed for dependent trades")
        if self.sample_unit not in {"daily_portfolio_pnl", "exposure_cluster"}:
            raise ValueError("sample_unit must be daily_portfolio_pnl or exposure_cluster")
        if self.block_length <= 0:
            raise ValueError("block_length must be positive")
        if self.iterations <= 0:
            raise ValueError("iterations must be positive")
        if self.alpha <= 0 or self.alpha >= 1:
            raise ValueError("alpha must be between 0 and 1")
        if self.direction != "two-sided":
            raise ValueError("direction must be two-sided")
        if self.block_definition != "moving_contiguous_periods":
            raise ValueError("block_definition must be moving_contiguous_periods")

    def to_dict(self) -> dict[str, Any]:
        return {
            "sample_unit": self.sample_unit,
            "block_definition": self.block_definition,
            "block_length": self.block_length,
            "iterations": self.iterations,
            "seed": self.seed,
            "alpha": self.alpha,
            "direction": self.direction,
        }


@dataclass(frozen=True)
class BootstrapResult:
    observed_mean: float
    ci_low: float
    ci_high: float
    iterations: int
    seed: int
    block_length: int
    sample_unit: str
    alpha: float
    direction: str
    block_definition: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "observed_mean": self.observed_mean,
            "ci_low": self.ci_low,
            "ci_high": self.ci_high,
            "iterations": self.iterations,
            "seed": self.seed,
            "block_length": self.block_length,
            "sample_unit": self.sample_unit,
            "alpha": self.alpha,
            "direction": self.direction,
            "block_definition": self.block_definition,
        }


def _clean_returns(returns: pd.Series) -> np.ndarray:
    if not isinstance(returns, pd.Series):
        raise TypeError("returns must be a pandas Series")
    if returns.empty:
        raise ValueError("returns must not be empty")
    if returns.index.has_duplicates or not returns.index.is_monotonic_increasing:
        raise ValueError("returns index must be unique and chronologically ordered")
    values = pd.to_numeric(returns, errors="coerce")
    if values.isna().any() or np.isinf(values.to_numpy(dtype=float)).any():
        raise ValueError("returns must contain only finite numeric values")
    return values.to_numpy(dtype=float)


def block_bootstrap_mean(returns: pd.Series, spec: BootstrapSpec) -> BootstrapResult:
    """Estimate a two-sided CI for mean returns using contiguous block resampling."""

    values = _clean_returns(returns)
    if len(values) < spec.block_length:
        raise ValueError("returns must contain at least block_length observations")

    rng = np.random.default_rng(spec.seed)
    starts = np.arange(0, len(values) - spec.block_length + 1)
    means: list[float] = []
    for _ in range(spec.iterations):
        sampled: list[float] = []
        while len(sampled) < len(values):
            start = int(rng.choice(starts))
            sampled.extend(values[start : start + spec.block_length].tolist())
        means.append(float(np.mean(sampled[: len(values)])))

    low, high = np.quantile(means, [spec.alpha / 2, 1 - spec.alpha / 2])
    return BootstrapResult(
        observed_mean=float(np.mean(values)),
        ci_low=float(low),
        ci_high=float(high),
        iterations=spec.iterations,
        seed=spec.seed,
        block_length=spec.block_length,
        sample_unit=spec.sample_unit,
        alpha=spec.alpha,
        direction=spec.direction,
        block_definition=spec.block_definition,
    )
