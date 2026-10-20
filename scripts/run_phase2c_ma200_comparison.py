#!/usr/bin/env python3
"""Run the pre-committed fixed-MA200 comparison (docs/PHASE2C_MA200_COMPARISON.md)."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from v3.phase2c.comparison import run_comparison  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--perp-dir", type=Path, default=Path("user_data/data-phase2c/binance/futures")
    )
    parser.add_argument(
        "--perp-manifest", type=Path, default=Path("evidence/phase2c/data-manifest.json")
    )
    parser.add_argument(
        "--spot-dir", type=Path, default=Path("user_data/data-phase2c/binance/spot")
    )
    parser.add_argument(
        "--spot-manifest", type=Path, default=Path("evidence/phase2c/spot-data-manifest.json")
    )
    parser.add_argument(
        "--perp-filters", type=Path, default=Path("evidence/phase2b/implementability.json")
    )
    parser.add_argument(
        "--spot-filters", type=Path, default=Path("evidence/phase2c/spot-filters-20261002.json")
    )
    parser.add_argument(
        "--output", type=Path, default=Path("research_results/phase2c/ma200-comparison")
    )
    parser.add_argument("--generated-at", default=os.environ.get("V3_GENERATED_AT"))
    parser.add_argument(
        "--sleeve",
        type=float,
        default=500.0,
        help="500 is the pre-committed value; 1000 is the user decision in Decision 0018.",
    )
    args = parser.parse_args()
    result = run_comparison(
        args.perp_dir,
        args.perp_manifest,
        args.spot_dir,
        args.spot_manifest,
        args.perp_filters,
        args.spot_filters,
        args.output,
        sleeve=args.sleeve,
        generated_at=args.generated_at,
    )
    print(f"decision={result['decision']}")
    print(f"report={args.output / 'REPORT.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
