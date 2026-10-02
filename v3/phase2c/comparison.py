"""Pre-committed MA200 comparison (docs/PHASE2C_MA200_COMPARISON.md).

Fixed MA200 on perpetuals against volatility-matched holds on perpetuals and on
spot, over the same period, sleeve, and risk rule, in ideal and exchange-
constrained modes. Diagnosis on already-seen data; never a promotion basis.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from v3.phase2.data import load_phase2_panel
from v3.phase2.research import SeriesMetrics, _write

from .research import (
    DATA_END,
    Phase2cConfig,
    _summary,
    load_spot_filters,
    load_venue_filters,
    walk_forward,
)
from .trend import (
    NORMAL,
    STRESS,
    SYMBOLS,
    Cost,
    TrendRule,
    load_spot_panel,
    simulate_trend,
    target_weights,
)

PRIMARY = (pd.Timestamp("2022-08-01", tz="UTC"), DATA_END)
REFERENCE = (pd.Timestamp("2020-08-01", tz="UTC"), DATA_END)
SPOT_FEE_BPS = 10.0
MA200 = TrendRule("ma200")
BH_VT = TrendRule("bh_vt")
CRITERIA = {
    "retention": 0.70,
    "drawdown_ratio": 2.0 / 3.0,
    "max_skip_share": 0.10,
}


def spot_cost(cost: Cost) -> Cost:
    return Cost(cost.name, cost.slippage_bps, fee_bps=SPOT_FEE_BPS)


def _flips(panel, start, end) -> dict[str, int]:
    weights = target_weights(panel, MA200)
    window = weights[(weights.index >= start) & (weights.index <= end)]
    out = {}
    for symbol in SYMBOLS:
        signs = np.sign(window[symbol].dropna())
        signs = signs[signs != 0]
        out[symbol] = int((signs != signs.shift()).sum() - 1) if len(signs) else 0
    return out


def _run(panel, rule, cost, window, *, filters, market, cache, sleeve) -> dict[str, Any]:
    result = simulate_trend(
        panel,
        [(window[0], rule)],
        cost=cost,
        start=window[0],
        end=window[1],
        sleeve=sleeve,
        filters=filters,
        weights_cache=cache,
        market=market,
    )
    summary = _summary(result)
    metrics = SeriesMetrics.from_returns(result.daily_returns)
    years = metrics.days / 365.0 if metrics.days else 1.0
    by_year = summary["pnl_by_year"]
    summary.update(
        {
            "market": market,
            "constrained": filters is not None,
            "order_attempts": result.extra["order_attempts"],
            "orders_per_year": result.trades / years,
            "skip_share": result.rounding_skips / result.extra["order_attempts"]
            if result.extra["order_attempts"]
            else 0.0,
            "worst_year_pnl": min(by_year.values()) if by_year else 0.0,
            "return_over_mdd": summary["annualized_return"] / metrics.max_drawdown
            if metrics.max_drawdown > 0
            else float("inf"),
        }
    )
    return summary


def _criteria(ma: dict[str, Any], hold: dict[str, Any]) -> dict[str, bool]:
    ma_net = ma["decomposition"]["total_pnl"]
    hold_net = hold["decomposition"]["total_pnl"]
    retention = ma_net >= CRITERIA["retention"] * hold_net if hold_net > 0 else ma_net >= hold_net
    return {
        "C1_retention": bool(retention),
        "C2_drawdown": bool(
            ma["metrics"]["max_drawdown"]
            <= CRITERIA["drawdown_ratio"] * hold["metrics"]["max_drawdown"]
        ),
        "C3_efficiency": bool(ma["return_over_mdd"] >= hold["return_over_mdd"]),
        "C4_worst_year": bool(ma["worst_year_pnl"] >= hold["worst_year_pnl"]),
        "C5_implementable": bool(ma["skip_share"] <= CRITERIA["max_skip_share"]),
    }


def run_comparison(
    perp_dir: Path,
    perp_manifest: Path,
    spot_dir: Path,
    spot_manifest: Path,
    perp_filters_path: Path,
    spot_filters_path: Path,
    output_dir: Path,
    *,
    sleeve: float = 500.0,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Run the plan. ``sleeve`` 500 is the pre-committed value; 1,000 is Decision 0018."""
    perp = load_phase2_panel(perp_dir, manifest_path=perp_manifest, symbols=SYMBOLS)
    spot = load_spot_panel(spot_dir, manifest_path=spot_manifest)
    perp_filters = load_venue_filters(perp_filters_path)
    spot_filters = load_spot_filters(spot_filters_path)
    perp_cache: dict = {}
    spot_cache: dict = {}
    costs: dict[str, Any] = {}
    for cost in (NORMAL, STRESS):
        block: dict[str, Any] = {}
        for period_name, window in (("primary", PRIMARY), ("reference", REFERENCE)):
            runs = {}
            for mode, pf, sf in (
                ("ideal", None, None),
                ("constrained", perp_filters, spot_filters),
            ):
                runs[f"MA200-perp/{mode}"] = _run(
                    perp,
                    MA200,
                    cost,
                    window,
                    filters=pf,
                    market="perp",
                    cache=perp_cache,
                    sleeve=sleeve,
                )
                runs[f"BHVT-perp/{mode}"] = _run(
                    perp,
                    BH_VT,
                    cost,
                    window,
                    filters=pf,
                    market="perp",
                    cache=perp_cache,
                    sleeve=sleeve,
                )
                runs[f"BHVT-spot/{mode}"] = _run(
                    spot,
                    BH_VT,
                    spot_cost(cost),
                    window,
                    filters=sf,
                    market="spot",
                    cache=spot_cache,
                    sleeve=sleeve,
                )
            block[period_name] = {
                "window": [window[0].isoformat(), window[1].isoformat()],
                "runs": runs,
                "ma200_flips": _flips(perp, *window),
            }
        primary = block["primary"]["runs"]
        block["criteria_vs_spot"] = _criteria(
            primary["MA200-perp/constrained"], primary["BHVT-spot/constrained"]
        )
        block["criteria_vs_perp_reference"] = _criteria(
            primary["MA200-perp/constrained"], primary["BHVT-perp/constrained"]
        )
        h4 = walk_forward(perp, cost, sleeve=sleeve, filters=perp_filters, cache=perp_cache)
        block["h4_walk_forward_constrained_corrected"] = h4["summary"]
        costs[cost.name] = block
    passed = all(all(costs[c]["criteria_vs_spot"].values()) for c in costs)
    result = {
        "schema_version": 1,
        "generated_at": generated_at
        or datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "plan": "docs/PHASE2C_MA200_COMPARISON.md",
        "decision": "OBSERVE_ELIGIBLE" if passed else "PAUSE_RESEARCH",
        "criteria": CRITERIA,
        "sleeve": sleeve,
        "plan_departure": None
        if sleeve == Phase2cConfig().sleeve
        else "Decision 0018: sleeve chosen by the user after the 500 USDT result",
        "spot_fee_bps": SPOT_FEE_BPS,
        "costs": costs,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    _write(
        output_dir / "results.json",
        json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False, default=str) + "\n",
    )
    _write(output_dir / "REPORT.md", render_report(result))
    return result


def render_report(result: dict[str, Any]) -> str:
    lines = [
        "# Phase 2c follow-up — fixed MA200 comparison",
        "",
        f"- generated_at: `{result['generated_at']}`",
        f"- plan: `{result['plan']}` (diagnosis on already-seen data; never a promotion basis)",
        f"- decision: **{result['decision']}**",
        *(
            [f"- **plan departure:** {result['plan_departure']}"]
            if result.get("plan_departure")
            else []
        ),
        f"- sleeve {result['sleeve']:.0f} USDT, half per asset, at most 1x; spot taker fee "
        f"{result['spot_fee_bps']:.0f} bps, perpetual taker fee 5 bps",
        "",
    ]
    for cost in ("normal", "stress"):
        block = result["costs"][cost]
        for period in ("primary", "reference"):
            p = block[period]
            title = "judged" if period == "primary" else "reference only"
            lines += [
                f"## {cost} cost — {p['window'][0][:10]} → {p['window'][1][:10]} ({title})",
                "",
                "| Strategy | Mode | Net USDT | Ann. return | Sharpe | MDD | Return/MDD | Worst year | "
                "Price | Funding | Fees | Slippage | Orders/yr | Skipped/attempts |",
                "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
            ]
            for name, s in p["runs"].items():
                strategy, mode = name.split("/")
                d, m = s["decomposition"], s["metrics"]
                lines.append(
                    f"| {strategy} | {mode} | {d['total_pnl']:.2f} | {s['annualized_return']:.2%} | "
                    f"{m['sharpe']:.2f} | {m['max_drawdown']:.2%} | {s['return_over_mdd']:.2f} | "
                    f"{s['worst_year_pnl']:.2f} | {d['price_pnl']:.2f} | {d['funding_pnl']:.2f} | "
                    f"{d['fees']:.2f} | {d['slippage']:.2f} | {s['orders_per_year']:.1f} | "
                    f"{s['rounding_skips']}/{s['order_attempts']} |"
                )
            flips = p["ma200_flips"]
            lines += ["", f"MA200 direction changes: BTC {flips['BTC']}, ETH {flips['ETH']}.", ""]
            if period == "primary":
                by_year = {
                    name: s["pnl_by_year"]
                    for name, s in p["runs"].items()
                    if name.endswith("constrained")
                }
                years = sorted({y for v in by_year.values() for y in v})
                lines += [
                    "| Constrained P&L by year | " + " | ".join(years) + " |",
                    "|---|" + "---:|" * len(years),
                ]
                for name, values in by_year.items():
                    lines.append(
                        f"| {name.split('/')[0]} | "
                        + " | ".join(f"{values.get(y, 0.0):.2f}" for y in years)
                        + " |"
                    )
                lines.append("")
        crit = block["criteria_vs_spot"]
        ref = block["criteria_vs_perp_reference"]
        h4 = block["h4_walk_forward_constrained_corrected"]
        lines += [
            f"**Criteria ({cost}, MA200-perp vs BHVT-spot, constrained):** "
            + ", ".join(f"{k} {'PASS' if v else 'FAIL'}" for k, v in crit.items()),
            "",
            "Reference against BHVT-perp: "
            + ", ".join(f"{k} {'PASS' if v else 'FAIL'}" for k, v in ref.items()),
            "",
            f"Phase 2c H4 walk-forward, constrained with the corrected order rule (gate 8 reference): "
            f"net {h4['decomposition']['total_pnl']:.2f} USDT, Sharpe {h4['metrics']['sharpe']:.2f}, "
            f"MDD {h4['metrics']['max_drawdown']:.2%}.",
            "",
        ]
    lines += [
        "## Interpretation",
        "",
        "OBSERVE_ELIGIBLE means only that an order-free forward observation of the fixed MA200 may "
        "be registered; it is not evidence of an edge, because MA200 was singled out after the "
        "Phase 2c results. PAUSE_RESEARCH means the drawdown advantage does not survive the spot "
        "comparison or the exchange constraints. Constrained mode applies the 2026-10 filters to "
        "past prices; the end-of-window close ignores the filters.",
        "",
    ]
    return "\n".join(lines)
