"""Phase 1E latency summaries with explicit Demo interpretation boundaries."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass(frozen=True)
class LatencySummary:
    sample_count: int
    median_ms: float
    p99_ms: float

    def to_dict(self) -> dict[str, int | float]:
        return {
            "sample_count": self.sample_count,
            "median_ms": self.median_ms,
            "p99_ms": self.p99_ms,
        }


@dataclass(frozen=True)
class Phase1SlaEvidence:
    quote_age: LatencySummary
    hedge_latency_demo_lower_bound: LatencySummary
    maximum_quote_age_ms: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "quote_age": self.quote_age.to_dict(),
            "hedge_latency_demo_lower_bound": self.hedge_latency_demo_lower_bound.to_dict(),
            "maximum_quote_age_ms": self.maximum_quote_age_ms,
            "interpretation": (
                "Demo hedge latency is a lower-bound infrastructure measurement and must be "
                "remeasured with Phase 3 small-capital live fills"
            ),
        }


def summarize_phase1_sla(
    quote_age_samples_ms: list[int],
    hedge_latency_samples_ms: list[int],
) -> Phase1SlaEvidence:
    quote = _summary(quote_age_samples_ms, "quote age")
    hedge = _summary(hedge_latency_samples_ms, "hedge latency")
    return Phase1SlaEvidence(
        quote_age=quote,
        hedge_latency_demo_lower_bound=hedge,
        maximum_quote_age_ms=math.ceil(quote.p99_ms * 2),
    )


def summarize_latency(values: list[int], name: str) -> LatencySummary:
    """Public single-series summary with the same 50-sample floor as the SLA evidence."""
    return _summary(values, name)


def _summary(values: list[int], name: str) -> LatencySummary:
    if len(values) < 50:
        raise ValueError(f"{name} requires at least 50 samples")
    array = np.asarray(values, dtype=float)
    if not np.isfinite(array).all() or (array < 0).any():
        raise ValueError(f"{name} samples must be finite and non-negative")
    return LatencySummary(
        sample_count=len(values),
        median_ms=float(np.percentile(array, 50)),
        p99_ms=float(np.percentile(array, 99)),
    )
