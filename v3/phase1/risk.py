"""Independent fail-closed risk decision for a Phase 1 carry intent."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from v3.costs import DecimalInput, as_decimal

from .policy import Phase1Policy


@dataclass(frozen=True)
class CarryRiskContext:
    intent_fields: dict[str, str]
    cost_ledger_complete: bool
    leverage_by_instrument: dict[str, DecimalInput]
    quote_age_ms: int | None
    leg_notional: DecimalInput
    minimum_notional_by_instrument: dict[str, DecimalInput]
    local_positions_match_venue: bool
    unexplained_residual_usdt: DecimalInput
    residual_unclassified_hours: DecimalInput
    daily_loss_usdt: DecimalInput
    monthly_abort_cost_usdt: DecimalInput
    abort_attempts_this_month: int
    consecutive_aborts: int
    idempotency_key_is_new: bool
    environment: str
    live_orders: bool
    real_capital: bool
    evaluated_at: datetime

    def __post_init__(self) -> None:
        for name in (
            "leg_notional",
            "unexplained_residual_usdt",
            "residual_unclassified_hours",
            "daily_loss_usdt",
            "monthly_abort_cost_usdt",
        ):
            object.__setattr__(self, name, as_decimal(getattr(self, name), field_name=name))
        if self.leg_notional <= 0:
            raise ValueError("leg_notional must be positive")
        if self.quote_age_ms is not None and self.quote_age_ms < 0:
            raise ValueError("quote_age_ms must be non-negative")
        if self.abort_attempts_this_month < 0 or self.consecutive_aborts < 0:
            raise ValueError("abort counts must be non-negative")
        if self.evaluated_at.tzinfo is None or self.evaluated_at.utcoffset() is None:
            raise ValueError("evaluated_at must include a timezone")
        object.__setattr__(self, "evaluated_at", self.evaluated_at.astimezone(UTC))
        for name in (
            "unexplained_residual_usdt",
            "residual_unclassified_hours",
            "daily_loss_usdt",
            "monthly_abort_cost_usdt",
        ):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} must be non-negative")


@dataclass(frozen=True)
class RiskDecision:
    approved: bool
    reasons: tuple[str, ...]
    observed_leverage: dict[str, str]
    quote_age_ms: int | None
    evaluated_at: datetime

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "approved": self.approved,
            "reasons": list(self.reasons),
            "observed_leverage": self.observed_leverage,
            "quote_age_ms": self.quote_age_ms,
            "evaluated_at": self.evaluated_at.isoformat(),
        }


def evaluate_carry_risk(context: CarryRiskContext, policy: Phase1Policy) -> RiskDecision:
    reasons: list[str] = []
    observed_leverage: dict[str, str] = {}
    exact_leverage: dict[str, Decimal] = {}

    missing_fields = [
        name
        for name in policy.required_intent_fields
        if not context.intent_fields.get(name, "").strip()
    ]
    if missing_fields:
        reasons.append(f"intent fields missing: {', '.join(missing_fields)}")
    if not context.cost_ledger_complete:
        reasons.append("cost ledger is incomplete")
    if not policy.fee_schedule.complete:
        reasons.append("credentialed mainnet fee schedule is incomplete")
    elif not policy.fee_schedule.is_fresh(context.evaluated_at):
        reasons.append("credentialed mainnet fee schedule is stale")
    if context.leg_notional > policy.maximum_carry_leg_notional:
        reasons.append("leg notional exceeds the carry sleeve collateral boundary")

    for instrument in policy.allowed_instruments:
        raw = context.leverage_by_instrument.get(instrument)
        if raw is None:
            reasons.append(f"leverage is unknown for {instrument}")
            continue
        try:
            leverage = as_decimal(raw, field_name=f"leverage[{instrument}]")
        except (TypeError, ValueError):
            reasons.append(f"leverage is invalid for {instrument}")
            continue
        observed_leverage[instrument] = str(leverage)
        exact_leverage[instrument] = leverage
        if leverage <= 0 or leverage > policy.maximum_leverage:
            reasons.append(f"leverage exceeds policy for {instrument}")

    perp_leverage = exact_leverage.get("BTCUSDT-PERP.BINANCE")
    if perp_leverage is not None and perp_leverage > 0:
        maximum_notional_at_observed_leverage = policy.carry_sleeve_capital / (
            Decimal("1") + (Decimal("1") / perp_leverage)
        )
        if context.leg_notional > maximum_notional_at_observed_leverage:
            reasons.append("leg notional exceeds collateral available at observed leverage")

    if context.quote_age_ms is None:
        reasons.append("quote age is unmeasured")
    elif policy.maximum_quote_age_ms is None:
        reasons.append("quote-age SLA is unmeasured")
    elif context.quote_age_ms > policy.maximum_quote_age_ms:
        reasons.append("quote is stale")

    for instrument in policy.allowed_instruments:
        raw_minimum = context.minimum_notional_by_instrument.get(instrument)
        if raw_minimum is None:
            reasons.append(f"minimum notional is unknown for {instrument}")
            continue
        minimum = as_decimal(raw_minimum, field_name=f"minimum_notional[{instrument}]")
        if minimum <= 0:
            reasons.append(f"minimum notional is invalid for {instrument}")
        elif context.leg_notional < minimum * policy.minimum_notional_headroom:
            reasons.append(f"notional headroom is insufficient for {instrument}")

    if not context.local_positions_match_venue:
        reasons.append("local positions do not match venue")
    _check_reconciliation(context, policy, reasons)

    daily_loss_limit = policy.total_capital * policy.daily_loss_fraction
    if context.daily_loss_usdt >= daily_loss_limit:
        reasons.append("daily loss limit reached")
    if context.monthly_abort_cost_usdt >= policy.monthly_abort_budget:
        reasons.append("monthly abort budget reached")
    if context.abort_attempts_this_month >= policy.maximum_abort_attempts_per_month:
        reasons.append("monthly abort attempt limit reached")
    if context.consecutive_aborts >= policy.consecutive_abort_halt_threshold:
        reasons.append("consecutive abort halt threshold reached")
    if not context.idempotency_key_is_new:
        reasons.append("idempotency key already exists")
    if context.environment != "demo" or context.live_orders or context.real_capital:
        reasons.append("runtime authorization is outside the Phase 1 boundary")

    return RiskDecision(
        approved=not reasons,
        reasons=tuple(reasons),
        observed_leverage=observed_leverage,
        quote_age_ms=context.quote_age_ms,
        evaluated_at=context.evaluated_at,
    )


def _check_reconciliation(
    context: CarryRiskContext,
    policy: Phase1Policy,
    reasons: list[str],
) -> None:
    if context.unexplained_residual_usdt <= 0:
        return
    reconciliation = policy.raw["reconciliation"]
    maximum_residual = reconciliation["maximum_unexplained_residual_usdt"]
    maximum_hours = reconciliation["maximum_unclassified_hours"]
    if maximum_residual is None or maximum_hours is None:
        reasons.append("reconciliation thresholds are unmeasured")
        return
    if context.unexplained_residual_usdt >= as_decimal(
        maximum_residual, field_name="maximum_unexplained_residual_usdt"
    ):
        reasons.append("unexplained reconciliation residual exceeds policy")
    if context.residual_unclassified_hours >= as_decimal(
        maximum_hours, field_name="maximum_unclassified_hours"
    ):
        reasons.append("reconciliation residual exceeded classification time")
