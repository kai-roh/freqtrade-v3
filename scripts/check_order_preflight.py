#!/usr/bin/env python3
"""Validate final order admission, including instrument checks and intent."""

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

from v3.preflight import order_preflight_from_mapping, validate_order_preflight  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def _load(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(), parse_float=Decimal)
    if not isinstance(data, dict):
        raise ValueError("order preflight input must be a JSON object")
    return data


def _write(output: Path | None, payload: dict[str, Any]) -> None:
    serialized = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if output is None:
        print(serialized, end="")
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(serialized)


def main() -> int:
    args = parse_args()
    try:
        result = validate_order_preflight(order_preflight_from_mapping(_load(args.input)))
        _write(args.output, result.to_dict())
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print(f"order preflight failed: {exc}", file=sys.stderr)
        return 2
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
