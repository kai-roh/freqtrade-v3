"""Phase 2b risk-neutralization diagnosis (docs/PHASE2B_RISK_DIAGNOSIS.md).

Diagnosis only, on already-seen data. Stage 1 attributes the two traced H3
episodes to the balance rule and to beta mismatch. Stage 2 runs one continuous
account per grid point over 2025-07-07..2026-07-30 (no fold concatenation, no
overlapping dates) and applies the pre-committed continue-or-shelve criteria to
the exchange-constrained combined variant.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from .maker import (
    H3_NORMAL,
    H3_STRESS,
    MakerPanel,
    RiskVariant,
    h3_grid,
    load_maker_panel,
    simulate_maker_basket,
)
from .research import EXIT_EXTENSION_DAYS, SeriesMetrics, _write
from .research_2b import STAGE_A_FOLDS, STAGE_A_HORIZON

WINDOW = (pd.Timestamp("2025-07-07", tz="UTC"), STAGE_A_HORIZON)
VARIANT_SPECS = (("V0", False, False), ("V1", True, False), ("V2", False, True), ("V3", True, True))
MODES = ("ideal", "constrained")
COSTS = (H3_NORMAL, H3_STRESS)
MIN_EPISODES = 6
MIN_GRID_POINTS = 3


def load_venue_filters(path: Path) -> dict[str, tuple[float, float]]:
    raw = json.loads(path.read_text())["raw_filters"]
    return {
        symbol.removesuffix("USDT"): (float(row["MIN_NOTIONAL"]), float(row["LOT_SIZE.stepSize"]))
        for symbol, row in raw.items()
    }


def variants(filters: dict[str, tuple[float, float]]) -> list[RiskVariant]:
    out = []
    for mode in MODES:
        for name, balance, beta in VARIANT_SPECS:
            out.append(
                RiskVariant(
                    f"{name}-{mode}",
                    balance=balance,
                    beta=beta,
                    venue_filters=filters if mode == "constrained" else None,
                )
            )
    return out


def _summary(result) -> dict[str, Any]:
    d = result.decomposition
    episodes = [e["pnl_usdt"] for e in result.episodes]
    metrics = SeriesMetrics.from_returns(result.daily_returns)
    return {
        "net": d["total_pnl"],
        "price": d["price_pnl"],
        "funding": d["funding_pnl"],
        "costs": d["fees"] + d["slippage"],
        "trades": result.trades,
        "episodes": len(episodes),
        "episode_pnl": episodes,
        "net_minus_best_episode": d["total_pnl"] - max(episodes) if episodes else d["total_pnl"],
        "days": metrics.days,
        "max_drawdown": metrics.max_drawdown,
        "sharpe": metrics.sharpe,
        "decisions": result.decisions,
        "entry_allowed_decisions": result.extra.get("entry_allowed_decisions"),
        "stop_events": result.stop_events,
        "mean_abs_net_dollar": result.extra.get("mean_abs_net_dollar"),
        "mean_abs_net_beta": result.extra.get("mean_abs_net_beta"),
        "min_notional_skips": result.extra.get("min_notional_skips"),
        "balance_full_exits": result.extra.get("balance_full_exits"),
        "balance_orders": result.extra.get("balance_orders"),
    }


def _effects(rows: dict[str, dict[str, Any]], mode: str) -> dict[str, dict[str, float]]:
    def get(name, key):
        return rows[f"{name}-{mode}"][key]

    out = {}
    for key in ("net", "price"):
        v0, v1, v2, v3 = (get(n, key) for n in ("V0", "V1", "V2", "V3"))
        out[key] = {
            "balance_V1_minus_V0": v1 - v0,
            "beta_V2_minus_V0": v2 - v0,
            "combined_V3_minus_V0": v3 - v0,
            "interaction": v3 - v1 - v2 + v0,
        }
    return out


def stage_one(panel: MakerPanel, recorded: dict, filters) -> dict[str, Any]:
    stage_a = recorded["hypotheses"]["H3"]
    out: dict[str, Any] = {}
    for cost in COSTS:
        fold_row = next(r for r in stage_a[cost.name]["stage_a"]["folds"] if r["episodes"])
        rule = next(r for r in h3_grid("H3") if r.label() == fold_row["selected"])
        _, _, validation_start, validation_end = STAGE_A_FOLDS[fold_row["fold"]]
        start = pd.Timestamp(validation_start, tz="UTC")
        entry_end = pd.Timestamp(validation_end, tz="UTC")
        end = entry_end + pd.Timedelta(days=EXIT_EXTENSION_DAYS)
        rows = {}
        for variant in variants(filters):
            result = simulate_maker_basket(
                panel,
                rule,
                execution=cost,
                start=start,
                end=end,
                entry_end=entry_end,
                risk=variant,
            )
            rows[variant.name] = _summary(result)
        baseline = rows["V0-ideal"]
        expected = fold_row["decomposition"]["total_pnl"]
        if abs(baseline["net"] - expected) > 1e-9:
            raise ValueError("V0-ideal does not reproduce the recorded fold")
        out[cost.name] = {
            "fold": fold_row["fold"],
            "rule": rule.label(),
            "window": [start.isoformat(), end.isoformat()],
            "rows": rows,
            "effects": {mode: _effects(rows, mode) for mode in MODES},
        }
    return out


def stage_two(panel: MakerPanel, filters) -> dict[str, Any]:
    start, end = WINDOW
    out: dict[str, Any] = {}
    for rule in h3_grid("H3"):
        per_rule: dict[str, Any] = {}
        for cost in COSTS:
            rows = {}
            for variant in variants(filters):
                result = simulate_maker_basket(
                    panel,
                    rule,
                    execution=cost,
                    start=start,
                    end=end,
                    entry_end=end,
                    risk=variant,
                )
                rows[variant.name] = _summary(result)
            per_rule[cost.name] = {"rows": rows, "effects": {m: _effects(rows, m) for m in MODES}}
        out[rule.label()] = per_rule
    return out


def verdict(stage2: dict[str, Any], variant: str = "V3-constrained") -> dict[str, Any]:
    opportunity, economics, robust = [], [], []
    for label, per_rule in stage2.items():
        rows = {cost: per_rule[cost]["rows"][variant] for cost in ("normal", "stress")}
        if rows["normal"]["episodes"] >= MIN_EPISODES:
            opportunity.append(label)
        economic = all(
            r["net"] > 0 and r["funding"] > r["costs"] + max(0.0, -r["price"])
            for r in rows.values()
        )
        if economic:
            economics.append(label)
            if all(r["net_minus_best_episode"] >= 0 for r in rows.values()):
                robust.append(label)
    checks = {
        "opportunity": len(opportunity) >= MIN_GRID_POINTS,
        "economics": len(economics) >= MIN_GRID_POINTS,
        "not_few_trades": bool(economics) and len(robust) == len(economics),
    }
    return {
        "variant": variant,
        "grid_points_with_enough_episodes": opportunity,
        "grid_points_economic": economics,
        "grid_points_robust_to_best_episode": robust,
        "checks": checks,
        "decision": "CONTINUE_TO_NEW_REGISTRATION" if all(checks.values()) else "SHELVE_FAMILY",
    }


def run_risk_diagnosis(
    data_dir: Path,
    output_dir: Path,
    *,
    manifest_path: Path,
    filters_path: Path,
    recorded_path: Path,
    generated_at: str | None = None,
) -> dict[str, Any]:
    panel = load_maker_panel(data_dir, manifest_path=manifest_path)
    filters = load_venue_filters(filters_path)
    recorded = json.loads(recorded_path.read_text())
    stage1 = stage_one(panel, recorded, filters)
    stage2 = stage_two(panel, filters)
    result = {
        "schema_version": 1,
        "generated_at": generated_at
        or datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "plan": "docs/PHASE2B_RISK_DIAGNOSIS.md",
        "diagnosis_only": True,
        "stage_two_window": [WINDOW[0].isoformat(), WINDOW[1].isoformat()],
        "venue_filters": {k: list(v) for k, v in filters.items()},
        "stage_one": stage1,
        "stage_two": stage2,
        "verdict": verdict(stage2),
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    _write(
        output_dir / "results.json",
        json.dumps(result, indent=2, sort_keys=True, default=str) + "\n",
    )
    _write(output_dir / "REPORT.md", render(result))
    return result


def render(result: dict[str, Any]) -> str:
    lines = [
        "# Phase 2b risk-neutralization diagnosis",
        "",
        f"- generated_at: `{result['generated_at']}`",
        f"- plan: `{result['plan']}` (diagnosis on already-seen data; never a promotion basis)",
        f"- decision: **{result['verdict']['decision']}**",
        "",
        "## Stage 1 — the two traced episodes",
        "",
    ]
    for cost, block in result["stage_one"].items():
        lines += [
            f"### {cost} cost — fold {block['fold']}, `{block['rule']}`",
            "",
            "| Variant | Net | Price | Funding | Costs | Trades | Episodes | Mean abs net $ | "
            "Mean abs net β$ | Min-notional skips | Full exits |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
        for name, r in block["rows"].items():
            lines.append(
                f"| {name} | {r['net']:.3f} | {r['price']:.3f} | {r['funding']:.3f} | "
                f"{r['costs']:.3f} | {r['trades']} | {r['episodes']} | "
                f"{r['mean_abs_net_dollar']:.1f} | {r['mean_abs_net_beta']:.1f} | "
                f"{r['min_notional_skips']} | {r['balance_full_exits']} |"
            )
        lines += [
            "",
            "| Mode | Effect on net | Balance (V1−V0) | Beta (V2−V0) | Both (V3−V0) | Interaction |",
            "|---|---|---:|---:|---:|---:|",
        ]
        for mode, effects in block["effects"].items():
            for key in ("net", "price"):
                e = effects[key]
                lines.append(
                    f"| {mode} | {key} | {e['balance_V1_minus_V0']:+.3f} | {e['beta_V2_minus_V0']:+.3f} | "
                    f"{e['combined_V3_minus_V0']:+.3f} | {e['interaction']:+.3f} |"
                )
        lines.append("")
    start, end = result["stage_two_window"]
    lines += [
        f"## Stage 2 — one continuous account per grid point, {start[:10]} → {end[:10]}",
        "",
        "| Grid point | Cost | Variant | Net | Price | Funding | Costs | Episodes | Entry-allowed "
        "decisions | Net − best episode | MDD | Min-notional skips |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for label, per_rule in result["stage_two"].items():
        for cost in ("normal", "stress"):
            for name, r in per_rule[cost]["rows"].items():
                lines.append(
                    f"| {label} | {cost} | {name} | {r['net']:.2f} | {r['price']:.2f} | "
                    f"{r['funding']:.2f} | {r['costs']:.2f} | {r['episodes']} | "
                    f"{r['entry_allowed_decisions']}/{r['decisions']} | "
                    f"{r['net_minus_best_episode']:.2f} | {r['max_drawdown']:.2%} | "
                    f"{r['min_notional_skips']} |"
                )
    v = result["verdict"]
    lines += [
        "",
        f"## Verdict ({v['variant']})",
        "",
        f"- Grid points with at least {MIN_EPISODES} episodes: {v['grid_points_with_enough_episodes'] or 'none'}",
        f"- Grid points economic under both costs: {v['grid_points_economic'] or 'none'}",
        f"- Of those, robust to removing the best episode: {v['grid_points_robust_to_best_episode'] or 'none'}",
        f"- Checks: {v['checks']}",
        f"- Decision: **{v['decision']}**",
        "",
        "Episode P&L is the equity change from the first held hour, so it excludes entry costs. "
        "Exchange filters are the 2026-10-02 values applied to past prices. Betas are trailing "
        "30-day hourly estimates clipped to [0.25, 4].",
        "",
    ]
    return "\n".join(lines)
