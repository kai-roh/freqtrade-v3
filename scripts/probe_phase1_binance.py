#!/usr/bin/env python3
"""Capture a redacted, GET-only Binance Phase 1 connectivity snapshot."""

from __future__ import annotations

import argparse
import json
import ssl
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from v3.phase1.binance_probe import (  # noqa: E402
    fee_snapshot_from_probe,
    load_dotenv_credentials,
    probe_phase1_binance,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--credentials-env-file", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--fee-output", type=Path)
    parser.add_argument("--location", required=True)
    parser.add_argument(
        "--classify-mainnet-credentials-on-demo",
        action="store_true",
        help="Explicitly test the live key against Demo read-only account endpoints.",
    )
    parser.add_argument("--ca-file", type=Path)
    return parser.parse_args()


def _default_ca_file() -> Path | None:
    if ssl.get_default_verify_paths().cafile is not None:
        return None
    candidate = Path("/etc/ssl/cert.pem")
    return candidate if candidate.exists() else None


def main() -> int:
    args = parse_args()
    try:
        mainnet = load_dotenv_credentials(args.credentials_env_file, "BINANCE")
        demo = load_dotenv_credentials(args.credentials_env_file, "BINANCE_DEMO")
        result = probe_phase1_binance(
            mainnet_credentials=mainnet,
            demo_credentials=demo,
            classify_mainnet_credentials_on_demo=args.classify_mainnet_credentials_on_demo,
            location=args.location,
            ca_file=args.ca_file or _default_ca_file(),
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        if args.fee_output is not None:
            fee_snapshot = fee_snapshot_from_probe(result, maximum_age_hours=24)
            args.fee_output.parent.mkdir(parents=True, exist_ok=True)
            args.fee_output.write_text(json.dumps(fee_snapshot, indent=2, sort_keys=True) + "\n")
    except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print(f"Binance probe failed safely: {exc}", file=sys.stderr)
        return 2
    conclusion = result["conclusion"]
    print(
        "binance_probe="
        f"{args.output} demo_ready={conclusion['demo_authenticated_integration_ready']} "
        f"mainnet_credentials_valid={conclusion['mainnet_credentials_valid']} "
        "orders_disabled=true"
    )
    return 0 if conclusion["demo_authenticated_integration_ready"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
