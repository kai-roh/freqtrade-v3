"""Synthetic execution contracts; no downloaded data required."""

import numpy as np
import pandas as pd
import pytest

from v3.candle_scalp import ScalpingConfig, backtest, prepare_signals


def bars(n=12, price=100.0):
    index = pd.date_range("2025-10-01", periods=n, freq="1min", tz="UTC")
    return pd.DataFrame(
        dict(open=price, high=price + 0.05, low=price - 0.05, close=price, volume=100.0),
        index=index,
    )


def signals(b, at=0, close=100.0, atr=1.0, **extra):
    return pd.DataFrame(
        [dict(close=close, atr=atr, entry_signal=True, bearish=True, breakout_level=99.0, **extra)],
        index=[b.index[at]],
    )


def cfg(**kw):
    return ScalpingConfig("pullback", min_notional=0.0, **kw)


def run(b, s=None, **kw):
    return backtest(b, signals(b) if s is None else s, cfg(**kw))


def test_closed_time_alignment_and_prefix():
    b = bars(240 * 55)
    b["close"] += np.sin(np.arange(len(b)) / 200) * 0.03
    whole = prepare_signals(b, "pullback")
    prefix = prepare_signals(b.iloc[:12001], "pullback")
    pd.testing.assert_frame_equal(prefix, whole.loc[prefix.index])
    assert whole.index[0] == b.index[0] + pd.Timedelta(minutes=30)
    assert prefix.index[-1] <= b.index[12000] + pd.Timedelta(minutes=1)
    assert not whole.entry_signal.any()


def test_strict_trade_through_touch_and_stress():
    b = bars()
    limit = 100 * (1 - 0.0002)
    b["low"] = limit * (1 - 0.0002)
    normal = run(b)
    assert normal.fills.empty
    assert normal.summary["unfilled_orders"] == 1
    b.loc[b.index[1], "low"] -= 0.00001
    assert run(b).summary["entry_fills"] == 1
    assert run(b, stress=True).summary["entry_fills"] == 0


def test_post_only_rejection_and_expiry():
    b = bars()
    b.loc[b.index[0], ["open", "low", "close"]] = 99.0
    assert run(b).summary["passive_rejections"] == 1
    b = bars()
    b["low"] = 99.97
    b.loc[b.index[5], "low"] = 99.9
    r = run(b)
    assert r.fills.empty
    assert r.summary["unfilled_orders"] == 1


def test_no_entry_minute_profit_and_stop_first():
    b = bars(3)
    b.loc[b.index[0], ["low", "high"]] = [99.9, 102.0]
    r = run(b)
    assert r.trades.exit_reason.tolist() == ["end"]
    b.loc[b.index[0], "low"] = 98.0
    r = run(b)
    assert r.trades.exit_reason.tolist() == ["stop"]
    assert r.trades.net_pnl.iloc[0] < 0


def test_target_no_gap_windfall_and_ledger():
    b = bars(3)
    b.loc[b.index[0], "low"] = 99.9
    b.loc[b.index[1], ["open", "high", "low", "close"]] = [103.0, 104.0, 102.0, 103.0]
    r = run(b)
    assert r.trades.exit_reason.tolist() == ["target"]
    assert r.trades.exit_price.iloc[0] == pytest.approx(99.98 * 1.003)
    assert r.trades.net_pnl.sum() == pytest.approx(r.summary["net_pnl"])
    assert r.summary["net_pnl"] == pytest.approx(
        r.summary["price_pnl"]
        - r.summary["fees"]
        - r.summary["slippage_cost"]
        + r.summary["funding_pnl"]
    )


def test_bounded_adds_fixed_stop_and_adverse_add_sequence():
    b = bars(10)
    b["high"] = 100.0
    b.loc[b.index[5] :, ["open", "high", "low", "close"]] = [99.5, 99.6, 99.45, 99.5]
    b.loc[b.index[0], "low"] = 99.9
    s = signals(b)
    for i, close in [(2, 99.4), (4, 98.9), (6, 98.8)]:
        s.loc[b.index[i]] = [close, 1.0, False, True, 99.0]
        b.loc[b.index[i], ["open", "low", "close", "high"]] = [
            close + 0.1,
            close - 0.05,
            close,
            101.0 if i < 6 else 99.6,
        ]
    r = run(b, s, averaging=True)
    assert r.summary["add_fills"] == 2
    assert r.trades.adds.iloc[0] == 2
    assert r.trades.stop.iloc[0] == pytest.approx(98.48)
    assert r.trades.exit_reason.iloc[0] == "end"
    assert (r.fills.query("kind != 'exit'").eval("quantity*price").sum()) <= 500


def test_campaign_risk_shrinks_initial_and_adds():
    b = bars(4)
    b.loc[b.index[0], "low"] = 99.9
    r = run(b, risk_usdt=0.2)
    entry = r.fills.iloc[0]
    stopfill = 98.48 * (1 - 0.0002)
    worst = (
        entry.quantity * (entry.price - stopfill) + entry.fee + entry.quantity * stopfill * 0.0005
    )
    assert worst <= 0.2 + 1e-10
    assert r.fills.quantity.iloc[0] / 0.001 == pytest.approx(
        round(r.fills.quantity.iloc[0] / 0.001)
    )


def test_funding_before_open_exit_not_on_entry():
    b = bars(4)
    b.loc[b.index[0], "low"] = 99.9
    funding = pd.DataFrame(
        dict(funding_rate=[0.01, 0.01], mark_price=[100.0, 100.0]), index=b.index[[0, 2]]
    )
    r = backtest(b, signals(b), cfg(), funding)
    quantity = r.fills.quantity.iloc[0]
    assert r.summary["funding_pnl"] == pytest.approx(-quantity)
    assert r.trades.net_pnl.sum() == pytest.approx(r.summary["net_pnl"])


def test_daily_and_account_halt_with_gap():
    b = bars(4)
    b.loc[b.index[0], "low"] = 99.9
    # Funding can cross risk thresholds before the next minute open.
    for rate, reason in [(0.06, "daily_halt"), (0.3, "account_halt")]:
        funding = pd.DataFrame(dict(funding_rate=[rate], mark_price=[100.0]), index=b.index[[1]])
        r = backtest(b, signals(b), cfg(), funding)
        assert r.trades.exit_reason.tolist() == [reason]
        assert r.trades.net_pnl.sum() == pytest.approx(r.summary["net_pnl"])


def test_breakout_invalidation_at_open_and_timeout_cap():
    b = bars(245)
    b.loc[b.index[0], "low"] = 99.9
    s = signals(b)
    s.loc[b.index[2]] = [98.0, 1.0, False, True, 99.0]
    r = backtest(b, s, ScalpingConfig("breakout", averaging=True, min_notional=0.0))
    assert r.trades.exit_reason.tolist() == ["breakout_failure"]
    assert r.summary["add_fills"] == 0
    r = run(b)
    assert r.trades.exit_reason.tolist() == ["timeout"]
    assert r.trades.holding_minutes.iloc[0] == 240


def test_final_forced_loss_and_minimum_refusal():
    b = bars(3)
    b.loc[b.index[0], "low"] = 99.9
    b.loc[b.index[-1], ["low", "close"]] = [99.0, 99.0]
    r = run(b)
    assert r.trades.net_pnl.iloc[0] < 0
    assert r.equity.unrealized_pnl.iloc[-1] == 0
    r = backtest(b, signals(b), ScalpingConfig("pullback", min_notional=300))
    assert r.summary["rounding_refusals"] == 1


@pytest.mark.parametrize("reason,at", [("breakout_failure", 2), ("timeout", 240)])
@pytest.mark.parametrize("gap", [False, True])
def test_open_exits_precede_unknown_intrabar_stop(reason, at, gap):
    b = bars(245)
    b.loc[b.index[0], "low"] = 99.9
    s = signals(b)
    if reason == "breakout_failure":
        s.loc[b.index[at]] = [98.0, 1.0, False, True, 99.0]
    b.loc[b.index[at], "low"] = 90.0
    if gap:
        b.loc[b.index[at], "open"] = 90.0
    r = backtest(b, s, ScalpingConfig("breakout", min_notional=0.0, risk_usdt=0.2))
    assert r.trades.exit_reason.tolist() == ["stop" if gap else reason]
    assert r.trades.exit_price.iloc[0] == pytest.approx((90 if gap else 100) * (1 - 0.0002))
    assert r.trades.exit_time.iloc[0] == b.index[at]


def test_intraminute_filled_notional_survives_same_minute_stop():
    b = bars(3)
    b.loc[b.index[0], "low"] = 98.0
    r = run(b)
    assert r.trades.exit_reason.tolist() == ["stop"]
    assert r.equity.exposure.iloc[0] == 0
    assert r.equity.filled_notional_peak.iloc[0] > 0
    assert r.summary["max_filled_notional"] == r.equity.filled_notional_peak.max()
    assert r.summary["max_filled_notional"] <= 500
    assert r.equity.filled_notional_peak.iloc[1] == 0


def test_intraminute_filled_notional_records_existing_position_before_open_exit():
    b = bars(4)
    b.loc[b.index[0], "low"] = 99.9
    b.loc[b.index[1], "low"] = 98.0
    r = run(b)
    assert r.equity.exposure.iloc[1] == 0
    assert r.equity.filled_notional_peak.iloc[1] == pytest.approx(
        r.fills.iloc[0].quantity * r.fills.iloc[0].price
    )


def regime_fixture(strategy):
    """Deterministic 30m regimes expanded to valid continuous minute candles."""
    n = 1800
    k = np.arange(n)
    if strategy == "range":
        close = 100 + np.sin(k * 0.15)
    else:
        close = 100 + 0.025 * k + 0.12 * np.sin(k * 0.4)
    volume = 100 + 20 * (1 + np.sin(k * 0.73))
    if strategy == "pullback":
        for point in (1500, 1600, 1700):
            close[point] = close[point - 1] - 0.9
            close[point + 1] = close[point] - 0.9
            volume[point : point + 2] = 600
    elif strategy == "breakout":
        for point in (1500, 1600, 1700):
            close[point] += 1.2
            volume[point] = 600
    else:
        volume[(k % 9) == 0] = 600
    opened = np.r_[close[0], close[:-1]]
    minute = np.tile(np.arange(30), n)
    block = np.repeat(k, 30)
    o = opened[block] + (close[block] - opened[block]) * minute / 30
    c = opened[block] + (close[block] - opened[block]) * (minute + 1) / 30
    high, low = np.maximum(o, c) + 0.01, np.minimum(o, c) - 0.01
    high[minute == 10] = np.maximum(opened[block[minute == 10]], close[block[minute == 10]]) + 0.15
    low[minute == 20] = np.minimum(opened[block[minute == 20]], close[block[minute == 20]]) - 0.15
    return pd.DataFrame(
        dict(open=o, high=high, low=low, close=c, volume=np.repeat(volume / 30, 30)),
        index=pd.date_range("2025-09-01", periods=n * 30, freq="1min", tz="UTC"),
    )


@pytest.mark.parametrize("strategy", ["pullback", "range", "breakout"])
def test_positive_signals_prefix_and_unfinished_higher_candle_invariance(strategy):
    b = regime_fixture(strategy)
    full = prepare_signals(b, strategy)
    positives = full.index[full.entry_signal]
    assert len(positives) >= 1, f"Fixture must exercise positive {strategy} signals"
    positive = positives[-1]
    # A complete positive signal, a partially formed next30m candle, and cuts
    # inside the next1h/4h block all retain exactly the already available rows.
    count = b.index.get_indexer([positive])[0]
    for length in (count, count + 7, count + 37, count + 127):
        prefix = prepare_signals(b.iloc[:length], strategy)
        pd.testing.assert_frame_equal(prefix, full.loc[prefix.index])
        assert prefix.index.max() <= b.index[length - 1] + pd.Timedelta(minutes=1)
        assert prefix.entry_signal.any()
    # Replace every future minute (including the unfinished higher-timeframe
    # candle) with a radically different valid tape; past positive signals stay.
    changed = b.copy()
    future = changed.index >= positive
    changed.loc[future, ["open", "high", "low", "close", "volume"]] = [
        50.0,
        80.0,
        20.0,
        40.0,
        10000.0,
    ]
    replay = prepare_signals(changed, strategy)
    pd.testing.assert_frame_equal(full.loc[:positive], replay.loc[:positive])
