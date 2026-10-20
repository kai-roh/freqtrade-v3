"""T1 Demo executor and guard (Decision 0029).

The executor runs daily after 00:00 UTC. On Mondays (Sunday decisions) it computes
the T1 targets from Mainnet public candles and rebalances the account to them:
closes and reductions first, then openings and increases, all as IOC limit orders
with a price cap. On other days it only records the account. Between rebalances the
positions drift, as in the backtest.

The guard runs every few minutes. It closes everything reduce-only and halts on the
loss stop, a stale executor, or positions that differ from the executor's record.
Executor and guard share a lock so the guard never checks a half-finished rebalance.

Symbols the Demo venue does not list are left in cash and recorded. Demo funding and
order books differ from Mainnet, so Demo P&L is execution evidence; the T1 forward
verdict uses the Mainnet archive (PHASE2G_PREREGISTRATION.md §3).
"""

from __future__ import annotations

import fcntl
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

import pandas as pd

from v3.ma200live.client import ExchangeError, FuturesClient, floor_to
from v3.ma200live.engine import (
    GUARD_IOC_ATTEMPTS,
    GUARD_PRICE_CAP_BPS,
    LiveConfig,
    StateStore,
    Step,
    execute_step,
    strategy_equity,
)

from .signal import is_decision_day, live_targets

MARGIN_TYPE = "CROSSED"  # gross exposure 1 on cross margin: no single-position liquidation
LEVERAGE = 2


@contextmanager
def state_lock(root: Path, wait: bool) -> Iterator[bool]:
    """Exclusive lock on ``root/.lock``; yields False when busy and ``wait`` is False."""
    path = Path(root) / ".lock"
    handle = path.open("a")
    try:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | (0 if wait else fcntl.LOCK_NB))
        except BlockingIOError:
            yield False
            return
        try:
            yield True
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)
    finally:
        handle.close()


def _make_id(config: LiveConfig, role: str, day: str, run: int, step: int):
    env = "d" if config.environment == "demo" else "m"

    def make(symbol: str, attempt: int) -> str:
        return f"t1{env}{role}{day[2:]}r{run}s{step}a{attempt}{symbol}"[:36]

    return make


@dataclass
class Order:
    step: Step
    target_qty: Decimal


def plan_orders(
    current: dict[str, Decimal],
    targets: dict[str, float],
    prices: dict[str, Decimal],
    filters: dict[str, dict[str, Decimal]],
    sleeve: Decimal,
) -> tuple[list[Order], list[Order], dict[str, str], dict[str, Decimal]]:
    """Return (exits, entries, skipped, target quantities).

    Exits are closes and reductions (reduce-only); entries are openings and increases.
    A flip is a close followed by an opening. Openings below the venue minimum are
    skipped and recorded.
    """
    exits: list[Order] = []
    entries: list[Order] = []
    skipped: dict[str, str] = {}
    target_qty: dict[str, Decimal] = {}
    for symbol in sorted(set(current) | set(targets)):
        qty = current.get(symbol, Decimal(0))
        weight = targets.get(symbol, 0.0)
        if symbol not in filters:
            if weight:
                skipped[symbol] = "not listed on this venue"
            target_qty[symbol] = qty
            continue
        flt = filters[symbol]
        price = prices[symbol]
        raw = Decimal(str(weight)) * sleeve / price
        target = floor_to(abs(raw), flt["step"]) * (1 if raw >= 0 else -1)
        target_qty[symbol] = target
        if target == qty:
            continue

        def opening_ok(amount: Decimal, flt=flt, price=price) -> bool:
            return amount >= flt["min_qty"] and amount * price >= flt["min_notional"]

        def side(delta: Decimal) -> str:
            return "BUY" if delta > 0 else "SELL"

        flip = qty != 0 and target != 0 and (qty > 0) != (target > 0)
        if target == 0 or flip:
            exits.append(Order(Step(symbol, side(-qty), abs(qty), True, "close"), Decimal(0)))
            if flip:
                if opening_ok(abs(target)):
                    entries.append(
                        Order(Step(symbol, side(target), abs(target), False, "open"), target)
                    )
                else:
                    skipped[symbol] = "open below minimum order"
                    target_qty[symbol] = Decimal(0)
            continue
        delta = target - qty
        if qty != 0 and abs(target) < abs(qty):
            exits.append(Order(Step(symbol, side(delta), abs(delta), True, "reduce"), target))
        elif opening_ok(abs(delta)):
            purpose = "open" if qty == 0 else "increase"
            entries.append(Order(Step(symbol, side(delta), abs(delta), False, purpose), target))
        else:
            skipped[symbol] = "order below minimum notional"
            target_qty[symbol] = qty
    return exits, entries, skipped, target_qty


def _held(positions: dict[str, dict[str, Decimal]]) -> dict[str, Decimal]:
    return {s: p["qty"] for s, p in positions.items() if p["qty"] != 0}


def _record_equity(store: StateStore, now: pd.Timestamp, equity: Decimal) -> dict[str, Any]:
    """Keep one equity mark per UTC day; return day and week (since Monday) changes."""
    history = store._read("equity-history.json") or {}
    day = now.strftime("%Y-%m-%d")
    previous_days = sorted(d for d in history if d < day)
    history[day] = str(equity)
    store._write("equity-history.json", history)
    config = store.config()
    prev = Decimal(history[previous_days[-1]]) if previous_days else config.starting_capital
    monday = (now.normalize() - pd.Timedelta(days=now.weekday())).strftime("%Y-%m-%d")
    before_week = [d for d in previous_days if d < monday]
    week_base = Decimal(history[before_week[-1]]) if before_week else config.starting_capital
    return {
        "day_change": str(equity - prev),
        "week_change": str(equity - week_base),
        "total_change": str(equity - config.starting_capital),
    }


def run_executor(
    client: FuturesClient,
    store: StateStore,
    *,
    now: pd.Timestamp,
    force_rebalance: bool = False,
) -> dict[str, Any]:
    config = store.config()
    if force_rebalance and config.environment != "demo":
        raise PermissionError("forced rebalances are a Demo verification tool only")
    day = now.strftime("%Y%m%d")
    decision_day = now.floor("D") - pd.Timedelta(days=1)
    rebalance = force_rebalance or is_decision_day(decision_day)
    report: dict[str, Any] = {
        "kind": "executor",
        "now": now.isoformat(),
        "environment": config.environment,
        "rebalance": rebalance,
    }
    halt = store.halt()
    if halt is not None:
        report.update(status="halted", halt=halt)
        store.save_report(f"executor-{day}.json", report)
        return report
    with state_lock(store.root, wait=True):
        run = store.next_run_index(day)
        try:
            results: list[dict[str, Any]] = []
            skipped: dict[str, str] = {}
            target_qty: dict[str, Decimal] = {}
            signal = None
            if rebalance:
                signal = live_targets(client, now)
                venue = client.tradable_perpetuals()
                before = client.positions(every_symbol=True)
                client.allow(set(signal["weights"]) | set(_held(before)))
                listed = [s for s in client.symbols if s in venue]
                filters = {s: f for s, f in client.filters().items() if s in venue}
                for symbol in listed:
                    if client.open_orders(symbol):
                        raise RuntimeError(f"unexpected open orders on {symbol}")
                prices = {}
                for symbol in listed:
                    book = client.book(symbol)
                    prices[symbol] = (book["bid"] + book["ask"]) / 2
                targets = {s: w for s, w in signal["weights"].items()}
                exits, entries, skipped, target_qty = plan_orders(
                    _held(before), targets, prices, filters, config.sleeve
                )
                for order in entries:
                    client.ensure_margin(order.step.symbol, MARGIN_TYPE, LEVERAGE)
                for index, order in enumerate(exits + entries):
                    results.append(
                        execute_step(
                            client, store, config, order.step, filters[order.step.symbol],
                            day=day, run=run, index=index,
                            make_id=_make_id(config, "x", day, run, index),
                        )
                    )  # fmt: skip
            after = client.positions(every_symbol=True)
            steps = lot_steps(client, set(target_qty) | set(_held(after)))
            mismatch = {}
            for symbol, qty in target_qty.items():
                actual = after.get(symbol, {"qty": Decimal(0)})["qty"]
                if abs(actual - qty) > steps[symbol]:
                    mismatch[symbol] = f"target {qty} actual {actual}"
            equity = strategy_equity(client, config, after, every_symbol=True)
            changes = _record_equity(store, now, equity["equity"])
            ok = not mismatch
            previous = store.heartbeat() or {}
            store.write_heartbeat(
                {
                    "last_run": now.isoformat(),
                    "last_success": now.isoformat() if ok else previous.get("last_success"),
                    "consecutive_failures": 0
                    if ok
                    else int(previous.get("consecutive_failures", 0)) + 1,
                    "positions": {s: str(q) for s, q in _held(after).items()},
                    "steps": {s: str(steps[s]) for s in _held(after)},
                    "last_decision": signal["decision_day"]
                    if signal
                    else previous.get("last_decision"),
                }
            )
            report.update(
                status="ok" if ok else "mismatch",
                run=run,
                signal=signal,
                skipped=skipped,
                results=results,
                positions={
                    s: {"qty": str(p["qty"]), "unrealized": str(p["unrealized"])}
                    for s, p in after.items()
                    if p["qty"] != 0
                },
                equity={k: str(v) for k, v in equity.items()},
                changes=changes,
                mismatch=mismatch,
            )
        except Exception as exc:  # recorded; the guard handles prolonged failure
            previous = store.heartbeat() or {}
            if previous:
                previous["last_run"] = now.isoformat()
                previous["consecutive_failures"] = int(previous.get("consecutive_failures", 0)) + 1
                store.write_heartbeat(previous)
            store.journal({"event": "executor_error", "error": f"{type(exc).__name__}: {exc}"})
            report.update(status="error", error=f"{type(exc).__name__}: {exc}")
    store.save_report(f"executor-{day}.json", report)
    store.save_report("executor-latest.json", report)
    return report


def lot_steps(client: FuturesClient, symbols) -> dict[str, Decimal]:
    """Lot step per symbol (the allowlist is widened to cover them)."""
    symbols = set(symbols)
    if not symbols:
        return {}
    client.allow(symbols)
    found = client.filters()
    return {s: found[s]["step"] if s in found else Decimal(0) for s in symbols}


def flatten_all(
    client: FuturesClient, store: StateStore, config: LiveConfig, reason: str
) -> list[dict[str, Any]]:
    now = pd.Timestamp.now(tz="UTC")
    day = now.strftime("%Y%m%d")
    run = store.next_run_index(f"guard-{day}")
    positions = client.positions(every_symbol=True)
    held = _held(positions)
    client.allow(held)
    filters = client.filters()
    results = []
    for symbol in held:
        try:
            client.cancel_all(symbol)
        except ExchangeError as exc:
            store.journal({"event": "cancel_error", "symbol": symbol, "message": str(exc)})
    for index, (symbol, qty) in enumerate(sorted(held.items())):
        step = Step(symbol, "SELL" if qty > 0 else "BUY", abs(qty), True, "close")
        outcome = execute_step(
            client, store, config, step, filters[symbol], day=day, run=run, index=index,
            cap_bps=GUARD_PRICE_CAP_BPS, attempts=GUARD_IOC_ATTEMPTS, role="g",
            make_id=_make_id(config, "g", day, run, index),
        )  # fmt: skip
        left = client.positions(every_symbol=True).get(symbol, {"qty": Decimal(0)})["qty"]
        if left != 0:
            market_id = _make_id(config, "m", day, run, index)(symbol, 9)
            try:
                res = client.place_reduce_only_market(
                    symbol, "SELL" if left > 0 else "BUY", abs(left), market_id
                )
                outcome["market_fallback"] = {"executed": res.get("executedQty")}
            except ExchangeError as exc:
                outcome["market_fallback"] = {"error": str(exc)}
        results.append(outcome)
    store.journal({"event": "flatten", "reason": reason, "results": results})
    return results


def run_guard(
    client: FuturesClient,
    store: StateStore,
    *,
    now: pd.Timestamp,
    test_stop_equity: Decimal | None = None,
) -> dict[str, Any]:
    config = store.config()
    if test_stop_equity is not None and config.environment != "demo":
        raise PermissionError("test stop levels are a Demo verification tool only")
    report: dict[str, Any] = {"kind": "guard", "now": now.isoformat()}
    with state_lock(store.root, wait=False) as free:
        if not free:
            report["status"] = "busy"  # the executor is rebalancing; the next run checks
            store.save_report("guard-latest.json", report)
            return report
        positions = client.positions(every_symbol=True)
        held = _held(positions)
        report["positions"] = {s: str(q) for s, q in held.items()}
        halt = store.halt()
        if halt is not None:
            report["status"] = "halted"
            if held:
                report["flatten"] = flatten_all(client, store, config, "halted_with_positions")
                report["status"] = "halted_flattened"
            store.save_report("guard-latest.json", report)
            return report
        equity = strategy_equity(client, config, positions, every_symbol=True)
        stop = test_stop_equity if test_stop_equity is not None else config.stop_equity
        reasons = []
        if equity["equity"] <= stop:
            reasons.append("loss_stop")
        heartbeat = store.heartbeat()
        if heartbeat is None:
            if held:
                reasons.append("positions_without_executor_record")
        else:
            last = heartbeat.get("last_success")
            if held and (
                last is None or now - pd.Timestamp(last) > pd.Timedelta(hours=config.stale_hours)
            ):
                reasons.append("executor_stale")
            recorded = {s: Decimal(q) for s, q in heartbeat.get("positions", {}).items()}
            steps = {s: Decimal(q) for s, q in heartbeat.get("steps", {}).items()}
            for symbol in sorted(set(recorded) | set(held)):
                actual = held.get(symbol, Decimal(0))
                if abs(actual - recorded.get(symbol, Decimal(0))) > steps.get(symbol, Decimal(0)):
                    reasons.append(f"position_mismatch_{symbol}")
        report["equity"] = {k: str(v) for k, v in equity.items()}
        report["stop_used"] = str(stop)
        if reasons:
            store.set_halt(reasons, {"equity": str(equity["equity"]), "stop": str(stop)})
            report["flatten"] = flatten_all(client, store, config, ",".join(reasons))
            report["status"] = "triggered"
            report["reasons"] = reasons
        else:
            report["status"] = "ok"
    store.save_report("guard-latest.json", report)
    return report
