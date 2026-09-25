"""Phase 2 research panel: hourly perp prices, mark prices, and funding settlements.

Loads the frozen dataset described by evidence/phase2/data-manifest.json and
fails closed when a file hash differs from the manifest. No exchange access.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from .implementability import UNIVERSE


@dataclass(frozen=True)
class Phase2Panel:
    open: pd.DataFrame  # hourly open per symbol
    close: pd.DataFrame  # hourly close per symbol
    mark: pd.DataFrame  # hourly mark close per symbol
    funding: pd.DataFrame  # settlement-indexed funding rate per symbol
    symbols: tuple[str, ...]

    def __post_init__(self) -> None:
        for name in ("open", "close", "mark"):
            frame = getattr(self, name)
            if not isinstance(frame.index, pd.DatetimeIndex) or frame.index.tz is None:
                raise ValueError(f"{name} must have a tz-aware DatetimeIndex")
            if not frame.index.is_monotonic_increasing or frame.index.has_duplicates:
                raise ValueError(f"{name} index must be sorted and unique")
            if tuple(frame.columns) != self.symbols:
                raise ValueError(f"{name} columns must equal the panel symbols")
        if not self.open.index.equals(self.close.index) or not self.open.index.equals(
            self.mark.index
        ):
            raise ValueError("open, close, and mark must share one hourly index")
        if tuple(self.funding.columns) != self.symbols:
            raise ValueError("funding columns must equal the panel symbols")
        if not self.funding.index.isin(self.open.index).all():
            raise ValueError("every funding settlement must fall on an hourly boundary")

    @property
    def settlement_index(self) -> pd.DatetimeIndex:
        return self.funding.index


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read(path: Path, column: str) -> pd.Series:
    frame = pd.read_feather(path)
    index = pd.to_datetime(frame["date"], utc=True)
    series = pd.Series(frame[column].astype(float).to_numpy(), index=index).sort_index()
    if series.index.has_duplicates:
        raise ValueError(f"duplicate timestamps in {path.name}")
    return series


def load_phase2_panel(
    data_dir: Path,
    *,
    manifest_path: Path | None = None,
    symbols: tuple[str, ...] = UNIVERSE,
) -> Phase2Panel:
    manifest = json.loads(manifest_path.read_text())["files"] if manifest_path else None
    opens, closes, marks, fundings = {}, {}, {}, {}
    for base in symbols:
        slug = f"{base}_USDT_USDT-1h"
        paths = {
            kind: data_dir / f"{slug}-{kind}.feather"
            for kind in ("futures", "funding_rate", "mark")
        }
        for kind, path in paths.items():
            if not path.is_file():
                raise FileNotFoundError(path)
            if manifest is not None:
                recorded = manifest.get(f"{base}/{kind}", {}).get("sha256")
                if recorded != _sha256(path):
                    raise ValueError(f"{path.name} differs from the frozen manifest")
        opens[base] = _read(paths["futures"], "open")
        closes[base] = _read(paths["futures"], "close")
        marks[base] = _read(paths["mark"], "close")
        fundings[base] = _read(paths["funding_rate"], "open")
    open_frame = pd.DataFrame(opens).dropna(how="any")
    close_frame = pd.DataFrame(closes).loc[open_frame.index]
    mark_frame = pd.DataFrame(marks).loc[open_frame.index]
    funding_frame = pd.DataFrame(fundings).dropna(how="any")
    funding_frame = funding_frame.loc[funding_frame.index.isin(open_frame.index)]
    return Phase2Panel(
        open=open_frame[list(symbols)],
        close=close_frame[list(symbols)],
        mark=mark_frame[list(symbols)],
        funding=funding_frame[list(symbols)],
        symbols=tuple(symbols),
    )
