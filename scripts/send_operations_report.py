#!/usr/bin/env python3
"""Collect and deliver one V3 daily or weekly operations report."""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from v3.reporting import (  # noqa: E402
    ReportError,
    atomic_write,
    build_report,
    collect_operations,
    load_research_summary,
    send_telegram,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("period", choices=("daily", "weekly"))
    parser.add_argument("--telegram-always", action="store_true")
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--output-root", type=Path, default=Path("reports"))
    parser.add_argument(
        "--research-results",
        type=Path,
        default=Path(
            os.getenv("V3_RESEARCH_RESULTS", "research_results/scheduled/latest/results.json")
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    timezone_name = os.getenv("REPORT_TZ", "Asia/Seoul")
    try:
        now = datetime.now(ZoneInfo(timezone_name))
    except ZoneInfoNotFoundError:
        print("report timezone is invalid", file=sys.stderr)
        return 2

    try:
        payloads = collect_operations(
            os.getenv("FT_API_BASE", "http://127.0.0.1:8080/api/v1"),
            os.getenv("FREQTRADE_USERNAME", ""),
            os.getenv("FREQTRADE_PASSWORD", ""),
            args.period,
        )
        research = load_research_summary(args.research_results)
        markdown, telegram_text = build_report(
            args.period,
            payloads,
            generated_at=now,
            research=research,
        )
        if not args.no_write:
            report_path = args.output_root / args.period / f"{now.date().isoformat()}.md"
            atomic_write(report_path, markdown)
            print(f"report={report_path}")
        print(telegram_text)
        if args.telegram_always:
            send_telegram(
                telegram_text,
                os.getenv("TELEGRAM_TOKEN", ""),
                os.getenv("TELEGRAM_CHAT_ID", ""),
            )
            print("telegram=sent")
    except ReportError as exc:
        print(f"report failed: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
