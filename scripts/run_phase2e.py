#!/usr/bin/env python3
"""Phase 2e: one-hypothesis confirmation of the F1 momentum ensemble E1
(docs/PHASE2E_PREREGISTRATION.md).

  develop  E1 and benchmarks on the Phase 2d development window (already-seen data)
  holdout  E1 once on 2025-01-01..2026-09-29 against gates H1-H4
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.run_phase2d import HOLDOUT, WINDOWS, markets, run, summary  # noqa: E402
from v3.phase2d.engine import simulate  # noqa: E402
from v3.phase2d.strategies import BENCHMARKS, E1_MEMBERS, ensemble_fn  # noqa: E402

OUT = PROJECT_ROOT / "research_results/phase2e"


def evaluate(window) -> dict:
    m = markets()
    start, end = window
    e1 = simulate(m["spot"], ensemble_fn(E1_MEMBERS, m["spot"]), start=start, end=end, every=7)
    doubled = simulate(
        m["spot"],
        ensemble_fn(E1_MEMBERS, m["spot"]),
        start=start,
        end=end,
        every=7,
        cost_multiplier=2.0,
    )
    return {
        "window": [start.isoformat(), end.isoformat()],
        "E1": summary(e1),
        "E1_double_cost": summary(doubled),
        "benchmarks": {b.family: summary(run(m["spot"], b, start, end)) for b in BENCHMARKS},
        "returns": e1.returns,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("step", choices=["develop", "holdout"])
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    if args.step == "develop":
        result = evaluate(WINDOWS["spot"])
        path = OUT / "dev-results.json"
    else:
        path = OUT / "holdout-results.json"
        if path.exists():
            raise SystemExit("holdout already evaluated; it is computed once")
        result = evaluate(HOLDOUT)
        e1, btc = result["E1"], result["benchmarks"]["BTC"]
        gates = {
            "H1_positive": e1["total"] > 0,
            "H2_sharpe_ge_0.5": e1["sharpe"] >= 0.5,
            "H3_sharpe_ge_btc": e1["sharpe"] >= btc["sharpe"],
            "H4_mdd_below_btc": e1["mdd"] < btc["mdd"],
        }
        result["gates"] = gates
        result["verdict"] = "PASS" if all(gates.values()) else "FAIL"
    returns = result.pop("returns")
    returns.to_csv(path.with_suffix(".returns.csv"), header=["E1"], float_format="%.8g")
    path.write_text(json.dumps(result, indent=2, default=str) + "\n")
    show = {k: v for k, v in result.items() if k != "benchmarks"}
    print(json.dumps(show, indent=1, default=str))
    print(
        json.dumps(
            {
                k: {x: round(v[x], 3) for x in ("total", "cagr", "sharpe", "mdd")}
                for k, v in result["benchmarks"].items()
            },
            indent=1,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
