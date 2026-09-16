import hashlib
import json
from decimal import Decimal

import pytest

from v3.hyperliquid import (
    HyperliquidMetadataError,
    build_preflight_input_from_snapshot,
    endpoint_for,
    parse_perp_snapshot,
)
from v3.instruments import VenueEnvironment


def _response() -> bytes:
    return json.dumps(
        [
            {
                "universe": [
                    {"name": "BTC", "szDecimals": 5, "maxLeverage": 40},
                    {
                        "name": "OLD",
                        "szDecimals": 2,
                        "maxLeverage": 3,
                        "isDelisted": True,
                    },
                ]
            },
            [
                {"markPx": "79864.0", "oraclePx": "79854.9", "funding": "0.0000125"},
                {"markPx": None, "oraclePx": "1.2", "funding": "0.0"},
            ],
        ],
        separators=(",", ":"),
    ).encode()


def test_parse_perp_snapshot_derives_precision_and_hashes_exact_response():
    raw = _response()
    snapshot = parse_perp_snapshot(
        raw,
        VenueEnvironment.MAINNET,
        symbols=["btc"],
        fetched_at="2026-08-25T00:00:00+00:00",
    )
    instrument = snapshot.instruments[0]

    assert snapshot.response_sha256 == hashlib.sha256(raw).hexdigest()
    assert instrument.spec.instrument_id == "BTC"
    assert instrument.spec.asset_index == 0
    assert instrument.spec.minimum_notional == Decimal("10")
    assert instrument.spec.quantity_increment == Decimal("0.00001")
    assert instrument.spec.price_increment == Decimal("0.1")
    assert instrument.spec.price_max_decimal_places == 1
    assert instrument.spec.integer_price_has_no_significant_digit_limit is True
    assert instrument.venue_max_leverage == 40
    assert instrument.mark_price == Decimal("79864.0")
    assert snapshot.to_dict()["instruments"][0]["source"].endswith(snapshot.response_sha256)


def test_parse_perp_snapshot_marks_delisted_instrument_inactive():
    snapshot = parse_perp_snapshot(_response(), VenueEnvironment.TESTNET, symbols=["OLD"])

    assert snapshot.instruments[0].spec.is_active is False
    assert snapshot.instruments[0].mark_price is None


def test_parse_perp_snapshot_fails_on_missing_symbol_or_misaligned_contexts():
    with pytest.raises(HyperliquidMetadataError, match="not found"):
        parse_perp_snapshot(_response(), VenueEnvironment.MAINNET, symbols=["ETH"])

    broken = json.dumps([{"universe": [{"name": "BTC"}]}, []]).encode()
    with pytest.raises(HyperliquidMetadataError, match="equal lengths"):
        parse_perp_snapshot(broken, VenueEnvironment.MAINNET)


def test_build_preflight_input_from_snapshot_uses_captured_spec_and_notional_headroom():
    snapshot = parse_perp_snapshot(_response(), VenueEnvironment.TESTNET).to_dict()

    payload = build_preflight_input_from_snapshot(
        snapshot,
        instrument_id="BTC",
        price="60000",
        target_notional="30",
        observed_leverage="2",
        quote_age_ms=100,
        order_reject_probe="passed",
        policy={"maximum_quote_age_ms": 250, "require_order_reject_probe": True},
        intent={
            "entry_reason": "funding spread above threshold",
            "target_position": "perp short",
            "normal_exit": "spread closes",
            "risk_exit": "leverage or quote freshness failure",
            "max_holding_or_review_at": "next settlement",
            "cost_and_risk_budget": "max legging 5 bps",
        },
    )

    assert payload["instrument"]["source"].endswith(snapshot["response_sha256"])
    assert payload["instrument"]["quantity_increment"] == "0.00001"
    assert payload["order"]["quantity"] == "0.00050"
    assert payload["policy"]["require_order_reject_probe"] is True


def test_build_preflight_input_from_snapshot_rejects_ambiguous_sizing():
    snapshot = parse_perp_snapshot(_response(), VenueEnvironment.TESTNET).to_dict()

    with pytest.raises(HyperliquidMetadataError, match="quantity or target_notional"):
        build_preflight_input_from_snapshot(
            snapshot,
            instrument_id="BTC",
            price="60000",
            quantity="0.001",
            target_notional="30",
            observed_leverage="2",
            quote_age_ms=100,
        )


def test_hyperliquid_rejects_generic_demo_environment():
    with pytest.raises(HyperliquidMetadataError, match="no demo environment"):
        endpoint_for(VenueEnvironment.DEMO)
