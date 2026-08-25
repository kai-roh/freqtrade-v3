"""Run-level reproducibility metadata required by the Phase 0 gate."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
GIT_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}([0-9a-f]{24})?$")
NO_MODEL_ARTIFACT_SHA256 = hashlib.sha256(b"freqtrade-v3:no-model").hexdigest()


def sha256_file(path: Path) -> str:
    if not path.is_file():
        raise FileNotFoundError(path)
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _utc(value: datetime, *, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must include a timezone")
    return value.astimezone(UTC)


def _timestamp(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _require_sha256(value: str, field_name: str) -> None:
    if not SHA256_PATTERN.fullmatch(value):
        raise ValueError(f"{field_name} must be a lowercase SHA-256 hex digest")


@dataclass(frozen=True)
class TimeRange:
    start: datetime
    end: datetime

    def __post_init__(self) -> None:
        start = _utc(self.start, field_name="timerange.start")
        end = _utc(self.end, field_name="timerange.end")
        if start >= end:
            raise ValueError("timerange.start must be before timerange.end")
        object.__setattr__(self, "start", start)
        object.__setattr__(self, "end", end)

    def to_dict(self) -> dict[str, str]:
        return {"start": _timestamp(self.start), "end": _timestamp(self.end)}


@dataclass(frozen=True)
class RunManifest:
    """The seven mandatory identifiers for every promoted research or deployment run."""

    git_commit_sha: str
    container_image_digest: str
    dependency_lock_sha256: str
    config_sha256: str
    model_artifact_sha256: str
    data_snapshot_id: str
    timerange: TimeRange
    generated_at: datetime
    source_dirty: bool = False
    dependencies_exact: bool = True

    def __post_init__(self) -> None:
        if not GIT_SHA_PATTERN.fullmatch(self.git_commit_sha):
            raise ValueError("git_commit_sha must be a lowercase 40- or 64-character Git hash")
        if not self.container_image_digest.startswith("sha256:"):
            raise ValueError("container_image_digest must start with sha256:")
        _require_sha256(self.container_image_digest.removeprefix("sha256:"), "container digest")
        _require_sha256(self.dependency_lock_sha256, "dependency_lock_sha256")
        _require_sha256(self.config_sha256, "config_sha256")
        _require_sha256(self.model_artifact_sha256, "model_artifact_sha256")
        if not self.data_snapshot_id.strip():
            raise ValueError("data_snapshot_id is required")
        object.__setattr__(self, "generated_at", _utc(self.generated_at, field_name="generated_at"))

    def required_metadata(self) -> dict[str, Any]:
        return {
            "git_commit_sha": self.git_commit_sha,
            "container_image_digest": self.container_image_digest,
            "dependency_lock_sha256": self.dependency_lock_sha256,
            "config_sha256": self.config_sha256,
            "model_artifact_sha256": self.model_artifact_sha256,
            "data_snapshot_id": self.data_snapshot_id,
            "timerange": self.timerange.to_dict(),
        }

    @property
    def manifest_id(self) -> str:
        encoded = json.dumps(
            self.required_metadata(), sort_keys=True, separators=(",", ":")
        ).encode()
        return hashlib.sha256(encoded).hexdigest()

    def assert_deployable(self) -> None:
        if self.source_dirty:
            raise ValueError("dirty source tree is not deployable")
        if not self.dependencies_exact:
            raise ValueError("unlocked dependencies are not deployable")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "manifest_id": self.manifest_id,
            "generated_at": _timestamp(self.generated_at),
            "source_dirty": self.source_dirty,
            "dependencies_exact": self.dependencies_exact,
            **self.required_metadata(),
        }


def dependency_lock_is_exact(path: Path) -> bool:
    """Recognize resolved lock formats or exact ``package==version`` requirements."""

    if not path.is_file() or path.stat().st_size == 0:
        return False
    if path.name in {"uv.lock", "poetry.lock", "Pipfile.lock"}:
        return True
    requirement_lines = []
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or line.startswith("--hash="):
            continue
        if line.startswith("-") or " @ " in line:
            return False
        requirement_lines.append(line.removesuffix("\\").strip())
    return bool(requirement_lines) and all("==" in line for line in requirement_lines)


def data_snapshot_id(paths: list[Path], *, root: Path | None = None) -> str:
    """Hash file names and contents independent of caller-provided ordering."""

    if not paths:
        raise ValueError("at least one data snapshot path is required")
    root = (root or Path.cwd()).resolve()
    rows: list[dict[str, str]] = []
    for path in paths:
        resolved = path.resolve()
        try:
            display = resolved.relative_to(root).as_posix()
        except ValueError:
            display = resolved.as_posix()
        rows.append({"path": display, "sha256": sha256_file(resolved)})
    encoded = json.dumps(sorted(rows, key=lambda row: row["path"]), separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def write_manifest(path: Path, manifest: RunManifest) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        temporary.write_text(json.dumps(manifest.to_dict(), indent=2, sort_keys=True) + "\n")
        temporary.chmod(0o600)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
