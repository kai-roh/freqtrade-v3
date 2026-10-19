#!/usr/bin/env python3
"""Phase 2d broad strategy search (docs/PHASE2D_PREREGISTRATION.md).

freeze   build the daily panels from the raw archive and record their hashes
develop  run the 120 registered configurations and benchmarks on the development
         window, compute PBO / DSR / gates, write dev results (no holdout days)
holdout  evaluate the development-gate survivors once on the holdout window
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from v3.phase2d.data import build_panel, load_panel, save_panel  # noqa: E402
from v3.phase2d.engine import Market, metrics, simulate, split_reused_symbols  # noqa: E402
from v3.phase2d.evaluate import TRIALS, daily_sharpe, deflated_sharpe, pbo_cscv  # noqa: E402
from v3.phase2d.strategies import BENCHMARKS, Config, registered_grid, weight_fn  # noqa: E402

DATA = PROJECT_ROOT / "user_data/data-phase2d"
OUT = PROJECT_ROOT / "research_results/phase2d"
UTC = "UTC"
WINDOWS = {
    "spot": (pd.Timestamp("2018-01-01", tz=UTC), pd.Timestamp("2024-12-31", tz=UTC)),
    "perp": (pd.Timestamp("2020-07-01", tz=UTC), pd.Timestamp("2024-12-31", tz=UTC)),
}
# The last archived day is 2026-09-30; its open-to-open return needs 10-01, so the
# holdout's last earned day is 09-29.
HOLDOUT = (pd.Timestamp("2025-01-01", tz=UTC), pd.Timestamp("2026-09-29", tz=UTC))


def freeze() -> None:
    hashes = {}
    for market in ("spot", "um"):
        panel = split_reused_symbols(build_panel(DATA, market))
        hashes[market] = save_panel(panel, DATA / f"panel-{market}.csv.gz")
        print(market, panel.close.shape, hashes[market])
    (DATA / "panel-hashes.json").write_text(json.dumps(hashes, indent=2) + "\n")


def markets() -> dict[str, Market]:
    return {
        "spot": Market(load_panel(DATA / "panel-spot.csv.gz"), "spot"),
        "perp": Market(load_panel(DATA / "panel-um.csv.gz"), "perp"),
    }


def run(market: Market, config: Config, start, end, cost_multiplier=1.0):
    return simulate(
        market,
        weight_fn(config, market),
        start=start,
        end=end,
        every=config.every,
        cost_multiplier=cost_multiplier,
    )


def summary(result) -> dict:
    out = metrics(result.returns)
    out.update(
        turnover=result.turnover, costs=result.costs, funding=result.funding,
        days=len(result.returns),
    )  # fmt: skip
    return out


def develop() -> None:
    m = markets()
    grid = registered_grid()
    started = time.time()
    rows, returns = [], {}
    for c in grid:
        start, end = WINDOWS[c.venue]
        res = run(m[c.venue], c, start, end)
        rows.append({**c.to_json(), "venue": c.venue, **summary(res)})
        returns[c.label()] = res.returns
    bench = {}
    for venue, (start, end) in WINDOWS.items():
        for b in BENCHMARKS:
            res = run(m["spot"], b, start, end)
            bench[f"{b.family}@{venue}"] = summary(res)
    trial_sharpes = np.array([daily_sharpe(returns[c.label()]) for c in grid])
    table = pd.DataFrame(rows).set_index("label")
    families = {}
    for fam in ("F1", "F2", "F3", "F4", "F5", "F6"):
        members = table[table.family == fam]
        best = members.sharpe.idxmax()
        c = next(x for x in grid if x.label() == best)
        venue = c.venue
        start, end = WINDOWS[venue]
        bench_best_sharpe = max(bench[f"{b.family}@{venue}"]["sharpe"] for b in BENCHMARKS)
        btc_mdd = bench[f"BTC@{venue}"]["mdd"]
        doubled = summary(run(m[venue], c, start, end, cost_multiplier=2.0))
        pbo = pbo_cscv(pd.DataFrame({lbl: returns[lbl] for lbl in members.index}))
        dsr = deflated_sharpe(returns[best], trial_sharpes, TRIALS)
        r = table.loc[best]
        gates = {
            "D1_sharpe_beats_benchmarks": bool(r.sharpe > bench_best_sharpe),
            "D2_dsr_ge_0.95": bool(dsr >= 0.95),
            "D3_pbo_le_0.30": bool(pbo <= 0.30),
            "D4_double_cost_beats_benchmarks": bool(doubled["sharpe"] > bench_best_sharpe),
            "D5_mdd_below_btc": bool(r.mdd < btc_mdd),
            "D6_majority_positive_years": bool(r.years_positive * 2 > r.years),
        }
        families[fam] = {
            "best": best,
            "config": c.to_json(),
            "dev": {k: (v if not isinstance(v, np.generic) else v.item()) for k, v in r.items()},
            "double_cost": doubled,
            "pbo": pbo,
            "dsr": dsr,
            "benchmark_best_sharpe": bench_best_sharpe,
            "btc_mdd": btc_mdd,
            "gates": gates,
            "dev_pass": all(gates.values()),
        }
    OUT.mkdir(parents=True, exist_ok=True)
    table.to_csv(OUT / "dev-all-configs.csv", float_format="%.6g")
    pd.DataFrame(returns).to_csv(OUT / "dev-daily-returns.csv.gz", float_format="%.8g")
    result = {
        "registration": "docs/PHASE2D_PREREGISTRATION.md",
        "panel_hashes": json.loads((DATA / "panel-hashes.json").read_text()),
        "windows": {k: [a.isoformat(), b.isoformat()] for k, (a, b) in WINDOWS.items()},
        "trials": len(grid),
        "benchmarks": bench,
        "families": families,
        "dev_survivors": [f for f, v in families.items() if v["dev_pass"]],
        "runtime_s": round(time.time() - started, 1),
    }
    (OUT / "dev-results.json").write_text(json.dumps(result, indent=2, default=str) + "\n")
    print(
        json.dumps(
            {
                f: {
                    "best": v["best"],
                    "sharpe": round(v["dev"]["sharpe"], 3),
                    "cagr": round(v["dev"]["cagr"], 3),
                    "mdd": round(v["dev"]["mdd"], 3),
                    "pbo": round(v["pbo"], 3),
                    "dsr": round(v["dsr"], 3),
                    "pass": v["dev_pass"],
                }
                for f, v in families.items()
            },
            indent=1,
        )
    )
    print(
        "benchmarks",
        json.dumps(
            {
                k: {
                    "sharpe": round(v["sharpe"], 3),
                    "cagr": round(v["cagr"], 3),
                    "mdd": round(v["mdd"], 3),
                }
                for k, v in bench.items()
            },
            indent=1,
        ),
    )


def holdout() -> None:
    dev_path = OUT / "dev-results.json"
    if not dev_path.is_file():
        raise SystemExit("run develop first; the holdout is evaluated only after selection")
    dev = json.loads(dev_path.read_text())
    if (OUT / "holdout-results.json").exists():
        raise SystemExit("holdout already evaluated; it is computed once")
    m = markets()
    start, end = HOLDOUT
    bench = {b.family: summary(run(m["spot"], b, start, end)) for b in BENCHMARKS}
    evaluated = {}
    for fam in dev["dev_survivors"]:
        c = Config(**{k: v for k, v in dev["families"][fam]["config"].items() if k != "label"})
        s = summary(run(m[c.venue], c, start, end))
        gates = {
            "H1_positive": s["total"] > 0,
            "H2_sharpe_ge_0.5": s["sharpe"] >= 0.5,
            "H3_sharpe_ge_btc": s["sharpe"] >= bench["BTC"]["sharpe"],
        }
        evaluated[fam] = {
            "best": dev["families"][fam]["best"],
            "holdout": s,
            "gates": gates,
            "pass": all(gates.values()),
        }
    passing = [f for f, v in evaluated.items() if v["pass"]]
    selected = max(passing, key=lambda f: dev["families"][f]["dev"]["sharpe"]) if passing else None
    result = {
        "window": [start.isoformat(), end.isoformat()],
        "benchmarks": bench,
        "evaluated": evaluated,
        "verdict": "PASS" if selected else "STOP_NO_EDGE",
        "selected": selected,
    }
    (OUT / "holdout-results.json").write_text(json.dumps(result, indent=2, default=str) + "\n")
    print(json.dumps(result, indent=1, default=str)[:4000])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("step", choices=["freeze", "develop", "holdout"])
    args = parser.parse_args()
    {"freeze": freeze, "develop": develop, "holdout": holdout}[args.step]()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
