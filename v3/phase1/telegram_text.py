"""Compact Korean one-line summaries for runner notifications.

The runner records full event details in its evidence file; Telegram only needs
a short human line plus the Demo marker. Nothing here changes what is persisted.
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from typing import Any

ACTION_LABELS = {
    "spot_buy_ioc": "현물 매수 제출",
    "hedge_perp_sell": "선물 숏 헤지 제출",
    "close_perp_buy": "선물 종료 제출",
    "close_spot_sell": "현물 매도 제출",
}
SIDE_LABELS = {"BUY": "매수", "SELL": "매도"}


def _instrument(name: str) -> str:
    return "선물" if "PERP" in name else "현물"


def _price(value: Any) -> str:
    return str(Decimal(str(value)).quantize(Decimal("0.01")))


def compact_event(kind: str, detail: Mapping[str, Any]) -> tuple[str, str, dict[str, Any]]:
    """Return (title, summary, details) for one runner event."""
    if kind == "start":
        if detail.get("status") == "RESUMING":
            return (
                "재시작 · 열린 에피소드 재개",
                f"intent {str(detail.get('intent_id', ''))[:8]}",
                {},
            )
        return (
            "실행 시작",
            f"에피소드 최대 {detail.get('maximum_episodes', '?')}회 · 보유 {detail.get('hold_seconds', '?')}초",
            {},
        )
    if kind == "trade":
        if detail.get("fill_confirmed"):
            side = SIDE_LABELS.get(str(detail.get("side")), str(detail.get("side")))
            return (
                f"체결 {_instrument(str(detail.get('instrument', '')))} {side}",
                f"{Decimal(str(detail['quantity'])).normalize()} BTC @ {_price(detail['price'])}",
                {},
            )
        action = ACTION_LABELS.get(str(detail.get("action")), str(detail.get("action")))
        reason = detail.get("episode_reason")
        summary = reason if reason else ("접수 대기" if detail.get("submitted") else "제출 실패")
        if detail.get("status") == "UNKNOWN":
            summary = "전송 결과 불명 · 재전송 없음"
        return action, summary, {}
    if kind == "stop":
        if detail.get("status") == "STOPPED":
            return (
                "실행 종료",
                f"사유 {detail.get('reason')} · 종료 에피소드 {detail.get('episodes_closed', '?')}",
                {},
            )
        if detail.get("residual_settled"):
            return (
                "에피소드 종료 · 잔량 정산",
                f"잔량 {detail.get('residual_base')} BTC 보유 기록 · 정확 flat 아님",
                {},
            )
        if detail.get("completed_episode"):
            return "에피소드 종료 · flat", "양 레그 0", {}
        return "중단", str(detail.get("status", "")), {}
    if kind == "error":
        return (
            f"오류 {detail.get('error_type', '')}",
            "신규 주문 중단 · 확인 필요",
            {"status": detail.get("status"), "reason": detail.get("reason")}
            if detail.get("reason")
            else {},
        )
    return kind, "", {}
