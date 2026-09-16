"""Read-only Telegram command bot for the Phase 1 Demo run.

Answers /status, /profit, /balance, /daily, and /help for the single configured
chat. It reads the PostgreSQL ledger through a read-only transaction setting,
the runner's evidence directory, and Demo account GET endpoints. It has no order
transport, never edits policy, and ignores every other chat.
"""

from __future__ import annotations

import json
import ssl
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from .http import RejectRedirects
from .notifications import TELEGRAM_API_HOST, split_telegram

KST = timezone(timedelta(hours=9), "KST")
COMMANDS: tuple[tuple[str, str], ...] = (
    ("status", "실행기·에피소드·원장 상태"),
    ("profit", "에피소드별 Demo 실현 손익"),
    ("balance", "Demo 지갑·포지션 잔고"),
    ("daily", "오늘(KST) 요약"),
    ("help", "명령 목록"),
)
TERMINAL_STATES = {"CLOSED"}


def _kst(value: datetime | str | None) -> str:
    if value is None:
        return "-"
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(KST).strftime("%m-%d %H:%M:%S")


def _q(value: Decimal | str | None, places: str = "0.01") -> str:
    if value is None:
        return "-"
    return str(Decimal(str(value)).quantize(Decimal(places)))


def parse_command(text: str | None) -> str | None:
    """Return the bare command name for '/cmd', '/cmd@bot', or '/cmd args'."""
    if not text or not text.startswith("/"):
        return None
    head = text.split()[0][1:]
    return head.split("@", 1)[0].lower() or None


@dataclass(frozen=True)
class LedgerFacts:
    intents: list[tuple[str, str, datetime]]
    fills: list[dict[str, Any]]
    residuals: dict[str, Decimal]
    unresolved_recovery: int
    inbox_not_applied: int
    active_commands: int
    open_incidents: int


def load_ledger_facts(connection) -> LedgerFacts:
    with connection.transaction():
        intents = [
            (str(r[0]), r[1], r[2])
            for r in connection.execute(
                "SELECT id,state,created_at FROM intents "
                "WHERE strategy_id='phase1_demo_engineering' ORDER BY created_at"
            ).fetchall()
        ]
        fills = [
            {
                "intent_id": str(r[0]),
                "leg": r[1],
                "side": r[2],
                "quantity": r[3],
                "price": r[4],
                "fee_amount": r[5],
                "fee_token": r[6],
                "filled_at": r[7],
            }
            for r in connection.execute(
                "SELECT c.intent_id,c.leg,c.side,f.quantity,f.price,f.fee_amount,f.fee_token,"
                "f.filled_at FROM fills f JOIN orders o ON o.id=f.order_id "
                "JOIN order_commands c ON c.id=o.command_id ORDER BY f.filled_at"
            ).fetchall()
        ]
        residuals = {
            str(r[0]): r[1]
            for r in connection.execute(
                "SELECT intent_id,residual_base FROM episode_residuals"
            ).fetchall()
        }

        def count(sql: str) -> int:
            return int(connection.execute(sql).fetchone()[0])

        return LedgerFacts(
            intents,
            fills,
            residuals,
            count(
                "SELECT count(*) FROM order_recovery_checks WHERE status IN ('PENDING','BLOCKED')"
            ),
            count("SELECT count(*) FROM fill_event_inbox WHERE status<>'APPLIED'"),
            count("SELECT count(*) FROM order_commands WHERE active"),
            count("SELECT count(*) FROM incidents WHERE status<>'resolved'"),
        )


def episode_pnl(fills: list[dict[str, Any]]) -> dict[str, dict[str, Decimal]]:
    """Realized USDT cash flow per episode from fills; BTC fees and dust stay in BTC."""
    result: dict[str, dict[str, Decimal]] = {}
    for fill in fills:
        row = result.setdefault(
            fill["intent_id"],
            {"usdt": Decimal(0), "fees_usdt": Decimal(0), "fees_btc": Decimal(0)},
        )
        notional = Decimal(fill["quantity"]) * Decimal(fill["price"])
        row["usdt"] += notional if fill["side"] == "sell" else -notional
        if fill["fee_token"] == "USDT":
            row["fees_usdt"] += Decimal(fill["fee_amount"])
        elif fill["fee_token"] == "BTC":
            row["fees_btc"] += Decimal(fill["fee_amount"])
    for row in result.values():
        row["net_usdt"] = row["usdt"] - row["fees_usdt"]
    return result


def load_run_evidence(evidence_dir: Path) -> dict[str, Any]:
    info: dict[str, Any] = {"started_at": None, "events": [], "bounds": None}
    started = evidence_dir / "started-at.txt"
    if started.is_file():
        info["started_at"] = started.read_text().strip()
    latest: dict[str, Any] | None = None
    for path in sorted(evidence_dir.glob("run*.json")):
        try:
            data = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if latest is None or path.stat().st_mtime >= latest["_mtime"]:
            latest = {"_mtime": path.stat().st_mtime, **data}
    if latest:
        info["events"] = latest.get("events", [])
        info["bounds"] = latest.get("run_bounds")
    return info


def status_text(facts: LedgerFacts, run: Mapping[str, Any], now: datetime) -> str:
    closed = [i for i in facts.intents if i[1] in TERMINAL_STATES]
    open_ = [i for i in facts.intents if i[1] not in TERMINAL_STATES]
    bounds = run.get("bounds") or {}
    events = run.get("events") or []
    last = events[-1] if events else None
    lines = ["[DEMO] 상태"]
    lines.append(f"실행 시작: {_kst(run.get('started_at'))} KST")
    if bounds:
        lines.append(
            f"에피소드: {len(closed)} 종료 / 최대 {bounds.get('maximum_episodes')} · "
            f"간격 {int(bounds.get('episode_interval_seconds', 0)) // 60}분"
        )
    else:
        lines.append(f"에피소드 종료: {len(closed)}")
    if open_:
        lines.append(f"진행 중: {open_[0][1]} (시작 {_kst(open_[0][2])})")
    else:
        lines.append("진행 중: 없음 (다음 에피소드 대기)")
    if last:
        age = int((now - datetime.fromisoformat(last["at"])).total_seconds())
        lines.append(f"마지막 이벤트: {last['kind']} {_kst(last['at'])} ({age // 60}분 전)")
        if last["kind"] == "stop" and last.get("status") == "STOPPED":
            lines.append(f"⏹ 실행기 종료: {last.get('reason')}")
        elif last["kind"] == "error":
            lines.append(f"❌ 마지막 오류: {last.get('error_type')}")
    integrity = (
        facts.unresolved_recovery,
        facts.inbox_not_applied,
        facts.active_commands,
        facts.open_incidents,
    )
    lines.append(
        "원장: 정상"
        if integrity == (0, 0, 0, 0)
        else f"원장 주의: 복구 {integrity[0]} · inbox {integrity[1]} · 활성명령 {integrity[2]} · incident {integrity[3]}"
    )
    return "\n".join(lines)


def profit_text(facts: LedgerFacts, limit: int = 10) -> str:
    pnl = episode_pnl(facts.fills)
    lines = ["[DEMO] 에피소드별 실현 손익 (수익성 검증 아님)"]
    total = Decimal(0)
    total_btc_dust = Decimal(0)
    for index, (intent_id, state, created_at) in enumerate(facts.intents, start=1):
        row = pnl.get(intent_id)
        if row is None:
            continue
        total += row["net_usdt"]
        dust = facts.residuals.get(intent_id, Decimal(0))
        total_btc_dust += dust
        if index > len(facts.intents) - limit:
            sign = "+" if row["net_usdt"] >= 0 else ""
            lines.append(
                f"#{index} {_kst(created_at)[:11]} {state} {sign}{_q(row['net_usdt'])} USDT"
                + (f" · 잔량 {dust} BTC" if dust else "")
            )
    sign = "+" if total >= 0 else ""
    lines.append(f"합계 {sign}{_q(total)} USDT · 정산 잔량 {total_btc_dust} BTC (계정 보유)")
    lines.append("※ 수수료 포함 USDT 현금흐름, 잔량 BTC는 미평가")
    return "\n".join(lines)


def daily_text(facts: LedgerFacts, run: Mapping[str, Any], now: datetime) -> str:
    day = now.astimezone(KST).date()

    def on_day(value: datetime | str) -> bool:
        if isinstance(value, str):
            value = datetime.fromisoformat(value)
        return value.astimezone(KST).date() == day

    pnl = episode_pnl(facts.fills)
    today_intents = [i for i in facts.intents if on_day(i[2])]
    closed_today = [i for i in today_intents if i[1] in TERMINAL_STATES]
    fills_today = [f for f in facts.fills if on_day(f["filled_at"])]
    pnl_today = sum((pnl[i[0]]["net_usdt"] for i in today_intents if i[0] in pnl), Decimal(0))
    dust_today = sum((facts.residuals.get(i[0], Decimal(0)) for i in today_intents), Decimal(0))
    events = [e for e in (run.get("events") or []) if on_day(e["at"])]
    errors = [e for e in events if e["kind"] == "error"]
    undelivered = [e for e in events if e.get("telegram_delivered") is False]
    sign = "+" if pnl_today >= 0 else ""
    lines = [
        f"[DEMO] {day.isoformat()} 일일 요약 (KST)",
        f"에피소드: 시작 {len(today_intents)} · 종료 {len(closed_today)}",
        f"체결: {len(fills_today)}건",
        f"실현 손익: {sign}{_q(pnl_today)} USDT · 정산 잔량 {dust_today} BTC",
        f"오류 {len(errors)}건 · 알림 미전달 {len(undelivered)}건",
    ]
    return "\n".join(lines)


def balance_text(account: Mapping[str, Any]) -> str:
    perp = Decimal(str(account["perp_qty"]))
    return "\n".join(
        [
            "[DEMO] 잔고",
            f"현물 USDT: {_q(account['spot_usdt'])}",
            f"현물 BTC: {account['spot_total_btc']}",
            f"선물 가용 USDT: {_q(account['perp_usdt'])}",
            f"선물 포지션: {perp} BTC" + (" (flat)" if perp == 0 else ""),
            f"레버리지 {account['leverage']}x {account['margin_type']} · 미체결 {len(account['open_orders'])}",
        ]
    )


def help_text() -> str:
    return "\n".join(["[DEMO] 명령"] + [f"/{name} — {desc}" for name, desc in COMMANDS])


class TelegramApi:
    def __init__(self, token: str, *, opener: Callable[..., Any] | None = None, timeout=35.0):
        if not token:
            raise ValueError("TELEGRAM_TOKEN is required")
        self.token = token
        self.opener = opener or _opener
        self.timeout = timeout

    def call(self, method: str, **params: Any) -> Any:
        url = f"https://{TELEGRAM_API_HOST}/bot{self.token}/{method}"
        body = urllib.parse.urlencode(
            {k: (json.dumps(v) if isinstance(v, list | dict) else v) for k, v in params.items()}
        ).encode()
        request = urllib.request.Request(url, data=body, method="POST")
        with self.opener(request, timeout=self.timeout) as response:
            data = json.loads(response.read().decode())
        if not isinstance(data, dict) or data.get("ok") is not True:
            raise ValueError(f"telegram {method} rejected")
        return data["result"]

    def register_commands(self) -> None:
        self.call(
            "setMyCommands",
            commands=[{"command": name, "description": desc} for name, desc in COMMANDS],
        )

    def send(self, chat_id: str, text: str) -> None:
        for chunk in split_telegram(text):
            self.call("sendMessage", chat_id=chat_id, text=chunk, disable_web_page_preview="true")

    def updates(self, offset: int | None, timeout_seconds: int = 25) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"timeout": timeout_seconds, "allowed_updates": ["message"]}
        if offset is not None:
            params["offset"] = offset
        return self.call("getUpdates", **params)


def _opener(request, *, timeout: float):
    context = ssl.create_default_context()
    return urllib.request.build_opener(
        RejectRedirects(), urllib.request.HTTPSHandler(context=context)
    ).open(request, timeout=timeout)


def answer(
    command: str,
    *,
    facts_loader: Callable[[], LedgerFacts],
    run_loader: Callable[[], Mapping[str, Any]],
    account_loader: Callable[[], Mapping[str, Any]],
    now: datetime | None = None,
) -> str | None:
    now = now or datetime.now(UTC)
    if command in {"help", "start"}:
        return help_text()
    if command == "status":
        return status_text(facts_loader(), run_loader(), now)
    if command == "profit":
        return profit_text(facts_loader())
    if command == "daily":
        return daily_text(facts_loader(), run_loader(), now)
    if command == "balance":
        return balance_text(account_loader())
    return None


def handle_update(update: Mapping[str, Any], *, chat_id: str, **loaders) -> tuple[str, str] | None:
    """Return (chat_id, reply) for an authorized command, else None."""
    message = update.get("message") or {}
    chat = message.get("chat") or {}
    if str(chat.get("id")) != str(chat_id):
        return None
    command = parse_command(message.get("text"))
    if command is None:
        return None
    try:
        reply = answer(command, **loaders)
    except Exception as exc:  # noqa: BLE001 - the bot must keep serving read-only replies.
        reply = f"[DEMO] 조회 실패: {type(exc).__name__}"
    if reply is None:
        return None
    return str(chat_id), reply
