"""Bounded Binance Demo node diagnostic. Never an execution entry point."""

from __future__ import annotations

import asyncio
import json
import os
import sys
import traceback
from contextlib import ExitStack, contextmanager
from datetime import UTC, datetime
from importlib.metadata import version
from unittest.mock import patch

from .adapters import build_nautilus_client_configs, canonical_instrument_id
from .binance_probe import SPOT_DEMO, USDM_DEMO, BinanceCredentials


@contextmanager
def _private_native_logs():
    """Standalone diagnostic only: suppress even Rust/native error payloads."""
    sys.stdout.flush()
    sys.stderr.flush()
    saved = [os.dup(1), os.dup(2)]
    try:
        with open(os.devnull, "w") as sink:
            os.dup2(sink.fileno(), 1)
            os.dup2(sink.fileno(), 2)
            yield
    finally:
        sys.stdout.flush()
        sys.stderr.flush()
        for target, original in zip((1, 2), saved, strict=True):
            os.dup2(original, target)
            os.close(original)


def permitted_diagnostic_request(base_url: str, method: str, path: str) -> bool:
    if base_url.rstrip("/") not in {SPOT_DEMO, USDM_DEMO} or "?" in path:
        return False
    if method == "GET":
        return path in {
            "/api/v3/time",
            "/api/v3/exchangeInfo",
            "/api/v3/account",
            "/api/v3/account/commission",
            "/fapi/v1/time",
            "/fapi/v1/exchangeInfo",
            "/fapi/v2/account",
            "/fapi/v3/account",
            "/fapi/v1/commissionRate",
            "/fapi/v1/positionSide/dual",
            "/fapi/v1/symbolConfig",
            "/fapi/v3/positionRisk",
            "/fapi/v2/positionRisk",
        }
    return method in {"POST", "PUT", "DELETE"} and path in {
        "/api/v3/userDataStream",
        "/fapi/v1/listenKey",
    }


def run_node_smoke(
    credentials: BinanceCredentials, *, timeout_seconds: float = 45, hmac_spot_compat: bool = False
) -> dict:
    if not 1 <= timeout_seconds <= 60:
        raise ValueError("diagnostic timeout must be 1..60 seconds")
    if version("nautilus-trader") != "1.231.0":
        raise ValueError("node diagnostic requires pinned Nautilus 1.231.0")
    from nautilus_trader.adapters.binance.execution import BinanceCommonExecutionClient
    from nautilus_trader.adapters.binance.factories import (
        BinanceLiveDataClientFactory,
        BinanceLiveExecClientFactory,
    )
    from nautilus_trader.adapters.binance.http.client import BinanceHttpClient
    from nautilus_trader.adapters.binance.websocket.user import BinanceUserDataWebSocketClient
    from nautilus_trader.common.config import LoggingConfig
    from nautilus_trader.live.config import LiveExecEngineConfig, TradingNodeConfig
    from nautilus_trader.live.node import TradingNode
    from nautilus_trader.model.enums import TradingState

    from .binance_hmac_stream import DemoHmacSpotUserStream, Phase1DemoExecClientFactory

    result = {
        "schema_version": 1,
        "captured_at": datetime.now(UTC).isoformat(),
        "environment": "demo",
        "diagnostic_only": True,
        "deployment_authorized": False,
        "orders_submitted": False,
        "strategies_loaded": 0,
        "connected": False,
        "stopped": False,
        "errors": [],
        "blocked_requests": [],
        "http_requests": [],
        "websocket_steps": [],
        "websocket_error_codes": [],
        "hmac_spot_compat": hmac_spot_compat,
    }
    original_send = BinanceHttpClient.send_request
    original_ws_message = BinanceUserDataWebSocketClient._handle_message

    def observe_ws_response(self, raw):
        try:
            response = json.loads(raw)
            code = response.get("error", {}).get("code")
            if type(code) is int:
                result["websocket_error_codes"].append(
                    {"product": "futures" if self._is_futures else "spot", "code": code}
                )
        except (ValueError, AttributeError, TypeError):
            pass
        return original_ws_message(self, raw)

    async def guarded_send(self, http_method, url_path, *args, **kwargs):
        method = getattr(http_method, "name", str(http_method).split(".")[-1])
        request_record = {"method": method, "path": url_path.split("?")[0]}
        result["http_requests"].append(request_record)
        if not permitted_diagnostic_request(self.base_url, method, url_path):
            # Never retain URL query, payload, account IDs, API keys or signatures.
            result["blocked_requests"].append({"method": method, "path": url_path.split("?")[0]})
            raise RuntimeError("request is outside the order-free diagnostic allowlist")
        try:
            response = await original_send(self, http_method, url_path, *args, **kwargs)
            request_record["received"] = True
            return response
        except Exception as exc:
            request_record["error"] = type(exc).__name__
            raise

    async def denied_mutation(*_args, **_kwargs):
        result["errors"].append("BlockedOrderMutation")
        raise RuntimeError("order mutation disabled in node diagnostic")

    def track_ws_step(original, name):
        async def tracked(self, *args, **kwargs):
            step = {"product": "futures" if self._is_futures else "spot", "step": name}
            result["websocket_steps"].append(step)
            try:
                value = await original(self, *args, **kwargs)
                step["completed"] = True
                return value
            except Exception as exc:
                step["error"] = type(exc).__name__
                if "Ed25519" in str(exc):
                    step["classification"] = "Ed25519_required"
                raise

        return tracked

    loop = asyncio.new_event_loop()
    loop.set_exception_handler(lambda _loop, _context: result["errors"].append("AsyncTaskFailure"))
    node = None
    with ExitStack() as guards:
        guards.enter_context(_private_native_logs())
        guards.enter_context(patch.object(BinanceHttpClient, "send_request", guarded_send))
        guards.enter_context(
            patch.object(BinanceUserDataWebSocketClient, "_handle_message", observe_ws_response)
        )
        for name in ("connect", "session_logon", "subscribe_user_data_stream"):
            guards.enter_context(
                patch.object(
                    BinanceUserDataWebSocketClient,
                    name,
                    track_ws_step(getattr(BinanceUserDataWebSocketClient, name), name),
                )
            )
        if hmac_spot_compat:
            for name in ("session_logon", "subscribe_user_data_stream"):
                guards.enter_context(
                    patch.object(
                        DemoHmacSpotUserStream,
                        name,
                        track_ws_step(getattr(DemoHmacSpotUserStream, name), name),
                    )
                )
        for name in vars(BinanceCommonExecutionClient):
            if name.startswith(("_submit_", "_cancel_", "_modify_")):
                guards.enter_context(
                    patch.object(BinanceCommonExecutionClient, name, denied_mutation)
                )
        try:
            configs = build_nautilus_client_configs(
                api_key=credentials.api_key, api_secret=credentials.api_secret
            )
            node = TradingNode(
                TradingNodeConfig(
                    trader_id="DIAGNOSTIC-001",
                    logging=LoggingConfig(log_level="ERROR"),
                    exec_engine=LiveExecEngineConfig(reconciliation=False),
                    data_clients=configs["data_clients"],
                    exec_clients=configs["execution_clients"],
                    timeout_connection=timeout_seconds,
                    timeout_disconnection=5,
                    timeout_post_stop=0.1,
                    timeout_shutdown=2,
                ),
                loop=loop,
            )
            for client_id in configs["data_clients"]:
                node.add_data_client_factory(client_id, BinanceLiveDataClientFactory)
                node.add_exec_client_factory(
                    client_id,
                    Phase1DemoExecClientFactory
                    if hmac_spot_compat
                    else BinanceLiveExecClientFactory,
                )
            node.build()
            node.kernel.risk_engine.set_trading_state(TradingState.HALTED)
            loop.run_until_complete(asyncio.wait_for(node.kernel.start_async(), timeout_seconds))
            instruments = sorted(str(i.id) for i in node.kernel.cache.instruments())
            result["instruments"] = instruments
            canonical = sorted(canonical_instrument_id(i) for i in instruments)
            result["canonical_instruments"] = canonical
            result["account_count"] = len(node.kernel.cache.accounts())
            result["account_venue_mapping_valid"] = all(
                node.kernel.cache.account_for_venue(config.venue) is not None
                for config in configs["execution_clients"].values()
            )
            result["connected"] = (
                node.kernel.data_engine.check_connected()
                and node.kernel.exec_engine.check_connected()
                and canonical == ["BTCUSDT-PERP.BINANCE", "BTCUSDT.BINANCE"]
                and result["account_count"] == 2
                and result["account_venue_mapping_valid"]
            )
        except Exception as exc:
            result["errors"].append(type(exc).__name__)
            result["failure_frames"] = [
                {
                    "module": frame.filename.rsplit("/", 1)[-1],
                    "line": frame.lineno,
                    "function": frame.name,
                }
                for frame in traceback.extract_tb(exc.__traceback__)[-4:]
            ]
        finally:
            if node is not None:
                result["instruments_at_stop"] = sorted(
                    str(i.id) for i in node.kernel.cache.instruments()
                )
                result["accounts_at_stop"] = len(node.kernel.cache.accounts())
                result["data_connected_at_stop"] = node.kernel.data_engine.check_connected()
                result["execution_connected_at_stop"] = node.kernel.exec_engine.check_connected()
                try:
                    loop.run_until_complete(asyncio.wait_for(node.stop_async(), 12))
                    result["stopped"] = (
                        node.kernel.data_engine.check_disconnected()
                        and node.kernel.exec_engine.check_disconnected()
                    )
                except Exception as exc:
                    result["errors"].append(type(exc).__name__)
                node.dispose()
            elif not loop.is_closed():
                loop.close()
    result["passed"] = bool(
        result["connected"]
        and result["stopped"]
        and not result["errors"]
        and not result["blocked_requests"]
    )
    return result
