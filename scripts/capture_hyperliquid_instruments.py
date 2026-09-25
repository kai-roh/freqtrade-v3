#!/usr/bin/env python3
"""Capture read-only Hyperliquid perpetual metadata and derived order constraints."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from v3.hyperliquid import (  # noqa: E402
    HyperliquidMetadataError,
    fetch_metadata_response,
    parse_perp_snapshot,
)
from v3.instruments import VenueEnvironment  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--environment",
        choices=[environment.value for environment in VenueEnvironment],
        required=True,
    )
    parser.add_argument("--symbol", action="append", dest="symbols")
    parser.add_argument(
        "--input-response",
        type=Path,
        help="Replay a previously captured raw response instead of using the network.",
    )
    parser.add_argument(
        "--raw-output",
        type=Path,
        help="Required for a network capture; preserves the exact response behind the hash.",
    )
    parser.add_argument("--fetched-at", help="Override capture time for deterministic replay.")
    parser.add_argument("--timeout-seconds", type=float, default=15.0)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def _write_private(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    path.chmod(0o600)


def _require_distinct_paths(*paths: Path | None) -> None:
    resolved = [path.resolve() for path in paths if path is not None]
    if len(resolved) != len(set(resolved)):
        raise ValueError("input, raw output, and parsed output paths must be distinct")


def main() -> int:
    args = parse_args()
    environment = VenueEnvironment(args.environment)
    try:
        _require_distinct_paths(args.input_response, args.raw_output, args.output)
        if args.input_response is None:
            if args.raw_output is None:
                raise ValueError("--raw-output is required for a network capture")
            raw = fetch_metadata_response(environment, timeout_seconds=args.timeout_seconds)
            _write_private(args.raw_output, raw)
        else:
            raw = args.input_response.read_bytes()
            if args.raw_output is not None:
                _write_private(args.raw_output, raw)
        snapshot = parse_perp_snapshot(
            raw,
            environment,
            symbols=args.symbols,
            fetched_at=args.fetched_at,
        )
        serialized = json.dumps(snapshot.to_dict(), indent=2, sort_keys=True) + "\n"
        _write_private(args.output, serialized.encode())
    except (HyperliquidMetadataError, OSError, TypeError, ValueError) as exc:
        print(f"Hyperliquid metadata capture failed: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
