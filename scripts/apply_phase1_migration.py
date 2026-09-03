#!/usr/bin/env python3
"""Apply the Phase 1 PostgreSQL migration using an explicitly supplied DSN."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MIGRATION_ROOT = PROJECT_ROOT / "v3" / "phase1" / "migrations"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--direction", choices=("up", "down"), default="up")
    parser.add_argument("--dsn-env", default="PHASE1_DATABASE_DSN")
    parser.add_argument("--allow-destructive-rollback", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.direction == "down" and not args.allow_destructive_rollback:
        print("rollback requires --allow-destructive-rollback", file=sys.stderr)
        return 2
    dsn = os.environ.get(args.dsn_env, "").strip()
    if not dsn:
        print(f"missing database DSN in {args.dsn_env}", file=sys.stderr)
        return 2
    try:
        import psycopg
    except ImportError:
        print("install the locked execution dependencies first", file=sys.stderr)
        return 2

    migration = MIGRATION_ROOT / f"0001_phase1_ledger.{args.direction}.sql"
    try:
        with psycopg.connect(dsn, autocommit=True) as connection:
            connection.execute(migration.read_text())
    except (OSError, psycopg.Error) as exc:
        print(f"migration failed: {exc}", file=sys.stderr)
        return 2
    print(f"migration={migration.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
