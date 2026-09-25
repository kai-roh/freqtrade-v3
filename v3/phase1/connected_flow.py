"""Durable, order-free observation -> cost evidence -> isolated risk decisions.

This module deliberately has no execution client. A positive scanner target is
a candidate, never an authorization to submit an order.
"""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from v3.reproducibility import RunManifest

from .ledger import CostLedgerEntryRow, IntentRow, RiskDecisionRow
from .observations import Phase1CarryMarketObservation
from .policy import Phase1Policy
from .postgres import PostgresPhase1Ledger
from .risk import CarryRiskContext
from .risk_service import Phase1RiskService
from .scanner import scan_carry
from .state_machine import CarryStateMachine, IntentState


def record_observation_cycle(
    *,
    market: Phase1CarryMarketObservation,
    policy: Phase1Policy,
    manifest: RunManifest,
    ledger: PostgresPhase1Ledger,
    risk_service: Phase1RiskService,
    leverage: int | None,
) -> dict:
    manifest.assert_deployable()
    observed = datetime.now(UTC)
    if not timedelta(0) <= observed - market.captured_at <= timedelta(seconds=30):
        raise ValueError("market observation is stale or from the future")
    # Atomic observation batch: no half-written instrument/quote relationships.
    with ledger.connection.transaction():
        for instrument in (market.spot_instrument, market.perp_instrument):
            ledger.add_instrument_snapshot(instrument.to_postgres_row())
        for quote in (market.spot_quote, market.perp_quote):
            ledger.add_quote_observation(quote.to_postgres_row())
    if market.funding.funding_interval_minutes is None:
        return {"orders_submitted": False, "reason": "funding_interval_unmeasured"}

    requested = policy.maximum_carry_leg_notional
    target = scan_carry(
        market.scanner_observation(
            requested_notional=requested,
            holding_period_hours=policy.maximum_holding_hours,
        ),
        policy,
    )
    intent_id = str(uuid4())
    fields = {
        "entry_reason": "observation_only: " + target.decision_reason,
        "target_position": json.dumps(
            {"candidate_notional": str(target.target_notional), "orders_enabled": False}
        ),
        "normal_exit": "funding convergence or maximum holding review",
        "risk_exit": "deny on stale quote, incomplete costs, or unverified reconciliation",
        "max_holding_or_review_at": (
            observed + timedelta(hours=target.holding_period_hours)
        ).isoformat(),
        "cost_and_risk_budget": json.dumps(target.to_dict(), sort_keys=True),
    }
    # target_notional stores the evaluated sizing scenario, not a fabricated $1
    # order when the scanner emits zero. Candidate zero remains in intent fields.
    intent = IntentRow(
        intent_id, manifest.manifest_id, target.cost_ledger_id, requested, fields, observed
    )
    with ledger.connection.transaction():
        ledger.add_intent(intent, strategy_id="phase1_observation_only")
        for category, bps in (
            (
                "spot_round_trip_fee",
                policy.fee_schedule.spot_maker_bps * 2
                if policy.fee_schedule.spot_maker_bps is not None
                else None,
            ),
            (
                "perp_round_trip_fee",
                policy.fee_schedule.perp_maker_bps * 2
                if policy.fee_schedule.perp_maker_bps is not None
                else None,
            ),
            ("impact", None),
            ("legging", None),
            ("rebalance", None),
            ("requote", None),
            ("funding_reversal", None),
        ):
            ledger.add_cost_entry(
                CostLedgerEntryRow(
                    str(uuid4()),
                    intent_id,
                    target.cost_ledger_id,
                    category,
                    requested * bps / Decimal("10000") if bps is not None else None,
                    None,
                    "USDT",
                    "per_leg_notional",
                    policy.fee_schedule.source if bps is not None else "unmeasured",
                    policy.fee_schedule.captured_at if bps is not None else None,
                    {
                        "demo_fee_ignored": True,
                        "observation_only": True,
                        "target": target.to_dict(),
                    },
                )
            )
        ledger.connection.execute(
            """INSERT INTO funding_events
            (id,intent_id,instrument_id,interval_minutes,funding_rate,settlement_at,source)
            VALUES (%s,%s,%s,%s,%s,%s,%s)""",
            (
                str(uuid4()),
                intent_id,
                market.perp_instrument.instrument_id,
                market.funding.funding_interval_minutes,
                market.funding.funding_rate,
                market.funding.settlement_at,
                market.funding.source_environment + ":" + market.funding.source,
            ),
        )

    risk_observed = datetime.now(UTC)
    ages = [q.market_age_ms for q in (market.spot_quote, market.perp_quote)]
    age = (
        None
        if any(a is None for a in ages)
        else max(
            a + max(0, int((risk_observed - q.received_at).total_seconds() * 1000))
            for a, q in zip(ages, (market.spot_quote, market.perp_quote), strict=True)
        )
    )
    context = CarryRiskContext(
        intent_fields=fields,
        cost_ledger_complete=False,
        leverage_by_instrument={
            "BTCUSDT.BINANCE": "1",
            **({"BTCUSDT-PERP.BINANCE": str(leverage)} if leverage is not None else {}),
        },
        quote_age_ms=age,
        leg_notional=requested,
        minimum_notional_by_instrument={
            s.instrument_id: s.minimum_notional
            for s in (market.spot_instrument, market.perp_instrument)
        },
        # Account authentication is NOT position reconciliation. No fabricated pass.
        local_positions_match_venue=False,
        unexplained_residual_usdt="0",
        residual_unclassified_hours="0",
        daily_loss_usdt="0",
        monthly_abort_cost_usdt="0",
        abort_attempts_this_month=0,
        consecutive_aborts=0,
        idempotency_key_is_new=True,
        environment="demo",
        live_orders=False,
        real_capital=False,
        evaluated_at=risk_observed,
    )
    started = time.monotonic()
    decision = risk_service.evaluate(context)
    latency = int((time.monotonic() - started) * 1000)
    if decision.approved:
        raise RuntimeError("observation-only context unexpectedly approved")
    with ledger.connection.transaction():
        ledger.add_risk_decision(
            RiskDecisionRow(
                str(uuid4()),
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
        machine.transition(IntentState.PLANNED, trigger="observation", guards={"persisted": True})
        machine.transition(IntentState.ABORTING, trigger="risk_denied", guards={"denied": True})
        machine.transition(
            IntentState.CLOSED, trigger="no_order_submitted", guards={"orders_disabled": True}
        )
    return {
        "schema_version": 1,
        "manifest_id": manifest.manifest_id,
        "intent_id": intent_id,
        "target": target.to_dict(),
        "risk": decision.to_dict(),
        "risk_latency_ms": latency,
        "orders_submitted": False,
        "final_state": "CLOSED",
        "source": "live_public_observation",
    }
