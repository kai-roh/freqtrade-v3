#!/usr/bin/env python3
"""Summarize Phase 1E quote-age and hedge-latency samples from the ledger.

Read-only. Writes evidence JSON with a proposed maximum_quote_age_ms when at
least 50 futures exchange-age samples exist. It never edits the policy file;
adopting the value is a separate reviewed commit. Exit 3 means evidence was
written but samples are still insufficient.
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import psycopg  # noqa: E402

from v3.phase1.policy import load_phase1_policy  # noqa: E402
from v3.phase1.sla_evidence import (  # noqa: E402
    build_sla_evidence,
    hedge_latency_samples,
    quote_age_samples,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--policy", type=Path, default=Path("configs/phase1-policy.json"))
    parser.add_argument("--since", help="ISO timestamp; only quotes received at/after it")
    args = parser.parse_args()
    policy = load_phase1_policy(args.policy)
    since = datetime.fromisoformat(args.since) if args.since else None
    with psycopg.connect(os.environ["PHASE1_DATABASE_DSN"], autocommit=True) as connection:
        quotes = quote_age_samples(connection, since=since)
        hedges = hedge_latency_samples(connection)
    evidence = build_sla_evidence(
        quotes["perp_exchange_age_ms"],
        hedges,
        spot_unmeasured_quotes=quotes["spot_unmeasured_quotes"],
        policy_maximum_quote_age_ms=policy.maximum_quote_age_ms,
    )
    evidence["source_sha"] = os.environ.get("PHASE1_BUILD_SOURCE_SHA")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps(evidence, sort_keys=True))
    sufficient = evidence["quote_age_perp"]["sufficient"]
    return 0 if sufficient and evidence["hedge_latency_demo_lower_bound"]["sufficient"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
