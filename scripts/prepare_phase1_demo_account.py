#!/usr/bin/env python3
"""Inspect and optionally prepare Binance Demo USD-M settings for Phase 1."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from v3.phase1.binance_admin import prepare_demo_futures_account  # noqa: E402
from v3.phase1.binance_probe import load_dotenv_credentials  # noqa: E402
from v3.phase1.http import secure_open  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--credentials-env-file", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--apply-demo-config",
        action="store_true",
        help="Apply Demo USD-M isolated margin and 2x leverage after flatness checks.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        credentials = load_dotenv_credentials(args.credentials_env_file, "BINANCE_DEMO")
        if credentials is None:
            raise ValueError("BINANCE_DEMO credentials are required")
        result = prepare_demo_futures_account(
            credentials,
            apply_changes=args.apply_demo_config,
            opener=secure_open,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Demo account preparation failed safely: {exc}", file=sys.stderr)
        return 2

    payload = result.to_dict()
    payload["captured_at"] = datetime.now(UTC).isoformat()
    payload["official_sources"] = {
        "binance_demo_spot": (
            "https://developers.binance.com/en/docs/products/spot/demo-mode/general-info"
        ),
        "binance_usdm_trade": (
            "https://developers.binance.com/en/docs/catalog/"
            "core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/trade"
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(
        f"demo_account_preflight={args.output} "
        f"ready={payload['ready_for_phase1_demo_execution']} "
        f"actions_required={','.join(payload['actions_required']) or 'none'}"
    )
    return 0 if payload["ready_for_phase1_demo_execution"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
