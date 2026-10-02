#!/usr/bin/env python3
"""Freeze the Phase 2c dataset: BTC and ETH perpetual 1h candles, funding, mark to the cutoff.

Registration: docs/PHASE2C_PREREGISTRATION.md §4. The whole span is development
data. Rows after the cutoff are dropped; the manifest records sha256, rows,
span, hourly coverage, and settlement intervals per file.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.build_phase2_data_manifest import describe  # noqa: E402

SYMBOLS = ("BTC", "ETH")
KINDS = ("futures", "funding_rate", "mark")
# market -> (file name pattern, kinds, default raw dir, default output dir, default manifest)
MARKETS = {
    "perp": (
        "{symbol}_USDT_USDT-1h-{kind}.feather",
        KINDS,
        "user_data/data-phase2c/raw",
        "user_data/data-phase2c/binance/futures",
        "evidence/phase2c/data-manifest.json",
    ),
    "spot": (
        "{symbol}_USDT-1h.feather",
        ("spot",),
        "user_data/data-phase2c/spot-raw",
        "user_data/data-phase2c/binance/spot",
        "evidence/phase2c/spot-data-manifest.json",
    ),
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--market", choices=sorted(MARKETS), default="perp")
    parser.add_argument("--raw-dir", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--start", default="2020-01-01T00:00:00+00:00")
    parser.add_argument("--cutoff", default="2026-10-01T23:00:00+00:00")
    args = parser.parse_args()
    pattern, kinds, raw_dir, output_dir, manifest_path = MARKETS[args.market]
    raw_dir = args.raw_dir or Path(raw_dir)
    output_dir = args.output_dir or Path(output_dir)
    manifest_path = args.manifest or Path(manifest_path)
    start, cutoff = pd.Timestamp(args.start), pd.Timestamp(args.cutoff)
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "registration": "docs/PHASE2C_PREREGISTRATION.md",
        "market": args.market,
        "timeframe": "1h",
        "start": start.isoformat(),
        "cutoff": cutoff.isoformat(),
        "development_only": True,
        "files": {},
        "missing": [],
    }
    for symbol in SYMBOLS:
        for kind in kinds:
            name = pattern.format(symbol=symbol, kind=kind)
            raw = raw_dir / name
            if not raw.is_file():
                manifest["missing"].append(f"{symbol}/{kind}")
                continue
            frame = pd.read_feather(raw)
            dates = pd.to_datetime(frame["date"], utc=True)
            frame = frame[(dates >= start) & (dates <= cutoff)].reset_index(drop=True)
            out = output_dir / name
            frame.to_feather(out)
            # Spot candles are described like futures candles (hourly coverage).
            manifest["files"][f"{symbol}/{kind}"] = describe(
                out, "futures" if kind == "spot" else kind
            )
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"files": len(manifest["files"]), "missing": manifest["missing"]}))
    return 0 if not manifest["missing"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
