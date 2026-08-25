#!/usr/bin/env python3
"""Check the legacy Freqtrade shadow boundary before Docker startup."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from v3.runtime_preflight import load_and_validate  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=Path("configs/dry-run.json"))
    parser.add_argument("--compose", type=Path, default=Path("docker-compose.yml"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        result = load_and_validate(args.config, args.compose)
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print(f"shadow preflight failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
