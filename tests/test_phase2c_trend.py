import math

import numpy as np
import pandas as pd
import pytest

from v3.phase2.data import Phase2Panel
from v3.phase2c.research import windows
from v3.phase2c.trend import (
    NORMAL,
    TrendRule,
    VenueFilters,
    daily_closes,
    simulate_trend,
    target_weights,
    trend_grid,
)

T0 = pd.Timestamp("2024-01-01", tz="UTC")
SYMBOLS = ("BTC", "ETH")


def make_panel(days=300, *, drift=0.002, wiggle=0.01, funding=0.0001, seed=7):
    hours = pd.date_range(T0, periods=days * 24, freq="1h")
    rng = np.random.default_rng(seed)
    steps = drift / 24 + wiggle / math.sqrt(24) * rng.standard_normal((len(hours), 2))
    prices = 100.0 * np.exp(np.cumsum(steps, axis=0))
    frame = pd.DataFrame(prices, index=hours, columns=list(SYMBOLS))
    settlements = hours[hours.hour % 8 == 0]
    rates = pd.DataFrame(funding, index=settlements, columns=list(SYMBOLS))
    return Phase2Panel(open=frame, close=frame, mark=frame, funding=rates, symbols=SYMBOLS)


def test_grid_and_windows_match_the_registration():
    assert [r.label() for r in trend_grid()] == [
        "H4 L=20d binary",
        "H4 L=20d linear",
        "H4 L=60d binary",
        "H4 L=60d linear",
        "H4 L=120d binary",
        "H4 L=120d linear",
    ]
    w = windows()
    assert len(w) == 9
    assert (str(w[0].train_start.date()), str(w[0].validation_start.date())) == (
        "2020-07-02",
        "2022-08-01",
    )
    assert (str(w[4].train_start.date()), str(w[4].train_end.date())) == (
        "2022-06-30",
        "2024-06-29",
    )
    assert str(w[8].validation_end.date()) == "2026-10-01"


def test_weights_are_bounded_scaled_and_warm_up_as_nan():
    panel = make_panel(drift=0.006)
    for rule in trend_grid():
        w = target_weights(panel, rule)
        assert w.iloc[:60].isna().all().all()
        assert (w.dropna().abs() <= 1.0 + 1e-12).all().all()
    binary = target_weights(panel, TrendRule("trend", 60, "binary")).dropna()
    linear = target_weights(panel, TrendRule("trend", 60, "linear")).dropna()
    bh = target_weights(panel, TrendRule("bh_vt")).dropna()
    # A strong uptrend gives mostly long positions; linear conviction never exceeds binary.
    assert (binary.iloc[-100:] > 0).mean().min() >= 0.9
    assert (bh > 0).all().all()
    assert (linear.abs() <= binary.abs() + 1e-12).all().all()


def test_signal_uses_only_closes_before_the_decision():
    panel = make_panel()
    rule = TrendRule("trend", 60, "linear")
    decision = daily_closes(panel).index[200]
    before = target_weights(panel, rule).loc[decision]
    shocked_open = panel.open.copy()
    shocked_open.loc[shocked_open.index >= decision] *= 3.0
    shocked = Phase2Panel(
        open=shocked_open,
        close=shocked_open,
        mark=shocked_open,
        funding=panel.funding,
        symbols=SYMBOLS,
    )
    after = target_weights(shocked, rule).loc[decision]
    pd.testing.assert_series_equal(before, after)


def test_trades_execute_at_the_next_open_with_costs_and_funding():
    panel = make_panel(days=120, wiggle=0.0, drift=0.004)
    rule = TrendRule("bh_vt")
    start, end = T0 + pd.Timedelta(days=80), T0 + pd.Timedelta(days=100)
    result = simulate_trend(panel, [(start, rule)], cost=NORMAL, start=start, end=end, sleeve=500)
    first = result.episodes[0]
    assert first["start"] == (start + pd.Timedelta(hours=1)).isoformat()
    d = result.decomposition
    # Fees and slippage are exactly 5 and 2 bps of traded notional.
    assert d["fees"] == pytest.approx(result.traded_notional * 0.0005)
    assert d["slippage"] == pytest.approx(result.traded_notional * 0.0002)
    # Longs pay positive funding; hourly price steps add up to the price P&L.
    assert d["funding_pnl"] < 0
    ls = result.long_short
    assert ls["long_price_pnl"] + ls["short_price_pnl"] == pytest.approx(d["price_pnl"], abs=1e-9)
    assert d["total_pnl"] == pytest.approx(
        d["price_pnl"] + d["funding_pnl"] - d["fees"] - d["slippage"]
    )


def test_rebalance_only_when_weight_drifts_past_the_threshold():
    panel = make_panel(days=200, wiggle=0.0, drift=0.002)
    rule = TrendRule("bh_vt")
    start = T0 + pd.Timedelta(days=80)
    # 60 days of 0.2% daily drift move the weight by about 13%: entry and exit only.
    short = simulate_trend(
        panel, [(start, rule)], cost=NORMAL, start=start, end=start + pd.Timedelta(days=60)
    )
    assert short.trades == 4
    # About 22% over 100 days crosses the 0.20 threshold once per asset.
    long = simulate_trend(
        panel, [(start, rule)], cost=NORMAL, start=start, end=start + pd.Timedelta(days=100)
    )
    assert long.trades == 6


def test_schedule_switches_rule_at_the_effective_date():
    panel = make_panel(days=200)
    start, switch, end = (
        T0 + pd.Timedelta(days=130),
        T0 + pd.Timedelta(days=160),
        T0 + pd.Timedelta(days=190),
    )
    result = simulate_trend(
        panel,
        [(start, TrendRule("bh_vt")), (switch, TrendRule("none"))],
        cost=NORMAL,
        start=start,
        end=end,
    )
    assert all(pd.Timestamp(e["end"]) <= switch + pd.Timedelta(hours=1) for e in result.episodes)


def test_venue_rounding_floors_toward_zero_and_drops_tiny_orders():
    filters = VenueFilters(step={"BTC": 0.001, "ETH": 0.001}, min_notional={"BTC": 50, "ETH": 20})
    assert filters.round_qty("BTC", 0.0029, 80_000) == pytest.approx(0.002)
    assert filters.round_qty("BTC", -0.0029, 80_000) == pytest.approx(-0.002)
    assert filters.round_qty("BTC", 0.0006, 80_000) == 0.0
    assert filters.round_qty("ETH", 0.004, 4_000) == 0.0  # 16 USDT is below the 20 minimum
