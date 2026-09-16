"""Runtime order admission built on instrument conformance and mandatory intent."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import Any

from .instruments import (
    InstrumentPreflightPolicy,
    InstrumentPreflightRequest,
    InstrumentPreflightResult,
    check_instrument_conformance,
    instrument_preflight_policy_from_mapping,
    instrument_preflight_request_from_mapping,
)


@dataclass(frozen=True)
class IntentRecord:
    """The six strategy-independent fields required before any order is admitted."""

    entry_reason: str
    target_position: str
    normal_exit: str
    risk_exit: str
    max_holding_or_review_at: str
    cost_and_risk_budget: str

    def __post_init__(self) -> None:
        for key, value in asdict(self).items():
            if not value.strip():
                raise ValueError(f"{key} must not be blank")

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class OrderPreflight:
    instrument: InstrumentPreflightRequest
    intent: IntentRecord | None
    policy: InstrumentPreflightPolicy = InstrumentPreflightPolicy()


@dataclass(frozen=True)
class PreflightResult:
    passed: bool
    reasons: tuple[str, ...]
    instrument: InstrumentPreflightResult
    intent: dict[str, str] | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "passed": self.passed,
            "reasons": list(self.reasons),
            "instrument": self.instrument.to_dict(),
            "intent": self.intent,
        }


def intent_record_from_mapping(data: Mapping[str, Any]) -> IntentRecord:
    return IntentRecord(
        entry_reason=_required_intent_text(data, "entry_reason"),
        target_position=_required_intent_text(data, "target_position"),
        normal_exit=_required_intent_text(data, "normal_exit"),
        risk_exit=_required_intent_text(data, "risk_exit"),
        max_holding_or_review_at=_required_intent_text(data, "max_holding_or_review_at"),
        cost_and_risk_budget=_required_intent_text(data, "cost_and_risk_budget"),
    )


def _required_intent_text(data: Mapping[str, Any], field_name: str) -> str:
    value = data[field_name]
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    return value


def order_preflight_from_mapping(data: Mapping[str, Any]) -> OrderPreflight:
    """Build final order admission input from the public JSON preflight schema."""

    intent = data.get("intent")
    if intent is not None and not isinstance(intent, Mapping):
        raise TypeError("intent must be a JSON object")
    return OrderPreflight(
        instrument=instrument_preflight_request_from_mapping(data),
        intent=intent_record_from_mapping(intent) if intent is not None else None,
        policy=instrument_preflight_policy_from_mapping(data.get("policy")),
    )


def validate_order_preflight(preflight: OrderPreflight) -> PreflightResult:
    instrument = check_instrument_conformance(preflight.instrument, preflight.policy)
    reasons = tuple(
        f"{check.code}: {check.detail}" for check in instrument.checks if not check.passed
    )
    if preflight.intent is None:
        reasons += ("intent: all six intent fields are required",)
    return PreflightResult(
        passed=not reasons,
        reasons=reasons,
        instrument=instrument,
        intent=preflight.intent.to_dict() if preflight.intent is not None else None,
    )
