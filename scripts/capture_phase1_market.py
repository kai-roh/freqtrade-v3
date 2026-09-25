#!/usr/bin/env python3
"""Capture public Demo quotes and Mainnet funding without credentials or orders."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from v3.phase1.binance_probe import BinanceReadOnlyClient  # noqa: E402
from v3.phase1.observations import capture_binance_carry_market_observation  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        observation = capture_binance_carry_market_observation(BinanceReadOnlyClient())
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(observation.to_dict(), indent=2, sort_keys=True) + "\n")
        print("public_market_captured=true orders_submitted=false")
        return 0
    except Exception as exc:
        print(f"public observation rejected: {type(exc).__name__}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
