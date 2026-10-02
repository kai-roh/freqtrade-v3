"""Signed Binance USD-M REST client for the MA200 executor and guard (Decision 0020).

Allowlisted endpoints and symbols only. Demo is the default environment.
Mainnet requires an authorization record naming a real-capital decision, and
none exists, so Mainnet construction fails today. Market data for signals
always comes from the Mainnet public endpoints, which need no credentials.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import ssl
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from decimal import ROUND_DOWN, ROUND_UP, Decimal
from typing import Any
from urllib.parse import urlencode

DEMO_BASE = "https://demo-fapi.binance.com"
MAINNET_BASE = "https://fapi.binance.com"
SYMBOLS = ("BTCUSDT", "ETHUSDT")

PUBLIC = {
    ("GET", "/fapi/v1/time"),
    ("GET", "/fapi/v1/exchangeInfo"),
    ("GET", "/fapi/v1/ticker/bookTicker"),
    ("GET", "/fapi/v1/klines"),
    ("GET", "/fapi/v1/premiumIndex"),
}
SIGNED = {
    ("GET", "/fapi/v3/positionRisk"),
    ("GET", "/fapi/v1/order"),
    ("GET", "/fapi/v1/openOrders"),
    ("GET", "/fapi/v1/income"),
    ("GET", "/fapi/v1/symbolConfig"),
    ("POST", "/fapi/v1/order"),
    ("POST", "/fapi/v1/leverage"),
    ("POST", "/fapi/v1/marginType"),
    ("DELETE", "/fapi/v1/allOpenOrders"),
}
# (method, url, headers, body) -> (http status, parsed JSON)
Transport = Callable[[str, str, Mapping[str, str], bytes | None], tuple[int, Any]]


class ExchangeError(Exception):
    def __init__(self, status: int | None, code: int | None, message: str):
        super().__init__(f"{status} {code} {message}")
        self.status = status
        self.code = code


@dataclass(frozen=True)
class Credentials:
    api_key: str
    api_secret: str


def urllib_transport(timeout: float = 10.0) -> Transport:
    context = ssl.create_default_context()

    def send(method, url, headers, body):
        request = urllib.request.Request(url, data=body, headers=dict(headers), method=method)
        try:
            with urllib.request.urlopen(request, timeout=timeout, context=context) as response:
                return response.status, json.loads(response.read() or b"null")
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            try:
                return exc.code, json.loads(raw or b"null")
            except json.JSONDecodeError:
                return exc.code, {"msg": raw.decode(errors="replace")[:200]}

    return send


class FuturesClient:
    def __init__(
        self,
        environment: str,
        credentials: Credentials | None,
        *,
        authorization: Mapping[str, Any] | None = None,
        transport: Transport | None = None,
        public_transport: Transport | None = None,
    ):
        if environment == "mainnet":
            if not (
                authorization
                and authorization.get("real_capital_authorized") is True
                and str(authorization.get("decision", "")).strip()
            ):
                raise PermissionError("Mainnet orders need a recorded real-capital decision")
            self.base = MAINNET_BASE
        elif environment == "demo":
            self.base = DEMO_BASE
        else:
            raise ValueError("environment must be demo or mainnet")
        self.environment = environment
        self.credentials = credentials
        self._transport = transport or urllib_transport()
        # Public Mainnet candles need no credentials; the same transport can carry them.
        self._public = public_transport or self._transport
        self._offset_ms: int | None = None

    # ------------------------------------------------------------------ transport
    def _call(
        self,
        method: str,
        path: str,
        params: Mapping[str, Any] | None,
        *,
        signed: bool,
        base: str | None = None,
        transport: Transport | None = None,
    ) -> Any:
        key = (method, path)
        if key not in (SIGNED if signed else PUBLIC):
            raise PermissionError(f"{method} {path} is not allowlisted")
        query = {k: v for k, v in (params or {}).items() if v is not None}
        if "symbol" in query and query["symbol"] not in SYMBOLS:
            raise PermissionError(f"symbol {query['symbol']} is not allowed")
        headers: dict[str, str] = {}
        if signed:
            if self.credentials is None:
                raise PermissionError("signed request needs credentials")
            query["timestamp"] = self._now_ms()
            query["recvWindow"] = 5000
            payload = urlencode(query)
            query["signature"] = hmac.new(
                self.credentials.api_secret.encode(), payload.encode(), hashlib.sha256
            ).hexdigest()
            headers["X-MBX-APIKEY"] = self.credentials.api_key
        url = (base or self.base) + path
        body = None
        if method == "POST":
            body = urlencode(query).encode()
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        elif query:
            url += "?" + urlencode(query)
        status, data = (transport or self._transport)(method, url, headers, body)
        if status is None or status >= 400:
            code = data.get("code") if isinstance(data, Mapping) else None
            message = data.get("msg", "") if isinstance(data, Mapping) else str(data)
            raise ExchangeError(status, code, message)
        return data

    def _now_ms(self) -> int:
        if self._offset_ms is None:
            data = self._call("GET", "/fapi/v1/time", None, signed=False)
            self._offset_ms = int(data["serverTime"]) - int(time.time() * 1000)
        return int(time.time() * 1000) + self._offset_ms

    # --------------------------------------------------------------- market data
    def public_daily_klines(self, symbol: str, limit: int = 400) -> list[list[Any]]:
        """Mainnet public daily candles (signals are computed from the real market)."""
        return self._call(
            "GET",
            "/fapi/v1/klines",
            {"symbol": symbol, "interval": "1d", "limit": limit},
            signed=False,
            base=MAINNET_BASE,
            transport=self._public,
        )

    def book(self, symbol: str) -> dict[str, Decimal]:
        data = self._call("GET", "/fapi/v1/ticker/bookTicker", {"symbol": symbol}, signed=False)
        return {"bid": Decimal(data["bidPrice"]), "ask": Decimal(data["askPrice"])}

    def filters(self) -> dict[str, dict[str, Decimal]]:
        data = self._call("GET", "/fapi/v1/exchangeInfo", None, signed=False)
        out = {}
        for row in data["symbols"]:
            if row["symbol"] not in SYMBOLS:
                continue
            by_type = {f["filterType"]: f for f in row["filters"]}
            out[row["symbol"]] = {
                "step": Decimal(by_type["LOT_SIZE"]["stepSize"]),
                "min_qty": Decimal(by_type["LOT_SIZE"]["minQty"]),
                "tick": Decimal(by_type["PRICE_FILTER"]["tickSize"]),
                "min_notional": Decimal(by_type["MIN_NOTIONAL"]["notional"]),
            }
        return out

    # ------------------------------------------------------------------- account
    def positions(self) -> dict[str, dict[str, Decimal]]:
        data = self._call("GET", "/fapi/v3/positionRisk", None, signed=True)
        out = {
            s: {"qty": Decimal(0), "unrealized": Decimal(0), "mark": Decimal(0)} for s in SYMBOLS
        }
        for row in data:
            if row.get("symbol") in SYMBOLS:
                out[row["symbol"]] = {
                    "qty": out[row["symbol"]]["qty"] + Decimal(row["positionAmt"]),
                    "unrealized": out[row["symbol"]]["unrealized"]
                    + Decimal(row.get("unRealizedProfit", "0")),
                    "mark": Decimal(row.get("markPrice", "0")),
                }
        return out

    def open_orders(self, symbol: str) -> list[dict[str, Any]]:
        return self._call("GET", "/fapi/v1/openOrders", {"symbol": symbol}, signed=True)

    def order_by_client_id(self, symbol: str, client_id: str) -> dict[str, Any] | None:
        try:
            return self._call(
                "GET",
                "/fapi/v1/order",
                {"symbol": symbol, "origClientOrderId": client_id},
                signed=True,
            )
        except ExchangeError as exc:
            if exc.code == -2013:  # order does not exist
                return None
            raise

    def income(self, start_ms: int) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        cursor = start_ms
        for _ in range(50):
            page = self._call(
                "GET", "/fapi/v1/income", {"startTime": cursor, "limit": 1000}, signed=True
            )
            rows.extend(page)
            if len(page) < 1000:
                break
            cursor = int(page[-1]["time"]) + 1
        return [r for r in rows if r.get("symbol") in SYMBOLS]

    def symbol_config(self, symbol: str) -> dict[str, Any]:
        data = self._call("GET", "/fapi/v1/symbolConfig", {"symbol": symbol}, signed=True)
        return data[0] if isinstance(data, list) and data else {}

    # -------------------------------------------------------------------- orders
    def ensure_isolated_2x(self, symbol: str) -> None:
        config = self.symbol_config(symbol)
        if config.get("marginType") != "ISOLATED":
            try:
                self._call(
                    "POST",
                    "/fapi/v1/marginType",
                    {"symbol": symbol, "marginType": "ISOLATED"},
                    signed=True,
                )
            except ExchangeError as exc:
                if exc.code != -4046:  # no need to change
                    raise
        if int(config.get("leverage", 0)) != 2:
            self._call("POST", "/fapi/v1/leverage", {"symbol": symbol, "leverage": 2}, signed=True)

    def place_ioc(
        self,
        symbol: str,
        side: str,
        qty: Decimal,
        price: Decimal,
        *,
        reduce_only: bool,
        client_id: str,
    ) -> dict[str, Any]:
        if side not in {"BUY", "SELL"} or qty <= 0 or price <= 0:
            raise ValueError("invalid IOC order")
        return self._call(
            "POST",
            "/fapi/v1/order",
            {
                "symbol": symbol,
                "side": side,
                "type": "LIMIT",
                "timeInForce": "IOC",
                "quantity": _plain(qty),
                "price": _plain(price),
                "reduceOnly": "true" if reduce_only else None,
                "newClientOrderId": client_id,
                "newOrderRespType": "RESULT",
            },
            signed=True,
        )

    def place_reduce_only_market(
        self, symbol: str, side: str, qty: Decimal, client_id: str
    ) -> dict[str, Any]:
        """Emergency exit only (guard): a risk exit must complete."""
        return self._call(
            "POST",
            "/fapi/v1/order",
            {
                "symbol": symbol,
                "side": side,
                "type": "MARKET",
                "quantity": _plain(qty),
                "reduceOnly": "true",
                "newClientOrderId": client_id,
                "newOrderRespType": "RESULT",
            },
            signed=True,
        )

    def cancel_all(self, symbol: str) -> None:
        self._call("DELETE", "/fapi/v1/allOpenOrders", {"symbol": symbol}, signed=True)


def _plain(value: Decimal) -> str:
    text = format(value.normalize(), "f")
    return text


def floor_to(value: Decimal, step: Decimal) -> Decimal:
    return (value / step).to_integral_value(rounding=ROUND_DOWN) * step


def ceil_to(value: Decimal, step: Decimal) -> Decimal:
    return (value / step).to_integral_value(rounding=ROUND_UP) * step
