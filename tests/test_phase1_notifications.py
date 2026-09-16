import json
import urllib.parse
from datetime import UTC, datetime

import pytest

from v3.phase1.notifications import (
    Phase1Notification,
    format_phase1_notification,
    phase1_notification_from_env,
    redact_sensitive,
    send_phase1_telegram,
    split_telegram,
)


class FakeResponse:
    def __init__(self, body: dict):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def read(self) -> bytes:
        return json.dumps(self.body).encode()


def notification(**overrides) -> Phase1Notification:
    values = {
        "event_type": "trade",
        "title": "two-leg episode accepted",
        "summary": "spot/perp Demo commands reached local enqueue",
        "observed_at": datetime(2026, 9, 14, 1, 2, 3, tzinfo=UTC),
        "details": {"intent_id": "intent-1", "api_key": "secret", "nested": {"token": "t"}},
    }
    values.update(overrides)
    return Phase1Notification(**values)


def test_phase1_notification_requires_demo_operational_event() -> None:
    with pytest.raises(ValueError, match="event_type"):
        notification(event_type="profit")
    with pytest.raises(ValueError, match="timezone"):
        notification(observed_at=datetime(2026, 9, 14, 1, 2, 3))


def test_formatter_prominently_marks_demo_and_redacts_sensitive_details() -> None:
    message = format_phase1_notification(notification())

    assert message.startswith("[DEMO][PHASE1][TRADE]")
    assert "api_key: [REDACTED]" in message
    assert "token" in message
    assert "secret" not in message
    assert '"t"' not in message


def test_redact_sensitive_recurses_without_mutating_non_secret_values() -> None:
    redacted = redact_sensitive(
        {
            "intent_id": "intent-1",
            "client_secret": "hidden",
            "items": [{"password": "hidden"}, {"venue": "BINANCE_DEMO"}],
        }
    )

    assert redacted == {
        "intent_id": "intent-1",
        "client_secret": "[REDACTED]",
        "items": [{"password": "[REDACTED]"}, {"venue": "BINANCE_DEMO"}],
    }


def test_send_phase1_telegram_uses_exact_api_host_and_bounded_timeout() -> None:
    requests = []

    def opener(request, **kwargs):
        requests.append((request, kwargs))
        return FakeResponse({"ok": True})

    result = send_phase1_telegram(
        notification(event_type="start", title="week run started"),
        token="demo-token",
        chat_id="123",
        opener=opener,
        timeout=3.0,
    )

    assert result.delivered
    assert result.error_type is None
    assert len(requests) == 1
    request, kwargs = requests[0]
    parts = urllib.parse.urlsplit(request.full_url)
    assert parts.scheme == "https"
    assert parts.hostname == "api.telegram.org"
    assert request.get_method() == "POST"
    assert kwargs["timeout"] == 3.0
    body = urllib.parse.parse_qs(request.data.decode())
    assert body["chat_id"] == ["123"]
    assert body["disable_web_page_preview"] == ["true"]
    assert "[DEMO][PHASE1][START]" in body["text"][0]


def test_send_phase1_telegram_returns_false_for_missing_or_failed_delivery() -> None:
    assert not send_phase1_telegram(notification(), token="", chat_id="123").delivered

    def failing_opener(*args, **kwargs):
        raise OSError("contains-demo-token")

    result = send_phase1_telegram(
        notification(event_type="error", title="runner stopped"),
        token="demo-token",
        chat_id="123",
        opener=failing_opener,
    )

    assert not result.delivered
    assert result.error_type == "OSError"
    assert "demo-token" not in str(result)


def test_phase1_notification_from_env_reads_credentials_without_printing(monkeypatch) -> None:
    calls = []

    def opener(request, **kwargs):
        calls.append(request)
        return FakeResponse({"ok": True})

    monkeypatch.setenv("TELEGRAM_TOKEN", "env-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "456")

    result = phase1_notification_from_env(notification(event_type="stop"), opener=opener)

    assert result.delivered
    assert "env-token" in calls[0].full_url


def test_split_telegram_returns_chunks_inside_limit() -> None:
    chunks = split_telegram("line1\n" + "x" * 20, limit=10)

    assert all(len(chunk) <= 10 for chunk in chunks)
    assert "".join(chunks).replace("\n", "") == "line1" + "x" * 20
