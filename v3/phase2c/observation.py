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


def _report_days(end: pd.Timestamp, start: pd.Timestamp) -> list[pd.Timestamp]:
    """Daily report valuation times (same hour as ``end``) from the first one after ``start``."""
    days = []
    t = end
    while t > start:
        days.append(t)
        t -= pd.Timedelta(days=1)
    return days[::-1]


def _period_key(t: pd.Timestamp, freq: str) -> str:
    local = (t + KST).normalize()
    label = local - pd.Timedelta(days=local.weekday()) if freq == "W" else local.replace(day=1)
    return label.strftime("%Y-%m-%d")


def _period_pnl(
    value_at, days: list[pd.Timestamp], freq: str, current_end: pd.Timestamp
) -> list[dict]:
    """P&L per calendar period (KST week from Monday, or month) of the daily reports.

    Each daily report covers the 24 hours before its valuation time, so a period is the
    sum of its reports and the periods add up to the total.
    """
    rows: dict[str, float] = {}
    for t in days:
        key = _period_key(t, freq)
        rows[key] = rows.get(key, 0.0) + value_at(t) - value_at(t - pd.Timedelta(days=1))
    current = _period_key(current_end, freq)
    return [
        {"period_start": key, "pnl": pnl, "complete": key != current} for key, pnl in rows.items()
    ]


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
    marks = pd.Series(result.extra["hourly_equity"], dtype=float)
    marks.index = pd.to_datetime(marks.index)

    def value_at(ts: pd.Timestamp) -> float:
        """Account value after the trades of hour ``ts``; the sleeve before the start."""
        points = marks[marks.index <= ts]
        return float(points.iloc[-1]) if len(points) else SLEEVE

    # Periods follow the daily reports: a report covers the 24 hours before ``end``; the
    # week starts with Monday's report and the month with the report on the 1st (KST).
    local = (end + KST).normalize()
    week_first = end - pd.Timedelta(days=local.weekday())
    month_first = end - pd.Timedelta(days=local.day - 1)
    days = _report_days(end, start)

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
        "pnl_day": current - value_at(end - pd.Timedelta(days=1)),
        "pnl_week": current - value_at(week_first - pd.Timedelta(days=1)),
        "pnl_month": current - value_at(month_first - pd.Timedelta(days=1)),
        "decomposition": result.decomposition,
        "positions": positions,
        "trades": result.extra["trade_log"],
        "skipped_orders": result.rounding_skips,
        "order_attempts": result.extra["order_attempts"],
        "weekly": _period_pnl(value_at, days, "W", end),
        "monthly": _period_pnl(value_at, days, "M", end),
        "last_hour": result.extra["last_hour"],
    }


def reconcile_live(report: dict[str, Any], live_positions: dict[str, str] | None) -> None:
    """Compare executor positions (BTCUSDT/ETHUSDT quantities) with the virtual MA200 account.

    Differences are shown as weight units of the per-asset cap; the Demo lot (0.0001 BTC)
    is finer than the Mainnet lot the observation uses (0.001 BTC), so small gaps are expected.
    """
    if not live_positions or report.get("status") != "running":
        return
    virtual = report["accounts"]["MA200"]["positions"]
    cap = SLEEVE / len(SYMBOLS)
    rows = {}
    for asset in SYMBOLS:
        live_qty = float(live_positions.get(f"{asset}USDT", "0"))
        v = virtual[asset]
        price = v["notional"] / v["qty"] if v["qty"] else None
        if price is None:
            rows[asset] = {"live_qty": live_qty, "virtual_qty": 0.0, "weight_gap": None}
            continue
        rows[asset] = {
            "live_qty": live_qty,
            "virtual_qty": v["qty"],
            "weight_gap": (live_qty - v["qty"]) * price / cap,
        }
    report["live_reconciliation"] = rows
    report["checks"]["live_matches_virtual"] = all(
        r["weight_gap"] is None
        and abs(r["live_qty"]) < 1e-12
        or r["weight_gap"] is not None
        and abs(r["weight_gap"]) <= 0.10
        for r in rows.values()
    )


def summarize_live(
    report: dict[str, Any], executor_reports: list[dict[str, Any]], starting_capital: float
) -> None:
    """Add the Demo executor's actual account (equity at each daily run) to the report.

    Daily P&L is the change between consecutive executor runs; the first run is measured
    from the starting capital. Weeks and months use the same KST periods as the virtual
    accounts. Halted or failed runs carry no equity and are skipped.
    """
    if report.get("status") != "running":
        return
    now = pd.Timestamp(report["now"])
    runs = sorted(
        (
            (pd.Timestamp(r["now"]), r)
            for r in executor_reports
            if isinstance(r.get("equity"), dict) and "equity" in r["equity"]
        ),
        key=lambda item: item[0],
    )
    runs = [(t, r) for t, r in runs if t <= now]
    if not runs:
        return
    series = pd.Series({t: float(r["equity"]["equity"]) for t, r in runs})
    latest = runs[-1][1]["equity"]
    changes = series.diff()
    changes.iloc[0] = series.iloc[0] - starting_capital
    end = pd.Timestamp(report["evaluated_to"])

    def periods(freq: str) -> dict[str, float]:
        rows: dict[str, float] = {}
        for t, change in changes.items():
            key = _period_key(t, freq)
            rows[key] = rows.get(key, 0.0) + float(change)
        return rows

    weekly, monthly = periods("W"), periods("M")
    last = series.index[-1]
    report["live"] = {
        "last_run": last.isoformat(),
        "equity": float(series.iloc[-1]),
        "pnl_total": float(series.iloc[-1] - starting_capital),
        "pnl_day": float(changes.iloc[-1]),
        "pnl_week": weekly.get(_period_key(end, "W"), 0.0),
        "pnl_month": monthly.get(_period_key(end, "M"), 0.0),
        "distance_to_stop": float(latest["distance_to_stop"])
        if "distance_to_stop" in latest
        else None,
        "weekly": weekly,
        "monthly": monthly,
        "fresh": end - last < pd.Timedelta(hours=26),
    }
    report["checks"]["live_executor_fresh"] = report["live"]["fresh"]


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
        f"손익: 24시간 {_signed(ma['pnl_day'])} · 이번 주 {_signed(ma['pnl_week'])} · "
        f"이번 달 {_signed(ma['pnl_month'])}",
        "비교(24시간): "
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
    live = report.get("live_reconciliation")
    if live:
        lines.append(
            "Demo 실행 대사: "
            + " · ".join(
                f"{a} 실행 {r['live_qty']:g} / 관측 {r['virtual_qty']:g}"
                + (f" (비중 차 {r['weight_gap']:+.2f})" if r["weight_gap"] is not None else "")
                for a, r in live.items()
            )
        )
    actual = report.get("live")
    if actual:
        lines.append(
            f"Demo 실제: 자산 {actual['equity']:,.2f} USDT (시작 대비 {_signed(actual['pnl_total'])})"
            f" · 24시간 {_signed(actual['pnl_day'])} · 이번 주 {_signed(actual['pnl_week'])}"
            f" · 이번 달 {_signed(actual['pnl_month'])}"
            + (
                f" · 중단선까지 {actual['distance_to_stop']:,.2f}"
                if actual.get("distance_to_stop") is not None
                else ""
            )
            + ("" if actual["fresh"] else f" (마지막 실행 {_kst(actual['last_run'])} KST)")
        )
    lines.append(check_line)
    for flag, key, title in ((weekly, "weekly", "주간"), (monthly, "monthly", "월간")):
        if not flag:
            continue
        header = f"{title} 손익표 (USDT): 기간 | MA200 | 현물 보유 | 선물 보유"
        lines.append(header + (" | Demo 실제" if actual else ""))
        names = list(report["accounts"])
        for i, row in enumerate(report["accounts"]["MA200"][key]):
            values = [_signed(report["accounts"][n][key][i]["pnl"]) for n in names]
            if actual:
                demo = actual[key].get(row["period_start"])
                values.append(_signed(demo) if demo is not None else "-")
            label = row["period_start"][5:] + ("" if row["complete"] else " (진행 중)")
            lines.append(f"{label} | " + " | ".join(values))
    return "\n".join(lines)
