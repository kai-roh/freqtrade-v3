"""Declarative Binance Demo client specs and lazy Nautilus construction."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class BinanceClientSpec:
    client_id: str
    account_type: str
    environment: str = "DEMO"
    query_commission_rates: bool = True
    order_submission_enabled: bool = False

    def __post_init__(self) -> None:
        if self.account_type not in {"SPOT", "USDT_FUTURES"}:
            raise ValueError("unsupported Binance account type")
        if self.environment != "DEMO":
            raise ValueError("Phase 1 Binance clients must use DEMO")
        if self.order_submission_enabled:
            raise ValueError("Phase 1A clients must be order-free")


def phase1_binance_client_specs() -> tuple[BinanceClientSpec, BinanceClientSpec]:
    return (
        BinanceClientSpec(client_id="BINANCE_SPOT_DEMO", account_type="SPOT"),
        BinanceClientSpec(client_id="BINANCE_USDM_DEMO", account_type="USDT_FUTURES"),
    )


def build_nautilus_client_configs(
    *,
    api_key: str,
    api_secret: str,
) -> dict[str, dict[str, Any]]:
    """Build version-pinned Nautilus configs without starting a node or submitting orders."""

    if not api_key.strip() or not api_secret.strip():
        raise ValueError("Binance Demo credentials are required")
    try:
        from nautilus_trader.adapters.binance.common.enums import (
            BinanceAccountType,
            BinanceEnvironment,
        )
        from nautilus_trader.adapters.binance.config import (
            BinanceDataClientConfig,
            BinanceExecClientConfig,
            BinanceInstrumentProviderConfig,
        )
    except ImportError as exc:
        raise RuntimeError("install the locked execution dependencies first") from exc

    provider = BinanceInstrumentProviderConfig(
        load_all=False,
        filters={"symbols": ["BTCUSDT"]},
        query_commission_rates=True,
    )
    data_clients: dict[str, Any] = {}
    execution_clients: dict[str, Any] = {}
    for spec in phase1_binance_client_specs():
        account_type = getattr(BinanceAccountType, spec.account_type)
        common = {
            "api_key": api_key,
            "api_secret": api_secret,
            "account_type": account_type,
            "environment": BinanceEnvironment.DEMO,
            "instrument_provider": provider,
        }
        data_clients[spec.client_id] = BinanceDataClientConfig(**common)
        execution_clients[spec.client_id] = BinanceExecClientConfig(**common)
    return {"data_clients": data_clients, "execution_clients": execution_clients}
