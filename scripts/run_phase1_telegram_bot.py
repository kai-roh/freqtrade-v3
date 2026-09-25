#!/usr/bin/env python3
"""Serve read-only Telegram commands for the Phase 1 Demo run.

Reads TELEGRAM_TOKEN / TELEGRAM_CHAT_ID and Demo credentials from the mounted
env file, PHASE1_DATABASE_DSN from the environment, and the runner evidence
directory. Replies only to the configured chat. No order transport exists here.
"""

import argparse
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import psycopg  # noqa: E402

from v3.phase1.binance_probe import load_dotenv_credentials  # noqa: E402
from v3.phase1.demo_inspector import DemoInspector  # noqa: E402
from v3.phase1.telegram_bot import (  # noqa: E402
    TelegramApi,
    handle_update,
    load_ledger_facts,
    load_run_evidence,
)


def _env_values(path: Path) -> dict[str, str]:
    values = {}
    for line in path.read_text().splitlines():
        name, sep, value = line.partition("=")
        if sep and name.strip() in {"TELEGRAM_TOKEN", "TELEGRAM_CHAT_ID"}:
            values[name.strip()] = value.strip().strip("\"'")
    return values


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--credentials-env-file", type=Path, required=True)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--register-commands", action="store_true")
    parser.add_argument("--once", action="store_true", help="poll once and exit (diagnostics)")
    args = parser.parse_args()
    values = _env_values(args.credentials_env_file)
    api = TelegramApi(values.get("TELEGRAM_TOKEN", ""))
    chat_id = values.get("TELEGRAM_CHAT_ID", "")
    if not chat_id:
        raise SystemExit("TELEGRAM_CHAT_ID is required")
    credentials = load_dotenv_credentials(args.credentials_env_file, "BINANCE_DEMO")
    inspector = DemoInspector(credentials) if credentials else None
    dsn = os.environ["PHASE1_DATABASE_DSN"]
    if args.register_commands:
        api.register_commands()
        print("commands registered", flush=True)

    def facts():
        with psycopg.connect(
            dsn, autocommit=True, options="-c default_transaction_read_only=on"
        ) as connection:
            return load_ledger_facts(connection)

    def account():
        if inspector is None:
            raise ValueError("Demo credentials unavailable")
        return inspector.account()

    offset = None
    while True:
        try:
            updates = api.updates(offset)
        except Exception as exc:  # noqa: BLE001 - transport hiccups must not kill the bot.
            print(f"poll failed: {type(exc).__name__}", flush=True)
            time.sleep(5)
            if args.once:
                return 1
            continue
        for update in updates:
            offset = int(update["update_id"]) + 1
            reply = handle_update(
                update,
                chat_id=chat_id,
                facts_loader=facts,
                run_loader=lambda: load_run_evidence(args.evidence_dir),
                account_loader=account,
            )
            if reply is not None:
                try:
                    api.send(*reply)
                except Exception as exc:  # noqa: BLE001
                    print(f"send failed: {type(exc).__name__}", flush=True)
        if args.once:
            return 0


if __name__ == "__main__":
    raise SystemExit(main())
