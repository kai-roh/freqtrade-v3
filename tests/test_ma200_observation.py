import json
import math

import numpy as np
import pandas as pd
import pytest

from v3.phase1.notifications import send_telegram_text
from v3.phase2.data import Phase2Panel
from v3.phase2c.observation import (
    ObservationInputs,
    last_complete_hour,
    observe,
    render_message,
)
from v3.phase2c.trend import NORMAL, TrendRule, VenueFilters, simulate_trend

SYMBOLS = ("BTC", "ETH")
T0 = pd.Timestamp("2025-06-01", tz="UTC")
DAYS = 300
START = T0 + pd.Timedelta(days=260)


def panels(seed=3):
    hours = pd.date_range(T0, periods=DAYS * 24, freq="1h")
    rng = np.random.default_rng(seed)
    steps = 0.001 / 24 + 0.03 / math.sqrt(24) * rng.standard_normal((len(hours), 2))
    prices = pd.DataFrame(
        100.0 * np.exp(np.cumsum(steps, axis=0)) * [800.0, 30.0], index=hours, columns=list(SYMBOLS)
    )
    settlements = hours[hours.hour % 8 == 0]
    funding = pd.DataFrame(0.0001, index=settlements, columns=list(SYMBOLS))
    perp = Phase2Panel(open=prices, close=prices, mark=prices, funding=funding, symbols=SYMBOLS)
    no_funding = pd.DataFrame(
        columns=list(SYMBOLS), index=pd.DatetimeIndex([], tz="UTC"), dtype=float
    )
    spot = Phase2Panel(open=prices, close=prices, mark=prices, funding=no_funding, symbols=SYMBOLS)
    perp_filters = VenueFilters(
        step={"BTC": 0.001, "ETH": 0.001}, min_notional={"BTC": 50, "ETH": 20}
    )
    spot_filters = VenueFilters(
        step={"BTC": 0.00001, "ETH": 0.0001},
        min_notional={"BTC": 5, "ETH": 5},
        reduce_only_exempt=False,
    )
    return ObservationInputs(perp, spot, perp_filters, spot_filters)


def test_last_complete_hour():
    assert last_complete_hour(pd.Timestamp("2026-10-03 02:10", tz="UTC")) == pd.Timestamp(
        "2026-10-03 01:00", tz="UTC"
    )


def test_before_the_start_only_previews_the_signal():
    inputs = panels()
    report = observe(inputs, now=START - pd.Timedelta(hours=5), start=START)
    assert report["status"] == "not_started" and report["orders_submitted"] is False
    assert set(report["signal"]["weights"]) == set(SYMBOLS)
    message = render_message(report, weekly=False, monthly=False)
    assert message.startswith("[관측][MA200] 관측 시작 전")


def test_running_accounts_add_up_and_render():
    inputs = panels()
    now = START + pd.Timedelta(days=20, hours=2, minutes=10)
    report = observe(inputs, now=now, start=START)
    assert report["status"] == "running" and report["dry_run_day"] == 21
    for account in report["accounts"].values():
        assert account["equity"] == pytest.approx(1000.0 + account["pnl_total"])
        assert sum(r["pnl"] for r in account["weekly"]) == pytest.approx(account["pnl_total"])
        assert sum(r["pnl"] for r in account["monthly"]) == pytest.approx(account["pnl_total"])
    # Spot never holds a short and never pays funding.
    spot = report["accounts"]["현물 보유"]
    assert all(p["qty"] >= 0 for p in spot["positions"].values())
    assert spot["decomposition"]["funding_pnl"] == 0.0
    message = render_message(report, weekly=True, monthly=True)
    assert "주문 없음" in message and "주간 손익표" in message and "월간 손익표" in message
    json.dumps(report, default=str)


def test_stale_data_fails_the_checks():
    inputs = panels()
    now = inputs.perp.open.index[-1] + pd.Timedelta(days=2)
    report = observe(inputs, now=now, start=START)
    assert report["checks"]["perp_data_fresh"] is False
    assert "점검 실패" in render_message(report, weekly=False, monthly=False)


def test_observation_mode_keeps_positions_open_and_marks_them():
    inputs = panels()
    end = START + pd.Timedelta(days=10)
    kept = simulate_trend(
        inputs.perp,
        [(START, TrendRule("bh_vt"))],
        cost=NORMAL,
        start=START,
        end=end,
        sleeve=1000,
        flatten_at_end=False,
    )
    closed = simulate_trend(
        inputs.perp, [(START, TrendRule("bh_vt"))], cost=NORMAL, start=START, end=end, sleeve=1000
    )
    assert all(q > 0 for q in kept.extra["open_positions"].values())
    assert all(q == 0 for q in closed.extra["open_positions"].values())
    # Same path; the closed account only adds the final exit costs.
    gap = kept.decomposition["total_pnl"] - closed.decomposition["total_pnl"]
    assert gap == pytest.approx(
        closed.decomposition["fees"]
        + closed.decomposition["slippage"]
        - kept.decomposition["fees"]
        - kept.decomposition["slippage"]
    )


def test_plain_telegram_text_delivery_contract():
    sent = []

    class Response:
        def __init__(self, body):
            self.body = body

        def read(self):
            return json.dumps(self.body).encode()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def opener(request, timeout):
        sent.append(request)
        return Response({"ok": True})

    assert send_telegram_text("hello", token="t", chat_id="c", opener=opener).delivered
    assert len(sent) == 1
    missing = send_telegram_text("hello", token="", chat_id="c", opener=opener)
    assert not missing.delivered and missing.error_type == "missing_credentials"
