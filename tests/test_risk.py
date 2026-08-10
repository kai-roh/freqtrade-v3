import pytest

from v3.risk import RiskConfig, build_risk_contract, gross_return, net_return, turnover


def test_long_and_short_contract_levels_are_atr_based():
    config = RiskConfig(stop_atr=2, target_atr=3, max_holding_candles=10, round_trip_cost_bps=15)

    long = build_risk_contract(100, 2, "long", config)
    short = build_risk_contract(100, 2, "short", config)

    assert long.stop_price == 96
    assert long.target_price == 106
    assert short.stop_price == 104
    assert short.target_price == 94
    assert long.max_holding_candles == 10
    assert long.round_trip_cost_bps == 15


def test_return_accounting_uses_full_round_trip_cost_and_1x_turnover():
    gross = gross_return("long", 100, 110)

    assert gross == pytest.approx(0.10)
    assert gross_return("short", 100, 90) == pytest.approx(0.10)
    assert net_return(gross, 20) == pytest.approx(0.098)
    assert turnover() == 2.0


def test_invalid_risk_inputs_raise():
    with pytest.raises(ValueError):
        RiskConfig(stop_atr=0)
    with pytest.raises(ValueError):
        build_risk_contract(100, 0, "long", RiskConfig())
    with pytest.raises(ValueError):
        build_risk_contract(100, 1, "flat", RiskConfig())
