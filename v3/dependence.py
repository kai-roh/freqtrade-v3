"""Auditable serial-dependence diagnostics for ordered portfolio returns."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class LagDiagnostic:
    lag: int
    autocorrelation: float
    ljung_box_q: float
    p_value: float

    def to_dict(self) -> dict[str, int | float]:
        return {
            "lag": self.lag,
            "autocorrelation": self.autocorrelation,
            "ljung_box_q": self.ljung_box_q,
            "p_value": self.p_value,
        }


@dataclass(frozen=True)
class ReturnDependenceDiagnostics:
    observation_count: int
    maximum_lag: int
    lags: tuple[LagDiagnostic, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "method": {
                "autocorrelation": "demeaned_biased_acf",
                "portmanteau": "ljung_box",
                "null_hypothesis": "no_autocorrelation_through_reported_lag",
            },
            "observation_count": self.observation_count,
            "maximum_lag": self.maximum_lag,
            "lags": [row.to_dict() for row in self.lags],
        }


def return_dependence_diagnostics(
    returns: pd.Series, *, maximum_lag: int = 10
) -> ReturnDependenceDiagnostics:
    if not isinstance(returns, pd.Series):
        raise TypeError("returns must be a pandas Series")
    if returns.empty:
        raise ValueError("returns must not be empty")
    if maximum_lag <= 0 or maximum_lag >= len(returns):
        raise ValueError("maximum_lag must be between 1 and observation_count - 1")
    numeric = pd.to_numeric(returns, errors="coerce")
    values = numeric.to_numpy(dtype=float)
    if numeric.isna().any() or not np.isfinite(values).all():
        raise ValueError("returns must contain only finite numeric values")

    centered = values - np.mean(values)
    denominator = float(np.dot(centered, centered))
    if denominator == 0:
        raise ValueError("returns must have non-zero variance")

    count = len(values)
    autocorrelations: list[float] = []
    diagnostics: list[LagDiagnostic] = []
    for lag in range(1, maximum_lag + 1):
        autocorrelation = float(np.dot(centered[lag:], centered[:-lag]) / denominator)
        autocorrelations.append(autocorrelation)
        q_statistic = (
            count
            * (count + 2)
            * sum(
                value**2 / (count - index) for index, value in enumerate(autocorrelations, start=1)
            )
        )
        diagnostics.append(
            LagDiagnostic(
                lag=lag,
                autocorrelation=autocorrelation,
                ljung_box_q=q_statistic,
                p_value=_chi_square_survival(q_statistic, lag),
            )
        )
    return ReturnDependenceDiagnostics(count, maximum_lag, tuple(diagnostics))


def _chi_square_survival(statistic: float, degrees_of_freedom: int) -> float:
    if statistic < 0 or degrees_of_freedom <= 0:
        raise ValueError("invalid chi-square arguments")
    return _regularized_gamma_q(degrees_of_freedom / 2, statistic / 2)


def _regularized_gamma_q(shape: float, value: float) -> float:
    """Regularized upper incomplete gamma using stable series/continued fractions."""

    if shape <= 0 or value < 0:
        raise ValueError("invalid incomplete-gamma arguments")
    if value == 0:
        return 1.0
    epsilon = 3e-14
    floor = 1e-300
    maximum_iterations = 1000

    if value < shape + 1:
        term = 1 / shape
        series = term
        shifted_shape = shape
        for _ in range(maximum_iterations):
            shifted_shape += 1
            term *= value / shifted_shape
            series += term
            if abs(term) <= abs(series) * epsilon:
                lower = series * math.exp(-value + shape * math.log(value) - math.lgamma(shape))
                return min(1.0, max(0.0, 1 - lower))
        raise RuntimeError("incomplete-gamma series did not converge")

    b_value = value + 1 - shape
    c_value = 1 / floor
    d_value = 1 / b_value
    fraction = d_value
    for iteration in range(1, maximum_iterations + 1):
        coefficient = -iteration * (iteration - shape)
        b_value += 2
        d_value = coefficient * d_value + b_value
        if abs(d_value) < floor:
            d_value = floor
        c_value = b_value + coefficient / c_value
        if abs(c_value) < floor:
            c_value = floor
        d_value = 1 / d_value
        delta = d_value * c_value
        fraction *= delta
        if abs(delta - 1) <= epsilon:
            result = math.exp(-value + shape * math.log(value) - math.lgamma(shape)) * fraction
            return min(1.0, max(0.0, result))
    raise RuntimeError("incomplete-gamma continued fraction did not converge")
