"""Phase 2 walk-forward orchestration with the registered gates and PBO diagnostic."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from v3.validation import WalkForwardConfig, make_purged_walk_forward_folds

from .basket import (
    NORMAL_COST,
    STRESS_COST,
    CostModel,
    Rule,
    SimulationResult,
    h1_grid,
    h2_grid,
    simulate_basket,
)
from .data import Phase2Panel, load_phase2_panel
from .pbo import probability_of_backtest_overfitting, sharpe

WARMUP_DAYS = 14
EXIT_EXTENSION_DAYS = 14


@dataclass(frozen=True)
class Phase2Config:
    fold_count: int = 6
    train_days: int = 180
    validation_days: int = 30
    embargo_days: int = 14
    pbo_partitions: int = 16
    profit_factor_min: float = 1.15
    max_drawdown_max: float = 0.10
    min_positive_folds: int = 4
    max_contribution: float = 0.50
    pbo_max: float = 0.20


@dataclass(frozen=True)
class SeriesMetrics:
    days: int
    total_return: float
    expectancy: float
    profit_factor: float
    max_drawdown: float
    sharpe: float

    @classmethod
    def from_returns(cls, returns: pd.Series) -> SeriesMetrics:
        if returns.empty:
            return cls(0, 0.0, 0.0, 0.0, 0.0, 0.0)
        values = returns.to_numpy(dtype=float)
        gains = values[values > 0].sum()
        losses = -values[values < 0].sum()
        if gains == 0 and losses == 0:
            pf = 0.0
        elif losses == 0:
            pf = float("inf")
        else:
            pf = float(gains / losses)
        equity = np.cumprod(1 + values)
        peak = np.maximum.accumulate(np.concatenate(([1.0], equity)))[1:]
        drawdown = float(((peak - equity) / peak).max())
        return cls(
            days=int(len(values)),
            total_return=float(equity[-1] - 1),
            expectancy=float(values.mean()),
            profit_factor=pf,
            max_drawdown=drawdown,
            sharpe=float(sharpe(values.reshape(-1, 1))[0]),
        )

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        if not np.isfinite(data["profit_factor"]):
            data["profit_factor"] = "infinity"
        return data


def _daily_timeline(panel: Phase2Panel) -> pd.DataFrame:
    days = panel.open.index.normalize().unique()
    first = days[0] + pd.Timedelta(days=WARMUP_DAYS)
    last = days[-1] - pd.Timedelta(days=EXIT_EXTENSION_DAYS)
    days = days[(days >= first) & (days <= last)]
    return pd.DataFrame({"available": True}, index=days)


def _select(results: list[SimulationResult]) -> SimulationResult:
    def key(result: SimulationResult) -> tuple[float, float]:
        metrics = SeriesMetrics.from_returns(result.daily_returns)
        return (metrics.sharpe, -result.traded_notional)

    return max(results, key=key)


def _contribution(values: dict[str, float]) -> float:
    positives = [v for v in values.values() if v > 0]
    if not positives:
        return 1.0 if values else 0.0
    return max(positives) / sum(positives)


def evaluate_hypothesis(
    panel: Phase2Panel,
    grid: tuple[Rule, ...],
    *,
    cost: CostModel,
    folds,
    config: Phase2Config,
) -> dict[str, Any]:
    fold_rows = []
    combined_returns = []
    fold_pnls: dict[str, float] = {}
    asset_pnls: dict[str, float] = {}
    decomposition = {"price_pnl": 0.0, "funding_pnl": 0.0, "fees": 0.0, "slippage": 0.0}
    blocked = trades = episodes = 0
    panel_end = panel.open.index[-1]
    for fold in folds:
        train = [
            simulate_basket(
                panel,
                rule,
                cost=cost,
                start=fold.train_start,
                end=fold.train_end,
                entry_end=fold.train_end,
            )
            for rule in grid
        ]
        chosen = _select(train)
        end = min(fold.validation_end + pd.Timedelta(days=EXIT_EXTENSION_DAYS), panel_end)
        validation = simulate_basket(
            panel,
            chosen.rule,
            cost=cost,
            start=fold.validation_start,
            end=end,
            entry_end=fold.validation_end,
        )
        metrics = SeriesMetrics.from_returns(validation.daily_returns)
        combined_returns.append(validation.daily_returns)
        fold_pnls[str(fold.fold_id)] = validation.decomposition["total_pnl"]
        for symbol, row in validation.per_symbol.items():
            asset_pnls[symbol] = asset_pnls.get(symbol, 0.0) + row["price_pnl"] + row["funding_pnl"]
        for key in decomposition:
            decomposition[key] += validation.decomposition[key]
        blocked += validation.blocked_entries
        trades += validation.trades
        episodes += len(validation.episodes)
        fold_rows.append(
            {
                "fold": fold.fold_id,
                "selected": chosen.rule.label(),
                "training_sharpe": SeriesMetrics.from_returns(chosen.daily_returns).sharpe,
                "validation": metrics.to_dict(),
                "validation_summary": validation.to_dict(),
            }
        )
    returns = pd.concat(combined_returns) if combined_returns else pd.Series(dtype=float)
    aggregate = SeriesMetrics.from_returns(returns)
    positive_folds = sum(1 for value in fold_pnls.values() if value > 0)
    fold_contribution = _contribution(fold_pnls)
    asset_contribution = _contribution(asset_pnls)
    # PBO over the full registered period for the whole grid of this hypothesis.
    start, end = folds[0].train_start, panel_end
    full = [simulate_basket(panel, rule, cost=cost, start=start, end=end) for rule in grid]
    matrix = pd.concat([r.daily_returns.rename(r.rule.label()) for r in full], axis=1).fillna(0.0)
    pbo = probability_of_backtest_overfitting(matrix, partitions=config.pbo_partitions)
    gates = {
        "expectancy_positive": aggregate.expectancy > 0,
        "profit_factor": aggregate.profit_factor >= config.profit_factor_min,
        "max_drawdown": aggregate.max_drawdown <= config.max_drawdown_max,
        "positive_folds": positive_folds >= config.min_positive_folds,
        "fold_contribution": fold_contribution <= config.max_contribution,
        "asset_contribution": asset_contribution <= config.max_contribution,
        "pbo": pbo["pbo"] <= config.pbo_max,
    }
    total = (
        decomposition["price_pnl"]
        + decomposition["funding_pnl"]
        - decomposition["fees"]
        - decomposition["slippage"]
    )
    return {
        "cost": cost.name,
        "aggregate": aggregate.to_dict(),
        "positive_folds": positive_folds,
        "fold_contribution": fold_contribution,
        "asset_contribution": asset_contribution,
        "asset_pnl": asset_pnls,
        "decomposition": decomposition | {"total_pnl": total},
        "decomposition_answers": {
            "funding_positive_but_price_loss_dominates": decomposition["funding_pnl"] > 0
            and decomposition["price_pnl"] < 0
            and abs(decomposition["price_pnl"]) > decomposition["funding_pnl"],
            "costs_exceed_funding": decomposition["fees"] + decomposition["slippage"]
            > max(decomposition["funding_pnl"], 0.0),
            "dominant_asset": max(asset_pnls, key=asset_pnls.get) if asset_pnls else None,
        },
        "blocked_entries": blocked,
        "trades": trades,
        "episodes": episodes,
        "pbo": pbo,
        "gates": gates,
        "passed": all(gates.values()),
        "folds": fold_rows,
    }


def run_phase2_research(
    data_dir: Path,
    output_dir: Path,
    *,
    manifest_path: Path | None = None,
    config: Phase2Config | None = None,
    generated_at: str | None = None,
    panel: Phase2Panel | None = None,
) -> dict[str, Any]:
    config = config or Phase2Config()
    panel = panel or load_phase2_panel(data_dir, manifest_path=manifest_path)
    timeline = _daily_timeline(panel)
    folds = make_purged_walk_forward_folds(
        timeline,
        WalkForwardConfig(
            train_duration=f"{config.train_days}D",
            validation_duration=f"{config.validation_days}D",
            fold_count=config.fold_count,
            label_horizon=f"{config.embargo_days}D",
            embargo=f"{config.embargo_days}D",
            min_train_rows=int(config.train_days * 0.95),
            min_validation_rows=int(config.validation_days * 0.9),
        ),
    )
    hypotheses: dict[str, Any] = {}
    for name, grid in (("H1", h1_grid()), ("H2", h2_grid())):
        hypotheses[name] = {
            cost.name: evaluate_hypothesis(panel, grid, cost=cost, folds=folds, config=config)
            for cost in (NORMAL_COST, STRESS_COST)
        }
        hypotheses[name]["passed"] = all(
            block["passed"]
            for block in hypotheses[name].values()
            if isinstance(block, dict) and "passed" in block
        )
    hypotheses["H0"] = {"passed": False, "note": "no-trade control; zero return by construction"}
    promoted = [name for name in ("H1", "H2") if hypotheses[name]["passed"]]
    result = {
        "schema_version": 1,
        "generated_at": generated_at
        or datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "registration": "docs/PHASE2_PREREGISTRATION.md",
        "decision": "ALLOW_SHADOW_OBSERVATION" if promoted else "STOP_NO_EDGE",
        "promoted": promoted,
        "config": asdict(config),
        "universe": list(panel.symbols),
        "panel": {
            "start": panel.open.index[0].isoformat(),
            "end": panel.open.index[-1].isoformat(),
            "hours": int(len(panel.open)),
            "settlements": int(len(panel.funding)),
        },
        "folds": [
            {
                "fold": f.fold_id,
                "train_start": f.train_start.isoformat(),
                "train_end": f.train_end.isoformat(),
                "validation_start": f.validation_start.isoformat(),
                "validation_end": f.validation_end.isoformat(),
            }
            for f in folds
        ],
        "hypotheses": hypotheses,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    _write(
        output_dir / "results.json",
        json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False, default=str) + "\n",
    )
    _write(output_dir / "REPORT.md", render_report(result))
    return result


def _write(path: Path, content: str) -> None:
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(content)
        temporary.chmod(0o660)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _fmt(value: Any, spec: str) -> str:
    return value if isinstance(value, str) else format(value, spec)


def render_report(result: dict[str, Any]) -> str:
    lines = [
        "# Phase 2 Research Report",
        "",
        f"- generated_at: `{result['generated_at']}`",
        f"- decision: **{result['decision']}**",
        f"- registration: `{result['registration']}`",
        f"- universe: {', '.join(result['universe'])}",
        f"- panel: {result['panel']['start'][:10]} → {result['panel']['end'][:10]}",
        "",
        "## Gate results (daily portfolio net returns, sleeve basis)",
        "",
        "| Hypothesis | Cost | Days | PF | Expectancy/day | MDD | Positive folds | Fold conc. | Asset conc. | PBO | Blocked entries | Pass |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for name in ("H1", "H2"):
        for cost in ("normal", "stress"):
            block = result["hypotheses"][name][cost]
            agg = block["aggregate"]
            lines.append(
                f"| {name} | {cost} | {agg['days']} | {_fmt(agg['profit_factor'], '.3f')} | "
                f"{agg['expectancy']:.6f} | {agg['max_drawdown']:.2%} | {block['positive_folds']} | "
                f"{block['fold_contribution']:.2f} | {block['asset_contribution']:.2f} | "
                f"{block['pbo']['pbo']:.2f} | {block['blocked_entries']} | "
                f"{'PASS' if block['passed'] else 'FAIL'} |"
            )
    lines += [
        "",
        "## P&L decomposition (USDT, sum over validation folds)",
        "",
        "| Hypothesis | Cost | Total | Price | Funding | Fees | Slippage | Trades | Episodes |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name in ("H1", "H2"):
        for cost in ("normal", "stress"):
            block = result["hypotheses"][name][cost]
            d = block["decomposition"]
            lines.append(
                f"| {name} | {cost} | {d['total_pnl']:.2f} | {d['price_pnl']:.2f} | {d['funding_pnl']:.2f} | "
                f"{d['fees']:.2f} | {d['slippage']:.2f} | {block['trades']} | {block['episodes']} |"
            )
    lines += ["", "## Fold selections", ""]
    for name in ("H1", "H2"):
        lines.append(f"### {name}")
        lines.append("")
        lines.append(
            "| Cost | Fold | Selected on training | Train Sharpe | Validation return | Validation PF |"
        )
        lines.append("|---|---:|---|---:|---:|---:|")
        for cost in ("normal", "stress"):
            for row in result["hypotheses"][name][cost]["folds"]:
                v = row["validation"]
                lines.append(
                    f"| {cost} | {row['fold']} | {row['selected']} | {row['training_sharpe']:.2f} | "
                    f"{v['total_return']:.2%} | {_fmt(v['profit_factor'], '.3f')} |"
                )
        lines.append("")
    lines += [
        "## Interpretation",
        "",
        "H0 (no trade) is the control. A hypothesis passes only if every gate holds under both cost "
        "regimes and its PBO is at or below 0.20. Results are conditional on the eight symbols chosen "
        "in 2026-09 and on Binance USD-M funding; they do not transfer to another venue. Passing "
        "authorizes only a separate Demo/shadow observation, never real capital.",
        "",
    ]
    return "\n".join(lines)
