"""Fixed 1x ATR risk contract and position accounting helpers."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class RiskConfig:
    stop_atr: float = 2.0
    target_atr: float = 3.0
    max_holding_candles: int = 16
    round_trip_cost_bps: float = 10.0

    def __post_init__(self) -> None:
        if self.stop_atr <= 0 or self.target_atr <= 0:
            raise ValueError("ATR stop and target multipliers must be positive")
        if self.max_holding_candles <= 0:
            raise ValueError("max_holding_candles must be positive")
        if self.round_trip_cost_bps < 0:
            raise ValueError("round_trip_cost_bps must be non-negative")


@dataclass(frozen=True)
class RiskContract:
    side: str
    entry_price: float
    stop_price: float
    target_price: float
    max_holding_candles: int
    round_trip_cost_bps: float
    leverage: float = 1.0


def build_risk_contract(
    entry_price: float, atr_value: float, side: str, config: RiskConfig
) -> RiskContract:
    if side not in {"long", "short"}:
        raise ValueError("side must be 'long' or 'short'")
    if not np.isfinite(entry_price) or entry_price <= 0:
        raise ValueError("entry_price must be finite and positive")
    if not np.isfinite(atr_value) or atr_value <= 0:
        raise ValueError("atr_value must be finite and positive")

    direction = 1.0 if side == "long" else -1.0
    return RiskContract(
        side=side,
        entry_price=float(entry_price),
        stop_price=float(entry_price - direction * config.stop_atr * atr_value),
        target_price=float(entry_price + direction * config.target_atr * atr_value),
        max_holding_candles=config.max_holding_candles,
        round_trip_cost_bps=config.round_trip_cost_bps,
    )


def gross_return(side: str, entry_price: float, exit_price: float) -> float:
    if side == "long":
        return exit_price / entry_price - 1.0
    if side == "short":
        return (entry_price - exit_price) / entry_price
    raise ValueError("side must be 'long' or 'short'")


def net_return(gross: float, round_trip_cost_bps: float) -> float:
    return gross - round_trip_cost_bps / 10_000.0


def turnover(leverage: float = 1.0) -> float:
    return 2.0 * leverage
