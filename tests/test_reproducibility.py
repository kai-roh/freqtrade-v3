import json
from datetime import UTC, datetime

import pytest

from v3.reproducibility import (
    NO_MODEL_ARTIFACT_SHA256,
    RunManifest,
    TimeRange,
    data_snapshot_id,
    dependency_lock_is_exact,
    sha256_file,
    write_manifest,
)


def _manifest(**overrides):
    values = {
        "git_commit_sha": "a" * 40,
        "container_image_digest": f"sha256:{'b' * 64}",
        "dependency_lock_sha256": "c" * 64,
        "config_sha256": "d" * 64,
        "model_artifact_sha256": NO_MODEL_ARTIFACT_SHA256,
        "data_snapshot_id": "snapshot-2026-08-19",
        "timerange": TimeRange(datetime(2025, 1, 1, tzinfo=UTC), datetime(2026, 1, 1, tzinfo=UTC)),
        "generated_at": datetime(2026, 8, 19, tzinfo=UTC),
    }
    values.update(overrides)
    return RunManifest(**values)


def test_manifest_contains_all_seven_fields_and_has_stable_identity():
    first = _manifest()
    later = _manifest(generated_at=datetime(2026, 8, 20, tzinfo=UTC))

    assert first.manifest_id == later.manifest_id
    assert set(first.required_metadata()) == {
        "git_commit_sha",
        "container_image_digest",
        "dependency_lock_sha256",
        "config_sha256",
        "model_artifact_sha256",
        "data_snapshot_id",
        "timerange",
    }
    assert first.to_dict()["manifest_id"] == first.manifest_id


def test_dirty_manifest_is_recordable_but_not_deployable():
    manifest = _manifest(source_dirty=True)

    with pytest.raises(ValueError, match="dirty"):
        manifest.assert_deployable()

    unlocked = _manifest(dependencies_exact=False)
    with pytest.raises(ValueError, match="unlocked"):
        unlocked.assert_deployable()


def test_data_snapshot_is_order_independent_and_manifest_write_is_private(tmp_path):
    first = tmp_path / "a.parquet"
    second = tmp_path / "b.parquet"
    first.write_bytes(b"a")
    second.write_bytes(b"b")

    assert data_snapshot_id([first, second], root=tmp_path) == data_snapshot_id(
        [second, first], root=tmp_path
    )
    assert sha256_file(first) != sha256_file(second)

    output = tmp_path / "run-manifest.json"
    write_manifest(output, _manifest())
    written = json.loads(output.read_text())
    assert written["schema_version"] == 1
    assert output.stat().st_mode & 0o777 == 0o600


def test_manifest_rejects_naive_time_and_invalid_hashes():
    with pytest.raises(ValueError, match="timezone"):
        TimeRange(datetime(2025, 1, 1), datetime(2026, 1, 1))
    with pytest.raises(ValueError, match="container"):
        _manifest(container_image_digest="latest")


def test_dependency_lock_requires_resolved_or_exact_versions(tmp_path):
    loose = tmp_path / "requirements.txt"
    exact = tmp_path / "requirements.lock.txt"
    resolved = tmp_path / "uv.lock"
    loose.write_text("pandas\nnumpy>=2\n")
    exact.write_text("pandas==3.0.2\nnumpy==2.4.4\n")
    resolved.write_text("version = 1\n")

    assert not dependency_lock_is_exact(loose)
    assert dependency_lock_is_exact(exact)
    assert dependency_lock_is_exact(resolved)
