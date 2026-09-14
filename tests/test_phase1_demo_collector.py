import asyncio
from decimal import Decimal

import pytest

from v3.phase1.demo_collector import stream_quote_row
from v3.phase1.demo_inspector import DemoInspector
from v3.phase1.demo_node import DemoQuote


@pytest.mark.parametrize("fail", [False, True])
def test_node_disposed_only_after_owned_loop_stops(monkeypatch, fail):
    from v3.phase1 import demo_collector

    disposed = []

    class Runtime:
        def __init__(self):
            self.loop = asyncio.get_running_loop()

        def dispose(self):
            assert not self.loop.is_running()
            disposed.append(True)

    async def collect(credentials, connection, *, seconds, runtimes):
        runtimes.append(Runtime())
        if fail:
            raise ValueError("fixture failure")
        return {"passed": True}

    monkeypatch.setattr(demo_collector, "_collect_demo_stream", collect)
    if fail:
        with pytest.raises(ValueError, match="fixture failure"):
            demo_collector.collect_demo_stream(None, None)
    else:
        assert demo_collector.collect_demo_stream(None, None) == {"passed": True}
    assert disposed == [True]


def test_migration_discovery_ignores_macos_resource_forks(tmp_path, monkeypatch):
    from v3.phase1 import postgres

    (tmp_path / "0001_test.up.sql").write_text("SELECT 1;")
    (tmp_path / "._0001_test.up.sql").write_bytes(b"\x00\xff")
    monkeypatch.setattr(postgres, "MIGRATION_ROOT", tmp_path)
    assert [path.name for path in postgres.migration_paths()] == ["0001_test.up.sql"]


def test_spot_quote_does_not_invent_exchange_age():
    quote = DemoQuote(Decimal(100), Decimal(101), 2_000_000_000, 1.0, None)
    row = stream_quote_row("snapshot", quote)
    assert row.age_ms is None
    assert row.venue_timestamp is None
    assert row.timestamp_source == "unavailable"


def test_perp_quote_age_rounds_up():
    quote = DemoQuote(Decimal(100), Decimal(101), 2_000_000_000, 1.0, 1_999_999_999)
    assert stream_quote_row("snapshot", quote).age_ms == 1


@pytest.mark.parametrize("timestamp", [0, -1, 2_000_000_001])
def test_invalid_quote_timestamp_rejected(timestamp):
    with pytest.raises(ValueError, match="timestamp"):
        stream_quote_row(
            "snapshot", DemoQuote(Decimal(100), Decimal(101), 2_000_000_000, 1, timestamp)
        )


def test_inspector_rejects_unknown_leg_before_request():
    inspector = DemoInspector(None)
    with pytest.raises(ValueError, match="unknown Demo leg"):
        inspector.order("mainnet", "client")


def test_inspector_refuses_truncated_fill_history():
    inspector = DemoInspector(None)
    inspector.get = lambda *args: [{}] * 1000
    with pytest.raises(ValueError, match="pagination"):
        inspector.fills("spot", "123")
