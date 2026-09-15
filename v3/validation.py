"""Purged walk-forward validation and promotion gates."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from math import isfinite

import pandas as pd

from .metrics import TradeMetrics, compute_trade_metrics


@dataclass(frozen=True)
class WalkForwardConfig:
    train_duration: pd.Timedelta | str
    validation_duration: pd.Timedelta | str
    fold_count: int
    label_horizon: pd.Timedelta | str
    embargo: pd.Timedelta | str | None = None
    min_train_rows: int = 1
    min_validation_rows: int = 1


@dataclass(frozen=True)
class Fold:
    fold_id: int
    train_start: pd.Timestamp
    train_end: pd.Timestamp
    validation_start: pd.Timestamp
    validation_end: pd.Timestamp
    train_indices: tuple[object, ...]
    validation_indices: tuple[object, ...]


@dataclass(frozen=True)
class PromotionConfig:
    profit_factor_min: float = 1.15
    max_drawdown_max: float = 0.10
    min_positive_folds: int = 4
    required_folds: int = 6
    max_single_fold_contribution: float = 0.50
    max_single_pair_contribution: float = 0.50
    cost_stress: float = 0.0
    initial_capital: float = 1.0


DEFAULT_PROMOTION_CONFIG = PromotionConfig()


@dataclass(frozen=True)
class PromotionResult:
    passed: bool
    reasons: tuple[str, ...]
    aggregate_metrics: TradeMetrics
    fold_metrics: tuple[TradeMetrics, ...]
    positive_folds: int
    max_fold_contribution: float
    max_pair_contribution: float


def _duration(value: pd.Timedelta | str, name: str) -> pd.Timedelta:
    duration = pd.Timedelta(value)
    if duration <= pd.Timedelta(0):
        raise ValueError(f"{name} must be positive")
    return duration


def _timeline(data: pd.DataFrame, time_col: str | None) -> pd.Series:
    if not isinstance(data, pd.DataFrame):
        raise TypeError("data must be a pandas DataFrame")
    if data.empty:
        raise ValueError("data must not be empty")
    if time_col is None:
        if not isinstance(data.index, pd.DatetimeIndex):
            raise ValueError("data must have a DatetimeIndex or a time_col")
        times = pd.Series(data.index, index=data.index)
    else:
        if time_col not in data.columns:
            raise ValueError(f"data missing time column: {time_col}")
        times = pd.to_datetime(data[time_col], errors="coerce")
        times = pd.Series(times, index=data.index)
    if times.isna().any():
        raise ValueError("timestamps must be valid")
    if not times.is_monotonic_increasing:
        raise ValueError("data must be sorted chronologically")
    if times.duplicated().any():
        raise ValueError("timestamps must be unique")
    return times


def _assert_row_embargo(times, train_mask, validation_mask, minimum_gap, fold_id: int) -> None:
    """Check the embargo on the selected rows themselves, independent of boundary math."""
    last_train = pd.Timestamp(times[train_mask].iloc[-1])
    first_validation = pd.Timestamp(times[validation_mask].iloc[0])
    if first_validation - last_train < pd.Timedelta(minimum_gap):
        raise ValueError(f"fold {fold_id} violates embargo")


def make_purged_walk_forward_folds(
    data: pd.DataFrame,
    config: WalkForwardConfig,
    *,
    time_col: str | None = None,
) -> tuple[Fold, ...]:
    """Create chronological folds with a purge/embargo gap before validation."""

    train_duration = _duration(config.train_duration, "train_duration")
    validation_duration = _duration(config.validation_duration, "validation_duration")
    label_horizon = _duration(config.label_horizon, "label_horizon")
    configured_embargo = pd.Timedelta(0) if config.embargo is None else pd.Timedelta(config.embargo)
    if configured_embargo < pd.Timedelta(0):
        raise ValueError("embargo must be non-negative")
    embargo = max(configured_embargo, label_horizon)
    if config.fold_count <= 0:
        raise ValueError("fold_count must be positive")
    if config.min_train_rows <= 0 or config.min_validation_rows <= 0:
        raise ValueError("minimum row counts must be positive")

    times = _timeline(data, time_col)
    first = pd.Timestamp(times.iloc[0])
    last = pd.Timestamp(times.iloc[-1])
    folds: list[Fold] = []

    for fold_id in range(config.fold_count):
        train_start = first + (fold_id * validation_duration)
        train_end = train_start + train_duration
        validation_start = train_end + embargo
        validation_end = validation_start + validation_duration
        if validation_end > last + pd.Timedelta(1, "ns"):
            raise ValueError("insufficient data for requested fold_count and durations")

        train_mask = (times >= train_start) & (times < train_end)
        validation_mask = (times >= validation_start) & (times < validation_end)
        train_indices = tuple(data.index[train_mask])
        validation_indices = tuple(data.index[validation_mask])
        if len(train_indices) < config.min_train_rows:
            raise ValueError(f"fold {fold_id} has insufficient train rows")
        if len(validation_indices) < config.min_validation_rows:
            raise ValueError(f"fold {fold_id} has insufficient validation rows")
        if set(train_indices).intersection(validation_indices):
            raise ValueError(f"fold {fold_id} train/validation indices overlap")
        _assert_row_embargo(times, train_mask, validation_mask, embargo, fold_id)

        folds.append(
            Fold(
                fold_id=fold_id,
                train_start=train_start,
                train_end=train_end,
                validation_start=validation_start,
                validation_end=validation_end,
                train_indices=train_indices,
                validation_indices=validation_indices,
            )
        )

    return tuple(folds)


def _as_sequence(
    fold_trades: Sequence[pd.DataFrame] | Mapping[object, pd.DataFrame],
) -> tuple[pd.DataFrame, ...]:
    if isinstance(fold_trades, Mapping):
        return tuple(fold_trades[key] for key in sorted(fold_trades))
    return tuple(fold_trades)


def _max_positive_contribution(values: Iterable[float]) -> float:
    positives = [float(value) for value in values if float(value) > 0.0]
    total_positive = sum(positives)
    if total_positive <= 0.0:
        return 1.0
    return max(positives) / total_positive


def evaluate_promotion(
    fold_trades: Sequence[pd.DataFrame] | Mapping[object, pd.DataFrame],
    config: PromotionConfig = DEFAULT_PROMOTION_CONFIG,
) -> PromotionResult:
    """Evaluate promotion gates across validation fold trade results."""

    folds = _as_sequence(fold_trades)
    if len(folds) != config.required_folds:
        empty = compute_trade_metrics(
            pd.DataFrame(columns=["pnl", "pair", "side", "notional"]),
            cost_stress=config.cost_stress,
            initial_capital=config.initial_capital,
        )
        return PromotionResult(
            passed=False,
            reasons=(f"expected {config.required_folds} folds, got {len(folds)}",),
            aggregate_metrics=empty,
            fold_metrics=(),
            positive_folds=0,
            max_fold_contribution=1.0,
            max_pair_contribution=1.0,
        )

    fold_metrics = tuple(
        compute_trade_metrics(
            frame,
            cost_stress=config.cost_stress,
            initial_capital=config.initial_capital,
        )
        for frame in folds
    )
    aggregate = compute_trade_metrics(
        pd.concat(folds, ignore_index=True),
        cost_stress=config.cost_stress,
        initial_capital=config.initial_capital,
    )
    positive_folds = sum(metric.net_pnl > 0.0 for metric in fold_metrics)
    max_fold_contribution = _max_positive_contribution(metric.net_pnl for metric in fold_metrics)
    max_pair_contribution = _max_positive_contribution(aggregate.pair_contributions.values())

    reasons: list[str] = []
    if aggregate.trade_count == 0:
        reasons.append("no trades")
    if aggregate.profit_factor < config.profit_factor_min:
        reasons.append(
            f"profit factor {aggregate.profit_factor:.6g} below {config.profit_factor_min:.6g}"
        )
    if not isfinite(aggregate.expectancy) or aggregate.expectancy <= 0.0:
        reasons.append("expectancy is not positive")
    if aggregate.max_closed_equity_drawdown > config.max_drawdown_max:
        reasons.append(
            "max closed-equity drawdown "
            f"{aggregate.max_closed_equity_drawdown:.6g} exceeds {config.max_drawdown_max:.6g}"
        )
    if positive_folds < config.min_positive_folds:
        reasons.append(f"positive folds {positive_folds} below {config.min_positive_folds}")
    if max_fold_contribution > config.max_single_fold_contribution:
        reasons.append(
            "single fold contribution "
            f"{max_fold_contribution:.6g} exceeds {config.max_single_fold_contribution:.6g}"
        )
    if max_pair_contribution > config.max_single_pair_contribution:
        reasons.append(
            "single pair contribution "
            f"{max_pair_contribution:.6g} exceeds {config.max_single_pair_contribution:.6g}"
        )

    return PromotionResult(
        passed=not reasons,
        reasons=tuple(reasons),
        aggregate_metrics=aggregate,
        fold_metrics=fold_metrics,
        positive_folds=int(positive_folds),
        max_fold_contribution=float(max_fold_contribution),
        max_pair_contribution=float(max_pair_contribution),
    )
