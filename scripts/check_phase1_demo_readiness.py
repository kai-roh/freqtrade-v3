#!/usr/bin/env python3
"""Read Demo wallet/position prerequisites and optionally test the Demo Telegram channel."""

import argparse
import json
import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from v3.phase1.binance_probe import load_dotenv_credentials  # noqa: E402
from v3.phase1.demo_inspector import DemoInspector  # noqa: E402
from v3.phase1.notifications import Phase1Notification, send_phase1_telegram  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--credentials-env-file", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--notify", action="store_true")
    args = parser.parse_args()
    result = {
        "orders_submitted": False,
        "passed": False,
        "captured_at": datetime.now(UTC).isoformat(),
    }
    try:
        credentials = load_dotenv_credentials(args.credentials_env_file, "BINANCE_DEMO")
        if credentials is None:
            raise ValueError("dedicated Demo credentials required")
        account = DemoInspector(credentials).account()
        result["checks"] = {
            "spot_funded_for_180_notional": account["spot_usdt"] >= Decimal("181.8"),
            "perp_funded_for_180_notional": account["perp_usdt"] >= Decimal("181.8"),
            "perp_flat": account["perp_qty"] == 0,
            "no_btc_open_orders": not account["open_orders"],
            "isolated_margin": account["margin_type"] == "ISOLATED",
            "leverage_at_most_two": 1 <= account["leverage"] <= 2,
        }
        result["passed"] = all(result["checks"].values())
        if args.notify:
            values = {}
            for raw in args.credentials_env_file.read_text().splitlines():
                key, separator, value = raw.partition("=")
                if separator and key.strip() in {"TELEGRAM_TOKEN", "TELEGRAM_CHAT_ID"}:
                    value = value.strip()
                    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
                        value = value[1:-1]
                    values[key.strip()] = value
            delivery = send_phase1_telegram(
                Phase1Notification(
                    "start",
                    "실시간 원장 연결 점검",
                    "데모 현물·선물 호가의 PostgreSQL 저장을 확인했습니다. "
                    "이 알림은 연결 시험이며 주문·일주일 자동매매는 아직 시작하지 않았습니다.",
                    datetime.now(UTC),
                    {"account_preflight_passed": result["passed"]},
                ),
                token=values.get("TELEGRAM_TOKEN", ""),
                chat_id=values.get("TELEGRAM_CHAT_ID", ""),
            )
            result["telegram_delivered"] = delivery.delivered
            result["telegram_error_type"] = delivery.error_type
    except Exception as exc:
        result["error_type"] = type(exc).__name__
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, sort_keys=True))
    return 0 if result["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
