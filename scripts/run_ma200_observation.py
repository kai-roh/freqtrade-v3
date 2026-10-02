#!/usr/bin/env python3
"""Order-free daily MA200 forward observation: recompute, save, and send the Telegram report.

Reads public candles already refreshed on disk, never touches an account, and
never submits an order. Exit 3 means the report was written but an operational
check failed (stale data or a skipped virtual order).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from v3.phase1.notifications import send_telegram_text  # noqa: E402
from v3.phase2.data import load_phase2_panel  # noqa: E402
from v3.phase2c.observation import (  # noqa: E402
    ObservationInputs,
    observe,
    reconcile_live,
    render_message,
)
from v3.phase2c.research import load_spot_filters, load_venue_filters  # noqa: E402
from v3.phase2c.trend import SYMBOLS, load_spot_panel  # noqa: E402


def _telegram_credentials(path: Path | None) -> dict[str, str]:
    values: dict[str, str] = {}
    if path is None or not path.is_file():
        return values
    for line in path.read_text().splitlines():
        name, sep, value = line.partition("=")
        if sep and name.strip() in {"TELEGRAM_TOKEN", "TELEGRAM_CHAT_ID"}:
            values[name.strip()] = value.strip().strip("\"'")
    return values


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--perp-dir", type=Path, required=True)
    parser.add_argument("--spot-dir", type=Path, required=True)
    parser.add_argument("--perp-filters", type=Path, required=True)
    parser.add_argument("--spot-filters", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--credentials-env-file", type=Path)
    parser.add_argument("--send-telegram", action="store_true")
    parser.add_argument("--now", help="ISO time for replays and tests; default is the clock")
    parser.add_argument(
        "--live-state-dir", type=Path, help="executor state to reconcile (read-only)"
    )
    args = parser.parse_args()
    now = pd.Timestamp(args.now) if args.now else pd.Timestamp.now(tz="UTC")
    inputs = ObservationInputs(
        perp=load_phase2_panel(args.perp_dir, manifest_path=None, symbols=SYMBOLS),
        spot=load_spot_panel(args.spot_dir, manifest_path=None),
        perp_filters=load_venue_filters(args.perp_filters),
        spot_filters=load_spot_filters(args.spot_filters),
    )
    report = observe(inputs, now=now)
    heartbeat = args.live_state_dir / "heartbeat.json" if args.live_state_dir else None
    if heartbeat is not None and heartbeat.is_file():
        reconcile_live(report, json.loads(heartbeat.read_text()).get("positions"))
    kst = now + pd.Timedelta(hours=9)
    message = render_message(report, weekly=kst.weekday() == 0, monthly=kst.day == 1)
    report["message"] = message
    report["source_sha"] = os.environ.get("PHASE1_BUILD_SOURCE_SHA")
    if args.send_telegram:
        creds = _telegram_credentials(args.credentials_env_file)
        delivery = send_telegram_text(
            message,
            token=creds.get("TELEGRAM_TOKEN", ""),
            chat_id=creds.get("TELEGRAM_CHAT_ID", ""),
        )
        report["telegram_delivered"] = delivery.delivered
        report["telegram_error_type"] = delivery.error_type
    args.output_dir.mkdir(parents=True, exist_ok=True)
    body = json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"
    (args.output_dir / f"observation-{kst:%Y%m%d}.json").write_text(body)
    (args.output_dir / "latest.json").write_text(body)
    print(message)
    return 0 if all(report["checks"].values()) else 3


if __name__ == "__main__":
    raise SystemExit(main())
