from pathlib import Path

import pandas as pd
import pytest

import v3.research as research
from v3.baselines import no_trade, volatility_breakout
from v3.research import (
    Candidate,
    ResearchConfig,
    _combine_portfolio_fold,
    _evaluate_portfolio,
    _exit_extended_index,
    _metric_frame,
    _run_slice,
    load_market_data,
    run_milestone_one,
)
from v3.risk import RiskConfig


def _candles(index: pd.DatetimeIndex) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": index,
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.5,
            "volume": 10.0,
        }
    )


def test_metric_frame_uses_gross_return_and_unit_notional():
    events = pd.DataFrame(
        {
            "gross_return": [0.01, -0.02],
            "pair": ["BTC/USDT:USDT", "BTC/USDT:USDT"],
            "side": ["long", "short"],
            "entry_time": pd.to_datetime(["2026-01-01", "2026-01-02"], utc=True),
            "exit_time": pd.to_datetime(["2026-01-01 01:00", "2026-01-02 01:00"], utc=True),
        }
    )

    trades = _metric_frame(events)

    assert trades["pnl"].tolist() == [0.01, -0.02]
    assert trades["notional"].tolist() == [1.0, 1.0]


def test_portfolio_fold_is_ordered_by_realized_exit_time():
    later_btc = pd.DataFrame(
        {
            "pnl": [-0.2],
            "pair": ["BTC/USDT:USDT"],
            "side": ["long"],
            "notional": [1.0],
            "entry_time": pd.to_datetime(["2026-01-02"], utc=True),
            "exit_time": pd.to_datetime(["2026-01-02 01:00"], utc=True),
        }
    )
    earlier_eth = pd.DataFrame(
        {
            "pnl": [0.1],
            "pair": ["ETH/USDT:USDT"],
            "side": ["long"],
            "notional": [1.0],
            "entry_time": pd.to_datetime(["2026-01-01"], utc=True),
            "exit_time": pd.to_datetime(["2026-01-01 01:00"], utc=True),
        }
    )

    combined = _combine_portfolio_fold([later_btc, earlier_eth])

    assert combined["pair"].tolist() == ["ETH/USDT:USDT", "BTC/USDT:USDT"]


def test_research_config_defaults_match_milestone_gate():
    config = ResearchConfig()
    assert config.fold_count == 6
    assert config.train_days == 90
    assert config.validation_days == 30
    assert config.capital_fraction_per_trade == 0.05
    assert config.embargo_hours == 6
    assert config.normal_cost_bps == 20.0
    assert config.stress_cost_bps == 30.0


def test_load_market_data_fails_closed_when_file_missing(tmp_path: Path):
    with pytest.raises(FileNotFoundError, match="missing research data"):
        load_market_data(tmp_path, "BTC/USDT:USDT", "15m")


def test_load_market_data_accepts_dense_ordered_candles(tmp_path: Path, monkeypatch):
    path = tmp_path / "BTC_USDT_USDT-15m-futures.feather"
    path.touch()
    frame = _candles(pd.date_range("2026-01-01", periods=100, freq="15min", tz="UTC"))
    monkeypatch.setattr(pd, "read_feather", lambda _: frame)

    market, metadata = load_market_data(tmp_path, "BTC/USDT:USDT", "15m")

    assert len(market) == 100
    assert metadata["coverage"] == 1.0
    assert metadata["max_gap_seconds"] == 900.0


def test_load_market_data_rejects_unsorted_or_sparse_candles(tmp_path: Path, monkeypatch):
    path = tmp_path / "BTC_USDT_USDT-15m-futures.feather"
    path.touch()
    ordered = pd.date_range("2026-01-01", periods=100, freq="15min", tz="UTC")
    unsorted = _candles(ordered[[1, 0, *range(2, len(ordered))]])
    monkeypatch.setattr(pd, "read_feather", lambda _: unsorted)
    with pytest.raises(ValueError, match="not chronologically sorted"):
        load_market_data(tmp_path, "BTC/USDT:USDT", "15m")

    sparse = _candles(pd.date_range("2026-01-01", periods=20, freq="1h", tz="UTC"))
    monkeypatch.setattr(pd, "read_feather", lambda _: sparse)
    with pytest.raises(ValueError, match="candle coverage"):
        load_market_data(tmp_path, "BTC/USDT:USDT", "15m")


def test_milestone_requires_six_folds_before_loading_data(tmp_path: Path):
    with pytest.raises(ValueError, match="at least 6"):
        run_milestone_one(
            tmp_path,
            tmp_path / "output",
            ResearchConfig(fold_count=5),
            generated_at="2026-08-10T00:00:00Z",
        )


def test_milestone_embargo_covers_longest_candidate_horizon(tmp_path: Path):
    with pytest.raises(ValueError, match="maximum trade horizon"):
        run_milestone_one(
            tmp_path,
            tmp_path / "output",
            ResearchConfig(embargo_hours=4),
            generated_at="2026-08-10T00:00:00Z",
        )


def test_portfolio_rejects_profit_concentrated_in_one_pair():
    folds = []
    for _ in range(6):
        folds.append(
            pd.DataFrame(
                {
                    "pnl": [0.01, 0.0],
                    "pair": ["BTC/USDT:USDT", "ETH/USDT:USDT"],
                    "side": ["long", "long"],
                    "notional": [1.0, 1.0],
                }
            )
        )

    result = _evaluate_portfolio(folds, cost_fraction=0.0, fold_count=6)

    assert result.passed is False
    assert result.max_pair_contribution == 1.0
    assert any("single pair contribution" in reason for reason in result.reasons)


def test_full_no_trade_milestone_is_reproducible(tmp_path: Path, monkeypatch):
    index_15m = pd.date_range("2026-01-01", periods=8 * 24 * 4 + 1, freq="15min", tz="UTC")
    index_1h = pd.date_range("2026-01-01", periods=8 * 24 + 1, freq="1h", tz="UTC")

    def market(index: pd.DatetimeIndex) -> pd.DataFrame:
        values = pd.Series(range(len(index)), index=index, dtype=float)
        return pd.DataFrame(
            {
                "open": 100.0 + values * 0.01,
                "high": 101.0 + values * 0.01,
                "low": 99.0 + values * 0.01,
                "close": 100.5 + values * 0.01,
                "volume": 10.0,
            },
            index=index,
        )

    frames = {"15m": market(index_15m), "1h": market(index_1h)}

    def fake_load(_data_dir: Path, pair: str, timeframe: str):
        frame = frames[timeframe]
        return frame, {
            "path": f"fixture/{pair}/{timeframe}",
            "sha256": timeframe,
            "rows": len(frame),
            "start": frame.index[0].isoformat(),
            "end": frame.index[-1].isoformat(),
            "coverage": 1.0,
            "max_gap_seconds": 900.0 if timeframe == "15m" else 3600.0,
        }

    monkeypatch.setattr(research, "load_market_data", fake_load)
    monkeypatch.setattr(
        research,
        "_candidate_catalog",
        lambda: (Candidate("no_trade", no_trade, ({},)),),
    )
    config = ResearchConfig(
        fold_count=6,
        train_days=1,
        validation_days=1,
        embargo_hours=6,
        min_train_trades=1,
    )
    generated_at = "2026-08-10T00:00:00Z"

    first = run_milestone_one(
        tmp_path,
        tmp_path / "first",
        config,
        generated_at=generated_at,
    )
    second_output = tmp_path / "second"
    second_output.mkdir()
    for name in ("results.json", "REPORT.md"):
        stale = second_output / name
        stale.write_text("stale")
        stale.chmod(0o440)
    second = run_milestone_one(
        tmp_path,
        second_output,
        config,
        generated_at=generated_at,
    )

    assert first == second
    assert first["decision"] == "STOP_BEFORE_CLASSIFIER"
    assert first["generated_at"] == generated_at
    assert (tmp_path / "first/REPORT.md").is_file()
    assert (tmp_path / "first/results.json").read_bytes() == (
        tmp_path / "second/results.json"
    ).read_bytes()
    assert (tmp_path / "first/REPORT.md").read_bytes() == (
        tmp_path / "second/REPORT.md"
    ).read_bytes()
    assert (tmp_path / "second/results.json").stat().st_mode & 0o777 == 0o660
    assert (tmp_path / "second/REPORT.md").stat().st_mode & 0o777 == 0o660


def test_documented_docker_runner_forwards_reproducible_timestamp():
    runner = (Path(__file__).resolve().parents[1] / "scripts/run_walk_forward.sh").read_text()

    assert '-e V3_GENERATED_AT="${V3_GENERATED_AT:-}"' in runner
    assert '--user "1000:$HOST_GID"' in runner
    assert "chmod 2770" in runner
    assert "chmod 0777" not in runner


def test_metric_frame_scales_pnl_and_notional_to_the_capital_fraction():
    events = pd.DataFrame(
        {
            "gross_return": [0.10, -0.20],
            "pair": ["BTC/USDT:USDT", "ETH/USDT:USDT"],
            "side": ["long", "long"],
            "entry_time": pd.to_datetime(["2026-01-01", "2026-01-02"], utc=True),
            "exit_time": pd.to_datetime(["2026-01-01 01:00", "2026-01-02 01:00"], utc=True),
        }
    )
    trades = _metric_frame(events, 0.05)
    assert trades["pnl"].tolist() == pytest.approx([0.005, -0.01])
    assert trades["notional"].tolist() == [0.05, 0.05]
    with pytest.raises(ValueError):
        _metric_frame(events, 0)


def test_fold_boundary_trades_resolve_exits_on_later_rows_without_new_entries():
    index = pd.date_range("2026-01-01", periods=40, freq="15min", tz="UTC")
    values = pd.Series(range(len(index)), index=index, dtype=float)
    market = pd.DataFrame(
        {
            "open": 100.0 + values,
            "high": 100.5 + values,
            "low": 99.5 + values,
            "close": 100.2 + values,
            "volume": 10.0,
        },
        index=index,
    )
    features = pd.DataFrame({"atr": 1.0}, index=index)
    validation = list(index[:20])

    extended = _exit_extended_index(market.index, validation, 8)
    assert len(extended) == 28 and list(extended[:20]) == validation
    assert _exit_extended_index(market.index, list(index[-3:]), 8).tolist() == list(index[-3:])

    def signal(_features, **_options):
        frame = pd.DataFrame({"long": False, "short": False}, index=_features.index)
        frame.loc[_features.index[18], "long"] = True  # opens at row 19, near the boundary
        if len(_features.index) > 25:
            frame.loc[_features.index[25], "long"] = True  # outside the fold: must be ignored
        return frame

    candidate = Candidate("boundary", signal, ({},))
    risk = RiskConfig(stop_atr=100, target_atr=100, max_holding_candles=8, round_trip_cost_bps=0)
    truncated = _run_slice(
        market.loc[validation],
        features.loc[validation],
        candidate,
        pair="BTC/USDT:USDT",
        side="long",
        options={},
        risk=risk,
    )
    resolved = _run_slice(
        market.loc[extended],
        features.loc[extended],
        candidate,
        pair="BTC/USDT:USDT",
        side="long",
        options={},
        risk=risk,
        entry_index=pd.Index(validation),
    )
    assert len(truncated) == 1 and len(resolved) == 1
    assert truncated["exit_time"].iloc[0] == index[19]
    assert resolved["exit_time"].iloc[0] == index[26]
    assert resolved["pnl"].iloc[0] > truncated["pnl"].iloc[0]


def test_volatility_breakout_signal_is_importable_for_catalog_parity():
    assert callable(volatility_breakout)
