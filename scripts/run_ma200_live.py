#!/usr/bin/env python3
"""MA200 live executor and guard (Decision 0020). Demo by default; Mainnet is locked.

Subcommands:
  init         create the state (start time, capital, risk) once
  execute      daily rebalance (after 01:00 UTC)
  guard        loss stop / stale executor / mismatch check; flattens and halts on trigger
  clear-halt   lift a halt after review (records the actual positions as the baseline)
  set-stop     change the loss-stop level with an audit record (user decision)
  status       print the state without trading

Demo-only verification options: --test-override-weights, --test-stop-equity, --test-now.
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

from v3.ma200live.client import SYMBOLS, Credentials, FuturesClient  # noqa: E402
from v3.ma200live.engine import (  # noqa: E402
    GUARD_ALERT_AFTER,
    LiveConfig,
    StateStore,
    guard_alert_due,
    run_executor,
    run_guard,
    strategy_equity,
)
from v3.phase1.binance_probe import load_dotenv_credentials  # noqa: E402
from v3.phase1.notifications import send_telegram_text  # noqa: E402

KST = pd.Timedelta(hours=9)
NAMES = {"BTCUSDT": "BTC", "ETHUSDT": "ETH"}


def _env_values(path: Path) -> dict[str, str]:
    values = {}
    for line in path.read_text().splitlines():
        name, sep, value = line.partition("=")
        if sep:
            values[name.strip()] = value.strip().strip("\"'")
    return values


def _client(args, environment: str) -> FuturesClient:
    prefix = "BINANCE_DEMO" if environment == "demo" else "BINANCE"
    creds = load_dotenv_credentials(args.credentials_env_file, prefix)
    if creds is None:
        raise SystemExit(f"{prefix} credentials missing")
    authorization = None
    if environment == "mainnet":
        if not args.authorization or not args.authorization.is_file():
            raise SystemExit("Mainnet needs --authorization naming a real-capital decision")
        authorization = json.loads(args.authorization.read_text())
    return FuturesClient(
        environment, Credentials(creds.api_key, creds.api_secret), authorization=authorization
    )


def _side(weight: float) -> str:
    return "롱" if weight > 0 else ("숏" if weight < 0 else "없음")


def _kst(ts: str) -> str:
    return (pd.Timestamp(ts) + KST).strftime("%m-%d %H:%M")


def executor_message(report: dict, env: str) -> str:
    tag = f"[{env.upper()}][MA200 실행]"
    if report["status"] == "halted":
        reasons = ", ".join(report["halt"]["reasons"])
        return f"{tag} {_kst(report['now'])} KST · 정지 중(사유: {reasons}) · 주문 없음"
    if report["status"] == "error":
        return f"{tag} {_kst(report['now'])} KST · 오류: {report['error']} · 주문 없음, 보호 장치가 감시 중"
    sig = report["signal"]
    lines = [
        f"{tag} {_kst(report['now'])} KST · {'정상' if report['status'] == 'ok' else '불일치 경고'}",
        "신호: "
        + " · ".join(
            f"{NAMES[s]} {_side(w)} {w:+.2f} (MA200 {sig['distance'][s]:+.1%})"
            for s, w in report["weights_used"].items()
        ),
    ]
    fills = [r for r in report["results"] if Decimal(r["filled"]) > 0]
    if fills:
        lines.append(
            "주문: "
            + " · ".join(
                f"{NAMES[r['symbol']]} {'매수' if r['side'] == 'BUY' else '매도'} {r['filled']}"
                f" @ {Decimal(r['avg_price']):,.1f}{' (감축)' if r['reduce_only'] else ''}"
                for r in fills
            )
        )
    else:
        skipped = [p["skipped"] for p in report["plans"] if p["skipped"]]
        lines.append(
            "주문: 없음" + (f" ({'; '.join(skipped)})" if skipped else " (변화 기준 미달)")
        )
    lines.append(
        "포지션: " + " · ".join(f"{NAMES[s]} {p['qty']}" for s, p in report["positions"].items())
    )
    eq = report["equity"]
    lines.append(
        f"전략 자산: {Decimal(eq['equity']):,.2f} USDT · 중단선 {Decimal(eq['stop_equity']):,.0f}"
        f"까지 {Decimal(eq['distance_to_stop']):,.2f} · 펀딩 {Decimal(eq['funding']):+.2f}"
        f" · 수수료 {Decimal(eq['commission']):+.2f}"
    )
    if report.get("mismatch"):
        lines.append(f"불일치: {report['mismatch']} (보호 장치가 확인)")
    if report.get("override_weights"):
        lines.append(f"Demo 검증용 비중 덮어쓰기: {report['override_weights']}")
    return "\n".join(lines)


def guard_message(report: dict, env: str) -> str | None:
    tag = f"[{env.upper()}][MA200 보호]"
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
        "command", choices=["init", "execute", "guard", "clear-halt", "set-stop", "status"]
    )
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--credentials-env-file", type=Path, required=True)
    parser.add_argument("--environment", choices=["demo", "mainnet"], default="demo")
    parser.add_argument("--authorization", type=Path)
    parser.add_argument("--vol-target", type=float, default=0.25)
    parser.add_argument("--stop-equity", default="900")
    parser.add_argument("--starting-capital", default="1000")
    parser.add_argument("--note", default="")
    parser.add_argument("--send-telegram", action="store_true")
    parser.add_argument("--test-override-weights", help="Demo only, e.g. BTCUSDT=-0.4,ETHUSDT=0")
    parser.add_argument("--test-stop-equity", help="Demo only: guard stop level for verification")
    parser.add_argument("--test-now", help="Demo only: ISO time for staleness verification")
    args = parser.parse_args()
    store = StateStore(args.state_dir)
    now = pd.Timestamp.now(tz="UTC")
    tests = args.test_override_weights or args.test_stop_equity or args.test_now
    if tests and args.environment != "demo":
        raise SystemExit("test options are Demo-only")
    if args.test_now:
        now = pd.Timestamp(args.test_now)
    if args.command == "init":
        store.init(
            LiveConfig(
                environment=args.environment,
                start_ms=int(pd.Timestamp.now(tz="UTC").timestamp() * 1000),
                starting_capital=Decimal(args.starting_capital),
                sleeve=Decimal(args.starting_capital),
                vol_target=args.vol_target,
                stop_equity=Decimal(args.stop_equity),
            )
        )
        print(json.dumps(store.config().to_json(), indent=2))
        return 0
    config = store.config()
    if config.environment != args.environment:
        raise SystemExit(f"state is for {config.environment}, not {args.environment}")
    client = _client(args, config.environment)
    telegram = _env_values(args.credentials_env_file)
    report: dict
    message: str | None = None
    if args.command == "execute":
        override = None
        if args.test_override_weights:
            override = {
                k: float(v)
                for k, v in (item.split("=") for item in args.test_override_weights.split(","))
            }
        report = run_executor(client, store, now=now, override_weights=override)
        message = executor_message(report, config.environment)
    elif args.command == "guard":
        stop = Decimal(args.test_stop_equity) if args.test_stop_equity else None
        try:
            report = run_guard(client, store, now=now, test_stop_equity=stop)
        except Exception as exc:  # noqa: BLE001 - every failure must be counted and reported
            error = f"{type(exc).__name__}: {exc}"
            failures = store.guard_failed(error)
            report = {
                "kind": "guard",
                "now": now.isoformat(),
                "status": "error",
                "error": error,
                "consecutive_failures": failures,
            }
            if guard_alert_due(failures):
                message = (
                    f"[{config.environment.upper()}][MA200 보호] {_kst(report['now'])} KST · "
                    f"점검 실패 {failures}회 연속 (10분 간격) · 손실 중단 감시가 멈춘 상태\n"
                    f"오류: {error[:200]}"
                )
        else:
            previous = store.guard_succeeded()
            message = guard_message(report, config.environment)
            if previous >= GUARD_ALERT_AFTER:
                recovered = (
                    f"[{config.environment.upper()}][MA200 보호] {_kst(report['now'])} KST · "
                    f"점검 복구 ({previous}회 연속 실패 후 정상)"
                )
                message = recovered + (f"\n{message}" if message else "")
    elif args.command == "set-stop":
        before, after = store.update_stop(Decimal(args.stop_equity), args.note)
        report = {"kind": "set-stop", "from": str(before), "to": str(after), "note": args.note}
        message = (
            f"[{config.environment.upper()}][MA200 보호] 손실 중단선 변경: "
            f"{before} → {after} USDT ({args.note})"
        )
    elif args.command == "clear-halt":
        positions = client.positions()
        previous = store.clear_halt(
            args.note or "cleared", {s: str(positions[s]["qty"]) for s in SYMBOLS}
        )
        report = {"kind": "clear-halt", "previous": previous}
        message = (
            f"[{config.environment.upper()}][MA200 보호] 정지 해제: {args.note or '-'}"
            if previous
            else None
        )
    else:
        positions = client.positions()
        report = {
            "kind": "status",
            "halt": store.halt(),
            "heartbeat": store.heartbeat(),
            "positions": {s: str(positions[s]["qty"]) for s in SYMBOLS},
            "equity": {k: str(v) for k, v in strategy_equity(client, config, positions).items()},
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
            # The engine saved the report before delivery; record the delivery too.
            store.save_report(f"executor-{now:%Y%m%d}.json", report)
            if report.get("status") != "halted":
                store.save_report("executor-latest.json", report)
    if args.command == "guard" and report.get("status") == "ok":
        equity = report.get("equity", {}).get("equity")
        print(f"{report['now']} guard ok equity={equity} positions={report.get('positions')}")
    else:
        print(json.dumps(report, indent=2, sort_keys=True, default=str))
    if message:
        print(message)
    return 0 if report.get("status") not in {"error", "mismatch"} else 3


if __name__ == "__main__":
    raise SystemExit(main())
