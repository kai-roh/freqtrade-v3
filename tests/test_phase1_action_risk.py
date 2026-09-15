import copy
import time
from dataclasses import asdict
from decimal import Decimal

import pytest

from v3.phase1.action_risk import ActionRiskService, evaluate_action, payload_hash
from v3.phase1.episode_plan import EpisodeLimits, EpisodeSnapshot


def request():
    snapshot = EpisodeSnapshot(
        "holding", "0.005", "-0.001", venue_spot_base="0.005", venue_perp_base="-0.001"
    )
    limits = EpisodeLimits("0.00001", "0.001", "5", "50", "60000", "60001", "60000", "60001")
    return {
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
