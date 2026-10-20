#!/usr/bin/env python3
"""Build final order-preflight input from a captured Hyperliquid snapshot."""

from __future__ import annotations

import argparse
import json
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from v3.hyperliquid import (  # noqa: E402
    HyperliquidMetadataError,
    build_preflight_input_from_snapshot,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--instrument", required=True)
    parser.add_argument("--price")
    parser.add_argument("--price-source", choices=["mark", "oracle"], default="mark")
    size = parser.add_mutually_exclusive_group(required=True)
    size.add_argument("--quantity")
    size.add_argument("--target-notional")
    parser.add_argument("--observed-leverage", required=True)
    parser.add_argument("--quote-age-ms", type=int, required=True)
    parser.add_argument(
        "--order-reject-probe",
        choices=["not_run", "passed", "failed"],
        default="not_run",
    )
    parser.add_argument("--maximum-leverage", default="2")
    parser.add_argument("--minimum-notional-headroom", default="3")
    parser.add_argument("--maximum-quote-age-ms", type=int, default=250)
    parser.add_argument("--require-order-reject-probe", action="store_true")
    parser.add_argument("--entry-reason", required=True)
    parser.add_argument("--target-position", required=True)
    parser.add_argument("--normal-exit", required=True)
    parser.add_argument("--risk-exit", required=True)
    parser.add_argument("--max-holding-or-review-at", required=True)
    parser.add_argument("--cost-and-risk-budget", required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def _load(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(), parse_float=Decimal)
    if not isinstance(data, dict):
        raise ValueError("Hyperliquid snapshot must be a JSON object")
    return data


def main() -> int:
    args = parse_args()
    policy = {
        "maximum_leverage": args.maximum_leverage,
        "minimum_notional_headroom": args.minimum_notional_headroom,
        "maximum_quote_age_ms": args.maximum_quote_age_ms,
        "require_order_reject_probe": args.require_order_reject_probe,
    }
    intent = {
        "entry_reason": args.entry_reason,
        "target_position": args.target_position,
        "normal_exit": args.normal_exit,
        "risk_exit": args.risk_exit,
        "max_holding_or_review_at": args.max_holding_or_review_at,
        "cost_and_risk_budget": args.cost_and_risk_budget,
    }
    try:
        payload = build_preflight_input_from_snapshot(
            _load(args.snapshot),
            instrument_id=args.instrument,
            price=args.price,
            price_source=args.price_source,
            quantity=args.quantity,
            target_notional=args.target_notional,
            observed_leverage=args.observed_leverage,
            quote_age_ms=args.quote_age_ms,
            order_reject_probe=args.order_reject_probe,
            policy=policy,
            intent=intent,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        args.output.chmod(0o600)
    except (HyperliquidMetadataError, OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print(f"Hyperliquid preflight input build failed: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
