import numpy as np
import pandas as pd
import pytest

from v3.divergence import DivergenceConfig, backtest, prepare_signals


def market(rows=8):
    frame = pd.DataFrame(
        {"open": 100.0, "high": 100.3, "low": 99.8, "close": 100.0, "volume": 10.0},
        index=pd.date_range("2025-01-01", periods=rows, freq="1min", tz="UTC"),
    )
    frame["entry_signal"] = False
    frame["stop"] = 99.0
    frame["target"] = 102.0
    frame.loc[frame.index[0], "entry_signal"] = True
    return frame


def config(**kwargs):
    return DivergenceConfig(min_notional=0, **kwargs)


def test_stop_first_when_both_touched_and_no_confirmation_bar_fill():
    bars = market()
    bars.loc[bars.index[0], ["high", "low"]] = [110, 90]
    bars.loc[bars.index[1], ["high", "low"]] = [103, 98]
    result = backtest(bars, config(), prepared=True)
    trade = result.trades.iloc[0]
    assert trade.entry_time == bars.index[1]
    assert trade.exit_reason == "stop"
    assert trade.entry_price == pytest.approx(100.02)
    assert trade.exit_price == pytest.approx(99 * 0.9998)
    expected = trade.quantity * (trade.exit_price - trade.entry_price)
    expected -= trade.quantity * (trade.entry_price + trade.exit_price) * 0.0005
    assert trade.net_pnl == pytest.approx(expected)
    assert result.summary["net_pnl"] == pytest.approx(expected)
    assert -expected <= 2.5


def test_gap_stop_uses_worse_open_and_can_exceed_budget():
    bars = market()
    bars.loc[bars.index[2], ["open", "low", "high", "close"]] = [95, 94, 96, 95]
    result = backtest(bars, config(), prepared=True)
    trade = result.trades.iloc[0]
    assert trade.exit_price == pytest.approx(95 * 0.9998)
    assert trade.net_pnl < -2.5


def test_target_gap_does_not_receive_better_open():
    bars = market()
    bars.loc[bars.index[2], ["open", "high", "low", "close"]] = [105, 106, 104, 105]
    result = backtest(bars, config(), prepared=True)
    assert result.trades.iloc[0].exit_price == pytest.approx(102 * 0.9998)


def test_quantity_rounding_and_minimum_notional():
    bars = market()
    result = backtest(bars, config(lot_step=0.1), prepared=True)
    trade = result.trades.iloc[0]
    assert trade.quantity == pytest.approx(2.1)
    assert trade.quantity * trade.entry_price <= 500
    skipped = backtest(bars, DivergenceConfig(min_notional=300), prepared=True)
    assert skipped.trades.empty
    assert skipped.summary["skipped_signals"] == 1


def test_funding_cash_and_marked_equity_are_reconciled():
    bars = market()
    bars.loc[bars.index[2:5], "close"] = 99.85
    rates = pd.DataFrame(
        {"funding_rate": [0.001, -0.0005], "mark_price": [100, 100]},
        index=[bars.index[1], bars.index[3]],
    )
    result = backtest(bars, config(), rates, prepared=True)
    trade = result.trades.iloc[0]
    # A position opened at the settlement time does not receive that settlement.
    assert trade.funding == pytest.approx(-trade.quantity * 100 * 0.0005)
    assert result.equity.unrealized_pnl.iloc[2] < 0
    assert result.equity.equity.iloc[2] == pytest.approx(
        result.equity.cash.iloc[2] + trade.quantity * (99.85 - trade.entry_price)
    )
    assert result.summary["net_pnl"] == pytest.approx(trade.net_pnl)
    assert result.summary["max_drawdown_pct"] < 0


def test_timeout_after_ten_complete_bars_no_same_bar_reentry():
    bars = market(15)
    bars.loc[bars.index[10], "entry_signal"] = True
    result = backtest(bars, config(), prepared=True)
    assert len(result.trades) == 1
    trade = result.trades.iloc[0]
    assert trade.exit_reason == "timeout"
    assert trade.exit_time == bars.index[11]


def test_end_force_close_and_no_future_signal_entry():
    bars = market()
    bars["entry_signal"] = False
    bars.loc[bars.index[-1], "entry_signal"] = True
    assert backtest(bars, config(), prepared=True).trades.empty
    bars.loc[bars.index[0], "entry_signal"] = True
    result = backtest(bars, config(), prepared=True)
    assert result.trades.iloc[0].exit_reason == "end"
    assert result.equity.unrealized_pnl.iloc[-1] == 0


def test_signal_prefix_invariance_including_partial_hour():
    rng = np.random.default_rng(42)
    n = 60 * 220 + 37
    close = 100 * np.exp(np.cumsum(rng.normal(0.00008, 0.001, n)))
    open_ = np.r_[close[0], close[:-1]]
    bars = pd.DataFrame(
        {
            "open": open_,
            "high": np.maximum(open_, close) * rng.uniform(1.0001, 1.002, n),
            "low": np.minimum(open_, close) * rng.uniform(0.998, 0.9999, n),
            "close": close,
            "volume": rng.uniform(1, 10, n),
        },
        index=pd.date_range("2025-01-01", periods=n, freq="1min", tz="UTC"),
    )
    full = prepare_signals(bars)
    for cut in (60 * 205, 60 * 210 + 23, n - 1):
        prefix = prepare_signals(bars.iloc[:cut])
        pd.testing.assert_frame_equal(prefix, full.iloc[:cut])
    assert not full.trend.iloc[: 60 * 200 - 1].any()
    assert full.trend.any()
    assert full.entry_signal.any(), "Fixture must exercise positive signals"


def test_strict_pivot_only_emitted_two_bars_later():
    bars = market(30)
    bars["low"] = 99.0
    bars.loc[bars.index[20], "low"] = 98
    signals = prepare_signals(bars)
    assert not signals.low_confirmed.iloc[:22].any()
    assert signals.low_confirmed.iloc[22]
    assert not signals.low_confirmed.iloc[23:].any()
    prefix = prepare_signals(bars.iloc[:22])
    assert not prefix.low_confirmed.any()


def test_missing_candles_rejected():
    with pytest.raises(ValueError, match="Missing candles"):
        backtest(market().drop(market().index[3]))


def test_cost_decomposition_reconciles_with_final_cash():
    bars = market()
    rates = pd.DataFrame({"funding_rate": [0.001]}, index=[bars.index[3]])
    result = backtest(bars, config(), rates, prepared=True)
    summary = result.summary
    assert summary["net_pnl"] == pytest.approx(
        summary["price_pnl"] - summary["slippage_cost"] - summary["fees"] + summary["funding_pnl"]
    )
    assert summary["slippage_cost"] > 0
    assert summary["fees"] > 0


@pytest.mark.parametrize("column", ["funding_rate", "mark_price"])
def test_invalid_funding_rejected(column):
    rates = pd.DataFrame(
        {"funding_rate": [0.001], "mark_price": [100.0]}, index=[market().index[3]]
    )
    rates[column] = np.nan
    with pytest.raises(ValueError, match="finite"):
        backtest(market(), config(), rates, prepared=True)


def test_naive_timestamps_rejected():
    bars = market()
    bars.index = bars.index.tz_localize(None)
    with pytest.raises(ValueError, match="timezone-aware"):
        prepare_signals(bars)


def test_five_minute_hour_uses_only_completed_twelve_candles():
    bars = market(12 * 204 + 11)
    bars.index = pd.date_range("2025-01-01", periods=len(bars), freq="5min", tz="UTC")
    bars["close"] = 100 + np.arange(len(bars)) * 0.01
    bars["open"] = bars.close
    bars["high"], bars["low"] = bars.close + 0.2, bars.close - 0.2
    full = prepare_signals(bars)
    assert not full.trend.iloc[12 * 200 - 2]
    assert full.trend.iloc[12 * 203 - 1]
    pd.testing.assert_frame_equal(prepare_signals(bars.iloc[:-5]), full.iloc[:-5])


def test_timeout_open_above_target_does_not_receive_gap_windfall():
    bars = market(15)
    bars.loc[bars.index[11], ["open", "high", "low", "close"]] = [105, 106, 104, 105]
    result = backtest(bars, config(), prepared=True)
    trade = result.trades.iloc[0]
    assert trade.exit_time == bars.index[11]
    assert trade.raw_exit_price == 102
    assert trade.exit_price == pytest.approx(102 * 0.9998)


def test_timeout_open_below_stop_keeps_adverse_gap():
    bars = market(15)
    bars.loc[bars.index[11], ["open", "high", "low", "close"]] = [95, 96, 94, 95]
    result = backtest(bars, config(), prepared=True)
    assert result.trades.iloc[0].exit_price == pytest.approx(95 * 0.9998)
