#!/usr/bin/env python3
"""Run a bounded order-free Demo diagnostic; no trading deployment is started."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from v3.phase1.binance_probe import load_dotenv_credentials  # noqa: E402
from v3.phase1.node_smoke import run_node_smoke  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--credentials-env-file", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--timeout-seconds", type=float, default=45)
    parser.add_argument("--hmac-spot-compat", action="store_true")
    args = parser.parse_args()
    try:
        credentials = load_dotenv_credentials(args.credentials_env_file, "BINANCE_DEMO")
        result = run_node_smoke(
            credentials,
            timeout_seconds=args.timeout_seconds,
            hmac_spot_compat=args.hmac_spot_compat,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        print(f"demo_node_passed={result['passed']} orders_submitted=false")
        return 0 if result["passed"] else 2
    except Exception as exc:
        print(f"diagnostic failed safely: {type(exc).__name__}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
