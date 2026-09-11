import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from v3.phase1.fee_input import load_fee_snapshot, policy_with_fee_snapshot
from v3.phase1.policy import load_phase1_policy

ROOT = Path(__file__).resolve().parents[1]


def snapshot(tmp_path, **overrides):
    data = json.loads((ROOT / "evidence/phase1/binance-mainnet-fees-2026-09-08.json").read_text())
    data.update(overrides)
    path = tmp_path / "fees.json"
    path.write_text(json.dumps(data))
    return path


def test_shared_fee_input_preserves_policy_and_freshness(tmp_path):
    now = datetime.now(UTC)
    original = load_phase1_policy(ROOT / "configs/phase1-policy.json")
    updated = policy_with_fee_snapshot(original, snapshot(tmp_path, captured_at=now.isoformat()))
    assert updated.fee_schedule.is_fresh(now)
    assert updated.fee_schedule.maker_round_trip_bps == 24
    assert not updated.fee_schedule.is_fresh(now + timedelta(hours=25))
    assert updated.raw == original.raw
    assert updated.maximum_quote_age_ms is None


@pytest.mark.parametrize(
    "overrides",
    [
        {"source": "demo"},
        {"symbol": "ETHUSDT"},
        {"maximum_age_hours": 48},
        {"maximum_age_hours": True},
        {"include_exit_cost": False},
        {"bnb_discount_applied": True},
        {"perp_maker_bps": "NaN"},
        {"normal_round_trip_cost_bps": "0"},
        {"captured_at": "2026-09-08T00:00:00"},
    ],
)
def test_invalid_fee_evidence_denied(tmp_path, overrides):
    with pytest.raises((ValueError, TypeError)):
        load_fee_snapshot(snapshot(tmp_path, **overrides))
