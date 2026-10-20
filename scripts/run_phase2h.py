#!/usr/bin/env python3
"""Phase 2h: consistency-first intraday decision system (docs/PHASE2H_PREREGISTRATION.md).

freeze   hash the reduced hourly bars and metrics (before any result)
smoke    run one configuration on 2022 only (training data) to check the machinery
run      walk-forward out-of-sample 2023-01..2026-09 for the 8 configurations, gates
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from v3.phase2d.evaluate import daily_sharpe, deflated_sharpe  # noqa: E402
from v3.phase2h.engine import (  # noqa: E402
    Config,
    consistency,
    design,
    registered_grid,
    simulate,
    targets,
    walk_forward,
)
from v3.phase2h.features import FEATURES_A, FEATURES_B, build_panel  # noqa: E402

DATA2H = PROJECT_ROOT / "user_data/data-phase2h"
DATA2D = PROJECT_ROOT / "user_data/data-phase2d"
OUT = PROJECT_ROOT / "research_results/phase2h"
UTC = "UTC"
OOS = (pd.Timestamp("2023-01-01", tz=UTC), pd.Timestamp("2026-09-29", tz=UTC))
TRIALS = 196


def symbols() -> list[str]:
    return sorted(p.stem for p in (DATA2D / "metrics").glob("*.csv"))


def freeze() -> None:
    digest = hashlib.sha256()
    files = sorted((DATA2H / "bars-1h").glob("*.csv.gz")) + sorted(
        (DATA2H / "metrics-1h").glob("*.csv.gz")
    )
    for path in files:
        digest.update(path.parent.name.encode() + path.name.encode())
        digest.update(path.read_bytes())
    value = digest.hexdigest()
    (DATA2H / "manifest.json").write_text(
        json.dumps({"files": len(files), "sha256": value}, indent=1) + "\n"
    )
    print(len(files), value)


def gates(stats: dict, doubled: dict, dsr: float) -> dict:
    years = stats["yearly"]
    return {
        "G1_sharpe_ge_2": stats["sharpe"] >= 2.0,
        "G2_week_hit_ge_65": stats["week_hit"] >= 0.65,
        "G3_month_hit_ge_80": stats["month_hit"] >= 0.80,
        "G4_worst_week_ge_-5": stats["worst_week"] >= -0.05,
        "G5_kept_ge_20pct": stats["concentration_share_kept"] >= 0.20,
        "G6_every_year_positive": all(years.get(y, -1) > 0 for y in (2023, 2024, 2025, 2026)),
        "G7_double_cost": doubled["total"] > 0 and doubled["sharpe"] >= 1.0,
        "G8_dsr_ge_0.95": dsr >= 0.95,
    }


def run(smoke: bool) -> None:
    started = time.time()
    panel = build_panel(DATA2H, DATA2D, symbols())
    print("panel", panel.close.shape, round(time.time() - started), "s", flush=True)
    designs = {"A": design(panel, FEATURES_A), "B": design(panel, FEATURES_B)}
    grid = registered_grid()
    if smoke:
        grid = [Config(4, "A", 1.0)]
        window = (pd.Timestamp("2022-07-01", tz=UTC), pd.Timestamp("2022-12-30", tz=UTC))
    else:
        window = OOS
    rows, returns, extras = [], {}, {}
    for c in grid:
        y = targets(panel, c.horizon)
        pred = walk_forward(panel, designs[c.features], y, c.horizon, *window)
        res = simulate(panel, pred, c, *window)
        dbl = simulate(panel, pred, c, *window, cost_multiplier=2.0)
        stats = consistency(res.daily_returns)
        stats_dbl = consistency(dbl.daily_returns)
        returns[c.label()] = res.daily_returns
        extras[c.label()] = {
            "turnover": res.turnover, "costs": res.costs, "funding": res.funding,
            "stops": res.stops, "loss_limits": res.loss_limits, "trades": res.trades,
            "invested_share": res.hours_invested / max(res.hours, 1),
            "mean_gross": res.gross_sum / max(res.hours, 1),
        }  # fmt: skip
        rows.append({"label": c.label(), **stats, "double_cost": stats_dbl, **extras[c.label()]})
        print(
            c.label(),
            f"sh={stats['sharpe']:.2f} tot={stats['total']:.2f} mdd={stats['mdd']:.2f}",
            f"wk={stats['week_hit']:.2f} mo={stats['month_hit']:.2f} worstwk={stats['worst_week']:.3f}",
            f"medwk={stats['median_week']:.4f} kept={stats['concentration_share_kept']:.2f}",
            f"inv={extras[c.label()]['invested_share']:.2f} gross={extras[c.label()]['mean_gross']:.2f}",
            f"costs={res.costs:.2f} stops={res.stops} limits={res.loss_limits}",
            {y: round(v, 3) for y, v in stats["yearly"].items()},
            flush=True,
        )
    if smoke:
        return
    trial_sharpes = np.array([daily_sharpe(r) for r in returns.values()])
    for row in rows:
        dsr = deflated_sharpe(returns[row["label"]], trial_sharpes, TRIALS)
        row["dsr"] = dsr
        row["gates"] = gates(row, row["double_cost"], dsr)
        row["pass"] = all(row["gates"].values())
    passing = [r for r in rows if r["pass"]]
    selected = max(passing, key=lambda r: r["sharpe"])["label"] if passing else None
    OUT.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(returns).to_csv(OUT / "oos-daily-returns.csv", float_format="%.8g")
    result = {
        "registration": "docs/PHASE2H_PREREGISTRATION.md",
        "manifest": json.loads((DATA2H / "manifest.json").read_text()),
        "oos": [OOS[0].isoformat(), OOS[1].isoformat()],
        "trials_cumulative": TRIALS,
        "configs": rows,
        "verdict": "CANDIDATE" if selected else "STOP_NO_EDGE",
        "selected": selected,
        "runtime_s": round(time.time() - started, 1),
    }
    (OUT / "results.json").write_text(json.dumps(result, indent=2, default=str) + "\n")
    for r in rows:
        print(r["label"], "dsr", round(r["dsr"], 3), {k[:2]: v for k, v in r["gates"].items()})
    print("verdict", result["verdict"], selected)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("step", choices=["freeze", "smoke", "run"])
    args = parser.parse_args()
    if args.step == "freeze":
        freeze()
    else:
        run(smoke=args.step == "smoke")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
