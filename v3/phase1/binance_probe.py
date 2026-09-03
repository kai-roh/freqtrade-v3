"""Read-only Binance connectivity probes with redacted, allowlisted output."""

from __future__ import annotations

import hashlib
import hmac
import json
import ssl
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

SPOT_DEMO = "https://demo-api.binance.com"
USDM_DEMO = "https://demo-fapi.binance.com"
SPOT_LIVE = "https://api.binance.com"
USDM_LIVE = "https://fapi.binance.com"

ALLOWED_REQUESTS = frozenset(
    {
        (SPOT_DEMO, "/api/v3/time", False),
        (SPOT_DEMO, "/api/v3/ping", False),
        (SPOT_DEMO, "/api/v3/exchangeInfo", False),
        (SPOT_DEMO, "/api/v3/account", True),
        (USDM_DEMO, "/fapi/v1/time", False),
        (USDM_DEMO, "/fapi/v1/ping", False),
        (USDM_DEMO, "/fapi/v1/exchangeInfo", False),
        (USDM_DEMO, "/fapi/v1/premiumIndex", False),
        (USDM_DEMO, "/fapi/v3/account", True),
        (SPOT_LIVE, "/api/v3/time", False),
        (SPOT_LIVE, "/api/v3/account", True),
        (SPOT_LIVE, "/api/v3/account/commission", True),
        (USDM_LIVE, "/fapi/v1/time", False),
        (USDM_LIVE, "/fapi/v3/account", True),
        (USDM_LIVE, "/fapi/v1/commissionRate", True),
        (USDM_LIVE, "/fapi/v1/symbolConfig", True),
    }
)


@dataclass(frozen=True)
class BinanceCredentials:
    api_key: str
    api_secret: str

    def __post_init__(self) -> None:
        if not self.api_key.strip() or not self.api_secret.strip():
            raise ValueError("Binance credentials must be non-empty")


@dataclass(frozen=True)
class ProbeResponse:
    ok: bool
    http_status: int | None
    data: Any = None
    exchange_code: int | None = None
    network_error: str | None = None

    def status_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "ok": self.ok,
            "http_status": self.http_status,
        }
        if self.exchange_code is not None:
            result["exchange_code"] = self.exchange_code
        if self.network_error is not None:
            result["network_error"] = self.network_error
        return result


OpenUrl = Callable[..., Any]


class BinanceReadOnlyClient:
    """Minimal signed GET client which cannot address order or transfer endpoints."""

    def __init__(
        self,
        credentials: BinanceCredentials | None = None,
        *,
        timeout_seconds: float = 10,
        ca_file: Path | None = None,
        opener: OpenUrl = urlopen,
    ) -> None:
        self.credentials = credentials
        self.timeout_seconds = timeout_seconds
        self._opener = opener
        self._ssl_context = (
            ssl.create_default_context(cafile=str(ca_file))
            if ca_file is not None
            else ssl.create_default_context()
        )

    def get(
        self,
        base_url: str,
        path: str,
        *,
        signed: bool = False,
        params: Mapping[str, str | int] | None = None,
        server_time_path: str | None = None,
    ) -> ProbeResponse:
        if (base_url, path, signed) not in ALLOWED_REQUESTS:
            raise ValueError("Binance probe request is not on the read-only allowlist")
        query: dict[str, str | int] = dict(params or {})
        headers: dict[str, str] = {}
        if signed:
            if self.credentials is None:
                raise ValueError("signed Binance probe requires credentials")
            if server_time_path is None:
                raise ValueError("signed Binance probe requires a server time path")
            clock = self.get(base_url, server_time_path)
            if not clock.ok or not isinstance(clock.data, Mapping):
                return ProbeResponse(
                    ok=False,
                    http_status=clock.http_status,
                    exchange_code=clock.exchange_code,
                    network_error=clock.network_error or "server_time_unavailable",
                )
            server_time = clock.data.get("serverTime")
            if isinstance(server_time, bool) or not isinstance(server_time, int):
                return ProbeResponse(False, clock.http_status, network_error="invalid_server_time")
            query["timestamp"] = server_time
            query["recvWindow"] = 5000
            payload = urlencode(query)
            query["signature"] = hmac.new(
                self.credentials.api_secret.encode(),
                payload.encode(),
                hashlib.sha256,
            ).hexdigest()
            headers["X-MBX-APIKEY"] = self.credentials.api_key
        request = Request(
            base_url + path + (f"?{urlencode(query)}" if query else ""),
            headers=headers,
            method="GET",
        )
        try:
            with self._opener(
                request,
                timeout=self.timeout_seconds,
                context=self._ssl_context,
            ) as response:
                return ProbeResponse(
                    ok=True,
                    http_status=response.status,
                    data=json.loads(response.read() or b"{}"),
                )
        except HTTPError as exc:
            return ProbeResponse(
                ok=False,
                http_status=exc.code,
                exchange_code=_exchange_error_code(exc.read()),
            )
        except (TimeoutError, URLError) as exc:
            return ProbeResponse(
                ok=False,
                http_status=None,
                network_error=type(exc).__name__,
            )


def probe_phase1_binance(
    *,
    mainnet_credentials: BinanceCredentials | None,
    demo_credentials: BinanceCredentials | None,
    classify_mainnet_credentials_on_demo: bool,
    location: str,
    ca_file: Path | None = None,
    captured_at: datetime | None = None,
    opener: OpenUrl = urlopen,
) -> dict[str, Any]:
    """Capture only non-secret facts needed for the Phase 1 admission decision."""

    captured = captured_at or datetime.now(UTC)
    public_client = BinanceReadOnlyClient(ca_file=ca_file, opener=opener)
    demo_auth_credentials = demo_credentials
    demo_credential_source = "dedicated_demo"
    if demo_auth_credentials is None and classify_mainnet_credentials_on_demo:
        demo_auth_credentials = mainnet_credentials
        demo_credential_source = "mainnet_cross_check"
    if demo_auth_credentials is None:
        demo_credential_source = "absent"

    spot_public = public_client.get(SPOT_DEMO, "/api/v3/ping")
    usdm_public = public_client.get(USDM_DEMO, "/fapi/v1/ping")
    spot_exchange = public_client.get(
        SPOT_DEMO,
        "/api/v3/exchangeInfo",
        params={"symbol": "BTCUSDT"},
    )
    usdm_exchange = public_client.get(
        USDM_DEMO,
        "/fapi/v1/exchangeInfo",
        params={"symbol": "BTCUSDT"},
    )
    funding = public_client.get(
        USDM_DEMO,
        "/fapi/v1/premiumIndex",
        params={"symbol": "BTCUSDT"},
    )

    demo_auth = _not_run_status("demo_credentials_absent")
    if demo_auth_credentials is not None:
        demo_client = BinanceReadOnlyClient(
            demo_auth_credentials,
            ca_file=ca_file,
            opener=opener,
        )
        demo_auth = {
            "spot_account": demo_client.get(
                SPOT_DEMO,
                "/api/v3/account",
                signed=True,
                params={"omitZeroBalances": "true"},
                server_time_path="/api/v3/time",
            ).status_dict(),
            "usdm_account": demo_client.get(
                USDM_DEMO,
                "/fapi/v3/account",
                signed=True,
                server_time_path="/fapi/v1/time",
            ).status_dict(),
        }

    mainnet = _not_run_status("mainnet_credentials_absent")
    if mainnet_credentials is not None:
        live_client = BinanceReadOnlyClient(
            mainnet_credentials,
            ca_file=ca_file,
            opener=opener,
        )
        spot_account = live_client.get(
            SPOT_LIVE,
            "/api/v3/account",
            signed=True,
            params={"omitZeroBalances": "true"},
            server_time_path="/api/v3/time",
        )
        usdm_account = live_client.get(
            USDM_LIVE,
            "/fapi/v3/account",
            signed=True,
            server_time_path="/fapi/v1/time",
        )
        spot_fees = live_client.get(
            SPOT_LIVE,
            "/api/v3/account/commission",
            signed=True,
            params={"symbol": "BTCUSDT"},
            server_time_path="/api/v3/time",
        )
        usdm_fees = live_client.get(
            USDM_LIVE,
            "/fapi/v1/commissionRate",
            signed=True,
            params={"symbol": "BTCUSDT"},
            server_time_path="/fapi/v1/time",
        )
        symbol_config = live_client.get(
            USDM_LIVE,
            "/fapi/v1/symbolConfig",
            signed=True,
            params={"symbol": "BTCUSDT"},
            server_time_path="/fapi/v1/time",
        )
        mainnet = {
            "spot_account": _sanitize_spot_account(spot_account),
            "usdm_account": _sanitize_usdm_account(usdm_account),
            "spot_commission": _sanitize_spot_commission(spot_fees),
            "usdm_commission": _sanitize_usdm_commission(usdm_fees),
            "usdm_symbol_config": _sanitize_symbol_config(symbol_config),
        }

    dedicated_demo_valid = demo_credential_source == "dedicated_demo" and _both_accounts_ok(
        demo_auth
    )
    location = location.strip() or "unknown"
    return {
        "schema_version": 1,
        "captured_at": captured.isoformat(),
        "location": location,
        "symbol": "BTCUSDT",
        "safety": {
            "http_methods": ["GET"],
            "order_endpoints_called": False,
            "transfer_endpoints_called": False,
            "secret_fields_recorded": False,
        },
        "demo": {
            "public": {
                "spot": spot_public.status_dict(),
                "usdm": usdm_public.status_dict(),
            },
            "credential_source": demo_credential_source,
            "authentication": demo_auth,
            "spot_instrument": _sanitize_instrument(spot_exchange, product="spot"),
            "usdm_instrument": _sanitize_instrument(usdm_exchange, product="usdm"),
            "funding": _sanitize_funding(funding),
        },
        "mainnet_read_only": mainnet,
        "conclusion": {
            "dedicated_demo_credentials_valid": dedicated_demo_valid,
            "demo_authenticated_integration_ready": dedicated_demo_valid,
            "mainnet_credentials_valid": _mainnet_credentials_valid(mainnet),
            "orders_remain_disabled": True,
        },
    }


def load_dotenv_credentials(path: Path, prefix: str) -> BinanceCredentials | None:
    """Read one exact key pair without shell evaluation or variable expansion."""

    values: dict[str, str] = {}
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key not in {f"{prefix}_API_KEY", f"{prefix}_API_SECRET"}:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        values[key] = value
    api_key = values.get(f"{prefix}_API_KEY")
    api_secret = values.get(f"{prefix}_API_SECRET")
    if api_key is None and api_secret is None:
        return None
    if not api_key or not api_secret:
        raise ValueError(f"{prefix} credentials must include both key and secret")
    return BinanceCredentials(api_key, api_secret)


def fee_snapshot_from_probe(result: Mapping[str, Any], *, maximum_age_hours: int) -> dict[str, Any]:
    """Derive the scanner's conservative fee input from a successful live GET probe."""

    if maximum_age_hours <= 0:
        raise ValueError("maximum_age_hours must be positive")
    mainnet = result.get("mainnet_read_only")
    if not isinstance(mainnet, Mapping):
        raise ValueError("probe has no Mainnet result")
    spot = mainnet.get("spot_commission")
    usdm = mainnet.get("usdm_commission")
    if not isinstance(spot, Mapping) or spot.get("ok") is not True:
        raise ValueError("probe has no successful Spot commission result")
    if not isinstance(usdm, Mapping) or usdm.get("ok") is not True:
        raise ValueError("probe has no successful USD-M commission result")
    spot_maker = _required_decimal(spot, "standard_maker_bps")
    spot_taker = _required_decimal(spot, "standard_taker_bps")
    perp_maker = _required_decimal(usdm, "maker_bps")
    perp_taker = _required_decimal(usdm, "taker_bps")
    entry = spot_maker + perp_maker
    location = str(result.get("location", "unknown")).strip() or "unknown"
    return {
        "schema_version": 1,
        "captured_at": result["captured_at"],
        "maximum_age_hours": maximum_age_hours,
        "symbol": result.get("symbol"),
        "source": f"credentialed-mainnet-account-query-from-{location}",
        "spot_maker_bps": str(spot_maker),
        "spot_taker_bps": str(spot_taker),
        "perp_maker_bps": str(perp_maker),
        "perp_taker_bps": str(perp_taker),
        "bnb_discount_available": spot.get("bnb_discount_enabled_for_account") is True
        and spot.get("bnb_discount_enabled_for_symbol") is True,
        "bnb_discount_factor": spot.get("bnb_discount_factor"),
        "bnb_discount_applied": False,
        "include_exit_cost": True,
        "normal_entry_cost_bps": str(entry),
        "normal_round_trip_cost_bps": str(entry * Decimal("2")),
    }


def _exchange_error_code(payload: bytes) -> int | None:
    try:
        code = json.loads(payload or b"{}").get("code")
    except (AttributeError, json.JSONDecodeError):
        return None
    return code if isinstance(code, int) and not isinstance(code, bool) else None


def _required_decimal(data: Mapping[str, Any], key: str) -> Decimal:
    try:
        value = Decimal(str(data[key]))
    except (InvalidOperation, KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"probe fee field {key} is invalid") from exc
    if value < 0:
        raise ValueError(f"probe fee field {key} must be non-negative")
    return value


def _not_run_status(reason: str) -> dict[str, Any]:
    return {"status": "not_run", "reason": reason}


def _response_data(response: ProbeResponse) -> Mapping[str, Any] | None:
    return response.data if response.ok and isinstance(response.data, Mapping) else None


def _sanitize_spot_account(response: ProbeResponse) -> dict[str, Any]:
    result = response.status_dict()
    data = _response_data(response)
    if data is not None:
        result.update(
            {
                "can_trade": data.get("canTrade"),
                "account_type": data.get("accountType"),
                "permissions": data.get("permissions"),
            }
        )
    return result


def _sanitize_usdm_account(response: ProbeResponse) -> dict[str, Any]:
    result = response.status_dict()
    data = _response_data(response)
    if data is not None:
        result.update(
            {
                "can_trade": data.get("canTrade"),
                "multi_assets_margin": data.get("multiAssetsMargin"),
            }
        )
    return result


def _to_bps(value: Any) -> str | None:
    try:
        return str(Decimal(str(value)) * Decimal("10000"))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _sanitize_spot_commission(response: ProbeResponse) -> dict[str, Any]:
    result = response.status_dict()
    data = _response_data(response)
    if data is None:
        return result
    standard = data.get("standardCommission")
    discount = data.get("discount")
    if isinstance(standard, Mapping):
        result["standard_maker_bps"] = _to_bps(standard.get("maker"))
        result["standard_taker_bps"] = _to_bps(standard.get("taker"))
    if isinstance(discount, Mapping):
        result["bnb_discount_enabled_for_account"] = discount.get("enabledForAccount")
        result["bnb_discount_enabled_for_symbol"] = discount.get("enabledForSymbol")
        result["bnb_discount_factor"] = discount.get("discount")
    return result


def _sanitize_usdm_commission(response: ProbeResponse) -> dict[str, Any]:
    result = response.status_dict()
    data = _response_data(response)
    if data is not None:
        result["maker_bps"] = _to_bps(data.get("makerCommissionRate"))
        result["taker_bps"] = _to_bps(data.get("takerCommissionRate"))
    return result


def _sanitize_symbol_config(response: ProbeResponse) -> dict[str, Any]:
    result = response.status_dict()
    data = response.data if response.ok else None
    if isinstance(data, list) and data and isinstance(data[0], Mapping):
        data = data[0]
    if isinstance(data, Mapping):
        result.update(
            {
                "symbol": data.get("symbol"),
                "margin_type": data.get("marginType"),
                "leverage": data.get("leverage"),
                "auto_add_margin": data.get("isAutoAddMargin"),
                "max_notional_value": data.get("maxNotionalValue"),
            }
        )
    return result


def _sanitize_instrument(response: ProbeResponse, *, product: str) -> dict[str, Any]:
    result = response.status_dict()
    data = _response_data(response)
    symbols = data.get("symbols") if data is not None else None
    symbol = symbols[0] if isinstance(symbols, list) and symbols else None
    if not isinstance(symbol, Mapping):
        return result
    result.update(
        {
            "symbol": symbol.get("symbol"),
            "status": symbol.get("status"),
            "base_asset": symbol.get("baseAsset"),
            "quote_asset": symbol.get("quoteAsset"),
            "filters": _filter_summary(symbol.get("filters"), product=product),
        }
    )
    return result


def _filter_summary(filters: Any, *, product: str) -> dict[str, Any]:
    if not isinstance(filters, list):
        return {}
    by_type = {item.get("filterType"): item for item in filters if isinstance(item, Mapping)}
    price = by_type.get("PRICE_FILTER", {})
    lot = by_type.get("LOT_SIZE", {})
    notional = by_type.get("NOTIONAL") or by_type.get("MIN_NOTIONAL") or {}
    min_notional = notional.get("minNotional") if product == "spot" else notional.get("notional")
    return {
        "tick_size": price.get("tickSize"),
        "minimum_quantity": lot.get("minQty"),
        "quantity_step": lot.get("stepSize"),
        "minimum_notional": min_notional,
    }


def _sanitize_funding(response: ProbeResponse) -> dict[str, Any]:
    result = response.status_dict()
    data = _response_data(response)
    if data is not None:
        result.update(
            {
                "symbol": data.get("symbol"),
                "last_funding_rate": data.get("lastFundingRate"),
                "next_funding_time": data.get("nextFundingTime"),
                "venue_time": data.get("time"),
            }
        )
    return result


def _both_accounts_ok(authentication: Mapping[str, Any]) -> bool:
    return all(
        isinstance(authentication.get(key), Mapping) and authentication[key].get("ok") is True
        for key in ("spot_account", "usdm_account")
    )


def _mainnet_credentials_valid(mainnet: Mapping[str, Any]) -> bool:
    return all(
        isinstance(mainnet.get(key), Mapping) and mainnet[key].get("ok") is True
        for key in ("spot_account", "usdm_account")
    )
