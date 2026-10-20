#!/usr/bin/env python3
"""Record Demo account readiness and signed order-test responses without fills."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from v3.phase1.binance_probe import load_dotenv_credentials  # noqa: E402
from v3.phase1.demo_validation import capture_demo_validation  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--credentials-env-file", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    credentials = load_dotenv_credentials(args.credentials_env_file, "BINANCE_DEMO")
    if credentials is None:
        parser.error("dedicated Demo credentials required")
    result = capture_demo_validation(credentials)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as output:
        output.write(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result))
    return 0 if result["validation_api_passed"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
