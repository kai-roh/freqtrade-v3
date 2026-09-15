"""At-most-once Demo position management, distinct from economic entry approval."""

from __future__ import annotations

import json
import time
from contextlib import contextmanager
from dataclasses import asdict
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from psycopg.pq import TransactionStatus
from psycopg.rows import dict_row

from .action_risk import ActionRiskService, payload_hash
from .demo_node import DemoNode
from .dispatch import DispatchJournal
from .episode_plan import EpisodeLimits, EpisodePhase, EpisodeSnapshot, plan_episode_action
from .ledger import OrderCommandRow, RiskDecisionRow
from .postgres import PostgresPhase1Ledger


@contextmanager
def account_execution_lock(connection):
    """Shared with the matching probe; held through external submission."""
    if connection.info.transaction_status != TransactionStatus.IDLE:
        raise ValueError("account lock requires idle connection")
    with connection.transaction():
        acquired = connection.execute("SELECT pg_try_advisory_lock(31092027)").fetchone()[0]
    if not acquired:
        raise ValueError("another executor owns the Demo account")
    try:
        yield
    finally:
        with connection.transaction():
            connection.execute("SELECT pg_advisory_unlock(31092027)")


def record_episode_baseline(connection, intent_id, account):
    """Must run before the first command. Never infer a baseline after a fill."""
    _account_fresh(account)
    if account["open_orders"] or Decimal(account["perp_qty"]) != 0:
        raise ValueError("baseline requires no open BTC orders and flat futures")
    spot = Decimal(account["spot_total_btc"])
    if not spot.is_finite() or spot < 0:
        raise ValueError("invalid baseline inventory")
    with connection.transaction():
        connection.execute("SELECT pg_advisory_xact_lock(31092028)")
        connection.execute("SELECT id FROM intents WHERE id=%s FOR UPDATE", (intent_id,))
        if connection.execute(
            "SELECT 1 FROM order_commands WHERE intent_id=%s", (intent_id,)
        ).fetchone():
            raise ValueError("baseline cannot be registered after commands")
        # Settled residuals of earlier episodes remain account inventory. They are
        # inherited as pre-existing BTC here, never re-owned or sold by this episode.
        inherited = connection.execute(
            "SELECT COALESCE(sum(residual_base),0) FROM episode_residuals"
        ).fetchone()[0]
        if inherited > spot:
            raise ValueError("account holds less BTC than the settled residual record")
        connection.execute(
            "INSERT INTO episode_baselines(intent_id,spot_base,observed_at,evidence,inherited_residual_base) "
            "VALUES (%s,%s,%s,%s::jsonb,%s)",
            (intent_id, spot, datetime.now(UTC), json.dumps(_safe_account(account)), inherited),
        )


def _account_fresh(account):
    age = (time.time_ns() - account["observed_ns"]) / 1e9
    if not 0 <= age <= 5:
        raise ValueError("account observation expired")
    for field in ("spot_total_btc", "spot_btc", "perp_qty", "spot_usdt", "perp_usdt"):
        if not Decimal(account[field]).is_finite():
            raise ValueError("nonfinite account evidence")


def _safe_account(account):
    return {
        key: str(account[key])
        for key in (
            "spot_total_btc",
            "spot_btc",
            "perp_qty",
            "spot_usdt",
            "perp_usdt",
            "observed_ns",
            "leverage",
            "margin_type",
        )
    }


def _state(connection, intent_id, account, closing):
    with connection.cursor(row_factory=dict_row) as cursor:
        baseline = cursor.execute(
            "SELECT spot_base,close_requested_at FROM episode_baselines WHERE intent_id=%s",
            (intent_id,),
        ).fetchone()
        if not baseline:
            raise ValueError("persisted pre-entry baseline required")
        residual = cursor.execute(
            "SELECT residual_base FROM episode_residuals WHERE intent_id=%s", (intent_id,)
        ).fetchone()
        settled = residual["residual_base"] if residual else Decimal(0)
        # An unsubmitted opposite-leg reservation can be retired only after approval.
        commands = cursor.execute(
            "SELECT c.id,c.leg,c.active,d.status AS dispatch_status,o.status AS order_status,"
            "o.filled_quantity,COALESCE((SELECT sum(f.quantity) FROM fills f WHERE f.order_id=o.id),0) AS fill_total "
            "FROM order_commands c LEFT JOIN order_dispatches d ON d.command_id=c.id "
            "LEFT JOIN orders o ON o.command_id=c.id WHERE c.intent_id=%s ORDER BY c.id",
            (intent_id,),
        ).fetchall()
        for command in commands:
            if (
                command["filled_quantity"] is not None
                and command["filled_quantity"] != command["fill_total"]
            ):
                raise ValueError("order/fill totals disagree")
            if command["order_status"] is not None and command["order_status"] not in {
                "FILLED",
                "CANCELED",
                "CANCELLED",
                "EXPIRED",
                "REJECTED",
            }:
                raise ValueError("working order must be canceled and reconciled first")
            if command["dispatch_status"] not in {None, "OBSERVED"}:
                raise ValueError("unknown dispatch blocks position actions")
        rows = cursor.execute(
            "SELECT c.leg,c.side,f.quantity,f.price,f.fee_amount,f.fee_token,f.id "
            "FROM fills f JOIN orders o ON o.id=f.order_id JOIN order_commands c ON c.id=o.command_id "
            "WHERE c.intent_id=%s ORDER BY f.id",
            (intent_id,),
        ).fetchall()
    spot = perp = fees = Decimal(0)
    for row in rows:
        signed = row["quantity"] if row["side"] == "buy" else -row["quantity"]
        if row["leg"] == "spot":
            spot += signed
            if row["fee_token"] == "BTC":
                fees += row["fee_amount"]
        else:
            perp += signed
    snapshot = EpisodeSnapshot(
        phase=EpisodePhase.CLOSING
        if closing or baseline["close_requested_at"] is not None
        else EpisodePhase.HOLDING,
        spot_filled_base=spot,
        perp_filled_base=perp,
        spot_base_fee=fees,
        settled_residual_base=settled,
        venue_spot_base=Decimal(account["spot_total_btc"]) - baseline["spot_base"] - settled,
        venue_perp_base=Decimal(account["perp_qty"]),
        open_order_count=len(account["open_orders"]),
    )
    fingerprint = payload_hash(
        {
            "commands": str(commands),
            "fills": str(rows),
            "baseline": str(baseline),
            "settled_residual": str(settled),
        }
    )
    return snapshot, commands, fingerprint


def submit_position_action(**kwargs):
    with account_execution_lock(kwargs["connection"]):
        return _submit_position_action(**kwargs)


def _submit_position_action(
    *,
    connection,
    runtime,
    risk_service,
    manifest,
    intent_id,
    account,
    limits: EpisodeLimits,
    receive_gap_ms,
    observed_ns,
    price: Decimal,
    closing=False,
    allow_test_transport=False,
):
    """Submit one IOC action only after independent approval and a durable claim.

    Caller holds account execution session lock 31092027 and owns the event loop.
    Account and quote evidence must be refreshed before each invocation. No retries.
    """
    if connection.info.transaction_status != TransactionStatus.IDLE:
        raise ValueError("position gateway requires an idle dedicated connection")
    manifest.assert_deployable()
    if not isinstance(risk_service, ActionRiskService):
        raise ValueError("independent action risk process required")
    if isinstance(runtime, DemoNode):
        strategy = runtime.strategy
    elif allow_test_transport:
        strategy = runtime
    else:
        raise ValueError("pinned DemoNode required")
    _account_fresh(account)
    with connection.transaction():
        intent = connection.execute(
            "SELECT run_manifest_id,state FROM intents WHERE id=%s", (intent_id,)
        ).fetchone()
        if not intent or intent[0] != manifest.manifest_id or intent[1] == "CLOSED":
            raise ValueError("active intent must match the deployment manifest")
        if closing:
            connection.execute(
                "UPDATE episode_baselines SET close_requested_at=COALESCE(close_requested_at,now()) "
                "WHERE intent_id=%s",
                (intent_id,),
            )
        snapshot, _, fingerprint = _state(connection, intent_id, account, closing)
    action = plan_episode_action(snapshot, limits)
    payload = {
        "environment": "demo",
        "live_orders": False,
        "real_capital": False,
        "freshness_basis": "local_receive_gap",
        "engineering_config_sha256": risk_service.config_sha256,
        "account_reconciled": snapshot.net_spot_base == snapshot.venue_spot_base
        and snapshot.perp_filled_base == snapshot.venue_perp_base
        and not account["open_orders"],
        "receive_gap_ms": list(receive_gap_ms),
        "observed_ns": observed_ns,
        "snapshot": {
            key: str(value) if isinstance(value, Decimal) else value
            for key, value in asdict(snapshot).items()
        },
        "limits": {key: str(value) for key, value in asdict(limits).items()},
        "action": action.action.value,
        "quantity": str(action.quantity),
        "price": str(price),
        "reduce_only": action.reduce_only,
        "perp_leverage": str(account["leverage"]),
        "margin_type": account["margin_type"],
    }
    approval = risk_service.evaluate(payload)
    if not approval.approved:
        return {"submitted": False, "reason": approval.reason}
    leg = "spot" if action.action.value == "close_spot_sell" else "perp"
    side = "buy" if action.reduce_only else "sell"
    if leg == "spot" and action.quantity > Decimal(account["spot_btc"]):
        raise ValueError("owned Spot is not available for sale")
    if action.action.value == "hedge_perp_sell" and action.quantity * price / Decimal(
        account["leverage"]
    ) > Decimal(account["perp_usdt"]):
        raise ValueError("insufficient hedge margin")
    ledger = PostgresPhase1Ledger(connection)
    command_id, decision_id = str(uuid4()), str(uuid4())
    # A fresh random suffix makes a different command distinct, while the durable
    # claim and prior evidence prevent replay of an uncertain earlier command.
    key = "v3a" + uuid4().hex[:29]
    prepared = strategy.prepare_limit(
        canonical="BTCUSDT.BINANCE" if leg == "spot" else "BTCUSDT-PERP.BINANCE",
        side=side,
        quantity=action.quantity,
        price=price,
        client_id=key,
        post_only=False,
        reduce_only=action.reduce_only,
    )
    with connection.transaction():
        connection.execute("SELECT pg_advisory_xact_lock(31092028)")
        connection.execute("SELECT id FROM intents WHERE id=%s FOR UPDATE", (intent_id,))
        _account_fresh(account)
        if (time.time_ns() - observed_ns) / 1e6 + max(receive_gap_ms) > 2000:
            raise ValueError("quote expired after action approval")
        if connection.execute(
            "SELECT 1 FROM order_recovery_checks WHERE status IN ('PENDING','BLOCKED') LIMIT 1"
        ).fetchone():
            raise ValueError("unresolved recovery")
        if connection.execute(
            "SELECT 1 FROM fill_event_inbox WHERE status <> 'APPLIED' LIMIT 1"
        ).fetchone():
            raise ValueError("unprocessed fill evidence")
        if connection.execute(
            "SELECT 1 FROM order_commands WHERE active AND intent_id<>%s LIMIT 1", (intent_id,)
        ).fetchone():
            raise ValueError("another intent has active commands")
        if (
            connection.execute(
                "SELECT count(*) FROM order_commands WHERE intent_id=%s AND order_type='IOC_LIMIT'",
                (intent_id,),
            ).fetchone()[0]
            >= 6
        ):
            raise ValueError("bounded episode action attempt limit reached")
        _, commands, current = _state(connection, intent_id, account, closing)
        if current != fingerprint:
            raise ValueError("inventory evidence changed during approval")
        for command in commands:
            if command["active"]:
                if command["dispatch_status"] is not None:
                    raise ValueError("active submitted command blocks replacement")
                ledger.deactivate_command(str(command["id"]))
        now = datetime.now(UTC)
        ledger.add_risk_decision(
            RiskDecisionRow(decision_id, intent_id, True, (), None, now),
            observed_leverage={
                "purpose": "demo_position_management",
                "request_hash": approval.request_hash,
                "perp_leverage": str(account["leverage"]),
                "margin_type": account["margin_type"],
            },
        )
        ledger.add_command(
            OrderCommandRow(command_id, intent_id, leg, key, action.quantity, price),
            instrument_id="BTCUSDT.BINANCE" if leg == "spot" else "BTCUSDT-PERP.BINANCE",
            side=side,
            order_type="IOC_LIMIT",
        )
        connection.execute(
            "INSERT INTO order_dispatches(command_id,risk_decision_id,client_order_id,payload,status,claimed_at,updated_at) VALUES (%s,%s,%s,%s::jsonb,'CLAIMED',%s,%s)",
            (command_id, decision_id, key, json.dumps(payload), now, now),
        )
    error = None
    try:
        strategy.orders_enabled = True
        strategy.submit_prepared(prepared)
    except Exception as exc:
        error = exc
    finally:
        strategy.orders_enabled = False
    DispatchJournal(connection).record_enqueue_result(command_id, error=error)
    return {
        "submitted": error is None,
        "status": "UNKNOWN" if error else "ENQUEUED",
        "command_id": command_id,
        "client_order_id": key,
        "action": action.action.value,
    }
