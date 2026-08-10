import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import freeze_v2_evidence as freeze  # noqa: E402


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, sort_keys=True))


def make_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "v2"
    (repo / "user_data/strategies").mkdir(parents=True)
    (repo / "user_data/freqaimodels").mkdir(parents=True)
    (repo / "user_data/llm").mkdir(parents=True)
    (repo / "user_data/models/kai_v1").mkdir(parents=True)
    (repo / "scripts").mkdir()
    (repo / "docs").mkdir()
    (repo / "docker-compose.yml").write_text("services:\n  freqtrade: {}\n")
    (repo / "scripts/run_backtest.sh").write_text("#!/bin/sh\ntrue\n")
    (repo / "user_data/strategies/KaiBaseStrategy.py").write_text("class KaiBaseStrategy: pass\n")
    (repo / "user_data/freqaimodels/LLMEnhancedModel.py").write_text(
        "class LLMEnhancedModel: pass\n"
    )
    (repo / "user_data/llm/claude_client.py").write_text("class ClaudeClient: pass\n")
    (repo / "user_data/models/kai_v1/historic_predictions.pkl").write_bytes(b"not copied")

    write_json(
        repo / "user_data/config.json",
        {
            "max_open_trades": 2,
            "stake_currency": "USDT",
            "exchange": {
                "name": "binance",
                "key": "do-not-leak",
                "secret": "do-not-leak",
                "pair_whitelist": ["BTC/USDT:USDT"],
            },
            "telegram": {
                "enabled": True,
                "token": "do-not-leak",
                "chat_id": "do-not-leak",
                "notification_settings": {"status": "on"},
            },
            "api_server": {
                "enabled": True,
                "jwt_secret_key": "do-not-leak",
                "username": "do-not-leak",
                "password": "do-not-leak",
                "listen_port": 8080,
            },
            "freqai": {"enabled": True, "identifier": "kai_v1"},
        },
    )
    write_json(
        repo / "user_data/evaluation_phase.json",
        {
            "phase": "fixture_phase",
            "baseline": {"closed_trades": 1, "cumulative_pnl_usdt": 2.5},
        },
    )

    db_path = repo / "user_data/tradesv3.sqlite"
    con = sqlite3.connect(db_path)
    con.execute(
        """
        CREATE TABLE trades (
            id INTEGER PRIMARY KEY,
            pair TEXT,
            is_open BOOLEAN,
            open_date TEXT,
            close_date TEXT,
            close_profit_abs FLOAT,
            realized_profit FLOAT,
            close_profit FLOAT,
            strategy TEXT
        )
        """
    )
    con.executemany(
        """
        INSERT INTO trades
          (pair, is_open, open_date, close_date, close_profit_abs, realized_profit, close_profit, strategy)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            ("BTC/USDT:USDT", 0, "2026-01-01", "2026-01-02", 1.25, 1.25, 0.01, "Kai"),
            ("ETH/USDT:USDT", 1, "2026-01-03", None, -0.5, -0.5, -0.02, "Kai"),
        ],
    )
    con.commit()
    con.close()
    return repo


def test_filter_config_excludes_secret_keys() -> None:
    safe = freeze.filter_config(
        {
            "exchange": {"name": "binance", "key": "secret", "secret": "secret"},
            "telegram": {"enabled": True, "token": "secret", "chat_id": "secret"},
            "api_server": {"enabled": True, "password": "secret", "jwt_secret_key": "secret"},
        },
        freeze.SAFE_CONFIG_SPEC,
    )

    freeze.assert_no_secret_keys(safe)
    serialized = json.dumps(safe)
    assert "secret" not in serialized
    assert "token" not in serialized
    assert "password" not in serialized
    assert safe["exchange"] == {"name": "binance"}


def test_build_evidence_from_local_fixture_without_remote(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)

    evidence = freeze.build_evidence(
        source_repo=repo,
        generated_at="2026-08-10T00:00:00Z",
        evidence_cutoff="2026-08-10T00:00:00Z",
    )

    assert evidence["generated_at"] == "2026-08-10T00:00:00Z"
    assert evidence["remote"] is None
    assert evidence["local"]["config"]["safe_fields"]["exchange"]["name"] == "binance"
    assert "key" not in evidence["local"]["config"]["safe_fields"]["exchange"]
    assert evidence["local"]["trade_metrics"]["metrics"]["summary"]["trade_count"] == 2
    assert evidence["local"]["trade_metrics"]["metrics"]["summary"]["open_trade_count"] == 1
    assert evidence["local"]["trade_metrics"]["metrics"]["summary"]["close_profit_abs_sum"] == 0.75
    assert evidence["local"]["evaluation_phase"]["metrics"]["phase"] == "fixture_phase"
    assert evidence["local"]["historic_prediction_artifacts"][0]["path"].endswith(
        "historic_predictions.pkl"
    )
    assert not any(
        item["path"].endswith(".sqlite") for item in evidence["local"]["selected_file_hashes"]
    )


def test_write_outputs_are_dated_and_machine_readable(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    evidence = freeze.build_evidence(
        source_repo=repo,
        generated_at="2026-08-10T12:34:56Z",
        evidence_cutoff="2026-08-10T12:34:56Z",
    )
    evidence["remote"] = {
        "git": {"branch": "main", "sha": "abc", "is_dirty": True},
        "trade_metrics": {
            "sha256": "remote-db-sha",
            "summary": {
                "trade_count": 194,
                "open_trade_count": 0,
                "close_profit_abs_sum": -183.83960848,
                "first_close_date": "2026-05-14 23:08:36.052000",
                "last_close_date": "2026-08-09 09:25:26.046000",
            },
        },
    }

    json_path, md_path = freeze.write_outputs(evidence, tmp_path / "evidence/v2-baseline")

    assert json_path.name == "v2-baseline-2026-08-10.json"
    assert md_path.name == "v2-baseline-2026-08-10.md"
    assert json.loads(json_path.read_text())["schema_version"] == 1
    markdown = md_path.read_text()
    assert "# V2 Baseline Evidence" in markdown
    assert "## Trade Metrics" in markdown
    assert "- local_trade_count: `2` open=`1`" in markdown
    assert "- remote_trade_count: `194` open=`0`" in markdown
    assert "- remote_close_profit_abs_sum: `-183.83960848`" in markdown
    assert "- remote_first_close_date: `2026-05-14 23:08:36.052000`" in markdown
    assert "- remote_last_close_date: `2026-08-09 09:25:26.046000`" in markdown
    assert "- remote_db_sha256: `remote-db-sha`" in markdown
    assert (
        "Databases, model binaries, logs, and sensitive config values are not copied." in markdown
    )


def test_remote_parsers_are_deterministic() -> None:
    git = freeze.parse_remote_git("branch=main\nsha=abc\n M README.md\n?? scratch\n")
    runtime = freeze.parse_remote_runtime(
        '{"ID":"1","Image":"img","Names":"freqtrade","Status":"Up","Ports":"8080"}\n'
        "\n--compose-ps--\nNAME IMAGE\nfreqtrade img\n"
        "\n--checksums--\nabc  docker-compose.yml\ndef  user_data/config.json\n"
    )

    assert git == {
        "branch": "main",
        "sha": "abc",
        "status_short": [" M README.md", "?? scratch"],
        "is_dirty": True,
    }
    assert runtime["docker_ps"][0]["names"] == "freqtrade"
    assert runtime["checksums"] == [
        {"path": "docker-compose.yml", "sha256": "abc"},
        {"path": "user_data/config.json", "sha256": "def"},
    ]
