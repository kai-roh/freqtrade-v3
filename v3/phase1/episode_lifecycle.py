"""Audited episode state transitions from reconciled fills, never local enqueue."""

import json
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from .episode_plan import EpisodeActionType, EpisodePhase, plan_episode_action
from .ledger import CostLedgerEntryRow, IncidentRow
from .position_gateway import _account_fresh, _safe_account, _state, account_execution_lock
from .postgres import PostgresPhase1Ledger
from .state_machine import (
    CarryStateMachine,
    IntentState,
    InvariantSnapshot,
    invariant_violations,
)

RESIDUAL_GUARDS = ("perp_flat", "no_open_orders", "residual_below_minimum_order")
DELTA_DRIFT_FRACTION = Decimal("0.05")


def episode_invariant_snapshot(
    connection,
    *,
    intent_id,
    snapshot,
    commands,
    limits,
    state,
    now=None,
    unhedged_budget_notional_ms=None,
):
    """Build the six-invariant view of one episode from durable ledger rows only."""
    now = now or datetime.now(UTC)
    with connection.cursor() as cursor:
        order_ids = {
            str(row[0])
            for row in cursor.execute(
                "SELECT o.id FROM orders o JOIN order_commands c ON c.id=o.command_id "
                "WHERE c.intent_id=%s",
                (intent_id,),
            ).fetchall()
        }
        fills = cursor.execute(
            "SELECT f.order_id,f.venue,f.venue_fill_id,c.leg,c.side,f.quantity,f.price,"
            "f.fee_amount,f.fee_token,f.filled_at FROM fills f JOIN orders o ON o.id=f.order_id "
            "JOIN order_commands c ON c.id=o.command_id WHERE c.intent_id=%s "
            "ORDER BY f.filled_at,f.id",
            (intent_id,),
        ).fetchall()
        approved = cursor.execute(
            "SELECT approved FROM risk_decisions WHERE intent_id=%s "
            "ORDER BY decided_at DESC,id DESC LIMIT 1",
            (intent_id,),
        ).fetchone()
    active_by_leg = {"spot": 0, "perp": 0}
    for command in commands:
        if command["active"]:
            active_by_leg[command["leg"]] += 1
    # Unhedged exposure integrates |owned Spot - short perp| over wall time between
    # durable fills, then to now. It is a bound on hedge latency cost, not PnL.
    exposure_ms = Decimal(0)
    spot = perp = Decimal(0)
    previous = None
    for row in fills:
        order_id, _, _, leg, side, quantity, price, fee_amount, fee_token, filled_at = row
        if previous is not None:
            elapsed_ms = Decimal(int((filled_at - previous).total_seconds() * 1000))
            exposure_ms += abs(spot + perp) * price * max(elapsed_ms, Decimal(0))
        signed = quantity if side == "buy" else -quantity
        if leg == "spot":
            spot += signed
            if fee_token == "BTC":
                spot -= fee_amount
        else:
            perp += signed
        previous = filled_at
    if previous is not None and abs(spot + perp) > 0 and state not in {IntentState.CLOSED}:
        elapsed_ms = Decimal(int((now - previous).total_seconds() * 1000))
        exposure_ms += abs(spot + perp) * limits.spot_bid * max(elapsed_ms, Decimal(0))
    return InvariantSnapshot(
        state=state,
        active_commands_by_leg=active_by_leg,
        spot_notional=snapshot.net_spot_base * limits.spot_bid,
        perp_notional=snapshot.perp_filled_base * limits.perp_bid,
        maximum_delta_drift_fraction=DELTA_DRIFT_FRACTION,
        local_positions={"spot": snapshot.net_spot_base, "perp": snapshot.perp_filled_base},
        venue_positions={
            "spot": snapshot.venue_spot_base,
            "perp": snapshot.venue_perp_base,
        },
        rounding_tolerance=Decimal(0),
        known_order_ids=frozenset(order_ids),
        fill_order_ids=tuple(str(row[0]) for row in fills),
        venue_fill_keys=tuple((row[1], row[2]) for row in fills),
        has_approved_risk_decision=bool(approved and approved[0]),
        unhedged_notional_milliseconds=exposure_ms,
        maximum_unhedged_notional_milliseconds=unhedged_budget_notional_ms,
    )


def _enforce_invariants(connection, **kwargs):
    violations = invariant_violations(episode_invariant_snapshot(connection, **kwargs))
    if violations:
        raise ValueError("episode invariant violated: " + "; ".join(violations))


def reconcile_episode_state(
    connection,
    *,
    intent_id,
    account,
    limits,
    closing=False,
    unhedged_budget_notional_ms=None,
):
    """Reconcile durable fills with the venue snapshot, then enforce the six invariants.

    Any invariant violation rolls back this tick's transitions and raises, so the
    caller halts new orders. Budget None means the notional-duration invariant is
    not measured for this caller; every other invariant is always enforced.
    """
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

        def enforce():
            _enforce_invariants(
                connection,
                intent_id=intent_id,
                snapshot=snapshot,
                commands=commands,
                limits=limits,
                state=machine.state,
                unhedged_budget_notional_ms=unhedged_budget_notional_ms,
            )

        if machine.state == IntentState.CLOSED:
            if not flat:
                raise ValueError("closed episode has inventory")
            enforce()
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
        enforce()
        return {
            "state": machine.state.value,
            "flat": flat,
            "orders_submitted": False,
            "net_spot_base": str(snapshot.net_spot_base),
            "perp_base": str(snapshot.perp_filled_base),
        }


def settle_episode_residual(connection, *, intent_id, account, limits, reason=None):
    """Record sub-minimum Spot dust as an owned, settled residual and close the episode.

    This is the only audited path from a dust-stuck closing episode to CLOSED. It
    never sells, never resets the baseline, and refuses anything that a bounded
    order could still close. The residual stays in the account and is inherited
    by the next episode baseline as pre-existing inventory.
    """
    with account_execution_lock(connection), connection.transaction():
        connection.execute("SELECT pg_advisory_xact_lock(31092028)")
        _account_fresh(account)
        row = connection.execute(
            "SELECT i.state,b.close_requested_at FROM intents i "
            "JOIN episode_baselines b ON b.intent_id=i.id WHERE i.id=%s FOR UPDATE",
            (intent_id,),
        ).fetchone()
        if row is None:
            raise ValueError("unknown episode or missing baseline")
        state, close_requested_at = IntentState(row[0]), row[1]
        if state not in {
            IntentState.ABORTING,
            IntentState.RECONCILING,
            IntentState.RECONCILIATION_BLOCKED,
        }:
            raise ValueError("residual settlement requires a closing episode")
        if close_requested_at is None:
            raise ValueError("residual settlement requires a persisted close request")
        if connection.execute(
            "SELECT 1 FROM episode_residuals WHERE intent_id=%s", (intent_id,)
        ).fetchone():
            raise ValueError("residual already settled")
        if connection.execute(
            "SELECT 1 FROM order_recovery_checks WHERE status IN ('PENDING','BLOCKED') LIMIT 1"
        ).fetchone():
            raise ValueError("unresolved recovery prevents residual settlement")
        if connection.execute(
            "SELECT 1 FROM fill_event_inbox WHERE status<>'APPLIED' LIMIT 1"
        ).fetchone():
            raise ValueError("unprocessed fill prevents residual settlement")
        if connection.execute("SELECT 1 FROM order_commands WHERE active LIMIT 1").fetchone():
            raise ValueError("active command prevents residual settlement")
        if account["open_orders"]:
            raise ValueError("open venue orders prevent residual settlement")
        snapshot, _, _ = _state(connection, intent_id, account, True)
        if snapshot.perp_filled_base != 0 or snapshot.venue_perp_base != 0:
            raise ValueError("futures must be flat before settling Spot residual")
        if snapshot.net_spot_base != snapshot.venue_spot_base:
            raise ValueError("account and episode Spot inventory do not reconcile")
        action = plan_episode_action(snapshot, limits)
        residual = snapshot.net_spot_base
        if action.action != EpisodeActionType.DUST_REMAINS or action.dust_base != residual:
            raise ValueError("only unsellable closing dust can be settled")
        if residual <= 0:
            raise ValueError("no residual to settle")
        mark = residual * limits.spot_bid
        if residual >= limits.spot_lot_size and mark >= limits.spot_min_notional:
            raise ValueError("residual is still sellable; submit a bounded close instead")
        now = datetime.now(UTC)
        detail = reason or "closing Spot remainder below sell lot or notional minimum"
        evidence = {
            "account": _safe_account(account),
            "limits": {
                "spot_lot_size": str(limits.spot_lot_size),
                "spot_min_notional": str(limits.spot_min_notional),
                "spot_bid": str(limits.spot_bid),
            },
            "spot_filled_base": str(snapshot.spot_filled_base),
            "spot_base_fee": str(snapshot.spot_base_fee),
            "from_state": state.value,
            "planner_reason": action.reason,
        }
        connection.execute(
            "INSERT INTO episode_residuals(intent_id,residual_base,residual_mark_usdt,reason,"
            "recorded_at,evidence) VALUES (%s,%s,%s,%s,%s,%s::jsonb)",
            (intent_id, residual, mark, detail, now, json.dumps(evidence)),
        )
        ledger = PostgresPhase1Ledger(connection)
        cost_ledger_id = connection.execute(
            "SELECT cost_ledger_id FROM intents WHERE id=%s", (intent_id,)
        ).fetchone()[0]
        ledger.add_cost_entry(
            CostLedgerEntryRow(
                str(uuid4()),
                intent_id,
                cost_ledger_id,
                "residual_inventory",
                None,
                mark,
                "USDT",
                "spot_bid_mark_of_unsellable_remainder",
                "episode_residual_settlement",
                now,
                {"residual_base": str(residual), "asset": "BTC", "sold": False},
            )
        )
        incident_id = str(uuid4())
        ledger.add_incident(
            IncidentRow(incident_id, intent_id, "residual_settlement", "info", detail, now),
            status="resolved",
        )
        connection.execute(
            "UPDATE incidents SET resolved_at=%s,resolution_evidence=%s WHERE id=%s",
            (now, json.dumps({"episode_residuals": intent_id}), incident_id),
        )
        ledger.record_reconciliation(
            run_id=str(uuid4()),
            intent_id=intent_id,
            explained_residual=mark,
            unexplained_residual=Decimal(0),
            currency="USDT",
            result="RESIDUAL_SETTLED",
            detail={"residual_base": str(residual), "reason": detail},
            started_at=now,
            completed_at=now,
        )
        machine = CarryStateMachine(intent_id, ledger, state)
        guards = dict.fromkeys(RESIDUAL_GUARDS, True) | {"residual_recorded": True}
        if machine.state == IntentState.RECONCILIATION_BLOCKED:
            machine.transition(IntentState.RECONCILING, trigger="residual_settled", guards=guards)
        machine.transition(IntentState.CLOSED, trigger="residual_settled", guards=guards)
        return {
            "state": IntentState.CLOSED.value,
            "flat": False,
            "residual_settled": True,
            "orders_submitted": False,
            "residual_base": str(residual),
            "residual_mark_usdt": str(mark),
        }
