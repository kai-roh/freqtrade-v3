"""Phase 2h hourly panel, point-in-time universe, funding events, and features
(PHASE2H_PREREGISTRATION.md §2-3).

Bar t covers [t, t+1h). A feature on bar t uses data up to the end of bar t; the
decision taken then fills at the open of bar t+1.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from v3.phase2d.data import _parse_funding, load_panel
from v3.phase2d.engine import Market

from .data import load_bars

UNIVERSE = 20
FEATURES_A = (
    "r1", "r4", "r24", "r72", "rel24", "vsurge", "tk4", "tk24", "volratio", "vwap_gap",
    "range_pos",
)  # fmt: skip
FEATURES_B = FEATURES_A + ("oi4", "oi24", "top_z", "acct_z", "funding")


@dataclass
class HourlyPanel:
    index: pd.DatetimeIndex
    symbols: list[str]
    open: np.ndarray
    high: np.ndarray
    low: np.ndarray
    close: np.ndarray
    universe: np.ndarray  # bool (T, S): in the day's top-20
    tier_bps: np.ndarray  # slippage bps (T, S) from the previous day's liquidity rank
    funding_end: np.ndarray  # funding rate settled at the end of bar t (T, S)
    features: dict[str, np.ndarray]  # raw feature values (T, S), float32


def _wide(frames: dict[str, pd.Series], index: pd.DatetimeIndex) -> pd.DataFrame:
    return pd.DataFrame(frames).reindex(index).astype(float)


def daily_universe(data2d: Path, index: pd.DatetimeIndex, symbols: list[str]):
    """Universe and slippage tier per hour, from the previous UTC day's Phase 2d rank."""
    market = Market(load_panel(data2d / "panel-um.csv.gz"), "perp")
    rank = pd.DataFrame(market.rank, index=market.days, columns=market.symbols)
    base = rank.T.groupby(lambda s: s.split("#")[0]).min().T  # relisted series share a ticker
    base = base.reindex(columns=symbols)
    prev = base.shift(1)  # day D uses the rank at the close of D-1
    hourly = prev.reindex(index.floor("D")).to_numpy()
    universe = hourly <= UNIVERSE
    tier = np.where(hourly <= 10, 5.0, 10.0)
    return universe, tier


def funding_events(data2d: Path, index: pd.DatetimeIndex, symbols: list[str]) -> np.ndarray:
    """Rate settled at the end of each bar (a settlement at time T ends bar T-1h)."""
    out = np.zeros((len(index), len(symbols)))
    pos = {s: j for j, s in enumerate(symbols)}
    start = index[0]
    for path in sorted((data2d / "raw" / "um" / "funding").glob("*.zip")):
        symbol = path.name.split("-fundingRate-")[0]
        if symbol not in pos:
            continue
        series = _parse_funding(path.read_bytes())
        bar = ((series.index - start) / pd.Timedelta(hours=1)).to_numpy()
        bar = np.rint(bar).astype(int) - 1  # settlement at T (+ms jitter) ends bar T-1h
        ok = (bar >= 0) & (bar < len(index))
        np.add.at(out[:, pos[symbol]], bar[ok], series.to_numpy()[ok])
    return out


def build_panel(data2h: Path, data2d: Path, symbols: list[str]) -> HourlyPanel:
    bars = {s: load_bars(data2h, "1h", s) for s in symbols}
    bars = {s: b for s, b in bars.items() if len(b)}
    symbols = sorted(bars)
    start = min(b.index.min() for b in bars.values())
    end = max(b.index.max() for b in bars.values())
    index = pd.date_range(start, end, freq="h")
    f = {k: _wide({s: b[k] for s, b in bars.items()}, index) for k in
         ("open", "high", "low", "close", "quote_volume", "taker_quote")}  # fmt: skip
    close, qv = f["close"], f["quote_volume"]
    feats: dict[str, pd.DataFrame] = {}
    r1 = close / close.shift(1) - 1
    for n in (1, 4, 24, 72):
        feats[f"r{n}"] = close / close.shift(n) - 1
    feats["rel24"] = feats["r24"].sub(feats["r24"]["BTCUSDT"], axis=0)
    q4 = qv.rolling(4, min_periods=4).sum()
    feats["vsurge"] = q4 / (qv.rolling(168, min_periods=120).sum().shift(4) * 4 / 168)
    feats["tk4"] = f["taker_quote"].rolling(4, min_periods=4).sum() / q4
    feats["tk24"] = (
        f["taker_quote"].rolling(24, min_periods=24).sum() / qv.rolling(24, min_periods=24).sum()
    )
    feats["volratio"] = (
        r1.rolling(24, min_periods=20).std() / r1.rolling(168, min_periods=120).std()
    )
    typical = (f["high"] + f["low"] + close) / 3
    day = index.floor("D")
    cum_qv = qv.groupby(day).cumsum()
    cum_px = (qv * typical).groupby(day).cumsum()
    feats["vwap_gap"] = close / (cum_px / cum_qv.where(cum_qv > 0)) - 1
    low24 = f["low"].rolling(24, min_periods=24).min()
    high24 = f["high"].rolling(24, min_periods=24).max()
    feats["range_pos"] = (close - low24) / (high24 - low24).where(high24 > low24)
    metrics = {}
    for s in symbols:
        path = data2h / "metrics-1h" / f"{s}.csv.gz"
        if path.is_file():
            m = pd.read_csv(path)
            if len(m) and "time" in m.columns:
                metrics[s] = m.set_index(pd.to_datetime(m.pop("time"), utc=True))
    for col, key in (("oi_value", "oi"), ("top_ls", "top"), ("acct_ls", "acct")):
        metrics_col = _wide({s: m[col] for s, m in metrics.items() if col in m}, index)
        metrics_col = metrics_col.reindex(columns=symbols)
        if key == "oi":
            oi = metrics_col.where(metrics_col > 0)
            feats["oi4"] = oi / oi.shift(4) - 1
            feats["oi24"] = oi / oi.shift(24) - 1
        else:
            feats[f"{key}_z"] = metrics_col - metrics_col.rolling(168, min_periods=120).mean()
    funding_end = funding_events(data2d, index, symbols)
    settled = pd.DataFrame(np.where(funding_end != 0, funding_end, np.nan), index=index,
                           columns=symbols)  # fmt: skip
    feats["funding"] = settled.ffill()
    universe, tier = daily_universe(data2d, index, symbols)
    as32 = {k: v.reindex(columns=symbols).to_numpy(np.float32) for k, v in feats.items()}
    return HourlyPanel(
        index=index,
        symbols=symbols,
        open=f["open"].to_numpy(),
        high=f["high"].to_numpy(),
        low=f["low"].to_numpy(),
        close=close.to_numpy(),
        universe=universe & close.notna().to_numpy(),
        tier_bps=tier,
        funding_end=funding_end,
        features=as32,
    )


def ranked(values: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Cross-sectional rank within ``mask`` per row, scaled to [-0.5, 0.5]; missing -> 0."""
    frame = pd.DataFrame(np.where(mask & np.isfinite(values), values, np.nan))
    r = frame.rank(axis=1)
    n = frame.notna().sum(axis=1)
    scaled = (r.sub(1)).div((n - 1).where(n > 1), axis=0) - 0.5
    return scaled.fillna(0.0).to_numpy(np.float32)
