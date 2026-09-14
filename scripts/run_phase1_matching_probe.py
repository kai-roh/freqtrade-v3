#!/usr/bin/env python3
"""Submit and immediately cancel exactly one bounded real Binance Demo order."""

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import psycopg  # noqa: E402

from v3.phase1.binance_probe import load_dotenv_credentials  # noqa: E402
from v3.phase1.matching_probe import run_matching_probe  # noqa: E402
from v3.phase1.notifications import Phase1Notification, send_phase1_telegram  # noqa: E402
from v3.phase1.postgres import apply_migrations  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--credentials-env-file", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--product", required=True, choices=("spot", "perp"))
    parser.add_argument("--execute-demo-probe", action="store_true", required=True)
    args = parser.parse_args()
    result = {
        "environment": "demo",
        "passed": False,
        "strategy_started": False,
        "captured_at": datetime.now(UTC).isoformat(),
    }
    try:
        credentials = load_dotenv_credentials(args.credentials_env_file, "BINANCE_DEMO")
        if credentials is None:
            raise ValueError("dedicated Demo credentials required")
        with psycopg.connect(os.environ["PHASE1_DATABASE_DSN"]) as connection:
            apply_migrations(connection)
            connection.commit()
            result.update(
                run_matching_probe(
                    credentials,
                    connection,
                    product=args.product,
                    source_sha=os.environ["PHASE1_BUILD_SOURCE_SHA"],
                    image_digest=os.environ["PHASE1_IMAGE_DIGEST"],
                )
            )
    except Exception as exc:
        result["error_type"] = type(exc).__name__
    values = {}
    for raw in args.credentials_env_file.read_text().splitlines():
        key, separator, value = raw.partition("=")
        if separator and key.strip() in {"TELEGRAM_TOKEN", "TELEGRAM_CHAT_ID"}:
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
                value = value[1:-1]
            values[key.strip()] = value
    delivered = send_phase1_telegram(
        Phase1Notification(
            "trade" if result["passed"] else "error",
            "실제 데모 주문 접수·취소 시험",
            "전략 자동매매는 시작하지 않았습니다. "
            + (
                "거래소 주문 취소와 체결 0건을 확인했습니다."
                if result["passed"]
                else "확인이 필요하여 후속 주문을 중단했습니다."
            ),
            datetime.now(UTC),
            result,
        ),
        token=values.get("TELEGRAM_TOKEN", ""),
        chat_id=values.get("TELEGRAM_CHAT_ID", ""),
    )
    result["telegram_delivered"] = delivered.delivered
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, sort_keys=True))
    return 0 if result["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
