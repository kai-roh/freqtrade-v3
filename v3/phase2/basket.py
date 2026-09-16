"""Dollar-neutral perp basket simulator for the pre-registered Phase 2 hypotheses.

Hourly loop over completed candles. Decisions use data at or before the decision
timestamp and execute at that hour's open; funding settles on positions held
into the settlement hour at the mark price of the previous candle close. Costs
apply to actual quantity changes. The daily stop, holding cap, hysteresis, and
the H1 spread filter follow docs/PHASE2_PREREGISTRATION.md.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from .data import Phase2Panel
from .signals import (
    Selection,
    daily_lookback_returns,
    funding_spread,
    select_legs,
    trailing_funding_mean,
)


@dataclass(frozen=True)
class CostModel:
    name: str
    fee_bps: float
    slippage_bps: float

    @property
    def one_way(self) -> float:
        return (self.fee_bps + self.slippage_bps) / 10_000.0


NORMAL_COST = CostModel("normal", 5.0, 2.0)
STRESS_COST = CostModel("stress", 5.0, 5.0)
STOP_SLIPPAGE_BPS = 5.0


@dataclass(frozen=True)
class BasketContract:
    sleeve_usdt: float = 200.0
    gross_target_usdt: float = 300.0
    daily_stop_fraction: float = 0.02
    rebalance_band: float = 0.25
    halt_hours: int = 24

    def leg_notional(self, k: int) -> float:
        return self.gross_target_usdt / 2.0 / k


@dataclass(frozen=True)
class Rule:
    """One pre-registered grid point."""

    hypothesis: str  # "H0", "H1", "H2"
    k: int = 2
    window_hours: int = 168  # H1
    spread_min: float = 0.0001  # H1, per settlement
    lookback_days: int = 5  # H2
    hold_days: int = 1  # H2 re-evaluation cadence
    max_hold_hours: int = 14 * 24

    def label(self) -> str:
        if self.hypothesis == "H0":
            return "H0"
        if self.hypothesis == "H1":
            return f"H1 W={self.window_hours}h k={self.k} s_min={self.spread_min * 10_000:.1f}bp"
        return f"H2 L={self.lookback_days}d k={self.k} H={self.hold_days}d"


DEFAULT_CONTRACT = BasketContract()


def h1_grid() -> tuple[Rule, ...]:
    return tuple(
        Rule("H1", k=k, window_hours=w, spread_min=s, max_hold_hours=14 * 24)
        for w in (48, 168, 336)
        for k in (2, 3)
        for s in (0.00005, 0.0001)
    )


def h2_grid() -> tuple[Rule, ...]:
    return tuple(
        Rule("H2", k=k, lookback_days=lb, hold_days=h, max_hold_hours=10 * 24)
        for lb in (3, 5, 10)
        for k in (2, 3)
        for h in (1, 3)
    )


@dataclass
class SimulationResult:
    rule: Rule
    cost: CostModel
    daily_returns: pd.Series
    equity: pd.Series
    decomposition: dict[str, float]
    per_symbol: dict[str, dict[str, float]]
    trades: int
    traded_notional: float
    episodes: list[dict[str, Any]]
    blocked_entries: int
    stop_events: int
    forced_exits: int
    decisions: int
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule": self.rule.label(),
            "cost": self.cost.name,
            "days": int(len(self.daily_returns)),
            "total_return": float(self.equity.iloc[-1] / self.equity.iloc[0] - 1)
            if len(self.equity)
            else 0.0,
            "decomposition": self.decomposition,
            "per_symbol": self.per_symbol,
            "trades": self.trades,
            "traded_notional": self.traded_notional,
            "episodes": len(self.episodes),
            "blocked_entries": self.blocked_entries,
            "stop_events": self.stop_events,
            "forced_exits": self.forced_exits,
            "decisions": self.decisions,
        }


def _scores_for(panel: Phase2Panel, rule: Rule) -> pd.DataFrame | None:
    if rule.hypothesis == "H1":
        return trailing_funding_mean(panel.funding, rule.window_hours)
    if rule.hypothesis == "H2":
        return daily_lookback_returns(panel.close, rule.lookback_days)
    return None


def _decision_times(panel: Phase2Panel, rule: Rule, scores: pd.DataFrame | None) -> set:
    if scores is None:
        return set()
    times = scores.dropna(how="all").index
    if rule.hypothesis == "H2" and rule.hold_days > 1:
        times = times[:: rule.hold_days]
    return set(times.intersection(panel.open.index))


def simulate_basket(
    panel: Phase2Panel,
    rule: Rule,
    *,
    cost: CostModel,
    start: pd.Timestamp,
    end: pd.Timestamp,
    entry_end: pd.Timestamp | None = None,
    contract: BasketContract | None = None,
) -> SimulationResult:
    """Run one rule over [start, end]; new entries stop after entry_end; flat at end."""
    contract = contract or DEFAULT_CONTRACT
    entry_end = entry_end or end
    hours = panel.open.index[(panel.open.index >= start) & (panel.open.index <= end)]
    if len(hours) < 2:
        raise ValueError("simulation window must contain at least two hourly candles")
    scores = _scores_for(panel, rule)
    decision_times = _decision_times(panel, rule, scores)
    symbols = list(panel.symbols)
    stop_cost = CostModel("stop", cost.fee_bps, STOP_SLIPPAGE_BPS)
    # Array views for the hot loop; pandas lookups per hour are too slow for the grid.
    open_rows = {t: panel.open.loc[t] for t in hours}
    mark_prev_frame = panel.mark.shift(1)
    settlement_rates = {
        t: (panel.funding.loc[t], mark_prev_frame.loc[t])
        for t in panel.settlement_index
        if t in open_rows
    }
    score_rows = (
        {t: scores.loc[t] for t in decision_times if t in open_rows} if scores is not None else {}
    )

    cash = contract.sleeve_usdt
    qty: dict[str, float] = dict.fromkeys(symbols, 0.0)
    entered_at: dict[str, pd.Timestamp] = {}
    sym_cash: dict[str, float] = dict.fromkeys(symbols, 0.0)
    sym_funding: dict[str, float] = dict.fromkeys(symbols, 0.0)
    fees = slippage = funding_total = traded_notional = 0.0
    trades = blocked = stops = forced = decisions = 0
    selection = Selection((), ())
    halted_until: pd.Timestamp | None = None
    day_start_equity: float | None = None
    daily_equity: dict[pd.Timestamp, float] = {}
    episodes: list[dict[str, Any]] = []
    episode_start: pd.Timestamp | None = None
    episode_start_equity = 0.0

    def held() -> list[str]:
        return [s for s in symbols if abs(qty[s]) > 0]

    def equity_at(prices: pd.Series) -> float:
        return cash + sum(qty[s] * float(prices[s]) for s in symbols if qty[s])

    def trade(symbol: str, target_qty: float, price: float, model: CostModel, when) -> None:
        nonlocal cash, fees, slippage, traded_notional, trades
        delta = target_qty - qty[symbol]
        if abs(delta) < 1e-12:
            return
        notional = abs(delta) * price
        cash -= delta * price
        sym_cash[symbol] -= delta * price
        fee = notional * model.fee_bps / 10_000.0
        slip = notional * model.slippage_bps / 10_000.0
        cash -= fee + slip
        fees += fee
        slippage += slip
        traded_notional += notional
        trades += 1
        qty[symbol] = target_qty if abs(target_qty) > 1e-12 else 0.0
        if qty[symbol] and symbol not in entered_at:
            entered_at[symbol] = when
        if not qty[symbol]:
            entered_at.pop(symbol, None)

    def close_all(price_row: pd.Series, model: CostModel, when) -> None:
        for symbol in held():
            trade(symbol, 0.0, float(price_row[symbol]), model, when)

    for t in hours:
        opens = open_rows[t]
        # 1. Funding on positions held into this settlement.
        if t in settlement_rates:
            rates, marks = settlement_rates[t]
            for symbol in held():
                mark = float(marks[symbol])
                if pd.isna(mark):
                    mark = float(opens[symbol])
                paid = -qty[symbol] * mark * float(rates[symbol])
                cash += paid
                funding_total += paid
                sym_funding[symbol] += paid
        # 2. Mark-to-market, day boundary, daily stop.
        equity = equity_at(opens)
        if t.hour == 0 or day_start_equity is None:
            day_start_equity = equity
            daily_equity[t.normalize()] = equity
        if held() and equity <= day_start_equity * (1 - contract.daily_stop_fraction):
            close_all(opens, stop_cost, t)
            stops += 1
            halted_until = t + pd.Timedelta(hours=contract.halt_hours)
            selection = Selection((), ())
        # 3. Holding cap and end-of-window flattening.
        if t == hours[-1]:
            close_all(opens, cost, t)
        else:
            for symbol in held():
                if t - entered_at[symbol] >= pd.Timedelta(hours=rule.max_hold_hours):
                    trade(symbol, 0.0, float(opens[symbol]), cost, t)
                    forced += 1
                    selection = Selection(
                        tuple(s for s in selection.shorts if s != symbol),
                        tuple(s for s in selection.longs if s != symbol),
                    )
        # 4. Scheduled decision.
        if t in score_rows and t != hours[-1] and (halted_until is None or t >= halted_until):
            decisions += 1
            row = score_rows[t]
            candidate = select_legs(row, k=rule.k, previous=selection)
            allow_entries = t <= entry_end
            if rule.hypothesis == "H1" and allow_entries:
                spread = funding_spread(row, candidate)
                if spread is None or spread < rule.spread_min:
                    allow_entries = False
                    blocked += 1
            if not allow_entries:
                candidate = Selection(
                    tuple(s for s in candidate.shorts if qty[s] < 0),
                    tuple(s for s in candidate.longs if qty[s] > 0),
                )
            leg = contract.leg_notional(rule.k)
            targets: dict[str, float] = {}
            for symbol in candidate.shorts:
                targets[symbol] = -leg
            for symbol in candidate.longs:
                targets[symbol] = leg
            for symbol in held():
                if symbol not in targets:
                    trade(symbol, 0.0, float(opens[symbol]), cost, t)
            for symbol, target_notional in targets.items():
                price = float(opens[symbol])
                current = qty[symbol] * price
                if (
                    qty[symbol] == 0.0
                    or (current > 0) != (target_notional > 0)
                    or abs(current / target_notional - 1) > contract.rebalance_band
                ):
                    trade(symbol, target_notional / price, price, cost, t)
            selection = candidate
        # 5. Episode bookkeeping.
        if held() and episode_start is None:
            episode_start = t
            episode_start_equity = equity_at(opens)
        elif not held() and episode_start is not None:
            episodes.append(
                {
                    "start": episode_start.isoformat(),
                    "end": t.isoformat(),
                    "hours": int((t - episode_start).total_seconds() // 3600),
                    "pnl_usdt": equity_at(opens) - episode_start_equity,
                }
            )
            episode_start = None

    final_prices = panel.open.loc[hours[-1]]
    equity_series = pd.Series(daily_equity).sort_index()
    end_equity = equity_at(final_prices)
    equity_series.loc[hours[-1].normalize() + pd.Timedelta(days=1)] = end_equity
    equity_series = equity_series[~equity_series.index.duplicated(keep="last")].sort_index()
    daily_returns = equity_series.pct_change().dropna()
    total = end_equity - contract.sleeve_usdt
    per_symbol = {
        s: {
            "price_pnl": sym_cash[s] + qty[s] * float(final_prices[s]),
            "funding_pnl": sym_funding[s],
        }
        for s in symbols
    }
    return SimulationResult(
        rule=rule,
        cost=cost,
        daily_returns=daily_returns,
        equity=equity_series,
        decomposition={
            "total_pnl": total,
            "price_pnl": total - funding_total + fees + slippage,
            "funding_pnl": funding_total,
            "fees": fees,
            "slippage": slippage,
        },
        per_symbol=per_symbol,
        trades=trades,
        traded_notional=traded_notional,
        episodes=episodes,
        blocked_entries=blocked,
        stop_events=stops,
        forced_exits=forced,
        decisions=decisions,
    )
