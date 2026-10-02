#!/usr/bin/env python3
"""Run the Phase 2b risk-neutralization diagnosis (docs/PHASE2B_RISK_DIAGNOSIS.md)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from v3.phase2.risk_diagnosis import run_risk_diagnosis  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-dir", type=Path, default=Path("user_data/data-phase2b/binance/futures")
    )
    parser.add_argument(
        "--manifest", type=Path, default=Path("evidence/phase2b/data-manifest.json")
    )
    parser.add_argument(
        "--filters", type=Path, default=Path("evidence/phase2b/implementability.json")
    )
    parser.add_argument(
        "--recorded", type=Path, default=Path("research_results/phase2b/results.json")
    )
    parser.add_argument(
        "--output", type=Path, default=Path("research_results/phase2b/risk-diagnosis")
    )
    args = parser.parse_args()
    result = run_risk_diagnosis(
        args.data_dir,
        args.output,
        manifest_path=args.manifest,
        filters_path=args.filters,
        recorded_path=args.recorded,
    )
    print(f"decision={result['verdict']['decision']}")
    print(f"report={args.output / 'REPORT.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
