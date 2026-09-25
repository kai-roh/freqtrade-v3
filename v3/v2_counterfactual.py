"""Verified V2 fee-only counterfactual preparation for block bootstrap."""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .costs import DecimalInput, as_decimal

REQUIRED_TRADE_COLUMNS = {"id", "close_date", "close_profit_abs", "is_open"}
REQUIRED_ORDER_COLUMNS = {
    "id",
    "ft_trade_id",
    "order_type",
    "cost",
    "filled",
    "status",
}


@dataclass(frozen=True)
class FeeOnlyCounterfactualSpec:
    original_fee_rate: DecimalInput
    maker_fee_rate: DecimalInput
    taker_fee_rate: DecimalInput
    reference_capital: DecimalInput
    reporting_timezone: str = "Asia/Seoul"
    scenario_id: str = "all-limit-maker-nonlimit-taker"

    def __post_init__(self) -> None:
        for name in (
            "original_fee_rate",
            "maker_fee_rate",
            "taker_fee_rate",
            "reference_capital",
        ):
            value = as_decimal(getattr(self, name), field_name=name)
            if value <= 0:
                raise ValueError(f"{name} must be positive")
            object.__setattr__(self, name, value)
        if not self.scenario_id.strip():
            raise ValueError("scenario_id is required")
        try:
            ZoneInfo(self.reporting_timezone)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"unknown reporting timezone: {self.reporting_timezone}") from exc

    def to_dict(self) -> dict[str, str]:
        return {
            "scenario_id": self.scenario_id,
            "original_fee_rate": str(self.original_fee_rate),
            "maker_fee_rate": str(self.maker_fee_rate),
            "taker_fee_rate": str(self.taker_fee_rate),
            "reference_capital": str(self.reference_capital),
            "reporting_timezone": self.reporting_timezone,
        }


@dataclass(frozen=True)
class DailyCounterfactualReturn:
    day: date
    closed_trade_count: int
    gross_pnl: Decimal
    counterfactual_fee: Decimal
    counterfactual_net_pnl: Decimal
    net_return: Decimal

    def to_dict(self) -> dict[str, str | int]:
        return {
            "timestamp": self.day.isoformat(),
            "closed_trade_count": self.closed_trade_count,
            "gross_pnl": str(self.gross_pnl),
            "counterfactual_fee": str(self.counterfactual_fee),
            "counterfactual_net_pnl": str(self.counterfactual_net_pnl),
            "net_return": str(self.net_return),
        }


@dataclass(frozen=True)
class FeeOnlyCounterfactualResult:
    database_sha256: str
    closed_trade_count: int
    filled_order_count: int
    original_net_pnl: Decimal
    restored_original_fee: Decimal
    gross_pnl: Decimal
    counterfactual_fee: Decimal
    counterfactual_net_pnl: Decimal
    daily_returns: tuple[DailyCounterfactualReturn, ...]
    spec: FeeOnlyCounterfactualSpec

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "database_sha256": self.database_sha256,
            "closed_trade_count": self.closed_trade_count,
            "filled_order_count": self.filled_order_count,
            "original_net_pnl": str(self.original_net_pnl),
            "restored_original_fee": str(self.restored_original_fee),
            "gross_pnl": str(self.gross_pnl),
            "counterfactual_fee": str(self.counterfactual_fee),
            "counterfactual_net_pnl": str(self.counterfactual_net_pnl),
            "calendar_day_count": len(self.daily_returns),
            "spec": self.spec.to_dict(),
        }


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_fee_only_counterfactual(
    database_path: Path,
    *,
    expected_database_sha256: str,
    expected_closed_trade_count: int,
    spec: FeeOnlyCounterfactualSpec,
) -> FeeOnlyCounterfactualResult:
    """Read a hash-matched SQLite database without mutating it."""

    if not database_path.is_file():
        raise ValueError(f"database does not exist: {database_path}")
    wal_path = Path(f"{database_path}-wal")
    if wal_path.exists() and wal_path.stat().st_size:
        raise ValueError("database has a non-empty WAL; checkpoint the frozen export first")
    actual_hash = sha256_file(database_path)
    if actual_hash != expected_database_sha256.lower():
        raise ValueError(
            f"database SHA-256 mismatch: expected={expected_database_sha256} actual={actual_hash}"
        )
    if expected_closed_trade_count <= 0:
        raise ValueError("expected_closed_trade_count must be positive")

    connection = sqlite3.connect(f"{database_path.resolve().as_uri()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        _require_columns(connection, "trades", REQUIRED_TRADE_COLUMNS)
        _require_columns(connection, "orders", REQUIRED_ORDER_COLUMNS)
        trades = connection.execute(
            """
            SELECT id, close_date, close_profit_abs
            FROM trades
            WHERE is_open = 0
            ORDER BY close_date, id
            """
        ).fetchall()
        orders = connection.execute(
            """
            SELECT ft_trade_id, order_type, cost
            FROM orders
            WHERE COALESCE(filled, 0) > 0 AND status = 'closed'
            ORDER BY ft_trade_id, id
            """
        ).fetchall()
    finally:
        connection.close()

    if len(trades) != expected_closed_trade_count:
        raise ValueError(
            "closed trade count mismatch: "
            f"expected={expected_closed_trade_count} actual={len(trades)}"
        )
    orders_by_trade: dict[int, list[sqlite3.Row]] = {}
    for order in orders:
        orders_by_trade.setdefault(int(order["ft_trade_id"]), []).append(order)
    closed_trade_ids = {int(trade["id"]) for trade in trades}
    unexpected_trade_ids = sorted(set(orders_by_trade) - closed_trade_ids)
    if unexpected_trade_ids:
        joined = ", ".join(str(trade_id) for trade_id in unexpected_trade_ids[:10])
        raise ValueError(f"filled orders exist outside the closed-trade universe: {joined}")

    timezone = ZoneInfo(spec.reporting_timezone)
    daily: dict[date, dict[str, Decimal | int]] = {}
    original_net_pnl = Decimal(0)
    restored_original_fee = Decimal(0)
    counterfactual_fee = Decimal(0)

    for trade in trades:
        trade_id = int(trade["id"])
        trade_orders = orders_by_trade.get(trade_id, [])
        if not trade_orders:
            raise ValueError(f"closed trade {trade_id} has no filled closed orders")
        close_date = _parse_freqtrade_datetime(trade["close_date"]).astimezone(timezone).date()
        net_pnl = _required_decimal(trade["close_profit_abs"], f"trade {trade_id} close_profit_abs")
        trade_original_fee = Decimal(0)
        trade_counterfactual_fee = Decimal(0)
        for order in trade_orders:
            cost = _required_decimal(order["cost"], f"trade {trade_id} order cost")
            if cost <= 0:
                raise ValueError(f"trade {trade_id} order cost must be positive")
            trade_original_fee += cost * spec.original_fee_rate
            trade_counterfactual_fee += cost * _counterfactual_rate(order["order_type"], spec)
        trade_gross_pnl = net_pnl + trade_original_fee
        trade_counterfactual_net = trade_gross_pnl - trade_counterfactual_fee
        totals = daily.setdefault(
            close_date,
            {
                "closed_trade_count": 0,
                "gross_pnl": Decimal(0),
                "counterfactual_fee": Decimal(0),
                "counterfactual_net_pnl": Decimal(0),
            },
        )
        totals["closed_trade_count"] = int(totals["closed_trade_count"]) + 1
        totals["gross_pnl"] = Decimal(totals["gross_pnl"]) + trade_gross_pnl
        totals["counterfactual_fee"] = (
            Decimal(totals["counterfactual_fee"]) + trade_counterfactual_fee
        )
        totals["counterfactual_net_pnl"] = (
            Decimal(totals["counterfactual_net_pnl"]) + trade_counterfactual_net
        )
        original_net_pnl += net_pnl
        restored_original_fee += trade_original_fee
        counterfactual_fee += trade_counterfactual_fee

    daily_returns = _calendar_daily_returns(daily, spec.reference_capital)
    gross_pnl = original_net_pnl + restored_original_fee
    counterfactual_net_pnl = gross_pnl - counterfactual_fee
    if sum((row.counterfactual_net_pnl for row in daily_returns), Decimal(0)) != (
        counterfactual_net_pnl
    ):
        raise RuntimeError("daily counterfactual totals do not reconcile")

    return FeeOnlyCounterfactualResult(
        database_sha256=actual_hash,
        closed_trade_count=len(trades),
        filled_order_count=len(orders),
        original_net_pnl=original_net_pnl,
        restored_original_fee=restored_original_fee,
        gross_pnl=gross_pnl,
        counterfactual_fee=counterfactual_fee,
        counterfactual_net_pnl=counterfactual_net_pnl,
        daily_returns=daily_returns,
        spec=spec,
    )


def _require_columns(connection: sqlite3.Connection, table: str, required: set[str]) -> None:
    rows = connection.execute(f"PRAGMA table_info({table})").fetchall()
    columns = {str(row[1]) for row in rows}
    missing = required - columns
    if missing:
        raise ValueError(f"{table} is missing required columns: {', '.join(sorted(missing))}")


def _parse_freqtrade_datetime(value: Any) -> datetime:
    if not isinstance(value, str) or not value:
        raise ValueError("closed trade is missing close_date")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"invalid close_date: {value}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def _required_decimal(value: Any, field_name: str) -> Decimal:
    if value is None:
        raise ValueError(f"{field_name} is required")
    return as_decimal(str(value), field_name=field_name)


def _counterfactual_rate(order_type: Any, spec: FeeOnlyCounterfactualSpec) -> Decimal:
    normalized = str(order_type or "").strip().lower()
    if normalized == "limit":
        return spec.maker_fee_rate
    if normalized in {"market", "stop-market", "stop_market"}:
        return spec.taker_fee_rate
    raise ValueError(f"unsupported filled order type: {order_type!r}")


def _calendar_daily_returns(
    daily: dict[date, dict[str, Decimal | int]], reference_capital: Decimal
) -> tuple[DailyCounterfactualReturn, ...]:
    if not daily:
        raise ValueError("database contains no closed trades")
    current = min(daily)
    last = max(daily)
    rows: list[DailyCounterfactualReturn] = []
    while current <= last:
        values = daily.get(
            current,
            {
                "closed_trade_count": 0,
                "gross_pnl": Decimal(0),
                "counterfactual_fee": Decimal(0),
                "counterfactual_net_pnl": Decimal(0),
            },
        )
        net_pnl = Decimal(values["counterfactual_net_pnl"])
        rows.append(
            DailyCounterfactualReturn(
                day=current,
                closed_trade_count=int(values["closed_trade_count"]),
                gross_pnl=Decimal(values["gross_pnl"]),
                counterfactual_fee=Decimal(values["counterfactual_fee"]),
                counterfactual_net_pnl=net_pnl,
                net_return=net_pnl / reference_capital,
            )
        )
        current += timedelta(days=1)
    return tuple(rows)
