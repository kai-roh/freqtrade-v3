#!/usr/bin/env python3
"""Run a pre-registered block bootstrap over ordered net-return periods."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from v3.bootstrap import BootstrapSpec, block_bootstrap_mean  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-csv", type=Path, required=True)
    parser.add_argument("--registration", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timestamp-column", default="timestamp")
    parser.add_argument("--return-column", default="net_return")
    return parser.parse_args()


def _load_registration(path: Path) -> BootstrapSpec:
    data: dict[str, Any] = json.loads(path.read_text())
    return BootstrapSpec(
        sample_unit=data["sample_unit"],
        block_definition=data["block_definition"],
        block_length=int(data["block_length"]),
        iterations=int(data["iterations"]),
        seed=int(data["seed"]),
        alpha=float(data.get("alpha", 0.05)),
        direction=data.get("direction", "two-sided"),
    )


def _load_returns(path: Path, timestamp_column: str, return_column: str) -> pd.Series:
    frame = pd.read_csv(path)
    missing = {timestamp_column, return_column}.difference(frame.columns)
    if missing:
        raise ValueError(f"missing CSV columns: {', '.join(sorted(missing))}")
    timestamps = pd.to_datetime(frame[timestamp_column], utc=True, errors="coerce")
    if timestamps.isna().any():
        raise ValueError("timestamp column contains invalid values")
    return pd.Series(frame[return_column].to_numpy(), index=pd.DatetimeIndex(timestamps))


def main() -> int:
    args = parse_args()
    try:
        spec = _load_registration(args.registration)
        returns = _load_returns(args.input_csv, args.timestamp_column, args.return_column)
        result = block_bootstrap_mean(returns, spec)
        payload = {
            "schema_version": 1,
            "registration": spec.to_dict(),
            "observation_count": len(returns),
            "result": result.to_dict(),
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print(f"bootstrap failed: {exc}", file=sys.stderr)
        return 2
    print(f"bootstrap={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
