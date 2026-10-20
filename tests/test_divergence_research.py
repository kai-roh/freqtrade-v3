"""Research boundary tests: fail closed data checks and portfolio decision semantics."""

import json
import zipfile

import numpy as np
import pandas as pd
import pytest

from scripts.build_divergence_dataset import read_archive, sha256, validate_bars
from scripts.run_divergence_research import aggregate, bootstrap, gate_pair, load_frozen


def bars():
    return pd.DataFrame(
        {
            "date": pd.date_range("2026-01-01", periods=10, freq="1min", tz="UTC"),
            "open": np.arange(10) + 100.0,
            "high": np.arange(10) + 102.0,
            "low": np.arange(10) + 99.0,
            "close": np.arange(10) + 101.0,
            "volume": np.arange(10) + 1.0,
        }
    )


def test_cadence_accepts_equivalent_timestamp_resolution_and_rejects_gaps():
    frame = bars()
    frame["date"] = frame.date.dt.as_unit("ms")
    validate_bars(frame, "2026-01-01", "2026-01-01 00:10")
    with pytest.raises(ValueError, match="cadence"):
        validate_bars(frame.drop(index=4), "2026-01-01", "2026-01-01 00:10")


def test_invalid_ohlcv_rejected():
    frame = bars()
    frame.loc[3, "low"] = 1000
    with pytest.raises(ValueError, match="OHLC"):
        validate_bars(frame, "2026-01-01", "2026-01-01 00:10")


def test_exact_five_minute_aggregation_and_partial_rejection():
    frame = bars().set_index("date")
    result = aggregate(frame, 5)
    assert result.iloc[0].to_dict() == {
        "open": 100,
        "high": 106,
        "low": 99,
        "close": 105,
        "volume": 15,
    }
    assert result.index[0] == frame.index[0]
    with pytest.raises(ValueError, match="Incomplete"):
        aggregate(frame.iloc[:-1], 5)


def test_archive_header_and_timestamp_schema(tmp_path):
    archive = tmp_path / "data.zip"
    with zipfile.ZipFile(archive, "w") as stream:
        stream.writestr(
            "data.csv", "open_time,open,high,low,close,volume\n1767225600000,100,102,99,101,20\n"
        )
    frame = read_archive(archive)
    assert frame.date.iloc[0] == pd.Timestamp("2026-01-01", tz="UTC")
    assert frame.close.iloc[0] == 101
    with zipfile.ZipFile(archive, "w") as stream:
        stream.writestr("data.csv", "1767225600000000,100,102,99,101,20\n")
    with pytest.raises(ValueError, match="timestamp unit"):
        read_archive(archive)


def test_tampered_frozen_dataset_rejected_before_read(tmp_path):
    registration = tmp_path / "registration.md"
    registration.write_text("frozen rules\n")
    changed = tmp_path / "bad.feather"
    changed.write_bytes(b"corrupt bytes")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "registration": str(registration),
                "registration_sha256": sha256(registration),
                "files": {"BTC/bars": {"path": str(changed), "sha256": "0" * 64}},
            }
        )
    )
    with pytest.raises(ValueError, match="hash mismatch"):
        load_frozen(manifest)
    registration.write_text("changed rules\n")
    with pytest.raises(ValueError, match="Registration changed"):
        load_frozen(manifest)


def good_summary():
    return {
        "trades": 120,
        "net_pnl": 20,
        "profit_factor": 1.3,
        "max_drawdown_pct": 2,
        "positive_folds": 5,
        "positive_profit_concentration": 0.7,
        "bootstrap": {"lower_95": 0.01},
    }


def test_cost_stress_failure_cannot_be_hidden_by_normal_profit():
    normal, stress = good_summary(), good_summary()
    assert gate_pair(normal, stress)["decision"] == "RESEARCH_ONLY_PASS"
    stress["net_pnl"] = -1
    assert gate_pair(normal, stress)["decision"] == "STOP_NO_EDGE"
    stress["trades"] = 99
    assert gate_pair(normal, stress)["decision"] == "INSUFFICIENT_TRADES"


def test_bootstrap_is_deterministic_and_keeps_zero_days():
    series = pd.Series(np.r_[np.ones(5), np.zeros(360)])
    first = bootstrap(series)
    assert first == bootstrap(series)
    assert first["mean_daily_pnl"] == pytest.approx(5 / 365)
    assert bootstrap(pd.Series(np.zeros(365)))["lower_95"] == 0


def test_numpy_statistics_remain_json_serializable():
    normal, stress = good_summary(), good_summary()
    normal["positive_profit_concentration"] = np.float64(0.7)
    stress["positive_profit_concentration"] = np.float64(0.7)
    json.dumps(gate_pair(normal, stress), allow_nan=False)
