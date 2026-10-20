"""Demo-only Binance account preparation for Phase 1.

This module is deliberately narrower than a trading client. It can inspect the
Demo USD-M account and, with an explicit caller flag, request isolated margin and
2x leverage while the symbol is flat. It cannot place orders or transfer funds.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from .binance_probe import (
    USDM_DEMO,
    BinanceCredentials,
    BinanceDemoConfigClient,
    BinanceReadOnlyClient,
    ProbeResponse,
)

SYMBOL = "BTCUSDT"
TARGET_MARGIN_TYPE = "ISOLATED"
TARGET_LEVERAGE = 2


@dataclass(frozen=True)
class DemoFuturesPreparation:
    apply_requested: bool
    flat: bool
    open_order_count: int | None
    nonzero_position_count: int | None
    margin_type: str | None
    leverage: int | None
    usdt_available_positive: bool | None
    usdt_available_at_least_300: bool | None
    actions_required: tuple[str, ...]
    actions_applied: tuple[str, ...]
    blocked_reasons: tuple[str, ...]

    @property
    def ready_for_phase1_demo_execution(self) -> bool:
        return (
            self.flat
            and self.margin_type == TARGET_MARGIN_TYPE
            and self.leverage is not None
            and 0 < self.leverage <= TARGET_LEVERAGE
            and self.usdt_available_at_least_300 is True
            and not self.blocked_reasons
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "environment": "demo",
            "symbol": SYMBOL,
            "apply_requested": self.apply_requested,
            "flat": self.flat,
            "open_order_count": self.open_order_count,
            "nonzero_position_count": self.nonzero_position_count,
            "margin_type": self.margin_type,
            "leverage": self.leverage,
            "usdt_available_positive": self.usdt_available_positive,
            "usdt_available_at_least_300": self.usdt_available_at_least_300,
            "actions_required": list(self.actions_required),
            "actions_applied": list(self.actions_applied),
            "blocked_reasons": list(self.blocked_reasons),
            "ready_for_phase1_demo_execution": self.ready_for_phase1_demo_execution,
            "safety": {
                "matching_engine_orders_submitted": False,
                "transfers_submitted": False,
                "mainnet_endpoints_called": False,
            },
        }


def prepare_demo_futures_account(
    credentials: BinanceCredentials,
    *,
    apply_changes: bool,
    opener: Any,
) -> DemoFuturesPreparation:
    reader = BinanceReadOnlyClient(credentials, opener=opener)
    account = reader.get(
        USDM_DEMO,
        "/fapi/v3/account",
        signed=True,
        server_time_path="/fapi/v1/time",
    )
    open_orders = reader.get(
        USDM_DEMO,
        "/fapi/v1/openOrders",
        signed=True,
        params={"symbol": SYMBOL},
        server_time_path="/fapi/v1/time",
    )
    symbol_config = reader.get(
        USDM_DEMO,
        "/fapi/v1/symbolConfig",
        signed=True,
        params={"symbol": SYMBOL},
        server_time_path="/fapi/v1/time",
    )

    facts = _extract_futures_facts(account, open_orders, symbol_config)
    blocked = list(facts["blocked_reasons"])
    open_order_count = facts["open_order_count"]
    nonzero_position_count = facts["nonzero_position_count"]
    flat = open_order_count == 0 and nonzero_position_count == 0
    if open_order_count is None or nonzero_position_count is None:
        blocked.append("flatness could not be measured")
    elif not flat:
        blocked.append("symbol is not flat")

    actions = []
    if facts["margin_type"] != TARGET_MARGIN_TYPE:
        actions.append("set_margin_type_isolated")
    if facts["leverage"] != TARGET_LEVERAGE:
        actions.append("set_leverage_2")

    applied: list[str] = []
    if facts["usdt_available_at_least_300"] is not True:
        blocked.append("Demo Futures USDT available balance is below 300 or unknown")
    if apply_changes and not blocked and actions:
        client = BinanceDemoConfigClient(credentials, opener=opener)
        if "set_margin_type_isolated" in actions:
            response = client.post(
                USDM_DEMO,
                "/fapi/v1/marginType",
                params={"symbol": SYMBOL, "marginType": TARGET_MARGIN_TYPE},
                server_time_path="/fapi/v1/time",
            )
            if _configuration_ok(response, already_done_code=-4046):
                applied.append("set_margin_type_isolated")
            else:
                blocked.append("margin type update failed")
        if "set_leverage_2" in actions and not blocked:
            response = client.post(
                USDM_DEMO,
                "/fapi/v1/leverage",
                params={"symbol": SYMBOL, "leverage": TARGET_LEVERAGE},
                server_time_path="/fapi/v1/time",
            )
            if _configuration_ok(response):
                applied.append("set_leverage_2")
            else:
                blocked.append("leverage update failed")
        if applied:
            refreshed = reader.get(
                USDM_DEMO,
                "/fapi/v1/symbolConfig",
                signed=True,
                params={"symbol": SYMBOL},
                server_time_path="/fapi/v1/time",
            )
            facts.update(_extract_symbol_config(refreshed))

    if facts["usdt_available_at_least_300"] is False:
        blocked.append("Demo Futures USDT available balance is below 300")

    return DemoFuturesPreparation(
        apply_requested=apply_changes,
        flat=flat,
        open_order_count=open_order_count,
        nonzero_position_count=nonzero_position_count,
        margin_type=facts["margin_type"],
        leverage=facts["leverage"],
        usdt_available_positive=facts["usdt_available_positive"],
        usdt_available_at_least_300=facts["usdt_available_at_least_300"],
        actions_required=tuple(actions),
        actions_applied=tuple(applied),
        blocked_reasons=tuple(dict.fromkeys(blocked)),
    )


def _extract_futures_facts(
    account: ProbeResponse,
    open_orders: ProbeResponse,
    symbol_config: ProbeResponse,
) -> dict[str, Any]:
    facts = {
        "open_order_count": None,
        "nonzero_position_count": None,
        "margin_type": None,
        "leverage": None,
        "usdt_available_positive": None,
        "usdt_available_at_least_300": None,
        "blocked_reasons": [],
    }
    if not account.ok or not isinstance(account.data, Mapping):
        facts["blocked_reasons"].append("USD-M account endpoint unavailable")
    else:
        facts.update(_extract_account(account.data))
    if not open_orders.ok or not isinstance(open_orders.data, list):
        facts["blocked_reasons"].append("open orders endpoint unavailable")
    else:
        facts["open_order_count"] = len(open_orders.data)
    facts.update(_extract_symbol_config(symbol_config))
    if facts["margin_type"] is None or facts["leverage"] is None:
        facts["blocked_reasons"].append("symbol configuration endpoint unavailable")
    return facts


def _extract_account(data: Mapping[str, Any]) -> dict[str, Any]:
    positions = data.get("positions")
    assets = data.get("assets")
    nonzero = None
    if isinstance(positions, list):
        nonzero = sum(
            1
            for position in positions
            if isinstance(position, Mapping)
            and position.get("symbol") == SYMBOL
            and _decimal(position.get("positionAmt")) != Decimal("0")
        )
    available = None
    if isinstance(assets, list):
        for asset in assets:
            if isinstance(asset, Mapping) and asset.get("asset") == "USDT":
                available = _decimal(asset.get("availableBalance"))
                break
    return {
        "nonzero_position_count": nonzero,
        "usdt_available_positive": None if available is None else available > 0,
        "usdt_available_at_least_300": None if available is None else available >= Decimal("300"),
    }


def _extract_symbol_config(response: ProbeResponse) -> dict[str, Any]:
    data = response.data if response.ok else None
    if isinstance(data, list) and data and isinstance(data[0], Mapping):
        data = data[0]
    if not isinstance(data, Mapping):
        return {"margin_type": None, "leverage": None}
    if data.get("symbol") != SYMBOL:
        return {"margin_type": None, "leverage": None}
    leverage = data.get("leverage")
    if isinstance(leverage, str) and leverage.isdigit():
        leverage = int(leverage)
    return {
        "margin_type": str(data.get("marginType", "")).upper() or None,
        "leverage": leverage
        if isinstance(leverage, int) and not isinstance(leverage, bool)
        else None,
    }


def _decimal(value: Any) -> Decimal:
    try:
        result = Decimal(str(value))
        if not result.is_finite():
            raise ValueError("nonfinite account value")
        return result
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError("account numeric field is missing or invalid") from None


def _configuration_ok(response: ProbeResponse, *, already_done_code: int | None = None) -> bool:
    if response.ok:
        return True
    return already_done_code is not None and response.exchange_code == already_done_code
