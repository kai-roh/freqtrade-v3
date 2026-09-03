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
