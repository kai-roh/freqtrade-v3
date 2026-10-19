#!/usr/bin/env python3
"""Download checksum-verified public USD-M minute data into an isolated directory.

Source schema/checksums: https://github.com/binance/binance-public-data
No credentials, exchange accounts, orders, or server changes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
BASE = "https://data.binance.vision/data/futures/um/monthly/klines"
SYMBOLS = ("BTC", "ETH")
MONTHS = tuple(pd.date_range("2025-09-01", "2026-09-01", freq="MS").strftime("%Y-%m"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(url: str, path: Path) -> None:
    temporary = path.with_suffix(path.suffix + ".partial")
    try:
        subprocess.run(
            [
                "curl",
                "--fail",
                "--location",
                "--silent",
                "--show-error",
                "--retry",
                "3",
                "--connect-timeout",
                "15",
                "--max-time",
                "180",
                url,
                "--output",
                str(temporary),
            ],
            check=True,
        )
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def fetch(task: tuple[str, str, Path]) -> dict:
    symbol, month, directory = task
    name = f"{symbol}USDT-1m-{month}.zip"
    path = directory / name
    url = f"{BASE}/{symbol}USDT/1m/{name}"
    checksum = path.with_suffix(".zip.CHECKSUM")
    if not checksum.exists():
        download(url + ".CHECKSUM", checksum)
    expected = checksum.read_text().split()[0]
    if len(expected) != 64:
        raise ValueError(f"invalid checksum: {checksum}")
    if not path.exists():
        download(url, path)
    actual = sha256(path)
    if actual != expected:
        raise ValueError(f"checksum mismatch (remove corrupt local archive to retry): {path}")
    return {
        "symbol": symbol,
        "month": month,
        "url": url,
        "sha256": actual,
        "bytes": path.stat().st_size,
        "file": str(path),
    }


def validate_bars(frame: pd.DataFrame, start: str, end: str) -> None:
    expected = pd.date_range(start, end, inclusive="left", freq="1min", tz="UTC")
    dates = pd.DatetimeIndex(frame["date"])
    if not dates.as_unit("ns").equals(expected.as_unit("ns")):
        raise ValueError(f"minute cadence mismatch: {len(dates)} vs {len(expected)} expected")
    values = frame[["open", "high", "low", "close", "volume"]]
    if not np.isfinite(values.to_numpy()).all():
        raise ValueError("nonfinite OHLCV")
    if (values[["open", "high", "low", "close"]] <= 0).any().any():
        raise ValueError("nonpositive price")
    if (values.volume < 0).any():
        raise ValueError("negative volume")
    if (
        (values.high < values[["open", "close", "low"]].max(axis=1))
        | (values.low > values[["open", "close", "high"]].min(axis=1))
    ).any():
        raise ValueError("invalid OHLC ordering")


def read_archive(path: Path) -> pd.DataFrame:
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != 1 or not names[0].endswith(".csv"):
            raise ValueError(f"unexpected archive members: {path}")
        with archive.open(names[0]) as stream:
            raw = pd.read_csv(stream, header=None, usecols=range(6), dtype=str)
    # Official futures monthly CSVs can carry a header; allow exactly that header.
    if raw.iloc[0, 0] == "open_time":
        raw = raw.iloc[1:].reset_index(drop=True)
    raw.columns = ["date", "open", "high", "low", "close", "volume"]
    timestamp = pd.to_numeric(raw.date, errors="raise")
    if timestamp.max() >= 10**14:
        raise ValueError("unexpected futures timestamp unit (expected milliseconds)")
    raw["date"] = pd.to_datetime(timestamp, unit="ms", utc=True)
    for column in raw.columns[1:]:
        raw[column] = pd.to_numeric(raw[column], errors="raise").astype(float)
    return raw


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=ROOT / "user_data/data-divergence")
    parser.add_argument(
        "--manifest", type=Path, default=ROOT / "evidence/divergence/data-manifest.json"
    )
    args = parser.parse_args()
    archive_dir = args.data_dir / "archives"
    archive_dir.mkdir(parents=True, exist_ok=True)
    tasks = [(symbol, month, archive_dir) for symbol in SYMBOLS for month in MONTHS]
    with ThreadPoolExecutor(max_workers=4) as executor:
        archives = list(executor.map(fetch, tasks))
    manifest = {
        "generated_at": datetime.now(UTC).isoformat(),
        "registration": "docs/DIVERGENCE_PREREGISTRATION.md",
        "registration_sha256": sha256(ROOT / "docs/DIVERGENCE_PREREGISTRATION.md"),
        "development_only": True,
        "start": "2025-10-01T00:00:00+00:00",
        "end_exclusive": "2026-10-01T00:00:00+00:00",
        "archives": [],
        "files": {},
    }
    for row in archives:
        manifest["archives"].append({key: value for key, value in row.items() if key != "file"})
    for symbol in SYMBOLS:
        frame = pd.concat(
            [read_archive(Path(row["file"])) for row in archives if row["symbol"] == symbol],
            ignore_index=True,
        )
        validate_bars(frame, "2025-09-01", "2026-10-01")
        out = args.data_dir / f"{symbol}-1m.feather"
        frame.to_feather(out)
        manifest["files"][f"{symbol}/bars"] = {
            "path": str(out.relative_to(ROOT)),
            "sha256": sha256(out),
            "rows": len(frame),
            "first": frame.date.iloc[0].isoformat(),
            "last": frame.date.iloc[-1].isoformat(),
            "missing_minutes": 0,
        }
        # Preserve frozen Phase 2c funding and mark bytes rather than requesting account data.
        for kind in ("funding_rate", "mark"):
            source = (
                ROOT
                / "user_data/data-phase2c/binance/futures"
                / f"{symbol}_USDT_USDT-1h-{kind}.feather"
            )
            values = pd.read_feather(source)
            dates = pd.DatetimeIndex(pd.to_datetime(values.date, utc=True))
            if dates.has_duplicates or not dates.is_monotonic_increasing:
                raise ValueError(f"invalid {kind} timestamps")
            expected = pd.date_range(
                "2025-09-01",
                "2026-10-01",
                inclusive="left",
                freq="8h" if kind == "funding_rate" else "1h",
                tz="UTC",
            )
            if not expected.isin(dates).all():
                raise ValueError(f"missing frozen {kind} rows for {symbol}")
            target = args.data_dir / f"{symbol}-{kind}.feather"
            target.write_bytes(source.read_bytes())
            manifest["files"][f"{symbol}/{kind}"] = {
                "path": str(target.relative_to(ROOT)),
                "sha256": sha256(target),
                "source": str(source.relative_to(ROOT)),
                "rows": len(values),
            }
        print(json.dumps({"symbol": symbol, "rows": len(frame), "sha256": sha256(out)}), flush=True)
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
