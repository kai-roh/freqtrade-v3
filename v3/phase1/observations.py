"""Order-free live market observations for Phase 1 carry scanning."""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from v3.costs import as_decimal

from .binance_probe import (
    SPOT_DEMO,
    USDM_DEMO,
    USDM_LIVE,
    BinanceReadOnlyClient,
)
from .postgres import (
    InstrumentSnapshotRow,
    QuoteObservationRow,
)
from .scanner import CarryObservation

Clock = Callable[[], datetime]

OBSERVATION_NAMESPACE = uuid.UUID("58ae58f6-4b39-45f5-8044-8ddc69b30fac")


@dataclass(frozen=True)
class InstrumentSnapshotRecord:
    id: str
    venue: str
    instrument_id: str
    raw_symbol: str
    price_precision: int
    size_precision: int
    minimum_notional: Decimal
    tick_size: Decimal
    lot_size: Decimal
    status: str
    content_hash: str
    observed_at: datetime

    def to_postgres_row(self) -> InstrumentSnapshotRow:
        return InstrumentSnapshotRow(
            snapshot_id=self.id,
            venue=self.venue,
            instrument_id=self.instrument_id,
            raw_symbol=self.raw_symbol,
            price_precision=self.price_precision,
            size_precision=self.size_precision,
            minimum_notional=self.minimum_notional,
            tick_size=self.tick_size,
            lot_size=self.lot_size,
            status=self.status,
            content_hash=self.content_hash,
            observed_at=self.observed_at,
        )


@dataclass(frozen=True)
class QuoteObservationRecord:
    id: str
    instrument_snapshot_id: str
    bid: Decimal
    ask: Decimal
    venue_timestamp: datetime | None
    received_at: datetime
    market_age_ms: int | None
    transport_rtt_ms: int
    collection_mode: str
    source_environment: str

    @property
    def quote_age_ms_for_risk(self) -> int | None:
        return self.market_age_ms

    @property
    def timestamp_source(self) -> str:
        return "exchange_event" if self.venue_timestamp is not None else "rest_received_at"

    def to_postgres_row(self) -> QuoteObservationRow:
        return QuoteObservationRow(
            quote_id=self.id,
            instrument_snapshot_id=self.instrument_snapshot_id,
            bid=self.bid,
            ask=self.ask,
            received_at=self.received_at,
            collection_mode=self.collection_mode,
            venue_timestamp=self.venue_timestamp,
            age_ms=self.market_age_ms,
            transport_rtt_ms=self.transport_rtt_ms,
            timestamp_source=self.timestamp_source,
        )


@dataclass(frozen=True)
class FundingObservationRecord:
    symbol: str
    funding_rate: Decimal
    funding_interval_minutes: int | None
    settlement_at: datetime
    source_environment: str
    source: str
    trailing_rates: tuple[Decimal, ...] = ()


@dataclass(frozen=True)
class Phase1CarryMarketObservation:
    spot_instrument: InstrumentSnapshotRecord
    perp_instrument: InstrumentSnapshotRecord
    spot_quote: QuoteObservationRecord
    perp_quote: QuoteObservationRecord
    funding: FundingObservationRecord
    captured_at: datetime

    def scanner_observation(
        self,
        *,
        requested_notional: Decimal | str,
        holding_period_hours: int,
        other_success_cost_bps: Decimal | str = Decimal("0"),
    ) -> CarryObservation:
        if self.funding.funding_interval_minutes is None:
            raise ValueError("funding interval is unmeasured")
        return CarryObservation(
            venue="binance",
            spot_instrument_id=self.spot_instrument.instrument_id,
            perp_instrument_id=self.perp_instrument.instrument_id,
            requested_notional=requested_notional,
            funding_rate=self.funding.funding_rate,
            funding_interval_minutes=self.funding.funding_interval_minutes,
            holding_period_hours=holding_period_hours,
            instrument_snapshot_id=self.perp_instrument.id,
            observed_at=self.captured_at,
            other_success_cost_bps=other_success_cost_bps,
            trailing_funding_rates=self.funding.trailing_rates,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "captured_at": self.captured_at.isoformat(),
            "spot_instrument": _jsonable(self.spot_instrument.to_postgres_row().__dict__),
            "perp_instrument": _jsonable(self.perp_instrument.to_postgres_row().__dict__),
            "spot_quote": _quote_dict(self.spot_quote),
            "perp_quote": _quote_dict(self.perp_quote),
            "funding": {
                "symbol": self.funding.symbol,
                "funding_rate": str(self.funding.funding_rate),
                "funding_interval_minutes": self.funding.funding_interval_minutes,
                "settlement_at": self.funding.settlement_at.isoformat(),
                "source_environment": self.funding.source_environment,
                "source": self.funding.source,
                "trailing_rates": [str(rate) for rate in self.funding.trailing_rates],
            },
        }


def capture_binance_carry_market_observation(
    client: BinanceReadOnlyClient,
    *,
    symbol: str = "BTCUSDT",
    clock: Clock | None = None,
    monotonic: Callable[[], float] | None = None,
    funding_history_limit: int = 24,
) -> Phase1CarryMarketObservation:
    """Fetch order-free public facts needed to bridge the scanner and risk layer."""

    now = clock or (lambda: datetime.now(UTC))
    mono = monotonic or time.monotonic
    captured_at = _utc(now(), "captured_at")
    spot_exchange = _require_mapping(
        client.get(SPOT_DEMO, "/api/v3/exchangeInfo", params={"symbol": symbol}).data,
        "spot exchangeInfo",
    )
    perp_exchange = _require_mapping(
        client.get(USDM_DEMO, "/fapi/v1/exchangeInfo", params={"symbol": symbol}).data,
        "USD-M exchangeInfo",
    )
    spot_instrument = instrument_snapshot_from_exchange_info(
        venue="binance",
        instrument_id=f"{symbol}.BINANCE",
        payload=spot_exchange,
        symbol=symbol,
        observed_at=captured_at,
    )
    perp_instrument = instrument_snapshot_from_exchange_info(
        venue="binance",
        instrument_id=f"{symbol}-PERP.BINANCE",
        payload=perp_exchange,
        symbol=symbol,
        observed_at=captured_at,
    )
    spot_quote = _timed_book_ticker(
        client,
        base_url=SPOT_DEMO,
        path="/api/v3/ticker/bookTicker",
        symbol=symbol,
        instrument_snapshot_id=spot_instrument.id,
        collection_mode="risk_decision",
        source_environment="demo_spot",
        clock=now,
        monotonic=mono,
    )
    perp_quote = _timed_book_ticker(
        client,
        base_url=USDM_DEMO,
        path="/fapi/v1/ticker/bookTicker",
        symbol=symbol,
        instrument_snapshot_id=perp_instrument.id,
        collection_mode="risk_decision",
        source_environment="demo_usdm",
        clock=now,
        monotonic=mono,
    )
    funding = capture_mainnet_public_funding(
        client, symbol=symbol, clock=now, history_limit=funding_history_limit
    )
    return Phase1CarryMarketObservation(
        spot_instrument=spot_instrument,
        perp_instrument=perp_instrument,
        spot_quote=spot_quote,
        perp_quote=perp_quote,
        funding=funding,
        captured_at=_utc(now(), "captured_at"),
    )


def capture_mainnet_public_funding(
    client: BinanceReadOnlyClient,
    *,
    symbol: str,
    clock: Clock | None = None,
    history_limit: int = 3,
) -> FundingObservationRecord:
    if history_limit < 3:
        raise ValueError("funding history needs at least three settlements")
    captured_at = _utc((clock or (lambda: datetime.now(UTC)))(), "captured_at")
    history_data = client.get(
        USDM_LIVE,
        "/fapi/v1/fundingRate",
        params={"symbol": symbol, "limit": history_limit},
    ).data
    history = _require_sequence(history_data, "fundingRate")
    rows = [_require_mapping(row, "fundingRate row") for row in history]
    symbol_rows = [row for row in rows if row.get("symbol") == symbol]
    if not symbol_rows:
        raise ValueError("funding history did not include the requested symbol")
    symbol_rows.sort(key=lambda row: _millis_to_utc(row.get("fundingTime"), "fundingTime"))
    latest = symbol_rows[-1]
    funding_rate = _positive_or_signed_decimal(latest.get("fundingRate"), "fundingRate")
    settlement_at = _millis_to_utc(latest.get("fundingTime"), "fundingTime")
    trailing_rates = tuple(
        _positive_or_signed_decimal(row.get("fundingRate"), "fundingRate") for row in symbol_rows
    )

    info = client.get(USDM_LIVE, "/fapi/v1/fundingInfo").data
    interval = _interval_from_funding_info(info, symbol)
    source = "fundingInfo"
    if interval is None:
        interval = _interval_from_history(symbol_rows)
        source = "fundingRate_history"
    if interval is None:
        source = "unmeasured"
    if settlement_at > captured_at:
        raise ValueError("latest funding settlement is in the future")
    if interval is not None and captured_at - settlement_at > timedelta(minutes=interval + 2):
        raise ValueError("funding history is stale")
    return FundingObservationRecord(
        symbol=symbol,
        funding_rate=funding_rate,
        funding_interval_minutes=interval,
        settlement_at=settlement_at,
        source_environment="mainnet_public_usdm",
        source=source,
        trailing_rates=trailing_rates,
    )


def instrument_snapshot_from_exchange_info(
    *,
    venue: str,
    instrument_id: str,
    payload: Mapping[str, Any],
    symbol: str,
    observed_at: datetime,
) -> InstrumentSnapshotRecord:
    symbols = _require_sequence(payload.get("symbols"), "symbols")
    match = next(
        (item for item in symbols if isinstance(item, Mapping) and item.get("symbol") == symbol),
        None,
    )
    if match is None:
        raise ValueError(f"{symbol} not found in exchangeInfo")
    status = str(match.get("status", ""))
    if status != "TRADING":
        raise ValueError(f"{symbol} status is not TRADING")
    filters = _filters_by_type(match)
    price_filter = filters.get("PRICE_FILTER")
    lot_filter = filters.get("LOT_SIZE")
    min_filter = filters.get("MIN_NOTIONAL") or filters.get("NOTIONAL")
    if price_filter is None or lot_filter is None or min_filter is None:
        raise ValueError("exchangeInfo is missing price, lot, or notional filters")
    tick_size = _positive_decimal(price_filter.get("tickSize"), "tickSize")
    lot_size = _positive_decimal(lot_filter.get("stepSize"), "stepSize")
    minimum_notional = _positive_decimal(
        min_filter.get("minNotional") or min_filter.get("notional"), "minNotional"
    )
    content = {
        "instrument_id": instrument_id,
        "symbol": symbol,
        "status": status,
        "tick_size": str(tick_size),
        "lot_size": str(lot_size),
        "minimum_notional": str(minimum_notional),
    }
    content_hash = hashlib.sha256(
        json.dumps(content, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    snapshot_id = str(uuid.uuid5(OBSERVATION_NAMESPACE, f"{instrument_id}:{content_hash}"))
    return InstrumentSnapshotRecord(
        id=snapshot_id,
        venue=venue,
        instrument_id=instrument_id,
        raw_symbol=symbol,
        price_precision=_precision(tick_size),
        size_precision=_precision(lot_size),
        minimum_notional=minimum_notional,
        tick_size=tick_size,
        lot_size=lot_size,
        status=status,
        content_hash=content_hash,
        observed_at=_utc(observed_at, "observed_at"),
    )


def quote_observation_from_book_ticker(
    *,
    payload: Mapping[str, Any],
    symbol: str,
    instrument_snapshot_id: str,
    source_environment: str,
    collection_mode: str,
    received_at: datetime,
    transport_rtt_ms: int,
) -> QuoteObservationRecord:
    if payload.get("symbol") != symbol:
        raise ValueError(f"bookTicker symbol is not {symbol}")
    bid = _positive_decimal(payload.get("bidPrice"), "bidPrice")
    ask = _positive_decimal(payload.get("askPrice"), "askPrice")
    if ask < bid:
        raise ValueError("bookTicker ask is below bid")
    venue_timestamp: datetime | None = None
    market_age_ms: int | None = None
    if "time" in payload:
        venue_timestamp = _millis_to_utc(payload["time"], "time")
        market_age_ms = round(
            (_utc(received_at, "received_at") - venue_timestamp).total_seconds() * 1000
        )
        if market_age_ms < 0:
            raise ValueError("quote timestamp is in the future; verify clock synchronization")
    quote_id = str(
        uuid.uuid5(
            OBSERVATION_NAMESPACE,
            f"{instrument_snapshot_id}:{source_environment}:{bid}:{ask}:{received_at.isoformat()}",
        )
    )
    if transport_rtt_ms < 0:
        raise ValueError("transport_rtt_ms must be non-negative")
    if collection_mode not in {"risk_decision", "phase1e_sample"}:
        raise ValueError("invalid quote collection_mode")
    return QuoteObservationRecord(
        id=quote_id,
        instrument_snapshot_id=instrument_snapshot_id,
        bid=bid,
        ask=ask,
        venue_timestamp=venue_timestamp,
        received_at=_utc(received_at, "received_at"),
        market_age_ms=market_age_ms,
        transport_rtt_ms=transport_rtt_ms,
        collection_mode=collection_mode,
        source_environment=source_environment,
    )


def _timed_book_ticker(
    client: BinanceReadOnlyClient,
    *,
    base_url: str,
    path: str,
    symbol: str,
    instrument_snapshot_id: str,
    collection_mode: str,
    source_environment: str,
    clock: Clock,
    monotonic: Callable[[], float],
) -> QuoteObservationRecord:
    start = monotonic()
    response = client.get(base_url, path, params={"symbol": symbol})
    end = monotonic()
    if not response.ok:
        raise ValueError(f"bookTicker request failed for {source_environment}")
    payload = _require_mapping(response.data, "bookTicker")
    return quote_observation_from_book_ticker(
        payload=payload,
        symbol=symbol,
        instrument_snapshot_id=instrument_snapshot_id,
        source_environment=source_environment,
        collection_mode=collection_mode,
        received_at=clock(),
        transport_rtt_ms=round((end - start) * 1000),
    )


def _filters_by_type(symbol_payload: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    filters = _require_sequence(symbol_payload.get("filters"), "filters")
    result: dict[str, Mapping[str, Any]] = {}
    for item in filters:
        if not isinstance(item, Mapping):
            continue
        filter_type = item.get("filterType")
        if isinstance(filter_type, str):
            result[filter_type] = item
    return result


def _interval_from_funding_info(data: Any, symbol: str) -> int | None:
    if not isinstance(data, Sequence) or isinstance(data, (str, bytes, bytearray)):
        return None
    for item in data:
        if not isinstance(item, Mapping) or item.get("symbol") != symbol:
            continue
        hours = item.get("fundingIntervalHours")
        if isinstance(hours, bool) or not isinstance(hours, int) or hours <= 0:
            return None
        return hours * 60
    return None


def _interval_from_history(rows: Sequence[Mapping[str, Any]]) -> int | None:
    if len(rows) < 3:
        return None
    try:
        times = [_millis_to_utc(row.get("fundingTime"), "fundingTime") for row in rows[-3:]]
    except ValueError:
        return None
    diffs = [
        round((later - earlier).total_seconds() / 60)
        for earlier, later in zip(times, times[1:], strict=False)
    ]
    if diffs and len(set(diffs)) == 1 and diffs[0] > 0:
        return diffs[0]
    return None


def _positive_decimal(value: Any, field_name: str) -> Decimal:
    decimal = _positive_or_signed_decimal(value, field_name)
    if decimal <= 0:
        raise ValueError(f"{field_name} must be positive")
    return decimal


def _positive_or_signed_decimal(value: Any, field_name: str) -> Decimal:
    try:
        return as_decimal(value, field_name=field_name)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be a decimal") from exc


def _precision(value: Decimal) -> int:
    return max(0, -value.normalize().as_tuple().exponent)


def _millis_to_utc(value: Any, field_name: str) -> datetime:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field_name} must be an integer millisecond timestamp")
    return datetime.fromtimestamp(value / 1000, UTC)


def _utc(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must include a timezone")
    return value.astimezone(UTC)


def _require_mapping(value: Any, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field_name} must be an object")
    return value


def _require_sequence(value: Any, field_name: str) -> Sequence[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise ValueError(f"{field_name} must be an array")
    return value


def _quote_dict(record: QuoteObservationRecord) -> dict[str, Any]:
    return {
        "id": record.id,
        "instrument_snapshot_id": record.instrument_snapshot_id,
        "bid": str(record.bid),
        "ask": str(record.ask),
        "venue_timestamp": (
            record.venue_timestamp.isoformat() if record.venue_timestamp is not None else None
        ),
        "received_at": record.received_at.isoformat(),
        "market_age_ms": record.market_age_ms,
        "transport_rtt_ms": record.transport_rtt_ms,
        "collection_mode": record.collection_mode,
        "source_environment": record.source_environment,
    }


def _jsonable(value: Mapping[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, item in value.items():
        if isinstance(item, Decimal):
            result[key] = str(item)
        elif isinstance(item, datetime):
            result[key] = item.isoformat()
        else:
            result[key] = item
    return result
