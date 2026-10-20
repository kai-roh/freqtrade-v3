"""Live T1 target weights from Mainnet public daily candles (PHASE2G_PREREGISTRATION.md §2).

The rule matches the backtest (``v3.phase2f.strategies`` T1 on the Phase 2d engine):

- **Universe:** on decision day d, the top 20 USDT perpetuals by 30-day median daily
  quote volume (at least 20 days in the window). A symbol needs 90 days of candles
  and a close on d. Stablecoin and wrapped bases are excluded.
- **Score:** taker buy quote volume / quote volume, averaged over L days.
- **Members:** for L in {3, 7, 14} and K in {3, 5}, long the K highest scores and
  short the K lowest, at 0.5/K each. A member is flat when fewer than 2K names have a
  score. T1 is the simple average of the six members.

Decisions are taken on Sundays (day d's candle closes at Monday 00:00 UTC) and
filled at Monday's open.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from v3.phase2d.data import eligible_symbol
from v3.phase2d.engine import ANCHOR, LIQUIDITY_WINDOW, MIN_HISTORY_DAYS
from v3.phase2f.strategies import T1_MEMBERS, UNIVERSE

SHORTLIST = 80  # symbols fetched, by 24h quote volume, before the 30-day ranking
KLINE_DAYS = 130


def is_decision_day(day: pd.Timestamp) -> bool:
    return (day.normalize() - ANCHOR).days % 7 == 0


def weights_from_frames(
    close: pd.DataFrame, quote_volume: pd.DataFrame, taker_quote: pd.DataFrame, day: pd.Timestamp
) -> dict[str, Any]:
    """T1 targets for decision day ``day`` from wide daily frames (index: UTC day)."""
    symbols = list(close.columns)
    age = close.notna().cumsum().where(close.notna())
    liquidity = quote_volume.rolling(LIQUIDITY_WINDOW, min_periods=20).median()
    eligible = (age >= MIN_HISTORY_DAYS) & close.notna() & liquidity.notna()
    rank = liquidity.where(eligible).rank(axis=1, ascending=False)
    if day not in rank.index:
        raise RuntimeError(f"no candles for decision day {day.date()}")
    universe = [s for s in symbols if rank.loc[day, s] <= UNIVERSE]
    share = taker_quote / quote_volume.where(quote_volume > 0)
    total: dict[str, float] = {}
    scores: dict[int, dict[str, float]] = {}
    for c in T1_MEMBERS:
        score = share.rolling(c.lookback, min_periods=c.lookback).mean().loc[day]
        scores[c.lookback] = {s: float(score[s]) for s in universe if np.isfinite(score[s])}
        ok = [s for s in universe if np.isfinite(score[s])]  # column order, like the backtest
        if len(ok) < 2 * c.k:
            continue
        values = np.array([score[s] for s in ok])
        order = np.argsort(values, kind="stable")
        longs = [ok[i] for i in order[::-1][: c.k]]
        shorts = [ok[i] for i in order[: c.k]]
        for s in longs:
            total[s] = total.get(s, 0.0) + 0.5 / c.k / len(T1_MEMBERS)
        for s in shorts:
            total[s] = total.get(s, 0.0) - 0.5 / c.k / len(T1_MEMBERS)
    weights = {s: w for s, w in sorted(total.items()) if abs(w) > 1e-12}
    return {
        "decision_day": day.date().isoformat(),
        "universe": universe,
        "weights": weights,
        "scores": scores,
        "rank": {s: int(rank.loc[day, s]) for s in universe},
    }


def live_frames(client, now: pd.Timestamp) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Completed Mainnet daily candles for the shortlisted perpetuals."""
    info = client.public_exchange_info()
    perps = {
        row["symbol"]
        for row in info["symbols"]
        if row.get("status") == "TRADING"
        and row.get("contractType") == "PERPETUAL"
        and row.get("quoteAsset") == "USDT"
        and eligible_symbol(row["symbol"])
    }
    tickers = [t for t in client.public_24hr() if t["symbol"] in perps]
    tickers.sort(key=lambda t: -float(t["quoteVolume"]))
    now_ms = int(now.timestamp() * 1000)
    close, qv, taker = {}, {}, {}
    for t in tickers[:SHORTLIST]:
        rows = client.public_daily_klines(t["symbol"], limit=KLINE_DAYS)
        done = [r for r in rows if int(r[6]) < now_ms]
        index = pd.to_datetime([int(r[0]) for r in done], unit="ms", utc=True)
        close[t["symbol"]] = pd.Series([float(r[4]) for r in done], index=index)
        qv[t["symbol"]] = pd.Series([float(r[7]) for r in done], index=index)
        taker[t["symbol"]] = pd.Series([float(r[10]) for r in done], index=index)
    frames = [pd.DataFrame(x).sort_index() for x in (close, qv, taker)]
    full = pd.date_range(frames[0].index.min(), frames[0].index.max(), freq="D")
    return tuple(f.reindex(full) for f in frames)  # type: ignore[return-value]


def live_targets(client, now: pd.Timestamp) -> dict[str, Any]:
    close, qv, taker = live_frames(client, now)
    day = now.floor("D") - pd.Timedelta(days=1)
    return weights_from_frames(close, qv, taker, day)
