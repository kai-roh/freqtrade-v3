"""Phase 2c development-stage evaluation (docs/PHASE2C_PREREGISTRATION.md §5-§6)."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from v3.bootstrap import BootstrapSpec, block_bootstrap_mean
from v3.phase2.data import Phase2Panel, load_phase2_panel
from v3.phase2.pbo import probability_of_backtest_overfitting
from v3.phase2.research import SeriesMetrics, _write

from .trend import (
    CONTROLS,
    NORMAL,
    STRESS,
    SYMBOLS,
    Cost,
    TrendResult,
    TrendRule,
    VenueFilters,
    simulate_trend,
    trend_grid,
)


def _ts(value: str) -> pd.Timestamp:
    return pd.Timestamp(value, tz="UTC")


FIRST_DECISION = _ts("2020-07-01")
DATA_END = _ts("2026-10-01 23:00")
FIRST_VALIDATION = _ts("2022-08-01")
VALIDATION_DAYS = 182
EMBARGO_DAYS = 30
TRAIN_DAYS = 730
WINDOW_COUNT = 9
EVALUATION_END = _ts("2026-10-01")


@dataclass(frozen=True)
class Window:
    index: int
    train_start: pd.Timestamp
    train_end: pd.Timestamp
    validation_start: pd.Timestamp
    validation_end: pd.Timestamp


@dataclass(frozen=True)
class Phase2cConfig:
    sleeve: float = 500.0
    min_annual_return_stress: float = 0.08
    max_drawdown: float = 0.30
    min_positive_windows: int = 5
    min_positive_configs: int = 4
    pbo_max: float = 0.20
    pbo_partitions: int = 16
    bootstrap_block: int = 20
    bootstrap_iterations: int = 10_000
    bootstrap_seed: int = 20261002
    # True reproduces the recorded run, whose constrained mode checked the holding
    # against the minimum notional; the exchange checks the order delta.
    legacy_holding_min_notional: bool = False


def windows() -> tuple[Window, ...]:
    out = []
    start = FIRST_VALIDATION
    for i in range(WINDOW_COUNT):
        end = min(start + pd.Timedelta(days=VALIDATION_DAYS), EVALUATION_END)
        train_end = start - pd.Timedelta(days=EMBARGO_DAYS)
        out.append(Window(i, train_end - pd.Timedelta(days=TRAIN_DAYS), train_end, start, end))
        start = start + pd.Timedelta(days=VALIDATION_DAYS)
    if out[-1].validation_end != EVALUATION_END:
        raise ValueError("windows must end at the registered evaluation end")
    if out[0].train_start < FIRST_DECISION:
        raise ValueError("first training window starts before warm-up ends")
    return tuple(out)


def load_venue_filters(path: Path, *, legacy: bool = False) -> VenueFilters:
    """USD-M perpetual filters from evidence/phase2b/implementability.json."""
    raw = json.loads(path.read_text())["raw_filters"]
    return VenueFilters(
        step={s: float(raw[f"{s}USDT"]["LOT_SIZE.stepSize"]) for s in SYMBOLS},
        min_notional={s: float(raw[f"{s}USDT"]["MIN_NOTIONAL"]) for s in SYMBOLS},
        reduce_only_exempt=True,
        legacy_holding_rule=legacy,
    )


def load_spot_filters(path: Path) -> VenueFilters:
    """Spot filters from evidence/phase2c/spot-filters-20261002.json (no reduce-only)."""
    raw = json.loads(path.read_text())["symbols"]
    return VenueFilters(
        step={s: float(raw[f"{s}USDT"]["LOT_SIZE.stepSize"]) for s in SYMBOLS},
        min_notional={s: float(raw[f"{s}USDT"]["minNotional"]) for s in SYMBOLS},
        reduce_only_exempt=False,
    )


def _annualized(metrics: SeriesMetrics) -> float:
    if metrics.days == 0:
        return 0.0
    return (1.0 + metrics.total_return) ** (365.0 / metrics.days) - 1.0


def _summary(result: TrendResult) -> dict[str, Any]:
    metrics = SeriesMetrics.from_returns(result.daily_returns)
    by_year = result.daily_pnl.groupby(result.daily_pnl.index.year).sum()
    return {
        "label": result.label,
        "cost": result.cost,
        "metrics": metrics.to_dict(),
        "annualized_return": _annualized(metrics),
        "decomposition": result.decomposition,
        "long_short": result.long_short,
        "per_symbol": result.per_symbol,
        "trades": result.trades,
        "traded_notional": result.traded_notional,
        "annual_turnover_x_sleeve": result.traded_notional
        / float(result.equity.iloc[0])
        * 365.0
        / max(metrics.days, 1),
        "time_in_market": result.time_in_market,
        "episodes": len(result.episodes),
        "episodes_by_symbol": {
            s: sum(1 for e in result.episodes if e["symbol"] == s) for s in SYMBOLS
        },
        "best_episode_pnl": max((e["pnl"] for e in result.episodes), default=0.0),
        "pnl_by_year": {str(k): float(v) for k, v in by_year.items()},
        "rounding_skips": result.rounding_skips,
    }


def _select(
    panel, grid, cost, window, *, sleeve, filters, cache
) -> tuple[TrendRule, list[dict[str, Any]]]:
    scored = []
    for rule in grid:
        result = simulate_trend(
            panel,
            [(window.train_start, rule)],
            cost=cost,
            start=window.train_start,
            end=window.train_end,
            sleeve=sleeve,
            filters=filters,
            weights_cache=cache,
        )
        metrics = SeriesMetrics.from_returns(result.daily_returns)
        scored.append((metrics.sharpe, -result.traded_notional, rule, metrics))
    scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
    table = [
        {"rule": r.label(), "train_sharpe": s, "train_total_return": m.total_return}
        for s, _, r, m in scored
    ]
    return scored[0][2], table


def walk_forward(
    panel: Phase2Panel,
    cost: Cost,
    *,
    sleeve: float,
    filters: VenueFilters | None,
    cache: dict,
) -> dict[str, Any]:
    grid = trend_grid()
    schedule, selections = [], []
    for window in windows():
        rule, table = _select(
            panel, grid, cost, window, sleeve=sleeve, filters=filters, cache=cache
        )
        schedule.append((window.validation_start, rule))
        selections.append(
            {
                "window": window.index,
                "train": [window.train_start.isoformat(), window.train_end.isoformat()],
                "validation": [
                    window.validation_start.isoformat(),
                    window.validation_end.isoformat(),
                ],
                "selected": rule.label(),
                "training_table": table,
            }
        )
    result = simulate_trend(
        panel,
        schedule,
        cost=cost,
        start=FIRST_VALIDATION,
        end=DATA_END,
        sleeve=sleeve,
        filters=filters,
        weights_cache=cache,
    )
    window_pnl = []
    all_windows = windows()
    for window in all_windows:
        # daily_pnl at day d is the equity change from d-1 00:00 to d 00:00. The last
        # window also takes the final day, which ends with the flattening trade.
        last = window.validation_end + (
            pd.Timedelta(days=1) if window is all_windows[-1] else pd.Timedelta(0)
        )
        pnl = result.daily_pnl[
            (result.daily_pnl.index > window.validation_start) & (result.daily_pnl.index <= last)
        ].sum()
        window_pnl.append(float(pnl))
    for row, pnl in zip(selections, window_pnl, strict=True):
        row["validation_pnl"] = pnl
    return {"result": result, "summary": _summary(result), "selections": selections}


def evaluate(panel: Phase2Panel, *, filters: VenueFilters, config: Phase2cConfig) -> dict[str, Any]:
    cache: dict = {}
    out: dict[str, Any] = {"costs": {}}
    for cost in (NORMAL, STRESS):
        wf = walk_forward(panel, cost, sleeve=config.sleeve, filters=None, cache=cache)
        wf_constrained = walk_forward(
            panel, cost, sleeve=config.sleeve, filters=filters, cache=cache
        )
        controls = {
            rule.label(): _summary(
                simulate_trend(
                    panel,
                    [(FIRST_VALIDATION, rule)],
                    cost=cost,
                    start=FIRST_VALIDATION,
                    end=DATA_END,
                    sleeve=config.sleeve,
                    weights_cache=cache,
                )
            )
            for rule in CONTROLS
        }
        full = [
            simulate_trend(
                panel,
                [(FIRST_DECISION, rule)],
                cost=cost,
                start=FIRST_DECISION,
                end=DATA_END,
                sleeve=config.sleeve,
                weights_cache=cache,
            )
            for rule in trend_grid()
        ]
        matrix = pd.concat(
            [
                r.daily_returns.rename(rule.label())
                for r, rule in zip(full, trend_grid(), strict=True)
            ],
            axis=1,
        ).fillna(0.0)
        pbo = probability_of_backtest_overfitting(matrix, partitions=config.pbo_partitions)
        bootstrap = block_bootstrap_mean(
            wf["result"].daily_returns,
            BootstrapSpec(
                "daily_portfolio_pnl",
                config.bootstrap_block,
                config.bootstrap_iterations,
                config.bootstrap_seed,
            ),
        )
        s = wf["summary"]
        m = s["metrics"]
        bh = controls["BH-VT"]
        daily = wf["result"].daily_pnl
        by_year = daily.groupby(daily.index.year).sum()
        total = float(daily.sum())
        gates = {
            "net_positive": s["decomposition"]["total_pnl"] > 0,
            "max_drawdown": m["max_drawdown"] <= config.max_drawdown,
            "beats_bh_vt_sharpe": m["sharpe"] >= bh["metrics"]["sharpe"],
            "beats_bh_vt_drawdown": m["max_drawdown"] <= bh["metrics"]["max_drawdown"],
            "constrained_net_positive": wf_constrained["summary"]["decomposition"]["total_pnl"] > 0,
        }
        if cost is STRESS:
            gates["annual_return_stress"] = (
                s["annualized_return"] >= config.min_annual_return_stress
            )
        if cost is NORMAL:
            gates["positive_windows"] = (
                sum(1 for row in wf["selections"] if row["validation_pnl"] > 0)
                >= config.min_positive_windows
            )
            gates["positive_configs"] = (
                sum(1 for r in full if r.decomposition["total_pnl"] > 0)
                >= config.min_positive_configs
            )
            gates["without_best_year"] = total - float(by_year.max()) >= 0
            gates["without_best_episode"] = total - s["best_episode_pnl"] >= 0
            gates["pbo"] = pbo["pbo"] <= config.pbo_max
        gates = {name: bool(value) for name, value in gates.items()}
        out["costs"][cost.name] = {
            "walk_forward": s,
            "selections": wf["selections"],
            "walk_forward_constrained": wf_constrained["summary"],
            "controls": controls,
            "full_period_configs": [_summary(r) for r in full],
            "pbo": pbo,
            "bootstrap": bootstrap.to_dict(),
            "gates": gates,
            "passed": all(gates.values()),
        }
    passed = all(block["passed"] for block in out["costs"].values())
    ci_positive = out["costs"]["normal"]["bootstrap"]["ci_low"] > 0
    if not passed:
        decision = "STOP_NO_EDGE"
    elif ci_positive:
        decision = "PASS_DEV"
    else:
        decision = "INCONCLUSIVE_DEV"
    out["decision"] = decision
    return out


def run_phase2c_research(
    data_dir: Path,
    output_dir: Path,
    *,
    manifest_path: Path,
    filters_path: Path,
    config: Phase2cConfig | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    config = config or Phase2cConfig()
    panel = load_phase2_panel(data_dir, manifest_path=manifest_path, symbols=SYMBOLS)
    if panel.open.index[-1] != DATA_END:
        raise ValueError("panel must end at the registered cutoff")
    filters = load_venue_filters(filters_path, legacy=config.legacy_holding_min_notional)
    evaluation = evaluate(panel, filters=filters, config=config)
    result = {
        "schema_version": 1,
        "generated_at": generated_at
        or datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "registration": "docs/PHASE2C_PREREGISTRATION.md",
        "decision": evaluation["decision"],
        "config": asdict(config),
        "panel": {
            "start": panel.open.index[0].isoformat(),
            "end": panel.open.index[-1].isoformat(),
            "hours": int(len(panel.open)),
            "settlements": int(len(panel.funding)),
        },
        "windows": [
            {
                "window": w.index,
                "train": [w.train_start.isoformat(), w.train_end.isoformat()],
                "validation": [w.validation_start.isoformat(), w.validation_end.isoformat()],
            }
            for w in windows()
        ],
        "evaluation": evaluation,
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


def render_report(result: dict[str, Any]) -> str:
    ev = result["evaluation"]
    lines = [
        "# Phase 2c Research Report — BTC/ETH low-frequency trend",
        "",
        f"- generated_at: `{result['generated_at']}`",
        f"- decision: **{ev['decision']}**",
        f"- registration: `{result['registration']}`",
        f"- panel: {result['panel']['start'][:10]} → {result['panel']['end'][:16]} "
        "(all development data; confirmation only on data after 2026-10-02)",
        f"- sleeve: {result['config']['sleeve']:.0f} USDT, half per asset, at most 1x",
        "",
        "## Walk-forward continuous account (2022-08-01 → 2026-10-01)",
        "",
        "| Cost | Mode | Net USDT | Ann. return | Sharpe | PF | MDD | Price | Funding | Fees | "
        "Slippage | Long price | Short price | Trades | Turnover x/yr |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for cost in ("normal", "stress"):
        for mode, key in (("ideal", "walk_forward"), ("constrained", "walk_forward_constrained")):
            s = ev["costs"][cost][key]
            m, d, ls = s["metrics"], s["decomposition"], s["long_short"]
            lines.append(
                f"| {cost} | {mode} | {d['total_pnl']:.2f} | {s['annualized_return']:.2%} | "
                f"{m['sharpe']:.2f} | {_pf(m['profit_factor'])} | {m['max_drawdown']:.2%} | "
                f"{d['price_pnl']:.2f} | {d['funding_pnl']:.2f} | {d['fees']:.2f} | "
                f"{d['slippage']:.2f} | {ls['long_price_pnl']:.2f} | {ls['short_price_pnl']:.2f} | "
                f"{s['trades']} | {s['annual_turnover_x_sleeve']:.1f} |"
            )
    lines += [
        "",
        "## Controls over the same period",
        "",
        "| Cost | Strategy | Net USDT | Ann. return | Sharpe | MDD | Time in market BTC/ETH |",
        "|---|---|---:|---:|---:|---:|---|",
    ]
    for cost in ("normal", "stress"):
        rows = {"H4 walk-forward": ev["costs"][cost]["walk_forward"]} | ev["costs"][cost][
            "controls"
        ]
        for name, s in rows.items():
            tim = s["time_in_market"]
            lines.append(
                f"| {cost} | {name} | {s['decomposition']['total_pnl']:.2f} | "
                f"{s['annualized_return']:.2%} | {s['metrics']['sharpe']:.2f} | "
                f"{s['metrics']['max_drawdown']:.2%} | {tim['BTC']:.0%} / {tim['ETH']:.0%} |"
            )
    lines += ["", "## Gates", ""]
    for cost in ("normal", "stress"):
        block = ev["costs"][cost]
        lines.append(
            f"- **{cost}**: "
            + ", ".join(f"{name} {'PASS' if ok else 'FAIL'}" for name, ok in block["gates"].items())
        )
    normal = ev["costs"]["normal"]
    boot = normal["bootstrap"]
    lines += [
        f"- PBO (normal): {normal['pbo']['pbo']:.2f} over {normal['pbo']['strategies']} configurations",
        f"- Block bootstrap of daily net returns (normal, 20-day blocks): mean "
        f"{boot['observed_mean']:.5f}, 95% CI [{boot['ci_low']:.5f}, {boot['ci_high']:.5f}]",
        "",
        "## Window selections (normal cost)",
        "",
        "| Window | Validation | Selected on training | Validation P&L |",
        "|---:|---|---|---:|",
    ]
    for row in normal["selections"]:
        lines.append(
            f"| {row['window']} | {row['validation'][0][:10]} → {row['validation'][1][:10]} | "
            f"{row['selected']} | {row['validation_pnl']:.2f} |"
        )
    lines += [
        "",
        "## Full-period configurations (2020-07-01 → 2026-10-01, normal cost)",
        "",
        "| Configuration | Net USDT | Ann. return | Sharpe | MDD | Episodes BTC/ETH |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for s in normal["full_period_configs"]:
        e = s["episodes_by_symbol"]
        lines.append(
            f"| {s['label']} | {s['decomposition']['total_pnl']:.2f} | {s['annualized_return']:.2%} | "
            f"{s['metrics']['sharpe']:.2f} | {s['metrics']['max_drawdown']:.2%} | "
            f"{e['BTC']} / {e['ETH']} |"
        )
    wf = normal["walk_forward"]
    lines += [
        "",
        "## Walk-forward P&L by calendar year (normal cost, USDT)",
        "",
        "| " + " | ".join(wf["pnl_by_year"]) + " |",
        "|" + "---:|" * len(wf["pnl_by_year"]),
        "| " + " | ".join(f"{v:.2f}" for v in wf["pnl_by_year"].values()) + " |",
        "",
        "## Interpretation",
        "",
        "All data here is development data that had been seen before; the verdict can at most "
        "earn an order-free forward observation on data after 2026-10-02. Conviction is expressed "
        "as one net position per asset, never as simultaneous long and short. Constrained mode "
        "applies the 2026-10 lot step and minimum notional to past prices.",
        "",
    ]
    return "\n".join(lines)
