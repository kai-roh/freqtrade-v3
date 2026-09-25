"""Wallet-balance routing without assuming Demo universal-transfer support."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class BalanceRoute(StrEnum):
    DIRECT_SUBMIT = "direct_submit"
    INTERNAL_TRANSFER = "internal_transfer"
    ABORT = "abort"


@dataclass(frozen=True)
class BalancePreparation:
    route: BalanceRoute
    reason: str


def choose_balance_route(
    *,
    wallets_sufficient: bool,
    transfer_capability_verified: bool,
    transfer_authorized: bool,
) -> BalancePreparation:
    if wallets_sufficient:
        return BalancePreparation(BalanceRoute.DIRECT_SUBMIT, "both wallets are funded")
    if transfer_capability_verified and transfer_authorized:
        return BalancePreparation(
            BalanceRoute.INTERNAL_TRANSFER,
            "wallet funding requires a pre-recorded internal transfer",
        )
    return BalancePreparation(
        BalanceRoute.ABORT,
        "wallet balance is insufficient and transfer capability is not verified and authorized",
    )
