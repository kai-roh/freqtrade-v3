"""Reproducible validation primitives for v3 strategy promotion."""

from typing import Any

__all__ = [
    "Fold",
    "PromotionConfig",
    "PromotionResult",
    "TradeMetrics",
    "WalkForwardConfig",
    "compute_trade_metrics",
    "evaluate_promotion",
    "make_purged_walk_forward_folds",
]


def __getattr__(name: str) -> Any:
    """Load numeric research dependencies only when their exports are requested."""

    if name in {"TradeMetrics", "compute_trade_metrics"}:
        from . import metrics

        return getattr(metrics, name)
    if name in {
        "Fold",
        "PromotionConfig",
        "PromotionResult",
        "WalkForwardConfig",
        "evaluate_promotion",
        "make_purged_walk_forward_folds",
    }:
        from . import validation

        return getattr(validation, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
