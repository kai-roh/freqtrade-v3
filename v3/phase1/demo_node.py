"""Pinned Demo node with a single coordinator-owned strategy and durable callbacks."""

import asyncio
import time
from dataclasses import dataclass
from decimal import Decimal
from importlib.metadata import version

from nautilus_trader.adapters.binance.factories import BinanceLiveDataClientFactory
from nautilus_trader.common.config import LoggingConfig
from nautilus_trader.live.config import LiveExecEngineConfig, TradingNodeConfig
from nautilus_trader.live.node import TradingNode
from nautilus_trader.model.enums import OrderSide, TimeInForce
from nautilus_trader.model.identifiers import ClientOrderId, InstrumentId
from nautilus_trader.trading.strategy import Strategy

from .adapters import (
    NAUTILUS_INSTRUMENT_IDS,
    build_nautilus_client_configs,
    canonical_instrument_id,
)
from .binance_hmac_stream import Phase1DemoExecClientFactory


@dataclass(frozen=True)
class DemoQuote:
    bid: Decimal
    ask: Decimal
    received_ns: int
    received_monotonic: float
    venue_ns: int | None

    def gap_ms(self):
        return (time.monotonic() - self.received_monotonic) * 1000


class DemoStrategy(Strategy):
    def __init__(self, *, fill_sink, quote_sink):
        super().__init__()
        self.fill_sink = fill_sink
        self.quote_sink = quote_sink
        self.quotes = {}
        self.failure = None
        self.orders_enabled = False

    def on_start(self):
        for runtime in NAUTILUS_INSTRUMENT_IDS.values():
            self.subscribe_quote_ticks(InstrumentId.from_str(runtime))

    def on_quote_tick(self, tick):
        canonical = canonical_instrument_id(str(tick.instrument_id))
        quote = DemoQuote(
            tick.bid_price.as_decimal(),
            tick.ask_price.as_decimal(),
            time.time_ns(),
            time.monotonic(),
            tick.ts_event if canonical.endswith("-PERP.BINANCE") else None,
        )
        self.quotes[canonical] = quote
        try:
            self.quote_sink(canonical, quote)
        except Exception as exc:
            self.failure = type(exc).__name__
            self.orders_enabled = False

    def on_order_filled(self, event):
        try:
            self.fill_sink(event)
        except Exception as exc:
            self.failure = type(exc).__name__
            self.orders_enabled = False

    def prepare_limit(
        self, *, canonical, side, quantity, price, client_id, post_only, reduce_only=False
    ):
        if canonical not in NAUTILUS_INSTRUMENT_IDS or side not in {"buy", "sell"}:
            raise ValueError("unsupported trial instrument or side")
        if reduce_only and canonical == "BTCUSDT.BINANCE":
            raise ValueError("Spot has no reduce-only instruction")
        instrument = self.cache.instrument(
            InstrumentId.from_str(NAUTILUS_INSTRUMENT_IDS[canonical])
        )
        if instrument is None:
            raise ValueError("instrument not loaded")
        qty, px = instrument.make_qty(quantity), instrument.make_price(price)
        if qty.as_decimal() != quantity or px.as_decimal() != price:
            raise ValueError("order precision must be validated before submission")
        return self.order_factory.limit(
            instrument_id=instrument.id,
            order_side=OrderSide.BUY if side == "buy" else OrderSide.SELL,
            quantity=qty,
            price=px,
            client_order_id=ClientOrderId(client_id),
            post_only=post_only,
            time_in_force=TimeInForce.GTC if post_only else TimeInForce.IOC,
            reduce_only=reduce_only,
        )

    def submit_prepared(self, order):
        if not self.orders_enabled or self.failure:
            raise ValueError("Demo strategy submission is disabled")
        self.submit_order(order)

    def cancel_owned(self, client_id):
        order = self.cache.order(ClientOrderId(client_id))
        if order is None or order.strategy_id != self.id:
            raise ValueError("cannot cancel an unknown or foreign order")
        if not order.is_closed:
            self.cancel_order(order)

    def order(self, client_id):
        return self.cache.order(ClientOrderId(client_id))


class DemoNode:
    def __init__(self, credentials, *, fill_sink, quote_sink, loop):
        if version("nautilus-trader") != "1.231.0":
            raise ValueError("Demo runtime requires Nautilus 1.231.0")
        configs = build_nautilus_client_configs(
            api_key=credentials.api_key, api_secret=credentials.api_secret
        )
        self.node = TradingNode(
            TradingNodeConfig(
                trader_id="V3TRIAL-001",
                logging=LoggingConfig(log_level="ERROR"),
                exec_engine=LiveExecEngineConfig(reconciliation=False),
                data_clients=configs["data_clients"],
                exec_clients=configs["execution_clients"],
                timeout_connection=40,
                timeout_disconnection=5,
                timeout_post_stop=0.1,
                timeout_shutdown=2,
            ),
            loop=loop,
        )
        self.strategy = DemoStrategy(fill_sink=fill_sink, quote_sink=quote_sink)
        self.node.trader.add_strategy(self.strategy)
        for client_id in configs["data_clients"]:
            self.node.add_data_client_factory(client_id, BinanceLiveDataClientFactory)
            self.node.add_exec_client_factory(client_id, Phase1DemoExecClientFactory)
        self.node.build()

    async def start(self):
        await asyncio.wait_for(self.node.kernel.start_async(), 45)
        if not self.node.kernel.exec_engine.check_connected():
            raise ValueError("Demo execution clients not connected")
        deadline = time.monotonic() + 30
        while set(self.strategy.quotes) != set(NAUTILUS_INSTRUMENT_IDS):
            if time.monotonic() >= deadline or self.strategy.failure:
                raise ValueError("Demo quote streams not ready")
            await asyncio.sleep(0.1)

    async def stop(self):
        self.strategy.orders_enabled = False
        await asyncio.wait_for(self.node.stop_async(), 15)

    def dispose(self):
        self.node.dispose()
