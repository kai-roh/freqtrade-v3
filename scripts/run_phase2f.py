#!/usr/bin/env python3
"""Phase 2f: regime long/short and positioning strategies (docs/PHASE2F_PREREGISTRATION.md).

freeze    hash the reduced positioning metrics (after the download)
develop   run the 66 registered configurations and benchmarks on the development
          windows, compute PBO and the development gates (no validation days)
validate  evaluate the development-gate survivors once on 2024-01-01..2026-09-29
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

from scripts.run_phase2d import DATA, markets, summary  # noqa: E402
from scripts.run_phase2d import run as run_benchmark  # noqa: E402
from v3.phase2d.engine import Market, simulate  # noqa: E402
from v3.phase2d.evaluate import daily_sharpe, deflated_sharpe, pbo_cscv  # noqa: E402
from v3.phase2d.strategies import BENCHMARKS  # noqa: E402
from v3.phase2f.data import load_metrics, taker_buy_share, write_manifest  # noqa: E402
from v3.phase2f.strategies import (  # noqa: E402
    TRIALS_BEFORE,
    Config,
    Signals,
    registered_grid,
    weight_fn,
)

OUT = PROJECT_ROOT / "research_results/phase2f"
UTC = "UTC"
FAMILIES = ("R1", "R2", "P1", "P2", "P3", "P4")
POSITIONING = {"P1", "P2", "P4"}
DEV = {
    "price": (pd.Timestamp("2020-07-01", tz=UTC), pd.Timestamp("2023-12-31", tz=UTC)),
    "positioning": (pd.Timestamp("2022-01-01", tz=UTC), pd.Timestamp("2023-12-31", tz=UTC)),
}
VALIDATION = (pd.Timestamp("2024-01-01", tz=UTC), pd.Timestamp("2026-09-29", tz=UTC))
SUB_PERIODS = {
    "2024": (pd.Timestamp("2024-01-01", tz=UTC), pd.Timestamp("2024-12-31", tz=UTC)),
    "2025-26": (pd.Timestamp("2025-01-01", tz=UTC), pd.Timestamp("2026-09-29", tz=UTC)),
}


def window_key(c: Config) -> str:
    return "positioning" if c.family in POSITIONING else "price"


def load() -> tuple[dict[str, Market], Signals]:
    m = markets()
    perp = m["perp"]
    metrics = load_metrics(DATA, perp.days, perp.symbols)
    signals = Signals(
        top_ls=metrics["top_ls"],
        acct_ls=metrics["acct_ls"],
        oi_value=metrics["oi_value"],
        taker_share=taker_buy_share(DATA, perp.days, perp.symbols),
    )
    return m, signals


def run(perp: Market, signals: Signals, c: Config, start, end, cost=1.0, side=0):
    """``side``: 0 both, +1 long legs only, -1 short legs only (P&L attribution)."""
    fn = weight_fn(c, perp, signals)
    if side:
        base = fn

        def fn(m, i):  # noqa: F811
            return {j: w for j, w in base(m, i).items() if w * side > 0}

    return simulate(perp, fn, start=start, end=end, every=c.every, cost_multiplier=cost)


def benchmarks(m: dict[str, Market], start, end) -> dict:
    return {b.family: summary(run_benchmark(m["spot"], b, start, end)) for b in BENCHMARKS}


def freeze() -> None:
    print(write_manifest(DATA))


def develop() -> None:
    m, signals = load()
    perp = m["perp"]
    grid = registered_grid()
    started = time.time()
    rows, returns = [], {}
    for c in grid:
        start, end = DEV[window_key(c)]
        res = run(perp, signals, c, start, end)
        rows.append({**c.to_json(), "window": window_key(c), **summary(res)})
        returns[c.label()] = res.returns
    bench = {k: benchmarks(m, *w) for k, w in DEV.items()}
    table = pd.DataFrame(rows).set_index("label")
    families = {}
    for fam in FAMILIES:
        members = table[table.family == fam]
        best = members.sharpe.idxmax()
        c = next(x for x in grid if x.label() == best)
        key = window_key(c)
        start, end = DEV[key]
        bench_best = max(v["sharpe"] for v in bench[key].values())
        btc_mdd = bench[key]["BTC"]["mdd"]
        doubled = summary(run(perp, signals, c, start, end, cost=2.0))
        pbo = pbo_cscv(pd.DataFrame({lbl: returns[lbl] for lbl in members.index}))
        r = table.loc[best]
        gates = {
            "D1_sharpe_beats_benchmarks": bool(r.sharpe > bench_best),
            "D3_pbo_le_0.30": bool(pbo <= 0.30),
            "D4_double_cost_beats_benchmarks": bool(doubled["sharpe"] > bench_best),
            "D5_mdd_below_btc": bool(r.mdd < btc_mdd),
            "D6_majority_positive_years": bool(r.years_positive * 2 > r.years),
        }
        families[fam] = {
            "best": best,
            "config": c.to_json(),
            "window": key,
            "dev": {k: (v.item() if isinstance(v, np.generic) else v) for k, v in r.items()},
            "long_only": summary(run(perp, signals, c, start, end, side=1)),
            "short_only": summary(run(perp, signals, c, start, end, side=-1)),
            "double_cost": doubled,
            "pbo": pbo,
            "benchmark_best_sharpe": bench_best,
            "btc_mdd": btc_mdd,
            "gates": gates,
            "dev_pass": all(gates.values()),
        }
    OUT.mkdir(parents=True, exist_ok=True)
    table.to_csv(OUT / "dev-all-configs.csv", float_format="%.6g")
    pd.DataFrame(returns).to_csv(OUT / "dev-daily-returns.csv.gz", float_format="%.8g")
    result = {
        "registration": "docs/PHASE2F_PREREGISTRATION.md",
        "panel_hashes": json.loads((DATA / "panel-hashes.json").read_text()),
        "metrics_manifest": json.loads((DATA / "metrics-manifest.json").read_text()),
        "windows": {k: [a.isoformat(), b.isoformat()] for k, (a, b) in DEV.items()},
        "trials": len(grid),
        "benchmarks": bench,
        "families": families,
        "dev_survivors": [f for f, v in families.items() if v["dev_pass"]],
        "runtime_s": round(time.time() - started, 1),
    }
    (OUT / "dev-results.json").write_text(json.dumps(result, indent=2, default=str) + "\n")
    for f, v in families.items():
        d = v["dev"]
        print(
            f, v["best"], f"sh={d['sharpe']:.2f} cagr={d['cagr']:.2f} mdd={d['mdd']:.2f}",
            f"pbo={v['pbo']:.2f}", "PASS" if v["dev_pass"] else "fail",
            {k: round(x, 2) for k, x in d["yearly"].items()},
        )  # fmt: skip
    for k, b in bench.items():
        print(k, {n: (round(x["sharpe"], 2), round(x["cagr"], 2)) for n, x in b.items()})


def validate() -> None:
    dev_path = OUT / "dev-results.json"
    if not dev_path.is_file():
        raise SystemExit("run develop first; validation is evaluated only after selection")
    path = OUT / "validation-results.json"
    if path.exists():
        raise SystemExit("validation already evaluated; it is computed once")
    dev = json.loads(dev_path.read_text())
    m, signals = load()
    perp = m["perp"]
    trial_sharpes = (
        pd.read_csv(OUT / "dev-daily-returns.csv.gz", index_col=0).apply(daily_sharpe).to_numpy()
    )
    trials = TRIALS_BEFORE + dev["trials"]
    bench = benchmarks(m, *VALIDATION)
    evaluated = {}
    for fam in dev["dev_survivors"]:
        c = Config(**{k: v for k, v in dev["families"][fam]["config"].items() if k != "label"})
        res = run(perp, signals, c, *VALIDATION)
        s = summary(res)
        subs = {k: summary(run(perp, signals, c, *w)) for k, w in SUB_PERIODS.items()}
        doubled = summary(run(perp, signals, c, *VALIDATION, cost=2.0))
        start, _ = DEV[window_key(c)]
        full = run(perp, signals, c, start, VALIDATION[1]).returns
        dsr = deflated_sharpe(full, trial_sharpes, trials)
        gates = {
            "V1_positive_and_sharpe_ge_0.5": bool(s["total"] > 0 and s["sharpe"] >= 0.5),
            "V2_positive_both_subperiods": all(v["total"] > 0 for v in subs.values()),
            "V3_double_cost_positive": bool(doubled["total"] > 0),
            "V4_mdd_below_btc": bool(s["mdd"] < bench["BTC"]["mdd"]),
            "V5_dsr_ge_0.95": bool(dsr >= 0.95),
        }
        evaluated[fam] = {
            "best": dev["families"][fam]["best"],
            "validation": s,
            "sub_periods": subs,
            "double_cost": doubled,
            "long_only": summary(run(perp, signals, c, *VALIDATION, side=1)),
            "short_only": summary(run(perp, signals, c, *VALIDATION, side=-1)),
            "dsr": dsr,
            "gates": gates,
            "pass": all(gates.values()),
        }
    passing = [f for f, v in evaluated.items() if v["pass"]]
    selected = max(passing, key=lambda f: dev["families"][f]["dev"]["sharpe"]) if passing else None
    result = {
        "window": [VALIDATION[0].isoformat(), VALIDATION[1].isoformat()],
        "trials_cumulative": trials,
        "benchmarks": bench,
        "benchmarks_sub_periods": {k: benchmarks(m, *w) for k, w in SUB_PERIODS.items()},
        "evaluated": evaluated,
        "verdict": "CANDIDATE" if selected else "STOP_NO_EDGE",
        "selected": selected,
    }
    path.write_text(json.dumps(result, indent=2, default=str) + "\n")
    print(json.dumps(result, indent=1, default=str)[:6000])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("step", choices=["freeze", "develop", "validate"])
    args = parser.parse_args()
    {"freeze": freeze, "develop": develop, "validate": validate}[args.step]()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
