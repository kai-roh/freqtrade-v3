"""Order-free forward observation of the fixed MA200 (docs/MA200_FORWARD_OBSERVATION.md).

Every run recomputes the virtual accounts from the observation start with the
same simulator, rule, costs, and exchange constraints as the research, without
closing at the end. Nothing here can place an order: it reads public candles
and writes a report and a Telegram message.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any

import pandas as pd

from v3.phase2.data import Phase2Panel

from .trend import NORMAL, SYMBOLS, Cost, TrendRule, VenueFilters, simulate_trend, target_weights

OBSERVATION_START = pd.Timestamp("2026-10-03 00:00", tz="UTC")
DRY_RUN_DAYS = 7
SLEEVE = 1000.0
SPOT_FEE_BPS = 10.0
MA200 = TrendRule("ma200")
BH_VT = TrendRule("bh_vt")
KST = timedelta(hours=9)
STALE_AFTER = pd.Timedelta(hours=2)


@dataclass(frozen=True)
class ObservationInputs:
    perp: Phase2Panel
    spot: Phase2Panel
    perp_filters: VenueFilters
    spot_filters: VenueFilters


def last_complete_hour(now: pd.Timestamp) -> pd.Timestamp:
    """Open time of the newest hourly candle that has fully closed."""
    return now.floor("h") - pd.Timedelta(hours=1)


def _signal(panel: Phase2Panel, cutoff: pd.Timestamp) -> dict[str, Any]:
    """Latest MA200 decision at or before ``cutoff``: weight and distance to the average."""
    weights = target_weights(panel, MA200)
    weights = weights[weights.index <= cutoff].dropna(how="all")
    if weights.empty:
        return {"decision_time": None, "weights": {}, "distance": {}}
    decision = weights.index[-1]
    closes = panel.close.shift(1)
    daily = closes[closes.index.hour == 0]
    daily = daily[daily.index <= decision]
    average = daily.rolling(200, min_periods=200).mean().iloc[-1]
    last = daily.iloc[-1]
    return {
        "decision_time": decision.isoformat(),
        "weights": {s: float(weights.loc[decision, s]) for s in SYMBOLS},
        "distance": {s: float(last[s] / average[s] - 1.0) for s in SYMBOLS},
    }


def _period_pnl(equity: pd.Series, current: float, start: pd.Timestamp, freq: str) -> list[dict]:
    """P&L per calendar period (week starting Monday, or month) from daily 00:00 equity."""
    points = equity[equity.index >= start]
    if freq == "W":
        period_start = points.index.normalize() - pd.to_timedelta(points.index.weekday, unit="D")
    else:
        period_start = points.index.normalize() - pd.to_timedelta(points.index.day - 1, unit="D")
    rows = []
    starts = sorted(set(period_start))
    for i, ps in enumerate(starts):
        opening = points[period_start == ps].iloc[0] if i else float(points.iloc[0])
        closing = (
            float(points[period_start == starts[i + 1]].iloc[0]) if i + 1 < len(starts) else current
        )
        rows.append({"period_start": ps.isoformat(), "pnl": closing - float(opening)})
    return rows


def _account(panel, rule, cost, filters, market, start, end) -> dict[str, Any]:
    result = simulate_trend(
        panel,
        [(start, rule)],
        cost=cost,
        start=start,
        end=end,
        sleeve=SLEEVE,
        filters=filters,
        market=market,
        flatten_at_end=False,
    )
    current = SLEEVE + result.decomposition["total_pnl"]
    daily = result.equity.iloc[:-1]  # 00:00 points; the last entry is the live valuation
    day_start = daily.iloc[-1] if len(daily) else SLEEVE
    week_start = end.normalize() - pd.Timedelta(days=end.weekday())
    month_start = end.normalize().replace(day=1)

    def since(ts: pd.Timestamp) -> float:
        points = daily[daily.index >= ts]
        return current - (float(points.iloc[0]) if len(points) else SLEEVE)

    cap = SLEEVE / len(SYMBOLS)
    positions = {
        s: {
            "qty": q,
            "notional": q * result.extra["last_open"][s],
            "weight": q * result.extra["last_open"][s] / cap,
        }
        for s, q in result.extra["open_positions"].items()
    }
    return {
        "equity": current,
        "pnl_total": current - SLEEVE,
        "pnl_day": current - float(day_start),
        "pnl_week": since(week_start),
        "pnl_month": since(month_start),
        "decomposition": result.decomposition,
        "positions": positions,
        "trades": result.extra["trade_log"],
        "skipped_orders": result.rounding_skips,
        "order_attempts": result.extra["order_attempts"],
        "weekly": _period_pnl(daily, current, start, "W"),
        "monthly": _period_pnl(daily, current, start, "M"),
        "last_hour": result.extra["last_hour"],
    }


def observe(
    inputs: ObservationInputs,
    *,
    now: pd.Timestamp,
    start: pd.Timestamp = OBSERVATION_START,
    cost: Cost = NORMAL,
) -> dict[str, Any]:
    target_end = last_complete_hour(now)
    end = min(target_end, inputs.perp.open.index[-1], inputs.spot.open.index[-1])
    checks = {
        "perp_data_fresh": inputs.perp.open.index[-1] >= target_end - STALE_AFTER,
        "spot_data_fresh": inputs.spot.open.index[-1] >= target_end - STALE_AFTER,
        "funding_fresh": len(inputs.perp.funding) > 0
        and inputs.perp.funding.index[-1] >= end - pd.Timedelta(hours=9),
    }
    report: dict[str, Any] = {
        "now": now.isoformat(),
        "observation_start": start.isoformat(),
        "evaluated_to": end.isoformat(),
        "sleeve": SLEEVE,
        "orders_submitted": False,
        "signal": _signal(inputs.perp, end),
        "checks": checks,
    }
    if end < start + pd.Timedelta(hours=1):
        report["status"] = "not_started"
        return report
    spot_cost = Cost(cost.name, cost.slippage_bps, fee_bps=SPOT_FEE_BPS)
    accounts = {
        "MA200": _account(inputs.perp, MA200, cost, inputs.perp_filters, "perp", start, end),
        "현물 보유": _account(
            inputs.spot, BH_VT, spot_cost, inputs.spot_filters, "spot", start, end
        ),
        "선물 보유": _account(inputs.perp, BH_VT, cost, inputs.perp_filters, "perp", start, end),
    }
    checks["no_skipped_orders"] = accounts["MA200"]["skipped_orders"] == 0
    report["status"] = "running"
    report["dry_run_day"] = int((end - start).total_seconds() // 86400) + 1
    report["dry_run_days"] = DRY_RUN_DAYS
    report["accounts"] = accounts
    return report


def _kst(ts: str | pd.Timestamp) -> str:
    return (pd.Timestamp(ts) + KST).strftime("%m-%d %H:%M")


def _side(weight: float) -> str:
    if weight > 0:
        return "롱"
    if weight < 0:
        return "숏"
    return "없음"


def _signed(value: float) -> str:
    return f"{value:+,.2f}"


def render_message(report: dict[str, Any], *, weekly: bool, monthly: bool) -> str:
    sig = report["signal"]
    distance = " · ".join(
        f"{s} {sig['distance'][s]:+.1%}({_side(sig['weights'][s])})" for s in sig["distance"]
    )
    checks = report["checks"]
    failed = [name for name, ok in checks.items() if not ok]
    check_line = "점검 정상" if not failed else "점검 실패: " + ", ".join(failed)
    if report["status"] == "not_started":
        return "\n".join(
            [
                "[관측][MA200] 관측 시작 전 · 주문 없음",
                f"시작: {_kst(report['observation_start'])} KST 결정, 1시간 뒤 가상 체결",
                f"현재 신호({_kst(sig['decision_time'])} KST 결정 기준): {distance}",
                check_line,
            ]
        )
    ma = report["accounts"]["MA200"]
    lines = [
        f"[관측][MA200] {_kst(report['evaluated_to'])} KST 기준 · 주문 없음 · "
        f"운영 점검 {min(report['dry_run_day'], report['dry_run_days'])}/{report['dry_run_days']}일",
        "포지션: "
        + " · ".join(
            f"{s} {_side(p['weight'])} {abs(p['qty']):g} ({p['weight']:+.2f})"
            for s, p in ma["positions"].items()
        ),
        f"가상 자산: {ma['equity']:,.2f} USDT (시작 대비 {_signed(ma['pnl_total'])})",
        f"손익: 오늘 {_signed(ma['pnl_day'])} · 이번 주 {_signed(ma['pnl_week'])} · "
        f"이번 달 {_signed(ma['pnl_month'])}",
        "비교(오늘): "
        + " · ".join(
            f"{name} {_signed(acc['pnl_day'])}"
            for name, acc in report["accounts"].items()
            if name != "MA200"
        ),
        f"MA200 거리: {distance}",
    ]
    today = [
        t
        for t in ma["trades"]
        if pd.Timestamp(t["time"]) > pd.Timestamp(report["evaluated_to"]) - pd.Timedelta(hours=24)
    ]
    if today:
        lines.append(
            "오늘 가상 주문: "
            + " · ".join(
                f"{t['symbol']} {'매수' if t['qty_after'] > t['qty_before'] else '매도'} "
                f"{abs(t['qty_after'] - t['qty_before']):g} @ {t['price']:,.1f}"
                for t in today
            )
        )
    lines.append(check_line)
    for flag, key, title in ((weekly, "weekly", "주간"), (monthly, "monthly", "월간")):
        if not flag:
            continue
        lines.append(f"{title} 손익표 (USDT): 기간 | MA200 | 현물 보유 | 선물 보유")
        names = list(report["accounts"])
        for i, row in enumerate(report["accounts"]["MA200"][key]):
            values = [report["accounts"][n][key][i]["pnl"] for n in names]
            label = _kst(row["period_start"])[:5]
            lines.append(f"{label} | " + " | ".join(_signed(v) for v in values))
    return "\n".join(lines)
