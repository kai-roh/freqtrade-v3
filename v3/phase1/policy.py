"""Machine-readable Phase 1 policy with fail-closed validation."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from v3.costs import as_decimal

EXPECTED_INTENT_FIELDS = (
    "entry_reason",
    "target_position",
    "normal_exit",
    "risk_exit",
    "max_holding_or_review_at",
    "cost_and_risk_budget",
)


def _mapping(data: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = data.get(key)
    if not isinstance(value, Mapping):
        raise ValueError(f"{key} must be an object")
    return value


def _decimal(data: Mapping[str, Any], key: str) -> Decimal:
    if key not in data:
        raise ValueError(f"{key} is required")
    return as_decimal(data[key], field_name=key)


def _optional_decimal(data: Mapping[str, Any], key: str) -> Decimal | None:
    value = data.get(key)
    if value is None:
        return None
    return as_decimal(value, field_name=key)


def _positive_int(data: Mapping[str, Any], key: str) -> int:
    value = data.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{key} must be a positive integer")
    return value


@dataclass(frozen=True)
class FeeSchedule:
    spot_maker_bps: Decimal | None
    spot_taker_bps: Decimal | None
    perp_maker_bps: Decimal | None
    perp_taker_bps: Decimal | None
    source: str
    include_exit_cost: bool
    captured_at: datetime | None = None
    maximum_age_hours: int | None = None

    def __post_init__(self) -> None:
        for name in (
            "spot_maker_bps",
            "spot_taker_bps",
            "perp_maker_bps",
            "perp_taker_bps",
        ):
            value = getattr(self, name)
            if value is not None and value < 0:
                raise ValueError(f"{name} must be non-negative")
        if not self.source.strip():
            raise ValueError("fee source is required")
        if self.captured_at is not None:
            if self.captured_at.tzinfo is None or self.captured_at.utcoffset() is None:
                raise ValueError("fee captured_at must include a timezone")
            object.__setattr__(self, "captured_at", self.captured_at.astimezone(UTC))
        if self.maximum_age_hours is not None and self.maximum_age_hours <= 0:
            raise ValueError("fee maximum_age_hours must be positive")

    @property
    def complete(self) -> bool:
        return all(
            value is not None
            for value in (
                self.spot_maker_bps,
                self.spot_taker_bps,
                self.perp_maker_bps,
                self.perp_taker_bps,
            )
        )

    @property
    def maker_entry_bps(self) -> Decimal | None:
        if self.spot_maker_bps is None or self.perp_maker_bps is None:
            return None
        return self.spot_maker_bps + self.perp_maker_bps

    @property
    def maker_round_trip_bps(self) -> Decimal | None:
        entry = self.maker_entry_bps
        if entry is None:
            return None
        return entry * (2 if self.include_exit_cost else 1)

    def is_fresh(self, at: datetime) -> bool:
        if at.tzinfo is None or at.utcoffset() is None:
            raise ValueError("fee freshness timestamp must include a timezone")
        if not self.complete or self.captured_at is None or self.maximum_age_hours is None:
            return False
        age = at.astimezone(UTC) - self.captured_at
        return timedelta(0) <= age <= timedelta(hours=self.maximum_age_hours)


@dataclass(frozen=True)
class Phase1Policy:
    schema_version: int
    environment: str
    live_orders: bool
    real_capital: bool
    allowed_instruments: frozenset[str]
    synthetic_environments: frozenset[str]
    total_capital: Decimal
    carry_sleeve_fraction: Decimal
    maximum_leverage: Decimal
    minimum_notional_headroom: Decimal
    maximum_delta_drift_fraction: Decimal
    maximum_abort_cost_bps: Decimal
    monthly_abort_budget_fraction: Decimal
    maximum_abort_attempts_per_month: int
    consecutive_abort_halt_threshold: int
    daily_loss_fraction: Decimal
    maximum_quote_age_ms: int | None
    assumed_abort_probability: Decimal
    minimum_expected_net_bps: Decimal
    minimum_holding_hours: int
    maximum_holding_hours: int
    required_intent_fields: tuple[str, ...]
    fee_schedule: FeeSchedule
    raw: Mapping[str, Any]

    def __post_init__(self) -> None:
        if self.schema_version != 2:
            raise ValueError("Phase 1 policy schema_version must be 2")
        if self.environment != "demo" or self.live_orders or self.real_capital:
            raise ValueError("Phase 1 policy must remain demo-only with capital authorization off")
        if self.allowed_instruments != {
            "BTCUSDT.BINANCE",
            "BTCUSDT-PERP.BINANCE",
        }:
            raise ValueError("Phase 1 instruments must be the approved BTCUSDT spot/perp pair")
        if "live" in self.synthetic_environments:
            raise ValueError("synthetic targets must never be allowed in live")
        if self.total_capital <= 0:
            raise ValueError("total capital must be positive")
        if not Decimal("0") < self.carry_sleeve_fraction <= Decimal("1"):
            raise ValueError("carry sleeve fraction must be in (0, 1]")
        if not Decimal("0") < self.maximum_leverage <= Decimal("2"):
            raise ValueError("maximum leverage must be in (0, 2]")
        if self.minimum_notional_headroom < Decimal("3"):
            raise ValueError("minimum notional headroom must be at least 3")
        if not Decimal("0") < self.maximum_delta_drift_fraction <= Decimal("0.05"):
            raise ValueError("maximum delta drift must be in (0, 0.05]")
        if self.maximum_abort_cost_bps <= 0:
            raise ValueError("maximum abort cost must be positive")
        if self.monthly_abort_budget_fraction <= 0:
            raise ValueError("monthly abort budget fraction must be positive")
        if not Decimal("0") < self.daily_loss_fraction <= Decimal("0.02"):
            raise ValueError("daily loss fraction must be in (0, 0.02]")
        if self.maximum_quote_age_ms is not None and self.maximum_quote_age_ms <= 0:
            raise ValueError("maximum quote age must be positive when measured")
        if not Decimal("0") <= self.assumed_abort_probability <= Decimal("1"):
            raise ValueError("assumed abort probability must be between 0 and 1")
        if self.minimum_expected_net_bps <= 0:
            raise ValueError("minimum expected net bps must be positive")
        if self.minimum_holding_hours >= self.maximum_holding_hours:
            raise ValueError("minimum holding hours must be below maximum holding hours")
        if self.required_intent_fields != EXPECTED_INTENT_FIELDS:
            raise ValueError("intent required fields differ from the six-field contract")

    @property
    def carry_sleeve_capital(self) -> Decimal:
        return self.total_capital * self.carry_sleeve_fraction

    @property
    def monthly_abort_budget(self) -> Decimal:
        return self.carry_sleeve_capital * self.monthly_abort_budget_fraction

    @property
    def maximum_carry_leg_notional(self) -> Decimal:
        """Cash spot plus isolated perp margin must fit inside the carry sleeve."""

        capital_per_notional = Decimal("1") + (Decimal("1") / self.maximum_leverage)
        return self.carry_sleeve_capital / capital_per_notional

    def synthetic_target_reasons(
        self,
        *,
        environment: str,
        live_orders: bool,
        real_capital: bool,
    ) -> tuple[str, ...]:
        reasons: list[str] = []
        if environment not in self.synthetic_environments:
            reasons.append("synthetic targets are restricted to demo/testnet")
        if live_orders:
            reasons.append("synthetic targets are forbidden when live orders are authorized")
        if real_capital:
            reasons.append("synthetic targets are forbidden with real capital")
        return tuple(reasons)


def policy_from_mapping(data: Mapping[str, Any]) -> Phase1Policy:
    execution = _mapping(data, "execution")
    authorization = _mapping(data, "authorization")
    capital = _mapping(data, "capital")
    risk = _mapping(data, "risk")
    scanner = _mapping(data, "scanner")
    sla = _mapping(data, "sla")
    instruments = _mapping(data, "instruments")
    synthetic = _mapping(data, "synthetic_target")
    intent = _mapping(data, "intent")
    costs = _mapping(data, "cost_model")
    order_types = _mapping(data, "order_types")
    source = _mapping(data, "source")

    allocation_keys = (
        "carry_sleeve_fraction",
        "basket_sleeve_fraction",
        "margin_buffer_fraction",
        "legging_hedge_fraction",
        "operating_fraction",
        "reserve_fraction",
    )
    allocation_total = sum((_decimal(capital, key) for key in allocation_keys), Decimal("0"))
    if allocation_total != Decimal("1"):
        raise ValueError("capital sleeve fractions must sum to 1")
    if (
        authorization.get("live_orders") is not False
        or authorization.get("real_capital") is not False
    ):
        raise ValueError("Phase 1 authorization flags must be explicit JSON false values")
    if execution.get("engine") != "nautilus_trader" or execution.get("primary_venue") != "binance":
        raise ValueError("Phase 1 execution engine and venue must remain NautilusTrader/Binance")
    if execution.get("product_types") != ["spot", "usd_m"]:
        raise ValueError("Phase 1 products must remain Spot and USD-M")
    if order_types != {
        "spot_post_only": "LIMIT_MAKER",
        "perp_post_only": "GTX",
        "emergency_hedge": "IOC_LIMIT",
    }:
        raise ValueError("Phase 1 order types differ from the approved execution contract")
    if not all(
        source.get(key) is True
        for key in (
            "require_clean_worktree",
            "require_dependency_lock_hash",
            "require_image_digest",
        )
    ):
        raise ValueError("all Phase 1 source admission gates must be enabled")
    if synthetic.get("forbidden_when_live_authorized") is not True:
        raise ValueError("synthetic targets must be forbidden when live is authorized")
    if risk.get("abort_budget_scope") != "per_month":
        raise ValueError("abort budget scope must be per_month")
    if sla.get("unmeasured_behavior") != "deny":
        raise ValueError("unmeasured quote-age behavior must deny execution")
    if costs.get("demo_fee_treatment") != "ignore":
        raise ValueError("Demo-reported fees must not drive the cost ledger")
    if costs.get("fee_source") != "credentialed_mainnet_account_query":
        raise ValueError("fees must come from a credentialed mainnet account query")
    if costs.get("unmeasured_behavior") != "observe_only":
        raise ValueError("unmeasured fees must keep the scanner observation-only")
    if costs.get("include_exit_cost") is not True:
        raise ValueError("successful carry economics must include exit cost")
    fee_values = tuple(
        costs.get(key)
        for key in ("spot_maker_bps", "spot_taker_bps", "perp_maker_bps", "perp_taker_bps")
    )
    if any(value is not None for value in fee_values) and not all(
        value is not None for value in fee_values
    ):
        raise ValueError("credentialed fee schedule must be entirely measured or entirely null")
    fee_captured_at = costs.get("snapshot_captured_at")
    fee_snapshot_evidence = costs.get("snapshot_evidence")
    fee_maximum_age_hours = costs.get("snapshot_maximum_age_hours")
    if all(value is not None for value in fee_values):
        if costs.get("bnb_discount_applied") is not False:
            raise ValueError(
                "Phase 1 fee schedule must conservatively exclude optional BNB discount"
            )
        if not isinstance(fee_captured_at, str) or not fee_captured_at.strip():
            raise ValueError("measured fee schedule requires snapshot_captured_at")
        if (
            not isinstance(fee_snapshot_evidence, str)
            or not fee_snapshot_evidence.startswith("evidence/phase1/")
            or not fee_snapshot_evidence.endswith(".json")
        ):
            raise ValueError("measured fee schedule requires a Phase 1 evidence JSON path")
        if (
            isinstance(fee_maximum_age_hours, bool)
            or not isinstance(fee_maximum_age_hours, int)
            or fee_maximum_age_hours <= 0
        ):
            raise ValueError("measured fee schedule requires positive snapshot_maximum_age_hours")
        entry_cost = _decimal(costs, "normal_entry_cost_bps")
        round_trip_cost = _decimal(costs, "normal_round_trip_cost_bps")
        expected_entry = _decimal(costs, "spot_maker_bps") + _decimal(costs, "perp_maker_bps")
        if entry_cost != expected_entry or round_trip_cost != expected_entry * 2:
            raise ValueError("declared normal costs differ from measured maker fees")
    elif any(
        costs.get(key) is not None
        for key in (
            "bnb_discount_applied",
            "normal_entry_cost_bps",
            "normal_round_trip_cost_bps",
            "snapshot_captured_at",
            "snapshot_evidence",
            "snapshot_maximum_age_hours",
        )
    ):
        raise ValueError("unmeasured fee schedule metadata must remain null")
    if scanner.get("replace_prior_after_phase") != "3":
        raise ValueError("Demo abort measurements cannot replace the prior before Phase 3")

    quote_age = sla.get("maximum_quote_age_ms")
    if quote_age is not None and (isinstance(quote_age, bool) or not isinstance(quote_age, int)):
        raise ValueError("maximum_quote_age_ms must be an integer or null")

    required_fields = intent.get("required_fields")
    if not isinstance(required_fields, list) or not all(
        isinstance(value, str) for value in required_fields
    ):
        raise ValueError("intent.required_fields must be a string list")

    return Phase1Policy(
        schema_version=int(data.get("schema_version", 0)),
        environment=str(execution.get("environment", "")),
        live_orders=authorization["live_orders"],
        real_capital=authorization["real_capital"],
        allowed_instruments=frozenset(str(value) for value in instruments.values()),
        synthetic_environments=frozenset(
            str(value) for value in synthetic.get("allowed_environments", [])
        ),
        total_capital=_decimal(capital, "total"),
        carry_sleeve_fraction=_decimal(capital, "carry_sleeve_fraction"),
        maximum_leverage=_decimal(risk, "maximum_leverage"),
        minimum_notional_headroom=_decimal(risk, "minimum_notional_headroom"),
        maximum_delta_drift_fraction=_decimal(risk, "maximum_delta_drift_fraction"),
        maximum_abort_cost_bps=_decimal(risk, "maximum_abort_cost_bps"),
        monthly_abort_budget_fraction=_decimal(
            risk, "monthly_abort_budget_fraction_of_carry_sleeve"
        ),
        maximum_abort_attempts_per_month=_positive_int(risk, "maximum_abort_attempts_per_month"),
        consecutive_abort_halt_threshold=_positive_int(risk, "consecutive_abort_halt_threshold"),
        daily_loss_fraction=_decimal(risk, "daily_loss_fraction_of_total_capital"),
        maximum_quote_age_ms=quote_age,
        assumed_abort_probability=_decimal(scanner, "assumed_abort_probability"),
        minimum_expected_net_bps=_decimal(scanner, "minimum_expected_net_bps"),
        minimum_holding_hours=_positive_int(scanner, "minimum_holding_hours"),
        maximum_holding_hours=_positive_int(scanner, "maximum_holding_hours"),
        required_intent_fields=tuple(required_fields),
        fee_schedule=FeeSchedule(
            spot_maker_bps=_optional_decimal(costs, "spot_maker_bps"),
            spot_taker_bps=_optional_decimal(costs, "spot_taker_bps"),
            perp_maker_bps=_optional_decimal(costs, "perp_maker_bps"),
            perp_taker_bps=_optional_decimal(costs, "perp_taker_bps"),
            source=str(costs.get("fee_source", "")),
            include_exit_cost=costs.get("include_exit_cost") is True,
            captured_at=(
                datetime.fromisoformat(fee_captured_at)
                if isinstance(fee_captured_at, str)
                else None
            ),
            maximum_age_hours=(
                fee_maximum_age_hours if isinstance(fee_maximum_age_hours, int) else None
            ),
        ),
        raw=data,
    )


def load_phase1_policy(path: Path) -> Phase1Policy:
    data = json.loads(path.read_text())
    if not isinstance(data, Mapping):
        raise ValueError("Phase 1 policy must be a JSON object")
    return policy_from_mapping(data)
