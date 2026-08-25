import pytest

from v3.instruments import (
    InstrumentPreflightPolicy,
    InstrumentPreflightRequest,
    InstrumentSpec,
    ProbeStatus,
    VenueEnvironment,
)
from v3.preflight import (
    IntentRecord,
    OrderPreflight,
    order_preflight_from_mapping,
    validate_order_preflight,
)


def _intent() -> IntentRecord:
    return IntentRecord(
        entry_reason="funding spread above threshold",
        target_position="spot long / perp short 1:1",
        normal_exit="spread below threshold after settlement",
        risk_exit="delta drift or margin floor breach",
        max_holding_or_review_at="next funding settlement",
        cost_and_risk_budget="max rebalance count 2, max legging 5 bps",
    )


def _instrument(**overrides) -> InstrumentPreflightRequest:
    values = {
        "spec": InstrumentSpec(
            venue="hyperliquid",
            environment=VenueEnvironment.TESTNET,
            instrument_id="BTC-PERP",
            minimum_notional="10",
            minimum_quantity="0.00001",
            quantity_increment="0.00001",
            price_increment="1",
            price_significant_digits=5,
            asset_index=0,
            source="testnet-meta-response",
        ),
        "price": "60000",
        "quantity": "0.00050",
        "observed_leverage": "2",
        "quote_age_ms": 100,
        "order_reject_probe": ProbeStatus.PASSED,
    }
    values.update(overrides)
    return InstrumentPreflightRequest(**values)


def test_order_preflight_accepts_conformant_instrument_and_complete_intent():
    result = validate_order_preflight(
        OrderPreflight(
            instrument=_instrument(),
            intent=_intent(),
            policy=InstrumentPreflightPolicy(
                maximum_quote_age_ms=250,
                require_order_reject_probe=True,
            ),
        )
    )

    assert result.passed
    assert result.reasons == ()
    assert result.intent == _intent().to_dict()


def test_order_preflight_fails_closed_on_instrument_and_missing_intent():
    result = validate_order_preflight(
        OrderPreflight(
            instrument=_instrument(observed_leverage="2.5", quote_age_ms=300),
            intent=None,
            policy=InstrumentPreflightPolicy(maximum_quote_age_ms=250),
        )
    )

    assert not result.passed
    assert any(reason.startswith("leverage:") for reason in result.reasons)
    assert any(reason.startswith("quote_age:") for reason in result.reasons)
    assert any(reason.startswith("intent:") for reason in result.reasons)


def test_intent_rejects_any_blank_required_field():
    with pytest.raises(ValueError, match="entry_reason"):
        IntentRecord(
            entry_reason="",
            target_position="spot/perp",
            normal_exit="spread closes",
            risk_exit="delta drift",
            max_holding_or_review_at="settlement",
            cost_and_risk_budget="budget",
        )


def test_order_preflight_mapping_rejects_null_intent_and_string_boolean():
    payload = {
        "instrument": {
            "venue": "binance",
            "environment": "demo",
            "instrument_id": "BTCUSDT.BINANCE",
            "minimum_notional": "10",
            "minimum_quantity": "0.00001",
            "quantity_increment": "0.00001",
            "price_increment": "0.01",
            "price_significant_digits": 8,
            "asset_index": 0,
            "source": "fixture",
            "active": True,
        },
        "order": {
            "price": "60000",
            "quantity": "0.0005",
            "observed_leverage": "2",
        },
        "policy": {"require_order_reject_probe": "false"},
        "intent": {
            "entry_reason": None,
            "target_position": "spot long, perp short",
            "normal_exit": "funding closes",
            "risk_exit": "delta drift",
            "max_holding_or_review_at": "next funding",
            "cost_and_risk_budget": "30 bps",
        },
    }

    with pytest.raises(TypeError, match="entry_reason must be a string"):
        order_preflight_from_mapping({**payload, "policy": {}})
    with pytest.raises(TypeError, match="require_order_reject_probe must be a boolean"):
        order_preflight_from_mapping(
            {
                **payload,
                "intent": {**payload["intent"], "entry_reason": "carry"},
            }
        )
