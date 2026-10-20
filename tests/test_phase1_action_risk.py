import copy
import json
import time
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path

import pytest

from v3.phase1.action_risk import (
    ENGINEERING_CONFIG_PATH,
    ActionRiskService,
    evaluate_action,
    load_engineering_bounds,
    payload_hash,
)
from v3.phase1.episode_plan import EpisodeLimits, EpisodeSnapshot

BOUNDS = load_engineering_bounds(ENGINEERING_CONFIG_PATH)


def request():
    snapshot = EpisodeSnapshot(
        "holding", "0.005", "-0.001", venue_spot_base="0.005", venue_perp_base="-0.001"
    )
    limits = EpisodeLimits("0.00001", "0.001", "5", "50", "60000", "60001", "60000", "60001")
    return {
        "engineering_config_sha256": BOUNDS.config_sha256,
        "environment": "demo",
        "real_capital": False,
        "live_orders": False,
        "freshness_basis": "local_receive_gap",
        "account_reconciled": True,
        "observed_ns": time.time_ns(),
        "receive_gap_ms": [0, 0],
        "snapshot": {
            key: str(value) if isinstance(value, Decimal) else value
            for key, value in asdict(snapshot).items()
        },
        "limits": {key: str(value) for key, value in asdict(limits).items()},
        "action": "hedge_perp_sell",
        "quantity": "0.004",
        "price": "60000",
        "reduce_only": False,
        "perp_leverage": "2",
        "margin_type": "ISOLATED",
    }


@pytest.mark.parametrize(
    "field,value",
    [
        ("environment", "live"),
        ("real_capital", True),
        ("live_orders", True),
        ("freshness_basis", "exchange_age"),
        ("account_reconciled", False),
        ("receive_gap_ms", [2001, 0]),
        ("observed_ns", 1),
        ("quantity", "0.005"),
        ("price", "61000"),
        ("reduce_only", True),
        ("perp_leverage", "5"),
        ("margin_type", "CROSSED"),
        ("action", "submit_entry_pair"),
        ("engineering_config_sha256", "0" * 64),
    ],
)
def test_risk_denies_outside_demo_position_management(field, value):
    payload = request()
    payload[field] = value
    assert not evaluate_action(payload).approved


def test_subprocess_approval_is_bound_to_exact_payload_and_unavailable_denies():
    with ActionRiskService() as service:
        payload = request()
        approval = service.evaluate(payload)
        assert approval.approved and approval.request_hash == payload_hash(payload)
        changed = copy.deepcopy(payload)
        changed["snapshot"]["unknown_dispatch_count"] = 1
        assert not service.evaluate(changed).approved
        service.process.terminate()
        service.process.join(timeout=1)
        assert not service.evaluate(request()).approved


def test_bounds_come_from_the_committed_engineering_config_not_hardcoded_values(tmp_path):
    assert BOUNDS.maximum_leg_usdt == Decimal("300")
    assert BOUNDS.maximum_receive_gap_ms == 2000
    assert BOUNDS.maximum_ioc_slippage_bps == Decimal("10")
    tighter = json.loads(ENGINEERING_CONFIG_PATH.read_text())
    tighter["maximum_leg_usdt"] = "100"
    tighter["target_leg_usdt"] = "90"
    path = tmp_path / "engineering.json"
    path.write_text(json.dumps(tighter))
    with ActionRiskService(config_path=path) as service:
        payload = request()
        # A payload declaring the default config hash is refused by a worker on another file.
        assert not service.evaluate(payload).approved
        payload["engineering_config_sha256"] = service.config_sha256
        approval = service.evaluate(payload)
        assert not approval.approved and "bounded Demo notional" in approval.reason
    with ActionRiskService() as service:
        assert service.evaluate(request()).approved


@pytest.mark.parametrize(
    "field,value",
    [
        ("environment", "live"),
        ("economic_approval", True),
        ("maximum_receive_gap_ms", 5000),
        ("maximum_leg_usdt", "301"),
        ("maximum_ioc_slippage_bps", "11"),
        ("maximum_run_seconds", 901),
        ("target_leg_usdt", "301"),
    ],
)
def test_engineering_config_ceilings_are_hard_limits(tmp_path, field, value):
    data = json.loads(ENGINEERING_CONFIG_PATH.read_text())
    data[field] = value
    path = tmp_path / "engineering.json"
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        load_engineering_bounds(Path(path))
