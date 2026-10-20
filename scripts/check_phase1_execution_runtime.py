#!/usr/bin/env python3
"""Validate a captured Phase 1 runtime snapshot without starting an engine."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from v3.phase1.policy import load_phase1_policy  # noqa: E402
from v3.phase1.runtime import ExecutionRuntimeFacts, validate_execution_runtime  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--facts", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        policy = load_phase1_policy(args.policy)
        data = json.loads(args.facts.read_text())
        data["instruments"] = frozenset(data["instruments"])
        facts = ExecutionRuntimeFacts(**data)
        result = validate_execution_runtime(facts, policy)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result.to_dict(), indent=2, sort_keys=True) + "\n")
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print(f"execution runtime check failed: {exc}", file=sys.stderr)
        return 2
    print(f"execution_preflight={args.output} passed={result.passed}")
    return 0 if result.passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
