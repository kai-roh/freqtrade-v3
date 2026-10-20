import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_order_free_carry_cli_uses_fresh_credentialed_fee_policy(tmp_path):
    output = tmp_path / "target.json"
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/scan_phase1_carry.py",
            "--policy",
            "configs/phase1-policy.json",
            "--observation",
            "examples/phase1/carry-observation.json",
            "--output",
            str(output),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(output.read_text())
    assert payload["actionable"]
    assert payload["net_expected_bps"] == "46.800000"


def test_execution_runtime_cli_passes_safe_fixture_and_fails_live_fixture(tmp_path):
    safe_output = tmp_path / "safe.json"
    command = [
        sys.executable,
        "scripts/check_phase1_execution_runtime.py",
        "--policy",
        "configs/phase1-policy.json",
        "--facts",
        "examples/phase1/runtime-preflight.json",
        "--output",
        str(safe_output),
    ]
    safe = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
    assert safe.returncode == 0, safe.stderr
    assert json.loads(safe_output.read_text())["passed"]

    facts = json.loads((ROOT / "examples/phase1/runtime-preflight.json").read_text())
    facts["environment"] = "live"
    unsafe_input = tmp_path / "unsafe.json"
    unsafe_input.write_text(json.dumps(facts))
    unsafe_output = tmp_path / "unsafe-output.json"
    command[command.index("examples/phase1/runtime-preflight.json")] = str(unsafe_input)
    command[-1] = str(unsafe_output)
    unsafe = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
    assert unsafe.returncode == 2
    assert not json.loads(unsafe_output.read_text())["passed"]
