import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STRATEGY_PATH = ROOT / "user_data/strategies/V3ShadowStrategy.py"


def test_configured_shadow_strategy_exists_and_starts_stopped():
    config = json.loads((ROOT / "configs/dry-run.json").read_text())
    env_example = (ROOT / ".env.example").read_text()

    assert config["initial_state"] == "stopped"
    assert "FREQTRADE_STRATEGY=V3ShadowStrategy" in env_example
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
