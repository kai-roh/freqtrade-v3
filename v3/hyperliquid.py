"""Read-only Hyperliquid perpetual instrument metadata capture."""

from __future__ import annotations

import hashlib
import json
import ssl
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_CEILING, Decimal
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

from .costs import DecimalInput, as_decimal
from .instruments import InstrumentSpec, VenueEnvironment

MAINNET_INFO_URL = "https://api.hyperliquid.xyz/info"
TESTNET_INFO_URL = "https://api.hyperliquid-testnet.xyz/info"
MINIMUM_PERP_NOTIONAL = Decimal("10")
PERP_MAX_DECIMALS = 6
PRICE_SIGNIFICANT_DIGITS = 5

INFO_ENDPOINT_DOC = (
    "https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint/perpetuals"
)
PRECISION_DOC = (
    "https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/tick-and-lot-size"
)
MINIMUM_NOTIONAL_DOC = (
    "https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/error-responses"
)


class HyperliquidMetadataError(ValueError):
    """Raised when a public metadata response violates the expected schema."""


@dataclass(frozen=True)
class HyperliquidPerpInstrument:
    spec: InstrumentSpec
    size_decimals: int
    venue_max_leverage: int
    mark_price: Decimal | None
    oracle_price: Decimal | None
    funding_rate: Decimal | None

    def to_dict(self) -> dict[str, Any]:
        spec = self.spec
        return {
            "venue": spec.venue,
            "environment": spec.environment.value,
            "instrument_id": spec.instrument_id,
            "asset_index": spec.asset_index,
            "active": spec.is_active,
            "minimum_notional": str(spec.minimum_notional),
            "minimum_quantity": str(spec.minimum_quantity),
            "quantity_increment": str(spec.quantity_increment),
            "price_increment": str(spec.price_increment),
            "price_significant_digits": spec.price_significant_digits,
            "price_max_decimal_places": spec.price_max_decimal_places,
            "integer_price_has_no_significant_digit_limit": (
                spec.integer_price_has_no_significant_digit_limit
            ),
            "size_decimals": self.size_decimals,
            "venue_max_leverage": self.venue_max_leverage,
            "mark_price": _optional_decimal(self.mark_price),
            "oracle_price": _optional_decimal(self.oracle_price),
            "funding_rate": _optional_decimal(self.funding_rate),
            "source": spec.source,
        }


@dataclass(frozen=True)
class HyperliquidPerpSnapshot:
    environment: VenueEnvironment
    endpoint: str
    fetched_at: str
    response_sha256: str
    instruments: tuple[HyperliquidPerpInstrument, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "venue": "hyperliquid",
            "environment": self.environment.value,
            "endpoint": self.endpoint,
            "request": {"type": "metaAndAssetCtxs"},
            "fetched_at": self.fetched_at,
            "response_sha256": self.response_sha256,
            "source_documents": {
                "metadata": INFO_ENDPOINT_DOC,
                "precision": PRECISION_DOC,
                "minimum_notional": MINIMUM_NOTIONAL_DOC,
            },
            "instruments": [instrument.to_dict() for instrument in self.instruments],
        }


def build_preflight_input_from_snapshot(
    snapshot: dict[str, Any],
    *,
    instrument_id: str,
    price: DecimalInput | None = None,
    price_source: str = "mark",
    quantity: DecimalInput | None = None,
    target_notional: DecimalInput | None = None,
    observed_leverage: DecimalInput | None,
    quote_age_ms: int | None,
    order_reject_probe: str = "not_run",
    policy: dict[str, Any] | None = None,
    intent: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Create order-preflight JSON from a captured Hyperliquid metadata snapshot."""

    instrument = _find_snapshot_instrument(snapshot, instrument_id)
    resolved_price = _resolve_order_price(instrument, price=price, price_source=price_source)
    resolved_quantity = _resolve_order_quantity(
        instrument,
        price=resolved_price,
        quantity=quantity,
        target_notional=target_notional,
    )
    return {
        "instrument": {
            "venue": instrument["venue"],
            "environment": instrument["environment"],
            "instrument_id": instrument["instrument_id"],
            "minimum_notional": instrument["minimum_notional"],
            "minimum_quantity": instrument["minimum_quantity"],
            "quantity_increment": instrument["quantity_increment"],
            "price_increment": instrument["price_increment"],
            "price_significant_digits": instrument["price_significant_digits"],
            "price_max_decimal_places": instrument.get("price_max_decimal_places"),
            "integer_price_has_no_significant_digit_limit": instrument.get(
                "integer_price_has_no_significant_digit_limit", False
            ),
            "asset_index": instrument.get("asset_index"),
            "active": instrument.get("active", True),
            "source": instrument["source"],
        },
        "order": {
            "price": str(resolved_price),
            "quantity": str(resolved_quantity),
            "observed_leverage": None
            if observed_leverage is None
            else str(as_decimal(observed_leverage, field_name="observed_leverage")),
            "quote_age_ms": quote_age_ms,
            "order_reject_probe": order_reject_probe,
        },
        "policy": policy or {},
        "intent": intent,
    }


def endpoint_for(environment: VenueEnvironment) -> str:
    if environment is VenueEnvironment.MAINNET:
        return MAINNET_INFO_URL
    if environment is VenueEnvironment.TESTNET:
        return TESTNET_INFO_URL
    raise HyperliquidMetadataError("Hyperliquid metadata has no demo environment")


def fetch_metadata_response(
    environment: VenueEnvironment,
    *,
    timeout_seconds: float = 15.0,
    opener: Callable[..., Any] = urlopen,
) -> bytes:
    """Fetch public metadata only; this function cannot submit an order."""

    request = Request(
        endpoint_for(environment),
        data=b'{"type":"metaAndAssetCtxs"}',
        headers={"Content-Type": "application/json", "User-Agent": "freqtrade-v3-phase0"},
        method="POST",
    )
    with opener(request, timeout=timeout_seconds, context=_verified_ssl_context()) as response:
        return response.read()


def parse_perp_snapshot(
    raw_response: bytes,
    environment: VenueEnvironment,
    *,
    symbols: Iterable[str] | None = None,
    fetched_at: str | None = None,
) -> HyperliquidPerpSnapshot:
    """Convert a captured ``metaAndAssetCtxs`` response into immutable specs."""

    try:
        payload = json.loads(raw_response)
    except (TypeError, json.JSONDecodeError) as exc:
        raise HyperliquidMetadataError("response is not valid JSON") from exc
    if not isinstance(payload, list) or len(payload) != 2:
        raise HyperliquidMetadataError("response must be [metadata, asset_contexts]")
    metadata, contexts = payload
    if not isinstance(metadata, dict) or not isinstance(contexts, list):
        raise HyperliquidMetadataError("metadata or asset contexts have an invalid type")
    universe = metadata.get("universe")
    if not isinstance(universe, list) or len(universe) != len(contexts):
        raise HyperliquidMetadataError("universe and asset contexts must have equal lengths")

    wanted = None if symbols is None else {symbol.strip().upper() for symbol in symbols}
    if wanted is not None and (not wanted or "" in wanted):
        raise HyperliquidMetadataError("symbols must not be blank")

    response_sha256 = hashlib.sha256(raw_response).hexdigest()
    endpoint = endpoint_for(environment)
    source = f"{endpoint}#sha256={response_sha256}"
    instruments: list[HyperliquidPerpInstrument] = []

    for asset_index, (instrument, context) in enumerate(zip(universe, contexts, strict=True)):
        if not isinstance(instrument, dict) or not isinstance(context, dict):
            raise HyperliquidMetadataError("instrument metadata and context must be objects")
        name = instrument.get("name")
        if not isinstance(name, str) or not name:
            raise HyperliquidMetadataError("instrument name is missing")
        if wanted is not None and name.upper() not in wanted:
            continue
        size_decimals = _integer_field(instrument, "szDecimals", minimum=0)
        if size_decimals > PERP_MAX_DECIMALS:
            raise HyperliquidMetadataError(
                f"{name} szDecimals exceeds perpetual maximum {PERP_MAX_DECIMALS}"
            )
        venue_max_leverage = _integer_field(instrument, "maxLeverage", minimum=1)
        quantity_increment = Decimal(1).scaleb(-size_decimals)
        price_max_decimal_places = PERP_MAX_DECIMALS - size_decimals
        price_increment = Decimal(1).scaleb(-price_max_decimal_places)
        spec = InstrumentSpec(
            venue="hyperliquid",
            environment=environment,
            instrument_id=name,
            minimum_notional=MINIMUM_PERP_NOTIONAL,
            minimum_quantity=quantity_increment,
            quantity_increment=quantity_increment,
            price_increment=price_increment,
            price_significant_digits=PRICE_SIGNIFICANT_DIGITS,
            price_max_decimal_places=price_max_decimal_places,
            integer_price_has_no_significant_digit_limit=True,
            asset_index=asset_index,
            source=source,
            is_active=not bool(instrument.get("isDelisted", False)),
        )
        instruments.append(
            HyperliquidPerpInstrument(
                spec=spec,
                size_decimals=size_decimals,
                venue_max_leverage=venue_max_leverage,
                mark_price=_decimal_field(context, "markPx"),
                oracle_price=_decimal_field(context, "oraclePx"),
                funding_rate=_decimal_field(context, "funding"),
            )
        )

    if wanted is not None:
        found = {instrument.spec.instrument_id.upper() for instrument in instruments}
        missing = sorted(wanted - found)
        if missing:
            raise HyperliquidMetadataError(f"requested instruments not found: {', '.join(missing)}")
    if not instruments:
        raise HyperliquidMetadataError("response contains no selected instruments")

    return HyperliquidPerpSnapshot(
        environment=environment,
        endpoint=endpoint,
        fetched_at=fetched_at or datetime.now(UTC).isoformat(),
        response_sha256=response_sha256,
        instruments=tuple(instruments),
    )


def _integer_field(data: dict[str, Any], key: str, *, minimum: int) -> int:
    value = data.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise HyperliquidMetadataError(f"{key} must be an integer >= {minimum}")
    return value


def _decimal_field(data: dict[str, Any], key: str) -> Decimal | None:
    value = data.get(key)
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (ValueError, TypeError) as exc:
        raise HyperliquidMetadataError(f"{key} is not a decimal") from exc


def _optional_decimal(value: Decimal | None) -> str | None:
    return None if value is None else str(value)


def _find_snapshot_instrument(snapshot: dict[str, Any], instrument_id: str) -> dict[str, Any]:
    if snapshot.get("venue") != "hyperliquid":
        raise HyperliquidMetadataError("snapshot venue must be hyperliquid")
    wanted = instrument_id.strip().upper()
    if not wanted:
        raise HyperliquidMetadataError("instrument_id is required")
    instruments = snapshot.get("instruments")
    if not isinstance(instruments, list):
        raise HyperliquidMetadataError("snapshot instruments must be a list")
    for instrument in instruments:
        if not isinstance(instrument, dict):
            raise HyperliquidMetadataError("snapshot instrument must be an object")
        if str(instrument.get("instrument_id", "")).upper() == wanted:
            return instrument
    raise HyperliquidMetadataError(f"instrument not found in snapshot: {instrument_id}")


def _resolve_order_price(
    instrument: dict[str, Any],
    *,
    price: DecimalInput | None,
    price_source: str,
) -> Decimal:
    if price is not None:
        return as_decimal(price, field_name="price")
    source_key = {"mark": "mark_price", "oracle": "oracle_price"}.get(price_source)
    if source_key is None:
        raise HyperliquidMetadataError("price_source must be mark or oracle")
    source_value = instrument.get(source_key)
    if source_value is None:
        raise HyperliquidMetadataError(f"{source_key} is unavailable in snapshot")
    return as_decimal(source_value, field_name=source_key)


def _resolve_order_quantity(
    instrument: dict[str, Any],
    *,
    price: Decimal,
    quantity: DecimalInput | None,
    target_notional: DecimalInput | None,
) -> Decimal:
    if quantity is not None and target_notional is not None:
        raise HyperliquidMetadataError("provide quantity or target_notional, not both")
    if quantity is not None:
        return as_decimal(quantity, field_name="quantity")
    if target_notional is None:
        raise HyperliquidMetadataError("quantity or target_notional is required")
    notional = as_decimal(target_notional, field_name="target_notional")
    if notional <= 0:
        raise HyperliquidMetadataError("target_notional must be positive")
    increment = as_decimal(instrument["quantity_increment"], field_name="quantity_increment")
    raw_quantity = notional / price
    steps = (raw_quantity / increment).to_integral_value(rounding=ROUND_CEILING)
    return (steps * increment).quantize(increment)


def _verified_ssl_context() -> ssl.SSLContext:
    """Use platform trust without ever falling back to an unverified connection."""

    default_paths = ssl.get_default_verify_paths()
    if (default_paths.cafile and Path(default_paths.cafile).is_file()) or (
        default_paths.capath and Path(default_paths.capath).is_dir()
    ):
        return ssl.create_default_context()
    for candidate in (
        Path("/etc/ssl/cert.pem"),
        Path("/etc/ssl/certs/ca-certificates.crt"),
        Path("/opt/homebrew/etc/openssl@3/cert.pem"),
    ):
        if candidate.is_file():
            return ssl.create_default_context(cafile=candidate)
    raise HyperliquidMetadataError("no trusted CA bundle is available for HTTPS verification")
