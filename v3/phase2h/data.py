"""Phase 2h data: intraday USD-M perpetual candles and hourly positioning metrics.

Each archive file is reduced as it is downloaded, and only per-symbol compressed CSVs
plus the raw files' SHA-256 are kept (disk is short).

- ``bars-<interval>/<symbol>.csv.gz``: open, high, low, close, quote_volume,
  taker_quote, and trades per bar, indexed by bar open time (UTC).
- ``metrics-1h/<symbol>.csv.gz``: hourly open interest value (last 5-minute row of
  the hour), top-trader and all-account long/short ratios, and taker long/short
  volume ratio (hourly means).
"""

from __future__ import annotations

import hashlib
import io
import re
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

from v3.phase2d.data import ARCHIVE, KLINE_COLUMNS, MARKETS, _get, _listing
from v3.phase2f.data import METRICS

BAR_FIELDS = ("open", "high", "low", "close", "quote_volume", "taker_quote", "trades")


def parse_bars(raw: bytes) -> pd.DataFrame:
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        text = archive.read(archive.namelist()[0])
    frame = pd.read_csv(io.BytesIO(text), header=None)
    if not str(frame.iloc[0, 0]).isdigit():
        frame = frame.iloc[1:]
    frame = frame.iloc[:, : len(KLINE_COLUMNS)]
    frame.columns = KLINE_COLUMNS[: frame.shape[1]]
    ts = frame["open_time"].astype("int64").to_numpy()
    ts = np.where(ts > 10**14, ts // 1000, ts)
    out = pd.DataFrame({c: frame[c].astype(float).to_numpy() for c in BAR_FIELDS})
    out.index = pd.to_datetime(ts, unit="ms", utc=True)
    out.index.name = "time"
    return out[~out.index.duplicated(keep="last")]


def reduce_metrics_hourly(raw: bytes) -> pd.DataFrame:
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        frame = pd.read_csv(io.BytesIO(archive.read(archive.namelist()[0])))
    if frame.empty or "create_time" not in frame.columns:
        return pd.DataFrame()
    frame.index = pd.to_datetime(frame["create_time"], utc=True)

    def col(name: str) -> pd.Series:
        return pd.to_numeric(frame.get(name), errors="coerce")

    hour = frame.index.floor("h")
    out = pd.DataFrame(
        {
            "oi_value": col("sum_open_interest_value").groupby(hour).last(),
            "top_ls": col("sum_toptrader_long_short_ratio").groupby(hour).mean(),
            "acct_ls": col("count_long_short_ratio").groupby(hour).mean(),
            "taker_ls": col("sum_taker_long_short_vol_ratio").groupby(hour).mean(),
        }
    )
    out.index.name = "time"
    return out


def _write(frame: pd.DataFrame, path: Path, hashes: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".part")
    frame.sort_index().to_csv(
        tmp, compression={"method": "gzip", "mtime": 0}, float_format="%.10g"
    )
    tmp.replace(path)
    path.with_suffix(".sha256").write_text("\n".join(hashes) + "\n")


def download_bars(
    symbols: list[str], out_dir: Path, interval: str, start: str, end: str, workers: int = 24
) -> None:
    months = {p.strftime("%Y-%m") for p in pd.period_range(start, end, freq="M")}

    def one(symbol: str) -> None:
        path = out_dir / f"bars-{interval}" / f"{symbol}.csv.gz"
        if path.is_file():
            return
        base = f"{MARKETS['um']}/{symbol}/{interval}"
        _, keys = _listing(base + "/")
        found = sorted(set(re.findall(rf"-{interval}-(\d{{4}}-\d{{2}})\.zip$", "\n".join(keys), re.M)))
        frames, hashes = [], []
        for month in (m for m in found if m in months):
            raw = _get(f"{ARCHIVE}/{base}/{symbol}-{interval}-{month}.zip")
            if raw is None:
                continue
            frames.append(parse_bars(raw))
            hashes.append(f"{month} {hashlib.sha256(raw).hexdigest()}")
        frame = pd.concat(frames) if frames else pd.DataFrame(columns=BAR_FIELDS)
        _write(frame[~frame.index.duplicated(keep="last")], path, hashes)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(one, symbols))


def download_metrics_hourly(
    symbols: list[str], out_dir: Path, first_day: str, last_day: str, workers: int = 48
) -> None:
    lo, hi = pd.Timestamp(first_day), pd.Timestamp(last_day)

    def one(symbol: str) -> None:
        path = out_dir / "metrics-1h" / f"{symbol}.csv.gz"
        if path.is_file():
            return
        _, keys = _listing(f"{METRICS}/{symbol}/")
        days = sorted(
            d for d in re.findall(r"-metrics-(\d{4}-\d{2}-\d{2})\.zip$", "\n".join(keys), re.M)
            if lo <= pd.Timestamp(d) <= hi
        )  # fmt: skip
        frames, hashes = [], []
        for d in days:
            raw = _get(f"{ARCHIVE}/{METRICS}/{symbol}/{symbol}-metrics-{d}.zip")
            if raw is None:
                continue
            frames.append(reduce_metrics_hourly(raw))
            hashes.append(f"{d} {hashlib.sha256(raw).hexdigest()}")
        frames = [f for f in frames if not f.empty]
        frame = pd.concat(frames) if frames else pd.DataFrame()
        if not frame.empty:
            frame = frame[~frame.index.duplicated(keep="last")]
        _write(frame, path, hashes)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(one, symbols))


def load_bars(out_dir: Path, interval: str, symbol: str) -> pd.DataFrame:
    path = out_dir / f"bars-{interval}" / f"{symbol}.csv.gz"
    frame = pd.read_csv(path, index_col="time", parse_dates=["time"])
    if frame.index.tz is None:
        frame.index = frame.index.tz_localize("UTC")
    return frame.astype(float)
