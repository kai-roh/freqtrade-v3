#!/usr/bin/env python3
"""Run the pre-registered Phase 2 basket research on the frozen dataset."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from v3.phase2.research import Phase2Config, run_phase2_research  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-dir", type=Path, default=Path("user_data/data-phase2/binance/futures")
    )
    parser.add_argument("--manifest", type=Path, default=Path("evidence/phase2/data-manifest.json"))
    parser.add_argument("--output", type=Path, default=Path("research_results/phase2"))
    parser.add_argument("--generated-at", default=os.environ.get("V3_GENERATED_AT"))
    args = parser.parse_args()
    result = run_phase2_research(
        args.data_dir,
        args.output,
        manifest_path=args.manifest,
        config=Phase2Config(),
        generated_at=args.generated_at,
    )
    print(f"decision={result['decision']} promoted={result['promoted']}")
    print(f"report={args.output / 'REPORT.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
