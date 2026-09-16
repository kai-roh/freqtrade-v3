import numpy as np
import pandas as pd
import pytest

from v3.phase2.basket import NORMAL_COST, STRESS_COST, Rule, h1_grid, h2_grid, simulate_basket
from v3.phase2.data import Phase2Panel
from v3.phase2.pbo import probability_of_backtest_overfitting
from v3.phase2.signals import (
    Selection,
    daily_lookback_returns,
    funding_spread,
    select_legs,
    trailing_funding_mean,
)

SYMBOLS = ("AAA", "BBB", "CCC", "DDD", "EEE", "FFF")


def panel(days=40, seed=7, funding_bias=None, drift=None):
    rng = np.random.default_rng(seed)
    index = pd.date_range("2026-01-01", periods=days * 24, freq="1h", tz="UTC")
    prices = {}
    for i, symbol in enumerate(SYMBOLS):
        mu = 0.0 if drift is None else drift[i]
        steps = 1 + rng.normal(mu, 0.002, len(index))
        prices[symbol] = 100.0 * (1 + i) * np.cumprod(steps)
    close = pd.DataFrame(prices, index=index)
    open_ = close.shift(1).bfill()
    settlements = index[index.hour % 8 == 0]
    funding = pd.DataFrame(
        {
            symbol: np.full(len(settlements), 0.0001 * (funding_bias[i] if funding_bias else 1.0))
            for i, symbol in enumerate(SYMBOLS)
        },
        index=settlements,
    )
    return Phase2Panel(
        open_[list(SYMBOLS)], close[list(SYMBOLS)], close[list(SYMBOLS)], funding, SYMBOLS
    )


def test_trailing_funding_mean_is_time_windowed_and_requires_a_full_window():
    p = panel(days=10)
    mean = trailing_funding_mean(p.funding, 48)
    assert mean.iloc[:5].isna().all().all()  # 48h = 6 settlements; first 5 incomplete
    assert mean.iloc[6:].notna().all().all()
    assert np.isclose(mean.iloc[-1]["AAA"], 0.0001)
    with pytest.raises(ValueError):
        trailing_funding_mean(p.funding, 4)


def test_daily_lookback_returns_align_to_completed_utc_days():
    p = panel(days=12)
    returns = daily_lookback_returns(p.close, 3)
    assert returns.index[0].hour == 0
    assert returns.iloc[:3].isna().all().all() and returns.iloc[3:].notna().all().all()


def test_select_legs_uses_hysteresis_and_deterministic_ties():
    scores = pd.Series({"AAA": 5.0, "BBB": 4.0, "CCC": 3.0, "DDD": 2.0, "EEE": 1.0, "FFF": 0.0})
    first = select_legs(scores, k=2)
    assert first == Selection(("AAA", "BBB"), ("FFF", "EEE"))
    # BBB slips to rank 3 (within k+1): held, so it stays; CCC does not replace it.
    shifted = pd.Series({"AAA": 5.0, "CCC": 4.5, "BBB": 4.0, "DDD": 2.0, "EEE": 1.0, "FFF": 0.0})
    assert select_legs(shifted, k=2, previous=first).shorts == ("AAA", "BBB")
    # BBB falls to rank 4 (outside k+1): replaced by the next best.
    dropped = pd.Series({"AAA": 5.0, "CCC": 4.5, "DDD": 4.2, "BBB": 4.0, "EEE": 1.0, "FFF": 0.0})
    assert select_legs(dropped, k=2, previous=first).shorts == ("AAA", "CCC")
    tied = pd.Series({"AAA": 1.0, "BBB": 1.0, "CCC": 1.0, "DDD": 0.0, "EEE": 0.0, "FFF": 0.0})
    assert select_legs(tied, k=2) == Selection(("AAA", "BBB"), ("DDD", "EEE"))
    assert select_legs(tied, k=2, previous=Selection(("CCC",), ())).shorts == ("CCC", "AAA")
    assert select_legs(pd.Series({"AAA": 1.0, "BBB": np.nan, "CCC": 0.0}), k=2) == Selection((), ())
    assert np.isclose(funding_spread(scores, first), (5 + 4) / 2 - (0 + 1) / 2)


def test_h0_never_trades_and_returns_are_zero():
    p = panel(days=30)
    result = simulate_basket(
        p, Rule("H0"), cost=NORMAL_COST, start=p.open.index[0], end=p.open.index[-1]
    )
    assert result.trades == 0 and result.decomposition["total_pnl"] == 0.0
    assert (result.daily_returns == 0).all()


def test_h1_collects_funding_pays_costs_on_quantity_changes_and_ends_flat():
    # Symbols 0..2 have high positive funding (short them, receive), 3..5 negative (long, receive).
    p = panel(days=30, funding_bias=(3, 3, 3, -3, -3, -3))
    rule = Rule("H1", k=2, window_hours=48, spread_min=0.0001)
    result = simulate_basket(p, rule, cost=NORMAL_COST, start=p.open.index[0], end=p.open.index[-1])
    d = result.decomposition
    assert result.trades >= 4 and d["funding_pnl"] > 0 and d["fees"] > 0 and d["slippage"] > 0
    assert np.isclose(d["fees"] / d["slippage"], 5 / 2, rtol=0.01)
    assert np.isclose(d["total_pnl"], d["price_pnl"] + d["funding_pnl"] - d["fees"] - d["slippage"])
    assert np.isclose(result.equity.iloc[-1] - result.equity.iloc[0], d["total_pnl"])
    assert result.blocked_entries == 0
    per_symbol_total = sum(v["price_pnl"] + v["funding_pnl"] for v in result.per_symbol.values())
    assert np.isclose(per_symbol_total, d["price_pnl"] + d["funding_pnl"], atol=1e-6)
    stress = simulate_basket(p, rule, cost=STRESS_COST, start=p.open.index[0], end=p.open.index[-1])
    assert stress.decomposition["slippage"] > d["slippage"]


def test_h1_spread_filter_blocks_entries_when_funding_is_flat_across_the_universe():
    p = panel(days=20)  # identical funding everywhere: spread is zero
    rule = Rule("H1", k=2, window_hours=48, spread_min=0.00005)
    result = simulate_basket(p, rule, cost=NORMAL_COST, start=p.open.index[0], end=p.open.index[-1])
    assert result.trades == 0 and result.blocked_entries > 0


def test_daily_stop_flattens_and_halts_for_a_day():
    # Strong opposite drifts make the dollar-neutral H2 reversal basket lose quickly.
    p = panel(days=30, drift=(0.004, 0.004, 0.0, 0.0, -0.004, -0.004), seed=3)
    rule = Rule("H2", k=2, lookback_days=3, hold_days=1, max_hold_hours=240)
    result = simulate_basket(p, rule, cost=NORMAL_COST, start=p.open.index[0], end=p.open.index[-1])
    assert result.stop_events >= 1
    assert result.decomposition["total_pnl"] < 0


def test_entry_end_stops_new_entries_but_allows_exits():
    p = panel(days=30, funding_bias=(3, 3, 3, -3, -3, -3))
    rule = Rule("H1", k=2, window_hours=48, spread_min=0.0001, max_hold_hours=48)
    mid = p.open.index[24 * 10]
    result = simulate_basket(
        p, rule, cost=NORMAL_COST, start=p.open.index[0], end=p.open.index[-1], entry_end=mid
    )
    last_episode_end = pd.Timestamp(result.episodes[-1]["end"])
    assert last_episode_end <= mid + pd.Timedelta(hours=49)


def test_grids_match_the_registration():
    assert len(h1_grid()) == 12 and len(h2_grid()) == 12
    assert {r.window_hours for r in h1_grid()} == {48, 168, 336}
    assert {r.spread_min for r in h1_grid()} == {0.00005, 0.0001}
    assert {r.lookback_days for r in h2_grid()} == {3, 5, 10}


def test_pbo_is_high_for_noise_and_low_for_a_genuinely_better_strategy():
    rng = np.random.default_rng(1)
    noise = pd.DataFrame(rng.normal(0, 0.01, (400, 8)))
    result = probability_of_backtest_overfitting(noise, partitions=8)
    assert 0.2 <= result["pbo"] <= 0.8 and result["splits"] == 70
    skilled = noise.copy()
    skilled[0] = rng.normal(0.004, 0.01, 400)
    assert probability_of_backtest_overfitting(skilled, partitions=8)["pbo"] < 0.2
    with pytest.raises(ValueError):
        probability_of_backtest_overfitting(noise.iloc[:10], partitions=8)
