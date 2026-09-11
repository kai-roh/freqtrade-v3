import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UP = ROOT / "v3" / "phase1" / "migrations" / "0001_phase1_ledger.up.sql"
DOWN = ROOT / "v3" / "phase1" / "migrations" / "0001_phase1_ledger.down.sql"
QUOTE_UP = ROOT / "v3" / "phase1" / "migrations" / "0002_quote_provenance.up.sql"


def test_phase1_migration_defines_14_tables_with_exact_numeric_and_utc_types():
    sql = UP.read_text()
    tables = re.findall(r"CREATE TABLE ([a-z_]+)", sql)

    assert len(tables) == 14
    assert "internal_transfers" in tables
    assert "state_transitions" in tables
    assert "NUMERIC" in sql
    assert "TIMESTAMPTZ" in sql
    assert "DOUBLE PRECISION" not in sql
    assert " REAL" not in sql


def test_order_fill_and_transfer_idempotency_are_database_constraints():
    sql = UP.read_text()

    assert "idempotency_key VARCHAR(32) NOT NULL UNIQUE" in sql
    assert "one_active_command_per_intent_leg" in sql
    assert "UNIQUE (venue, venue_fill_id)" in sql
    assert re.search(r"internal_transfers[\s\S]+idempotency_key TEXT NOT NULL UNIQUE", sql)


def test_down_migration_removes_every_created_table_in_reverse_dependency_order():
    created = re.findall(r"CREATE TABLE ([a-z_]+)", UP.read_text())
    dropped = re.findall(r"DROP TABLE IF EXISTS ([a-z_]+)", DOWN.read_text())

    assert dropped == list(reversed(created))


def test_quote_provenance_migration_keeps_rest_quotes_from_claiming_exchange_age():
    sql = QUOTE_UP.read_text()

    assert "ALTER COLUMN venue_timestamp DROP NOT NULL" in sql
    assert "ALTER COLUMN age_ms DROP NOT NULL" in sql
    assert "transport_rtt_ms BIGINT" in sql
    assert "timestamp_source" in sql
    assert "quote_observations_timestamp_consistency" in sql
