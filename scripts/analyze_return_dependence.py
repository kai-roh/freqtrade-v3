#!/usr/bin/env python3
"""Calculate ACF and Ljung-Box diagnostics for ordered return observations."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from v3.dependence import return_dependence_diagnostics  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-csv", type=Path, required=True)
    parser.add_argument("--return-column", default="net_return")
    parser.add_argument("--maximum-lag", type=int, default=10)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        frame = pd.read_csv(args.input_csv)
        if args.return_column not in frame:
            raise ValueError(f"missing CSV column: {args.return_column}")
        result = return_dependence_diagnostics(
            frame[args.return_column], maximum_lag=args.maximum_lag
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result.to_dict(), indent=2, sort_keys=True) + "\n")
    except (OSError, TypeError, ValueError, RuntimeError) as exc:
        print(f"dependence analysis failed: {exc}", file=sys.stderr)
        return 2
    print(f"dependence={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
