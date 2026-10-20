"""Pre-registered Phase 2 signals and the integer-legs selection rule.

All signals use only completed candles and completed settlements at or before
the decision timestamp. Selection returns k shorts (highest score) and k longs
(lowest score) with one-rank hysteresis and deterministic tie handling.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


def trailing_funding_mean(funding: pd.DataFrame, window_hours: int) -> pd.DataFrame:
    """Mean funding per settlement over a trailing time window ending at each settlement.

    The window is defined in hours, not settlement counts, and a value is only
    produced when the window holds the full expected number of settlements.
    """
    if window_hours <= 0:
        raise ValueError("window_hours must be positive")
    gaps = funding.index.to_series().diff().dropna()
    if gaps.empty:
        raise ValueError("at least two settlements are required")
    interval_hours = int(gaps.mode().iloc[0].total_seconds() // 3600)
    expected = window_hours // interval_hours
    if expected < 1:
        raise ValueError("window must cover at least one settlement interval")
    rolled = funding.rolling(f"{window_hours}h", closed="both", min_periods=expected).mean()
    return rolled


def daily_lookback_returns(close: pd.DataFrame, lookback_days: int) -> pd.DataFrame:
    """Return over the last L completed UTC days, indexed at the 00:00 boundary."""
    if lookback_days <= 0:
        raise ValueError("lookback_days must be positive")
    daily_close = close.resample("1D", label="right", closed="right").last().dropna(how="any")
    return daily_close / daily_close.shift(lookback_days) - 1


@dataclass(frozen=True)
class Selection:
    shorts: tuple[str, ...]
    longs: tuple[str, ...]


def select_legs(
    scores: pd.Series,
    *,
    k: int,
    previous: Selection | None = None,
) -> Selection:
    """k highest scores short, k lowest long, with one-rank hysteresis.

    A held symbol stays while its rank is within k+1 on its side; ties prefer
    held symbols, then symbol order. Symbols with NaN scores are ineligible.
    """
    if k < 1:
        raise ValueError("k must be positive")
    valid = scores.dropna()
    if len(valid) < 2 * k:
        return Selection((), ())
    previous = previous or Selection((), ())
    held = set(previous.shorts) | set(previous.longs)

    def pick(order: list[str], prior: tuple[str, ...]) -> tuple[str, ...]:
        keep_band = set(order[: k + 1])
        kept = [symbol for symbol in prior if symbol in keep_band]
        chosen = list(kept)
        for symbol in order:
            if len(chosen) >= k:
                break
            if symbol not in chosen:
                chosen.append(symbol)
        return tuple(chosen[:k])

    def ordered(ascending: bool) -> list[str]:
        frame = pd.DataFrame({"score": valid})
        frame["held"] = [0 if symbol in held else 1 for symbol in frame.index]
        frame["name"] = frame.index
        frame = frame.sort_values(["score", "held", "name"], ascending=[ascending, True, True])
        return list(frame.index)

    shorts = pick(ordered(ascending=False), previous.shorts)
    longs = pick(ordered(ascending=True), tuple(s for s in previous.longs if s not in shorts))
    longs = tuple(symbol for symbol in longs if symbol not in shorts)
    if len(longs) < k:
        for symbol in ordered(ascending=True):
            if len(longs) >= k:
                break
            if symbol not in longs and symbol not in shorts:
                longs = (*longs, symbol)
    return Selection(shorts, longs)


def funding_spread(scores: pd.Series, selection: Selection) -> float | None:
    """Mean trailing funding of the short basket minus the long basket."""
    if not selection.shorts or not selection.longs:
        return None
    return float(scores[list(selection.shorts)].mean() - scores[list(selection.longs)].mean())
