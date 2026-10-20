import ast
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
STRATEGY_PATH = ROOT / "user_data/strategies/V3ShadowStrategy.py"


def test_configured_shadow_strategy_exists_and_starts_running_fail_closed():
    config = json.loads((ROOT / "configs/dry-run.json").read_text())
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text())

    assert config["initial_state"] == "running"
    assert config["dry_run"] is True
    assert "--strategy V3ShadowStrategy" in compose["services"]["freqtrade_v3_shadow"]["command"]
    assert STRATEGY_PATH.is_file()


def test_shadow_strategy_is_fail_closed_and_fixed_one_x():
    source = STRATEGY_PATH.read_text()
    tree = ast.parse(source)

    assert 'dataframe["enter_long"] = 0' in source
    assert 'dataframe["enter_short"] = 0' in source
    assert "return 1.0" in source
    assert any(
        isinstance(node, ast.ClassDef) and node.name == "V3ShadowStrategy" for node in tree.body
    )
