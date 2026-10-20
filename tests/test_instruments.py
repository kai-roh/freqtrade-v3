from decimal import Decimal

from v3.instruments import (
    InstrumentPreflightPolicy,
    InstrumentPreflightRequest,
    InstrumentSpec,
    ProbeStatus,
    VenueEnvironment,
    check_instrument_conformance,
)


def _spec():
    return InstrumentSpec(
        venue="hyperliquid",
        environment=VenueEnvironment.MAINNET,
        instrument_id="BTC-PERP",
        minimum_notional="10",
        minimum_quantity="0.00001",
        quantity_increment="0.00001",
        price_increment="1",
        price_significant_digits=5,
        price_max_decimal_places=1,
        integer_price_has_no_significant_digit_limit=True,
        asset_index=0,
        source="venue-meta-snapshot-2026-08-19",
    )


def _request(**overrides):
    values = {
        "spec": _spec(),
        "price": "60000",
        "quantity": "0.00050",
        "observed_leverage": "2",
        "quote_age_ms": 100,
        "order_reject_probe": ProbeStatus.PASSED,
    }
    values.update(overrides)
    return InstrumentPreflightRequest(**values)


def test_instrument_preflight_passes_exact_three_x_headroom():
    result = check_instrument_conformance(
        _request(),
        InstrumentPreflightPolicy(
            maximum_quote_age_ms=250,
            require_order_reject_probe=True,
        ),
    )

    assert result.passed
    assert result.notional == Decimal("30.00000")
    assert result.to_dict()["environment"] == "mainnet"


def test_instrument_preflight_fails_closed_when_leverage_is_unknown_or_too_high():
    unknown = check_instrument_conformance(_request(observed_leverage=None))
    too_high = check_instrument_conformance(_request(observed_leverage="2.1"))

    assert not unknown.passed
    assert not too_high.passed
    assert not next(check for check in unknown.checks if check.code == "leverage").passed


def test_instrument_preflight_rejects_small_misaligned_or_stale_order():
    result = check_instrument_conformance(
        _request(price="60000.5", quantity="0.00049", quote_age_ms=251),
        InstrumentPreflightPolicy(maximum_quote_age_ms=250),
    )
    failures = {check.code for check in result.checks if not check.passed}

    assert {"minimum_notional_headroom", "price_increment", "quote_age"}.issubset(failures)


def test_order_reject_probe_can_be_mandatory_for_phase_one():
    result = check_instrument_conformance(
        _request(order_reject_probe=ProbeStatus.NOT_RUN),
        InstrumentPreflightPolicy(require_order_reject_probe=True),
    )

    assert not result.passed
    assert not next(check for check in result.checks if check.code == "order_reject_probe").passed


def test_integer_price_bypasses_significant_digits_but_not_decimal_precision():
    integer = check_instrument_conformance(_request(price="123456"))
    too_many_significant_digits = check_instrument_conformance(_request(price="12345.6"))
    too_many_decimal_places = check_instrument_conformance(_request(price="60000.01"))

    assert integer.passed
    assert not next(
        check
        for check in too_many_significant_digits.checks
        if check.code == "price_significant_digits"
    ).passed
    assert not next(
        check for check in too_many_decimal_places.checks if check.code == "price_decimal_places"
    ).passed


def test_delisted_instrument_fails_closed():
    spec = InstrumentSpec(**{**_spec().__dict__, "is_active": False})
    result = check_instrument_conformance(_request(spec=spec))

    assert not result.passed
    assert not next(check for check in result.checks if check.code == "instrument_active").passed
