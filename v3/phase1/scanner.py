"""Order-free funding carry scanner with abort-weighted economics."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal

from v3.costs import DecimalInput, as_decimal

from .policy import FeeSchedule, Phase1Policy


@dataclass(frozen=True)
class CarryObservation:
    venue: str
    spot_instrument_id: str
    perp_instrument_id: str
    requested_notional: DecimalInput
    funding_rate: DecimalInput
    funding_interval_minutes: int
    holding_period_hours: int
    instrument_snapshot_id: str
    other_success_cost_bps: DecimalInput = Decimal("0")

    def __post_init__(self) -> None:
        for name in ("requested_notional", "funding_rate", "other_success_cost_bps"):
            object.__setattr__(self, name, as_decimal(getattr(self, name), field_name=name))
        if self.venue != "binance":
            raise ValueError("Phase 1 carry venue must be binance")
        if not self.instrument_snapshot_id.strip():
            raise ValueError("instrument_snapshot_id is required")
        if self.requested_notional <= 0:
            raise ValueError("requested_notional must be positive")
        if self.funding_interval_minutes <= 0:
            raise ValueError("funding_interval_minutes must be positive")
        if self.holding_period_hours <= 0:
            raise ValueError("holding_period_hours must be positive")
        if self.other_success_cost_bps < 0:
            raise ValueError("other_success_cost_bps must be non-negative")


@dataclass(frozen=True)
class CarryTarget:
    venue: str
    spot_instrument_id: str
    perp_instrument_id: str
    target_notional: Decimal
    funding_rate: Decimal
    funding_interval_minutes: int
    expected_gross_bps: Decimal
    expected_success_cost_bps: Decimal | None
    net_expected_bps: Decimal | None
    assumed_abort_probability: Decimal
    holding_period_hours: int
    decision_reason: str
    instrument_snapshot_id: str
    cost_ledger_id: str

    @property
    def actionable(self) -> bool:
        return self.target_notional > 0

    def to_dict(self) -> dict[str, str | int | None | bool]:
        return {
            "schema_version": 1,
            "venue": self.venue,
            "spot_instrument_id": self.spot_instrument_id,
            "perp_instrument_id": self.perp_instrument_id,
            "target_notional": str(self.target_notional),
            "funding_rate": str(self.funding_rate),
            "funding_interval_minutes": self.funding_interval_minutes,
            "expected_gross_bps": str(self.expected_gross_bps),
            "expected_success_cost_bps": (
                str(self.expected_success_cost_bps)
                if self.expected_success_cost_bps is not None
                else None
            ),
            "net_expected_bps": (
                str(self.net_expected_bps) if self.net_expected_bps is not None else None
            ),
            "assumed_abort_probability": str(self.assumed_abort_probability),
            "holding_period_hours": self.holding_period_hours,
            "decision_reason": self.decision_reason,
            "instrument_snapshot_id": self.instrument_snapshot_id,
            "cost_ledger_id": self.cost_ledger_id,
            "actionable": self.actionable,
        }


def scan_carry(
    observation: CarryObservation,
    policy: Phase1Policy,
    *,
    fee_schedule: FeeSchedule | None = None,
) -> CarryTarget:
    if {
        observation.spot_instrument_id,
        observation.perp_instrument_id,
    } != policy.allowed_instruments:
        raise ValueError("observation instruments differ from the approved Phase 1 pair")
    if (
        not policy.minimum_holding_hours
        <= observation.holding_period_hours
        <= (policy.maximum_holding_hours)
    ):
        raise ValueError("holding period is outside the scanner policy range")
    if observation.requested_notional > policy.maximum_carry_leg_notional:
        raise ValueError("requested notional exceeds the carry sleeve collateral boundary")

    intervals = Decimal(observation.holding_period_hours * 60) / Decimal(
        observation.funding_interval_minutes
    )
    gross_bps = observation.funding_rate * intervals * Decimal("10000")
    schedule = fee_schedule or policy.fee_schedule
    round_trip_bps = schedule.maker_round_trip_bps
    cost_ledger_id = _cost_ledger_id(observation, policy, schedule)

    if round_trip_bps is None:
        return _zero_target(
            observation,
            policy,
            gross_bps,
            None,
            None,
            "observe_only: credentialed mainnet fee schedule is incomplete",
            cost_ledger_id,
        )

    success_cost_bps = round_trip_bps + observation.other_success_cost_bps
    probability = policy.assumed_abort_probability
    expected_net_bps = (Decimal("1") - probability) * (
        gross_bps - success_cost_bps
    ) - probability * policy.maximum_abort_cost_bps

    if observation.funding_rate <= 0:
        reason = "no_target: long-spot/short-perp funding is not positive"
    elif expected_net_bps < policy.minimum_expected_net_bps:
        reason = "no_target: abort-weighted expected net is below policy minimum"
    else:
        return CarryTarget(
            venue=observation.venue,
            spot_instrument_id=observation.spot_instrument_id,
            perp_instrument_id=observation.perp_instrument_id,
            target_notional=observation.requested_notional,
            funding_rate=observation.funding_rate,
            funding_interval_minutes=observation.funding_interval_minutes,
            expected_gross_bps=gross_bps,
            expected_success_cost_bps=success_cost_bps,
            net_expected_bps=expected_net_bps,
            assumed_abort_probability=probability,
            holding_period_hours=observation.holding_period_hours,
            decision_reason="target: abort-weighted expected net passes policy minimum",
            instrument_snapshot_id=observation.instrument_snapshot_id,
            cost_ledger_id=cost_ledger_id,
        )
    return _zero_target(
        observation,
        policy,
        gross_bps,
        success_cost_bps,
        expected_net_bps,
        reason,
        cost_ledger_id,
    )


def _zero_target(
    observation: CarryObservation,
    policy: Phase1Policy,
    gross_bps: Decimal,
    success_cost_bps: Decimal | None,
    expected_net_bps: Decimal | None,
    reason: str,
    cost_ledger_id: str,
) -> CarryTarget:
    return CarryTarget(
        venue=observation.venue,
        spot_instrument_id=observation.spot_instrument_id,
        perp_instrument_id=observation.perp_instrument_id,
        target_notional=Decimal("0"),
        funding_rate=observation.funding_rate,
        funding_interval_minutes=observation.funding_interval_minutes,
        expected_gross_bps=gross_bps,
        expected_success_cost_bps=success_cost_bps,
        net_expected_bps=expected_net_bps,
        assumed_abort_probability=policy.assumed_abort_probability,
        holding_period_hours=observation.holding_period_hours,
        decision_reason=reason,
        instrument_snapshot_id=observation.instrument_snapshot_id,
        cost_ledger_id=cost_ledger_id,
    )


def _cost_ledger_id(
    observation: CarryObservation,
    policy: Phase1Policy,
    schedule: FeeSchedule,
) -> str:
    payload = {
        "abort_probability": str(policy.assumed_abort_probability),
        "abort_loss_bps": str(policy.maximum_abort_cost_bps),
        "fee_source": schedule.source,
        "holding_period_hours": observation.holding_period_hours,
        "include_exit_cost": schedule.include_exit_cost,
        "instrument_snapshot_id": observation.instrument_snapshot_id,
        "other_success_cost_bps": str(observation.other_success_cost_bps),
        "perp_maker_bps": (
            str(schedule.perp_maker_bps) if schedule.perp_maker_bps is not None else None
        ),
        "spot_maker_bps": (
            str(schedule.spot_maker_bps) if schedule.spot_maker_bps is not None else None
        ),
        "perp_taker_bps": (
            str(schedule.perp_taker_bps) if schedule.perp_taker_bps is not None else None
        ),
        "spot_taker_bps": (
            str(schedule.spot_taker_bps) if schedule.spot_taker_bps is not None else None
        ),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()
