import os
import time
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from test_phase1_entry_gateway import (
    FakeStrategy,
    _isolated_database,
    _manifest,
    _policy_path,
    _request,
)

from v3.phase1.action_risk import ActionRiskService
from v3.phase1.dispatch import DispatchJournal
from v3.phase1.entry_gateway import submit_phase1_entry
from v3.phase1.episode_coordinator import manage_episode_once
from v3.phase1.episode_lifecycle import reconcile_episode_state
from v3.phase1.episode_plan import EpisodeLimits
from v3.phase1.policy import load_phase1_policy
from v3.phase1.position_gateway import submit_position_action
from v3.phase1.postgres import PostgresPhase1Ledger, apply_migrations
from v3.phase1.rest_recovery import RestFillSnapshot, RestOrderSnapshot, apply_rest_recovery
from v3.phase1.risk_service import Phase1RiskService, file_sha256


@pytest.fixture
def episode(tmp_path, request):
    dsn = os.getenv("PHASE1_TEST_DATABASE_DSN")
    if not dsn:
        pytest.skip("PHASE1_TEST_DATABASE_DSN not set")
    with _isolated_database(dsn) as db:
        apply_migrations(db)
        path = _policy_path(tmp_path)
        manifest = _manifest(config_sha256=file_sha256(path))
        strategy = FakeStrategy()
        with Phase1RiskService(policy_path=path, timeout_seconds=3) as risk:
            gateway_request = _request()
            # Pre-existing BTC must never become strategy-owned inventory.
            gateway_request.account_snapshot.update(spot_btc="0.25", spot_total_btc="0.25")
            entry = submit_phase1_entry(
                request=gateway_request,
                manifest=manifest,
                policy=load_phase1_policy(path),
                ledger=PostgresPhase1Ledger(db),
                risk_service=risk,
                dispatch=DispatchJournal(db),
                runtime=strategy,
                allow_test_transport=True,
                maximum_decision_age_ms=5000,
            )
        assert entry.approved and len(entry.submitted_command_ids) == 1
        _fill(
            db,
            entry.submitted_command_ids[0],
            "0.005",
            fee=getattr(request, "param", "0.000005"),
            token="BTC",
        )
        limits = EpisodeLimits("0.00001", "0.001", "5", "50", "60000", "60001", "60000", "60001")
        with ActionRiskService() as action_risk:
            yield db, manifest, strategy, action_risk, entry, limits


def _fill(db, command_id, quantity, *, fee="0", token="USDT"):
    command = db.execute(
        "SELECT leg,idempotency_key FROM order_commands WHERE id=%s", (command_id,)
    ).fetchone()
    now = datetime.now(UTC)
    snapshot = RestOrderSnapshot(
        "BINANCE_SPOT_DEMO" if command[0] == "spot" else "BINANCE_USDM_DEMO",
        command[1],
        "FILLED",
        command_id,
        Decimal(quantity),
        Decimal("60000"),
        now,
        (
            RestFillSnapshot(
                command_id, Decimal(quantity), Decimal("60000"), now, Decimal(fee), token, "TAKER"
            ),
        ),
    )
    assert (
        apply_rest_recovery(PostgresPhase1Ledger(db), command_id=command_id, snapshot=snapshot)[
            "status"
        ]
        == "APPLIED"
    )
    assert DispatchJournal(db).reconcile_from_recorded_order(command_id)


def _account(*, perp="0", owned="0.004995"):
    total = Decimal("0.25") + Decimal(owned)
    return dict(
        spot_total_btc=str(total),
        spot_btc=str(total),
        perp_qty=perp,
        observed_ns=time.time_ns(),
        spot_usdt="1000",
        perp_usdt="1000",
        open_orders=[],
        leverage=2,
        margin_type="ISOLATED",
    )


def _submit(episode, *, closing=False, account=None, price="60000"):
    db, manifest, strategy, risk, entry, limits = episode
    return submit_position_action(
        connection=db,
        runtime=strategy,
        risk_service=risk,
        manifest=manifest,
        intent_id=entry.intent_id,
        account=account or _account(),
        limits=limits,
        receive_gap_ms=(0, 0),
        observed_ns=time.time_ns(),
        price=Decimal(price),
        closing=closing,
        allow_test_transport=True,
    )


def _tick(episode, inspector, *, closing=False):
    db, manifest, strategy, risk, entry, limits = episode
    return manage_episode_once(
        connection=db,
        inspector=inspector,
        runtime=strategy,
        risk_service=risk,
        manifest=manifest,
        intent_id=entry.intent_id,
        market_evidence=lambda: (limits, (0, 0), time.time_ns()),
        closing=closing,
        allow_test_transport=True,
    )


@pytest.mark.parametrize("episode", ["0"], indirect=True)
def test_coordinator_restart_preserves_close_intent(episode):
    class Inspector:
        perp = "0"
        owned = "0.005"

        def account(self):
            return _account(perp=self.perp, owned=self.owned)

    inspector = Inspector()
    db, _, strategy, _, _, _ = episode
    hedge = _tick(episode, inspector)
    assert hedge["action"] == "hedge_perp_sell"
    _fill(db, hedge["command_id"], "0.005")
    inspector.perp = "-0.005"
    assert _tick(episode, inspector)["status"] == "WAIT"
    close = _tick(episode, inspector, closing=True)
    assert close["action"] == "close_perp_buy"
    _fill(db, close["command_id"], "0.005")
    inspector.perp = "0"
    # A new tick without closing=True must not re-open the short hedge.
    sell = _tick(episode, inspector)
    assert sell["action"] == "close_spot_sell"
    _fill(db, sell["command_id"], "0.005")
    inspector.owned = "0"
    assert _tick(episode, inspector)["status"] == "CLOSED"
    count = len(strategy.submitted)
    assert _tick(episode, inspector)["status"] == "CLOSED"
    assert len(strategy.submitted) == count


def test_coordinator_unknown_blocks_and_persists_exit(episode):
    class Inspector:
        def order(self, *_):
            raise TimeoutError("simulated missing venue evidence")

        def account(self):
            raise AssertionError("must stop before planning another order")

    db, _, strategy, _, entry, _ = episode
    _submit(episode)
    count = len(strategy.submitted)
    assert _tick(episode, Inspector(), closing=True)["status"] == "RECOVERY_BLOCKED"
    assert len(strategy.submitted) == count
    with db.transaction():
        assert db.execute(
            "SELECT close_requested_at IS NOT NULL FROM episode_baselines WHERE intent_id=%s",
            (entry.intent_id,),
        ).fetchone()[0]


def test_actual_fill_sizing_then_reduce_only_then_owned_spot_exit(episode):
    db, _, strategy, _, entry, _ = episode
    hedge = _submit(episode)
    assert hedge["submitted"] and hedge["action"] == "hedge_perp_sell"
    assert strategy.submitted[-1]["quantity"] == Decimal("0.004")
    assert strategy.submitted[-1]["post_only"] is False
    assert (
        db.execute(
            "SELECT active FROM order_commands WHERE id=%s", (entry.pending_command_ids[0],)
        ).fetchone()[0]
        is False
    )
    _fill(db, hedge["command_id"], "0.004")
    close = _submit(episode, closing=True, account=_account(perp="-0.004"), price="60001")
    assert close["submitted"] and strategy.submitted[-1]["reduce_only"] is True
    assert strategy.submitted[-1]["side"] == "buy"
    _fill(db, close["command_id"], "0.004")
    spot = _submit(episode, closing=True)
    assert spot["submitted"] and spot["action"] == "close_spot_sell"
    assert strategy.submitted[-1]["quantity"] == Decimal("0.00499")
    _fill(db, spot["command_id"], "0.00499")
    dust = _submit(episode, closing=True, account=_account(owned="0.000005"))
    assert not dust["submitted"]
    assert strategy.orders_enabled is False


def test_unknown_hedge_never_resubmits_or_sells_other_holdings(episode):
    db, _, strategy, _, _, _ = episode
    strategy.fail_on_submit = len(strategy.submitted) + 1
    result = _submit(episode)
    assert result["status"] == "UNKNOWN"
    assert not result["submitted"] and not strategy.orders_enabled
    with pytest.raises(ValueError, match="unknown dispatch"):
        _submit(episode, closing=True)
    assert (
        db.execute("SELECT count(*) FROM order_dispatches WHERE status='UNKNOWN'").fetchone()[0]
        == 1
    )


@pytest.mark.parametrize("change", ["foreign", "stale", "open_order", "margin"])
def test_bad_account_evidence_cannot_dispatch(episode, change):
    _, _, strategy, _, _, _ = episode
    before = len(strategy.submitted)
    account = _account()
    if change == "foreign":
        account["spot_total_btc"] = "0.8"
    if change == "stale":
        account["observed_ns"] -= 6_000_000_000
    if change == "open_order":
        account["open_orders"] = [{}]
    if change == "margin":
        account["margin_type"] = "CROSSED"
    if change == "stale":
        with pytest.raises(ValueError, match="expired"):
            _submit(episode, account=account)
    else:
        assert not _submit(episode, account=account)["submitted"]
    assert len(strategy.submitted) == before


def test_second_connection_cannot_submit_while_account_execution_lock_is_held(episode):
    import psycopg

    db, _, strategy, _, _, _ = episode
    with psycopg.connect(os.environ["PHASE1_TEST_DATABASE_DSN"], autocommit=True) as other:
        other.execute("SELECT pg_advisory_lock(31092027)")
        before = len(strategy.submitted)
        with pytest.raises(ValueError, match="another executor"):
            _submit(episode)
        assert len(strategy.submitted) == before
        other.execute("SELECT pg_advisory_unlock(31092027)")


def test_action_limit_stops_unbounded_requotes(episode):
    db, _, strategy, _, entry, _ = episode
    # Populate exhausted prior attempts with terminal, positively observed evidence.
    from uuid import uuid4

    from v3.phase1.ledger import OrderCommandRow

    ledger = PostgresPhase1Ledger(db)
    for index in range(6):
        command = str(uuid4())
        ledger.add_command(
            OrderCommandRow(
                command, entry.intent_id, "spot", "attempt-" + str(index), "0.001", "60000"
            ),
            order_type="IOC_LIMIT",
        )
        ledger.deactivate_command(command)
    before = len(strategy.submitted)
    with pytest.raises(ValueError, match="attempt limit"):
        _submit(episode)
    assert len(strategy.submitted) == before


@pytest.mark.parametrize("episode", ["0"], indirect=True)
def test_reconciled_full_cycle_has_audited_closed_state(episode):
    db, _, _, _, entry, limits = episode

    def sync(account, closing=False):
        return reconcile_episode_state(
            db, intent_id=entry.intent_id, account=account, limits=limits, closing=closing
        )

    assert sync(_account(owned="0.005"))["state"] == "HEDGE_REQUIRED"
    hedge = _submit(episode, account=_account(owned="0.005"))
    _fill(db, hedge["command_id"], "0.005")
    assert sync(_account(owned="0.005", perp="-0.005"))["state"] == "HEDGED"
    assert sync(_account(owned="0.005", perp="-0.005"), closing=True)["state"] == "RECONCILING"
    close = _submit(
        episode, closing=True, account=_account(owned="0.005", perp="-0.005"), price="60001"
    )
    _fill(db, close["command_id"], "0.005")
    spot = _submit(episode, closing=True, account=_account(owned="0.005"))
    _fill(db, spot["command_id"], "0.005")
    result = sync(_account(owned="0"), closing=True)
    assert result["state"] == "CLOSED" and result["flat"]
    assert db.execute("SELECT count(*) FROM order_commands WHERE active").fetchone()[0] == 0
    assert (
        db.execute("SELECT count(*) FROM state_transitions WHERE NOT accepted").fetchone()[0] == 0
    )
    assert sync(_account(owned="0"), closing=True)["state"] == "CLOSED"


def test_partial_entry_residual_cannot_be_closed_by_lifecycle(episode):
    db, _, _, _, entry, limits = episode
    result = reconcile_episode_state(
        db, intent_id=entry.intent_id, account=_account(), limits=limits, closing=True
    )
    assert result["state"] == "ABORTING" and not result["flat"]
