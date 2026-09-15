"""Explicit single-episode Demo engineering entry; normal carry gates unchanged."""

import json
import time
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from .action_risk import ActionRiskService
from .demo_node import DemoNode
from .dispatch import DispatchJournal
from .ledger import IntentRow, OrderCommandRow, RiskDecisionRow
from .position_gateway import (
    _account_fresh,
    _safe_account,
    account_execution_lock,
    record_episode_baseline,
)
from .postgres import PostgresPhase1Ledger
from .state_machine import CarryStateMachine, IntentState


def submit_engineering_entry(
    *,
    connection,
    runtime,
    risk_service,
    manifest,
    account,
    limits,
    quantity,
    price,
    receive_gap_ms,
    observed_ns,
    hold_seconds=300,
    allow_test_transport=False,
):
    manifest.assert_deployable()
    if not isinstance(risk_service, ActionRiskService):
        raise ValueError("independent risk process required")
    if not isinstance(runtime, DemoNode) and not allow_test_transport:
        raise ValueError("pinned Demo runtime required")
    strategy = runtime.strategy if isinstance(runtime, DemoNode) else runtime
    with account_execution_lock(connection):
        _account_fresh(account)
        payload = dict(
            environment="demo",
            live_orders=False,
            real_capital=False,
            freshness_basis="local_receive_gap",
            account_reconciled=True,
            receive_gap_ms=list(receive_gap_ms),
            observed_ns=observed_ns,
            purpose="demo_engineering_entry",
            economic_approval=False,
            synthetic_trigger=True,
            action="spot_buy_ioc",
            reduce_only=False,
            quantity=str(quantity),
            price=str(price),
            limits={k: str(v) for k, v in asdict(limits).items()},
            account=_safe_account(account) | {"open_orders": account["open_orders"]},
            hold_seconds=hold_seconds,
        )
        approval = risk_service.evaluate(payload)
        if not approval.approved:
            return {"submitted": False, "reason": approval.reason}
        intent_id, command_id, decision_id = (str(uuid4()) for _ in range(3))
        client_id = "v3e" + uuid4().hex[:29]
        order = strategy.prepare_limit(
            canonical="BTCUSDT.BINANCE",
            side="buy",
            quantity=quantity,
            price=price,
            client_id=client_id,
            post_only=False,
        )
        now = datetime.now(UTC)
        ledger = PostgresPhase1Ledger(connection)
        with connection.transaction():
            connection.execute("SELECT pg_advisory_xact_lock(31092028)")
            _account_fresh(account)
            if (time.time_ns() - observed_ns) / 1e6 + max(receive_gap_ms) > 2000:
                raise ValueError("entry quote expired")
            if connection.execute("SELECT 1 FROM intents WHERE state<>'CLOSED' LIMIT 1").fetchone():
                raise ValueError("existing episode blocks entry")
            if connection.execute(
                "SELECT 1 FROM intents WHERE run_manifest_id=%s LIMIT 1", (manifest.manifest_id,)
            ).fetchone():
                raise ValueError("one engineering episode per manifest; never replay entry")
            if (
                connection.execute(
                    "SELECT 1 FROM order_recovery_checks WHERE status IN ('PENDING','BLOCKED') LIMIT 1"
                ).fetchone()
                or connection.execute(
                    "SELECT 1 FROM fill_event_inbox WHERE status<>'APPLIED' LIMIT 1"
                ).fetchone()
                or connection.execute(
                    "SELECT 1 FROM order_commands WHERE active LIMIT 1"
                ).fetchone()
            ):
                raise ValueError("unresolved execution evidence blocks entry")
            ledger.add_intent(
                IntentRow(
                    intent_id,
                    manifest.manifest_id,
                    manifest.config_sha256,
                    quantity * price,
                    dict(
                        entry_reason="explicit synthetic Demo infrastructure trigger; no alpha claim",
                        target_position="owned Spot long / fee-adjusted perp short",
                        normal_exit="bounded engineering holding deadline",
                        risk_exit="unresolved evidence halts new orders; reconcile before close",
                        max_holding_or_review_at=(
                            now + timedelta(seconds=hold_seconds)
                        ).isoformat(),
                        cost_and_risk_budget="Demo only; 300 USDT leg cap; 10 bps IOC cap; economic gate NOT passed",
                    ),
                    now,
                ),
                strategy_id="phase1_demo_engineering",
            )
            record_episode_baseline(connection, intent_id, account)
            ledger.add_risk_decision(
                RiskDecisionRow(decision_id, intent_id, True, (), None, now),
                observed_leverage={
                    "purpose": "demo_engineering_entry",
                    "request_hash": approval.request_hash,
                },
            )
            machine = CarryStateMachine(intent_id, ledger)
            for state in (IntentState.PLANNED, IntentState.RISK_APPROVED, IntentState.SUBMITTING):
                machine.transition(
                    state, trigger="explicit_demo_engineering", guards={"approved": True}
                )
            ledger.add_command(
                OrderCommandRow(command_id, intent_id, "spot", client_id, quantity, price),
                instrument_id="BTCUSDT.BINANCE",
                side="buy",
                order_type="IOC_LIMIT",
            )
            connection.execute(
                "INSERT INTO order_dispatches(command_id,risk_decision_id,client_order_id,payload,status,claimed_at,updated_at) "
                "VALUES (%s,%s,%s,%s::jsonb,'CLAIMED',%s,%s)",
                (command_id, decision_id, client_id, json.dumps(payload), now, now),
            )
        error = None
        try:
            strategy.orders_enabled = True
            strategy.submit_prepared(order)
        except Exception as exc:
            error = exc
        finally:
            strategy.orders_enabled = False
        DispatchJournal(connection).record_enqueue_result(command_id, error=error)
        return dict(
            submitted=error is None,
            status="UNKNOWN" if error else "ENQUEUED",
            intent_id=intent_id,
            command_id=command_id,
            action="spot_buy_ioc",
        )
