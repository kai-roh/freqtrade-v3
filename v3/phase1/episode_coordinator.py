"""One bounded management tick for an existing, source-bound Demo episode.

No entry bypass, background retry, or order replacement is provided. A caller
must schedule ticks on the execution loop and supply a dedicated DB connection.
Stream callbacks must use a different connection. Unknown/working orders stop
this tick before any new order; cancellation is a separate audited operation.
"""

from datetime import UTC, datetime

from .episode_lifecycle import reconcile_episode_state
from .episode_plan import EpisodeActionType, plan_episode_action
from .position_gateway import _state, account_execution_lock, submit_position_action
from .rest_recovery import recover_tracked_order


def manage_episode_once(
    *,
    connection,
    inspector,
    runtime,
    risk_service,
    manifest,
    intent_id,
    market_evidence,
    closing=False,
    allow_test_transport=False,
):
    """Recover -> account GET -> fresh quotes -> reconcile -> at most one IOC.

    market_evidence() returns (EpisodeLimits, receive_gap_ms, observed_ns).
    Quote timestamps are not refreshed by this function. The approved price is
    the observed opposite quote, without increasing the slippage allowance.
    """
    manifest.assert_deployable()
    with account_execution_lock(connection):
        with connection.transaction():
            row = connection.execute(
                "SELECT run_manifest_id,state,max_holding_or_review_at FROM intents "
                "WHERE id=%s FOR UPDATE",
                (intent_id,),
            ).fetchone()
            if row is None or row[0] != manifest.manifest_id:
                raise ValueError("episode must belong to this deployment")
            if not connection.execute(
                "SELECT 1 FROM episode_baselines WHERE intent_id=%s", (intent_id,)
            ).fetchone():
                raise ValueError("pre-entry inventory baseline required")
            # Persist exit intent BEFORE REST I/O, including a crash or timeout.
            if (
                closing
                or datetime.now(UTC) >= row[2]
                or row[1]
                in {
                    "RECONCILING",
                    "RECONCILIATION_BLOCKED",
                    "ABORTING",
                }
            ):
                connection.execute(
                    "UPDATE episode_baselines SET close_requested_at="
                    "COALESCE(close_requested_at,now()) WHERE intent_id=%s",
                    (intent_id,),
                )
            commands = connection.execute(
                "SELECT c.id FROM order_commands c JOIN order_dispatches d ON d.command_id=c.id "
                "LEFT JOIN orders o ON o.command_id=c.id WHERE c.intent_id=%s AND "
                "(d.status<>'OBSERVED' OR o.status IS NULL OR o.status NOT IN "
                "('FILLED','CANCELED','CANCELLED','EXPIRED','REJECTED') OR EXISTS "
                "(SELECT 1 FROM order_recovery_checks r WHERE r.command_id=c.id "
                "AND r.status IN ('PENDING','BLOCKED'))) ORDER BY c.id",
                (intent_id,),
            ).fetchall()
        for command in commands:
            result = recover_tracked_order(connection, inspector, str(command[0]))
            if result["status"] != "APPLIED":
                return {"submitted": False, "status": "RECOVERY_BLOCKED"}
        with connection.transaction():
            working = connection.execute(
                "SELECT 1 FROM orders o JOIN order_commands c ON c.id=o.command_id "
                "WHERE c.intent_id=%s AND o.status NOT IN "
                "('FILLED','CANCELED','CANCELLED','EXPIRED','REJECTED') LIMIT 1",
                (intent_id,),
            ).fetchone()
        if working:
            return {"submitted": False, "status": "CANCEL_AND_RECONCILE_REQUIRED"}

        account = inspector.account()
        limits, receive_gap_ms, observed_ns = market_evidence()
        lifecycle = reconcile_episode_state(
            connection,
            intent_id=intent_id,
            account=account,
            limits=limits,
        )
        if lifecycle["flat"]:
            return {"submitted": False, "status": "CLOSED", "flat": True}
        with connection.transaction():
            snapshot, _, _ = _state(connection, intent_id, account, False)
        action = plan_episode_action(snapshot, limits)
        prices = {
            EpisodeActionType.HEDGE_PERP_SELL: limits.perp_bid,
            EpisodeActionType.CLOSE_PERP_BUY: limits.perp_ask,
            EpisodeActionType.CLOSE_SPOT_SELL: limits.spot_bid,
        }
        if action.action not in prices:
            return {
                "submitted": False,
                "status": action.action.value.upper(),
                "state": lifecycle["state"],
                "reason": action.reason,
            }
        return submit_position_action(
            connection=connection,
            runtime=runtime,
            risk_service=risk_service,
            manifest=manifest,
            intent_id=intent_id,
            account=account,
            limits=limits,
            receive_gap_ms=receive_gap_ms,
            observed_ns=observed_ns,
            price=prices[action.action],
            allow_test_transport=allow_test_transport,
        )
