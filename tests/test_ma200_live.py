import json
from decimal import Decimal
from urllib.parse import parse_qsl, urlsplit

import pandas as pd
import pytest

from v3.ma200live.client import Credentials, ExchangeError, FuturesClient
from v3.ma200live.engine import (
    LiveConfig,
    StateStore,
    plan_symbol,
    run_executor,
    run_guard,
    strategy_equity,
)

NOW = pd.Timestamp("2026-10-03 01:05", tz="UTC")
FILTERS = {
    "BTCUSDT": {"step": "0.001", "min_qty": "0.001", "tick": "0.1", "min_notional": "50"},
    "ETHUSDT": {"step": "0.001", "min_qty": "0.001", "tick": "0.01", "min_notional": "20"},
}


class FakeExchange:
    """In-memory USD-M venue: IOC fills, reduce-only rules, income, unknown outcomes."""

    def __init__(self, prices=None, trend=0.002):
        self.price = {
            "BTCUSDT": Decimal(prices[0] if prices else 100_000),
            "ETHUSDT": Decimal(prices[1] if prices else 4_000),
        }
        self.positions = {s: Decimal(0) for s in self.price}
        self.entry = {s: Decimal(0) for s in self.price}
        self.orders = {}
        self.income = []
        self.config = {s: {"marginType": "CROSSED", "leverage": 20} for s in self.price}
        self.fill_fraction = Decimal(1)
        self.fail_next_place = 0
        self.placed = 0
        self.trend = trend
        self.zero_avg = False

    def klines(self, symbol):
        rows = []
        start = NOW.floor("D") - pd.Timedelta(days=400)
        last = float(self.price[symbol])
        for i in range(400):
            day = start + pd.Timedelta(days=i)
            close = last * (1 + self.trend) ** (i - 399)
            open_ms = int(day.timestamp() * 1000)
            rows.append([open_ms, close, close, close, close, 0, open_ms + 86_399_999])
        return rows

    def __call__(self, method, url, headers, body):
        parts = urlsplit(url)
        query = dict(parse_qsl(parts.query))
        if body:
            query.update(dict(parse_qsl(body.decode())))
        path = parts.path
        if path == "/fapi/v1/time":
            return 200, {"serverTime": int(NOW.timestamp() * 1000)}
        if path == "/fapi/v1/klines":
            return 200, self.klines(query["symbol"])
        if path == "/fapi/v1/exchangeInfo":
            return 200, {
                "symbols": [
                    {
                        "symbol": s,
                        "filters": [
                            {
                                "filterType": "LOT_SIZE",
                                "stepSize": f["step"],
                                "minQty": f["min_qty"],
                            },
                            {"filterType": "PRICE_FILTER", "tickSize": f["tick"]},
                            {"filterType": "MIN_NOTIONAL", "notional": f["min_notional"]},
                        ],
                    }
                    for s, f in FILTERS.items()
                ]
            }
        if path == "/fapi/v1/ticker/bookTicker":
            p = self.price[query["symbol"]]
            return 200, {"bidPrice": str(p - 1), "askPrice": str(p + 1)}
        if path == "/fapi/v3/positionRisk":
            return 200, [
                {
                    "symbol": s,
                    "positionAmt": str(q),
                    "markPrice": str(self.price[s]),
                    "unRealizedProfit": str(q * (self.price[s] - self.entry[s])),
                }
                for s, q in self.positions.items()
            ]
        if path == "/fapi/v1/symbolConfig":
            return 200, [{"symbol": query["symbol"], **self.config[query["symbol"]]}]
        if path == "/fapi/v1/marginType":
            self.config[query["symbol"]]["marginType"] = query["marginType"]
            return 200, {"code": 200}
        if path == "/fapi/v1/leverage":
            self.config[query["symbol"]]["leverage"] = int(query["leverage"])
            return 200, {"leverage": int(query["leverage"])}
        if path == "/fapi/v1/openOrders":
            return 200, []
        if path == "/fapi/v1/allOpenOrders":
            return 200, {"code": 200}
        if path == "/fapi/v1/income":
            return 200, [r for r in self.income if r["time"] >= int(query["startTime"])]
        if path == "/fapi/v1/order" and method == "GET":
            order = self.orders.get(query["origClientOrderId"])
            return (200, order) if order else (400, {"code": -2013, "msg": "Order does not exist."})
        if path == "/fapi/v1/order" and method == "POST":
            return self.place(query)
        raise AssertionError(f"unexpected {method} {path}")

    def place(self, q):
        symbol, side, qty = q["symbol"], q["side"], Decimal(q["quantity"])
        signed = qty if side == "BUY" else -qty
        current = self.positions[symbol]
        if q.get("reduceOnly") == "true":
            if current == 0 or (current > 0) == (signed > 0):
                return 400, {"code": -2022, "msg": "ReduceOnly Order is rejected."}
            qty = min(qty, abs(current))
            signed = qty if side == "BUY" else -qty
        fill = (
            qty if q["type"] == "MARKET" else (qty * self.fill_fraction).quantize(Decimal("0.001"))
        )
        signed_fill = fill if side == "BUY" else -fill
        price = self.price[symbol]
        if (current > 0 and signed_fill < 0) or (current < 0 and signed_fill > 0):
            closed = min(abs(signed_fill), abs(current))
            pnl = closed * (price - self.entry[symbol]) * (1 if current > 0 else -1)
            self.income.append(
                {
                    "symbol": symbol,
                    "incomeType": "REALIZED_PNL",
                    "income": str(pnl),
                    "time": int(NOW.timestamp() * 1000),
                }
            )
        new = current + signed_fill
        if new != 0 and (current == 0 or (current > 0) != (new > 0)):
            self.entry[symbol] = price
        self.positions[symbol] = new
        self.income.append(
            {
                "symbol": symbol,
                "incomeType": "COMMISSION",
                "income": str(-fill * price * Decimal("0.0005")),
                "time": int(NOW.timestamp() * 1000),
            }
        )
        order = {
            "clientOrderId": q["newClientOrderId"],
            "status": "FILLED" if fill == qty else "EXPIRED",
            "executedQty": str(fill),
            "avgPrice": str(price),
            "cumQuote": str(fill * price),
        }
        self.orders[q["newClientOrderId"]] = order
        self.placed += 1
        if self.fail_next_place:
            self.fail_next_place -= 1
            return 503, {"msg": "timeout"}
        if self.zero_avg:  # immediate reply without settled prices; the query has them
            return 200, {**order, "avgPrice": "0.00", "cumQuote": "0.00000"}
        return 200, order


def make(tmp_path, exchange=None, environment="demo"):
    exchange = exchange or FakeExchange()
    client = FuturesClient(
        environment,
        Credentials("k", "s"),
        transport=exchange,
        authorization={"real_capital_authorized": True, "decision": "test"}
        if environment == "mainnet"
        else None,
    )
    store = StateStore(tmp_path)
    store.init(LiveConfig(environment=environment, start_ms=int(NOW.timestamp() * 1000) - 1))
    return exchange, client, store


def test_mainnet_is_locked_without_a_real_capital_decision():
    with pytest.raises(PermissionError):
        FuturesClient("mainnet", Credentials("k", "s"), transport=FakeExchange())
    with pytest.raises(PermissionError):
        FuturesClient(
            "mainnet",
            Credentials("k", "s"),
            transport=FakeExchange(),
            authorization={"real_capital_authorized": False, "decision": "x"},
        )


def test_only_allowlisted_symbols_and_endpoints():
    client = FuturesClient("demo", Credentials("k", "s"), transport=FakeExchange())
    with pytest.raises(PermissionError):
        client._call("GET", "/fapi/v1/ticker/bookTicker", {"symbol": "SOLUSDT"}, signed=False)
    with pytest.raises(PermissionError):
        client._call("POST", "/fapi/v1/transfer", {}, signed=True)


def flt(symbol):
    return {k: Decimal(v) for k, v in FILTERS[symbol].items()}


def test_plan_rules():
    config = LiveConfig("demo", 0)
    price = Decimal(100_000)
    # Within the threshold: no order.
    assert not plan_symbol("BTCUSDT", Decimal("0.002"), 0.45, price, config, flt("BTCUSDT")).steps
    # Flip: reduce-only close, then open.
    flip = plan_symbol("BTCUSDT", Decimal("0.002"), -0.4, price, config, flt("BTCUSDT"))
    assert [(s.purpose, s.reduce_only, s.qty) for s in flip.steps] == [
        ("close", True, Decimal("0.002")),
        ("open", False, Decimal("0.002")),
    ]
    # To flat: close only.
    flat = plan_symbol("BTCUSDT", Decimal("0.002"), 0.0, price, config, flt("BTCUSDT"))
    assert [s.purpose for s in flat.steps] == ["close"]
    # Reduce is reduce-only and exempt from the minimum notional.
    small = plan_symbol("ETHUSDT", Decimal("0.05"), 0.01, Decimal(4000), config, flt("ETHUSDT"))
    assert small.steps[0].reduce_only and small.steps[0].purpose == "reduce"
    # Opening below the minimum notional is skipped, not sent.
    tiny = plan_symbol("BTCUSDT", Decimal(0), 0.21, Decimal(400_000), config, flt("BTCUSDT"))
    assert not tiny.steps and tiny.skipped


def test_executor_enters_once_and_reruns_without_duplicates(tmp_path):
    exchange, client, store = make(tmp_path)
    first = run_executor(client, store, now=NOW)
    assert first["status"] == "ok"
    assert exchange.positions["BTCUSDT"] > 0 and exchange.positions["ETHUSDT"] > 0
    assert exchange.config["BTCUSDT"] == {"marginType": "ISOLATED", "leverage": 2}
    placed = exchange.placed
    second = run_executor(client, store, now=NOW + pd.Timedelta(minutes=10))
    assert second["status"] == "ok" and exchange.placed == placed
    heartbeat = store.heartbeat()
    assert heartbeat["last_success"] == (NOW + pd.Timedelta(minutes=10)).isoformat()
    assert Decimal(heartbeat["positions"]["BTCUSDT"]) == exchange.positions["BTCUSDT"]


def test_flip_override_is_demo_only_and_closes_before_opening(tmp_path):
    exchange, client, store = make(tmp_path)
    run_executor(client, store, now=NOW)
    report = run_executor(
        client, store, now=NOW + pd.Timedelta(minutes=5), override_weights={"BTCUSDT": -0.5}
    )
    assert report["status"] == "ok" and exchange.positions["BTCUSDT"] < 0
    purposes = [r["purpose"] for r in report["results"] if r["symbol"] == "BTCUSDT"]
    assert purposes == ["close", "open"]
    _, mainnet_client, mainnet_store = make(tmp_path / "m", environment="mainnet")
    with pytest.raises(PermissionError):
        run_executor(mainnet_client, mainnet_store, now=NOW, override_weights={"BTCUSDT": -0.5})


def test_partial_fills_retry_with_new_client_ids(tmp_path):
    exchange = FakeExchange()
    exchange.fill_fraction = Decimal("0.5")
    exchange, client, store = make(tmp_path, exchange)
    report = run_executor(client, store, now=NOW)
    btc = next(r for r in report["results"] if r["symbol"] == "BTCUSDT")
    assert len(btc["orders"]) >= 2
    assert len({o["client_id"] for o in btc["orders"]}) == len(btc["orders"])


def test_unknown_outcome_is_resolved_by_query_not_resent(tmp_path, monkeypatch):
    monkeypatch.setattr("v3.ma200live.engine.time.sleep", lambda _: None)
    exchange = FakeExchange()
    exchange.fail_next_place = 1  # the first order executes but the reply is a 503
    exchange, client, store = make(tmp_path, exchange)
    report = run_executor(client, store, now=NOW)
    assert report["status"] == "ok"
    first = report["results"][0]
    assert first["orders"][0]["status"] == "FILLED"
    # Exactly one order per step: the timed-out one was found, not sent twice.
    assert exchange.placed == len(report["results"])


def test_guard_loss_stop_flattens_and_halts_the_executor(tmp_path):
    exchange, client, store = make(tmp_path)
    run_executor(client, store, now=NOW)
    report = run_guard(client, store, now=NOW, test_stop_equity=Decimal(5000))
    assert report["status"] == "triggered" and "loss_stop" in report["reasons"]
    assert all(q == 0 for q in exchange.positions.values())
    assert store.halt() is not None
    halted = run_executor(client, store, now=NOW + pd.Timedelta(days=1))
    assert halted["status"] == "halted" and all(q == 0 for q in exchange.positions.values())
    store.clear_halt("reviewed in test", {"BTCUSDT": "0", "ETHUSDT": "0"})
    assert run_guard(client, store, now=NOW)["status"] == "ok"


def test_guard_stale_executor_and_position_mismatch(tmp_path):
    exchange, client, store = make(tmp_path)
    run_executor(client, store, now=NOW)
    stale = run_guard(client, store, now=NOW + pd.Timedelta(hours=51))
    assert "executor_stale" in stale["reasons"]
    exchange2, client2, store2 = make(tmp_path / "b")
    run_executor(client2, store2, now=NOW)
    exchange2.positions["ETHUSDT"] += Decimal("0.01")  # someone traded outside the executor
    mismatch = run_guard(client2, store2, now=NOW)
    assert "position_mismatch_ETHUSDT" in mismatch["reasons"]
    assert all(q == 0 for q in exchange2.positions.values())


def test_strategy_equity_counts_income_and_unrealized(tmp_path):
    exchange, client, store = make(tmp_path)
    run_executor(client, store, now=NOW)
    exchange.price["BTCUSDT"] += 1000
    equity = strategy_equity(client, store.config())
    expected_unrealized = exchange.positions["BTCUSDT"] * 1000
    assert equity["unrealized"] == pytest.approx(expected_unrealized)
    assert equity["equity"] == pytest.approx(
        Decimal(1000)
        + equity["commission"]
        + equity["realized"]
        + equity["funding"]
        + equity["unrealized"]
    )
    json.dumps({k: str(v) for k, v in equity.items()})


def test_exchange_errors_carry_codes():
    client = FuturesClient("demo", Credentials("k", "s"), transport=FakeExchange())
    assert client.order_by_client_id("BTCUSDT", "missing") is None
    with pytest.raises(ExchangeError):
        client.place_ioc(
            "BTCUSDT", "SELL", Decimal("0.001"), Decimal(100_000), reduce_only=True, client_id="x"
        )


def test_average_price_falls_back_to_cum_quote(tmp_path):
    exchange = FakeExchange()
    exchange.zero_avg = True
    exchange, client, store = make(tmp_path, exchange)
    report = run_executor(client, store, now=NOW)
    btc = next(r for r in report["results"] if r["symbol"] == "BTCUSDT")
    assert Decimal(btc["avg_price"]) == exchange.price["BTCUSDT"]


def test_stop_change_is_audited_and_used_by_the_guard(tmp_path):
    exchange, client, store = make(tmp_path)
    run_executor(client, store, now=NOW)
    with pytest.raises(ValueError):
        store.update_stop(Decimal(800), "")
    with pytest.raises(ValueError):
        store.update_stop(Decimal(1200), "above capital")
    assert store.update_stop(Decimal(800), "Decision 0021") == (Decimal(900), Decimal(800))
    assert store.config().stop_equity == Decimal(800)
    journal = (tmp_path / "journal.jsonl").read_text()
    assert '"event": "stop_changed"' in journal and '"to": "800"' in journal
    report = run_guard(client, store, now=NOW)
    assert report["status"] == "ok" and report["stop_used"] == "800"
