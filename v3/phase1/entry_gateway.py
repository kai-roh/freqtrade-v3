"""Payload-bound Phase 1 entry approval and Demo dispatch gateway.

This gateway intentionally does not relax the economic gates in
``configs/phase1-policy.json``. In particular, unmeasured Spot exchange quote
age still denies normal execution. Tests may inject a fake transport, but the
production path must receive the pinned ``DemoNode`` runtime.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Protocol
from uuid import uuid4

from v3.reproducibility import RunManifest

from .demo_node import DemoNode
from .dispatch import DispatchJournal, DispatchOrder
from .fee_input import policy_with_fee_snapshot
from .ledger import IntentRow, OrderCommandRow, RiskDecisionRow, command_idempotency_key
from .policy import Phase1Policy, load_phase1_policy
from .postgres import PostgresPhase1Ledger
from .risk import CarryRiskContext
from .risk_service import Phase1RiskService
from .state_machine import CarryStateMachine, IntentState
from .transfers import BalanceRoute, choose_balance_route


@dataclass(frozen=True)
class EntryLeg:
    leg: str
    quantity: Decimal
    price: Decimal

    def __post_init__(self) -> None:
        if self.leg not in {"spot", "perp"}:
            raise ValueError("entry leg must be spot or perp")
        if any(not value.is_finite() or value <= 0 for value in (self.quantity, self.price)):
            raise ValueError("entry quantity and price must be positive")

    @property
    def notional(self) -> Decimal:
        return self.quantity * self.price


@dataclass(frozen=True)
class WalletPreflight:
    wallets_sufficient: bool
    transfer_capability_verified: bool
    transfer_authorized: bool


@dataclass(frozen=True)
class EntryGatewayRequest:
    intent_fields: dict[str, str]
    cost_ledger_complete: bool
    leverage_by_instrument: dict[str, str]
    quote_age_ms: int | None
    leg_notional: Decimal
    minimum_notional_by_instrument: dict[str, str]
    local_positions_match_venue: bool
    unexplained_residual_usdt: Decimal
    residual_unclassified_hours: Decimal
    daily_loss_usdt: Decimal
    monthly_abort_cost_usdt: Decimal
    abort_attempts_this_month: int
    consecutive_aborts: int
    spot: EntryLeg
    perp: EntryLeg
    wallet_preflight: WalletPreflight
    evaluated_at: datetime

    def __post_init__(self) -> None:
        if self.spot.leg != "spot" or self.perp.leg != "perp":
            raise ValueError("spot and perp legs must be supplied in canonical order")
        if self.leg_notional <= 0:
            raise ValueError("leg notional must be positive")
        if self.spot.quantity != self.perp.quantity:
            raise ValueError("spot and perp base quantities must match")
        if self.leg_notional != max(self.spot.notional, self.perp.notional):
            raise ValueError("risk context leg_notional must match the larger command notional")
        if self.evaluated_at.tzinfo is None or self.evaluated_at.utcoffset() is None:
            raise ValueError("evaluated_at must include a timezone")


@dataclass(frozen=True)
class EntryGatewayResult:
    intent_id: str
    risk_decision_id: str
    approved: bool
    reasons: tuple[str, ...]
    submitted_command_ids: tuple[str, ...]
    unknown_command_ids: tuple[str, ...]
    pending_command_ids: tuple[str, ...]


class _StrategyTransport(Protocol):
    orders_enabled: bool

    def prepare_limit(
        self,
        *,
        canonical: str,
        side: str,
        quantity: Decimal,
        price: Decimal,
        client_id: str,
        post_only: bool,
        reduce_only: bool = False,
    ): ...

    def submit_prepared(self, order) -> None: ...


def submit_phase1_entry(
    *,
    request: EntryGatewayRequest,
    manifest: RunManifest,
    policy: Phase1Policy,
    ledger: PostgresPhase1Ledger,
    risk_service: Phase1RiskService,
    dispatch: DispatchJournal,
    runtime: DemoNode | _StrategyTransport,
    allow_test_transport: bool = False,
    maximum_decision_age_ms: int = 1000,
) -> EntryGatewayResult:
    """Evaluate risk in the subprocess, persist commands, and enqueue once.

    ``UNKNOWN`` dispatches are terminal until a separate REST recovery proves
    their venue state. The gateway does not submit emergency hedges or exits;
    those remain Phase 1D/1E work.

    Only the first entry leg is submitted by this function. Dispatch refuses a
    second unresolved submission for the same intent by design, so the opposite
    leg is returned as pending until read-only REST recovery records positive
    venue evidence for the first command and a fresh risk decision is made.
    """

    manifest.assert_deployable()
    if policy.environment != "demo" or policy.live_orders or policy.real_capital:
        raise ValueError("Phase 1 entry gateway requires demo-only policy authorization")
    if not isinstance(risk_service, Phase1RiskService):
        raise ValueError("Phase 1 entry gateway requires the independent risk service")
    if manifest.config_sha256 != risk_service.policy_hash:
        raise ValueError("run manifest config hash must match the risk service policy hash")
    expected_policy = policy_with_fee_snapshot(
        load_phase1_policy(risk_service.policy_path), risk_service.fee_snapshot_path
    )
    if policy != expected_policy:
        raise ValueError("gateway policy must match independent risk policy")
    strategy = _strategy(runtime, allow_test_transport=allow_test_transport)
    intent_id = str(uuid4())
    created_at = datetime.now(UTC)
    review_raw = request.intent_fields["max_holding_or_review_at"]
    try:
        review_at = datetime.fromisoformat(review_raw)
    except ValueError as exc:
        raise ValueError("max_holding_or_review_at must be a valid ISO timestamp") from exc
    if review_at.tzinfo is None or review_at.utcoffset() is None:
        raise ValueError("max_holding_or_review_at must include a timezone")
    review_at = review_at.astimezone(UTC)
    minimum_review_at = created_at + timedelta(hours=policy.minimum_holding_hours)
    maximum_review_at = created_at + timedelta(hours=policy.maximum_holding_hours)
    if not minimum_review_at <= review_at <= maximum_review_at:
        raise ValueError("max_holding_or_review_at is outside the Phase 1 holding window")
    fields = dict(request.intent_fields, max_holding_or_review_at=review_at.isoformat())
    intent = IntentRow(
        intent_id=intent_id,
        run_manifest_id=manifest.manifest_id,
        cost_ledger_id=manifest.config_sha256,
        target_notional=request.leg_notional,
        fields=fields,
        created_at=created_at,
    )
    ledger.add_intent(intent, strategy_id="phase1_carry_entry")
    context = CarryRiskContext(
        intent_fields=fields,
        cost_ledger_complete=request.cost_ledger_complete,
        leverage_by_instrument=dict(request.leverage_by_instrument),
        quote_age_ms=request.quote_age_ms,
        leg_notional=request.leg_notional,
        minimum_notional_by_instrument=dict(request.minimum_notional_by_instrument),
        local_positions_match_venue=request.local_positions_match_venue,
        unexplained_residual_usdt=request.unexplained_residual_usdt,
        residual_unclassified_hours=request.residual_unclassified_hours,
        daily_loss_usdt=request.daily_loss_usdt,
        monthly_abort_cost_usdt=request.monthly_abort_cost_usdt,
        abort_attempts_this_month=request.abort_attempts_this_month,
        consecutive_aborts=request.consecutive_aborts,
        idempotency_key_is_new=True,
        environment="demo",
        live_orders=False,
        real_capital=False,
        evaluated_at=request.evaluated_at,
    )
    started = time.monotonic()
    decision = risk_service.evaluate(context)
    latency = int((time.monotonic() - started) * 1000)
    risk_decision_id = str(uuid4())
    ledger.add_risk_decision(
        RiskDecisionRow(
            risk_decision_id,
            intent_id,
            decision.approved,
            decision.reasons,
            decision.quote_age_ms,
            decision.evaluated_at,
        ),
        observed_leverage=decision.observed_leverage,
        decision_latency_ms=latency,
    )
    machine = CarryStateMachine(intent_id, ledger)
    machine.transition(IntentState.PLANNED, trigger="intent_recorded", guards={"persisted": True})
    if not decision.approved:
        machine.transition(IntentState.ABORTING, trigger="risk_denied", guards={"denied": True})
        machine.transition(IntentState.CLOSED, trigger="no_order_submitted", guards={"flat": True})
        return EntryGatewayResult(intent_id, risk_decision_id, False, decision.reasons, (), (), ())

    balance = choose_balance_route(
        wallets_sufficient=request.wallet_preflight.wallets_sufficient,
        transfer_capability_verified=request.wallet_preflight.transfer_capability_verified,
        transfer_authorized=request.wallet_preflight.transfer_authorized,
    )
    if balance.route == BalanceRoute.INTERNAL_TRANSFER:
        machine.transition(
            IntentState.RISK_APPROVED, trigger="risk_approved", guards={"approved": True}
        )
        machine.transition(
            IntentState.TRANSFERRING,
            trigger="wallet_transfer_required",
            guards={"transfer_capability_verified": True, "transfer_authorized": True},
        )
        return EntryGatewayResult(
            intent_id,
            risk_decision_id,
            False,
            (balance.reason,),
            (),
            (),
            (),
        )
    if balance.route == BalanceRoute.ABORT:
        machine.transition(
            IntentState.ABORTING,
            trigger="wallet_preflight_failed",
            guards={"wallet_preflight_failed": True},
        )
        machine.transition(IntentState.CLOSED, trigger="no_order_submitted", guards={"flat": True})
        return EntryGatewayResult(
            intent_id,
            risk_decision_id,
            False,
            (balance.reason,),
            (),
            (),
            (),
        )
    machine.transition(
        IntentState.RISK_APPROVED, trigger="risk_approved", guards={"approved": True}
    )
    with ledger.connection.transaction():
        commands = _record_entry_commands(ledger, intent_id, request)
    machine.transition(
        IntentState.SUBMITTING,
        trigger="commands_recorded",
        guards={
            "wallets_sufficient": balance.route == BalanceRoute.DIRECT_SUBMIT,
            "commands_recorded": True,
        },
    )
    submitted: list[str] = []
    unknown: list[str] = []
    command_id = commands[0]
    try:
        strategy.orders_enabled = True
        order = dispatch.claim(
            command_id,
            risk_decision_id,
            maximum_quote_age_ms=policy.maximum_quote_age_ms,
            maximum_decision_age_ms=maximum_decision_age_ms,
        )
        error: Exception | None = None
        try:
            _submit_order(strategy, order)
        except Exception as exc:  # noqa: BLE001 - uncertainty is durable state.
            error = exc
            unknown.append(command_id)
        else:
            submitted.append(command_id)
        dispatch.record_enqueue_result(command_id, error=error)
        if error is not None:
            machine.transition(
                IntentState.ABORTING,
                trigger="first_leg_unknown",
                guards={"external_state_uncertain": True},
            )
    finally:
        strategy.orders_enabled = False
    return EntryGatewayResult(
        intent_id,
        risk_decision_id,
        True,
        (),
        tuple(submitted),
        tuple(unknown),
        tuple(commands[1:]),
    )


def _strategy(
    runtime: DemoNode | _StrategyTransport, *, allow_test_transport: bool
) -> _StrategyTransport:
    if isinstance(runtime, DemoNode):
        return runtime.strategy
    if not allow_test_transport:
        raise ValueError("production gateway requires the pinned DemoNode runtime")
    return runtime


def _record_entry_commands(
    ledger: PostgresPhase1Ledger, intent_id: str, request: EntryGatewayRequest
) -> tuple[str, str]:
    command_ids: list[str] = []
    for attempt, leg in enumerate((request.spot, request.perp)):
        command_id = str(uuid4())
        key = command_idempotency_key(
            intent_id=intent_id,
            leg=leg.leg,
            attempt=attempt,
            quantity=leg.quantity,
            price=leg.price,
        )
        ledger.add_command(
            OrderCommandRow(command_id, intent_id, leg.leg, key, leg.quantity, leg.price),
            attempt=attempt,
            instrument_id="BTCUSDT.BINANCE" if leg.leg == "spot" else "BTCUSDT-PERP.BINANCE",
            side="buy" if leg.leg == "spot" else "sell",
            order_type="LIMIT_MAKER" if leg.leg == "spot" else "GTX",
        )
        command_ids.append(command_id)
    return (command_ids[0], command_ids[1])


def _submit_order(strategy: _StrategyTransport, order: DispatchOrder) -> None:
    prepared = strategy.prepare_limit(
        canonical=order.instrument_id,
        side=order.side,
        quantity=order.quantity,
        price=order.price,
        client_id=order.client_order_id,
        post_only=True,
        reduce_only=False,
    )
    strategy.submit_prepared(prepared)
