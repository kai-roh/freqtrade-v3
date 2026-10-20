from decimal import Decimal

import pytest

from v3.costs import (
    CostBasis,
    CostCategory,
    CostLedger,
    CostLine,
    ExecutionLeg,
    ExecutionType,
)


def test_cost_ledger_accounts_for_execution_and_non_execution_costs_exactly():
    ledger = CostLedger(
        strategy_id="carry-v1",
        executions=(
            ExecutionLeg(
                event_id="event-1",
                leg_id="spot",
                venue="hyperliquid",
                instrument_id="BTC",
                execution_type=ExecutionType.MAKER_LIMIT,
                notional="100",
                fee_rate="0.00015",
                fee_source="official-tier-0",
            ),
            ExecutionLeg(
                event_id="event-1",
                leg_id="perp",
                venue="hyperliquid",
                instrument_id="BTC-PERP",
                execution_type=ExecutionType.STOP_MARKET,
                notional="100",
                fee_rate="0.00045",
                fee_source="official-tier-0",
            ),
        ),
        other_costs=(
            CostLine(
                CostCategory.FUNDING_OR_BORROW,
                "-0.01",
                "observed-funding-event",
                CostBasis.OBSERVED,
            ),
            CostLine(CostCategory.LEGGING_LOSS, "0.02", "paper-fill-estimate"),
        ),
    )

    assert ledger.total_cost == Decimal("0.07000")
    assert ledger.totals_by_category()[CostCategory.EXECUTION_FEE] == Decimal("0.06000")
    assert ledger.to_dict()["total_cost"] == "0.07000"


def test_cost_gate_requires_observed_edge_to_exceed_buffered_positive_cost():
    ledger = CostLedger(
        strategy_id="basket-v1",
        other_costs=(CostLine(CostCategory.MARKET_IMPACT, "0.20", "depth-snapshot"),),
    )

    required = ledger.required_gross_edge("200", "1.5")
    rejected = ledger.evaluate(required, "200", "1.5")
    passed = ledger.evaluate("0.0016", "200", "1.5")

    assert required == Decimal("0.0015")
    assert not rejected.passed
    assert passed.passed


def test_cost_inputs_fail_closed_on_missing_source_or_binary_float():
    with pytest.raises(ValueError, match="source"):
        CostLine(CostCategory.REQUOTE, "0.1", "")
    with pytest.raises(ValueError, match="fee_source"):
        ExecutionLeg(
            event_id="e",
            leg_id="l",
            venue="venue",
            instrument_id="instrument",
            execution_type=ExecutionType.MARKET,
            notional="10",
            fee_rate="0.001",
            fee_source="",
        )
    with pytest.raises(TypeError, match="Decimal"):
        CostLine(CostCategory.REBALANCING, 0.1, "estimate")
