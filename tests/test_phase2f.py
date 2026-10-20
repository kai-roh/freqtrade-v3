import io
import zipfile

import numpy as np
import pandas as pd
import pytest

from v3.phase2d.data import DailyPanel
from v3.phase2d.engine import Market
from v3.phase2f.data import reduce_metrics
from v3.phase2f.strategies import Config, Signals, registered_grid, weight_fn

DAYS = pd.date_range("2021-01-01", periods=300, freq="D", tz="UTC")


def market(prices: dict[str, np.ndarray]) -> Market:
    frame = pd.DataFrame(prices, index=DAYS)
    vol = pd.DataFrame({s: 1e6 * (len(prices) - i) for i, s in enumerate(prices)}, index=DAYS)
    panel = DailyPanel(open=frame, close=frame, quote_volume=vol, funding=frame * 0.0)
    return Market(panel, "perp")


def signals(m: Market, **frames: pd.DataFrame) -> Signals:
    empty = pd.DataFrame(np.nan, index=m.days, columns=m.symbols)
    return Signals(
        **{f: frames.get(f, empty) for f in ("top_ls", "acct_ls", "oi_value", "taker_share")}
    )


def test_registered_grid_has_66_trials():
    grid = registered_grid()
    assert len(grid) == 66 and len({c.label() for c in grid}) == 66
    assert {c.family for c in grid} == {"R1", "R2", "P1", "P2", "P3", "P4"}


def test_r1_asymmetric_sizing_follows_regime():
    n = len(DAYS)
    up = 100 * 1.01 ** np.arange(n)
    down = 100 * 0.99 ** np.arange(n)
    m = market({"BTCUSDT": down, "ETHUSDT": up})
    own = weight_fn(Config("R1", sma=50, up=1.0, down=0.5, source="own"), m)
    assert own(m, 200) == pytest.approx({0: -0.25, 1: 0.5})
    btc = weight_fn(Config("R1", sma=50, up=1.0, down=0.5, source="btc"), m)
    assert btc(m, 200) == pytest.approx({0: -0.25, 1: -0.25})
    assert own(m, 20) == {}  # no SMA yet


def test_r2_shorts_weakest_in_down_regime_and_longs_btc_in_up():
    n = len(DAYS)
    prices = {
        "BTCUSDT": 100 * 0.995 ** np.arange(n),
        "ETHUSDT": 100 * 0.99 ** np.arange(n),
        "AUSDT": 100 * 0.98 ** np.arange(n),
        "BUSDT": 100 * 1.001 ** np.arange(n),
    }
    m = market(prices)
    c = Config("R2", sma=100, lookback=14, k=1, up_mode="btc")
    assert weight_fn(c, m)(m, 200) == pytest.approx({2: -1.0})
    prices["BTCUSDT"] = 100 * 1.005 ** np.arange(n)
    m = market(prices)
    assert weight_fn(c, m)(m, 200) == {0: 1.0}


def test_positioning_fades_crowded_longs():
    n = len(DAYS)
    m = market({s: np.full(n, 100.0) for s in ("BTCUSDT", "ETHUSDT", "AUSDT", "BUSDT")})
    top = pd.DataFrame({"BTCUSDT": 1.0, "ETHUSDT": 2.0, "AUSDT": 3.0, "BUSDT": 0.5}, index=m.days)
    w = weight_fn(Config("P1", lookback=3, k=1), m, signals(m, top_ls=top))(m, 200)
    assert w == pytest.approx({3: 0.5, 2: -0.5})
    taker = top.copy()
    w = weight_fn(Config("P3", lookback=3, k=1), m, signals(m, taker_share=taker))(m, 200)
    assert w == pytest.approx({2: 0.5, 3: -0.5})
    sparse = top.copy()
    sparse[["AUSDT", "BUSDT", "ETHUSDT"]] = np.nan
    assert weight_fn(Config("P1", lookback=3, k=1), m, signals(m, top_ls=sparse))(m, 200) == {}


def test_reduce_metrics_takes_last_oi_and_mean_ratios():
    csv = (
        "create_time,symbol,sum_open_interest,sum_open_interest_value,"
        "count_toptrader_long_short_ratio,sum_toptrader_long_short_ratio,"
        "count_long_short_ratio,sum_taker_long_short_vol_ratio\n"
        "2023-05-01 00:00:00,X,1,100,1,1.0,2.0,0.5\n"
        "2023-05-01 23:55:00,X,1,300,1,3.0,4.0,1.5\n"
        "2023-05-02 00:00:00,X,1,999,1,9.0,9.0,9.0\n"
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("x.csv", csv)
    day, values = reduce_metrics(buf.getvalue())
    assert day == pd.Timestamp("2023-05-01", tz="UTC")
    assert values == pytest.approx(
        {"oi_value": 300, "top_ls": 2.0, "acct_ls": 3.0, "taker_ls": 1.0}
    )
