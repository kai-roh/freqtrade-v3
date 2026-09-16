"""V3 operations and research reporting helpers."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from base64 import b64encode
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

TELEGRAM_LIMIT = 4096


class ReportError(RuntimeError):
    """A report could not be collected or delivered safely."""


def split_telegram(text: str, limit: int = TELEGRAM_LIMIT) -> list[str]:
    """Split a message on newlines where possible."""

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
    return chunks


def fetch_json(
    url: str,
    username: str,
    password: str,
    *,
    timeout: float = 10.0,
    opener: Callable[..., Any] = urllib.request.urlopen,
) -> Any:
    """Fetch one authenticated Freqtrade API response."""

    token = b64encode(f"{username}:{password}".encode()).decode()
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "Authorization": f"Basic {token}"},
    )
    try:
        with opener(request, timeout=timeout) as response:
            return json.loads(response.read().decode())
    except (OSError, TimeoutError, urllib.error.URLError, json.JSONDecodeError) as exc:
        endpoint = urllib.parse.urlsplit(url).path.rsplit("/", 1)[-1]
        raise ReportError(f"Freqtrade API request failed for {endpoint}") from exc


def collect_operations(
    api_base: str,
    username: str,
    password: str,
    period: str,
    *,
    opener: Callable[..., Any] = urllib.request.urlopen,
) -> dict[str, Any]:
    """Collect the API payloads required for one report."""

    if period not in {"daily", "weekly"}:
        raise ValueError("period must be daily or weekly")
    timescale = 7 if period == "daily" else 8
    base = api_base.rstrip("/")

    def get(path: str) -> Any:
        return fetch_json(f"{base}/{path}", username, password, opener=opener)

    return {
        "profit": get("profit"),
        "status": get("status"),
        "balance": get("balance"),
        "periods": get(f"{period}?timescale={timescale}"),
    }


def load_research_summary(path: Path) -> dict[str, Any] | None:
    """Return a compact summary from one immutable research result."""

    if not path.is_file():
        return None
    try:
        result = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise ReportError("research result is unreadable") from exc

    ends = [row.get("end") for row in result.get("data", []) if row.get("end")]
    active = [row for row in result.get("portfolios", []) if row.get("candidate") != "no_trade"]
    best = None
    for row in active:
        aggregate = row.get("normal", {}).get("aggregate", {})
        profit_factor = aggregate.get("profit_factor")
        if isinstance(profit_factor, (int, float)) and (
            best is None or profit_factor > best["profit_factor"]
        ):
            best = {
                "candidate": row.get("candidate", "unknown"),
                "side": row.get("side", "unknown"),
                "profit_factor": float(profit_factor),
                "expectancy": float(aggregate.get("expectancy", 0.0)),
            }
    return {
        "decision": result.get("decision", "UNKNOWN"),
        "generated_at": result.get("generated_at", "unknown"),
        "data_end": max(ends) if ends else "unknown",
        "promoted": result.get("promoted_portfolios", []),
        "best": best,
    }


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _period_row(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    rows = payload.get("data")
    if not isinstance(rows, list) or not rows or not isinstance(rows[0], dict):
        return {}
    return rows[0]


def build_report(
    period: str,
    payloads: dict[str, Any],
    *,
    generated_at: datetime,
    research: dict[str, Any] | None = None,
) -> tuple[str, str]:
    """Build the Markdown artifact and short Telegram text."""

    if period not in {"daily", "weekly"}:
        raise ValueError("period must be daily or weekly")
    label = "일간" if period == "daily" else "주간"
    profit = payloads.get("profit") if isinstance(payloads.get("profit"), dict) else {}
    status = payloads.get("status") if isinstance(payloads.get("status"), list) else []
    balance = payloads.get("balance") if isinstance(payloads.get("balance"), dict) else {}
    current = _period_row(payloads.get("periods"))

    period_profit = _number(current.get("abs_profit"))
    period_ratio = _number(current.get("rel_profit"))
    period_trades = int(_number(current.get("trade_count")))
    cumulative_profit = _number(
        profit.get("profit_all_coin", profit.get("profit_closed_coin", 0.0))
    )
    cumulative_ratio = _number(
        profit.get("profit_all_ratio", profit.get("profit_closed_ratio", 0.0))
    )
    closed_trades = int(_number(profit.get("closed_trade_count")))
    profit_factor = _number(profit.get("profit_factor"))
    winrate = _number(profit.get("winrate"))
    total_balance = _number(balance.get("total_bot", balance.get("total", 0.0)))
    stamp = generated_at.isoformat()

    lines = [
        f"# V3 {label} 운영 리포트",
        "",
        f"- generated_at: `{stamp}`",
        "- mode: `DRY-RUN`",
        "- strategy: `V3ShadowStrategy`",
        f"- period trades: `{period_trades}`",
        f"- period PnL: `{period_profit:+.4f} USDT` (`{period_ratio:+.2%}`)",
        f"- cumulative closed trades: `{closed_trades}`",
        f"- cumulative PnL: `{cumulative_profit:+.4f} USDT` (`{cumulative_ratio:+.2%}`)",
        f"- profit factor: `{profit_factor:.3f}`",
        f"- win rate: `{winrate:.2%}`",
        f"- open trades: `{len(status)}`",
        f"- bot balance: `{total_balance:.4f} USDT`",
    ]
    short = [
        f"V3 {label} 리포트 | DRY-RUN",
        f"기간 거래 {period_trades}건 / 손익 {period_profit:+.4f} USDT ({period_ratio:+.2%})",
        f"누적 {closed_trades}건 / {cumulative_profit:+.4f} USDT / PF {profit_factor:.3f}",
        f"오픈 {len(status)}건 / 잔고 {total_balance:.4f} USDT",
    ]
    if research:
        best = research.get("best")
        lines.extend(
            [
                "",
                "## Research gate",
                "",
                f"- decision: `{research.get('decision', 'UNKNOWN')}`",
                f"- generated_at: `{research.get('generated_at', 'unknown')}`",
                f"- data_end: `{research.get('data_end', 'unknown')}`",
                f"- promoted portfolios: `{len(research.get('promoted', []))}`",
            ]
        )
        short.append(
            f"연구 판정 {research.get('decision', 'UNKNOWN')} / 승격 {len(research.get('promoted', []))}개"
        )
        if best:
            lines.append(
                "- best active candidate: "
                f"`{best['candidate']} {best['side']}` "
                f"(PF `{best['profit_factor']:.3f}`, EV `{best['expectancy']:.6f}`)"
            )
            short.append(
                f"최고 후보 {best['candidate']} {best['side']} / PF {best['profit_factor']:.3f}"
            )
    lines.extend(
        [
            "",
            "> This report does not authorize strategy promotion or live trading.",
            "",
        ]
    )
    return "\n".join(lines), "\n".join(short)


def atomic_write(path: Path, content: str) -> None:
    """Write a report without exposing a partially written artifact."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        temporary.write_text(content)
        temporary.chmod(0o600)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def send_telegram(
    text: str,
    token: str,
    chat_id: str,
    *,
    timeout: float = 10.0,
    opener: Callable[..., Any] = urllib.request.urlopen,
) -> None:
    """Deliver all chunks and raise a redacted error on any failure."""

    if not token or not chat_id:
        raise ReportError("Telegram credentials are not configured")
    for chunk in split_telegram(text):
        data = urllib.parse.urlencode(
            {
                "chat_id": chat_id,
                "text": chunk,
                "disable_notification": "true",
            }
        ).encode()
        request = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=data,
            method="POST",
        )
        try:
            with opener(request, timeout=timeout) as response:
                body = json.loads(response.read().decode())
        except (OSError, TimeoutError, urllib.error.URLError, json.JSONDecodeError) as exc:
            raise ReportError(f"Telegram delivery failed ({type(exc).__name__})") from exc
        if not isinstance(body, dict) or body.get("ok") is not True:
            raise ReportError("Telegram delivery was rejected")
