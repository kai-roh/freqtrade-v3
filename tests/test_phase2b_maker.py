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
from v3.phase2.research import Phase2Config, pbo_window

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


def test_phase2_pbo_window_stops_at_the_last_exit_observation():
    from types import SimpleNamespace

    folds = [
        SimpleNamespace(train_start=pd.Timestamp("2025-07-07", tz="UTC")),
        SimpleNamespace(validation_end=pd.Timestamp("2026-07-16", tz="UTC")),
    ]
    panel_end = pd.Timestamp("2026-10-01 23:00", tz="UTC")
    assert pbo_window(folds, panel_end, Phase2Config()) == (
        pd.Timestamp("2025-07-07", tz="UTC"),
        pd.Timestamp("2026-07-30", tz="UTC"),
    )
    # The recorded 2026-09-17 run read to the panel end; the flag reproduces it.
    assert pbo_window(folds, panel_end, Phase2Config(pbo_through_panel_end=True))[1] == panel_end


def _beta_frame(betas, hours=24 * 40):
    """Hourly opens whose returns are exact multiples of a BTC return series."""
    import numpy as np

    index = pd.date_range(T0, periods=hours, freq="1h")
    rng = np.random.default_rng(7)
    btc = rng.normal(0, 0.004, hours)
    data = {"BTC": 100 * np.cumprod(1 + btc)}
    for symbol, beta in betas.items():
        data[symbol] = 100 * np.cumprod(1 + beta * btc)
    return pd.DataFrame(data, index=index)


def test_betas_use_only_data_before_the_decision():
    from v3.phase2.maker import estimate_betas

    frame = _beta_frame({"X": 2.0, "Y": 0.5})
    t = frame.index[-1]
    betas = estimate_betas(frame, t, 30, (0.25, 4.0))
    assert betas["BTC"] == pytest.approx(1.0)
    assert betas["X"] == pytest.approx(2.0, rel=1e-6) and betas["Y"] == pytest.approx(0.5, rel=1e-6)
    # Changing the decision-hour price must not change the estimate.
    shocked = frame.copy()
    shocked.loc[t, "X"] *= 3
    assert estimate_betas(shocked, t, 30, (0.25, 4.0))["X"] == pytest.approx(betas["X"])


def test_beta_sizing_keeps_gross_and_equalises_beta_notional():
    from v3.phase2.maker import RiskVariant, _risk_targets
    from v3.phase2.signals import Selection

    frame = _beta_frame({"X": 2.0, "Y": 0.5})
    t = frame.index[-1]
    diag = {"min_notional_skips": 0, "balance_full_exits": 0}
    targets, legs = _risk_targets(
        RiskVariant("V2", beta=True),
        Selection(("X",), ("Y",)),
        150.0,
        frame.loc[t],
        frame,
        t,
        {},
        diag,
    )
    assert abs(targets["X"]) + targets["Y"] == pytest.approx(300.0)
    assert abs(targets["X"]) * 2.0 == pytest.approx(targets["Y"] * 0.5, rel=1e-6)
    assert legs == set()


def test_balance_shrinks_the_larger_side_and_exits_when_a_side_is_empty():
    from v3.phase2.maker import RiskVariant, _risk_targets
    from v3.phase2.signals import Selection

    frame = _beta_frame({"X": 1.0, "Y": 1.0, "Z": 1.0})
    t = frame.index[-1]
    diag = {"min_notional_skips": 0, "balance_full_exits": 0}
    targets, legs = _risk_targets(
        RiskVariant("V1", balance=True),
        Selection(("X",), ("Y", "Z")),
        50.0,
        frame.loc[t],
        frame,
        t,
        {},
        diag,
    )
    assert targets["X"] == pytest.approx(-50.0)
    assert targets["Y"] == pytest.approx(25.0) and targets["Z"] == pytest.approx(25.0)
    assert legs == {"Y", "Z"}
    empty, _ = _risk_targets(
        RiskVariant("V1", balance=True),
        Selection((), ("Y",)),
        50.0,
        frame.loc[t],
        frame,
        t,
        {},
        diag,
    )
    assert empty == {} and diag["balance_full_exits"] == 1


def test_venue_filters_floor_to_lot_and_drop_legs_below_minimum():
    from v3.phase2.maker import RiskVariant, _risk_targets
    from v3.phase2.signals import Selection

    frame = _beta_frame({"X": 1.0, "Y": 1.0})
    t = frame.index[-1]
    price = float(frame.loc[t, "X"])
    filters = {"BTC": (50.0, 1.0), "X": (5.0, 0.01), "Y": (5.0, 10.0)}
    diag = {"min_notional_skips": 0, "balance_full_exits": 0}
    targets, _ = _risk_targets(
        RiskVariant("V0c", venue_filters=filters),
        Selection(("X",), ("Y",)),
        50.0,
        frame.loc[t],
        frame,
        t,
        {},
        diag,
    )
    # X floors to whole 0.01 lots; Y's 10-unit lot is worth far more than 50 USDT, so it is dropped.
    assert targets["X"] == pytest.approx(-int(50 / price / 0.01) * 0.01 * price)
    assert "Y" not in targets and diag["min_notional_skips"] == 1
