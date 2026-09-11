from nautilus_trader.adapters.binance.common.enums import BinanceAccountType, BinanceEnvironment

from v3.phase1.adapters import build_nautilus_client_configs


def test_locked_nautilus_builds_distinct_order_free_demo_client_configs():
    configs = build_nautilus_client_configs(api_key="fixture-key", api_secret="fixture-secret")

    data = configs["data_clients"]
    execution = configs["execution_clients"]
    assert set(data) == {"BINANCE_SPOT_DEMO", "BINANCE_USDM_DEMO"}
    assert set(execution) == set(data)

    assert data["BINANCE_SPOT_DEMO"].environment is BinanceEnvironment.DEMO
    assert data["BINANCE_USDM_DEMO"].environment is BinanceEnvironment.DEMO
    assert data["BINANCE_SPOT_DEMO"].account_type is BinanceAccountType.SPOT
    assert data["BINANCE_USDM_DEMO"].account_type is BinanceAccountType.USDT_FUTURES

    for config in (*data.values(), *execution.values()):
        assert config.instrument_provider.query_commission_rates
        assert not config.instrument_provider.load_all
        assert len(config.instrument_provider.load_ids) == 1
        hash(config.instrument_provider)
    assert {str(i) for i in data["BINANCE_SPOT_DEMO"].instrument_provider.load_ids} == {
        "BTCUSDT.BINANCE_SPOT_DEMO"
    }
    assert {str(i) for i in data["BINANCE_USDM_DEMO"].instrument_provider.load_ids} == {
        "BTCUSDT-PERP.BINANCE_USDM_DEMO"
    }
    assert execution["BINANCE_SPOT_DEMO"].venue != execution["BINANCE_USDM_DEMO"].venue


def test_runtime_aliases_map_to_policy_ids_and_reject_unknowns():
    import pytest

    from v3.phase1.adapters import canonical_instrument_id

    assert canonical_instrument_id("BTCUSDT.BINANCE_SPOT_DEMO") == "BTCUSDT.BINANCE"
    assert canonical_instrument_id("BTCUSDT-PERP.BINANCE_USDM_DEMO") == "BTCUSDT-PERP.BINANCE"
    with pytest.raises(ValueError):
        canonical_instrument_id("BTCUSDT.BINANCE")


def test_two_execution_clients_register_in_one_pinned_node_without_network():
    import asyncio

    from nautilus_trader.adapters.binance.factories import (
        BinanceLiveDataClientFactory,
        BinanceLiveExecClientFactory,
    )
    from nautilus_trader.common.config import LoggingConfig
    from nautilus_trader.live.config import TradingNodeConfig
    from nautilus_trader.live.node import TradingNode

    configs = build_nautilus_client_configs(api_key="fixture-key", api_secret="fixture-secret")
    node = TradingNode(
        TradingNodeConfig(
            trader_id="FIXTURE-001",
            logging=LoggingConfig(log_level="ERROR"),
            data_clients=configs["data_clients"],
            exec_clients=configs["execution_clients"],
        ),
        loop=asyncio.new_event_loop(),
    )
    try:
        for client_id in configs["data_clients"]:
            node.add_data_client_factory(client_id, BinanceLiveDataClientFactory)
            node.add_exec_client_factory(client_id, BinanceLiveExecClientFactory)
        node.build()
        assert len(node.kernel.exec_engine.registered_clients) == 2
    finally:
        node.dispose()
