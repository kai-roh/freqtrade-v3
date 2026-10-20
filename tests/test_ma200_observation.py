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
    reconcile_live,
    render_message,
    summarize_live,
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


def test_live_reconciliation_flags_large_gaps_only():
    inputs = panels()
    report = observe(inputs, now=START + pd.Timedelta(days=5, hours=2), start=START)
    virtual = report["accounts"]["MA200"]["positions"]
    close = {f"{a}USDT": str(v["qty"]) for a, v in virtual.items()}
    reconcile_live(report, close)
    assert report["checks"]["live_matches_virtual"] is True
    assert "Demo 실행 대사" in render_message(report, weekly=False, monthly=False)
    far = {f"{a}USDT": str(v["qty"] * 3 + 1) for a, v in virtual.items()}
    reconcile_live(report, far)
    assert report["checks"]["live_matches_virtual"] is False


def test_period_pnl_follows_the_daily_reports():
    """24h P&L is the change since yesterday's report, not since 00:00 UTC (one hour)."""
    inputs = panels()
    now = START + pd.Timedelta(days=12, hours=2, minutes=10)
    today = observe(inputs, now=now, start=START)
    yesterday = observe(inputs, now=now - pd.Timedelta(days=1), start=START)
    for name, account in today["accounts"].items():
        before = yesterday["accounts"][name]
        assert account["pnl_day"] == pytest.approx(account["equity"] - before["equity"])
        # The current week and month are the sums of their daily reports so far.
        assert account["weekly"][-1]["pnl"] == pytest.approx(account["pnl_week"])
        assert account["monthly"][-1]["pnl"] == pytest.approx(account["pnl_month"])
        assert account["weekly"][-1]["complete"] is False
        assert all(row["complete"] for row in account["weekly"][:-1])
    end = pd.Timestamp(today["evaluated_to"])
    monday = end - pd.Timedelta(days=(end + pd.Timedelta(hours=9)).weekday())
    if monday - pd.Timedelta(days=1) > START:
        sunday_run = monday - pd.Timedelta(days=1) + pd.Timedelta(hours=1, minutes=10)
        week_open = observe(inputs, now=sunday_run, start=START)
        ma = today["accounts"]["MA200"]
        assert ma["pnl_week"] == pytest.approx(
            ma["equity"] - week_open["accounts"]["MA200"]["equity"]
        )


def test_demo_summary_uses_executor_runs_up_to_the_report():
    inputs = panels()
    now = START + pd.Timedelta(days=8, hours=2, minutes=10)
    report = observe(inputs, now=now, start=START)

    def run(days, equity):
        t = START + pd.Timedelta(days=days, hours=1, minutes=5)
        return {"now": t.isoformat(), "equity": {"equity": str(equity), "distance_to_stop": "1"}}

    runs = [
        run(0, 990.0),
        {"now": (START + pd.Timedelta(days=1)).isoformat(), "status": "halted"},
        run(7, 1004.0),
        run(8, 1001.0),
        run(9, 1500.0),  # after the report time: ignored in a replay
    ]
    summarize_live(report, runs, 1000.0)
    live = report["live"]
    assert live["equity"] == 1001.0 and live["pnl_total"] == pytest.approx(1.0)
    assert live["pnl_day"] == pytest.approx(-3.0)
    assert sum(live["weekly"].values()) == pytest.approx(1.0)
    assert sum(live["monthly"].values()) == pytest.approx(1.0)
    assert report["checks"]["live_executor_fresh"] is True
    message = render_message(report, weekly=True, monthly=False)
    assert "Demo 실제: 자산 1,001.00 USDT" in message and "| Demo 실제" in message
    # A stale executor is shown and fails the check.
    later = observe(inputs, now=now + pd.Timedelta(days=2), start=START)
    summarize_live(later, runs[:4], 1000.0)
    assert later["checks"]["live_executor_fresh"] is False
    assert "마지막 실행" in render_message(later, weekly=False, monthly=False)
