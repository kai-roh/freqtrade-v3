from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from v3.phase1.policy import FeeSchedule, load_phase1_policy
from v3.phase1.scanner import CarryObservation, scan_carry

ROOT = Path(__file__).resolve().parents[1]
CAPTURED_AT = datetime(2026, 9, 3, 2, 27, 4, 465026, tzinfo=UTC)


def _observation(rate="0.0001", hours=720, notional="300", venue="binance"):
    return CarryObservation(
        venue=venue,
        spot_instrument_id="BTCUSDT.BINANCE",
        perp_instrument_id="BTCUSDT-PERP.BINANCE",
        requested_notional=notional,
        funding_rate=rate,
        funding_interval_minutes=480,
        holding_period_hours=hours,
        instrument_snapshot_id="snapshot-1",
        observed_at=CAPTURED_AT,
    )


def _fees():
    return FeeSchedule(
        spot_maker_bps=Decimal("10"),
        spot_taker_bps=Decimal("10"),
        perp_maker_bps=Decimal("2"),
        perp_taker_bps=Decimal("5"),
        source="credentialed-mainnet-fixture",
        include_exit_cost=True,
        captured_at=CAPTURED_AT,
        maximum_age_hours=24,
    )


def test_scanner_is_observation_only_when_mainnet_fees_are_unknown():
    policy = load_phase1_policy(ROOT / "configs" / "phase1-policy.json")
    missing = FeeSchedule(None, None, None, None, "missing-fixture", True)

    target = scan_carry(_observation(), policy, fee_schedule=missing)

    assert not target.actionable
    assert target.net_expected_bps is None
    assert target.decision_reason.startswith("observe_only")


def test_scanner_includes_exit_fees_and_abort_probability_in_expected_net():
    policy = load_phase1_policy(ROOT / "configs" / "phase1-policy.json")

    target = scan_carry(_observation(), policy, fee_schedule=_fees())

    assert target.expected_gross_bps == Decimal("90.0000")
    assert target.expected_success_cost_bps == Decimal("24")
    assert target.net_expected_bps == Decimal("46.800000")
    assert target.actionable


def test_cost_ledger_identity_changes_with_exit_or_emergency_fee_assumptions():
    policy = load_phase1_policy(ROOT / "configs" / "phase1-policy.json")
    baseline = scan_carry(_observation(), policy, fee_schedule=_fees())
    no_exit = scan_carry(
        _observation(),
        policy,
        fee_schedule=FeeSchedule(
            spot_maker_bps=Decimal("10"),
            spot_taker_bps=Decimal("10"),
            perp_maker_bps=Decimal("2"),
            perp_taker_bps=Decimal("5"),
            source="credentialed-mainnet-fixture",
            include_exit_cost=False,
            captured_at=CAPTURED_AT,
            maximum_age_hours=24,
        ),
    )
    higher_taker = scan_carry(
        _observation(),
        policy,
        fee_schedule=FeeSchedule(
            spot_maker_bps=Decimal("10"),
            spot_taker_bps=Decimal("11"),
            perp_maker_bps=Decimal("2"),
            perp_taker_bps=Decimal("5"),
            source="credentialed-mainnet-fixture",
            include_exit_cost=True,
            captured_at=CAPTURED_AT,
            maximum_age_hours=24,
        ),
    )

    assert baseline.cost_ledger_id != no_exit.cost_ledger_id
    assert baseline.cost_ledger_id != higher_taker.cost_ledger_id


def test_low_funding_or_negative_funding_yields_zero_target():
    policy = load_phase1_policy(ROOT / "configs" / "phase1-policy.json")

    low = scan_carry(_observation(rate="0.00005"), policy, fee_schedule=_fees())
    negative = scan_carry(_observation(rate="-0.0001"), policy, fee_schedule=_fees())

    assert low.net_expected_bps == Decimal("10.800000")
    assert not low.actionable
    assert not negative.actionable
    assert "not positive" in negative.decision_reason


def test_stale_fee_snapshot_keeps_scanner_observational():
    policy = load_phase1_policy(ROOT / "configs" / "phase1-policy.json")
    observation = _observation()
    object.__setattr__(observation, "observed_at", CAPTURED_AT + timedelta(hours=25))

    target = scan_carry(observation, policy, fee_schedule=_fees())

    assert not target.actionable
    assert target.net_expected_bps is None
    assert "stale" in target.decision_reason


def test_scanner_rejects_unapproved_instrument_or_holding_period():
    policy = load_phase1_policy(ROOT / "configs" / "phase1-policy.json")
    wrong = CarryObservation(
        venue="binance",
        spot_instrument_id="ETHUSDT.BINANCE",
        perp_instrument_id="ETHUSDT-PERP.BINANCE",
        requested_notional="300",
        funding_rate="0.0001",
        funding_interval_minutes=480,
        holding_period_hours=720,
        instrument_snapshot_id="snapshot-1",
        observed_at=CAPTURED_AT,
    )
    with pytest.raises(ValueError, match="approved"):
        scan_carry(wrong, policy, fee_schedule=_fees())
    with pytest.raises(ValueError, match="holding period"):
        scan_carry(_observation(hours=24), policy, fee_schedule=_fees())

    with pytest.raises(ValueError, match="collateral boundary"):
        scan_carry(_observation(notional="301"), policy, fee_schedule=_fees())

    with pytest.raises(ValueError, match="venue"):
        scan_carry(_observation(venue="not-binance"), policy, fee_schedule=_fees())
