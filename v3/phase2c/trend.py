"""Phase 2c trend rules and the continuous single-account simulator.

Implements docs/PHASE2C_PREREGISTRATION.md §2-§3. Decisions are taken daily at
00:00 UTC from completed daily closes (the 23:00 candle close) and executed by
taker at the 01:00 open. Funding settles on positions held into a settlement at
the previous candle's mark, as in Phase 2. Each asset uses half the sleeve at
most 1x. A schedule of rules lets one continuous account switch configurations
at walk-forward window boundaries, so validation windows never overlap.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from v3.phase2.data import Phase2Panel

SYMBOLS = ("BTC", "ETH")
TAKER_FEE_BPS = 5.0
VOL_WINDOW = 60
VOL_TARGET = 0.25
DEAD_BAND = 0.5
REBALANCE_THRESHOLD = 0.20
EPSILON = 1e-12


@dataclass(frozen=True)
class Cost:
    name: str
    slippage_bps: float
    fee_bps: float = TAKER_FEE_BPS


NORMAL = Cost("normal", 2.0)
STRESS = Cost("stress", 5.0)


@dataclass(frozen=True)
class TrendRule:
    """One registered configuration or control."""

    kind: str  # "trend", "bh_vt", "ma200", "none"
    lookback_days: int = 0
    mapping: str = ""  # "binary" or "linear" for trend
    vol_target: float = VOL_TARGET

    def label(self) -> str:
        if self.kind == "trend":
            base = f"H4 L={self.lookback_days}d {self.mapping}"
        else:
            base = {"bh_vt": "BH-VT", "ma200": "MA200", "none": "H0"}[self.kind]
        if self.vol_target != VOL_TARGET:
            base += f" vol={self.vol_target:.0%}"
        return base


def trend_grid() -> tuple[TrendRule, ...]:
    return tuple(
        TrendRule("trend", lookback_days=lb, mapping=m)
        for lb in (20, 60, 120)
        for m in ("binary", "linear")
    )


CONTROLS = (TrendRule("none"), TrendRule("bh_vt"), TrendRule("ma200"))


def daily_closes(panel: Phase2Panel) -> pd.DataFrame:
    """Completed daily close indexed at the 00:00 decision that can first use it."""
    closes = panel.close.shift(1)
    return closes[closes.index.hour == 0].dropna(how="all")


def target_weights(panel: Phase2Panel, rule: TrendRule) -> pd.DataFrame:
    """Target weight per asset in [-1, 1] at each 00:00 decision (NaN while warming up)."""
    return weights_from_daily(daily_closes(panel), rule)


def weights_from_daily(dc: pd.DataFrame, rule: TrendRule) -> pd.DataFrame:
    """Target weights from completed daily closes indexed at their decision time.

    Shared by the research simulator and the live executor so both compute the
    same signal from the same closes.
    """
    if rule.vol_target <= 0:
        raise ValueError("vol_target must be positive")
    log_close = np.log(dc)
    sigma = log_close.diff().rolling(VOL_WINDOW, min_periods=VOL_WINDOW).std()
    scale = (rule.vol_target / (sigma * math.sqrt(365.0))).clip(upper=1.0)
    if rule.kind == "none":
        return pd.DataFrame(0.0, index=dc.index, columns=dc.columns)
    if rule.kind == "bh_vt":
        return scale
    if rule.kind == "ma200":
        average = dc.rolling(200, min_periods=200).mean()
        signal = np.sign(dc - average).where(average.notna())
        return signal * scale
    if rule.kind != "trend" or rule.lookback_days <= 0:
        raise ValueError(f"unknown rule {rule}")
    z = (log_close - log_close.shift(rule.lookback_days)) / (sigma * math.sqrt(rule.lookback_days))
    if rule.mapping == "binary":
        signal = np.sign(z).where(z.abs() >= DEAD_BAND, 0.0).where(z.notna())
    elif rule.mapping == "linear":
        signal = (z / 2.0).clip(-1.0, 1.0)
    else:
        raise ValueError(f"unknown mapping {rule.mapping}")
    return signal * scale


@dataclass(frozen=True)
class VenueFilters:
    """Lot step and minimum notional per asset (constrained mode).

    The exchange applies the minimum notional to each order, not to the holding.
    A perpetual order that only reduces the position is sent reduce-only and is
    exempt (Binance -4164); spot has no such exemption. ``legacy_holding_rule``
    reproduces the recorded 2026-10-02 Phase 2c run, which checked the holding.
    """

    step: dict[str, float]
    min_notional: dict[str, float]
    reduce_only_exempt: bool = True
    legacy_holding_rule: bool = False

    def floor_to_step(self, symbol: str, qty: float) -> float:
        if qty == 0.0:
            return 0.0
        step = self.step[symbol]
        return math.copysign(math.floor(abs(qty) / step + 1e-9) * step, qty)

    def round_qty(self, symbol: str, qty: float, price: float) -> float:
        """Legacy holding-based rule: floor, then zero a holding below the minimum."""
        rounded = self.floor_to_step(symbol, qty)
        if abs(rounded) * price < self.min_notional[symbol]:
            return 0.0
        return rounded

    def executable(self, symbol: str, current: float, target: float, price: float) -> float:
        """Position after one order toward ``target``; ``current`` when no order is allowed."""
        rounded = self.floor_to_step(symbol, target)
        delta = rounded - current
        if abs(delta) < self.step[symbol] / 2:
            return current
        reducing = current != 0.0 and rounded * current >= 0.0 and abs(rounded) < abs(current)
        if reducing and self.reduce_only_exempt:
            return rounded
        if abs(delta) * price < self.min_notional[symbol]:
            return current
        return rounded


@dataclass
class TrendResult:
    label: str
    cost: str
    daily_returns: pd.Series
    daily_pnl: pd.Series
    equity: pd.Series
    decomposition: dict[str, float]
    long_short: dict[str, float]
    per_symbol: dict[str, dict[str, float]]
    episodes: list[dict[str, Any]]
    trades: int
    traded_notional: float
    time_in_market: dict[str, float]
    rounding_skips: int
    extra: dict[str, Any] = field(default_factory=dict)


def simulate_trend(
    panel: Phase2Panel,
    schedule: list[tuple[pd.Timestamp, TrendRule]],
    *,
    cost: Cost,
    start: pd.Timestamp,
    end: pd.Timestamp,
    sleeve: float = 500.0,
    filters: VenueFilters | None = None,
    weights_cache: dict[TrendRule, pd.DataFrame] | None = None,
    market: str = "perp",
    flatten_at_end: bool = True,
) -> TrendResult:
    """One continuous account over [start, end]; flat at the end unless told otherwise.

    ``flatten_at_end=False`` (forward observation) keeps the positions open and
    values them at the last hour's open; the open positions are in ``extra``.

    ``market="spot"`` refuses short targets and uses the panel without funding.
    The end-of-window flattening is an accounting close and ignores the filters.

    ``schedule`` is a list of (effective_from, rule); the rule in force at a
    decision is the last entry whose effective_from is at or before it.
    """
    if not schedule:
        raise ValueError("schedule must not be empty")
    schedule = sorted(schedule, key=lambda item: item[0])
    cache = weights_cache if weights_cache is not None else {}
    for _, rule in schedule:
        if rule not in cache:
            cache[rule] = target_weights(panel, rule)
    index = panel.open.index
    i0, i1 = index.searchsorted(start), index.searchsorted(end, side="right")
    times = index[i0:i1]
    n = len(times)
    if n < 2:
        raise ValueError("window must contain at least two hours")
    symbols = list(panel.symbols)
    m = len(symbols)
    cap = sleeve / m
    opens = panel.open.to_numpy(dtype=float)[i0:i1]
    marks = panel.mark.shift(1).to_numpy(dtype=float)[i0:i1]
    rates = panel.funding.reindex(times).to_numpy(dtype=float)
    is_settlement = ~np.isnan(rates).all(axis=1)
    hour_of_day = times.hour.to_numpy()
    # Target weights in force at each 00:00 decision (NaN elsewhere or while warming up).
    targets = np.full((n, m), np.nan)
    # The rebalance threshold is in units of the registered 25% exposure, so a lower
    # volatility target scales the threshold with the positions (Decision 0020).
    thresholds = np.full(n, REBALANCE_THRESHOLD)
    effective = [t for t, _ in schedule]
    decision_rows = np.flatnonzero(hour_of_day == 0)
    for row in decision_rows:
        t = times[row]
        k = max(i for i, eff in enumerate(effective) if eff <= t) if effective[0] <= t else 0
        rule = schedule[k][1]
        frame = cache[rule]
        thresholds[row] = REBALANCE_THRESHOLD * rule.vol_target / VOL_TARGET
        if t in frame.index:
            targets[row] = frame.loc[t].to_numpy(dtype=float)

    if market not in {"perp", "spot"}:
        raise ValueError("market must be perp or spot")
    if market == "spot" and (np.nan_to_num(targets) < 0).any():
        raise ValueError("spot cannot hold a short position")
    cash = sleeve
    qty = np.zeros(m)
    fees = slippage = funding_total = traded = 0.0
    trades = skips = attempts = 0
    trade_log: list[dict[str, Any]] = []
    long_pnl = short_pnl = 0.0
    sym_price = np.zeros(m)
    sym_funding = np.zeros(m)
    in_market = np.zeros(m, dtype=int)
    daily_equity: dict[pd.Timestamp, float] = {}
    pending: dict[int, float] | None = None
    pending_row = -1
    spells: dict[int, dict[str, Any]] = {}
    episodes: list[dict[str, Any]] = []

    def close_spell(j: int, t: pd.Timestamp) -> None:
        spell = spells.pop(j, None)
        if spell is not None:
            spell["end"] = t.isoformat()
            spell["pnl"] = spell["price"] + spell["funding"] - spell["costs"]
            episodes.append(spell)

    def trade(j: int, target_qty: float, price: float, t: pd.Timestamp) -> None:
        nonlocal cash, fees, slippage, traded, trades
        delta = target_qty - qty[j]
        if abs(delta) < EPSILON:
            return
        notional = abs(delta) * price
        fee = notional * cost.fee_bps / 10_000.0
        slip = notional * cost.slippage_bps / 10_000.0
        cash -= delta * price + fee + slip
        fees += fee
        slippage += slip
        traded += notional
        trades += 1
        before = qty[j]
        after = target_qty if abs(target_qty) > EPSILON else 0.0
        qty[j] = after
        trade_log.append(
            {
                "time": t.isoformat(),
                "symbol": symbols[j],
                "qty_before": float(before),
                "qty_after": float(after),
                "price": float(price),
                "fee": fee,
                "slippage": slip,
            }
        )
        if before != 0.0 and (after == 0.0 or (before > 0) != (after > 0)):
            spells[j]["costs"] += fee + slip
            close_spell(j, t)
            if after != 0.0:
                spells[j] = _new_spell(symbols[j], after, t)
        elif before == 0.0:
            spells[j] = _new_spell(symbols[j], after, t)
            spells[j]["costs"] += fee + slip
        else:
            spells[j]["costs"] += fee + slip

    for row in range(n):
        t = times[row]
        price_row = opens[row]
        if row > 0:
            steps = qty * (price_row - opens[row - 1])
            for j in range(m):
                if qty[j]:
                    sym_price[j] += steps[j]
                    if qty[j] > 0:
                        long_pnl += steps[j]
                    else:
                        short_pnl += steps[j]
                    spells[j]["price"] += steps[j]
                    in_market[j] += 1
        if is_settlement[row]:
            for j in range(m):
                if qty[j] and not np.isnan(rates[row, j]):
                    mark = marks[row, j] if not np.isnan(marks[row, j]) else price_row[j]
                    paid = -qty[j] * mark * rates[row, j]
                    cash += paid
                    funding_total += paid
                    sym_funding[j] += paid
                    spells[j]["funding"] += paid
        if hour_of_day[row] == 0:
            daily_equity[t] = cash + float(qty @ price_row)
        if row == n - 1 and flatten_at_end:
            for j in range(m):
                trade(j, 0.0, float(price_row[j]), t)
            break
        if pending is not None and row == pending_row:
            for j, weight in pending.items():
                price = float(price_row[j])
                target_qty = weight * cap / price
                attempts += 1
                if filters is not None and filters.legacy_holding_rule:
                    rounded = filters.round_qty(symbols[j], target_qty, price)
                    if rounded == 0.0 and abs(target_qty) > EPSILON:
                        skips += 1
                    target_qty = rounded
                elif filters is not None:
                    executable = filters.executable(symbols[j], qty[j], target_qty, price)
                    if abs(executable - qty[j]) < EPSILON:
                        skips += 1
                    target_qty = executable
                trade(j, target_qty, price, t)
            pending = None
        if hour_of_day[row] == 0 and row + 1 < n:
            orders: dict[int, float] = {}
            for j in range(m):
                target = targets[row, j]
                if np.isnan(target):
                    continue
                current = qty[j] * price_row[j] / cap
                flip = current != 0.0 and target != 0.0 and (current > 0) != (target > 0)
                to_flat = target == 0.0 and current != 0.0
                if flip or to_flat or abs(target - current) >= thresholds[row]:
                    orders[j] = float(target)
            if orders:
                pending = orders
                pending_row = row + 1

    end_equity = cash + float(qty @ opens[-1])
    equity = pd.Series(daily_equity).sort_index()
    equity.loc[times[-1].normalize() + pd.Timedelta(days=1)] = end_equity
    equity = equity[~equity.index.duplicated(keep="last")].sort_index()
    daily_pnl = equity.diff().dropna()
    daily_returns = equity.pct_change().dropna()
    total = end_equity - sleeve
    return TrendResult(
        label=" | ".join(sorted({rule.label() for _, rule in schedule})),
        cost=cost.name,
        daily_returns=daily_returns,
        daily_pnl=daily_pnl,
        equity=equity,
        decomposition={
            "total_pnl": total,
            "price_pnl": total - funding_total + fees + slippage,
            "funding_pnl": funding_total,
            "fees": fees,
            "slippage": slippage,
        },
        long_short={"long_price_pnl": long_pnl, "short_price_pnl": short_pnl},
        per_symbol={
            symbols[j]: {"price_pnl": float(sym_price[j]), "funding_pnl": float(sym_funding[j])}
            for j in range(m)
        },
        episodes=episodes,
        trades=trades,
        traded_notional=traded,
        time_in_market={symbols[j]: int(in_market[j]) / n for j in range(m)},
        rounding_skips=skips,
        extra={
            "order_attempts": attempts,
            "market": market,
            "open_positions": {symbols[j]: float(qty[j]) for j in range(m)},
            "last_open": {symbols[j]: float(opens[-1, j]) for j in range(m)},
            "last_hour": times[-1].isoformat(),
            "pending_orders": {symbols[j]: w for j, w in (pending or {}).items()},
            "trade_log": trade_log,
        },
    )


def load_spot_panel(
    data_dir: Path, *, manifest_path: Path | None, symbols: tuple[str, ...] = SYMBOLS
) -> Phase2Panel:
    """Spot 1h candles as a panel without funding (mark = close).

    With a manifest every file is hash-checked (frozen research data); without
    one (live forward observation) the files are read as they are.
    """
    files = json.loads(Path(manifest_path).read_text())["files"] if manifest_path else None
    opens, closes = {}, {}
    for symbol in symbols:
        path = Path(data_dir) / f"{symbol}_USDT-1h.feather"
        if files is not None:
            recorded = files.get(f"{symbol}/spot", {}).get("sha256")
            if recorded != hashlib.sha256(path.read_bytes()).hexdigest():
                raise ValueError(f"{path.name} differs from the frozen spot manifest")
        frame = pd.read_feather(path)
        index = pd.to_datetime(frame["date"], utc=True)
        opens[symbol] = pd.Series(frame["open"].astype(float).to_numpy(), index=index)
        closes[symbol] = pd.Series(frame["close"].astype(float).to_numpy(), index=index)
    open_frame = pd.DataFrame(opens).dropna(how="any")[list(symbols)]
    close_frame = pd.DataFrame(closes).loc[open_frame.index, list(symbols)]
    funding = pd.DataFrame(columns=list(symbols), index=pd.DatetimeIndex([], tz="UTC"), dtype=float)
    return Phase2Panel(
        open=open_frame, close=close_frame, mark=close_frame, funding=funding, symbols=symbols
    )


def _new_spell(symbol: str, qty: float, t: pd.Timestamp) -> dict[str, Any]:
    return {
        "symbol": symbol,
        "side": "long" if qty > 0 else "short",
        "start": t.isoformat(),
        "price": 0.0,
        "funding": 0.0,
        "costs": 0.0,
    }
