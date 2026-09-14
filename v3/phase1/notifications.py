"""Phase 1 Demo notification helpers.

Notifications are operational evidence only. Delivery failures must not change
order state, retry venue calls, or promote a Demo run.
"""

from __future__ import annotations

import json
import os
import ssl
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from .http import RejectRedirects

TELEGRAM_API_HOST = "api.telegram.org"
TELEGRAM_SEND_TIMEOUT_SECONDS = 5.0
TELEGRAM_MESSAGE_LIMIT = 4096
PHASE1_EVENT_TYPES = frozenset({"start", "stop", "trade", "error"})
SENSITIVE_KEY_PARTS = ("api", "key", "secret", "token", "password", "signature")


@dataclass(frozen=True)
class Phase1Notification:
    event_type: str
    title: str
    summary: str
    observed_at: datetime
    details: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.event_type not in PHASE1_EVENT_TYPES:
            raise ValueError("event_type must be one of error, start, stop, trade")
        if not self.title.strip() or not self.summary.strip():
            raise ValueError("title and summary are required")
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("observed_at must include a timezone")


@dataclass(frozen=True)
class NotificationResult:
    delivered: bool
    error_type: str | None = None


def phase1_notification_from_env(
    notification: Phase1Notification,
    *,
    opener: Callable[..., Any] | None = None,
    timeout: float = TELEGRAM_SEND_TIMEOUT_SECONDS,
) -> NotificationResult:
    """Send a Demo notification using environment credentials only."""

    token = os.environ.get("TELEGRAM_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    return send_phase1_telegram(
        notification,
        token=token,
        chat_id=chat_id,
        opener=opener,
        timeout=timeout,
    )


def format_phase1_notification(notification: Phase1Notification) -> str:
    """Build a compact Telegram body with a prominent Demo marker."""

    observed = notification.observed_at.astimezone(UTC).isoformat()
    lines = [
        f"[DEMO][PHASE1][{notification.event_type.upper()}] {notification.title}",
        notification.summary,
        f"observed_at_utc: {observed}",
    ]
    safe_details = redact_sensitive(notification.details)
    if safe_details:
        lines.append("details:")
        for key in sorted(safe_details):
            lines.append(f"- {key}: {_format_detail_value(safe_details[key])}")
    return "\n".join(lines)


def send_phase1_telegram(
    notification: Phase1Notification,
    *,
    token: str,
    chat_id: str,
    opener: Callable[..., Any] | None = None,
    timeout: float = TELEGRAM_SEND_TIMEOUT_SECONDS,
) -> NotificationResult:
    """Deliver a Phase 1 Demo notification.

    The function returns a failed result instead of raising so callers cannot
    accidentally couple Telegram outages to trade retry logic.
    """

    if not token or not chat_id:
        return NotificationResult(False, "missing_credentials")
    if timeout <= 0 or timeout > 30:
        raise ValueError("timeout must be in the range (0, 30]")
    selected_opener = opener or _telegram_opener
    try:
        for chunk in split_telegram(format_phase1_notification(notification)):
            response = _post_telegram_chunk(
                chunk,
                token=token,
                chat_id=chat_id,
                opener=selected_opener,
                timeout=timeout,
            )
            if not isinstance(response, dict) or response.get("ok") is not True:
                return NotificationResult(False, "telegram_rejected")
    except (OSError, TimeoutError, urllib.error.URLError, json.JSONDecodeError) as exc:
        return NotificationResult(False, type(exc).__name__)
    return NotificationResult(True)


def split_telegram(text: str, limit: int = TELEGRAM_MESSAGE_LIMIT) -> tuple[str, ...]:
    if limit <= 0:
        raise ValueError("limit must be positive")
    chunks: list[str] = []
    remaining = text
    while len(remaining) > limit:
        cut = remaining.rfind("\n", 0, limit + 1)
        if cut < limit // 2:
            cut = limit
        chunks.append(remaining[:cut])
        remaining = remaining[cut:].lstrip("\n")
    if remaining:
        chunks.append(remaining)
    return tuple(chunks)


def redact_sensitive(value: Any, *, key_name: str = "") -> Any:
    if _is_sensitive_key(key_name):
        return "[REDACTED]"
    if isinstance(value, Mapping):
        return {str(key): redact_sensitive(item, key_name=str(key)) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [redact_sensitive(item, key_name=key_name) for item in value]
    return value


def _post_telegram_chunk(
    text: str,
    *,
    token: str,
    chat_id: str,
    opener: Callable[..., Any],
    timeout: float,
) -> Any:
    url = f"https://{TELEGRAM_API_HOST}/bot{token}/sendMessage"
    parts = urllib.parse.urlsplit(url)
    if parts.scheme != "https" or parts.hostname != TELEGRAM_API_HOST:
        raise ValueError("Telegram endpoint must be api.telegram.org over HTTPS")
    body = urllib.parse.urlencode(
        {
            "chat_id": chat_id,
            "text": text,
            "disable_web_page_preview": "true",
        }
    ).encode()
    request = urllib.request.Request(url, data=body, method="POST")
    with opener(request, timeout=timeout) as response:
        return json.loads(response.read().decode())


def _telegram_opener(request, *, timeout: float):
    context = ssl.create_default_context()
    opener = urllib.request.build_opener(
        RejectRedirects(),
        urllib.request.HTTPSHandler(context=context),
    )
    return opener.open(request, timeout=timeout)


def _is_sensitive_key(key_name: str) -> bool:
    folded = key_name.lower()
    return any(part in folded for part in SENSITIVE_KEY_PARTS)


def _format_detail_value(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
