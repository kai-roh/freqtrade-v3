from math import isinf

import pandas as pd
import pytest

from v3.metrics import compute_trade_metrics


def trades(pnls, *, pairs=None, sides=None, notionals=None, costs=None):
    count = len(pnls)
    data = {
        "pnl": pnls,
        "pair": pairs or ["BTC/USDT"] * count,
        "side": sides or ["long"] * count,
        "notional": notionals or [100.0] * count,
    }
    if costs is not None:
        data["cost"] = costs
    return pd.DataFrame(data)


def test_trade_metrics_are_deterministic_and_grouped():
    frame = trades(
        [0.20, -0.10, 0.05],
        pairs=["ETH/USDT", "BTC/USDT", "ETH/USDT"],
        sides=["short", "long", "short"],
        notionals=[50, 100, 25],
        costs=[0.01, 0.02, 0.00],
    )

    first = compute_trade_metrics(frame)
    second = compute_trade_metrics(frame)

    assert first == second
    assert first.trade_count == 3
    assert first.net_pnl == pytest.approx(0.12)
    assert first.profit_factor == pytest.approx(0.24 / 0.12)
    assert first.expectancy == pytest.approx(0.04)
    assert first.win_rate == pytest.approx(2 / 3)
    assert first.turnover == pytest.approx(175.0)
    assert first.side_contributions == {"long": -0.12, "short": 0.24}
    assert first.pair_contributions == {"BTC/USDT": -0.12, "ETH/USDT": 0.24}


def test_no_trade_metrics_fail_closed_for_pf():
    result = compute_trade_metrics(trades([]))

    assert result.trade_count == 0
    assert result.profit_factor == 0.0
    assert result.expectancy == 0.0
    assert result.max_closed_equity_drawdown == 0.0


def test_profit_factor_is_infinite_when_there_are_wins_and_no_losses():
    result = compute_trade_metrics(trades([0.10, 0.05]))

    assert isinf(result.profit_factor)
    assert result.net_pnl == pytest.approx(0.15)


def test_cost_stress_subtracts_from_gross_pnl():
    result = compute_trade_metrics(trades([0.10], notionals=[100.0]), cost_stress=0.001)

    assert result.net_pnl == pytest.approx(0.0)
    assert result.total_cost == pytest.approx(0.1)
    assert result.profit_factor == 0.0


def test_drawdown_uses_initial_capital_for_first_loss_sequence():
    result = compute_trade_metrics(trades([-0.05, 0.02]), initial_capital=1.0)

    assert result.max_closed_equity_drawdown == pytest.approx(0.05)


def test_drawdown_uses_initial_capital_for_underwater_equity_path():
    result = compute_trade_metrics(trades([0.10, -0.05, -0.10, 0.04]))

    assert result.max_closed_equity_drawdown == pytest.approx(0.15)


def test_initial_capital_must_be_positive():
    with pytest.raises(ValueError, match="initial_capital must be positive"):
        compute_trade_metrics(trades([0.10]), initial_capital=0.0)


def test_metrics_fail_closed_on_missing_or_non_finite_data():
    with pytest.raises(ValueError, match="missing required columns"):
        compute_trade_metrics(pd.DataFrame({"pnl": [1.0]}))

    with pytest.raises(ValueError, match="finite numeric"):
        compute_trade_metrics(trades([float("nan")]))
