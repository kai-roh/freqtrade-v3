#!/usr/bin/env python3
"""Create the seven-field run manifest and reject dirty deployments by default."""

from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from v3.reproducibility import (  # noqa: E402
    NO_MODEL_ARTIFACT_SHA256,
    RunManifest,
    TimeRange,
    data_snapshot_id,
    dependency_lock_is_exact,
    sha256_file,
    write_manifest,
)


def _datetime(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("timestamp must be ISO-8601") from exc


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--container-image-digest", required=True)
    parser.add_argument("--dependency-lock", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    model = parser.add_mutually_exclusive_group(required=True)
    model.add_argument("--model-artifact", type=Path)
    model.add_argument("--no-model", action="store_true")
    parser.add_argument("--data", type=Path, action="append", required=True)
    parser.add_argument("--data-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--timerange-start", type=_datetime, required=True)
    parser.add_argument("--timerange-end", type=_datetime, required=True)
    parser.add_argument("--generated-at", type=_datetime, default=datetime.now(UTC))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--allow-dirty", action="store_true")
    parser.add_argument("--allow-unlocked-dependencies", action="store_true")
    return parser.parse_args()


def _git(*args: str) -> str:
    result = subprocess.run(
        ("git", *args),
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def main() -> int:
    args = parse_args()
    try:
        git_sha = _git("rev-parse", "HEAD")
        dirty = bool(_git("status", "--porcelain"))
        manifest = RunManifest(
            git_commit_sha=git_sha,
            container_image_digest=args.container_image_digest,
            dependency_lock_sha256=sha256_file(args.dependency_lock),
            config_sha256=sha256_file(args.config),
            model_artifact_sha256=(
                NO_MODEL_ARTIFACT_SHA256 if args.no_model else sha256_file(args.model_artifact)
            ),
            data_snapshot_id=data_snapshot_id(args.data, root=args.data_root),
            timerange=TimeRange(args.timerange_start, args.timerange_end),
            generated_at=args.generated_at,
            source_dirty=dirty,
            dependencies_exact=dependency_lock_is_exact(args.dependency_lock),
        )
        if manifest.source_dirty and not args.allow_dirty:
            raise ValueError("dirty source tree is not deployable")
        if not manifest.dependencies_exact and not args.allow_unlocked_dependencies:
            raise ValueError("unlocked dependencies are not deployable")
        write_manifest(args.output, manifest)
    except (OSError, subprocess.CalledProcessError, TypeError, ValueError) as exc:
        print(f"manifest failed: {exc}", file=sys.stderr)
        return 2
    print(f"manifest_id={manifest.manifest_id}")
    print(f"manifest={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
