#!/usr/bin/env python3
"""Trace the Phase 2b H3 episodes leg by leg (diagnosis only, no new test).

Re-runs the recorded Stage A fold that traded, checks that the replay matches
research_results/phase2b/results.json exactly, and decomposes the episodes:
legs, expected versus realized funding, price P&L by symbol and side, timing,
long/short imbalance, the effect of the minimum-hold lock, and the stop.
Writes research_results/phase2b/episode-trace.json and EPISODE_TRACE.md.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from v3.phase2.maker import (  # noqa: E402
    H3_NORMAL,
    H3_STRESS,
    h3_grid,
    load_maker_panel,
    simulate_maker_basket,  # noqa: E402
)
from v3.phase2.research_2b import EXIT_EXTENSION_DAYS, STAGE_A_FOLDS  # noqa: E402


def _ts(value) -> str:
    return pd.Timestamp(value).isoformat()


def build_legs(trace, rule_k):
    """Reconstruct legs (open to flat per symbol) from trade and funding events."""
    open_legs: dict[str, dict] = {}
    legs = []
    decisions = {e["t"]: e for e in trace if e["type"] == "decision"}
    for event in trace:
        if event["type"] == "trade":
            symbol = event["symbol"]
            delta = event["qty_after"] - event["qty_before"]
            if event["qty_before"] == 0.0:
                decision = decisions.get(event["decided_at"], {})
                score = decision.get("scores", {}).get(symbol)
                open_legs[symbol] = {
                    "symbol": symbol,
                    "side": "short" if event["qty_after"] < 0 else "long",
                    "decided_at": event["decided_at"],
                    "entry_time": event["t"],
                    "entry_price": event["price"],
                    "entry_notional": abs(event["qty_after"]) * event["price"],
                    "entry_label": event["label"],
                    "entry_score_bp": None if score is None else score * 1e4,
                    "cash_flow": 0.0,
                    "costs": 0.0,
                    "funding": 0.0,
                    "settlements": 0,
                    "expected_funding": 0.0,
                    "rebalances": 0,
                }
            leg = open_legs[symbol]
            leg["cash_flow"] -= delta * event["price"]
            leg["costs"] += event["fee"] + event["slippage"]
            if event["qty_before"] != 0.0 and event["qty_after"] != 0.0:
                leg["rebalances"] += 1
            if event["qty_after"] == 0.0:
                leg.update(
                    exit_time=event["t"],
                    exit_price=event["price"],
                    exit_label=event["label"],
                    price_pnl=leg.pop("cash_flow"),
                )
                leg["hours_held"] = int(
                    (
                        pd.Timestamp(leg["exit_time"]) - pd.Timestamp(leg["entry_time"])
                    ).total_seconds()
                    // 3600
                )
                leg["net_pnl"] = leg["price_pnl"] + leg["funding"] - leg["costs"]
                leg["underlying_return"] = leg["exit_price"] / leg["entry_price"] - 1
                legs.append(open_legs.pop(symbol))
        elif event["type"] == "funding" and event["symbol"] in open_legs:
            leg = open_legs[event["symbol"]]
            leg["funding"] += event["paid"]
            leg["settlements"] += 1
            if leg["entry_score_bp"] is not None:
                notional = abs(event["qty"]) * event["mark"]
                sign = 1.0 if leg["side"] == "short" else -1.0
                leg["expected_funding"] += sign * notional * leg["entry_score_bp"] / 1e4
    if open_legs:
        raise ValueError(f"legs still open at the end of the replay: {sorted(open_legs)}")
    for leg in legs:
        for key in ("decided_at", "entry_time", "exit_time"):
            leg[key] = _ts(leg[key])
    return legs


def hourly_frame(trace):
    rows = []
    for event in (e for e in trace if e["type"] == "hour"):
        long_notional = sum(q * event["open"][s] for s, q in event["qty"].items() if q > 0)
        short_notional = -sum(q * event["open"][s] for s, q in event["qty"].items() if q < 0)
        rows.append(
            {
                "t": event["t"],
                "equity": event["equity"],
                "qty": event["qty"],
                "open": event["open"],
                "long_legs": sum(1 for q in event["qty"].values() if q > 0),
                "short_legs": sum(1 for q in event["qty"].values() if q < 0),
                "long_notional": long_notional,
                "short_notional": short_notional,
            }
        )
    frame = pd.DataFrame(rows).set_index("t")
    # Price P&L earned between consecutive hours by the positions held over them.
    price_step = [0.0]
    for (_, prev), (_, cur) in zip(
        frame.iloc[:-1].iterrows(), frame.iloc[1:].iterrows(), strict=True
    ):
        step = sum(q * (cur["open"][s] - prev["open"][s]) for s, q in prev["qty"].items())
        price_step.append(step)
    frame["price_step"] = price_step
    return frame


def analyse(panel, trace, result, rule):
    legs = build_legs(trace, rule.k)
    hours = hourly_frame(trace)
    decisions = [e for e in trace if e["type"] == "decision"]
    stops = [e for e in trace if e["type"] == "stop"]
    universe_open = panel.base.open
    episodes = []
    for number, episode in enumerate(result.episodes, start=1):
        start, end = pd.Timestamp(episode["start"]), pd.Timestamp(episode["end"])
        ep_legs = [leg for leg in legs if start <= pd.Timestamp(leg["entry_time"]) <= end]
        window = hours.loc[(hours.index >= start) & (hours.index <= end)]
        cumulative = window["price_step"].cumsum()
        first = window.index[0]

        def at(delta, cumulative=cumulative, first=first):
            sub = cumulative[cumulative.index <= first + delta]
            return float(sub.iloc[-1]) if len(sub) else 0.0

        unequal = window[window["long_legs"] != window["short_legs"]]
        imbalance = window["long_notional"] - window["short_notional"]
        u0, u1 = universe_open.loc[start], universe_open.loc[end]
        # Beta of each leg to BTC over the 30 days before entry (hourly open-to-open).
        history = universe_open.loc[start - pd.Timedelta(days=30) : start].pct_change().dropna()
        betas = {
            sym: float(history[sym].cov(history["BTC"]) / history["BTC"].var())
            for sym in panel.base.symbols
        }
        net_beta_notional = sum(
            (1 if leg["side"] == "long" else -1) * leg["entry_notional"] * betas[leg["symbol"]]
            for leg in ep_legs
        )
        by_side = {
            side: {
                "price_pnl": sum(leg["price_pnl"] for leg in ep_legs if leg["side"] == side),
                "funding": sum(leg["funding"] for leg in ep_legs if leg["side"] == side),
                "legs": [leg["symbol"] for leg in ep_legs if leg["side"] == side],
            }
            for side in ("short", "long")
        }
        episodes.append(
            {
                "episode": number,
                "start": episode["start"],
                "end": episode["end"],
                "hours": episode["hours"],
                "pnl_usdt": episode["pnl_usdt"],
                "legs": ep_legs,
                "by_side": by_side,
                "price_pnl_path": {
                    "after_24h": at(pd.Timedelta(hours=24)),
                    "after_5d": at(pd.Timedelta(days=5)),
                    "minimum": float(cumulative.min()),
                    "minimum_at": _ts(cumulative.idxmin()),
                    "end": float(cumulative.iloc[-1]),
                },
                "imbalance": {
                    "hours": int(len(window)),
                    "hours_unequal_leg_counts": int(len(unequal)),
                    "price_pnl_while_unequal": float(unequal["price_step"].sum()),
                    "max_abs_net_notional": float(imbalance.abs().max()),
                    "mean_net_notional": float(imbalance.mean()),
                },
                "entry_betas_to_btc": {leg["symbol"]: betas[leg["symbol"]] for leg in ep_legs},
                "net_beta_notional_usdt": net_beta_notional,
                "market": {
                    "equal_weight_universe_return": float((u1 / u0 - 1).mean()),
                    "btc_return": float(u1["BTC"] / u0["BTC"] - 1),
                    "symbol_returns": {s: float(u1[s] / u0[s] - 1) for s in panel.base.symbols},
                },
            }
        )
    # Minimum-hold lock: a held leg the ranking would have replaced but the lock kept.
    lock_effects = []
    seen = set()
    for decision in decisions:
        for side in ("shorts", "longs"):
            for symbol in decision["locked"][side]:
                if symbol in decision["ranked"][side] or (symbol, side) in seen:
                    continue
                leg = next(
                    (
                        leg
                        for leg in legs
                        if leg["symbol"] == symbol
                        and pd.Timestamp(leg["entry_time"])
                        <= pd.Timestamp(decision["t"])
                        <= pd.Timestamp(leg["exit_time"])
                    ),
                    None,
                )
                if leg is None:
                    continue
                seen.add((symbol, side))
                t0 = pd.Timestamp(decision["t"])
                unlock = pd.Timestamp(leg["decided_at"]) + pd.Timedelta(days=rule.min_hold_days)
                # Only the locked period: at the unlock decision the ranking decides again,
                # and an exit then executes at the next hour.
                t1 = min(pd.Timestamp(leg["exit_time"]), unlock + pd.Timedelta(hours=1))
                window = hours.loc[(hours.index > t0) & (hours.index <= t1)]
                qty_path = [
                    row["qty"].get(symbol, 0.0) for _, row in hours.loc[window.index].iterrows()
                ]
                previous_rows = hours.loc[(hours.index >= t0) & (hours.index < t1)]
                pnl = sum(
                    prev["qty"].get(symbol, 0.0) * (cur["open"][symbol] - prev["open"][symbol])
                    for (_, prev), (_, cur) in zip(
                        previous_rows.iterrows(), window.iterrows(), strict=False
                    )
                )
                funding = sum(
                    e["paid"]
                    for e in trace
                    if e["type"] == "funding"
                    and e["symbol"] == symbol
                    and t0 < pd.Timestamp(e["t"]) <= t1
                )
                lock_effects.append(
                    {
                        "symbol": symbol,
                        "side": side[:-1],
                        "first_kept_by_lock": _ts(t0),
                        "exit_time": leg["exit_time"],
                        "lock_window_end": _ts(t1),
                        "price_pnl_after_lock": pnl,
                        "funding_after_lock": funding,
                        "held_hours_after_lock": len(qty_path),
                    }
                )
    blocked = [
        {
            "t": _ts(d["t"]),
            "spread_bp": None if d["spread"] is None else d["spread"] * 1e4,
            "held_after": d["final"],
        }
        for d in decisions
        if not d["entries_allowed"] and (d["final"]["shorts"] or d["final"]["longs"])
    ]
    return {
        "legs": legs,
        "episodes": episodes,
        "lock_effects": lock_effects,
        "blocked_decisions_while_holding": blocked,
        "stops": [
            {"t": _ts(s["t"]), "equity": s["equity"], "day_start": s["day_start"]} for s in stops
        ],
        "totals": {
            "price_pnl_legs": sum(leg["price_pnl"] for leg in legs),
            "funding_legs": sum(leg["funding"] for leg in legs),
            "expected_funding_legs": sum(leg["expected_funding"] for leg in legs),
            "costs_legs": sum(leg["costs"] for leg in legs),
        },
    }


def render(report) -> str:
    lines = [
        "# Phase 2b H3 episode trace",
        "",
        f"- source: Stage A fold {report['fold']} validation, rule `{report['rule']}`, "
        f"cost `{report['cost']}`",
        f"- replay matches recorded fold decomposition: **{report['replay_matches']}**",
        "",
    ]
    t = report["analysis"]["totals"]
    lines += [
        "## Totals over the traced legs (USDT)",
        "",
        "| Price P&L | Funding realized | Funding expected at entry | Costs | Net |",
        "|---:|---:|---:|---:|---:|",
        f"| {t['price_pnl_legs']:.3f} | {t['funding_legs']:.3f} | {t['expected_funding_legs']:.3f} | "
        f"{t['costs_legs']:.3f} | "
        f"{t['price_pnl_legs'] + t['funding_legs'] - t['costs_legs']:.3f} |",
        "",
    ]
    for ep in report["analysis"]["episodes"]:
        lines += [
            f"## Episode {ep['episode']}: {ep['start'][:16]} → {ep['end'][:16]} ({ep['hours']} h)",
            "",
            f"Net over its legs {sum(leg['net_pnl'] for leg in ep['legs']):.3f} USDT "
            f"(equity change from the first held hour, which excludes entry costs: "
            f"{ep['pnl_usdt']:.3f}).",
            "",
            "| Leg | Side | Entry | Exit | Exit by | Score at entry (bp) | Underlying | Price P&L | "
            "Funding exp. | Funding real. | Costs | Net |",
            "|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
        for leg in ep["legs"]:
            lines.append(
                f"| {leg['symbol']} | {leg['side']} | {leg['entry_time'][5:16]} | "
                f"{leg['exit_time'][5:16]} | {leg['exit_label']} | "
                f"{leg['entry_score_bp']:.2f} | {leg['underlying_return']:+.2%} | "
                f"{leg['price_pnl']:.3f} | {leg['expected_funding']:.3f} | {leg['funding']:.3f} | "
                f"{leg['costs']:.3f} | {leg['net_pnl']:.3f} |"
            )
        side = ep["by_side"]
        path = ep["price_pnl_path"]
        imb = ep["imbalance"]
        market = ep["market"]
        lines += [
            "",
            f"- Short basket {side['short']['legs']}: price {side['short']['price_pnl']:.3f}, "
            f"funding {side['short']['funding']:.3f}. Long basket {side['long']['legs']}: "
            f"price {side['long']['price_pnl']:.3f}, funding {side['long']['funding']:.3f}.",
            f"- Price P&L path: after 24 h {path['after_24h']:.3f}, after 5 days "
            f"{path['after_5d']:.3f}, low {path['minimum']:.3f} at {path['minimum_at'][5:16]}, "
            f"end {path['end']:.3f}.",
            f"- Leg counts unequal for {imb['hours_unequal_leg_counts']} of {imb['hours']} hours "
            f"(price P&L in those hours {imb['price_pnl_while_unequal']:.3f}); max |long − short| "
            f"notional {imb['max_abs_net_notional']:.1f} USDT, mean {imb['mean_net_notional']:.1f}.",
            "- 30-day beta to BTC at entry: "
            + ", ".join(f"{k} {v:.2f}" for k, v in ep["entry_betas_to_btc"].items())
            + f". Net beta-weighted notional (long − short) {ep['net_beta_notional_usdt']:+.1f} USDT.",
            f"- Market over the episode: equal-weight universe "
            f"{market['equal_weight_universe_return']:+.2%}, BTC {market['btc_return']:+.2%}.",
            "",
        ]
    lines += ["## Minimum-hold lock", ""]
    effects = report["analysis"]["lock_effects"]
    if effects:
        lines += [
            "| Leg | Side | Kept by lock from | Lock ends | Final exit | Price P&L while locked | "
            "Funding while locked |",
            "|---|---|---|---|---|---:|---:|",
        ]
        for e in effects:
            lines.append(
                f"| {e['symbol']} | {e['side']} | {e['first_kept_by_lock'][5:16]} | "
                f"{e['lock_window_end'][5:16]} | {e['exit_time'][5:16]} | "
                f"{e['price_pnl_after_lock']:.3f} | "
                f"{e['funding_after_lock']:.3f} |"
            )
    else:
        lines.append("No leg was kept by the lock against the ranking.")
    lines += ["", "## Blocked decisions while holding", ""]
    blocked = report["analysis"]["blocked_decisions_while_holding"]
    if blocked:
        lines += ["| Decision | Spread (bp) | Held after |", "|---|---:|---|"]
        for b in blocked:
            spread = "n/a" if b["spread_bp"] is None else f"{b['spread_bp']:.2f}"
            lines.append(
                f"| {b['t'][5:16]} | {spread} | short {b['held_after']['shorts']} / "
                f"long {b['held_after']['longs']} |"
            )
    else:
        lines.append("None.")
    lines += ["", "## Daily stop", ""]
    stops = report["analysis"]["stops"]
    lines += (
        [
            f"- {s['t'][:16]}: equity {s['equity']:.3f} vs day start {s['day_start']:.3f}"
            for s in stops
        ]
        if stops
        else ["None."]
    )
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-dir", type=Path, default=Path("user_data/data-phase2b/binance/futures")
    )
    parser.add_argument(
        "--manifest", type=Path, default=Path("evidence/phase2b/data-manifest.json")
    )
    parser.add_argument(
        "--results", type=Path, default=Path("research_results/phase2b/results.json")
    )
    parser.add_argument("--output", type=Path, default=Path("research_results/phase2b"))
    parser.add_argument("--cost", choices=("normal", "stress"), default="normal")
    args = parser.parse_args()
    recorded = json.loads(args.results.read_text())
    stage_a = recorded["hypotheses"]["H3"][args.cost]["stage_a"]
    traded = [row for row in stage_a["folds"] if row["episodes"]]
    if len(traded) != 1:
        raise SystemExit(f"expected exactly one fold with episodes, found {len(traded)}")
    fold_row = traded[0]
    rule = next(r for r in h3_grid("H3") if r.label() == fold_row["selected"])
    train_start, train_end, validation_start, validation_end = STAGE_A_FOLDS[fold_row["fold"]]
    start = pd.Timestamp(validation_start, tz="UTC")
    entry_end = pd.Timestamp(validation_end, tz="UTC")
    end = entry_end + pd.Timedelta(days=EXIT_EXTENSION_DAYS)
    panel = load_maker_panel(args.data_dir, manifest_path=args.manifest)
    trace: list[dict] = []
    execution = H3_NORMAL if args.cost == "normal" else H3_STRESS
    result = simulate_maker_basket(
        panel, rule, execution=execution, start=start, end=end, entry_end=entry_end, trace=trace
    )
    matches = all(
        abs(result.decomposition[key] - value) < 1e-9
        for key, value in fold_row["decomposition"].items()
    )
    if not matches:
        raise SystemExit("replay does not match the recorded fold decomposition")
    report = {
        "schema_version": 1,
        "fold": fold_row["fold"],
        "rule": rule.label(),
        "cost": args.cost,
        "window": [start.isoformat(), end.isoformat()],
        "replay_matches": matches,
        "recorded_decomposition": fold_row["decomposition"],
        "analysis": analyse(panel, trace, result, rule),
    }
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "episode-trace.json").write_text(
        json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"
    )
    (args.output / "EPISODE_TRACE.md").write_text(render(report))
    print(f"replay_matches={matches} episodes={len(report['analysis']['episodes'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
