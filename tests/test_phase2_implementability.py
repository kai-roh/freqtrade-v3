from decimal import Decimal

import pytest

from v3.phase2.implementability import (
    SymbolFilters,
    evaluate_symbol,
    evaluate_universe,
    floored_leg_notional,
    leg_notional_target,
)


def test_leg_target_follows_the_300_usdt_gross_target():
    assert leg_notional_target(2) == Decimal("75")
    assert leg_notional_target(3) == Decimal("50")
    with pytest.raises(ValueError):
        leg_notional_target(4)


def test_btc_fails_headroom_at_k2_while_a_5_usdt_minimum_alt_passes():
    btc = SymbolFilters("BTCUSDT", "100", "0.001", "0.1", "77000")
    assert floored_leg_notional(btc, 2) == Decimal("0")  # 75 USDT < one 0.001 BTC step
    result = evaluate_symbol(btc, 2)
    assert not result["admissible"] and "3x minimum" in result["reasons"][0]
    sol = SymbolFilters("SOLUSDT", "5", "1", "0.001", "150")
    assert floored_leg_notional(sol, 3) == Decimal("0")  # 50 USDT < one whole SOL at 150
    sol_cheap = SymbolFilters("SOLUSDT", "5", "0.1", "0.001", "150")
    assert floored_leg_notional(sol_cheap, 2) == Decimal("75.0")
    assert evaluate_symbol(sol_cheap, 2)["admissible"]


def test_universe_feasibility_requires_two_k_admissible_symbols_per_side():
    cheap = [SymbolFilters(f"S{i}USDT", "5", "1", "0.001", "1") for i in range(4)]
    expensive = [SymbolFilters("BTCUSDT", "100", "0.001", "0.1", "77000")]
    result = evaluate_universe(cheap + expensive)
    assert result["by_legs_per_side"]["2"]["basket_feasible"] is True
    assert result["by_legs_per_side"]["3"]["basket_feasible"] is False
    assert "BTCUSDT" not in result["by_legs_per_side"]["2"]["admissible_symbols"]
    assert result["contract"]["gross_notional_target_usdt"] == "300"
