#!/usr/bin/env python3
"""Run the pre-registered Phase 2c BTC/ETH trend research on the frozen development dataset."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from v3.phase2c.research import run_phase2c_research  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-dir", type=Path, default=Path("user_data/data-phase2c/binance/futures")
    )
    parser.add_argument(
        "--manifest", type=Path, default=Path("evidence/phase2c/data-manifest.json")
    )
    parser.add_argument(
        "--filters", type=Path, default=Path("evidence/phase2b/implementability.json")
    )
    parser.add_argument("--output", type=Path, default=Path("research_results/phase2c"))
    parser.add_argument("--generated-at", default=os.environ.get("V3_GENERATED_AT"))
    args = parser.parse_args()
    result = run_phase2c_research(
        args.data_dir,
        args.output,
        manifest_path=args.manifest,
        filters_path=args.filters,
        generated_at=args.generated_at,
    )
    print(f"decision={result['decision']}")
    print(f"report={args.output / 'REPORT.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
