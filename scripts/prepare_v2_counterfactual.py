#!/usr/bin/env python3
"""Prepare hash-verified daily V2 fee-only returns for block bootstrap."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from v3.v2_counterfactual import (  # noqa: E402
    FeeOnlyCounterfactualSpec,
    build_fee_only_counterfactual,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--expected-database-sha256", required=True)
    parser.add_argument("--expected-closed-trade-count", type=int, required=True)
    parser.add_argument("--original-fee-rate", required=True)
    parser.add_argument("--maker-fee-rate", required=True)
    parser.add_argument("--taker-fee-rate", required=True)
    parser.add_argument("--reference-capital", required=True)
    parser.add_argument("--reporting-timezone", default="Asia/Seoul")
    parser.add_argument("--daily-output", type=Path, required=True)
    parser.add_argument("--summary-output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        spec = FeeOnlyCounterfactualSpec(
            original_fee_rate=args.original_fee_rate,
            maker_fee_rate=args.maker_fee_rate,
            taker_fee_rate=args.taker_fee_rate,
            reference_capital=args.reference_capital,
            reporting_timezone=args.reporting_timezone,
        )
        result = build_fee_only_counterfactual(
            args.database,
            expected_database_sha256=args.expected_database_sha256,
            expected_closed_trade_count=args.expected_closed_trade_count,
            spec=spec,
        )
        args.daily_output.parent.mkdir(parents=True, exist_ok=True)
        with args.daily_output.open("w", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=[
                    "timestamp",
                    "closed_trade_count",
                    "gross_pnl",
                    "counterfactual_fee",
                    "counterfactual_net_pnl",
                    "net_return",
                ],
            )
            writer.writeheader()
            writer.writerows(row.to_dict() for row in result.daily_returns)
        args.summary_output.parent.mkdir(parents=True, exist_ok=True)
        args.summary_output.write_text(
            json.dumps(result.to_dict(), indent=2, sort_keys=True) + "\n"
        )
        args.daily_output.chmod(0o600)
        args.summary_output.chmod(0o600)
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        print(f"V2 counterfactual preparation failed: {exc}", file=sys.stderr)
        return 2
    print(f"daily_returns={args.daily_output}")
    print(f"summary={args.summary_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
