#!/usr/bin/env python3
"""Freeze the Phase 2b dataset: the frozen Phase 2 panel plus rows up to the cutoff.

Registration (docs/PHASE2B_PREREGISTRATION.md §5): the Phase 2 panel is reused
only if every file still matches evidence/phase2/data-manifest.json. Rows after
the last frozen timestamp are appended from a fresh download, truncated at the
cutoff. Frozen rows are never replaced; where the fresh download overlaps them,
differences are measured and recorded but the frozen values are kept.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.build_phase2_data_manifest import describe, sha256  # noqa: E402
from v3.phase2.implementability import UNIVERSE  # noqa: E402

KINDS = ("futures", "funding_rate", "mark")
VALUE_COLUMNS = ("open", "high", "low", "close", "volume")


def _overlap(frozen: pd.DataFrame, fresh: pd.DataFrame) -> dict:
    merged = frozen.merge(fresh, on="date", how="left", suffixes=("_frozen", "_fresh"))
    missing = int(merged["open_fresh"].isna().sum())
    diffs = {}
    differing_rows = pd.Series(False, index=merged.index)
    for column in VALUE_COLUMNS:
        a, b = merged[f"{column}_frozen"], merged[f"{column}_fresh"]
        delta = (a - b).abs()
        differing_rows |= delta.fillna(0) > 0
        diffs[column] = float(delta.max()) if delta.notna().any() else None
    return {
        "rows_compared": int(len(merged)),
        "rows_missing_in_fresh": missing,
        "rows_differing": int(differing_rows.sum()),
        "max_abs_diff": diffs,
    }


def build(frozen_dir: Path, frozen_manifest: Path, raw_dir: Path, out_dir: Path, cutoff) -> dict:
    manifest = json.loads(frozen_manifest.read_text())
    mismatched = []
    for key, entry in manifest["files"].items():
        base, kind = key.split("/")
        path = frozen_dir / f"{base}_USDT_USDT-1h-{kind}.feather"
        if not path.is_file() or sha256(path) != entry["sha256"]:
            mismatched.append(key)
    if mismatched:
        raise SystemExit(f"frozen Phase 2 panel changed; refusing to build: {mismatched}")
    out_dir.mkdir(parents=True, exist_ok=True)
    result = {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "registration": "docs/PHASE2B_PREREGISTRATION.md",
        "timeframe": "1h",
        "cutoff": cutoff.isoformat(),
        "frozen_manifest": str(frozen_manifest),
        "frozen_manifest_sha256": hashlib.sha256(frozen_manifest.read_bytes()).hexdigest(),
        "frozen_files_verified": len(manifest["files"]),
        "files": {},
        "overlap_check": {},
        "missing": [],
    }
    for base in UNIVERSE:
        slug = f"{base}_USDT_USDT"
        for kind in KINDS:
            key = f"{base}/{kind}"
            frozen_path = frozen_dir / f"{slug}-1h-{kind}.feather"
            raw_path = raw_dir / f"{slug}-1h-{kind}.feather"
            if not raw_path.is_file():
                result["missing"].append(key)
                continue
            frozen = pd.read_feather(frozen_path)
            fresh = pd.read_feather(raw_path)
            frozen["date"] = pd.to_datetime(frozen["date"], utc=True)
            fresh["date"] = pd.to_datetime(fresh["date"], utc=True)
            result["overlap_check"][key] = _overlap(frozen, fresh)
            tail = fresh[(fresh["date"] > frozen["date"].max()) & (fresh["date"] <= cutoff)]
            combined = pd.concat([frozen, tail[frozen.columns]], ignore_index=True)
            combined = combined.sort_values("date").reset_index(drop=True)
            if combined["date"].duplicated().any():
                raise SystemExit(f"duplicate timestamps after splice: {key}")
            out_path = out_dir / f"{slug}-1h-{kind}.feather"
            combined.to_feather(out_path)
            entry = describe(out_path, kind)
            entry["frozen_rows"] = int(len(frozen))
            entry["appended_rows"] = int(len(tail))
            result["files"][key] = entry
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--frozen-dir", type=Path, default=Path("user_data/data-phase2/binance/futures")
    )
    parser.add_argument(
        "--frozen-manifest", type=Path, default=Path("evidence/phase2/data-manifest.json")
    )
    parser.add_argument("--raw-dir", type=Path, default=Path("user_data/data-phase2b/raw"))
    parser.add_argument(
        "--output-dir", type=Path, default=Path("user_data/data-phase2b/binance/futures")
    )
    parser.add_argument(
        "--manifest", type=Path, default=Path("evidence/phase2b/data-manifest.json")
    )
    parser.add_argument("--cutoff", default="2026-10-01T23:00:00+00:00")
    args = parser.parse_args()
    cutoff = pd.Timestamp(args.cutoff)
    if cutoff.tzinfo is None:
        raise SystemExit("cutoff must be timezone-aware")
    result = build(args.frozen_dir, args.frozen_manifest, args.raw_dir, args.output_dir, cutoff)
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    differing = {
        k: v["rows_differing"] for k, v in result["overlap_check"].items() if v["rows_differing"]
    }
    print(
        json.dumps(
            {
                "files": len(result["files"]),
                "missing": result["missing"],
                "overlap_rows_differing": differing,
            }
        )
    )
    return 0 if not result["missing"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
