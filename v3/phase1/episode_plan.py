"""Pure Phase 1 two-leg episode planner.

The planner converts durable, already-confirmed position evidence into the next
allowed Demo action. It never submits an order and never treats dust as flat.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_FLOOR, Decimal
from enum import StrEnum

from v3.costs import DecimalInput, as_decimal


class EpisodePhase(StrEnum):
    ENTRY = "entry"
    HOLDING = "holding"
    CLOSING = "closing"


class EpisodeActionType(StrEnum):
    SUBMIT_ENTRY_PAIR = "submit_entry_pair"
    HEDGE_PERP_SELL = "hedge_perp_sell"
    CLOSE_PERP_BUY = "close_perp_buy"
    CLOSE_SPOT_SELL = "close_spot_sell"
    DUST_REMAINS = "dust_remains"
    WAIT = "wait"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class EpisodeLimits:
    spot_lot_size: DecimalInput
    perp_lot_size: DecimalInput
    spot_min_notional: DecimalInput
    perp_min_notional: DecimalInput
    spot_bid: DecimalInput
    spot_ask: DecimalInput
    perp_bid: DecimalInput
    perp_ask: DecimalInput

    def __post_init__(self) -> None:
        for name in (
            "spot_lot_size",
            "perp_lot_size",
            "spot_min_notional",
            "perp_min_notional",
            "spot_bid",
            "spot_ask",
            "perp_bid",
            "perp_ask",
        ):
            object.__setattr__(self, name, as_decimal(getattr(self, name), field_name=name))
        if (
            self.spot_lot_size <= 0
            or self.perp_lot_size <= 0
            or self.spot_min_notional <= 0
            or self.perp_min_notional <= 0
            or self.spot_bid <= 0
            or self.spot_ask < self.spot_bid
            or self.perp_bid <= 0
            or self.perp_ask < self.perp_bid
        ):
            raise ValueError("invalid episode instrument or quote limits")


@dataclass(frozen=True)
class EpisodeSnapshot:
    phase: EpisodePhase
    spot_filled_base: DecimalInput
    perp_filled_base: DecimalInput
    spot_base_fee: DecimalInput = "0"
    venue_spot_base: DecimalInput | None = None
    venue_perp_base: DecimalInput | None = None
    pending_command_count: int = 0
    unknown_dispatch_count: int = 0
    open_order_count: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(self, "phase", EpisodePhase(self.phase))
        object.__setattr__(
            self, "spot_filled_base", _decimal("spot_filled_base", self.spot_filled_base)
        )
        object.__setattr__(
            self, "perp_filled_base", _decimal("perp_filled_base", self.perp_filled_base)
        )
        object.__setattr__(self, "spot_base_fee", _decimal("spot_base_fee", self.spot_base_fee))
        if self.venue_spot_base is not None:
            object.__setattr__(
                self, "venue_spot_base", _decimal("venue_spot_base", self.venue_spot_base)
            )
        if self.venue_perp_base is not None:
            object.__setattr__(
                self, "venue_perp_base", _decimal("venue_perp_base", self.venue_perp_base)
            )
        if any(
            type(count) is not int or count < 0
            for count in (
                self.pending_command_count,
                self.unknown_dispatch_count,
                self.open_order_count,
            )
        ):
            raise ValueError("episode counts must be non-negative")
        if self.spot_base_fee < 0:
            raise ValueError("spot_base_fee cannot be negative")

    @property
    def net_spot_base(self) -> Decimal:
        return self.spot_filled_base - self.spot_base_fee


@dataclass(frozen=True)
class EpisodeAction:
    action: EpisodeActionType
    reason: str
    quantity: Decimal | None = None
    reduce_only: bool = False
    dust_base: Decimal = Decimal("0")

    @property
    def blocks_new_entry(self) -> bool:
        return self.action in {EpisodeActionType.BLOCKED, EpisodeActionType.DUST_REMAINS}


def plan_episode_action(snapshot: EpisodeSnapshot, limits: EpisodeLimits) -> EpisodeAction:
    """Choose the next bounded action from confirmed two-leg evidence only."""

    problems = _snapshot_violations(snapshot, limits)
    if problems:
        return EpisodeAction(EpisodeActionType.BLOCKED, "; ".join(problems))
    if (
        snapshot.pending_command_count
        or snapshot.unknown_dispatch_count
        or snapshot.open_order_count
    ):
        return EpisodeAction(
            EpisodeActionType.WAIT,
            "pending, unknown, or open venue evidence blocks new actions",
        )

    spot = snapshot.net_spot_base
    perp = snapshot.perp_filled_base
    if spot < 0:
        return EpisodeAction(EpisodeActionType.BLOCKED, "net Spot inventory cannot be negative")
    if perp > 0:
        return EpisodeAction(EpisodeActionType.BLOCKED, "unexpected long perp position")

    if snapshot.phase == EpisodePhase.CLOSING:
        return _closing_action(spot, perp, limits)

    if spot == 0 and perp == 0:
        if snapshot.phase == EpisodePhase.ENTRY:
            return EpisodeAction(
                EpisodeActionType.SUBMIT_ENTRY_PAIR, "no exposure; entry pair allowed"
            )
        return EpisodeAction(EpisodeActionType.WAIT, "no exposure remains")

    if perp < -spot:
        return EpisodeAction(EpisodeActionType.BLOCKED, "perp short exceeds confirmed owned Spot")

    unhedged_spot = spot + perp
    hedge_qty = _floor_to_lot(unhedged_spot, limits.perp_lot_size)
    if hedge_qty > 0 and hedge_qty * limits.perp_bid >= limits.perp_min_notional:
        return EpisodeAction(
            EpisodeActionType.HEDGE_PERP_SELL,
            "confirmed net Spot inventory exceeds short perp hedge",
            hedge_qty,
        )
    if unhedged_spot > 0:
        return EpisodeAction(
            EpisodeActionType.DUST_REMAINS,
            "unhedged Spot remainder is below hedge lot or notional minimum",
            dust_base=unhedged_spot,
        )
    return EpisodeAction(EpisodeActionType.WAIT, "two legs are matched")


def _closing_action(spot: Decimal, perp: Decimal, limits: EpisodeLimits) -> EpisodeAction:
    if perp < 0:
        qty = _floor_to_lot(abs(perp), limits.perp_lot_size)
        if qty > 0 and qty * limits.perp_ask >= limits.perp_min_notional:
            return EpisodeAction(
                EpisodeActionType.CLOSE_PERP_BUY,
                "close short perp before selling owned Spot",
                qty,
                reduce_only=True,
            )
        return EpisodeAction(
            EpisodeActionType.DUST_REMAINS,
            "short perp dust remains below closing lot or notional minimum",
            dust_base=abs(perp),
        )
    if spot > 0:
        qty = _floor_to_lot(spot, limits.spot_lot_size)
        if qty > 0 and qty * limits.spot_bid >= limits.spot_min_notional:
            return EpisodeAction(
                EpisodeActionType.CLOSE_SPOT_SELL,
                "sell only owned net Spot inventory after perp is flat",
                qty,
            )
        return EpisodeAction(
            EpisodeActionType.DUST_REMAINS,
            "Spot dust remains below sell lot or notional minimum",
            dust_base=spot,
        )
    return EpisodeAction(EpisodeActionType.WAIT, "episode is flat")


def _snapshot_violations(snapshot: EpisodeSnapshot, limits: EpisodeLimits) -> list[str]:
    violations: list[str] = []
    expected_spot = snapshot.net_spot_base
    if snapshot.venue_spot_base is None or snapshot.venue_perp_base is None:
        violations.append("both venue position snapshots are required")
    if snapshot.venue_spot_base is not None and snapshot.venue_spot_base != expected_spot:
        violations.append("venue Spot inventory is inconsistent with durable fills")
    if (
        snapshot.venue_perp_base is not None
        and snapshot.venue_perp_base != snapshot.perp_filled_base
    ):
        violations.append("venue perp position is inconsistent with durable fills")
    if snapshot.spot_filled_base < 0:
        violations.append("Spot filled quantity cannot be negative")
    if snapshot.spot_base_fee > snapshot.spot_filled_base:
        violations.append("Spot base fee exceeds filled inventory")
    return violations


def _floor_to_lot(quantity: Decimal, lot: Decimal) -> Decimal:
    if quantity <= 0:
        return Decimal("0")
    return (quantity / lot).to_integral_value(rounding=ROUND_FLOOR) * lot


def _decimal(field_name: str, value: DecimalInput) -> Decimal:
    resolved = as_decimal(value, field_name=field_name)
    if not resolved.is_finite():
        raise ValueError(f"{field_name} must be finite")
    return resolved
