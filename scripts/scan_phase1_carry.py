#!/usr/bin/env python3
"""Evaluate one order-free carry observation against Phase 1 policy."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from v3.phase1.fee_input import load_fee_snapshot  # noqa: E402
from v3.phase1.policy import FeeSchedule, load_phase1_policy  # noqa: E402
from v3.phase1.scanner import CarryObservation, scan_carry  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--observation", type=Path, required=True)
    parser.add_argument("--fee-snapshot", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def _fee_schedule(path: Path | None) -> FeeSchedule | None:
    if path is None:
        return None
    return load_fee_snapshot(path)


def main() -> int:
    args = parse_args()
    try:
        policy = load_phase1_policy(args.policy)
        data = json.loads(args.observation.read_text())
        data["observed_at"] = datetime.fromisoformat(data["observed_at"])
        observation = CarryObservation(**data)
        target = scan_carry(observation, policy, fee_schedule=_fee_schedule(args.fee_snapshot))
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(target.to_dict(), indent=2, sort_keys=True) + "\n")
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print(f"carry scan failed: {exc}", file=sys.stderr)
        return 2
    print(f"carry_target={args.output} actionable={target.actionable}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
