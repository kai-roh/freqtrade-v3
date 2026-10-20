from decimal import Decimal

import numpy as np
import pandas as pd
import pytest

from tests.test_ma200_live import FakeExchange
from v3.ma200live.client import Credentials, FuturesClient
from v3.ma200live.engine import LiveConfig, StateStore
from v3.phase2d.data import DailyPanel
from v3.phase2d.engine import Market
from v3.phase2f.strategies import T1_MEMBERS, Signals, ensemble_fn
from v3.t1live.engine import plan_orders, run_executor, run_guard, state_lock
from v3.t1live.signal import is_decision_day, weights_from_frames

MONDAY = pd.Timestamp("2026-10-26 00:05", tz="UTC")  # decision day Sunday 10-25
NAMES = [f"A{i:02d}USDT" for i in range(24)] + ["BTCUSDT", "ETHUSDT"]


class MultiExchange(FakeExchange):
    """FakeExchange with many symbols, Mainnet-style tickers and taker columns."""

    def __init__(self, listed=None):
        super().__init__()
        rng = np.random.default_rng(7)
        self.price = {s: Decimal(str(round(float(rng.uniform(1, 50)), 2))) for s in NAMES}
        self.price["BTCUSDT"], self.price["ETHUSDT"] = Decimal(100_000), Decimal(4_000)
        self.positions = {s: Decimal(0) for s in NAMES}
        self.entry = {s: Decimal(0) for s in NAMES}
        self.config = {s: {"marginType": "ISOLATED", "leverage": 20} for s in NAMES}
        self.listed = set(listed or NAMES)
        self.volume = {s: 1e8 * (len(NAMES) - i) for i, s in enumerate(NAMES)}
        self.taker = {s: float(rng.uniform(0.4, 0.6)) for s in NAMES}

    def klines(self, symbol):
        rows = []
        start = MONDAY.floor("D") - pd.Timedelta(days=130)
        for i in range(130):
            day = start + pd.Timedelta(days=i)
            ms = int(day.timestamp() * 1000)
            qv = self.volume[symbol] * (1 + 0.01 * (i % 5))
            taker = qv * (self.taker[symbol] + 0.02 * np.sin(i + len(symbol)))
            px = float(self.price[symbol])
            rows.append([ms, px, px, px, px, 0, ms + 86_399_999, qv, 0, 0, taker, 0])
        return rows

    def __call__(self, method, url, headers, body):
        if url.endswith("/fapi/v1/ticker/24hr"):
            return 200, [{"symbol": s, "quoteVolume": str(v)} for s, v in self.volume.items()]
        if "/fapi/v1/exchangeInfo" in url:
            mainnet = "fapi.binance.com" in url and "demo" not in url
            names = NAMES if mainnet else sorted(self.listed)
            return 200, {
                "symbols": [
                    {
                        "symbol": s,
                        "status": "TRADING",
                        "contractType": "PERPETUAL",
                        "quoteAsset": "USDT",
                        "filters": [
                            {"filterType": "LOT_SIZE", "stepSize": "0.001", "minQty": "0.001"},
                            {"filterType": "PRICE_FILTER", "tickSize": "0.01"},
                            {"filterType": "MIN_NOTIONAL", "notional": "5"},
                        ],
                    }
                    for s in names
                ]
            }
        return super().__call__(method, url, headers, body)


def make(tmp_path, exchange=None, stop="650"):
    exchange = exchange or MultiExchange()
    client = FuturesClient("demo", Credentials("k", "s"), transport=exchange, symbols=())
    store = StateStore(tmp_path)
    store.init(
        LiveConfig(
            environment="demo",
            start_ms=int(MONDAY.timestamp() * 1000) - 1,
            stop_equity=Decimal(stop),
            price_cap_bps=Decimal(30),
        )
    )
    return exchange, client, store


FLT = {"step": Decimal("0.001"), "min_qty": Decimal("0.001"), "min_notional": Decimal("5")}


def test_plan_orders_exits_first_flips_and_skips():
    current = {"AUSDT": Decimal("2"), "BUSDT": Decimal("-1"), "CUSDT": Decimal("3")}
    targets = {"AUSDT": -0.1, "CUSDT": 0.01, "DUSDT": 0.002, "XUSDT": 0.1}
    prices = {s: Decimal(10) for s in ("AUSDT", "BUSDT", "CUSDT", "DUSDT")}
    filters = {s: FLT for s in prices}
    exits, entries, skipped, target = plan_orders(current, targets, prices, filters, Decimal(1000))
    assert [(o.step.symbol, o.step.purpose, o.step.qty) for o in exits] == [
        ("AUSDT", "close", Decimal("2")),
        ("BUSDT", "close", Decimal("1")),
        ("CUSDT", "reduce", Decimal("2")),
    ]
    assert all(o.step.reduce_only for o in exits)
    assert [(o.step.symbol, o.step.side, o.step.qty) for o in entries] == [
        ("AUSDT", "SELL", Decimal("10"))
    ]
    assert skipped == {"DUSDT": "order below minimum notional", "XUSDT": "not listed on this venue"}
    assert target["CUSDT"] == Decimal("1") and target["BUSDT"] == 0


def test_live_weights_match_the_backtest_rule():
    days = pd.date_range("2026-01-01", periods=140, freq="D", tz="UTC")
    rng = np.random.default_rng(3)
    names = [f"S{i:02d}USDT" for i in range(26)]
    close = pd.DataFrame(rng.uniform(1, 2, (140, 26)), index=days, columns=names)
    qv = pd.DataFrame(rng.uniform(1e6, 1e8, (140, 26)), index=days, columns=names)
    taker = qv * rng.uniform(0.3, 0.7, (140, 26))
    close.iloc[:60, 3] = np.nan  # too young
    panel = DailyPanel(open=close, close=close, quote_volume=qv, funding=close * 0)
    market = Market(panel, "perp")
    share = taker / qv
    empty = share * np.nan
    fn = ensemble_fn(
        T1_MEMBERS,
        _with_btc_eth(market),
        Signals(top_ls=empty, acct_ls=empty, oi_value=empty, taker_share=share),
    )
    day = days[-5]
    expected = {names[j]: w for j, w in fn(market, len(days) - 5).items() if abs(w) > 1e-12}
    got = weights_from_frames(close, qv, taker, day)["weights"]
    assert got.keys() == expected.keys()
    assert all(got[s] == pytest.approx(expected[s]) for s in got)
    assert sum(abs(w) for w in got.values()) <= 1.0 + 1e-9  # members can net out


def _with_btc_eth(market):
    # weight_fn looks up BTC/ETH indices; the test panel has neither, so alias two columns.
    market.symbols = list(market.symbols)
    market.symbols[-2], market.symbols[-1] = "BTCUSDT", "ETHUSDT"
    return market


def test_decision_days_are_sundays():
    assert is_decision_day(pd.Timestamp("2026-10-25", tz="UTC"))
    assert not is_decision_day(pd.Timestamp("2026-10-26", tz="UTC"))


def test_monday_rebalance_reaches_targets_and_reruns_without_orders(tmp_path):
    exchange, client, store = make(tmp_path)
    report = run_executor(client, store, now=MONDAY)
    assert report["status"] == "ok", report.get("error") or report.get("mismatch")
    weights = report["signal"]["weights"]
    assert weights and len(report["signal"]["universe"]) == 20
    held = {s: q for s, q in exchange.positions.items() if q}
    assert set(held) == set(weights)
    for s, w in weights.items():
        assert (held[s] > 0) == (w > 0)
        assert abs(held[s] * exchange.price[s] - Decimal(str(w)) * 1000) < exchange.price[s]
    assert all(exchange.config[s]["marginType"] == "CROSSED" for s in held)
    placed = exchange.placed
    again = run_executor(client, store, now=MONDAY + pd.Timedelta(minutes=5))
    assert again["status"] == "ok" and again["results"] == [] and exchange.placed == placed
    tuesday = run_executor(client, store, now=MONDAY + pd.Timedelta(days=1))
    assert tuesday["rebalance"] is False and tuesday["results"] == []
    assert run_guard(client, store, now=MONDAY + pd.Timedelta(days=1))["status"] == "ok"


def test_unlisted_symbols_stay_in_cash(tmp_path):
    exchange = MultiExchange(listed=[s for s in NAMES if s != "A01USDT"])
    exchange, client, store = make(tmp_path, exchange)
    report = run_executor(client, store, now=MONDAY)
    if "A01USDT" in report["signal"]["weights"]:
        assert report["skipped"]["A01USDT"] == "not listed on this venue"
    assert exchange.positions["A01USDT"] == 0
    assert report["status"] == "ok"


def test_guard_waits_for_the_executor_lock(tmp_path):
    _, client, store = make(tmp_path)
    with state_lock(store.root, wait=False) as got:
        assert got
        assert run_guard(client, store, now=MONDAY)["status"] == "busy"


def test_guard_mismatch_and_loss_stop_flatten_every_symbol(tmp_path):
    exchange, client, store = make(tmp_path)
    run_executor(client, store, now=MONDAY)
    exchange.positions["A23USDT"] = Decimal("1")  # a position the executor did not record
    report = run_guard(client, store, now=MONDAY + pd.Timedelta(minutes=10))
    assert report["status"] == "triggered"
    assert "position_mismatch_A23USDT" in report["reasons"]
    assert all(q == 0 for q in exchange.positions.values())
    assert run_executor(client, store, now=MONDAY + pd.Timedelta(days=7))["status"] == "halted"

    exchange, client, store = make(tmp_path / "b")
    run_executor(client, store, now=MONDAY)
    report = run_guard(client, store, now=MONDAY, test_stop_equity=Decimal(5000))
    assert report["status"] == "triggered" and report["reasons"] == ["loss_stop"]
    assert all(q == 0 for q in exchange.positions.values())


def test_client_allowlist_widens_only_on_request():
    client = FuturesClient("demo", Credentials("k", "s"), transport=MultiExchange(), symbols=())
    with pytest.raises(PermissionError):
        client.book("A00USDT")
    client.allow(["A00USDT"])
    assert client.book("A00USDT")["bid"] > 0
    assert client.public_daily_klines("A05USDT")  # Mainnet public reads are not restricted
