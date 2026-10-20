#!/usr/bin/env python3
"""Phase 2g: one-hypothesis check of the taker-flow ensemble T1
(docs/PHASE2G_PREREGISTRATION.md).

  develop   T1 and benchmarks on the Phase 2f price development window (seen data)
  validate  T1 once on 2024-01-01..2026-09-29 against gates V1-V5
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.run_phase2d import summary  # noqa: E402
from scripts.run_phase2f import DEV, SUB_PERIODS, VALIDATION, benchmarks, load  # noqa: E402
from scripts.run_phase2f import OUT as OUT_2F  # noqa: E402
from v3.phase2d.engine import simulate  # noqa: E402
from v3.phase2d.evaluate import daily_sharpe, deflated_sharpe  # noqa: E402
from v3.phase2f.strategies import T1_MEMBERS, ensemble_fn  # noqa: E402

OUT = PROJECT_ROOT / "research_results/phase2g"
TRIALS = 188


def t1(m, signals, start, end, cost=1.0, side=0):
    fn = ensemble_fn(T1_MEMBERS, m["perp"], signals)
    if side:
        base = fn

        def fn(mk, i):  # noqa: F811
            return {j: w for j, w in base(mk, i).items() if w * side > 0}

    return simulate(m["perp"], fn, start=start, end=end, every=7, cost_multiplier=cost)


def report(m, signals, window) -> dict:
    res = t1(m, signals, *window)
    return {
        "window": [window[0].isoformat(), window[1].isoformat()],
        "T1": summary(res),
        "T1_double_cost": summary(t1(m, signals, *window, cost=2.0)),
        "long_only": summary(t1(m, signals, *window, side=1)),
        "short_only": summary(t1(m, signals, *window, side=-1)),
        "benchmarks": benchmarks(m, *window),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("step", choices=["develop", "validate"])
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    m, signals = load()
    if args.step == "develop":
        result = report(m, signals, DEV["price"])
        path = OUT / "dev-results.json"
    else:
        path = OUT / "validation-results.json"
        if path.exists():
            raise SystemExit("validation already evaluated; it is computed once")
        result = report(m, signals, VALIDATION)
        subs = {k: summary(t1(m, signals, *w)) for k, w in SUB_PERIODS.items()}
        result["sub_periods"] = subs
        result["benchmarks_sub_periods"] = {k: benchmarks(m, *w) for k, w in SUB_PERIODS.items()}
        trial_sharpes = (
            pd.read_csv(OUT_2F / "dev-daily-returns.csv.gz", index_col=0)
            .apply(daily_sharpe)
            .to_numpy()
        )
        full = t1(m, signals, DEV["price"][0], VALIDATION[1]).returns
        dsr = deflated_sharpe(full, trial_sharpes, TRIALS)
        s = result["T1"]
        gates = {
            "V1_positive_and_sharpe_ge_0.5": bool(s["total"] > 0 and s["sharpe"] >= 0.5),
            "V2_positive_both_subperiods": all(v["total"] > 0 for v in subs.values()),
            "V3_double_cost_positive": bool(result["T1_double_cost"]["total"] > 0),
            "V4_mdd_below_btc": bool(s["mdd"] < result["benchmarks"]["BTC"]["mdd"]),
            "V5_dsr_ge_0.95": bool(dsr >= 0.95),
        }
        result.update(
            dsr=dsr,
            full_period=summary(t1(m, signals, DEV["price"][0], VALIDATION[1])),
            gates=gates,
            verdict="CANDIDATE" if all(gates.values()) else "FAIL",
        )
    path.write_text(json.dumps(result, indent=2, default=str) + "\n")
    print(json.dumps(result, indent=1, default=str)[:7000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
