#!/usr/bin/env python3
"""Validate one captured venue instrument and intended order without placing it."""

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

from v3.instruments import (  # noqa: E402
    InstrumentPreflightPolicy,
    InstrumentPreflightRequest,
    InstrumentSpec,
    ProbeStatus,
    VenueEnvironment,
    check_instrument_conformance,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def _load(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(), parse_float=Decimal)
    if not isinstance(data, dict):
        raise ValueError("instrument input must be a JSON object")
    return data


def build_result(data: dict[str, Any]) -> dict[str, Any]:
    instrument = data["instrument"]
    order = data["order"]
    policy_data = data.get("policy", {})
    spec = InstrumentSpec(
        venue=instrument["venue"],
        environment=VenueEnvironment(instrument["environment"]),
        instrument_id=instrument["instrument_id"],
        minimum_notional=instrument["minimum_notional"],
        minimum_quantity=instrument["minimum_quantity"],
        quantity_increment=instrument["quantity_increment"],
        price_increment=instrument["price_increment"],
        price_significant_digits=instrument["price_significant_digits"],
        price_max_decimal_places=instrument.get("price_max_decimal_places"),
        integer_price_has_no_significant_digit_limit=instrument.get(
            "integer_price_has_no_significant_digit_limit", False
        ),
        asset_index=instrument.get("asset_index"),
        source=instrument["source"],
        is_active=instrument.get("active", True),
    )
    request = InstrumentPreflightRequest(
        spec=spec,
        price=order["price"],
        quantity=order["quantity"],
        observed_leverage=order.get("observed_leverage"),
        quote_age_ms=order.get("quote_age_ms"),
        order_reject_probe=ProbeStatus(order.get("order_reject_probe", "not_run")),
    )
    policy = InstrumentPreflightPolicy(
        maximum_leverage=policy_data.get("maximum_leverage", "2"),
        minimum_notional_headroom=policy_data.get("minimum_notional_headroom", "3"),
        maximum_quote_age_ms=policy_data.get("maximum_quote_age_ms"),
        require_order_reject_probe=policy_data.get("require_order_reject_probe", False),
    )
    return check_instrument_conformance(request, policy).to_dict()


def _write(output: Path | None, payload: dict[str, Any]) -> None:
    serialized = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if output is None:
        print(serialized, end="")
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(serialized)


def main() -> int:
    args = parse_args()
    try:
        result = build_result(_load(args.input))
        _write(args.output, result)
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print(f"instrument preflight failed: {exc}", file=sys.stderr)
        return 2
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
