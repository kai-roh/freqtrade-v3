"""Runtime order admission built on instrument conformance and mandatory intent."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .instruments import (
    InstrumentPreflightPolicy,
    InstrumentPreflightRequest,
    InstrumentPreflightResult,
    check_instrument_conformance,
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
