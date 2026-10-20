"""Demo-only order validation; never addresses a matching-engine order endpoint."""

from __future__ import annotations

import hashlib
import hmac
import json
import ssl
from datetime import UTC, datetime
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request

from .binance_probe import (
    SPOT_DEMO,
    USDM_DEMO,
    BinanceCredentials,
    BinanceReadOnlyClient,
    _exchange_error_code,
    _sanitize_symbol_config,
)
from .http import RejectRedirects as RejectRedirects
from .http import secure_open


def validate_test_order(credentials, *, product, quantity, price, opener=secure_open):
    """Submit exactly one signed /order/test; caller cannot supply a URL or path."""
    if product not in {"spot", "usdm"}:
        raise ValueError("product must be spot or usdm")
    for value in (quantity, price):
        number = Decimal(value)
        if not number.is_finite() or number <= 0:
            raise ValueError("test quantity and price must be finite and positive")
    base, prefix = (SPOT_DEMO, "/api/v3") if product == "spot" else (USDM_DEMO, "/fapi/v1")
    reader = BinanceReadOnlyClient(credentials, opener=opener)
    clock = reader.get(base, prefix + "/time")
    if not clock.ok or not isinstance(clock.data, dict):
        return {"ok": False, "reason": "clock_unavailable"}
    timestamp = clock.data.get("serverTime")
    if type(timestamp) is not int:
        return {"ok": False, "reason": "clock_invalid"}
    params = {
        "symbol": "BTCUSDT",
        "side": "BUY" if product == "spot" else "SELL",
        "type": "LIMIT_MAKER" if product == "spot" else "LIMIT",
        "quantity": quantity,
        "price": price,
        "timestamp": timestamp,
        "recvWindow": 5000,
    }
    if product == "usdm":
        params["timeInForce"] = "GTX"
    body = urlencode(params)
    signature = hmac.new(credentials.api_secret.encode(), body.encode(), hashlib.sha256).hexdigest()
    req = Request(
        base + prefix + "/order/test",
        data=(body + "&signature=" + signature).encode(),
        headers={
            "X-MBX-APIKEY": credentials.api_key,
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    try:
        with opener(req, timeout=10, context=ssl.create_default_context()) as response:
            data = json.loads(response.read())
            # Spot returns {}; USD-M can return a validation-only order-shaped object.
            usdm_valid = (
                product == "usdm"
                and isinstance(data, dict)
                and data.get("symbol") == "BTCUSDT"
                and data.get("type") == "LIMIT"
                and data.get("side") == "SELL"
                and data.get("timeInForce") == "GTX"
                and Decimal(data.get("executedQty", "NaN")) == 0
                and Decimal(data.get("origQty", "NaN")) == Decimal(quantity)
                and "code" not in data
            )
            return {
                "ok": data == {} or usdm_valid,
                "http_status": response.status,
                "response_empty": data == {},
                "validation_order_response": usdm_valid,
                "reason": "validated_response"
                if data == {} or usdm_valid
                else "unverified_response_shape",
            }
    except HTTPError as exc:
        return {
            "ok": False,
            "http_status": exc.code,
            "exchange_code": _exchange_error_code(exc.read()),
        }
    except (URLError, TimeoutError, ValueError, ArithmeticError):
        return {"ok": False, "reason": "transport_or_response_invalid"}


def capture_demo_validation(credentials: BinanceCredentials, *, opener=secure_open):
    reader = BinanceReadOnlyClient(credentials, opener=opener)
    result = {"captured_at": datetime.now(UTC).isoformat(), "environment": "demo", "products": {}}
    for product, base, prefix, account_path, balance_key in (
        ("spot", SPOT_DEMO, "/api/v3", "/api/v3/account", "balances"),
        ("usdm", USDM_DEMO, "/fapi/v1", "/fapi/v3/account", "assets"),
    ):
        account = reader.get(base, account_path, signed=True, server_time_path=prefix + "/time")
        if (
            not account.ok
            or not isinstance(account.data, dict)
            or not isinstance(account.data.get(balance_key), list)
        ):
            result["products"][product] = {
                "authentication": account.status_dict(),
                "test_order": {"ok": False, "reason": "account_unavailable"},
            }
            continue
        asset = next((a for a in account.data[balance_key] if a.get("asset") == "USDT"), {})
        available = asset.get("free" if product == "spot" else "availableBalance")
        info = {
            "authentication": account.status_dict(),
            "usdt_available_positive": Decimal(available) > 0 if available is not None else None,
            "usdt_available_at_least_300": Decimal(available) >= 300
            if available is not None
            else None,
        }
        orders = reader.get(
            base,
            prefix + "/openOrders",
            signed=True,
            server_time_path=prefix + "/time",
            params={"symbol": "BTCUSDT"},
        )
        info["open_order_count"] = (
            len(orders.data) if orders.ok and isinstance(orders.data, list) else None
        )
        if product == "usdm":
            config = reader.get(
                base,
                prefix + "/symbolConfig",
                signed=True,
                server_time_path=prefix + "/time",
                params={"symbol": "BTCUSDT"},
            )
            info["symbol_config"] = _sanitize_symbol_config(config)
            positions = account.data.get("positions")
            info["nonzero_position_count"] = (
                sum(Decimal(p["positionAmt"]) != 0 for p in positions)
                if isinstance(positions, list)
                else None
            )
        quote = reader.get(base, prefix + "/ticker/bookTicker", params={"symbol": "BTCUSDT"})
        exchange = reader.get(base, prefix + "/exchangeInfo", params={"symbol": "BTCUSDT"})
        try:
            instrument = next(s for s in exchange.data["symbols"] if s["symbol"] == "BTCUSDT")
            filters = {f["filterType"]: f for f in instrument["filters"]}
            tick, step = (
                Decimal(filters["PRICE_FILTER"]["tickSize"]),
                Decimal(filters["LOT_SIZE"]["stepSize"]),
            )
            raw_price = Decimal(quote.data["bidPrice" if product == "spot" else "askPrice"])
            rounding = ROUND_FLOOR if product == "spot" else ROUND_CEILING
            price = (raw_price / tick).to_integral_value(rounding=rounding) * tick
            quantity = (Decimal("300") / price / step).to_integral_value(
                rounding=ROUND_CEILING
            ) * step
            info["test_order"] = validate_test_order(
                credentials,
                product=product,
                quantity=str(quantity),
                price=str(price),
                opener=opener,
            )
        except (KeyError, TypeError, ValueError, StopIteration, ArithmeticError):
            info["test_order"] = {"ok": False, "reason": "instrument_or_quote_invalid"}
        result["products"][product] = info
    result["safety"] = {
        "matching_engine_orders_submitted": False,
        "configuration_changed": False,
        "transfers_submitted": False,
        "balances_recorded": False,
    }
    result["validation_api_passed"] = all(
        p["test_order"]["ok"] for p in result["products"].values()
    )
    result["execution_authorized"] = False
    return result
