"""Phase 1E SLA evidence from the durable ledger; never rewrites policy.

Quote age uses only futures quotes with an exchange event timestamp. Spot
bookTicker has no exchange timestamp by design and is reported as unmeasured,
never as zero latency. Hedge latency is the wall time from the first Spot fill
to the first perp fill of the same episode, a Demo lower bound only.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import Any

from .sla import summarize_latency

MINIMUM_SAMPLES = 50


def quote_age_samples(connection, *, since: datetime | None = None) -> dict[str, Any]:
    params: list[Any] = ["BTCUSDT-PERP.BINANCE"]
    clause = ""
    if since is not None:
        clause = " AND q.received_at >= %s"
        params.append(since)
    with connection.cursor() as cursor:
        ages = [
            int(row[0])
            for row in cursor.execute(
                "SELECT q.age_ms FROM quote_observations q "
                "JOIN instrument_snapshots i ON i.id=q.instrument_snapshot_id "
                "WHERE i.instrument_id=%s AND q.timestamp_source='exchange_event' "
                "AND q.age_ms IS NOT NULL" + clause + " ORDER BY q.received_at",
                params,
            ).fetchall()
        ]
        spot_unmeasured = cursor.execute(
            "SELECT count(*) FROM quote_observations q "
            "JOIN instrument_snapshots i ON i.id=q.instrument_snapshot_id "
            "WHERE i.instrument_id='BTCUSDT.BINANCE' AND q.age_ms IS NULL"
        ).fetchone()[0]
    return {"perp_exchange_age_ms": ages, "spot_unmeasured_quotes": int(spot_unmeasured)}


def hedge_latency_samples(connection) -> list[int]:
    with connection.cursor() as cursor:
        rows = cursor.execute(
            "SELECT c.intent_id,c.leg,min(f.filled_at) FROM fills f "
            "JOIN orders o ON o.id=f.order_id JOIN order_commands c ON c.id=o.command_id "
            "WHERE c.side=CASE WHEN c.leg='spot' THEN 'buy' ELSE 'sell' END "
            "GROUP BY c.intent_id,c.leg"
        ).fetchall()
    first: dict[str, dict[str, datetime]] = {}
    for intent_id, leg, filled_at in rows:
        first.setdefault(str(intent_id), {})[leg] = filled_at
    samples = []
    for legs in first.values():
        if "spot" in legs and "perp" in legs:
            samples.append(max(0, math.ceil((legs["perp"] - legs["spot"]).total_seconds() * 1000)))
    return samples


def build_sla_evidence(
    quote_ages_ms: list[int],
    hedge_latencies_ms: list[int],
    *,
    spot_unmeasured_quotes: int,
    policy_maximum_quote_age_ms: int | None,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    generated_at = generated_at or datetime.now(UTC)
    evidence: dict[str, Any] = {
        "schema_version": 1,
        "generated_at": generated_at.isoformat(),
        "environment": "demo",
        "orders_submitted": False,
        "policy_maximum_quote_age_ms": policy_maximum_quote_age_ms,
        "policy_rewritten": False,
        "phase1e_complete": False,
        "spot_quote_exchange_age": {
            "measured": False,
            "unmeasured_quotes": spot_unmeasured_quotes,
            "reason": "Spot bookTicker has no exchange event timestamp; receive-gap is separate",
        },
        "quote_age_perp": {"sample_count": len(quote_ages_ms), "sufficient": False},
        "hedge_latency_demo_lower_bound": {
            "sample_count": len(hedge_latencies_ms),
            "sufficient": False,
        },
        "proposed_maximum_quote_age_ms": None,
        "interpretation": (
            "Proposal only. Applying maximum_quote_age_ms requires a reviewed policy commit; "
            "Demo hedge latency is a lower bound and never becomes an operating SLA"
        ),
    }
    if len(quote_ages_ms) >= MINIMUM_SAMPLES:
        summary = summarize_latency(quote_ages_ms, "quote age")
        evidence["quote_age_perp"] = {"sufficient": True, **summary.to_dict()}
        evidence["proposed_maximum_quote_age_ms"] = math.ceil(summary.p99_ms * 2)
    if len(hedge_latencies_ms) >= MINIMUM_SAMPLES:
        summary = summarize_latency(hedge_latencies_ms, "hedge latency")
        evidence["hedge_latency_demo_lower_bound"] = {"sufficient": True, **summary.to_dict()}
    return evidence
