#!/usr/bin/env python3
"""Settle one closing Demo episode's unsellable Spot residual without any order.

This is an explicit, audited, order-free operation. It refuses to run unless the
episode has a persisted close request, futures are flat, no BTC orders are open,
all fills are applied, and the remaining Spot is below the venue sell minimum.
The residual stays in the account and is inherited by the next episode baseline.
"""

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import psycopg  # noqa: E402

from v3.phase1.binance_probe import BinanceReadOnlyClient, load_dotenv_credentials  # noqa: E402
from v3.phase1.demo_inspector import DemoInspector  # noqa: E402
from v3.phase1.episode_lifecycle import (  # noqa: E402
    reconcile_episode_state,
    settle_episode_residual,
)
from v3.phase1.episode_plan import EpisodeLimits  # noqa: E402
from v3.phase1.notifications import Phase1Notification, send_phase1_telegram  # noqa: E402
from v3.phase1.observations import capture_binance_carry_market_observation  # noqa: E402
from v3.phase1.postgres import apply_migrations  # noqa: E402


def _telegram(path):
    values = {}
    for line in path.read_text().splitlines():
        name, sep, value = line.partition("=")
        if sep and name.strip() in {"TELEGRAM_TOKEN", "TELEGRAM_CHAT_ID"}:
            values[name.strip()] = value.strip().strip("\"'")
    return values


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--credentials-env-file", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--intent-id", required=True)
    parser.add_argument("--settle-residual", action="store_true", required=True)
    parser.add_argument("--notify", action="store_true")
    args = parser.parse_args()
    result = {
        "environment": "demo",
        "orders_submitted": False,
        "economic_approval": False,
        "captured_at": datetime.now(UTC).isoformat(),
        "intent_id": args.intent_id,
        "source_sha": os.environ.get("PHASE1_BUILD_SOURCE_SHA"),
        "image_digest": os.environ.get("PHASE1_IMAGE_DIGEST"),
    }
    exit_code = 2
    try:
        credentials = load_dotenv_credentials(args.credentials_env_file, "BINANCE_DEMO")
        if credentials is None:
            raise ValueError("dedicated Demo credentials required")
        observation = capture_binance_carry_market_observation(BinanceReadOnlyClient())
        spot, perp = observation.spot_instrument, observation.perp_instrument
        limits = EpisodeLimits(
            spot.lot_size,
            perp.lot_size,
            spot.minimum_notional,
            perp.minimum_notional,
            observation.spot_quote.bid,
            observation.spot_quote.ask,
            observation.perp_quote.bid,
            observation.perp_quote.ask,
        )
        inspector = DemoInspector(credentials)
        with psycopg.connect(os.environ["PHASE1_DATABASE_DSN"], autocommit=True) as connection:
            apply_migrations(connection)
            before = connection.execute(
                "SELECT state FROM intents WHERE id=%s", (args.intent_id,)
            ).fetchone()
            if before is None:
                raise ValueError("unknown intent")
            result["state_before"] = before[0]
            account = inspector.account()
            result["account_before"] = {
                "spot_total_btc": str(account["spot_total_btc"]),
                "perp_btc": str(account["perp_qty"]),
                "open_btc_orders": len(account["open_orders"]),
            }
            settled = settle_episode_residual(
                connection, intent_id=args.intent_id, account=account, limits=limits
            )
            result["settlement"] = settled
            account = inspector.account()
            lifecycle = reconcile_episode_state(
                connection, intent_id=args.intent_id, account=account, limits=limits
            )
            result["lifecycle_after"] = lifecycle
            result["account_after"] = {
                "spot_total_btc": str(account["spot_total_btc"]),
                "perp_btc": str(account["perp_qty"]),
                "open_btc_orders": len(account["open_orders"]),
            }
            result["open_intents"] = connection.execute(
                "SELECT count(*) FROM intents WHERE state<>'CLOSED'"
            ).fetchone()[0]
        result["passed"] = lifecycle["state"] == "CLOSED" and result["open_intents"] == 0
        exit_code = 0 if result["passed"] else 2
    except Exception as exc:
        result["error_type"] = type(exc).__name__
        result["error"] = str(exc)[:200]
        result["passed"] = False
    if args.notify:
        values = _telegram(args.credentials_env_file)
        delivery = send_phase1_telegram(
            Phase1Notification(
                "stop" if result["passed"] else "error",
                "잔량 정산",
                "매도 없이 소유 잔량으로 기록",
                datetime.now(UTC),
                {
                    "passed": result["passed"],
                    "residual_base": result.get("settlement", {}).get("residual_base"),
                    "state": result.get("lifecycle_after", {}).get("state"),
                    "error_type": result.get("error_type"),
                },
            ),
            token=values.get("TELEGRAM_TOKEN", ""),
            chat_id=values.get("TELEGRAM_CHAT_ID", ""),
        )
        result["telegram_delivered"] = delivery.delivered
        result["telegram_error_type"] = delivery.error_type
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True, default=str) + "\n")
    print(json.dumps(result, sort_keys=True, default=str))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
