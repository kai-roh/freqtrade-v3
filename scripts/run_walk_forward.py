#!/usr/bin/env python3
"""Run milestone-one deterministic walk-forward research."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from v3.research import ResearchConfig, run_milestone_one  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("user_data/data/binance/futures"),
    )
    parser.add_argument("--output", type=Path, default=Path("research_results/milestone-1"))
    parser.add_argument("--fold-count", type=int, default=6)
    parser.add_argument("--train-days", type=int, default=90)
    parser.add_argument("--validation-days", type=int, default=30)
    parser.add_argument("--embargo-hours", type=int, default=6)
    parser.add_argument("--min-train-trades", type=int, default=30)
    parser.add_argument("--normal-cost-bps", type=float, default=20.0)
    parser.add_argument("--stress-cost-bps", type=float, default=30.0)
    parser.add_argument(
        "--generated-at",
        default=os.environ.get("V3_GENERATED_AT"),
        help="Optional fixed UTC timestamp for byte-for-byte reproducible reports.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = run_milestone_one(
        args.data_dir,
        args.output,
        ResearchConfig(
            fold_count=args.fold_count,
            train_days=args.train_days,
            validation_days=args.validation_days,
            embargo_hours=args.embargo_hours,
            min_train_trades=args.min_train_trades,
            normal_cost_bps=args.normal_cost_bps,
            stress_cost_bps=args.stress_cost_bps,
        ),
        generated_at=args.generated_at,
    )
    print(f"decision={result['decision']}")
    print(f"report={args.output / 'REPORT.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
