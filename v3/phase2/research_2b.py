"""Phase 2b two-stage evaluation with the registered gates (docs/PHASE2B_PREREGISTRATION.md).

Stage A reuses the Phase 2 folds (declared contaminated, diagnostic). Stage B is
one evaluation on data no Phase 2 run used. Fold and Stage B windows are pinned
to the registration and checked against the fold builder; nothing in Stage A,
including the PBO matrix, reads data after the Stage A horizon.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from v3.validation import WalkForwardConfig, make_purged_walk_forward_folds

from .maker import (
    H3_NORMAL,
    H3_STRESS,
    H3T_NORMAL,
    H3T_STRESS,
    DailyRule,
    ExecutionModel,
    MakerPanel,
    h3_grid,
    load_maker_panel,
    simulate_maker_basket,
)
from .pbo import probability_of_backtest_overfitting
from .research import (
    EXIT_EXTENSION_DAYS,
    SeriesMetrics,
    _contribution,
    _daily_timeline,
    _select,
    _write,
)


def _ts(value: str) -> pd.Timestamp:
    return pd.Timestamp(value, tz="UTC")


# Registration §6: Stage A folds (identical to Phase 2) and the Stage B window.
STAGE_A_FOLDS = (
    ("2025-07-07", "2026-01-03", "2026-01-17", "2026-02-16"),
    ("2025-08-06", "2026-02-02", "2026-02-16", "2026-03-18"),
    ("2025-09-05", "2026-03-04", "2026-03-18", "2026-04-17"),
    ("2025-10-05", "2026-04-03", "2026-04-17", "2026-05-17"),
    ("2025-11-04", "2026-05-03", "2026-05-17", "2026-06-16"),
    ("2025-12-04", "2026-06-02", "2026-06-16", "2026-07-16"),
)
STAGE_A_HORIZON = _ts("2026-07-30")  # last fold's exit observation; Stage A reads nothing later
STAGE_B_TRAIN = (_ts("2026-01-17"), _ts("2026-07-16"))
STAGE_B_EVAL = (_ts("2026-07-31"), _ts("2026-10-01"))
STAGE_B_ENTRY_END = _ts("2026-09-30")
STRESS_SLIPPAGE_BPS = 5.0


@dataclass(frozen=True)
class Phase2bConfig:
    pbo_partitions: int = 16
    profit_factor_min: float = 1.15
    max_drawdown_max: float = 0.10
    min_positive_folds: int = 4
    max_contribution: float = 0.50
    pbo_max: float = 0.20
    stage_b_min_cycles: int = 2


@dataclass(frozen=True)
class PinnedFold:
    fold_id: int
    train_start: pd.Timestamp
    train_end: pd.Timestamp
    validation_start: pd.Timestamp
    validation_end: pd.Timestamp


def stage_a_folds(panel: MakerPanel) -> tuple[PinnedFold, ...]:
    """Registered folds, verified against the Phase 2 fold builder on this panel."""
    pinned = tuple(
        PinnedFold(i, _ts(a), _ts(b), _ts(c), _ts(d))
        for i, (a, b, c, d) in enumerate(STAGE_A_FOLDS)
    )
    built = make_purged_walk_forward_folds(
        _daily_timeline(panel.base),
        WalkForwardConfig(
            train_duration="180D",
            validation_duration="30D",
            fold_count=6,
            label_horizon="14D",
            embargo="14D",
            min_train_rows=171,
            min_validation_rows=27,
        ),
    )
    for fold, ref in zip(built, pinned, strict=True):
        if (fold.train_start, fold.train_end, fold.validation_start, fold.validation_end) != (
            ref.train_start,
            ref.train_end,
            ref.validation_start,
            ref.validation_end,
        ):
            raise ValueError(f"fold {ref.fold_id} differs from the registration")
    return pinned


def _fill_summary(results) -> dict[str, Any]:
    keys = (
        "maker_orders",
        "maker_filled",
        "taker_fallback",
        "taker_planned",
        "taker_risk",
        "maker_notional",
        "taker_notional",
    )
    total = {key: sum(r.extra.get(key, 0) for r in results) for key in keys}
    total["maker_fill_rate"] = (
        total["maker_filled"] / total["maker_orders"] if total["maker_orders"] else None
    )
    notional = total["maker_notional"] + total["taker_notional"]
    total["maker_notional_share"] = total["maker_notional"] / notional if notional else None
    return total


def _decomposition(results) -> dict[str, float]:
    keys = ("price_pnl", "funding_pnl", "fees", "slippage")
    out = {key: sum(r.decomposition[key] for r in results) for key in keys}
    out["total_pnl"] = out["price_pnl"] + out["funding_pnl"] - out["fees"] - out["slippage"]
    return out


def _holding_stats(results, days: int) -> dict[str, Any]:
    episodes = [e for r in results for e in r.episodes]
    traded = sum(r.traded_notional for r in results)
    return {
        "episodes": len(episodes),
        "mean_episode_days": (sum(e["hours"] for e in episodes) / len(episodes) / 24)
        if episodes
        else None,
        "traded_notional": traded,
        "annual_turnover_x_sleeve": traded / 200.0 * 365.0 / days if days else None,
        "trades": sum(r.trades for r in results),
        "blocked_entries": sum(r.blocked_entries for r in results),
        "decisions": sum(r.decisions for r in results),
        "stop_events": sum(r.stop_events for r in results),
        "forced_exits": sum(r.forced_exits for r in results),
    }


def evaluate_stage_a(
    panel: MakerPanel,
    grid: tuple[DailyRule, ...],
    *,
    execution: ExecutionModel,
    folds: tuple[PinnedFold, ...],
    config: Phase2bConfig,
) -> dict[str, Any]:
    fold_rows, validations, combined = [], [], []
    fold_pnls: dict[str, float] = {}
    asset_pnls: dict[str, float] = {}
    for fold in folds:
        train = [
            simulate_maker_basket(
                panel,
                rule,
                execution=execution,
                start=fold.train_start,
                end=fold.train_end,
                entry_end=fold.train_end,
            )
            for rule in grid
        ]
        chosen = _select(train)
        end = fold.validation_end + pd.Timedelta(days=EXIT_EXTENSION_DAYS)
        if end > STAGE_A_HORIZON:
            raise ValueError("Stage A must not read past its horizon")
        validation = simulate_maker_basket(
            panel,
            chosen.rule,
            execution=execution,
            start=fold.validation_start,
            end=end,
            entry_end=fold.validation_end,
        )
        validations.append(validation)
        combined.append(validation.daily_returns)
        fold_pnls[str(fold.fold_id)] = validation.decomposition["total_pnl"]
        for symbol, row in validation.per_symbol.items():
            asset_pnls[symbol] = asset_pnls.get(symbol, 0.0) + row["price_pnl"] + row["funding_pnl"]
        fold_rows.append(
            {
                "fold": fold.fold_id,
                "selected": chosen.rule.label(),
                "training_sharpe": SeriesMetrics.from_returns(chosen.daily_returns).sharpe,
                "validation": SeriesMetrics.from_returns(validation.daily_returns).to_dict(),
                "decomposition": validation.decomposition,
                "fills": validation.extra,
                "episodes": len(validation.episodes),
            }
        )
    returns = pd.concat(combined)
    aggregate = SeriesMetrics.from_returns(returns)
    full = [
        simulate_maker_basket(
            panel, rule, execution=execution, start=folds[0].train_start, end=STAGE_A_HORIZON
        )
        for rule in grid
    ]
    matrix = pd.concat([r.daily_returns.rename(r.rule.label()) for r in full], axis=1).fillna(0.0)
    pbo = probability_of_backtest_overfitting(matrix, partitions=config.pbo_partitions)
    positive_folds = sum(1 for value in fold_pnls.values() if value > 0)
    gates = {
        "expectancy_positive": aggregate.expectancy > 0,
        "profit_factor": aggregate.profit_factor >= config.profit_factor_min,
        "max_drawdown": aggregate.max_drawdown <= config.max_drawdown_max,
        "positive_folds": positive_folds >= config.min_positive_folds,
        "fold_contribution": _contribution(fold_pnls) <= config.max_contribution,
        "asset_contribution": _contribution(asset_pnls) <= config.max_contribution,
        "pbo": pbo["pbo"] <= config.pbo_max,
    }
    return {
        "cost": execution.name,
        "aggregate": aggregate.to_dict(),
        "positive_folds": positive_folds,
        "fold_contribution": _contribution(fold_pnls),
        "asset_contribution": _contribution(asset_pnls),
        "asset_pnl": asset_pnls,
        "decomposition": _decomposition(validations),
        "fills": _fill_summary(validations),
        "activity": _holding_stats(validations, aggregate.days),
        "pbo": pbo,
        "gates": gates,
        "passed": all(gates.values()),
        "folds": fold_rows,
    }


def evaluate_stage_b(
    panel: MakerPanel,
    grid: tuple[DailyRule, ...],
    *,
    execution: ExecutionModel,
    config: Phase2bConfig,
) -> dict[str, Any]:
    train = [
        simulate_maker_basket(
            panel,
            rule,
            execution=execution,
            start=STAGE_B_TRAIN[0],
            end=STAGE_B_TRAIN[1],
            entry_end=STAGE_B_TRAIN[1],
        )
        for rule in grid
    ]
    chosen = _select(train)
    result = simulate_maker_basket(
        panel,
        chosen.rule,
        execution=execution,
        start=STAGE_B_EVAL[0],
        end=STAGE_B_EVAL[1],
        entry_end=STAGE_B_ENTRY_END,
        final_slippage_bps=STRESS_SLIPPAGE_BPS,
    )
    metrics = SeriesMetrics.from_returns(result.daily_returns)
    d = result.decomposition
    cycles = len(result.episodes)
    enough_cycles = cycles >= config.stage_b_min_cycles
    gates = {
        "net_return_positive": d["total_pnl"] > 0,
        "max_drawdown": metrics.max_drawdown <= config.max_drawdown_max,
        "funding_exceeds_costs": d["funding_pnl"] > d["fees"] + d["slippage"],
        "minimum_cycles": enough_cycles,
    }
    verdict = "PASS" if all(gates.values()) else ("UNDECIDABLE" if not enough_cycles else "FAIL")
    return {
        "cost": execution.name,
        "selected": chosen.rule.label(),
        "training_sharpe": SeriesMetrics.from_returns(chosen.daily_returns).sharpe,
        "metrics": metrics.to_dict(),
        "decomposition": d,
        "fills": result.extra,
        "activity": _holding_stats([result], metrics.days),
        "episodes": result.episodes,
        "per_symbol": result.per_symbol,
        "gates": gates,
        "verdict": verdict,
        "passed": verdict == "PASS",
    }


def run_phase2b_research(
    data_dir: Path,
    output_dir: Path,
    *,
    manifest_path: Path | None = None,
    config: Phase2bConfig | None = None,
    generated_at: str | None = None,
    phase2_results: Path | None = None,
    panel: MakerPanel | None = None,
) -> dict[str, Any]:
    config = config or Phase2bConfig()
    panel = panel or load_maker_panel(data_dir, manifest_path=manifest_path)
    if panel.base.open.index[-1] < STAGE_B_EVAL[1]:
        raise ValueError("panel does not reach the end of the Stage B window")
    folds = stage_a_folds(panel)
    hypotheses: dict[str, Any] = {"H0": {"note": "no-trade control; zero return by construction"}}
    for name, models in (("H3", (H3_NORMAL, H3_STRESS)), ("H3T", (H3T_NORMAL, H3T_STRESS))):
        grid = h3_grid(name)
        block: dict[str, Any] = {}
        for model in models:
            block[model.name] = {
                "stage_a": evaluate_stage_a(
                    panel, grid, execution=model, folds=folds, config=config
                ),
                "stage_b": evaluate_stage_b(panel, grid, execution=model, config=config),
            }
        block["stage_a_passed"] = all(block[m.name]["stage_a"]["passed"] for m in models)
        block["stage_b_verdicts"] = {m.name: block[m.name]["stage_b"]["verdict"] for m in models}
        block["passed"] = block["stage_a_passed"] and all(
            block[m.name]["stage_b"]["passed"] for m in models
        )
        hypotheses[name] = block
    h3 = hypotheses["H3"]
    if h3["passed"]:
        decision = "ALLOW_SHADOW_OBSERVATION"
    elif "UNDECIDABLE" in h3["stage_b_verdicts"].values() and h3["stage_a_passed"]:
        decision = "UNDECIDABLE"
    else:
        decision = "STOP_NO_EDGE"
    reference = None
    if phase2_results and phase2_results.is_file():
        p2 = json.loads(phase2_results.read_text())["hypotheses"]["H1"]
        reference = {
            cost: {
                "trades": p2[cost]["trades"],
                "episodes": p2[cost]["episodes"],
                "decomposition": p2[cost]["decomposition"],
            }
            for cost in ("normal", "stress")
        }
    result = {
        "schema_version": 1,
        "generated_at": generated_at
        or datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "registration": "docs/PHASE2B_PREREGISTRATION.md",
        "decision": decision,
        "universe": list(panel.base.symbols),
        "panel": {
            "start": panel.base.open.index[0].isoformat(),
            "end": panel.base.open.index[-1].isoformat(),
            "hours": int(len(panel.base.open)),
            "settlements": int(len(panel.base.funding)),
        },
        "stage_a_folds": [
            {
                "fold": f.fold_id,
                "train": [f.train_start.isoformat(), f.train_end.isoformat()],
                "validation": [f.validation_start.isoformat(), f.validation_end.isoformat()],
            }
            for f in folds
        ],
        "stage_a_horizon": STAGE_A_HORIZON.isoformat(),
        "stage_b": {
            "train": [STAGE_B_TRAIN[0].isoformat(), STAGE_B_TRAIN[1].isoformat()],
            "evaluation": [STAGE_B_EVAL[0].isoformat(), STAGE_B_EVAL[1].isoformat()],
            "entry_end": STAGE_B_ENTRY_END.isoformat(),
        },
        "phase2_h1_reference": reference,
        "hypotheses": hypotheses,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    _write(
        output_dir / "results.json",
        json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False, default=str) + "\n",
    )
    _write(output_dir / "REPORT.md", render_report(result))
    return result


def _pf(value: Any) -> str:
    return value if isinstance(value, str) else f"{value:.3f}"


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.1%}"


def render_report(result: dict[str, Any]) -> str:
    lines = [
        "# Phase 2b Research Report",
        "",
        f"- generated_at: `{result['generated_at']}`",
        f"- decision: **{result['decision']}**",
        f"- registration: `{result['registration']}`",
        f"- universe: {', '.join(result['universe'])}",
        f"- panel: {result['panel']['start'][:16]} → {result['panel']['end'][:16]}",
        f"- Stage B evaluation: {result['stage_b']['evaluation'][0][:10]} → "
        f"{result['stage_b']['evaluation'][1][:10]} (untouched by Phase 2)",
        "",
        "## Stage A — Phase 2 folds (contaminated, diagnostic)",
        "",
        "| Hypothesis | Cost | Days | PF | Expectancy/day | MDD | Positive folds | Fold conc. | "
        "Asset conc. | PBO | Pass |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for name in ("H3", "H3T"):
        for cost in ("normal", "stress"):
            a = result["hypotheses"][name][cost]["stage_a"]
            agg = a["aggregate"]
            lines.append(
                f"| {name} | {cost} | {agg['days']} | {_pf(agg['profit_factor'])} | "
                f"{agg['expectancy']:.6f} | {agg['max_drawdown']:.2%} | {a['positive_folds']} | "
                f"{a['fold_contribution']:.2f} | {a['asset_contribution']:.2f} | "
                f"{a['pbo']['pbo']:.2f} | {'PASS' if a['passed'] else 'FAIL'} |"
            )
    lines += [
        "",
        "## Stage B — confirmatory window",
        "",
        "| Hypothesis | Cost | Selected | Net PnL | Funding | Fees | Slippage | MDD | Cycles | "
        "Verdict |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for name in ("H3", "H3T"):
        for cost in ("normal", "stress"):
            b = result["hypotheses"][name][cost]["stage_b"]
            d = b["decomposition"]
            lines.append(
                f"| {name} | {cost} | {b['selected']} | {d['total_pnl']:.2f} | "
                f"{d['funding_pnl']:.2f} | {d['fees']:.2f} | {d['slippage']:.2f} | "
                f"{b['metrics']['max_drawdown']:.2%} | {b['activity']['episodes']} | "
                f"{b['verdict']} |"
            )
    lines += [
        "",
        "## P&L decomposition and activity (USDT; Stage A sums over validation folds)",
        "",
        "| Hypothesis | Cost | Stage | Total | Price | Funding | Fees | Slippage | Trades | "
        "Episodes | Maker fill rate | Maker notional share | Turnover x sleeve/yr |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name in ("H3", "H3T"):
        for cost in ("normal", "stress"):
            for stage in ("stage_a", "stage_b"):
                s = result["hypotheses"][name][cost][stage]
                d, act, fills = s["decomposition"], s["activity"], s["fills"]
                turnover = act["annual_turnover_x_sleeve"]
                lines.append(
                    f"| {name} | {cost} | {stage[-1].upper()} | {d['total_pnl']:.2f} | "
                    f"{d['price_pnl']:.2f} | {d['funding_pnl']:.2f} | {d['fees']:.2f} | "
                    f"{d['slippage']:.2f} | {act['trades']} | {act['episodes']} | "
                    f"{_pct(fills.get('maker_fill_rate'))} | "
                    f"{_pct(fills.get('maker_notional_share'))} | "
                    f"{'n/a' if turnover is None else f'{turnover:.1f}'} |"
                )
    reference = result.get("phase2_h1_reference")
    if reference:
        lines += [
            "",
            "## Phase 2 H1 reference (same Stage A folds, taker, 8-hour decisions)",
            "",
            "| Cost | Trades | Episodes | Funding | Fees | Slippage | Total |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
        for cost, row in reference.items():
            d = row["decomposition"]
            lines.append(
                f"| {cost} | {row['trades']} | {row['episodes']} | {d['funding_pnl']:.2f} | "
                f"{d['fees']:.2f} | {d['slippage']:.2f} | {d['total_pnl']:.2f} |"
            )
    lines += ["", "## Stage A fold selections (H3)", ""]
    lines.append("| Cost | Fold | Selected on training | Train Sharpe | Validation return | PF |")
    lines.append("|---|---:|---|---:|---:|---:|")
    for cost in ("normal", "stress"):
        for row in result["hypotheses"]["H3"][cost]["stage_a"]["folds"]:
            v = row["validation"]
            lines.append(
                f"| {cost} | {row['fold']} | {row['selected']} | {row['training_sharpe']:.2f} | "
                f"{v['total_return']:.2%} | {_pf(v['profit_factor'])} |"
            )
    lines += [
        "",
        "## Interpretation",
        "",
        "H3 passes only if Stage A and Stage B both pass under both cost regimes. Stage A reuses "
        "folds whose Phase 2 results were known when H3 was designed, so it cannot pass H3 alone. "
        "H3T is a taker diagnostic and is never promoted. Maker fills use a trade-through rule on "
        "hourly candles, which cannot see queue position; live fill rates can be lower. Passing "
        "authorizes only a Demo/shadow observation, never real capital.",
        "",
    ]
    return "\n".join(lines)
