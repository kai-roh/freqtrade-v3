from decimal import Decimal

import pytest

from v3.phase1.episode_plan import (
    EpisodeActionType,
    EpisodeLimits,
    EpisodePhase,
    EpisodeSnapshot,
    plan_episode_action,
)


def limits(**overrides):
    values = {
        "spot_lot_size": "0.00001",
        "perp_lot_size": "0.001",
        "spot_min_notional": "5",
        "perp_min_notional": "50",
        "spot_bid": "60000",
        "spot_ask": "60001",
        "perp_bid": "60000",
        "perp_ask": "60001",
    }
    values.update(overrides)
    return EpisodeLimits(**values)


def snapshot(**overrides):
    values = {
        "phase": EpisodePhase.ENTRY,
        "spot_filled_base": "0",
        "perp_filled_base": "0",
    }
    values.update(overrides)
    values.setdefault(
        "venue_spot_base",
        str(Decimal(values["spot_filled_base"]) - Decimal(values.get("spot_base_fee", "0"))),
    )
    values.setdefault("venue_perp_base", values["perp_filled_base"])
    return EpisodeSnapshot(**values)


@pytest.mark.parametrize("field", ["venue_spot_base", "venue_perp_base"])
def test_missing_venue_evidence_never_authorizes_action(field):
    assert (
        plan_episode_action(snapshot(**{field: None}), limits()).action == EpisodeActionType.BLOCKED
    )


def test_sub_lot_foreign_inventory_is_not_treated_as_owned():
    action = plan_episode_action(snapshot(venue_spot_base="0.000001"), limits())
    assert action.action == EpisodeActionType.BLOCKED


def test_flat_entry_allows_one_entry_pair_when_no_unresolved_evidence():
    action = plan_episode_action(snapshot(), limits())

    assert action.action == EpisodeActionType.SUBMIT_ENTRY_PAIR
    assert action.quantity is None


@pytest.mark.parametrize(
    "field",
    ["pending_command_count", "unknown_dispatch_count", "open_order_count"],
)
def test_unresolved_evidence_blocks_new_entry_and_replay(field):
    action = plan_episode_action(snapshot(**{field: 1}), limits())

    assert action.action == EpisodeActionType.WAIT
    assert action.quantity is None
    assert "blocks new actions" in action.reason


def test_hedges_only_confirmed_net_spot_after_base_fee_floored_to_perp_lot():
    action = plan_episode_action(
        snapshot(
            spot_filled_base="0.0109",
            spot_base_fee="0.00004",
            perp_filled_base="-0.002",
            venue_spot_base="0.01086",
            venue_perp_base="-0.002",
        ),
        limits(),
    )

    assert action.action == EpisodeActionType.HEDGE_PERP_SELL
    assert action.quantity == Decimal("0.008")
    assert not action.reduce_only


def test_unhedged_remainder_below_perp_lot_is_explicit_dust_not_flat():
    action = plan_episode_action(
        snapshot(spot_filled_base="0.00099", perp_filled_base="0"),
        limits(perp_min_notional="1"),
    )

    assert action.action == EpisodeActionType.DUST_REMAINS
    assert action.dust_base == Decimal("0.00099")
    assert action.blocks_new_entry


def test_perp_overhedge_blocks_instead_of_adding_spot_exposure():
    action = plan_episode_action(
        snapshot(spot_filled_base="0.004", perp_filled_base="-0.005"),
        limits(),
    )

    assert action.action == EpisodeActionType.BLOCKED
    assert "exceeds confirmed owned Spot" in action.reason


def test_perp_only_partial_fill_is_closed_reduce_only_before_any_spot_sale():
    action = plan_episode_action(
        snapshot(
            phase=EpisodePhase.CLOSING,
            spot_filled_base="0",
            perp_filled_base="-0.002",
        ),
        limits(),
    )

    assert action.action == EpisodeActionType.CLOSE_PERP_BUY
    assert action.quantity == Decimal("0.002")
    assert action.reduce_only


def test_closing_sells_only_owned_net_spot_after_perp_is_flat():
    action = plan_episode_action(
        snapshot(
            phase=EpisodePhase.CLOSING,
            spot_filled_base="0.01003",
            spot_base_fee="0.00002",
            perp_filled_base="0",
        ),
        limits(),
    )

    assert action.action == EpisodeActionType.CLOSE_SPOT_SELL
    assert action.quantity == Decimal("0.01001")
    assert not action.reduce_only


def test_spot_dust_after_close_is_not_reported_flat():
    action = plan_episode_action(
        snapshot(
            phase=EpisodePhase.CLOSING,
            spot_filled_base="0.00008",
            perp_filled_base="0",
        ),
        limits(spot_min_notional="10"),
    )

    assert action.action == EpisodeActionType.DUST_REMAINS
    assert action.dust_base == Decimal("0.00008")


@pytest.mark.parametrize(
    "overrides,reason",
    [
        ({"venue_spot_base": "0.01"}, "venue Spot inventory"),
        ({"venue_perp_base": "-0.01"}, "venue perp position"),
        ({"spot_base_fee": "0.001"}, "Spot base fee exceeds"),
        ({"perp_filled_base": "0.001"}, "unexpected long perp"),
    ],
)
def test_inconsistent_or_foreign_snapshots_fail_closed(overrides, reason):
    action = plan_episode_action(snapshot(**overrides), limits())

    assert action.action == EpisodeActionType.BLOCKED
    assert reason in action.reason


def test_settled_residual_is_subtracted_from_owned_spot_and_bounded_by_inventory():
    closing = snapshot(
        phase=EpisodePhase.CLOSING,
        spot_filled_base="0.005",
        spot_base_fee="0.000005",
        settled_residual_base="0.000005",
        venue_spot_base="0.00499",
    )
    assert closing.net_spot_base == Decimal("0.00499")
    assert plan_episode_action(closing, limits()).action == EpisodeActionType.CLOSE_SPOT_SELL
    flat = snapshot(
        phase=EpisodePhase.CLOSING,
        spot_filled_base="0.000005",
        settled_residual_base="0.000005",
        venue_spot_base="0",
    )
    assert plan_episode_action(flat, limits()).action == EpisodeActionType.WAIT
    excessive = snapshot(
        phase=EpisodePhase.CLOSING,
        spot_filled_base="0.000005",
        settled_residual_base="0.000006",
        venue_spot_base="-0.000001",
    )
    assert plan_episode_action(excessive, limits()).action == EpisodeActionType.BLOCKED
    with pytest.raises(ValueError):
        snapshot(settled_residual_base="-0.000001")
