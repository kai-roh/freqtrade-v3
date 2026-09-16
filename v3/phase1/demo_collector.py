"""Bounded order-free streaming evidence collector with durable fill quarantine."""

import asyncio
import time
from datetime import UTC, datetime
from unittest.mock import patch
from uuid import uuid4

from .binance_probe import BinanceReadOnlyClient
from .demo_node import DemoNode
from .fill_inbox import DurableFillInbox
from .node_smoke import permitted_diagnostic_request
from .observations import capture_binance_carry_market_observation
from .postgres import PostgresPhase1Ledger, QuoteObservationRow


def stream_quote_row(instrument_snapshot_id, quote):
    """Missing Spot event time remains missing, never replaced by receive time."""
    age = None
    venue = None
    if quote.venue_ns is not None:
        if quote.venue_ns <= 0 or quote.venue_ns > quote.received_ns:
            raise ValueError("invalid exchange quote timestamp")
        age = (quote.received_ns - quote.venue_ns + 999_999) // 1_000_000
        venue = datetime.fromtimestamp(quote.venue_ns / 1e9, UTC)
    return QuoteObservationRow(
        quote_id=str(uuid4()),
        instrument_snapshot_id=instrument_snapshot_id,
        bid=quote.bid,
        ask=quote.ask,
        received_at=datetime.fromtimestamp(quote.received_ns / 1e9, UTC),
        collection_mode="phase1e_sample",
        venue_timestamp=venue,
        age_ms=age,
        timestamp_source="exchange_event" if venue else "unavailable",
    )


def collect_demo_stream(credentials, connection, *, seconds=60):
    loop = asyncio.new_event_loop()
    runtimes = []
    try:
        return loop.run_until_complete(
            _collect_demo_stream(credentials, connection, seconds=seconds, runtimes=runtimes)
        )
    finally:
        for runtime in runtimes:
            runtime.dispose()
        if not loop.is_closed():
            loop.close()


async def _collect_demo_stream(credentials, connection, *, seconds, runtimes):
    """Collect only. HTTP mutation paths for orders are blocked independently of strategy."""
    if not 5 <= seconds <= 3600:
        raise ValueError("collection duration must be 5..3600 seconds")
    from nautilus_trader.adapters.binance.http.client import BinanceHttpClient

    observation = await asyncio.to_thread(
        capture_binance_carry_market_observation, BinanceReadOnlyClient()
    )
    ledger = PostgresPhase1Ledger(connection)
    snapshots = {}
    for instrument in (observation.spot_instrument, observation.perp_instrument):
        ledger.add_instrument_snapshot(instrument.to_postgres_row())
        snapshots[instrument.instrument_id] = instrument.id
    connection.commit()
    inbox = DurableFillInbox(connection)
    counts = dict.fromkeys(snapshots, 0)
    last = dict.fromkeys(snapshots, float("-inf"))

    def quote_sink(canonical, quote):
        if time.monotonic() - last[canonical] < 1:
            return
        ledger.add_quote_observation(stream_quote_row(snapshots[canonical], quote))
        connection.commit()
        last[canonical] = time.monotonic()
        counts[canonical] += 1

    def fill_sink(event):
        receipt = inbox.receive(event)
        if inbox.process(receipt) != "APPLIED":
            raise ValueError("fill reconciliation blocked")

    original = BinanceHttpClient.send_request

    async def read_only_request(client, http_method, url_path, *args, **kwargs):
        method = getattr(http_method, "name", str(http_method).split(".")[-1])
        if not permitted_diagnostic_request(client.base_url, method, url_path):
            raise ValueError("collector HTTP order boundary")
        return await original(client, http_method, url_path, *args, **kwargs)

    runtime = DemoNode(
        credentials,
        fill_sink=fill_sink,
        quote_sink=quote_sink,
        loop=asyncio.get_running_loop(),
    )
    runtimes.append(runtime)
    with patch.object(BinanceHttpClient, "send_request", read_only_request):
        try:
            await runtime.start()
            deadline = time.monotonic() + seconds
            while time.monotonic() < deadline:
                if runtime.strategy.failure:
                    raise ValueError("durable stream callback failed")
                if not runtime.node.kernel.exec_engine.check_connected():
                    raise ValueError("Demo account stream disconnected")
                await asyncio.sleep(0.1)
        finally:
            await runtime.stop()
    if any(count < 2 for count in counts.values()):
        raise ValueError("insufficient two-leg stream evidence")
    return {
        "environment": "demo",
        "orders_submitted": False,
        "quote_samples": counts,
        "spot_exchange_age_measured": False,
        "passed": True,
    }
