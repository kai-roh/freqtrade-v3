#!/usr/bin/env python3
"""Build a complete cost ledger and evaluate the Phase 0 cost gate."""

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

from v3.costs import (  # noqa: E402
    CostBasis,
    CostCategory,
    CostLedger,
    CostLine,
    ExecutionLeg,
    ExecutionType,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def _load(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(), parse_float=Decimal)
    if not isinstance(data, dict):
        raise ValueError("cost gate input must be a JSON object")
    return data


def _write(output: Path | None, payload: dict[str, Any]) -> None:
    serialized = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if output is None:
        print(serialized, end="")
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(serialized)


def build_result(data: dict[str, Any]) -> dict[str, Any]:
    executions = tuple(
        ExecutionLeg(
            event_id=row["event_id"],
            leg_id=row["leg_id"],
            venue=row["venue"],
            instrument_id=row["instrument_id"],
            execution_type=ExecutionType(row["execution_type"]),
            notional=row["notional"],
            turnover=row.get("turnover", "1"),
            fee_rate=row["fee_rate"],
            fee_source=row["fee_source"],
            basis=CostBasis(row.get("basis", "estimated")),
        )
        for row in data.get("executions", [])
    )
    other_costs = tuple(
        CostLine(
            category=CostCategory(row["category"]),
            amount=row["amount"],
            source=row["source"],
            basis=CostBasis(row.get("basis", "estimated")),
            event_id=row.get("event_id", ""),
            leg_id=row.get("leg_id", ""),
            description=row.get("description", ""),
        )
        for row in data.get("other_costs", [])
    )
    ledger = CostLedger(
        strategy_id=data["strategy_id"],
        currency=data.get("currency", "USDT"),
        executions=executions,
        other_costs=other_costs,
    )
    gate = ledger.evaluate(
        data["observed_gross_edge"],
        data["reference_notional"],
        data.get("buffer_multiplier", "1.5"),
    )
    return {"ledger": ledger.to_dict(), "gate": gate.to_dict()}


def main() -> int:
    args = parse_args()
    try:
        result = build_result(_load(args.input))
        _write(args.output, result)
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print(f"cost gate failed: {exc}", file=sys.stderr)
        return 2
    return 0 if result["gate"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
