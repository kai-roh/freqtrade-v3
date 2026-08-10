"""Deterministic trade metric calculations."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from math import inf

import numpy as np
import pandas as pd

REQUIRED_TRADE_COLUMNS = frozenset({"pnl", "pair", "side", "notional"})


@dataclass(frozen=True)
class TradeMetrics:
    """Closed-trade performance summary."""

    trade_count: int
    net_pnl: float
    gross_profit: float
    gross_loss: float
    profit_factor: float
    expectancy: float
    win_rate: float
    max_closed_equity_drawdown: float
    turnover: float
    side_contributions: Mapping[str, float]
    pair_contributions: Mapping[str, float]
    total_cost: float


def _require_columns(trades: pd.DataFrame, required: frozenset[str]) -> None:
    missing = sorted(required.difference(trades.columns))
    if missing:
        raise ValueError(f"trades missing required columns: {', '.join(missing)}")


def _clean_numeric(series: pd.Series, name: str) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    if values.isna().any() or np.isinf(values.to_numpy(dtype=float)).any():
        raise ValueError(f"{name} must contain only finite numeric values")
    return values.astype(float)


def _group_contributions(labels: pd.Series, pnl: pd.Series) -> dict[str, float]:
    if pnl.empty:
        return {}
    grouped = pnl.groupby(labels.astype(str), sort=True).sum()
    return {str(key): round(float(value), 12) for key, value in grouped.items()}


def _closed_equity_drawdown(pnl: pd.Series, initial_capital: float) -> float:
    if pnl.empty:
        return 0.0

    equity = initial_capital + pnl.cumsum().to_numpy()
    high_water = np.maximum.accumulate(np.concatenate(([initial_capital], equity)))[1:]
    drawdown = high_water - equity
    if len(drawdown) == 0:
        return 0.0

    max_drawdown = float(drawdown.max())
    if max_drawdown <= 0.0:
        return 0.0

    return max_drawdown / initial_capital


def compute_trade_metrics(
    trades: pd.DataFrame,
    *,
    cost_stress: float = 0.0,
    initial_capital: float = 1.0,
) -> TradeMetrics:
    """Compute deterministic closed-trade metrics.

    Input ``pnl`` is treated as gross PnL. Optional ``cost`` plus
    ``cost_stress * abs(notional)`` are subtracted to produce net PnL.
    """

    if not isinstance(trades, pd.DataFrame):
        raise TypeError("trades must be a pandas DataFrame")
    if cost_stress < 0:
        raise ValueError("cost_stress must be non-negative")
    if initial_capital <= 0:
        raise ValueError("initial_capital must be positive")
    _require_columns(trades, REQUIRED_TRADE_COLUMNS)

    if trades.empty:
        return TradeMetrics(
            trade_count=0,
            net_pnl=0.0,
            gross_profit=0.0,
            gross_loss=0.0,
            profit_factor=0.0,
            expectancy=0.0,
            win_rate=0.0,
            max_closed_equity_drawdown=0.0,
            turnover=0.0,
            side_contributions={},
            pair_contributions={},
            total_cost=0.0,
        )

    pnl = _clean_numeric(trades["pnl"], "pnl")
    notional = _clean_numeric(trades["notional"], "notional").abs()
    cost = (
        _clean_numeric(trades["cost"], "cost")
        if "cost" in trades.columns
        else pd.Series(0.0, index=trades.index)
    )

    total_cost_series = cost + (notional * float(cost_stress))
    net = pnl - total_cost_series
    wins = net[net > 0]
    losses = net[net < 0]

    gross_profit = float(wins.sum())
    gross_loss = float(-losses.sum())
    if gross_profit == 0.0 and gross_loss == 0.0:
        profit_factor = 0.0
    elif gross_loss == 0.0:
        profit_factor = inf
    else:
        profit_factor = gross_profit / gross_loss

    return TradeMetrics(
        trade_count=int(len(trades)),
        net_pnl=float(net.sum()),
        gross_profit=gross_profit,
        gross_loss=gross_loss,
        profit_factor=float(profit_factor),
        expectancy=float(net.mean()),
        win_rate=float((net > 0).mean()),
        max_closed_equity_drawdown=float(_closed_equity_drawdown(net, float(initial_capital))),
        turnover=float(notional.sum()),
        side_contributions=_group_contributions(trades["side"], net),
        pair_contributions=_group_contributions(trades["pair"], net),
        total_cost=float(total_cost_series.sum()),
    )
