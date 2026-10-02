import json
from pathlib import Path

import pandas as pd
import pytest

from v3.phase2.basket import NORMAL_COST, Rule, simulate_basket
from v3.phase2.data import Phase2Panel, load_phase2_panel
from v3.phase2.maker import (
    H3_NORMAL,
    H3T_NORMAL,
    DailyRule,
    MakerPanel,
    h3_grid,
    simulate_maker_basket,
)

ROOT = Path(__file__).resolve().parents[1]
SYMBOLS = ("A", "B", "C", "D")
T0 = pd.Timestamp("2026-01-01", tz="UTC")


def make_panel(days=30, *, through_bps=3.0, funding=None):
    """Flat prices at 100. The hourly range is +/- through_bps around the open."""
    hours = pd.date_range(T0, periods=days * 24, freq="1h")
    flat = pd.DataFrame(100.0, index=hours, columns=list(SYMBOLS))
    band = through_bps / 10_000.0
    settlements = hours[hours.hour % 8 == 0]
    funding = funding or {"A": 0.001, "B": 0.0002, "C": -0.0002, "D": -0.001}
    rates = pd.DataFrame(
        {
            s: [funding[s](t) if callable(funding[s]) else funding[s] for t in settlements]
            for s in SYMBOLS
        },
        index=settlements,
    )
    base = Phase2Panel(open=flat, close=flat, mark=flat, funding=rates, symbols=SYMBOLS)
    return MakerPanel(base, flat * (1 + band), flat * (1 - band))


def rule(**overrides):
    values = dict(hypothesis="H3", k=1, window_hours=24)
    values.update(overrides)
    return DailyRule(**values)


def run(panel, *, execution=H3_NORMAL, days=30, **rule_overrides):
    return simulate_maker_basket(
        panel,
        rule(**rule_overrides),
        execution=execution,
        start=T0,
        end=T0 + pd.Timedelta(days=days) - pd.Timedelta(hours=1),
    )


def test_grid_is_the_registered_four_points():
    labels = [r.label() for r in h3_grid()]
    assert labels == ["H3 W=168h k=2", "H3 W=168h k=3", "H3 W=336h k=2", "H3 W=336h k=3"]
    assert all(r.min_hold_days == 5 and r.max_hold_days == 14 for r in h3_grid("H3T"))
    with pytest.raises(ValueError):
        h3_grid("H1")


def test_trade_through_fills_maker_at_the_limit_with_maker_fee():
    result = run(make_panel(through_bps=3.0), days=3)
    fills = result.extra
    # Entry pair on day 1, nothing else until the end-of-window taker close.
    assert fills["maker_orders"] == 2 and fills["maker_filled"] == 2
    assert fills["taker_fallback"] == 0 and fills["maker_fill_rate"] == 1.0
    # 2 legs x 150 USDT at 2 bps maker, then 2 x 150 at 5 bps taker + 2 bps slippage.
    assert result.decomposition["fees"] == pytest.approx(300 * 0.0002 + 300 * 0.0005)
    assert result.decomposition["slippage"] == pytest.approx(300 * 0.0002)


def test_no_trade_through_falls_back_to_taker_one_hour_later():
    result = run(make_panel(through_bps=1.0), days=3)
    fills = result.extra
    assert fills["maker_orders"] == 2 and fills["maker_filled"] == 0
    assert fills["taker_fallback"] == 2 and fills["maker_fill_rate"] == 0.0
    assert result.decomposition["fees"] == pytest.approx(600 * 0.0005)


def test_taker_diagnostic_executes_planned_trades_at_the_first_open():
    result = run(make_panel(through_bps=3.0), execution=H3T_NORMAL, days=3)
    assert result.extra["maker_orders"] == 0 and result.extra["taker_planned"] == 2


def test_decisions_happen_once_per_day_at_midnight():
    result = run(make_panel(), days=10)
    # Scores exist from day 0 16:00, so decisions run at 00:00 on days 1..9.
    assert result.decisions == 9


def test_minimum_hold_blocks_rank_exit_for_five_days():
    switch = T0 + pd.Timedelta(days=3)
    panel = make_panel(
        days=12,
        funding={
            "A": lambda t: 0.001 if t < switch else -0.001,
            "B": 0.0002,
            "C": lambda t: -0.0002 if t < switch else 0.002,
            "D": -0.001,
        },
    )
    result = run(panel, days=12)
    # A is shorted at the day-1 decision. Its rank collapses from day 3, but it is
    # locked until the day-6 decision, when C replaces it. A therefore receives
    # 5 settlements at +0.001 and 10 at -0.001 on a 150 USDT short.
    assert result.per_symbol["A"]["funding_pnl"] == pytest.approx(150 * (5 - 10) * 0.001)
    # C is short from day 6 01:00: 17 settlements at 0.002 up to day 11 16:00.
    assert result.per_symbol["C"]["funding_pnl"] == pytest.approx(150 * 17 * 0.002)


def test_hold_cap_closes_after_fourteen_days_and_skips_that_day():
    result = run(make_panel(days=20), days=20)
    assert result.forced_exits == 2
    # On the cap day A and D are excluded, so the basket rotates into B (short)
    # and C (long) at the same 01:00 maker attempt instead of re-entering A and D.
    assert result.extra["maker_notional"] == pytest.approx(300 + 600)
    # B is short from day 15 01:00: settlements day 15 08:00 .. day 19 16:00 = 14.
    assert result.per_symbol["B"]["funding_pnl"] == pytest.approx(150 * 14 * 0.0002)
    assert result.per_symbol["A"]["funding_pnl"] == pytest.approx(150 * 42 * 0.001)


def test_phase2_simulator_is_unchanged_on_the_frozen_panel():
    data_dir = ROOT / "user_data/data-phase2/binance/futures"
    manifest = ROOT / "evidence/phase2/data-manifest.json"
    recorded = ROOT / "research_results/phase2/results.json"
    if not data_dir.is_dir():
        pytest.skip("frozen Phase 2 data is not present locally")
    panel = load_phase2_panel(data_dir, manifest_path=manifest)
    fold = json.loads(recorded.read_text())["folds"][0]
    row = json.loads(recorded.read_text())["hypotheses"]["H1"]["normal"]["folds"][0]
    assert row["selected"] == "H1 W=168h k=3 s_min=0.5bp"
    start = pd.Timestamp(fold["validation_start"])
    end = pd.Timestamp(fold["validation_end"]) + pd.Timedelta(days=14)
    result = simulate_basket(
        panel,
        Rule("H1", k=3, window_hours=168, spread_min=0.00005),
        cost=NORMAL_COST,
        start=start,
        end=end,
        entry_end=pd.Timestamp(fold["validation_end"]),
    )
    expected = row["validation_summary"]["decomposition"]
    for key, value in expected.items():
        assert result.decomposition[key] == pytest.approx(value, rel=1e-12, abs=1e-12)
