import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _run(script: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        (sys.executable, str(ROOT / "scripts" / script), *args),
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_cost_and_instrument_example_commands_are_machine_readable():
    cost = _run(
        "calculate_cost_gate.py",
        "--input",
        "examples/phase0/cost-gate.json",
    )
    instrument = _run(
        "check_instrument_conformance.py",
        "--input",
        "examples/phase0/instrument-preflight.json",
    )

    assert cost.returncode == 0, cost.stderr
    assert json.loads(cost.stdout)["gate"]["passed"] is True
    assert instrument.returncode == 0, instrument.stderr
    assert json.loads(instrument.stdout)["passed"] is True


def test_run_manifest_command_records_source_state_and_allows_development_override(tmp_path):
    data = tmp_path / "snapshot.parquet"
    data.write_bytes(b"immutable-snapshot")
    unlocked = tmp_path / "unlocked-requirements.txt"
    unlocked.write_text("numpy\n")
    output = tmp_path / "manifest.json"

    result = _run(
        "build_run_manifest.py",
        "--container-image-digest",
        f"sha256:{'a' * 64}",
        "--dependency-lock",
        str(unlocked),
        "--config",
        "configs/research.json",
        "--no-model",
        "--data",
        str(data),
        "--data-root",
        str(tmp_path),
        "--timerange-start",
        "2025-01-01T00:00:00Z",
        "--timerange-end",
        "2026-01-01T00:00:00Z",
        "--generated-at",
        "2026-08-19T00:00:00Z",
        "--output",
        str(output),
        "--allow-dirty",
        "--allow-unlocked-dependencies",
    )

    assert result.returncode == 0, result.stderr
    manifest = json.loads(output.read_text())
    assert isinstance(manifest["source_dirty"], bool)
    assert manifest["dependencies_exact"] is False
    assert len(manifest["manifest_id"]) == 64
    assert output.stat().st_mode & 0o777 == 0o600


def test_block_bootstrap_command_uses_registration_without_overrides(tmp_path):
    source = tmp_path / "returns.csv"
    source.write_text(
        "timestamp,net_return\n"
        "2026-01-01,-0.01\n"
        "2026-01-02,0.01\n"
        "2026-01-03,-0.02\n"
        "2026-01-04,0.02\n"
        "2026-01-05,-0.01\n"
        "2026-01-06,0.01\n"
    )
    output = tmp_path / "bootstrap.json"

    result = _run(
        "run_block_bootstrap.py",
        "--input-csv",
        str(source),
        "--registration",
        "examples/phase0/block-bootstrap.preregister.json",
        "--output",
        str(output),
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(output.read_text())
    assert payload["observation_count"] == 6
    assert payload["registration"]["seed"] == 20260819


def test_hyperliquid_capture_replays_raw_metadata_without_network(tmp_path):
    raw = tmp_path / "meta.json"
    raw.write_text(
        json.dumps(
            [
                {"universe": [{"name": "BTC", "szDecimals": 5, "maxLeverage": 40}]},
                [{"markPx": "60000", "oraclePx": "60001", "funding": "0.0001"}],
            ]
        )
    )
    output = tmp_path / "snapshot.json"

    result = _run(
        "capture_hyperliquid_instruments.py",
        "--environment",
        "testnet",
        "--symbol",
        "BTC",
        "--input-response",
        str(raw),
        "--fetched-at",
        "2026-08-25T00:00:00+00:00",
        "--output",
        str(output),
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(output.read_text())
    assert payload["instruments"][0]["price_increment"] == "0.1"
    assert output.stat().st_mode & 0o777 == 0o600


def test_hyperliquid_capture_rejects_evidence_path_collisions(tmp_path):
    raw = tmp_path / "meta.json"
    original = json.dumps([{"universe": []}, []])
    raw.write_text(original)

    result = _run(
        "capture_hyperliquid_instruments.py",
        "--environment",
        "testnet",
        "--input-response",
        str(raw),
        "--output",
        str(raw),
    )

    assert result.returncode == 2
    assert "must be distinct" in result.stderr
    assert raw.read_text() == original


def test_hyperliquid_snapshot_can_build_and_validate_order_preflight(tmp_path):
    raw = tmp_path / "meta.json"
    raw.write_text(
        json.dumps(
            [
                {"universe": [{"name": "BTC", "szDecimals": 5, "maxLeverage": 40}]},
                [{"markPx": "60000", "oraclePx": "60001", "funding": "0.0001"}],
            ]
        )
    )
    snapshot = tmp_path / "snapshot.json"
    preflight_input = tmp_path / "order-preflight.json"

    capture = _run(
        "capture_hyperliquid_instruments.py",
        "--environment",
        "testnet",
        "--symbol",
        "BTC",
        "--input-response",
        str(raw),
        "--fetched-at",
        "2026-08-25T00:00:00+00:00",
        "--output",
        str(snapshot),
    )
    build = _run(
        "build_hyperliquid_preflight_input.py",
        "--snapshot",
        str(snapshot),
        "--instrument",
        "BTC",
        "--target-notional",
        "30",
        "--observed-leverage",
        "2",
        "--quote-age-ms",
        "100",
        "--order-reject-probe",
        "passed",
        "--require-order-reject-probe",
        "--entry-reason",
        "funding spread above threshold",
        "--target-position",
        "perp short",
        "--normal-exit",
        "spread closes",
        "--risk-exit",
        "leverage or quote freshness failure",
        "--max-holding-or-review-at",
        "next settlement",
        "--cost-and-risk-budget",
        "max legging 5 bps",
        "--output",
        str(preflight_input),
    )
    check = _run("check_order_preflight.py", "--input", str(preflight_input))

    assert capture.returncode == 0, capture.stderr
    assert build.returncode == 0, build.stderr
    assert preflight_input.stat().st_mode & 0o777 == 0o600
    assert check.returncode == 0, check.stderr
    result = json.loads(check.stdout)
    assert result["passed"] is True
    assert result["intent"]["entry_reason"] == "funding spread above threshold"


def test_order_preflight_cli_rejects_missing_intent():
    result = _run(
        "check_order_preflight.py",
        "--input",
        "examples/phase0/instrument-preflight.json",
    )

    assert result.returncode == 1
    assert "intent:" in result.stdout
