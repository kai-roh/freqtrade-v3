"""Phase 2b low-turnover maker funding carry simulator (docs/PHASE2B_PREREGISTRATION.md).

Reuses the Phase 2 signal, selection, sleeve, daily stop, and funding accounting
and changes only what the registration changes: one decision per day at 00:00
UTC, a minimum and maximum leg holding period, a wider rebalance band, and
execution. Planned trades post at the 01:00 open; a maker fill needs the 01:00
candle to trade through the limit by the trade-through margin, and unfilled legs
are completed by taker at the 02:00 open. Risk-reducing exits are taker with the
stop slippage. The Phase 2 simulator in ``basket.py`` is not modified.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from .basket import STOP_SLIPPAGE_BPS, BasketContract, SimulationResult
from .data import Phase2Panel, load_phase2_panel
from .implementability import UNIVERSE
from .signals import Selection, funding_spread, select_legs, trailing_funding_mean

MAKER_FEE_BPS = 2.0
TAKER_FEE_BPS = 5.0
EPSILON = 1e-12


@dataclass(frozen=True)
class ExecutionModel:
    """Cost regime plus execution style. ``maker=False`` is the taker diagnostic H3T."""

    name: str
    maker: bool
    taker_slippage_bps: float
    trade_through_bps: float
    maker_fee_bps: float = MAKER_FEE_BPS
    taker_fee_bps: float = TAKER_FEE_BPS


H3_NORMAL = ExecutionModel("normal", True, taker_slippage_bps=2.0, trade_through_bps=2.0)
H3_STRESS = ExecutionModel("stress", True, taker_slippage_bps=5.0, trade_through_bps=5.0)
H3T_NORMAL = ExecutionModel("normal", False, taker_slippage_bps=2.0, trade_through_bps=2.0)
H3T_STRESS = ExecutionModel("stress", False, taker_slippage_bps=5.0, trade_through_bps=5.0)

# Phase 2b contract: the Phase 2 sleeve with the 50% rebalance band.
PHASE2B_CONTRACT = BasketContract(rebalance_band=0.50)


@dataclass(frozen=True)
class DailyRule:
    """One registered H3/H3T grid point."""

    hypothesis: str  # "H3" (maker) or "H3T" (taker diagnostic)
    k: int
    window_hours: int
    spread_min: float = 0.0001  # 1.0 bp per settlement, fixed
    min_hold_days: int = 5
    max_hold_days: int = 14
    decision_hour: int = 0

    def label(self) -> str:
        return f"{self.hypothesis} W={self.window_hours}h k={self.k}"


def h3_grid(hypothesis: str = "H3") -> tuple[DailyRule, ...]:
    if hypothesis not in {"H3", "H3T"}:
        raise ValueError("hypothesis must be H3 or H3T")
    return tuple(DailyRule(hypothesis, k=k, window_hours=w) for w in (168, 336) for k in (2, 3))


@dataclass(frozen=True)
class MakerPanel:
    base: Phase2Panel
    high: pd.DataFrame
    low: pd.DataFrame

    def __post_init__(self) -> None:
        for name in ("high", "low"):
            frame = getattr(self, name)
            if not frame.index.equals(self.base.open.index):
                raise ValueError(f"{name} must share the hourly index")
            if tuple(frame.columns) != self.base.symbols:
                raise ValueError(f"{name} columns must equal the panel symbols")


def load_maker_panel(
    data_dir: Path, *, manifest_path: Path | None = None, symbols: tuple[str, ...] = UNIVERSE
) -> MakerPanel:
    base = load_phase2_panel(data_dir, manifest_path=manifest_path, symbols=symbols)
    highs, lows = {}, {}
    for symbol in symbols:
        frame = pd.read_feather(data_dir / f"{symbol}_USDT_USDT-1h-futures.feather")
        index = pd.to_datetime(frame["date"], utc=True)
        highs[symbol] = pd.Series(frame["high"].astype(float).to_numpy(), index=index)
        lows[symbol] = pd.Series(frame["low"].astype(float).to_numpy(), index=index)
    high = pd.DataFrame(highs).loc[base.open.index, list(symbols)]
    low = pd.DataFrame(lows).loc[base.open.index, list(symbols)]
    return MakerPanel(base, high, low)


def simulate_maker_basket(
    panel: MakerPanel,
    rule: DailyRule,
    *,
    execution: ExecutionModel,
    start: pd.Timestamp,
    end: pd.Timestamp,
    entry_end: pd.Timestamp | None = None,
    final_slippage_bps: float | None = None,
    contract: BasketContract = PHASE2B_CONTRACT,
) -> SimulationResult:
    """Run one rule over [start, end]; decisions stop after entry_end; flat at end.

    ``final_slippage_bps`` sets the taker slippage of the end-of-window close
    (Stage B uses the stress value); by default the regime's taker slippage.
    """
    base = panel.base
    entry_end = entry_end or end
    hours = base.open.index[(base.open.index >= start) & (base.open.index <= end)]
    if len(hours) < 2:
        raise ValueError("simulation window must contain at least two hourly candles")
    symbols = list(base.symbols)
    scores = trailing_funding_mean(base.funding, rule.window_hours)
    hour_set = set(hours)
    open_rows = {t: base.open.loc[t] for t in hours}
    high_rows = {t: panel.high.loc[t] for t in hours}
    low_rows = {t: panel.low.loc[t] for t in hours}
    mark_prev = base.mark.shift(1)
    settlements = {
        t: (base.funding.loc[t], mark_prev.loc[t]) for t in base.settlement_index if t in hour_set
    }
    decision_rows = {
        t: scores.loc[t]
        for t in scores.dropna(how="all").index
        if t in hour_set and t.hour == rule.decision_hour
    }
    final_slip = execution.taker_slippage_bps if final_slippage_bps is None else final_slippage_bps
    one_hour, two_hours = pd.Timedelta(hours=1), pd.Timedelta(hours=2)
    min_hold = pd.Timedelta(days=rule.min_hold_days)
    max_hold = pd.Timedelta(days=rule.max_hold_days)

    cash = contract.sleeve_usdt
    qty = dict.fromkeys(symbols, 0.0)
    entered_at: dict[str, pd.Timestamp] = {}
    sym_cash = dict.fromkeys(symbols, 0.0)
    sym_funding = dict.fromkeys(symbols, 0.0)
    fees = slippage = funding_total = traded_notional = 0.0
    trades = blocked = stops = forced = decisions = 0
    fills = {
        "maker_orders": 0,
        "maker_filled": 0,
        "taker_fallback": 0,
        "taker_planned": 0,
        "taker_risk": 0,
        "maker_notional": 0.0,
        "taker_notional": 0.0,
    }
    selection = Selection((), ())
    halted_until: pd.Timestamp | None = None
    day_start_equity: float | None = None
    daily_equity: dict[pd.Timestamp, float] = {}
    episodes: list[dict[str, Any]] = []
    episode_start: pd.Timestamp | None = None
    episode_start_equity = 0.0
    # Orders created at a decision: (symbol, target_notional, decision_time).
    maker_queue: list[tuple[str, float, pd.Timestamp]] = []
    maker_due: pd.Timestamp | None = None
    fallback_queue: list[tuple[str, float, pd.Timestamp]] = []
    fallback_due: pd.Timestamp | None = None

    def held() -> list[str]:
        return [s for s in symbols if abs(qty[s]) > 0]

    def equity_at(prices: pd.Series) -> float:
        return cash + sum(qty[s] * float(prices[s]) for s in symbols if qty[s])

    def trade(symbol, target_qty, price, fee_bps, slip_bps, opened_at, kind) -> None:
        nonlocal cash, fees, slippage, traded_notional, trades
        delta = target_qty - qty[symbol]
        if abs(delta) < EPSILON:
            return
        notional = abs(delta) * price
        cash -= delta * price
        sym_cash[symbol] -= delta * price
        fee = notional * fee_bps / 10_000.0
        slip = notional * slip_bps / 10_000.0
        cash -= fee + slip
        fees += fee
        slippage += slip
        traded_notional += notional
        trades += 1
        fills["maker_notional" if kind == "maker" else "taker_notional"] += notional
        previous = qty[symbol]
        qty[symbol] = target_qty if abs(target_qty) > EPSILON else 0.0
        if not qty[symbol]:
            entered_at.pop(symbol, None)
        elif previous == 0.0 or (previous > 0) != (qty[symbol] > 0):
            entered_at[symbol] = opened_at

    def taker(symbol, target_notional, prices, when, slip_bps, kind) -> None:
        price = float(prices[symbol])
        trade(
            symbol,
            target_notional / price,
            price,
            execution.taker_fee_bps,
            slip_bps,
            when,
            "taker",
        )
        fills[kind] += 1

    def close_all(prices, slip_bps, when) -> None:
        for symbol in held():
            taker(symbol, 0.0, prices, when, slip_bps, "taker_risk")

    for t in hours:
        opens = open_rows[t]
        # 1. Funding on positions held into this settlement (Phase 2 accounting).
        if t in settlements:
            rates, marks = settlements[t]
            for symbol in held():
                mark = float(marks[symbol])
                if pd.isna(mark):
                    mark = float(opens[symbol])
                paid = -qty[symbol] * mark * float(rates[symbol])
                cash += paid
                funding_total += paid
                sym_funding[symbol] += paid
        # 2. Mark-to-market, day boundary, daily stop (taker, stop slippage).
        equity = equity_at(opens)
        if t.hour == 0 or day_start_equity is None:
            day_start_equity = equity
            daily_equity[t.normalize()] = equity
        if held() and equity <= day_start_equity * (1 - contract.daily_stop_fraction):
            maker_queue, fallback_queue = [], []
            close_all(opens, STOP_SLIPPAGE_BPS, t)
            stops += 1
            halted_until = t + pd.Timedelta(hours=contract.halt_hours)
            selection = Selection((), ())
        # 3. End of window: cancel pending orders and flatten by taker.
        if t == hours[-1]:
            maker_queue, fallback_queue = [], []
            close_all(opens, final_slip, t)
        # 4. Maker attempts at the 01:00 open, judged on the 01:00 candle.
        if maker_queue and t == maker_due:
            for symbol, target_notional, decided in maker_queue:
                price = float(opens[symbol])
                target_qty = target_notional / price
                delta = target_qty - qty[symbol]
                if abs(delta) < EPSILON:
                    continue
                if not execution.maker:
                    taker(
                        symbol,
                        target_notional,
                        opens,
                        decided,
                        execution.taker_slippage_bps,
                        "taker_planned",
                    )
                    continue
                fills["maker_orders"] += 1
                margin = execution.trade_through_bps / 10_000.0
                if delta > 0:
                    filled = float(low_rows[t][symbol]) <= price * (1 - margin)
                else:
                    filled = float(high_rows[t][symbol]) >= price * (1 + margin)
                if filled:
                    trade(
                        symbol,
                        target_qty,
                        price,
                        execution.maker_fee_bps,
                        0.0,
                        decided,
                        "maker",
                    )
                    fills["maker_filled"] += 1
                else:
                    fallback_queue.append((symbol, target_notional, decided))
                    fallback_due = t + one_hour
            maker_queue = []
        # 5. Taker completion of unfilled maker legs at the 02:00 open.
        if fallback_queue and t == fallback_due:
            for symbol, target_notional, decided in fallback_queue:
                taker(
                    symbol,
                    target_notional,
                    opens,
                    decided,
                    execution.taker_slippage_bps,
                    "taker_fallback",
                )
            fallback_queue = []
        # 6. Daily decision at 00:00 using settlements and candles completed by then.
        if (
            t in decision_rows
            and t + two_hours <= hours[-1]
            and (halted_until is None or t >= halted_until)
        ):
            decisions += 1
            row = decision_rows[t].copy()
            capped = [s for s in held() if t - entered_at[s] >= max_hold]
            forced += len(capped)
            locked_shorts = [
                s for s in held() if qty[s] < 0 and s not in capped and t - entered_at[s] < min_hold
            ]
            locked_longs = [
                s for s in held() if qty[s] > 0 and s not in capped and t - entered_at[s] < min_hold
            ]
            previous = Selection(
                tuple(s for s in selection.shorts if s not in capped),
                tuple(s for s in selection.longs if s not in capped),
            )
            # A capped leg is closed and only reconsidered at the next daily decision.
            row[capped] = float("nan")
            ranked = select_legs(row, k=rule.k, previous=previous)
            shorts = list(locked_shorts)
            for symbol in ranked.shorts:
                if len(shorts) >= rule.k:
                    break
                if symbol not in shorts and symbol not in locked_longs:
                    shorts.append(symbol)
            longs = list(locked_longs)
            for symbol in ranked.longs:
                if len(longs) >= rule.k:
                    break
                if symbol not in longs and symbol not in shorts:
                    longs.append(symbol)
            candidate = Selection(tuple(shorts), tuple(longs))
            allow_entries = t <= entry_end
            if allow_entries:
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
            targets = {s: -leg for s in candidate.shorts} | {s: leg for s in candidate.longs}
            orders: list[tuple[str, float, pd.Timestamp]] = []
            for symbol in held():
                if symbol not in targets:
                    orders.append((symbol, 0.0, t))
            for symbol, target_notional in targets.items():
                current = qty[symbol] * float(opens[symbol])
                if (
                    qty[symbol] == 0.0
                    or (current > 0) != (target_notional > 0)
                    or abs(current / target_notional - 1) > contract.rebalance_band
                ):
                    orders.append((symbol, target_notional, t))
            if orders:
                maker_queue = orders
                maker_due = t + one_hour
            selection = candidate
        # 7. Episode bookkeeping (flat to flat, as in Phase 2).
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

    final_prices = base.open.loc[hours[-1]]
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
    attempts = fills["maker_orders"]
    extra = dict(fills)
    extra["maker_fill_rate"] = fills["maker_filled"] / attempts if attempts else None
    total_notional = fills["maker_notional"] + fills["taker_notional"]
    extra["maker_notional_share"] = (
        fills["maker_notional"] / total_notional if total_notional else None
    )
    return SimulationResult(
        rule=rule,
        cost=execution,
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
        extra=extra,
    )
