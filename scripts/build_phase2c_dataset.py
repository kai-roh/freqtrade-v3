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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path, default=Path("user_data/data-phase2c/raw"))
    parser.add_argument(
        "--output-dir", type=Path, default=Path("user_data/data-phase2c/binance/futures")
    )
    parser.add_argument(
        "--manifest", type=Path, default=Path("evidence/phase2c/data-manifest.json")
    )
    parser.add_argument("--start", default="2020-01-01T00:00:00+00:00")
    parser.add_argument("--cutoff", default="2026-10-01T23:00:00+00:00")
    args = parser.parse_args()
    start, cutoff = pd.Timestamp(args.start), pd.Timestamp(args.cutoff)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "registration": "docs/PHASE2C_PREREGISTRATION.md",
        "timeframe": "1h",
        "start": start.isoformat(),
        "cutoff": cutoff.isoformat(),
        "development_only": True,
        "files": {},
        "missing": [],
    }
    for symbol in SYMBOLS:
        for kind in KINDS:
            name = f"{symbol}_USDT_USDT-1h-{kind}.feather"
            raw = args.raw_dir / name
            if not raw.is_file():
                manifest["missing"].append(f"{symbol}/{kind}")
                continue
            frame = pd.read_feather(raw)
            dates = pd.to_datetime(frame["date"], utc=True)
            frame = frame[(dates >= start) & (dates <= cutoff)].reset_index(drop=True)
            out = args.output_dir / name
            frame.to_feather(out)
            manifest["files"][f"{symbol}/{kind}"] = describe(out, kind)
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"files": len(manifest["files"]), "missing": manifest["missing"]}))
    return 0 if not manifest["missing"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
