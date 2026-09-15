"""Audited episode state transitions from reconciled fills, never local enqueue."""

from .episode_plan import EpisodeActionType, EpisodePhase, plan_episode_action
from .position_gateway import _account_fresh, _state, account_execution_lock
from .postgres import PostgresPhase1Ledger
from .state_machine import CarryStateMachine, IntentState


def reconcile_episode_state(connection, *, intent_id, account, limits, closing=False):
    with account_execution_lock(connection), connection.transaction():
        connection.execute("SELECT pg_advisory_xact_lock(31092028)")
        _account_fresh(account)
        row = connection.execute(
            "SELECT state FROM intents WHERE id=%s FOR UPDATE", (intent_id,)
        ).fetchone()
        if row is None:
            raise ValueError("unknown episode")
        if connection.execute(
            "SELECT 1 FROM order_recovery_checks WHERE status IN ('PENDING','BLOCKED') LIMIT 1"
        ).fetchone():
            raise ValueError("unresolved recovery prevents episode transition")
        if connection.execute(
            "SELECT 1 FROM fill_event_inbox WHERE status<>'APPLIED' LIMIT 1"
        ).fetchone():
            raise ValueError("unprocessed fill prevents episode transition")
        if closing:
            connection.execute(
                "UPDATE episode_baselines SET close_requested_at=COALESCE(close_requested_at,now()) "
                "WHERE intent_id=%s",
                (intent_id,),
            )
        snapshot, commands, _ = _state(connection, intent_id, account, closing)
        closing = snapshot.phase == EpisodePhase.CLOSING
        if (
            snapshot.net_spot_base != snapshot.venue_spot_base
            or snapshot.perp_filled_base != snapshot.venue_perp_base
            or account["open_orders"]
        ):
            raise ValueError("account and episode positions do not reconcile")
        ledger = PostgresPhase1Ledger(connection)
        machine = CarryStateMachine(intent_id, ledger, IntentState(row[0]))

        def move(target, trigger):
            if machine.state != target:
                machine.transition(
                    target, trigger=trigger, guards={"venue_and_fills_reconciled": True}
                )

        flat = snapshot.net_spot_base == snapshot.perp_filled_base == 0
        if machine.state == IntentState.CLOSED:
            if not flat:
                raise ValueError("closed episode has inventory")
            return {"state": "CLOSED", "flat": True, "orders_submitted": False}
        if flat:
            for command in commands:
                if command["active"]:
                    if command["dispatch_status"] is not None:
                        raise ValueError("submitted command remains active")
                    ledger.deactivate_command(str(command["id"]))
            if machine.state == IntentState.HEDGED:
                move(IntentState.RECONCILING, "flat_venue_snapshot")
            if machine.state == IntentState.RECONCILIATION_BLOCKED:
                move(IntentState.RECONCILING, "residual_resolved")
            if machine.state == IntentState.PARTIALLY_HEDGED:
                move(IntentState.HEDGE_REQUIRED, "exposure_review")
            if machine.state in {
                IntentState.PLANNED,
                IntentState.SUBMITTING,
                IntentState.HEDGE_REQUIRED,
            }:
                move(IntentState.ABORTING, "no_remaining_exposure")
            move(IntentState.CLOSED, "confirmed_flat_no_working_orders")
        elif closing:
            if machine.state == IntentState.HEDGED:
                move(IntentState.RECONCILING, "exit_requested")
            elif machine.state == IntentState.PARTIALLY_HEDGED:
                move(IntentState.HEDGE_REQUIRED, "partial_entry_exit_requested")
                move(IntentState.ABORTING, "partial_entry_exit_requested")
            elif machine.state in {IntentState.SUBMITTING, IntentState.HEDGE_REQUIRED}:
                move(IntentState.ABORTING, "entry_exit_requested")
            action = plan_episode_action(snapshot, limits)
            if (
                action.action == EpisodeActionType.DUST_REMAINS
                and machine.state == IntentState.RECONCILING
            ):
                move(IntentState.RECONCILIATION_BLOCKED, "dust_is_not_flat")
        elif snapshot.net_spot_base + snapshot.perp_filled_base == 0:
            move(IntentState.HEDGED, "confirmed_equal_base_exposure")
        elif machine.state == IntentState.SUBMITTING:
            move(IntentState.PARTIALLY_HEDGED, "confirmed_partial_exposure")
            move(IntentState.HEDGE_REQUIRED, "confirmed_hedge_shortfall")
        return {
            "state": machine.state.value,
            "flat": flat,
            "orders_submitted": False,
            "net_spot_base": str(snapshot.net_spot_base),
            "perp_base": str(snapshot.perp_filled_base),
        }
