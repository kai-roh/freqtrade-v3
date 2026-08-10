"""Deterministic milestone-one research orchestration."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from math import isfinite
from pathlib import Path
from typing import Any

import pandas as pd

from .baselines import backtest_events, no_trade, trend_pullback, volatility_breakout
from .features import build_15m_features
from .metrics import TradeMetrics, compute_trade_metrics
from .risk import RiskConfig
from .validation import (
    PromotionConfig,
    PromotionResult,
    WalkForwardConfig,
    evaluate_promotion,
    make_purged_walk_forward_folds,
)

PAIRS = ("BTC/USDT:USDT", "ETH/USDT:USDT")
SIDES = ("long", "short")
EMPTY_TRADES = pd.DataFrame(columns=["pnl", "pair", "side", "notional", "entry_time", "exit_time"])
TIMEFRAME_STEPS = {"15m": pd.Timedelta(minutes=15), "1h": pd.Timedelta(hours=1)}
MIN_CANDLE_COVERAGE = 0.995
MAX_GAP_MULTIPLIER = 4


@dataclass(frozen=True)
class ResearchConfig:
    fold_count: int = 6
    train_days: int = 90
    validation_days: int = 30
    embargo_hours: int = 6
    min_train_trades: int = 30
    normal_cost_bps: float = 20.0
    stress_cost_bps: float = 30.0


@dataclass(frozen=True)
class Candidate:
    name: str
    signal: Callable[..., pd.DataFrame]
    signal_options: tuple[dict[str, float], ...]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _pair_slug(pair: str) -> str:
    return pair.replace("/", "_").replace(":", "_")


def _data_path(data_dir: Path, pair: str, timeframe: str) -> Path:
    return data_dir / f"{_pair_slug(pair)}-{timeframe}-futures.feather"


def load_market_data(
    data_dir: Path, pair: str, timeframe: str
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Load one Freqtrade futures feather file and validate its chronology."""

    path = _data_path(data_dir, pair, timeframe)
    if not path.is_file():
        raise FileNotFoundError(f"missing research data: {path}")
    frame = pd.read_feather(path)
    required = {"date", "open", "high", "low", "close", "volume"}
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"{path} missing columns: {', '.join(missing)}")
    if timeframe not in TIMEFRAME_STEPS:
        raise ValueError(f"unsupported timeframe: {timeframe}")
    frame = frame.loc[:, ["date", "open", "high", "low", "close", "volume"]].copy()
    frame["date"] = pd.to_datetime(frame["date"], utc=True, errors="coerce")
    if frame["date"].isna().any() or frame["date"].duplicated().any():
        raise ValueError(f"{path} has invalid or duplicate timestamps")
    if not frame["date"].is_monotonic_increasing:
        raise ValueError(f"{path} is not chronologically sorted")
    frame = frame.set_index("date")
    step = TIMEFRAME_STEPS[timeframe]
    if len(frame) < 2:
        raise ValueError(f"{path} has insufficient candles")
    gaps = frame.index.to_series().diff().dropna()
    expected_rows = int((frame.index[-1] - frame.index[0]) / step) + 1
    coverage = len(frame) / expected_rows
    max_gap = gaps.max()
    if coverage < MIN_CANDLE_COVERAGE:
        raise ValueError(f"{path} candle coverage {coverage:.6f} below {MIN_CANDLE_COVERAGE}")
    if max_gap > step * MAX_GAP_MULTIPLIER:
        raise ValueError(f"{path} maximum candle gap {max_gap} exceeds limit")
    metadata = {
        "path": str(path),
        "sha256": _sha256(path),
        "rows": int(len(frame)),
        "start": frame.index[0].isoformat(),
        "end": frame.index[-1].isoformat(),
        "coverage": float(coverage),
        "max_gap_seconds": float(max_gap.total_seconds()),
    }
    return frame, metadata


def _candidate_catalog() -> tuple[Candidate, ...]:
    return (
        Candidate("no_trade", no_trade, ({},)),
        Candidate(
            "trend_pullback",
            trend_pullback,
            tuple({"pullback_threshold": value} for value in (0.25, 0.50, 0.75)),
        ),
        Candidate(
            "volatility_breakout",
            volatility_breakout,
            tuple(
                {"breakout_threshold": threshold, "min_vol_surprise": volume}
                for threshold in (1.0, 1.5, 2.0)
                for volume in (0.0, 0.5)
            ),
        ),
    )


def _risk_catalog() -> tuple[RiskConfig, ...]:
    return (
        RiskConfig(stop_atr=1.5, target_atr=2.25, max_holding_candles=16, round_trip_cost_bps=0),
        RiskConfig(stop_atr=2.0, target_atr=3.0, max_holding_candles=16, round_trip_cost_bps=0),
        RiskConfig(stop_atr=2.0, target_atr=3.0, max_holding_candles=24, round_trip_cost_bps=0),
    )


def _metric_frame(events: pd.DataFrame) -> pd.DataFrame:
    if events.empty:
        return EMPTY_TRADES.copy()
    return pd.DataFrame(
        {
            "pnl": events["gross_return"].astype(float),
            "pair": events["pair"].astype(str),
            "side": events["side"].astype(str),
            "notional": 1.0,
            "entry_time": events["entry_time"],
            "exit_time": events["exit_time"],
        }
    )


def _combine_portfolio_fold(frames: list[pd.DataFrame]) -> pd.DataFrame:
    non_empty = [frame for frame in frames if not frame.empty]
    if not non_empty:
        return EMPTY_TRADES.copy()
    combined = pd.concat(non_empty, ignore_index=True)
    return combined.sort_values(
        ["exit_time", "entry_time", "pair"], kind="mergesort", ignore_index=True
    )


def _signals_for_side(
    candidate: Candidate,
    features: pd.DataFrame,
    side: str,
    options: dict[str, float],
) -> pd.DataFrame:
    return candidate.signal(
        features,
        allow_long=side == "long",
        allow_short=side == "short",
        **options,
    )


def _run_slice(
    market: pd.DataFrame,
    features: pd.DataFrame,
    candidate: Candidate,
    *,
    pair: str,
    side: str,
    options: dict[str, float],
    risk: RiskConfig,
) -> pd.DataFrame:
    signals = _signals_for_side(candidate, features, side, options)
    events = backtest_events(market, features, signals, pair=pair, risk_config=risk)
    return _metric_frame(events)


def _selection_key(
    metrics: TradeMetrics, options: dict[str, float], risk: RiskConfig
) -> tuple[Any, ...]:
    pf = metrics.profit_factor if isfinite(metrics.profit_factor) else 1_000_000.0
    stable_options = tuple((key, float(value)) for key, value in sorted(options.items()))
    stable_risk = (risk.stop_atr, risk.target_atr, risk.max_holding_candles)
    return (metrics.expectancy, pf, metrics.net_pnl, stable_options, stable_risk)


def _select_on_training(
    market: pd.DataFrame,
    features: pd.DataFrame,
    candidate: Candidate,
    *,
    pair: str,
    side: str,
    min_trades: int,
    cost_fraction: float,
) -> tuple[dict[str, float], RiskConfig, TradeMetrics] | None:
    if candidate.name == "no_trade":
        return None

    selected: tuple[dict[str, float], RiskConfig, TradeMetrics] | None = None
    selected_key: tuple[Any, ...] | None = None
    for options in candidate.signal_options:
        for risk in _risk_catalog():
            trades = _run_slice(
                market,
                features,
                candidate,
                pair=pair,
                side=side,
                options=options,
                risk=risk,
            )
            metrics = compute_trade_metrics(trades, cost_stress=cost_fraction)
            if metrics.trade_count < min_trades:
                continue
            key = _selection_key(metrics, options, risk)
            if selected_key is None or key > selected_key:
                selected = (dict(options), risk, metrics)
                selected_key = key
    return selected


def _promotion_to_dict(result: PromotionResult) -> dict[str, Any]:
    return {
        "passed": result.passed,
        "reasons": list(result.reasons),
        "positive_folds": result.positive_folds,
        "max_fold_contribution": result.max_fold_contribution,
        "max_pair_contribution": result.max_pair_contribution,
        "aggregate": _metrics_to_dict(result.aggregate_metrics),
        "folds": [_metrics_to_dict(metric) for metric in result.fold_metrics],
    }


def _evaluate_portfolio(
    fold_trades: list[pd.DataFrame],
    *,
    cost_fraction: float,
    fold_count: int,
) -> PromotionResult:
    return evaluate_promotion(
        fold_trades,
        PromotionConfig(
            required_folds=fold_count,
            min_positive_folds=4,
            max_single_pair_contribution=0.50,
            cost_stress=cost_fraction,
            initial_capital=1.0,
        ),
    )


def _metrics_to_dict(metrics: TradeMetrics) -> dict[str, Any]:
    output = asdict(metrics)
    if not isfinite(float(output["profit_factor"])):
        output["profit_factor"] = "infinity"
    return output


def _report_markdown(result: dict[str, Any]) -> str:
    lines = [
        "# Milestone 1 Research Report",
        "",
        f"- generated_at: `{result['generated_at']}`",
        f"- decision: **{result['decision']}**",
        f"- normal cost: `{result['config']['normal_cost_bps']:.1f} bps`",
        f"- stress cost: `{result['config']['stress_cost_bps']:.1f} bps`",
        "",
        "## Portfolio promotion results",
        "",
        "| Candidate | Side | Trades | PF normal | EV normal | MDD normal | Positive folds | Pair concentration | Stress pass | Decision |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in result["portfolios"]:
        normal = row["normal"]
        aggregate = normal["aggregate"]
        pf = aggregate["profit_factor"]
        pf_text = pf if isinstance(pf, str) else f"{pf:.3f}"
        lines.append(
            f"| {row['candidate']} | {row['side']} | {aggregate['trade_count']} | "
            f"{pf_text} | {aggregate['expectancy']:.6f} | "
            f"{aggregate['max_closed_equity_drawdown']:.3%} | {normal['positive_folds']} | "
            f"{normal['max_pair_contribution']:.3f} | "
            f"{'PASS' if row['stress']['passed'] else 'FAIL'} | "
            f"{'PROMOTE' if row['passed'] else 'REJECT'} |"
        )
    lines.extend(
        [
            "",
            "## Component diagnostics",
            "",
            "| Candidate | Pair | Side | Trades | PF normal | EV normal | MDD normal | Positive folds | Stress pass | Decision |",
            "|---|---|---:|---:|---:|---:|---:|---:|---:|---|",
        ]
    )
    for row in result["components"]:
        normal = row["normal"]
        aggregate = normal["aggregate"]
        pf = aggregate["profit_factor"]
        pf_text = pf if isinstance(pf, str) else f"{pf:.3f}"
        lines.append(
            f"| {row['candidate']} | {row['pair']} | {row['side']} | "
            f"{aggregate['trade_count']} | {pf_text} | {aggregate['expectancy']:.6f} | "
            f"{aggregate['max_closed_equity_drawdown']:.3%} | {normal['positive_folds']} | "
            f"{'PASS' if row['stress']['passed'] else 'FAIL'} | "
            f"{'PROMOTE' if row['passed'] else 'REJECT'} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "Classifier research is allowed only when a same-side BTC/ETH portfolio passes both normal and stress cost gates, including the 50% pair-contribution limit. Component rows are diagnostics only. Parameters are selected independently inside each training fold and are never selected on its validation rows.",
            "",
            "Machine-learning implementation remains blocked unless at least one deterministic portfolio is promoted. Passing this report still does not authorize live trading.",
            "",
        ]
    )
    return "\n".join(lines)


def _atomic_write_artifact(path: Path, content: str) -> None:
    """Replace one artifact through its directory, independent of old file ownership."""

    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(content)
        temporary.chmod(0o660)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def run_milestone_one(
    data_dir: Path,
    output_dir: Path,
    config: ResearchConfig | None = None,
    *,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Run deterministic component validation and write reproducible artifacts."""

    config = config or ResearchConfig()
    if config.fold_count < 6:
        raise ValueError("fold_count must be at least 6")
    if config.train_days <= 0 or config.validation_days <= 0:
        raise ValueError("durations must be positive")
    maximum_holding_candles = max(risk.max_holding_candles for risk in _risk_catalog())
    maximum_trade_horizon = pd.Timedelta(minutes=15 * maximum_holding_candles)
    configured_embargo = pd.Timedelta(hours=config.embargo_hours)
    if configured_embargo < maximum_trade_horizon:
        raise ValueError(f"embargo must cover the {maximum_trade_horizon} maximum trade horizon")
    if config.min_train_trades <= 0:
        raise ValueError("min_train_trades must be positive")
    if not 0 <= config.normal_cost_bps <= config.stress_cost_bps:
        raise ValueError("cost assumptions must be non-negative and stress >= normal")

    markets: dict[str, pd.DataFrame] = {}
    features: dict[str, pd.DataFrame] = {}
    data_manifest: list[dict[str, Any]] = []
    common_index: pd.DatetimeIndex | None = None
    for pair in PAIRS:
        market_15m, meta_15m = load_market_data(data_dir, pair, "15m")
        market_1h, meta_1h = load_market_data(data_dir, pair, "1h")
        markets[pair] = market_15m
        features[pair] = build_15m_features(market_15m, df_1h=market_1h)
        data_manifest.extend((meta_15m, meta_1h))
        common_index = (
            market_15m.index
            if common_index is None
            else common_index.intersection(market_15m.index)
        )

    if common_index is None or common_index.empty:
        raise ValueError("pairs have no common timeline")
    total_span = pd.Timedelta(days=config.train_days + config.fold_count * config.validation_days)
    total_span += pd.Timedelta(hours=config.embargo_hours)
    cutoff = common_index[-1] - total_span
    if common_index[0] > cutoff:
        raise ValueError("insufficient common data span for requested folds")
    timeline = pd.DataFrame(
        {"available": True},
        index=common_index[common_index >= cutoff],
    )
    walk_config = WalkForwardConfig(
        train_duration=f"{config.train_days}d",
        validation_duration=f"{config.validation_days}d",
        fold_count=config.fold_count,
        label_horizon=maximum_trade_horizon,
        embargo=f"{config.embargo_hours}h",
        min_train_rows=int(config.train_days * 24 * 4 * MIN_CANDLE_COVERAGE),
        min_validation_rows=int(config.validation_days * 24 * 4 * MIN_CANDLE_COVERAGE),
    )
    folds = make_purged_walk_forward_folds(timeline, walk_config)

    normal_cost = config.normal_cost_bps / 10_000.0
    stress_cost = config.stress_cost_bps / 10_000.0
    components: list[dict[str, Any]] = []
    portfolio_fold_trades: dict[tuple[str, str], list[list[pd.DataFrame]]] = {
        (candidate.name, side): [[] for _ in folds]
        for candidate in _candidate_catalog()
        for side in SIDES
    }
    for candidate in _candidate_catalog():
        for pair in PAIRS:
            for side in SIDES:
                validation_trades: list[pd.DataFrame] = []
                selections: list[dict[str, Any]] = []
                for fold in folds:
                    train_index = list(fold.train_indices)
                    validation_index = list(fold.validation_indices)
                    train_market = markets[pair].loc[train_index]
                    train_features = features[pair].loc[train_index]
                    selection = _select_on_training(
                        train_market,
                        train_features,
                        candidate,
                        pair=pair,
                        side=side,
                        min_trades=config.min_train_trades,
                        cost_fraction=normal_cost,
                    )
                    if selection is None:
                        empty = EMPTY_TRADES.copy()
                        validation_trades.append(empty)
                        portfolio_fold_trades[(candidate.name, side)][fold.fold_id].append(empty)
                        selections.append(
                            {"fold": fold.fold_id, "status": "no_eligible_training_candidate"}
                        )
                        continue
                    options, risk, train_metrics = selection
                    fold_trades = _run_slice(
                        markets[pair].loc[validation_index],
                        features[pair].loc[validation_index],
                        candidate,
                        pair=pair,
                        side=side,
                        options=options,
                        risk=risk,
                    )
                    validation_trades.append(fold_trades)
                    portfolio_fold_trades[(candidate.name, side)][fold.fold_id].append(fold_trades)
                    selections.append(
                        {
                            "fold": fold.fold_id,
                            "status": "selected",
                            "signal_options": options,
                            "risk": asdict(risk),
                            "training_metrics": _metrics_to_dict(train_metrics),
                        }
                    )

                normal = evaluate_promotion(
                    validation_trades,
                    PromotionConfig(
                        required_folds=config.fold_count,
                        min_positive_folds=min(4, config.fold_count),
                        max_single_pair_contribution=1.0,
                        cost_stress=normal_cost,
                        initial_capital=1.0,
                    ),
                )
                stress = evaluate_promotion(
                    validation_trades,
                    PromotionConfig(
                        required_folds=config.fold_count,
                        min_positive_folds=min(4, config.fold_count),
                        max_single_pair_contribution=1.0,
                        cost_stress=stress_cost,
                        initial_capital=1.0,
                    ),
                )
                components.append(
                    {
                        "candidate": candidate.name,
                        "pair": pair,
                        "side": side,
                        "passed": bool(normal.passed and stress.passed),
                        "normal": _promotion_to_dict(normal),
                        "stress": _promotion_to_dict(stress),
                        "selections": selections,
                    }
                )

    portfolios: list[dict[str, Any]] = []
    for candidate in _candidate_catalog():
        for side in SIDES:
            fold_trades = []
            for frames in portfolio_fold_trades[(candidate.name, side)]:
                fold_trades.append(_combine_portfolio_fold(frames))
            normal = _evaluate_portfolio(
                fold_trades,
                cost_fraction=normal_cost,
                fold_count=config.fold_count,
            )
            stress = _evaluate_portfolio(
                fold_trades,
                cost_fraction=stress_cost,
                fold_count=config.fold_count,
            )
            portfolios.append(
                {
                    "candidate": candidate.name,
                    "side": side,
                    "passed": bool(normal.passed and stress.passed),
                    "normal": _promotion_to_dict(normal),
                    "stress": _promotion_to_dict(stress),
                }
            )

    promoted = [row for row in portfolios if row["passed"]]
    result: dict[str, Any] = {
        "schema_version": 1,
        "generated_at": generated_at
        or datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "decision": "ALLOW_CLASSIFIER_RESEARCH" if promoted else "STOP_BEFORE_CLASSIFIER",
        "config": asdict(config),
        "data": data_manifest,
        "folds": [
            {
                "fold": fold.fold_id,
                "train_start": fold.train_start.isoformat(),
                "train_end": fold.train_end.isoformat(),
                "validation_start": fold.validation_start.isoformat(),
                "validation_end": fold.validation_end.isoformat(),
            }
            for fold in folds
        ],
        "components": components,
        "portfolios": portfolios,
        "promoted_portfolios": [
            {"candidate": row["candidate"], "side": row["side"]} for row in promoted
        ],
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    _atomic_write_artifact(
        output_dir / "results.json",
        json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
    )
    _atomic_write_artifact(output_dir / "REPORT.md", _report_markdown(result))
    return result
