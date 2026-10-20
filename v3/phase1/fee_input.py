"""Credentialed fee snapshot loading for Phase 1 scanner and risk service."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime
from pathlib import Path

from v3.costs import as_decimal

from .policy import FeeSchedule, Phase1Policy


def load_fee_snapshot(path: Path) -> FeeSchedule:
    data = json.loads(path.read_text())
    if data.get("schema_version") != 1:
        raise ValueError("fee snapshot schema_version must be 1")
    if data.get("symbol") != "BTCUSDT":
        raise ValueError("fee snapshot must be for BTCUSDT")
    if data.get("include_exit_cost") is not True:
        raise ValueError("fee snapshot must include exit cost")
    if data.get("bnb_discount_applied") is not False:
        raise ValueError("Phase 1 fee snapshot must exclude optional BNB discount")
    source = str(data.get("source", ""))
    if not source.startswith("credentialed-mainnet-account-query-from-"):
        raise ValueError("fee snapshot source must be a credentialed mainnet account query")
    maximum_age_hours = data.get("maximum_age_hours")
    if isinstance(maximum_age_hours, bool) or not isinstance(maximum_age_hours, int):
        raise ValueError("fee snapshot maximum_age_hours must be an integer")
    if maximum_age_hours <= 0 or maximum_age_hours > 24:
        raise ValueError("Phase 1 fee snapshot TTL must be in (0, 24] hours")

    spot_maker = as_decimal(data.get("spot_maker_bps"), field_name="spot_maker_bps")
    spot_taker = as_decimal(data.get("spot_taker_bps"), field_name="spot_taker_bps")
    perp_maker = as_decimal(data.get("perp_maker_bps"), field_name="perp_maker_bps")
    perp_taker = as_decimal(data.get("perp_taker_bps"), field_name="perp_taker_bps")
    entry = as_decimal(data.get("normal_entry_cost_bps"), field_name="normal_entry_cost_bps")
    round_trip = as_decimal(
        data.get("normal_round_trip_cost_bps"), field_name="normal_round_trip_cost_bps"
    )
    if entry != spot_maker + perp_maker or round_trip != entry * 2:
        raise ValueError("fee snapshot aggregate maker costs do not match leg fees")

    return FeeSchedule(
        spot_maker_bps=spot_maker,
        spot_taker_bps=spot_taker,
        perp_maker_bps=perp_maker,
        perp_taker_bps=perp_taker,
        source=source,
        include_exit_cost=True,
        captured_at=datetime.fromisoformat(str(data["captured_at"])),
        maximum_age_hours=maximum_age_hours,
    )


def policy_with_fee_snapshot(policy: Phase1Policy, path: Path | None) -> Phase1Policy:
    if path is None:
        return policy
    return replace(policy, fee_schedule=load_fee_snapshot(path))
