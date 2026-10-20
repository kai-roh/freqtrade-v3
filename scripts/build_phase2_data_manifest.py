#!/usr/bin/env python3
"""Freeze the Phase 2 research data: sha256, rows, span, coverage, funding interval per file."""

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from v3.phase2.implementability import UNIVERSE  # noqa: E402


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def describe(path: Path, kind: str) -> dict:
    frame = pd.read_feather(path)
    dates = pd.to_datetime(frame["date"], utc=True).sort_values()
    entry = {
        "sha256": sha256(path),
        "rows": int(len(frame)),
        "start": dates.iloc[0].isoformat(),
        "end": dates.iloc[-1].isoformat(),
    }
    if kind == "futures":
        expected = int((dates.iloc[-1] - dates.iloc[0]) / pd.Timedelta(hours=1)) + 1
        entry["coverage"] = round(len(frame) / expected, 6) if expected else None
    if kind == "funding_rate":
        gaps = dates.diff().dropna()
        mode = gaps.mode()
        entry["settlement_interval_minutes"] = (
            int(mode.iloc[0].total_seconds() // 60) if not mode.empty else None
        )
        entry["distinct_intervals_minutes"] = sorted(
            {int(g.total_seconds() // 60) for g in gaps.unique()}
        )[:8]
    return entry


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-dir", type=Path, default=Path("user_data/data-phase2/binance/futures")
    )
    parser.add_argument("--output", type=Path, default=Path("evidence/phase2/data-manifest.json"))
    parser.add_argument("--days", type=int, default=450)
    args = parser.parse_args()
    manifest = {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "requested_days": args.days,
        "timeframe": "1h",
        "files": {},
        "missing": [],
    }
    for base in UNIVERSE:
        slug = f"{base}_USDT_USDT"
        for kind in ("futures", "funding_rate", "mark"):
            path = args.data_dir / f"{slug}-1h-{kind}.feather"
            key = f"{base}/{kind}"
            if not path.is_file():
                manifest["missing"].append(key)
                continue
            manifest["files"][key] = describe(path, kind)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"files": len(manifest["files"]), "missing": manifest["missing"]}))
    return 0 if not manifest["missing"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
