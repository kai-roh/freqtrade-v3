"""Reproducible validation primitives for v3 strategy promotion."""

from .metrics import TradeMetrics, compute_trade_metrics
from .validation import (
    Fold,
    PromotionConfig,
    PromotionResult,
    WalkForwardConfig,
    evaluate_promotion,
    make_purged_walk_forward_folds,
)

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
