"""Exact, auditable cost accounting for strategy research and execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Any

DecimalInput = Decimal | int | str


def as_decimal(value: DecimalInput, *, field_name: str) -> Decimal:
    """Convert exact input to a finite Decimal and reject binary floats."""

    if isinstance(value, bool) or isinstance(value, float):
        raise TypeError(f"{field_name} must be Decimal, int, or str")
    try:
        result = value if isinstance(value, Decimal) else Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{field_name} is not a valid decimal") from exc
    if not result.is_finite():
        raise ValueError(f"{field_name} must be finite")
    return result


class CostCategory(StrEnum):
    EXECUTION_FEE = "execution_fee"
    MARKET_IMPACT = "market_impact"
    FUNDING_OR_BORROW = "funding_or_borrow"
    LEGGING_LOSS = "legging_loss"
    REBALANCING = "rebalancing"
    TRANSFER_OR_CONVERSION = "transfer_or_conversion"
    REQUOTE = "requote"


class CostBasis(StrEnum):
    OBSERVED = "observed"
    ESTIMATED = "estimated"
    STRESS = "stress"


class ExecutionType(StrEnum):
    MAKER_LIMIT = "maker_limit"
    TAKER_LIMIT = "taker_limit"
    MARKET = "market"
    STOP_MARKET = "stop_market"


@dataclass(frozen=True)
class CostLine:
    """One signed cost line; positive amounts are costs and negative amounts are receipts."""

    category: CostCategory
    amount: DecimalInput
    source: str
    basis: CostBasis = CostBasis.ESTIMATED
    event_id: str = ""
    leg_id: str = ""
    description: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "amount", as_decimal(self.amount, field_name="amount"))
        if not self.source.strip():
            raise ValueError("cost source is required")

    def to_dict(self) -> dict[str, str]:
        return {
            "category": self.category.value,
            "amount": str(self.amount),
            "source": self.source,
            "basis": self.basis.value,
            "event_id": self.event_id,
            "leg_id": self.leg_id,
            "description": self.description,
        }


@dataclass(frozen=True)
class ExecutionLeg:
    """A filled or modeled leg whose fee is based on actual notional turnover."""

    event_id: str
    leg_id: str
    venue: str
    instrument_id: str
    execution_type: ExecutionType
    notional: DecimalInput
    fee_rate: DecimalInput
    fee_source: str
    turnover: DecimalInput = Decimal("1")
    basis: CostBasis = CostBasis.ESTIMATED

    def __post_init__(self) -> None:
        for name in ("event_id", "leg_id", "venue", "instrument_id", "fee_source"):
            if not str(getattr(self, name)).strip():
                raise ValueError(f"{name} is required")
        for name in ("notional", "fee_rate", "turnover"):
            value = as_decimal(getattr(self, name), field_name=name)
            object.__setattr__(self, name, value)
        if self.notional <= 0:
            raise ValueError("notional must be positive")
        if self.fee_rate < 0:
            raise ValueError("fee_rate must be non-negative")
        if self.turnover <= 0:
            raise ValueError("turnover must be positive")

    @property
    def fee(self) -> Decimal:
        return self.notional * self.turnover * self.fee_rate

    def to_cost_line(self) -> CostLine:
        return CostLine(
            category=CostCategory.EXECUTION_FEE,
            amount=self.fee,
            source=self.fee_source,
            basis=self.basis,
            event_id=self.event_id,
            leg_id=self.leg_id,
            description=(
                f"{self.venue} {self.instrument_id} {self.execution_type.value}; "
                f"notional={self.notional} turnover={self.turnover} rate={self.fee_rate}"
            ),
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "event_id": self.event_id,
            "leg_id": self.leg_id,
            "venue": self.venue,
            "instrument_id": self.instrument_id,
            "execution_type": self.execution_type.value,
            "notional": str(self.notional),
            "turnover": str(self.turnover),
            "fee_rate": str(self.fee_rate),
            "fee": str(self.fee),
            "fee_source": self.fee_source,
            "basis": self.basis.value,
        }


@dataclass(frozen=True)
class CostGateResult:
    passed: bool
    observed_gross_edge: Decimal
    required_gross_edge: Decimal
    total_cost: Decimal
    reference_notional: Decimal
    buffer_multiplier: Decimal

    def to_dict(self) -> dict[str, str | bool]:
        return {
            "passed": self.passed,
            "observed_gross_edge": str(self.observed_gross_edge),
            "required_gross_edge": str(self.required_gross_edge),
            "total_cost": str(self.total_cost),
            "reference_notional": str(self.reference_notional),
            "buffer_multiplier": str(self.buffer_multiplier),
        }


@dataclass(frozen=True)
class CostLedger:
    """Immutable collection of complete strategy costs in one quote currency."""

    strategy_id: str
    currency: str = "USDT"
    executions: tuple[ExecutionLeg, ...] = field(default_factory=tuple)
    other_costs: tuple[CostLine, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not self.strategy_id.strip():
            raise ValueError("strategy_id is required")
        if not self.currency.strip():
            raise ValueError("currency is required")

    @property
    def cost_lines(self) -> tuple[CostLine, ...]:
        return tuple(execution.to_cost_line() for execution in self.executions) + self.other_costs

    @property
    def total_cost(self) -> Decimal:
        return sum((line.amount for line in self.cost_lines), start=Decimal("0"))

    def totals_by_category(self) -> dict[CostCategory, Decimal]:
        totals = {category: Decimal("0") for category in CostCategory}
        for line in self.cost_lines:
            totals[line.category] += line.amount
        return totals

    def required_gross_edge(
        self,
        reference_notional: DecimalInput,
        buffer_multiplier: DecimalInput = Decimal("1.5"),
    ) -> Decimal:
        notional = as_decimal(reference_notional, field_name="reference_notional")
        buffer = as_decimal(buffer_multiplier, field_name="buffer_multiplier")
        if notional <= 0:
            raise ValueError("reference_notional must be positive")
        if buffer < 1:
            raise ValueError("buffer_multiplier must be at least 1")
        return max(self.total_cost, Decimal("0")) * buffer / notional

    def evaluate(
        self,
        observed_gross_edge: DecimalInput,
        reference_notional: DecimalInput,
        buffer_multiplier: DecimalInput = Decimal("1.5"),
    ) -> CostGateResult:
        observed = as_decimal(observed_gross_edge, field_name="observed_gross_edge")
        notional = as_decimal(reference_notional, field_name="reference_notional")
        buffer = as_decimal(buffer_multiplier, field_name="buffer_multiplier")
        required = self.required_gross_edge(notional, buffer)
        return CostGateResult(
            passed=observed > required,
            observed_gross_edge=observed,
            required_gross_edge=required,
            total_cost=self.total_cost,
            reference_notional=notional,
            buffer_multiplier=buffer,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "strategy_id": self.strategy_id,
            "currency": self.currency,
            "executions": [execution.to_dict() for execution in self.executions],
            "other_costs": [line.to_dict() for line in self.other_costs],
            "totals_by_category": {
                category.value: str(amount)
                for category, amount in self.totals_by_category().items()
            },
            "total_cost": str(self.total_cost),
        }
