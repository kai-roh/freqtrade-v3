#!/usr/bin/env python3
"""Stream Demo evidence into PostgreSQL without permitting order submission."""

import argparse
import json
import os
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import psycopg  # noqa: E402

from v3.phase1.binance_probe import load_dotenv_credentials  # noqa: E402
from v3.phase1.demo_collector import collect_demo_stream  # noqa: E402
from v3.phase1.node_smoke import _private_native_logs  # noqa: E402
from v3.phase1.postgres import apply_migrations  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--credentials-env-file", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--seconds", type=int, default=60)
    args = parser.parse_args()
    result = {"passed": False, "orders_submitted": False}
    try:
        credentials = load_dotenv_credentials(args.credentials_env_file, "BINANCE_DEMO")
        with _private_native_logs(), psycopg.connect(os.environ["PHASE1_DATABASE_DSN"]) as conn:
            apply_migrations(conn)
            conn.commit()
            result = collect_demo_stream(credentials, conn, seconds=args.seconds)
    except Exception as exc:
        result["error_type"] = type(exc).__name__
        result["error_frames"] = [
            {"file": Path(frame.filename).name, "line": frame.lineno, "function": frame.name}
            for frame in traceback.extract_tb(exc.__traceback__)
        ]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, sort_keys=True))
    return 0 if result["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
