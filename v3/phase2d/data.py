"""Phase 2d data: daily Binance candles for every USDT pair, delisted ones included.

Source: the public bulk archive (data.binance.vision), monthly 1d kline files for spot
and USD-M perpetuals, plus monthly funding-rate files for perpetuals. Delisted
symbols stay in the archive, so the universe can be built point in time without
survivorship bias.

Spot files from 2025 onward carry microsecond timestamps; everything is normalized
to UTC day starts.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import ssl
import time
import urllib.error
import urllib.request
import zipfile
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

ARCHIVE = "https://data.binance.vision"
LISTING = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision"
MARKETS = {"spot": "data/spot/monthly/klines", "um": "data/futures/um/monthly/klines"}
FUNDING = "data/futures/um/monthly/fundingRate"
KLINE_COLUMNS = (
    "open_time",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "close_time",
    "quote_volume",
    "trades",
    "taker_base",
    "taker_quote",
    "ignore",
)
# Not tradable risk assets: stablecoins, fiat, wrapped/pegged tokens, leveraged tokens.
EXCLUDED_BASES = frozenset(
    {
        "USDC", "BUSD", "TUSD", "USDP", "PAX", "DAI", "FDUSD", "USDS", "USDSB", "SUSD",
        "UST", "USTC", "USDD", "AEUR", "EURI", "EUR", "GBP", "AUD", "TRY", "BRL", "RUB",
        "UAH", "NGN", "ZAR", "IDRT", "BIDR", "BKRW", "PAXG", "WBTC", "WBETH", "BETH",
        "XUSD", "USD1", "BFUSD", "RLUSD", "USDE", "PYUSD",
    }
)  # fmt: skip
LEVERAGED = re.compile(r"(UP|DOWN|BULL|BEAR)USDT$")


def _context() -> ssl.SSLContext:
    for path in ("/etc/ssl/cert.pem", "/etc/ssl/certs/ca-certificates.crt"):
        if Path(path).is_file():
            return ssl.create_default_context(cafile=path)
    return ssl.create_default_context()


_SSL = _context()


def _get(url: str, retries: int = 4) -> bytes | None:
    """GET with retries; ``None`` for a missing object (404)."""
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(url, timeout=60, context=_SSL) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return None
            if attempt + 1 == retries:
                raise
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            if attempt + 1 == retries:
                raise
        time.sleep(1.5 * (attempt + 1))
    return None


def _listing(prefix: str) -> tuple[list[str], list[str]]:
    """Common prefixes (sub-folders) and object keys under ``prefix``."""
    folders: list[str] = []
    keys: list[str] = []
    marker = ""
    while True:
        url = f"{LISTING}?delimiter=/&prefix={prefix}"
        if marker:
            url += f"&marker={marker}"
        body = (_get(url) or b"").decode()
        page_folders = [p for p in re.findall(r"<Prefix>([^<]+)</Prefix>", body) if p != prefix]
        page_keys = re.findall(r"<Key>([^<]+)</Key>", body)
        folders += page_folders
        keys += page_keys
        if "<IsTruncated>true</IsTruncated>" not in body:
            return folders, keys
        nxt = re.findall(r"<NextMarker>([^<]+)</NextMarker>", body)
        marker = nxt[0] if nxt else (page_folders or page_keys)[-1]


def eligible_symbol(symbol: str) -> bool:
    if not (symbol.isascii() and symbol.isalnum()):
        return False
    if not symbol.endswith("USDT") or LEVERAGED.search(symbol):
        return False
    base = symbol[: -len("USDT")]
    return bool(base) and base not in EXCLUDED_BASES


def list_symbols(market: str) -> list[str]:
    folders, _ = _listing(MARKETS[market] + "/")
    symbols = [f.rstrip("/").split("/")[-1] for f in folders]
    return sorted(s for s in symbols if eligible_symbol(s))


def _months(start: str, end: str) -> list[str]:
    return [p.strftime("%Y-%m") for p in pd.period_range(start, end, freq="M")]


def _parse_klines(raw: bytes, extra: tuple[str, ...] = ()) -> pd.DataFrame:
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        text = archive.read(archive.namelist()[0])
    frame = pd.read_csv(io.BytesIO(text), header=None)
    if not str(frame.iloc[0, 0]).isdigit():  # some files carry a header row
        frame = frame.iloc[1:]
    frame = frame.iloc[:, : len(KLINE_COLUMNS)]
    frame.columns = KLINE_COLUMNS[: frame.shape[1]]
    ts = frame["open_time"].astype("int64")
    ts = np.where(ts > 10**14, ts // 1000, ts)  # microseconds (spot, 2025+)
    out = pd.DataFrame(
        {
            c: frame[c].astype(float)
            for c in ("open", "high", "low", "close", "quote_volume", *extra)
        }
    )
    out.index = pd.to_datetime(ts, unit="ms", utc=True).normalize()
    return out[~out.index.duplicated(keep="last")]


def _parse_funding(raw: bytes) -> pd.Series:
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        text = archive.read(archive.namelist()[0])
    frame = pd.read_csv(io.BytesIO(text))
    time_col = "calc_time" if "calc_time" in frame.columns else frame.columns[0]
    rate_col = "last_funding_rate" if "last_funding_rate" in frame.columns else frame.columns[-1]
    ts = frame[time_col].astype("int64")
    ts = np.where(ts > 10**14, ts // 1000, ts)
    series = pd.Series(
        frame[rate_col].astype(float).to_numpy(), index=pd.to_datetime(ts, unit="ms", utc=True)
    )
    return series.sort_index()


@dataclass(frozen=True)
class DownloadPlan:
    market: str
    start: str  # YYYY-MM
    end: str  # YYYY-MM, last full month


def _symbol_months(market: str, symbol: str, kind: str = "klines") -> list[str]:
    prefix = f"{MARKETS[market]}/{symbol}/1d/" if kind == "klines" else f"{FUNDING}/{symbol}/"
    _, keys = _listing(prefix)
    found = re.findall(r"-(\d{4}-\d{2})\.zip$", "\n".join(keys), flags=re.M)
    return sorted(set(found))


def download_market(plan: DownloadPlan, out_dir: Path, workers: int = 16) -> dict[str, object]:
    """Fetch every eligible symbol's monthly 1d klines (and funding for USD-M) into ``out_dir``.

    Raw zips are cached under ``out_dir/raw`` so reruns only fetch what is missing.
    Returns the manifest (symbol list and SHA-256 of every raw file).
    """
    raw_dir = out_dir / "raw" / plan.market
    raw_dir.mkdir(parents=True, exist_ok=True)
    symbols = list_symbols(plan.market)
    wanted = set(_months(plan.start, plan.end))

    def fetch_symbol(symbol: str) -> list[tuple[str, str]]:
        files = []
        kinds = ["klines"] + (["funding"] if plan.market == "um" else [])
        for kind in kinds:
            for month in _symbol_months(plan.market, symbol, kind):
                if month not in wanted:
                    continue
                name = f"{symbol}-{'1d' if kind == 'klines' else 'fundingRate'}-{month}.zip"
                path = raw_dir / kind / name
                if not path.is_file():
                    base = (
                        MARKETS[plan.market] + f"/{symbol}/1d"
                        if kind == "klines"
                        else f"{FUNDING}/{symbol}"
                    )
                    data = _get(f"{ARCHIVE}/{base}/{name}")
                    if data is None:
                        continue
                    path.parent.mkdir(parents=True, exist_ok=True)
                    tmp = path.with_suffix(".part")
                    tmp.write_bytes(data)
                    tmp.replace(path)
                files.append((f"{kind}/{name}", hashlib.sha256(path.read_bytes()).hexdigest()))
        return files

    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(fetch_symbol, symbols))
    manifest = {
        "market": plan.market,
        "start": plan.start,
        "end": plan.end,
        "symbols": symbols,
        "files": dict(sorted(item for files in results for item in files)),
    }
    (out_dir / f"manifest-{plan.market}.json").write_text(json.dumps(manifest, indent=1) + "\n")
    return manifest


@dataclass(frozen=True)
class DailyPanel:
    """Wide daily panels (index: UTC day, columns: symbol)."""

    open: pd.DataFrame
    close: pd.DataFrame
    quote_volume: pd.DataFrame
    funding: pd.DataFrame | None = None  # daily sum of funding rates (perpetuals)

    @property
    def symbols(self) -> list[str]:
        return list(self.close.columns)


def build_panel(out_dir: Path, market: str, symbols: Iterable[str] | None = None) -> DailyPanel:
    """Assemble wide panels from the cached raw zips."""
    raw_dir = out_dir / "raw" / market
    frames: dict[str, list[pd.DataFrame]] = {}
    for path in sorted((raw_dir / "klines").glob("*.zip")):
        symbol = path.name.split("-1d-")[0]
        if symbols is not None and symbol not in symbols:
            continue
        frames.setdefault(symbol, []).append(_parse_klines(path.read_bytes()))
    data = {s: pd.concat(f).sort_index() for s, f in frames.items()}
    data = {s: d[~d.index.duplicated(keep="last")] for s, d in data.items()}
    panel = {
        field: pd.DataFrame({s: d[field] for s, d in data.items()}).sort_index()
        for field in ("open", "close", "quote_volume")
    }
    funding = None
    if market == "um":
        series = {}
        for path in sorted((raw_dir / "funding").glob("*.zip")):
            symbol = path.name.split("-fundingRate-")[0]
            if symbol in data:
                series.setdefault(symbol, []).append(_parse_funding(path.read_bytes()))
        daily = {s: pd.concat(v).groupby(lambda t: t.normalize()).sum() for s, v in series.items()}
        funding = pd.DataFrame(daily).reindex(panel["close"].index).fillna(0.0)
    full = pd.date_range(panel["close"].index.min(), panel["close"].index.max(), freq="D")
    return DailyPanel(
        open=panel["open"].reindex(full),
        close=panel["close"].reindex(full),
        quote_volume=panel["quote_volume"].reindex(full),
        funding=None if funding is None else funding.reindex(full).fillna(0.0),
    )


def save_panel(panel: DailyPanel, path: Path) -> str:
    """Write the panel as one long Parquet-free CSV.gz (portable); returns its SHA-256."""
    long = pd.concat(
        {
            "open": panel.open.stack(),
            "close": panel.close.stack(),
            "quote_volume": panel.quote_volume.stack(),
            **({"funding": panel.funding.stack()} if panel.funding is not None else {}),
        },
        axis=1,
    )
    long.index.names = ["day", "symbol"]
    path.parent.mkdir(parents=True, exist_ok=True)
    long.to_csv(path, compression={"method": "gzip", "mtime": 0}, float_format="%.10g")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_panel(path: Path) -> DailyPanel:
    long = pd.read_csv(path, parse_dates=["day"]).set_index(["day", "symbol"]).astype(float)
    days = pd.DatetimeIndex(long.index.levels[0])
    days = days.tz_convert("UTC") if days.tz is not None else days.tz_localize("UTC")
    long.index = long.index.set_levels(days, level=0)
    wide = {c: long[c].unstack("symbol").sort_index() for c in long.columns}
    full = pd.date_range(wide["close"].index.min(), wide["close"].index.max(), freq="D")
    return DailyPanel(
        open=wide["open"].reindex(full),
        close=wide["close"].reindex(full),
        quote_volume=wide["quote_volume"].reindex(full),
        funding=wide["funding"].reindex(full).fillna(0.0) if "funding" in wide else None,
    )
