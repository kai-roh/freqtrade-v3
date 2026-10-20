import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from v3.reporting import (
    ReportError,
    atomic_write,
    build_report,
    load_research_summary,
    send_telegram,
    split_telegram,
)

ROOT = Path(__file__).resolve().parents[1]


class FakeResponse:
    def __init__(self, body: dict):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def read(self) -> bytes:
        return json.dumps(self.body).encode()


def test_reporting_import_does_not_require_numeric_site_packages() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-S",
            "-c",
            "from v3.reporting import split_telegram; assert split_telegram('ok') == ['ok']",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr


def _payloads(period_profit: float = 1.25) -> dict:
    return {
        "profit": {
            "profit_all_coin": 3.5,
            "profit_all_ratio": 0.035,
            "closed_trade_count": 4,
            "profit_factor": 1.25,
            "winrate": 0.5,
        },
        "status": [{"pair": "BTC/USDT:USDT"}],
        "balance": {"total_bot": 1003.5},
        "periods": {
            "data": [
                {
                    "date": "2026-08-10",
                    "abs_profit": period_profit,
                    "rel_profit": 0.0125,
                    "trade_count": 2,
                }
            ]
        },
    }


@pytest.mark.parametrize(("period", "label"), [("daily", "일간"), ("weekly", "주간")])
def test_build_report_covers_operations_and_research(period: str, label: str) -> None:
    research = {
        "decision": "STOP_BEFORE_CLASSIFIER",
        "generated_at": "2026-08-10T00:00:00Z",
        "data_end": "2026-08-10T00:00:00+00:00",
        "promoted": [],
        "best": {
            "candidate": "trend_pullback",
            "side": "long",
            "profit_factor": 0.65,
            "expectancy": -0.001,
        },
    }
    markdown, telegram = build_report(
        period,
        _payloads(),
        generated_at=datetime(2026, 8, 10, 23, 0, tzinfo=ZoneInfo("Asia/Seoul")),
        research=research,
    )

    assert f"V3 {label}" in markdown
    assert "DRY-RUN" in markdown
    assert "period trades: `2`" in markdown
    assert "STOP_BEFORE_CLASSIFIER" in markdown
    assert "승격 0개" in telegram
    assert "PF 0.650" in telegram


def test_load_research_summary_finds_best_active_candidate(tmp_path: Path) -> None:
    path = tmp_path / "results.json"
    path.write_text(
        json.dumps(
            {
                "decision": "STOP_BEFORE_CLASSIFIER",
                "generated_at": "2026-08-10T00:00:00Z",
                "data": [{"end": "2026-08-09"}, {"end": "2026-08-10"}],
                "promoted_portfolios": [],
                "portfolios": [
                    {"candidate": "no_trade", "normal": {"aggregate": {"profit_factor": 0}}},
                    {
                        "candidate": "trend_pullback",
                        "side": "short",
                        "normal": {"aggregate": {"profit_factor": 0.7, "expectancy": -0.002}},
                    },
                ],
            }
        )
    )

    summary = load_research_summary(path)

    assert summary is not None
    assert summary["data_end"] == "2026-08-10"
    assert summary["best"]["candidate"] == "trend_pullback"


def test_split_telegram_prefers_newlines_and_respects_limit() -> None:
    chunks = split_telegram("first line\n" + "x" * 20, limit=15)

    assert "".join(chunks).replace("\n", "") == "first line" + "x" * 20
    assert all(len(chunk) <= 15 for chunk in chunks)


def test_send_telegram_requires_credentials_and_redacts_failures() -> None:
    with pytest.raises(ReportError, match="not configured"):
        send_telegram("message", "", "")

    secret = "very-secret-token"

    def failing_opener(*args, **kwargs):
        raise OSError(f"https://api.telegram.org/bot{secret}/sendMessage")

    with pytest.raises(ReportError) as error:
        send_telegram("message", secret, "123", opener=failing_opener)
    assert secret not in str(error.value)


def test_send_telegram_accepts_success_and_atomic_write_is_private(tmp_path: Path) -> None:
    requests = []

    def successful_opener(request, **kwargs):
        requests.append(request)
        return FakeResponse({"ok": True})

    send_telegram("message", "token", "chat", opener=successful_opener)
    assert len(requests) == 1

    path = tmp_path / "daily" / "report.md"
    atomic_write(path, "complete")
    assert path.read_text() == "complete"
    assert path.stat().st_mode & 0o777 == 0o600


def test_cli_defaults_to_host_owned_report_directory() -> None:
    script = (ROOT / "scripts/send_operations_report.py").read_text()

    assert 'default=Path("reports")' in script
    assert 'default=Path("user_data/reports")' not in script
