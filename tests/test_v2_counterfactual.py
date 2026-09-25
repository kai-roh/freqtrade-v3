import hashlib
import sqlite3
from decimal import Decimal

import pytest

from v3.v2_counterfactual import (
    FeeOnlyCounterfactualSpec,
    build_fee_only_counterfactual,
)


def _database(tmp_path):
    path = tmp_path / "trades.sqlite"
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE trades (
            id INTEGER PRIMARY KEY,
            is_open BOOLEAN NOT NULL,
            close_date TEXT,
            close_profit_abs FLOAT
        );
        CREATE TABLE orders (
            id INTEGER PRIMARY KEY,
            ft_trade_id INTEGER NOT NULL,
            order_type TEXT,
            cost FLOAT,
            filled FLOAT,
            status TEXT
        );
        """
    )
    connection.executemany(
        "INSERT INTO trades VALUES (?, ?, ?, ?)",
        [
            (1, 0, "2026-01-01 23:30:00", -1.0),
            (2, 0, "2026-01-03 00:30:00+00:00", 2.0),
        ],
    )
    connection.executemany(
        "INSERT INTO orders VALUES (?, ?, ?, ?, ?, ?)",
        [
            (1, 1, "limit", 100.0, 1.0, "closed"),
            (2, 1, "market", 100.0, 1.0, "closed"),
            (3, 2, "limit", 200.0, 2.0, "closed"),
            (4, 2, "stop-market", 200.0, 2.0, "closed"),
        ],
    )
    connection.commit()
    connection.close()
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return path, digest


def _spec():
    return FeeOnlyCounterfactualSpec(
        original_fee_rate="0.00067",
        maker_fee_rate="0.00015",
        taker_fee_rate="0.00045",
        reference_capital="1000",
    )


def test_fee_only_counterfactual_reconciles_fee_scenario(tmp_path):
    path, digest = _database(tmp_path)
    result = build_fee_only_counterfactual(
        path,
        expected_database_sha256=digest,
        expected_closed_trade_count=2,
        spec=_spec(),
    )

    assert result.original_net_pnl == Decimal("1.0")
    assert result.restored_original_fee == Decimal("0.402000")
    assert result.gross_pnl == Decimal("1.402000")
    assert result.counterfactual_fee == Decimal("0.180000")
    assert result.counterfactual_net_pnl == Decimal("1.222000")
    assert len(result.daily_returns) == 2
    assert [row.closed_trade_count for row in result.daily_returns] == [1, 1]
    assert sum((row.net_return for row in result.daily_returns), Decimal(0)) == Decimal("0.001222")


def test_fee_only_counterfactual_includes_calendar_gaps(tmp_path):
    path, digest = _database(tmp_path)
    connection = sqlite3.connect(path)
    connection.execute("UPDATE trades SET close_date = '2026-01-04 00:30:00+00:00' WHERE id = 2")
    connection.commit()
    connection.close()
    digest = hashlib.sha256(path.read_bytes()).hexdigest()

    result = build_fee_only_counterfactual(
        path,
        expected_database_sha256=digest,
        expected_closed_trade_count=2,
        spec=_spec(),
    )

    assert len(result.daily_returns) == 3
    assert result.daily_returns[1].closed_trade_count == 0
    assert result.daily_returns[1].net_return == 0


def test_fee_only_counterfactual_rejects_wrong_hash_count_and_unknown_order(tmp_path):
    path, digest = _database(tmp_path)

    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        build_fee_only_counterfactual(
            path,
            expected_database_sha256="0" * 64,
            expected_closed_trade_count=2,
            spec=_spec(),
        )
    with pytest.raises(ValueError, match="count mismatch"):
        build_fee_only_counterfactual(
            path,
            expected_database_sha256=digest,
            expected_closed_trade_count=194,
            spec=_spec(),
        )

    connection = sqlite3.connect(path)
    connection.execute("UPDATE orders SET order_type = 'trailing-stop' WHERE id = 2")
    connection.commit()
    connection.close()
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="unsupported filled order type"):
        build_fee_only_counterfactual(
            path,
            expected_database_sha256=digest,
            expected_closed_trade_count=2,
            spec=_spec(),
        )


def test_fee_only_counterfactual_rejects_uncheckpointed_wal(tmp_path):
    path, digest = _database(tmp_path)
    (tmp_path / "trades.sqlite-wal").write_bytes(b"uncheckpointed")

    with pytest.raises(ValueError, match="non-empty WAL"):
        build_fee_only_counterfactual(
            path,
            expected_database_sha256=digest,
            expected_closed_trade_count=2,
            spec=_spec(),
        )


def test_fee_only_counterfactual_rejects_orders_outside_closed_trade_universe(tmp_path):
    path, _ = _database(tmp_path)
    connection = sqlite3.connect(path)
    connection.execute(
        "INSERT INTO orders VALUES (?, ?, ?, ?, ?, ?)",
        (5, 999, "limit", 10.0, 1.0, "closed"),
    )
    connection.commit()
    connection.close()
    digest = hashlib.sha256(path.read_bytes()).hexdigest()

    with pytest.raises(ValueError, match="outside the closed-trade universe"):
        build_fee_only_counterfactual(
            path,
            expected_database_sha256=digest,
            expected_closed_trade_count=2,
            spec=_spec(),
        )
