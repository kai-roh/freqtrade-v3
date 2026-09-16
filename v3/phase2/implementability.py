"""Per-symbol implementability gate for the Phase 2 basket (pre-registration section 7).

Pure functions over venue filters. No network, no orders. A symbol is admissible
for a given legs-per-side k when the equal-weight leg notional, floored to the
symbol's quantity step at the reference price, still covers three times the
venue minimum notional and the isolated 2x liquidation distance exceeds 20%.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_FLOOR, Decimal
from typing import Any

from v3.costs import DecimalInput, as_decimal

UNIVERSE = ("BTC", "ETH", "SOL", "BNB", "XRP", "DOGE", "ADA", "LINK")
SLEEVE_USDT = Decimal("200")
GROSS_NOTIONAL_CAP_USDT = Decimal("400")
GROSS_NOTIONAL_TARGET_USDT = Decimal("300")
MARGIN_PER_SIDE_USDT = Decimal("150")  # target notional at 2x isolated
BUFFER_USDT = Decimal("50")
HEADROOM = Decimal("3")
ISOLATED_LEVERAGE = Decimal("2")
MINIMUM_LIQUIDATION_DISTANCE = Decimal("0.20")
LEGS_PER_SIDE = (2, 3)


@dataclass(frozen=True)
class SymbolFilters:
    symbol: str
    min_notional: DecimalInput
    step_size: DecimalInput
    tick_size: DecimalInput
    reference_price: DecimalInput
    maintenance_margin_rate: DecimalInput = "0.01"
    status: str = "TRADING"

    def __post_init__(self) -> None:
        for name in (
            "min_notional",
            "step_size",
            "tick_size",
            "reference_price",
            "maintenance_margin_rate",
        ):
            object.__setattr__(self, name, as_decimal(getattr(self, name), field_name=name))
        if min(self.min_notional, self.step_size, self.tick_size, self.reference_price) <= 0:
            raise ValueError("symbol filters must be positive")


def leg_notional_target(k: int) -> Decimal:
    if k not in LEGS_PER_SIDE:
        raise ValueError("legs per side must be 2 or 3")
    return GROSS_NOTIONAL_TARGET_USDT / 2 / k


def floored_leg_notional(filters: SymbolFilters, k: int) -> Decimal:
    target = leg_notional_target(k)
    quantity = (target / filters.reference_price / filters.step_size).to_integral_value(
        rounding=ROUND_FLOOR
    ) * filters.step_size
    return quantity * filters.reference_price


def liquidation_distance(filters: SymbolFilters) -> Decimal:
    """Approximate isolated liquidation distance as a fraction of entry price.

    With initial margin 1/leverage and maintenance rate m, liquidation is roughly
    at 1/leverage - m away from entry for either side (fees ignored, conservative).
    """
    return Decimal(1) / ISOLATED_LEVERAGE - filters.maintenance_margin_rate


def evaluate_symbol(filters: SymbolFilters, k: int) -> dict[str, Any]:
    notional = floored_leg_notional(filters, k)
    required = filters.min_notional * HEADROOM
    distance = liquidation_distance(filters)
    reasons = []
    if filters.status != "TRADING":
        reasons.append("symbol is not trading")
    if notional < required:
        reasons.append("leg notional below 3x minimum notional")
    if distance < MINIMUM_LIQUIDATION_DISTANCE:
        reasons.append("liquidation distance below 20%")
    return {
        "symbol": filters.symbol,
        "legs_per_side": k,
        "target_leg_notional_usdt": str(leg_notional_target(k)),
        "floored_leg_notional_usdt": str(notional),
        "required_minimum_usdt": str(required),
        "liquidation_distance": str(distance),
        "admissible": not reasons,
        "reasons": reasons,
    }


def evaluate_universe(filters: list[SymbolFilters]) -> dict[str, Any]:
    if MARGIN_PER_SIDE_USDT + BUFFER_USDT > SLEEVE_USDT:
        raise ValueError("margin plus buffer exceeds the basket sleeve")
    if GROSS_NOTIONAL_TARGET_USDT > GROSS_NOTIONAL_CAP_USDT:
        raise ValueError("gross target exceeds the gross cap")
    by_k: dict[str, Any] = {}
    for k in LEGS_PER_SIDE:
        rows = [evaluate_symbol(f, k) for f in filters]
        admissible = [r["symbol"] for r in rows if r["admissible"]]
        by_k[str(k)] = {
            "symbols": rows,
            "admissible_symbols": admissible,
            "admissible_count": len(admissible),
            # A basket needs k longs and k shorts drawn from distinct symbols.
            "basket_feasible": len(admissible) >= 2 * k,
        }
    return {
        "schema_version": 1,
        "contract": {
            "sleeve_usdt": str(SLEEVE_USDT),
            "gross_notional_cap_usdt": str(GROSS_NOTIONAL_CAP_USDT),
            "gross_notional_target_usdt": str(GROSS_NOTIONAL_TARGET_USDT),
            "margin_per_side_usdt": str(MARGIN_PER_SIDE_USDT),
            "buffer_usdt": str(BUFFER_USDT),
            "headroom": str(HEADROOM),
            "isolated_leverage": str(ISOLATED_LEVERAGE),
            "minimum_liquidation_distance": str(MINIMUM_LIQUIDATION_DISTANCE),
        },
        "by_legs_per_side": by_k,
        "interpretation": (
            "Research proceeds regardless; an infeasible k is reported as 'not implementable "
            "at this capital size' and never changes the registered hypotheses"
        ),
    }
