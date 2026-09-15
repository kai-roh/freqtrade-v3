"""Order-free funding carry scanner with abort-weighted economics."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
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
    observed_at: datetime
    other_success_cost_bps: DecimalInput = Decimal("0")
    trailing_funding_rates: tuple[DecimalInput, ...] = ()

    def __post_init__(self) -> None:
        for name in ("requested_notional", "funding_rate", "other_success_cost_bps"):
            object.__setattr__(self, name, as_decimal(getattr(self, name), field_name=name))
        object.__setattr__(
            self,
            "trailing_funding_rates",
            tuple(
                as_decimal(rate, field_name="trailing_funding_rates")
                for rate in self.trailing_funding_rates
            ),
        )
        if self.venue != "binance":
            raise ValueError("Phase 1 carry venue must be binance")
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("observed_at must include a timezone")
        object.__setattr__(self, "observed_at", self.observed_at.astimezone(UTC))
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
    projected_funding_rate: Decimal | None
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
            "projected_funding_rate": (
                str(self.projected_funding_rate)
                if self.projected_funding_rate is not None
                else None
            ),
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
    schedule = fee_schedule or policy.fee_schedule
    round_trip_bps = schedule.maker_round_trip_bps
    cost_ledger_id = _cost_ledger_id(observation, policy, schedule)

    projected = project_funding_rate(observation, policy)
    if projected is None:
        # The current settlement alone is a scenario, never a holding-period forecast.
        return _zero_target(
            observation,
            policy,
            observation.funding_rate * intervals * Decimal("10000"),
            None,
            None,
            "observe_only: trailing funding history is shorter than the projection window",
            cost_ledger_id,
            projected=None,
        )
    gross_bps = projected * intervals * Decimal("10000")

    if round_trip_bps is None:
        return _zero_target(
            observation,
            policy,
            gross_bps,
            None,
            None,
            "observe_only: credentialed mainnet fee schedule is incomplete",
            cost_ledger_id,
            projected=projected,
        )
    if not schedule.is_fresh(observation.observed_at):
        return _zero_target(
            observation,
            policy,
            gross_bps,
            round_trip_bps,
            None,
            "observe_only: credentialed mainnet fee schedule is stale or undated",
            cost_ledger_id,
            projected=projected,
        )

    success_cost_bps = round_trip_bps + observation.other_success_cost_bps
    probability = policy.assumed_abort_probability
    expected_net_bps = (Decimal("1") - probability) * (
        gross_bps - success_cost_bps
    ) - probability * policy.maximum_abort_cost_bps

    if observation.funding_rate <= 0 or projected <= 0:
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
            projected_funding_rate=projected,
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
        projected=projected,
    )


def project_funding_rate(observation: CarryObservation, policy: Phase1Policy) -> Decimal | None:
    """Conservative per-interval funding used for the holding-period projection.

    Returns None when the trailing history is shorter than the policy window.
    Otherwise the smaller of the current settlement and the trailing mean, so a
    one-off spike cannot pass the gate and a decaying regime is not overstated.
    """
    window = policy.funding_projection_intervals
    history = observation.trailing_funding_rates[-window:]
    if len(history) < window:
        return None
    trailing_mean = sum(history, Decimal(0)) / Decimal(len(history))
    return min(observation.funding_rate, trailing_mean)


def funding_reversal_exit(
    recent_funding_rates: tuple[DecimalInput, ...] | list[DecimalInput],
    policy: Phase1Policy,
) -> tuple[bool, str]:
    """Deterministic exit rule for an open carry: stop holding when funding stops paying.

    The rates must be chronological with the latest settlement last. Exit when the
    last N settlements are all non-positive, or when the trailing-window mean is
    non-positive. Insufficient history is itself an exit reason: an open position
    must not keep holding on unmeasured funding.
    """
    rates = [as_decimal(rate, field_name="recent_funding_rates") for rate in recent_funding_rates]
    consecutive = policy.funding_reversal_consecutive_intervals
    window = policy.funding_reversal_trailing_intervals
    if len(rates) < window:
        return True, "exit: trailing funding history is shorter than the reversal window"
    recent = rates[-window:]
    if all(rate <= 0 for rate in recent[-consecutive:]):
        return True, f"exit: last {consecutive} funding settlements were non-positive"
    if sum(recent, Decimal(0)) <= 0:
        return True, f"exit: trailing {window}-settlement funding mean is non-positive"
    return False, "hold: funding continues to pay the short perp leg"


def _zero_target(
    observation: CarryObservation,
    policy: Phase1Policy,
    gross_bps: Decimal,
    success_cost_bps: Decimal | None,
    expected_net_bps: Decimal | None,
    reason: str,
    cost_ledger_id: str,
    *,
    projected: Decimal | None,
) -> CarryTarget:
    return CarryTarget(
        venue=observation.venue,
        spot_instrument_id=observation.spot_instrument_id,
        perp_instrument_id=observation.perp_instrument_id,
        target_notional=Decimal("0"),
        funding_rate=observation.funding_rate,
        projected_funding_rate=projected,
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
        "fee_snapshot_captured_at": (
            schedule.captured_at.isoformat() if schedule.captured_at is not None else None
        ),
        "fee_snapshot_maximum_age_hours": schedule.maximum_age_hours,
        "funding_projection_intervals": policy.funding_projection_intervals,
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
