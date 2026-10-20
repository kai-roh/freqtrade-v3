#!/usr/bin/env python3
"""T1 taker-flow ensemble Demo executor and guard (Decision 0029). Demo only.

Subcommands:
  init         create the state (start time, capital, loss stop) once
  execute      daily after 00:00 UTC: Monday rebalance to the T1 targets, other days record
  guard        loss stop / stale executor / mismatch check; flattens and halts on trigger
  clear-halt   lift a halt after review (records the actual positions as the baseline)
  set-stop     change the loss-stop level with an audit record (user decision)
  status       print the state without trading
  targets      print this week's T1 targets from Mainnet public data (no account access)

Demo-only verification options: --test-force-rebalance, --test-stop-equity, --test-now.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from decimal import Decimal
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.run_ma200_live import _env_values, _kst  # noqa: E402
from v3.ma200live.client import Credentials, FuturesClient  # noqa: E402
from v3.ma200live.engine import (  # noqa: E402
    GUARD_ALERT_AFTER,
    LiveConfig,
    StateStore,
    guard_alert_due,
    strategy_equity,
)
from v3.phase1.binance_probe import load_dotenv_credentials  # noqa: E402
from v3.phase1.notifications import send_telegram_text  # noqa: E402
from v3.t1live.engine import run_executor, run_guard  # noqa: E402
from v3.t1live.signal import live_targets  # noqa: E402

TAG = "[DEMO][T1"


def _client(args) -> FuturesClient:
    creds = load_dotenv_credentials(args.credentials_env_file, "BINANCE_DEMO")
    if creds is None:
        raise SystemExit("BINANCE_DEMO credentials missing")
    return FuturesClient("demo", Credentials(creds.api_key, creds.api_secret), symbols=())


def _name(symbol: str) -> str:
    return symbol.removesuffix("USDT")


def executor_message(report: dict) -> str:
    tag = f"{TAG} 실행]"
    when = _kst(report["now"])
    if report["status"] == "halted":
        return (
            f"{tag} {when} KST · 정지 중(사유: {', '.join(report['halt']['reasons'])}) · 주문 없음"
        )
    if report["status"] == "error":
        return f"{tag} {when} KST · 오류: {report['error']} · 주문 없음, 보호 장치가 감시 중"
    eq = report["equity"]
    ch = report["changes"]
    lines = [
        f"{tag} {when} KST · {'정상' if report['status'] == 'ok' else '불일치 경고'}"
        + (" · 주간 리밸런싱" if report["rebalance"] else ""),
        f"전략 자산 {Decimal(eq['equity']):,.2f} USDT · 오늘 {Decimal(ch['day_change']):+,.2f}"
        f" · 이번 주 {Decimal(ch['week_change']):+,.2f} · 누적 {Decimal(ch['total_change']):+,.2f}",
        f"펀딩 {Decimal(eq['funding']):+.2f} · 수수료 {Decimal(eq['commission']):+.2f}"
        f" · 중단선 {Decimal(eq['stop_equity']):,.0f}까지 {Decimal(eq['distance_to_stop']):,.2f}",
    ]
    if report["rebalance"] and report.get("signal"):
        w = report["signal"]["weights"]
        longs = [f"{_name(s)} {v:.0%}" for s, v in sorted(w.items(), key=lambda x: -x[1]) if v > 0]
        shorts = [f"{_name(s)} {-v:.0%}" for s, v in sorted(w.items(), key=lambda x: x[1]) if v < 0]
        lines.append(f"목표(결정 {report['signal']['decision_day']}): 롱 " + ", ".join(longs))
        lines.append("숏 " + ", ".join(shorts))
        filled = sum(1 for r in report["results"] if Decimal(r["filled"]) > 0)
        lines.append(f"주문 {len(report['results'])}건 중 체결 {filled}건")
        if report["skipped"]:
            lines.append(
                "건너뜀: " + ", ".join(f"{_name(s)}({why})" for s, why in report["skipped"].items())
            )
    pos = report.get("positions", {})
    if pos:
        movers = sorted(pos.items(), key=lambda x: -abs(Decimal(x[1]["unrealized"])))[:4]
        lines.append(
            f"포지션 {len(pos)}개 · 평가손익 큰 순: "
            + ", ".join(f"{_name(s)} {Decimal(p['unrealized']):+.2f}" for s, p in movers)
        )
    if report.get("mismatch"):
        lines.append(f"불일치: {report['mismatch']} (보호 장치가 확인)")
    return "\n".join(lines)


def guard_message(report: dict) -> str | None:
    tag = f"{TAG} 보호]"
    if report["status"] == "triggered":
        eq = report.get("equity", {})
        return (
            f"{tag} {_kst(report['now'])} KST · 자동 청산 · 사유: {', '.join(report['reasons'])}\n"
            f"전략 자산 {Decimal(eq.get('equity', '0')):,.2f} USDT (기준 {report.get('stop_used')})"
            " → 전량 감축 청산, 실행 정지. 재개는 검토 후 명시적 해제로만."
        )
    if report["status"] == "halted_flattened":
        return f"{tag} {_kst(report['now'])} KST · 정지 중 포지션 발견 → 다시 청산"
    return None


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        "command",
        choices=["init", "execute", "guard", "clear-halt", "set-stop", "status", "targets"],
    )
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--credentials-env-file", type=Path, required=True)
    parser.add_argument("--stop-equity", default="650")
    parser.add_argument("--starting-capital", default="1000")
    parser.add_argument("--note", default="")
    parser.add_argument("--send-telegram", action="store_true")
    parser.add_argument("--test-force-rebalance", action="store_true")
    parser.add_argument("--test-stop-equity")
    parser.add_argument("--test-now")
    args = parser.parse_args()
    store = StateStore(args.state_dir)
    now = pd.Timestamp(args.test_now) if args.test_now else pd.Timestamp.now(tz="UTC")
    if args.command == "init":
        store.init(
            LiveConfig(
                environment="demo",
                start_ms=int(pd.Timestamp.now(tz="UTC").timestamp() * 1000),
                starting_capital=Decimal(args.starting_capital),
                sleeve=Decimal(args.starting_capital),
                stop_equity=Decimal(args.stop_equity),
                price_cap_bps=Decimal(30),
            )
        )
        print(json.dumps(store.config().to_json(), indent=2))
        return 0
    client = _client(args)
    if args.command == "targets":
        print(json.dumps(live_targets(client, now), indent=2, default=str))
        return 0
    if not (store.root / "config.json").is_file() and args.command in {"execute", "guard"}:
        print(f"{now.isoformat()} T1 state not initialized; nothing to do")
        return 0
    config = store.config()
    telegram = _env_values(args.credentials_env_file)
    message: str | None = None
    if args.command == "execute":
        report = run_executor(client, store, now=now, force_rebalance=args.test_force_rebalance)
        message = executor_message(report)
    elif args.command == "guard":
        stop = Decimal(args.test_stop_equity) if args.test_stop_equity else None
        try:
            report = run_guard(client, store, now=now, test_stop_equity=stop)
        except Exception as exc:  # noqa: BLE001 - every failure must be counted and reported
            error = f"{type(exc).__name__}: {exc}"
            failures = store.guard_failed(error)
            report = {"kind": "guard", "now": now.isoformat(), "status": "error", "error": error,
                      "consecutive_failures": failures}  # fmt: skip
            if guard_alert_due(failures):
                message = (
                    f"{TAG} 보호] {_kst(report['now'])} KST · 점검 실패 {failures}회 연속 "
                    f"(10분 간격) · 손실 중단 감시가 멈춘 상태\n오류: {error[:200]}"
                )
        else:
            previous = store.guard_succeeded() if report["status"] != "busy" else 0
            message = guard_message(report)
            if previous >= GUARD_ALERT_AFTER:
                recovered = (
                    f"{TAG} 보호] {_kst(report['now'])} KST · 점검 복구 "
                    f"({previous}회 연속 실패 후 정상)"
                )
                message = recovered + (f"\n{message}" if message else "")
    elif args.command == "set-stop":
        before, after = store.update_stop(Decimal(args.stop_equity), args.note)
        report = {"kind": "set-stop", "from": str(before), "to": str(after), "note": args.note}
        message = f"{TAG} 보호] 손실 중단선 변경: {before} → {after} USDT ({args.note})"
    elif args.command == "clear-halt":
        held = {
            s: str(p["qty"]) for s, p in client.positions(every_symbol=True).items() if p["qty"]
        }
        previous = store.clear_halt(args.note or "cleared", held)
        report = {"kind": "clear-halt", "previous": previous}
        message = f"{TAG} 보호] 정지 해제: {args.note or '-'}" if previous else None
    else:
        positions = client.positions(every_symbol=True)
        report = {
            "kind": "status",
            "halt": store.halt(),
            "heartbeat": store.heartbeat(),
            "positions": {s: str(p["qty"]) for s, p in positions.items() if p["qty"]},
            "equity": {
                k: str(v)
                for k, v in strategy_equity(client, config, positions, every_symbol=True).items()
            },
        }
    report["source_sha"] = os.environ.get("PHASE1_BUILD_SOURCE_SHA")
    if message and args.send_telegram:
        delivery = send_telegram_text(
            message,
            token=telegram.get("TELEGRAM_TOKEN", ""),
            chat_id=telegram.get("TELEGRAM_CHAT_ID", ""),
        )
        report["telegram_delivered"] = delivery.delivered
        if args.command == "execute":
            store.save_report(f"executor-{now:%Y%m%d}.json", report)
            if report.get("status") != "halted":
                store.save_report("executor-latest.json", report)
    if args.command == "guard" and report.get("status") in {"ok", "busy"}:
        equity = report.get("equity", {}).get("equity")
        print(
            f"{report['now']} guard {report['status']} equity={equity} n={len(report.get('positions', {}))}"
        )
    else:
        print(json.dumps(report, indent=2, sort_keys=True, default=str))
    if message:
        print(message)
    return 0 if report.get("status") not in {"error", "mismatch"} else 3


if __name__ == "__main__":
    raise SystemExit(main())
