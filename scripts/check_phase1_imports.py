#!/usr/bin/env python3
"""Order-free execution-image smoke test."""

from __future__ import annotations

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import nautilus_trader  # noqa: E402
import psycopg  # noqa: E402

from v3.phase1.adapters import phase1_binance_client_specs  # noqa: E402
from v3.phase1.policy import load_phase1_policy  # noqa: E402


def main() -> int:
    policy_path = Path(os.environ.get("PHASE1_POLICY_PATH", "configs/phase1-policy.json"))
    policy = load_phase1_policy(policy_path)
    specs = phase1_binance_client_specs()
    if policy.environment != "demo" or policy.live_orders or policy.real_capital:
        raise RuntimeError("unsafe Phase 1 policy")
    if any(spec.order_submission_enabled for spec in specs):
        raise RuntimeError("Phase 1A smoke unexpectedly enabled order submission")
    print(
        f"phase1_import_smoke=passed nautilus={nautilus_trader.__version__} "
        f"psycopg={psycopg.__version__} clients={len(specs)} orders=disabled"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
