import numpy as np
import pandas as pd
import pytest

from v3.phase2d.data import DailyPanel, eligible_symbol
from v3.phase2d.engine import Market, metrics, simulate, split_reused_symbols
from v3.phase2d.evaluate import deflated_sharpe, pbo_cscv
from v3.phase2d.strategies import Config, registered_grid, weight_fn

DAYS = pd.date_range("2017-06-01", periods=400, freq="D", tz="UTC")


def panel(prices: dict[str, np.ndarray], volume=None, funding=None) -> DailyPanel:
    frame = pd.DataFrame(prices, index=DAYS[: len(next(iter(prices.values())))])
    vol = pd.DataFrame(
        volume or {s: 1e6 * (i + 1) for i, s in enumerate(prices)}, index=frame.index
    )
    return DailyPanel(
        open=frame,
        close=frame.shift(-1).fillna(frame),  # close(t) = open(t+1)
        quote_volume=vol.where(frame.notna()),
        funding=None if funding is None else pd.DataFrame(funding, index=frame.index),
    )


def test_symbol_filter():
    assert eligible_symbol("BTCUSDT") and eligible_symbol("SOLUSDT")
    assert not eligible_symbol("USDCUSDT") and not eligible_symbol("BTCUPUSDT")
    assert not eligible_symbol("ETHBTC") and not eligible_symbol("WBTCUSDT")


def test_registered_grid_has_120_trials():
    grid = registered_grid()
    assert len(grid) == 120 and len({c.label() for c in grid}) == 120


def test_buy_and_hold_pays_entry_cost_and_tracks_price():
    n = len(DAYS)
    price = 100 * 1.001 ** np.arange(n)
    m = Market(panel({"BTCUSDT": price}), "spot")
    start, end = DAYS[200], DAYS[300]
    res = simulate(m, lambda mk, i: {0: 1.0}, start=start, end=end, every=100_000, anchor=DAYS[199])
    # Entry at open(start): fee 10 + slippage 5 bps on the first day only.
    assert res.returns.iloc[0] == pytest.approx((1 - 0.0015) * 1.001 - 1)
    assert res.returns.iloc[1:].to_numpy() == pytest.approx(0.001)
    assert res.costs == pytest.approx(0.0015)


def test_drift_between_rebalances_and_cash():
    n = len(DAYS)
    a = 100 * 1.01 ** np.arange(n)
    b = np.full(n, 100.0)
    m = Market(panel({"AUSDT": a, "BUSDT": b}), "spot")
    res = simulate(
        m,
        lambda mk, i: {0: 0.5},
        start=DAYS[200],
        end=DAYS[210],
        every=100_000,
        anchor=DAYS[199],
        cost_multiplier=0.0,
    )
    # Half in A (+1%/day), half cash: the A weight drifts up, so returns rise each day.
    r = res.returns.to_numpy()
    assert r[0] == pytest.approx(0.005)
    assert np.all(np.diff(r) > 0)
    equity = (1 + res.returns).prod()
    assert equity == pytest.approx(0.5 + 0.5 * 1.01**11)


def test_delisted_holding_exits_at_last_close_and_pays_cost():
    n = len(DAYS)
    a = np.full(n, 100.0)
    a[205:] = np.nan
    m = Market(panel({"AUSDT": a, "BTCUSDT": np.full(n, 50.0)}), "spot")
    res = simulate(
        m, lambda mk, i: {0: 1.0}, start=DAYS[200], end=DAYS[210], every=100_000, anchor=DAYS[199]
    )
    # Day 204 is the last open; the position is closed at day 204's close with an exit cost.
    assert res.costs == pytest.approx(0.0015 * 2)
    assert (res.returns.iloc[5:] == 0).all()


def test_perp_funding_sign():
    n = len(DAYS)
    flat = np.full(n, 100.0)
    m = Market(panel({"AUSDT": flat}, funding={"AUSDT": np.full(n, 0.001)}), "perp")
    # Rebalanced daily (no cost) so the exposure stays exactly 1x.
    longr = simulate(
        m,
        lambda mk, i: {0: 1.0},
        start=DAYS[200],
        end=DAYS[205],
        every=1,
        anchor=DAYS[0],
        cost_multiplier=0.0,
    )
    shortr = simulate(
        m,
        lambda mk, i: {0: -1.0},
        start=DAYS[200],
        end=DAYS[205],
        every=1,
        anchor=DAYS[0],
        cost_multiplier=0.0,
    )
    assert longr.returns.to_numpy() == pytest.approx(-0.001)
    assert shortr.returns.to_numpy() == pytest.approx(0.001)


def test_decisions_use_only_past_data():
    """A strategy that peeks at tomorrow would earn the jump; the engine must not allow it."""
    n = len(DAYS)
    a = np.full(n, 100.0)
    a[250:] = 200.0  # a jump at the open of day 250
    m = Market(panel({"AUSDT": a, "BTCUSDT": np.full(n, 1.0)}), "spot")
    seen = []

    def spy(mk, i):
        seen.append(i)
        return {0: 1.0} if mk.close[i, 0] > 150 else {}

    res = simulate(
        m, spy, start=DAYS[240], end=DAYS[260], every=1, anchor=DAYS[0], cost_multiplier=0.0
    )
    # close(249) = open(250) = 200, so the decision at close 249 buys at open 250: no gain.
    assert res.returns.sum() == pytest.approx(0.0)
    assert max(seen) == m.index_of(DAYS[259])


def test_reused_symbol_is_split_after_a_long_gap():
    n = len(DAYS)
    a = np.full(n, 10.0)
    a[100:130] = np.nan
    p = split_reused_symbols(panel({"LUNAUSDT": a}))
    assert set(p.close.columns) == {"LUNAUSDT", "LUNAUSDT#2"}
    assert p.close["LUNAUSDT"].iloc[130:].isna().all()
    assert p.close["LUNAUSDT#2"].iloc[:100].isna().all()


def test_universe_needs_history_and_ranks_by_liquidity():
    n = len(DAYS)
    prices = {"AUSDT": np.full(n, 1.0), "BUSDT": np.full(n, 1.0)}
    prices["BUSDT"][:300] = np.nan  # listed late
    m = Market(panel(prices, volume={"AUSDT": 1e6, "BUSDT": 1e9}), "spot")
    assert list(m.universe(350, 10)) == [0]  # B has < 90 days of history
    assert list(m.universe(395, 1)) == [1]  # later B is the most liquid


def test_momentum_family_picks_the_winner():
    n = len(DAYS)
    up = 100 * 1.01 ** np.arange(n)
    down = 100 * 0.99 ** np.arange(n)
    m = Market(panel({"BTCUSDT": up, "XUSDT": down}), "spot")
    w = weight_fn(Config("F1", n=10, lookback=30, k=1), m)(m, 300)
    assert w == {0: 1.0}
    ls = weight_fn(Config("F4", n=10, lookback=30, k=1), m)(m, 300)
    assert ls == {0: 0.5, 1: -0.5}


def test_pbo_low_for_a_real_edge_and_dsr_rewards_it():
    rng = np.random.default_rng(0)
    noise = pd.DataFrame(rng.normal(0, 0.01, (2000, 10)))
    edge = noise.copy()
    edge[0] += 0.003
    assert pbo_cscv(edge) < 0.1
    assert pbo_cscv(noise) > 0.2
    sharpes = noise.mean() / noise.std()
    assert deflated_sharpe(edge[0], sharpes.to_numpy(), trials=10) > 0.95
    assert deflated_sharpe(noise[1], sharpes.to_numpy(), trials=10) < 0.95


def test_metrics_basic():
    r = pd.Series([0.01, -0.02, 0.03], index=DAYS[:3])
    out = metrics(r)
    assert out["total"] == pytest.approx(1.01 * 0.98 * 1.03 - 1)
    assert out["mdd"] == pytest.approx(0.02)
