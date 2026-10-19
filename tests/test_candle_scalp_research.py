"""Portfolio accounting, paired comparisons and frozen research boundaries."""

import json
from types import SimpleNamespace

import pandas as pd
import pytest

from scripts.build_divergence_dataset import sha256
from scripts.run_candle_scalp_research import (
    load_study,
    marked_daily,
    paired_comparison,
    portfolio_summary,
    worst_dates,
)


def result_fixture():
    times = pd.DatetimeIndex(["2025-10-02T00:00Z", "2025-10-02T00:01Z"])
    equity = pd.DataFrame(
        {
            "equity": [501.0, 502.0],
            "exposure": [100.0, 0.0],
            "filled_notional_peak": [100.0, 100.0],
        },
        index=times,
    )
    trades = pd.DataFrame(
        {
            "net_pnl": [2.0],
            "price_pnl": [2.3],
            "fees": [0.2],
            "slippage_cost": [0.1],
            "funding_pnl": [0.0],
            "holding_minutes": [2.0],
            "exit_reason": ["target"],
            "exit_time": [times[-1]],
        }
    )
    fills = pd.DataFrame({"kind": ["entry", "exit"], "timestamp": times})
    return SimpleNamespace(
        equity=equity,
        trades=trades,
        fills=fills,
        summary={"initial_equity": 500, "net_pnl": 2, "trades": 1},
    )


def test_midnight_close_belongs_to_preceding_utc_day():
    series = pd.Series(
        [1.0, 2.0], index=pd.DatetimeIndex(["2025-10-02T00:00Z", "2025-10-02T00:01Z"])
    )
    result = marked_daily(series)
    assert list(result.index.strftime("%Y-%m-%d")) == ["2025-10-01", "2025-10-02"]
    assert list(result) == [1.0, 2.0]


def test_portfolio_reconciles_marked_and_closed_pnl_without_double_counting():
    results = {s: result_fixture() for s in ("BTC", "ETH")}
    signals = {
        s: pd.DataFrame({"entry_signal": [True]}, index=pd.DatetimeIndex(["2025-10-01T00:30Z"]))
        for s in results
    }
    summary, trades, fills, daily = portfolio_summary(results, signals)
    assert summary["net_pnl"] == pytest.approx(4)
    assert summary["price_pnl"] - summary["fees"] - summary["slippage_cost"] == pytest.approx(4)
    assert daily.pnl.sum() == pytest.approx(4)
    assert summary["max_exposure"] == 200
    assert summary["entry_fills"] == 2
    assert len(trades) == 2 and len(fills) == 4
    assert len(summary["two_month_pnl"]) == 6
    json.dumps(summary, allow_nan=False)


def test_broken_campaign_ledger_fails_closed():
    results = {s: result_fixture() for s in ("BTC", "ETH")}
    results["BTC"].trades.loc[0, "net_pnl"] = 100
    signals = {
        s: pd.DataFrame({"entry_signal": [False]}, index=pd.DatetimeIndex(["2025-10-01T00:30Z"]))
        for s in results
    }
    with pytest.raises(ValueError, match="ledger"):
        portfolio_summary(results, signals)


def test_paired_comparison_includes_inactive_days_and_labels_extra_exposure():
    index = pd.date_range("2025-10-01", periods=365, tz="UTC")
    single = pd.DataFrame({"pnl": [0.0] * 365, "mean_exposure": [10.0] * 365}, index=index)
    averaged = single.copy()
    averaged.loc[index[0], "pnl"] = -5
    averaged["mean_exposure"] = 20
    paired = paired_comparison(single, averaged)
    assert paired["net_pnl_difference"] == -5
    assert paired["bootstrap_daily_difference"]["mean_daily_pnl"] == pytest.approx(-5 / 365)
    assert paired["equal_risk_comparison"] is False
    assert paired["averaging_mean_exposure"] == 20
    with pytest.raises(ValueError, match="dates"):
        paired_comparison(single.iloc[1:], averaged)


def test_worst_days_use_previous_close_and_date_tie_breaker():
    dates = pd.date_range("2025-09-30", periods=13, tz="UTC")
    frame = pd.DataFrame({"close": [100.0, 90.0, 81.0] + [81.0] * 10}, index=dates)
    worst = worst_dates(frame)
    assert len(worst) == 10
    assert worst.index[0] == dates[1]
    assert worst.index[1] == dates[2]
    assert worst.iloc[0] == pytest.approx(-0.1)


def test_changed_study_registration_or_source_manifest_rejected(tmp_path):
    registration = tmp_path / "rules.md"
    source = tmp_path / "source.json"
    registration.write_text("frozen")
    source.write_text("{}")
    manifest = tmp_path / "study.json"
    manifest.write_text(
        json.dumps(
            {
                "registration": str(registration),
                "registration_sha256": sha256(registration),
                "source_manifest": str(source),
                "source_manifest_sha256": "0" * 64,
            }
        )
    )
    with pytest.raises(ValueError, match="Source data manifest changed"):
        load_study(manifest)
    registration.write_text("changed")
    with pytest.raises(ValueError, match="registration changed"):
        load_study(manifest)
