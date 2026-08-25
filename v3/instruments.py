"""Fail-closed instrument and order conformance checks."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Any

from .costs import DecimalInput, as_decimal


class VenueEnvironment(StrEnum):
    TESTNET = "testnet"
    MAINNET = "mainnet"


class ProbeStatus(StrEnum):
    NOT_RUN = "not_run"
    PASSED = "passed"
    FAILED = "failed"


@dataclass(frozen=True)
class InstrumentSpec:
    venue: str
    environment: VenueEnvironment
    instrument_id: str
    minimum_notional: DecimalInput
    minimum_quantity: DecimalInput
    quantity_increment: DecimalInput
    price_increment: DecimalInput
    price_significant_digits: int
    asset_index: int | None
    source: str
    price_max_decimal_places: int | None = None
    integer_price_has_no_significant_digit_limit: bool = False
    is_active: bool = True

    def __post_init__(self) -> None:
        for name in ("venue", "instrument_id", "source"):
            if not str(getattr(self, name)).strip():
                raise ValueError(f"{name} is required")
        for name in (
            "minimum_notional",
            "minimum_quantity",
            "quantity_increment",
            "price_increment",
        ):
            value = as_decimal(getattr(self, name), field_name=name)
            if value <= 0:
                raise ValueError(f"{name} must be positive")
            object.__setattr__(self, name, value)
        if self.price_significant_digits <= 0:
            raise ValueError("price_significant_digits must be positive")
        if self.price_max_decimal_places is not None and self.price_max_decimal_places < 0:
            raise ValueError("price_max_decimal_places must be non-negative")


@dataclass(frozen=True)
class InstrumentPreflightRequest:
    spec: InstrumentSpec
    price: DecimalInput
    quantity: DecimalInput
    observed_leverage: DecimalInput | None
    quote_age_ms: int | None = None
    order_reject_probe: ProbeStatus = ProbeStatus.NOT_RUN

    def __post_init__(self) -> None:
        for name in ("price", "quantity"):
            value = as_decimal(getattr(self, name), field_name=name)
            if value <= 0:
                raise ValueError(f"{name} must be positive")
            object.__setattr__(self, name, value)
        if self.observed_leverage is not None:
            leverage = as_decimal(self.observed_leverage, field_name="observed_leverage")
            if leverage <= 0:
                raise ValueError("observed_leverage must be positive")
            object.__setattr__(self, "observed_leverage", leverage)
        if self.quote_age_ms is not None and self.quote_age_ms < 0:
            raise ValueError("quote_age_ms must be non-negative")

    @property
    def notional(self) -> Decimal:
        return self.price * self.quantity


@dataclass(frozen=True)
class InstrumentPreflightPolicy:
    maximum_leverage: DecimalInput = Decimal("2")
    minimum_notional_headroom: DecimalInput = Decimal("3")
    maximum_quote_age_ms: int | None = None
    require_order_reject_probe: bool = False

    def __post_init__(self) -> None:
        for name in ("maximum_leverage", "minimum_notional_headroom"):
            value = as_decimal(getattr(self, name), field_name=name)
            if value <= 0:
                raise ValueError(f"{name} must be positive")
            object.__setattr__(self, name, value)
        if self.minimum_notional_headroom < 1:
            raise ValueError("minimum_notional_headroom must be at least 1")
        if self.maximum_quote_age_ms is not None and self.maximum_quote_age_ms < 0:
            raise ValueError("maximum_quote_age_ms must be non-negative")


@dataclass(frozen=True)
class PreflightCheck:
    code: str
    passed: bool
    detail: str

    def to_dict(self) -> dict[str, str | bool]:
        return {"code": self.code, "passed": self.passed, "detail": self.detail}


@dataclass(frozen=True)
class InstrumentPreflightResult:
    venue: str
    environment: VenueEnvironment
    instrument_id: str
    notional: Decimal
    checks: tuple[PreflightCheck, ...]

    @property
    def passed(self) -> bool:
        return all(check.passed for check in self.checks)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "passed": self.passed,
            "venue": self.venue,
            "environment": self.environment.value,
            "instrument_id": self.instrument_id,
            "notional": str(self.notional),
            "checks": [check.to_dict() for check in self.checks],
        }


def _aligned(value: Decimal, increment: Decimal) -> bool:
    return value % increment == 0


def _significant_digits(value: Decimal) -> int:
    normalized = value.normalize()
    digits = normalized.as_tuple().digits
    return len(digits)


def _decimal_places(value: Decimal) -> int:
    exponent = value.normalize().as_tuple().exponent
    return max(-exponent, 0)


def check_instrument_conformance(
    request: InstrumentPreflightRequest,
    policy: InstrumentPreflightPolicy | None = None,
) -> InstrumentPreflightResult:
    """Evaluate static metadata and order intent without placing an order."""

    policy = policy or InstrumentPreflightPolicy()
    spec = request.spec
    checks: list[PreflightCheck] = []

    checks.append(
        PreflightCheck(
            "metadata_source",
            bool(spec.source.strip()),
            f"source={spec.source or 'missing'}",
        )
    )
    checks.append(
        PreflightCheck(
            "instrument_active",
            spec.is_active,
            f"active={spec.is_active}",
        )
    )
    checks.append(
        PreflightCheck(
            "asset_index",
            spec.asset_index is not None and spec.asset_index >= 0,
            f"asset_index={spec.asset_index}",
        )
    )
    leverage_ok = (
        request.observed_leverage is not None
        and request.observed_leverage <= policy.maximum_leverage
    )
    checks.append(
        PreflightCheck(
            "leverage",
            leverage_ok,
            (
                f"observed={request.observed_leverage} maximum={policy.maximum_leverage}"
                if request.observed_leverage is not None
                else "observed leverage is unavailable"
            ),
        )
    )
    required_notional = spec.minimum_notional * policy.minimum_notional_headroom
    checks.append(
        PreflightCheck(
            "minimum_notional_headroom",
            request.notional >= required_notional,
            f"notional={request.notional} required={required_notional}",
        )
    )
    checks.append(
        PreflightCheck(
            "minimum_quantity",
            request.quantity >= spec.minimum_quantity,
            f"quantity={request.quantity} minimum={spec.minimum_quantity}",
        )
    )
    checks.append(
        PreflightCheck(
            "quantity_increment",
            _aligned(request.quantity, spec.quantity_increment),
            f"quantity={request.quantity} increment={spec.quantity_increment}",
        )
    )
    checks.append(
        PreflightCheck(
            "price_increment",
            _aligned(request.price, spec.price_increment),
            f"price={request.price} increment={spec.price_increment}",
        )
    )
    price_digits = _significant_digits(request.price)
    integer_price = request.price == request.price.to_integral_value()
    significant_digits_ok = price_digits <= spec.price_significant_digits or (
        integer_price and spec.integer_price_has_no_significant_digit_limit
    )
    checks.append(
        PreflightCheck(
            "price_significant_digits",
            significant_digits_ok,
            (
                f"observed={price_digits} maximum={spec.price_significant_digits} "
                f"integer_exception={spec.integer_price_has_no_significant_digit_limit}"
            ),
        )
    )
    if spec.price_max_decimal_places is not None:
        decimal_places = _decimal_places(request.price)
        checks.append(
            PreflightCheck(
                "price_decimal_places",
                decimal_places <= spec.price_max_decimal_places,
                f"observed={decimal_places} maximum={spec.price_max_decimal_places}",
            )
        )

    if policy.maximum_quote_age_ms is not None:
        quote_ok = (
            request.quote_age_ms is not None and request.quote_age_ms <= policy.maximum_quote_age_ms
        )
        checks.append(
            PreflightCheck(
                "quote_age",
                quote_ok,
                (
                    f"observed_ms={request.quote_age_ms} maximum_ms={policy.maximum_quote_age_ms}"
                    if request.quote_age_ms is not None
                    else "quote age is unavailable"
                ),
            )
        )

    probe_ok = request.order_reject_probe is not ProbeStatus.FAILED and (
        not policy.require_order_reject_probe or request.order_reject_probe is ProbeStatus.PASSED
    )
    checks.append(
        PreflightCheck(
            "order_reject_probe",
            probe_ok,
            f"status={request.order_reject_probe.value} required={policy.require_order_reject_probe}",
        )
    )

    return InstrumentPreflightResult(
        venue=spec.venue,
        environment=spec.environment,
        instrument_id=spec.instrument_id,
        notional=request.notional,
        checks=tuple(checks),
    )
