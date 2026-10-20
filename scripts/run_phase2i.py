#!/usr/bin/env python3
"""Phase 2i: the Phase 2h intraday signal with maker execution
(docs/PHASE2I_PREREGISTRATION.md).

freeze    hash the 15-minute bars used for the W=15 fill windows
develop   16 configurations on 2022-04-01..2022-12-30 (training period) + viability check
oos       16 configurations once on 2023-01-01..2026-09-29 against gates G1-G8
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from itertools import product
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.run_phase2h import DATA2D, DATA2H, gates, symbols  # noqa: E402
from v3.phase2d.evaluate import daily_sharpe, deflated_sharpe  # noqa: E402
from v3.phase2h.data import load_bars  # noqa: E402
from v3.phase2h.engine import (  # noqa: E402
    Config,
    MakerFill,
    consistency,
    design,
    maker_windows,
    simulate,
    targets,
    walk_forward,
)
from v3.phase2h.features import FEATURES_A, FEATURES_B, build_panel  # noqa: E402

OUT = PROJECT_ROOT / "research_results/phase2i"
UTC = "UTC"
DEV = (pd.Timestamp("2022-04-01", tz=UTC), pd.Timestamp("2022-12-30", tz=UTC))
OOS = (pd.Timestamp("2023-01-01", tz=UTC), pd.Timestamp("2026-09-29", tz=UTC))
TRIALS = 300
VIABLE_SHARPE = 1.5
VIABLE_WEEK_HIT = 0.55


def grid() -> list[tuple[Config, int]]:
    return [
        (Config(h, f, z, hold_frac=0.0, min_trade=0.03), w)
        for h, f, z, w in product((1, 4), ("A", "B"), (1.0, 1.5), (15, 60))
    ]


def label(c: Config, w: int) -> str:
    return f"{c.label()}-W{w}"


def freeze() -> None:
    digest = hashlib.sha256()
    files = sorted((DATA2H / "bars-15m").glob("*.csv.gz"))
    for path in files:
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    value = digest.hexdigest()
    (DATA2H / "manifest-15m.json").write_text(
        json.dumps({"files": len(files), "sha256": value}, indent=1) + "\n"
    )
    print(len(files), value)


def evaluate(window, step: str) -> list[dict]:
    started = time.time()
    names = symbols()
    panel = build_panel(DATA2H, DATA2D, names)
    panel.tier_bps = np.where(panel.tier_bps <= 5, 2.0, 4.0)  # §3: measured slippage + cushion
    bars15 = {s: load_bars(DATA2H, "15m", s) for s in panel.symbols}
    windows = {w: maker_windows(panel, bars15, w) for w in (15, 60)}
    designs = {"A": design(panel, FEATURES_A), "B": design(panel, FEATURES_B)}
    preds: dict[tuple[int, str], np.ndarray] = {}
    rows = []
    for c, w in grid():
        key = (c.horizon, c.features)
        if key not in preds:
            preds[key] = walk_forward(
                panel, designs[c.features], targets(panel, c.horizon), c.horizon, *window
            )
        pred = preds[key]
        dip, pop = windows[w]
        maker = MakerFill(dip, pop)
        res = simulate(panel, pred, c, *window, maker=maker)
        dbl = simulate(
            panel, pred, c, *window, cost_multiplier=2.0, maker=maker
        )  # maker 4 bps, taker x2
        taker = simulate(panel, pred, c, *window)
        s, s2, st = (consistency(r.daily_returns) for r in (res, dbl, taker))
        e = res.extra
        row = {
            "label": label(c, w), **s, "double_cost": s2,
            "taker_comparison": {k: st[k] for k in ("total", "sharpe", "week_hit")},
            "fill_rate": e["fills"] / max(e["orders"], 1), "orders": e["orders"],
            "maker_costs": e["maker_costs"], "taker_costs": e["taker_costs"],
            "funding": res.funding, "stops": res.stops, "loss_limits": res.loss_limits,
            "mean_gross": res.gross_sum / max(res.hours, 1),
            "mean_net_exposure": e["imbalance_sum"] / max(res.hours, 1),
            "turnover_per_day": res.turnover / max(len(res.daily_returns), 1),
            "returns": res.daily_returns,
        }  # fmt: skip
        rows.append(row)
        print(
            row["label"],
            f"sh={s['sharpe']:.2f} tot={s['total']:.3f} mdd={s['mdd']:.3f}",
            f"wk={s['week_hit']:.2f} mo={s['month_hit']:.2f} worstwk={s['worst_week']:.3f}",
            f"medwk={s['median_week']:.4f} kept={s['concentration_share_kept']:.2f}",
            f"fill={row['fill_rate']:.2f} gross={row['mean_gross']:.2f}",
            f"net_exp={row['mean_net_exposure']:.2f} turn/d={row['turnover_per_day']:.2f}",
            f"dbl_sh={s2['sharpe']:.2f} taker_sh={st['sharpe']:.2f}",
            {y: round(v, 3) for y, v in s["yearly"].items()},
            flush=True,
        )
    print(step, "runtime", round(time.time() - started), "s")
    return rows


def save(rows: list[dict], name: str, extra: dict) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({r["label"]: r["returns"] for r in rows}).to_csv(
        OUT / f"{name}-daily-returns.csv", float_format="%.8g"
    )
    payload = {**extra, "configs": [{k: v for k, v in r.items() if k != "returns"} for r in rows]}
    (OUT / f"{name}-results.json").write_text(json.dumps(payload, indent=2, default=str) + "\n")


def develop() -> None:
    rows = evaluate(DEV, "develop")
    viable = [
        r["label"]
        for r in rows
        if r["sharpe"] >= VIABLE_SHARPE and r["week_hit"] >= VIABLE_WEEK_HIT
    ]
    save(rows, "dev", {"window": [DEV[0].isoformat(), DEV[1].isoformat()], "viable": viable,
                       "proceed_to_oos": bool(viable)})  # fmt: skip
    print("viable", viable, "proceed" if viable else "STOP before OOS")


def oos() -> None:
    dev = json.loads((OUT / "dev-results.json").read_text())
    if not dev["proceed_to_oos"]:
        raise SystemExit("development viability check failed; OOS is not computed")
    if (OUT / "oos-results.json").exists():
        raise SystemExit("OOS already evaluated; it is computed once")
    rows = evaluate(OOS, "oos")
    trial_sharpes = np.array([daily_sharpe(r["returns"]) for r in rows])
    for r in rows:
        r["dsr"] = deflated_sharpe(r["returns"], trial_sharpes, TRIALS)
        r["gates"] = gates(r, r["double_cost"], r["dsr"])
        r["pass"] = all(r["gates"].values())
    passing = [r for r in rows if r["pass"]]
    selected = max(passing, key=lambda r: r["sharpe"])["label"] if passing else None
    save(rows, "oos", {
        "window": [OOS[0].isoformat(), OOS[1].isoformat()], "trials_cumulative": TRIALS,
        "verdict": "CANDIDATE" if selected else "STOP_NO_EDGE", "selected": selected,
    })  # fmt: skip
    for r in rows:
        print(r["label"], "dsr", round(r["dsr"], 3), {k[:2]: v for k, v in r["gates"].items()})
    print("verdict", "CANDIDATE" if selected else "STOP_NO_EDGE", selected)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("step", choices=["freeze", "develop", "oos"])
    args = parser.parse_args()
    {"freeze": freeze, "develop": develop, "oos": oos}[args.step]()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
