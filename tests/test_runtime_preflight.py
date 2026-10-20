import copy
import json
import stat
from pathlib import Path

import yaml

from v3.runtime_preflight import load_and_validate, validate_shadow_runtime

ROOT = Path(__file__).resolve().parents[1]


def _inputs():
    config = json.loads((ROOT / "configs/dry-run.json").read_text())
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text())
    return config, compose


def test_current_shadow_runtime_contract_passes_with_example_environment():
    result = load_and_validate(
        ROOT / "configs/dry-run.json",
        ROOT / "docker-compose.yml",
    )

    assert result.passed
    assert len(result.checks) == 9
    assert (ROOT / "scripts/start_shadow_runtime.sh").stat().st_mode & stat.S_IXUSR


def test_shadow_runtime_rejects_live_config_strategy_or_unpinned_image():
    config, compose = _inputs()
    unsafe_config = copy.deepcopy(config)
    unsafe_config["dry_run"] = False
    unsafe_config["force_entry_enable"] = True
    unsafe_compose = copy.deepcopy(compose)
    unsafe_compose["services"]["freqtrade_v3_shadow"]["image"] = "freqtradeorg/freqtrade:latest"
    unsafe_compose["services"]["freqtrade_v3_shadow"]["command"] = (
        "trade --strategy UnreviewedStrategy"
    )

    result = validate_shadow_runtime(unsafe_config, unsafe_compose)
    failures = {check.code for check in result.checks if not check.passed}

    assert {"dry_run", "force_entry", "strategy_argument", "image_digest"}.issubset(failures)


def test_shadow_strategy_cannot_be_overridden_by_shell_environment(monkeypatch):
    config, compose = _inputs()
    monkeypatch.setenv("FREQTRADE_STRATEGY", "must-not-run")

    serialized = json.dumps(validate_shadow_runtime(config, compose).to_dict())

    assert "must-not-run" not in serialized
    assert validate_shadow_runtime(config, compose).passed
