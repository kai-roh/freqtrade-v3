"""Phase 2f data: daily positioning metrics and taker flow for USD-M perpetuals.

Sources (data.binance.vision):

- ``futures/um/daily/metrics``: 5-minute open interest, top-trader and all-account
  long/short ratios, and the taker buy/sell volume ratio. One file per symbol-day.
- The taker buy quote volume column of the 1d klines already cached by Phase 2d.

Metrics files are many and small, so each is reduced to one daily row as it is
downloaded and only the reduction plus the raw file's SHA-256 is kept (disk is
short). Reduction of day d, all rows stamped within d (UTC):

- ``oi_value``: the last ``sum_open_interest_value`` of the day (USDT).
- ``top_ls``: mean ``sum_toptrader_long_short_ratio`` (position ratio).
- ``acct_ls``: mean ``count_long_short_ratio`` (all accounts).
- ``taker_ls``: mean ``sum_taker_long_short_vol_ratio``.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

from v3.phase2d.data import ARCHIVE, _get, _listing, _parse_klines

METRICS = "data/futures/um/daily/metrics"
METRIC_FIELDS = ("oi_value", "top_ls", "acct_ls", "taker_ls")


def reduce_metrics(raw: bytes) -> tuple[pd.Timestamp, dict[str, float]] | None:
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        frame = pd.read_csv(io.BytesIO(archive.read(archive.namelist()[0])))
    if frame.empty or "create_time" not in frame.columns:
        return None
    ts = pd.to_datetime(frame["create_time"], utc=True)
    day = ts.dt.normalize().mode().iloc[0]
    frame = frame[ts.dt.normalize() == day]

    def col(name: str) -> pd.Series:
        return pd.to_numeric(frame.get(name), errors="coerce")

    oi = col("sum_open_interest_value").dropna()
    return day, {
        "oi_value": float(oi.iloc[-1]) if len(oi) else np.nan,
        "top_ls": float(col("sum_toptrader_long_short_ratio").mean()),
        "acct_ls": float(col("count_long_short_ratio").mean()),
        "taker_ls": float(col("sum_taker_long_short_vol_ratio").mean()),
    }


def download_metrics(symbols: list[str], out_dir: Path, last_day: str, workers: int = 32) -> None:
    """Reduce every metrics file up to ``last_day`` into ``out_dir/metrics/<symbol>.csv``.

    A symbol already present is skipped, so an interrupted run resumes.
    """
    target = out_dir / "metrics"
    target.mkdir(parents=True, exist_ok=True)
    stop = pd.Timestamp(last_day)

    def one(symbol: str) -> None:
        path = target / f"{symbol}.csv"
        if path.is_file():
            return
        _, keys = _listing(f"{METRICS}/{symbol}/")
        days = sorted(
            d for d in re.findall(r"-metrics-(\d{4}-\d{2}-\d{2})\.zip$", "\n".join(keys), re.M)
            if pd.Timestamp(d) <= stop
        )  # fmt: skip
        rows = []
        for d in days:
            raw = _get(f"{ARCHIVE}/{METRICS}/{symbol}/{symbol}-metrics-{d}.zip")
            if raw is None:
                continue
            reduced = reduce_metrics(raw)
            if reduced is None:
                continue
            day, values = reduced
            rows.append({"day": day.strftime("%Y-%m-%d"), **values,
                         "sha256": hashlib.sha256(raw).hexdigest()})  # fmt: skip
        tmp = path.with_suffix(".part")
        pd.DataFrame(rows, columns=["day", *METRIC_FIELDS, "sha256"]).to_csv(
            tmp, index=False, float_format="%.10g"
        )
        tmp.replace(path)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(one, symbols))


def load_metrics(
    out_dir: Path, days: pd.DatetimeIndex, symbols: list[str]
) -> dict[str, pd.DataFrame]:
    """Wide daily metric panels aligned to ``days`` x ``symbols`` (``#n`` series share a ticker)."""
    per: dict[str, pd.DataFrame] = {}
    for symbol in sorted({s.split("#")[0] for s in symbols}):
        path = out_dir / "metrics" / f"{symbol}.csv"
        if path.is_file():
            frame = pd.read_csv(path, parse_dates=["day"])
            if not frame.empty:
                frame["day"] = frame["day"].dt.tz_localize("UTC")
                per[symbol] = frame.drop_duplicates("day", keep="last").set_index("day")
    out = {}
    for f in METRIC_FIELDS:
        wide = pd.DataFrame({s: per[s.split("#")[0]][f] for s in symbols if s.split("#")[0] in per})
        out[f] = wide.reindex(index=days, columns=symbols).astype(float)
    return out


def taker_buy_share(out_dir: Path, days: pd.DatetimeIndex, symbols: list[str]) -> pd.DataFrame:
    """Daily taker buy quote volume / quote volume from the cached Phase 2d 1d klines."""
    raw_dir = out_dir / "raw" / "um" / "klines"
    per: dict[str, list[pd.Series]] = {}
    wanted = {s.split("#")[0] for s in symbols}
    for path in sorted(raw_dir.glob("*.zip")):
        symbol = path.name.split("-1d-")[0]
        if symbol not in wanted:
            continue
        frame = _parse_klines(path.read_bytes(), extra=("taker_quote",))
        share = frame["taker_quote"] / frame["quote_volume"].where(frame["quote_volume"] > 0)
        per.setdefault(symbol, []).append(share)
    series = {s: pd.concat(v).sort_index() for s, v in per.items()}
    series = {s: v[~v.index.duplicated(keep="last")] for s, v in series.items()}
    wide = pd.DataFrame({s: series[s.split("#")[0]] for s in symbols if s.split("#")[0] in series})
    return wide.reindex(index=days, columns=symbols).astype(float)


def write_manifest(out_dir: Path) -> str:
    """SHA-256 over the reduced metric files (sorted), recorded before development."""
    digest = hashlib.sha256()
    files = sorted((out_dir / "metrics").glob("*.csv"))
    for path in files:
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    value = digest.hexdigest()
    (out_dir / "metrics-manifest.json").write_text(
        json.dumps({"files": len(files), "sha256": value}, indent=1) + "\n"
    )
    return value
