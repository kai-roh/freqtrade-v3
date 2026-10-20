import os
from datetime import UTC, datetime

import pytest
from test_phase1_entry_gateway import _isolated_database

from v3.phase1.postgres import apply_migrations
from v3.phase1.sla_evidence import build_sla_evidence, hedge_latency_samples, quote_age_samples


def test_insufficient_samples_never_propose_a_quote_sla():
    evidence = build_sla_evidence(
        [10] * 49,
        [],
        spot_unmeasured_quotes=75,
        policy_maximum_quote_age_ms=None,
        generated_at=datetime(2026, 9, 15, tzinfo=UTC),
    )
    assert evidence["proposed_maximum_quote_age_ms"] is None
    assert evidence["quote_age_perp"] == {"sample_count": 49, "sufficient": False}
    assert evidence["spot_quote_exchange_age"]["measured"] is False
    assert evidence["policy_rewritten"] is False and evidence["phase1e_complete"] is False


def test_sufficient_quote_samples_propose_p99_with_100_percent_margin_only():
    evidence = build_sla_evidence(
        list(range(50)),
        [5] * 10,
        spot_unmeasured_quotes=0,
        policy_maximum_quote_age_ms=None,
    )
    assert evidence["quote_age_perp"]["sufficient"] is True
    assert evidence["proposed_maximum_quote_age_ms"] == 98
    assert evidence["hedge_latency_demo_lower_bound"]["sufficient"] is False
    assert "reviewed policy commit" in evidence["interpretation"]


def test_ledger_queries_return_no_samples_on_an_empty_schema():
    dsn = os.getenv("PHASE1_TEST_DATABASE_DSN")
    if not dsn:
        pytest.skip("PHASE1_TEST_DATABASE_DSN not set")
    with _isolated_database(dsn) as db:
        apply_migrations(db)
        assert quote_age_samples(db) == {"perp_exchange_age_ms": [], "spot_unmeasured_quotes": 0}
        assert hedge_latency_samples(db) == []
