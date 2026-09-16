import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
V2_IDENTIFIERS = {
    "tradesv3.sqlite",
    "KaiBaseStrategy",
    "LLMEnhancedModel",
    "stable_freqai",
}


def load_json_config(name: str) -> dict:
    return json.loads((ROOT / "configs" / name).read_text())


def test_docker_compose_reuses_endpoint_but_isolates_v3_state() -> None:
    compose_text = (ROOT / "docker-compose.yml").read_text()
    compose = yaml.safe_load(compose_text)

    assert set(compose["services"]) == {"freqtrade_v3_shadow"}
    service = compose["services"]["freqtrade_v3_shadow"]

    assert service["container_name"] == "freqtrade_kai"
    assert service["ports"] == ["127.0.0.1:8080:8080"]
    assert "tradesv3_v3.sqlite" in service["command"]
    assert "configs/dry-run.json" in service["command"]
    assert "stable_freqai" not in service["image"]
    assert service["image"] == (
        "freqtradeorg/freqtrade@"
        "sha256:50720a4af314a812be2cfbf5cc6331c63e9332b06f3f4372241f54bc61a35486"
    )
    assert "healthcheck" in service
    assert all("TELEGRAM" not in item for item in service["environment"])

    for identifier in V2_IDENTIFIERS:
        assert identifier not in compose_text


def test_dry_run_config_is_btc_eth_15m_isolated_futures() -> None:
    config = load_json_config("dry-run.json")

    assert config["dry_run"] is True
    assert config["trading_mode"] == "futures"
    assert config["margin_mode"] == "isolated"
    assert config["timeframe"] == "15m"
    assert config["stake_amount"] == 50
    assert config["exchange"]["pair_whitelist"] == ["BTC/USDT:USDT", "ETH/USDT:USDT"]
    assert config["telegram"]["enabled"] is False
    assert config["api_server"]["enabled"] is True


def test_research_config_keeps_same_safe_market_scope_without_api_server() -> None:
    config = load_json_config("research.json")

    assert config["dry_run"] is True
    assert config["trading_mode"] == "futures"
    assert config["margin_mode"] == "isolated"
    assert config["timeframe"] == "15m"
    assert config["exchange"]["pair_whitelist"] == ["BTC/USDT:USDT", "ETH/USDT:USDT"]
    assert config["telegram"]["enabled"] is False
    assert config["api_server"]["enabled"] is False


def test_configs_do_not_embed_secrets_or_v2_runtime_identifiers() -> None:
    for path in (ROOT / "configs").glob("*.json"):
        text = path.read_text()
        config = json.loads(text)
        if not {"exchange", "telegram", "api_server"}.issubset(config):
            for identifier in V2_IDENTIFIERS:
                assert identifier not in text
            continue

        assert config["exchange"]["key"] == ""
        assert config["exchange"]["secret"] == ""
        assert config["telegram"]["token"] == ""
        assert config["telegram"]["chat_id"] == ""
        assert config["api_server"]["jwt_secret_key"] == ""
        assert config["api_server"]["username"] == ""
        assert config["api_server"]["password"] == ""

        for identifier in V2_IDENTIFIERS:
            assert identifier not in text
