import os
import time
from decimal import Decimal

import pytest
from test_phase1_entry_gateway import FakeStrategy, _isolated_database, _manifest

from v3.phase1.action_risk import ActionRiskService
from v3.phase1.engineering_entry import submit_engineering_entry
from v3.phase1.episode_plan import EpisodeLimits
from v3.phase1.postgres import apply_migrations


@pytest.mark.parametrize(
    "failure", [None, "funds", "open_orders", "margin", "age", "notional", "hold", "dirty"]
)
def test_engineering_entry_is_bounded_and_never_replayed(failure):
    dsn = os.getenv("PHASE1_TEST_DATABASE_DSN")
    if not dsn:
        pytest.skip("PHASE1_TEST_DATABASE_DSN not set")
    account = dict(
        spot_total_btc="0.25",
        spot_btc="0.25",
        perp_qty="0",
        spot_usdt="1000",
        perp_usdt="1000",
        observed_ns=time.time_ns(),
        leverage=2,
        margin_type="ISOLATED",
        open_orders=[],
    )
    if failure == "funds":
        account["spot_usdt"] = "0"
    if failure == "open_orders":
        account["open_orders"] = ["foreign"]
    if failure == "margin":
        account["margin_type"] = "CROSSED"
    with _isolated_database(dsn) as db, ActionRiskService() as risk:
        apply_migrations(db)
        runtime = FakeStrategy()
        kwargs = dict(
            connection=db,
            runtime=runtime,
            risk_service=risk,
            manifest=_manifest(dirty=failure == "dirty"),
            account=account,
            limits=EpisodeLimits("0.00001", "0.001", "5", "50", "60000", "60000", "60000", "60001"),
            quantity=Decimal("0.006" if failure == "notional" else "0.0036"),
            price=Decimal("60000"),
            receive_gap_ms=(3000 if failure == "age" else 0, 0),
            observed_ns=time.time_ns(),
            hold_seconds=5000 if failure == "hold" else 300,
            allow_test_transport=True,
        )
        if failure == "dirty":
            with pytest.raises(ValueError, match="dirty"):
                submit_engineering_entry(**kwargs)
        else:
            result = submit_engineering_entry(**kwargs)
            assert result["submitted"] is (failure is None)
        if failure is not None:
            assert not runtime.submitted
            assert db.execute("SELECT count(*) FROM order_commands").fetchone()[0] == 0
        else:
            assert len(runtime.submitted) == 1
            assert not runtime.orders_enabled
            with pytest.raises(ValueError, match="existing episode"):
                submit_engineering_entry(**kwargs)
            assert len(runtime.submitted) == 1
