"""MA200 daily executor and automatic guard (Decision 0020).

The executor runs once a day after 01:00 UTC. It computes the fixed MA200
target from Mainnet public daily closes, plans orders from the actual
positions, sends IOC limit orders with a price cap, and records everything.

The guard runs every few minutes. It closes everything reduce-only and halts
when the loss stop is reached, when the executor has not succeeded for too
long, or when positions differ from the executor's record. While halted, the
executor never trades. Only an explicit clear lifts the halt.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pandas as pd

from v3.phase2c.trend import REBALANCE_THRESHOLD, VOL_TARGET, TrendRule, weights_from_daily

from .client import SYMBOLS, ExchangeError, FuturesClient, ceil_to, floor_to

ASSET = {"BTCUSDT": "BTC", "ETHUSDT": "ETH"}
GUARD_PRICE_CAP_BPS = Decimal(50)
GUARD_IOC_ATTEMPTS = 5
UNKNOWN_QUERIES = 3


@dataclass(frozen=True)
class LiveConfig:
    environment: str
    start_ms: int
    starting_capital: Decimal = Decimal(1000)
    sleeve: Decimal = Decimal(1000)
    vol_target: float = VOL_TARGET
    stop_equity: Decimal = Decimal(900)
    stale_hours: float = 50.0
    price_cap_bps: Decimal = Decimal(10)
    attempts: int = 3

    @property
    def cap(self) -> Decimal:
        return self.sleeve / len(SYMBOLS)

    @property
    def threshold(self) -> float:
        return REBALANCE_THRESHOLD * self.vol_target / VOL_TARGET

    def to_json(self) -> dict[str, Any]:
        return {k: (str(v) if isinstance(v, Decimal) else v) for k, v in asdict(self).items()}

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> LiveConfig:
        decimals = {"starting_capital", "sleeve", "stop_equity", "price_cap_bps"}
        return cls(**{k: (Decimal(v) if k in decimals else v) for k, v in data.items()})


class StateStore:
    """Files under one directory: config, heartbeat, halt marker, journal, reports."""

    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, name: str) -> Path:
        return self.root / name

    def _write(self, name: str, data: Any) -> None:
        tmp = self._path(f".{name}.tmp")
        tmp.write_text(json.dumps(data, indent=2, sort_keys=True, default=str) + "\n")
        tmp.replace(self._path(name))

    def _read(self, name: str) -> Any:
        path = self._path(name)
        return json.loads(path.read_text()) if path.is_file() else None

    def config(self) -> LiveConfig:
        data = self._read("config.json")
        if data is None:
            raise FileNotFoundError("live state is not initialized (run init)")
        return LiveConfig.from_json(data)

    def init(self, config: LiveConfig) -> None:
        if self._path("config.json").exists():
            raise FileExistsError("live state already initialized")
        self._write("config.json", config.to_json())

    def heartbeat(self) -> dict[str, Any] | None:
        return self._read("heartbeat.json")

    def write_heartbeat(self, data: dict[str, Any]) -> None:
        self._write("heartbeat.json", data)

    def halt(self) -> dict[str, Any] | None:
        return self._read("halt.json")

    def set_halt(self, reasons: list[str], detail: dict[str, Any]) -> None:
        if self.halt() is None:
            self._write("halt.json", {"at": _now_iso(), "reasons": reasons, "detail": detail})

    def clear_halt(self, note: str, positions: dict[str, str]) -> dict[str, Any] | None:
        """Lift a halt after review and record the actual positions as the new baseline."""
        previous = self.halt()
        if previous is not None:
            self.journal(
                {
                    "event": "halt_cleared",
                    "previous": previous,
                    "note": note,
                    "positions": positions,
                }
            )
            self._path("halt.json").unlink()
            heartbeat = self.heartbeat()
            if heartbeat is not None:
                heartbeat["positions"] = positions
                self.write_heartbeat(heartbeat)
        return previous

    def journal(self, record: dict[str, Any]) -> None:
        record = {"at": _now_iso(), **record}
        with self._path("journal.jsonl").open("a") as handle:
            handle.write(json.dumps(record, sort_keys=True, default=str) + "\n")

    def next_run_index(self, day: str) -> int:
        runs = self._read("runs.json") or {}
        runs[day] = int(runs.get(day, -1)) + 1
        self._write("runs.json", runs)
        return runs[day]

    def save_report(self, name: str, data: dict[str, Any]) -> None:
        self._write(name, data)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


# --------------------------------------------------------------------- signal
def daily_closes(client: FuturesClient, now: pd.Timestamp) -> pd.DataFrame:
    """Completed Mainnet daily closes indexed at the 00:00 decision that can use them."""
    columns = {}
    now_ms = int(now.timestamp() * 1000)
    for symbol in SYMBOLS:
        rows = client.public_daily_klines(symbol)
        series = {
            pd.Timestamp(int(r[0]), unit="ms", tz="UTC") + pd.Timedelta(days=1): float(r[4])
            for r in rows
            if int(r[6]) < now_ms
        }
        columns[ASSET[symbol]] = pd.Series(series)
    return pd.DataFrame(columns).sort_index().dropna()


def live_signal(client: FuturesClient, config: LiveConfig, now: pd.Timestamp) -> dict[str, Any]:
    decision = now.floor("D")
    closes = daily_closes(client, now)
    weights = weights_from_daily(closes, TrendRule("ma200", vol_target=config.vol_target))
    if decision not in weights.index or weights.loc[decision].isna().any():
        raise RuntimeError(f"no complete MA200 signal for {decision.isoformat()}")
    average = closes.rolling(200, min_periods=200).mean().loc[decision]
    return {
        "decision_time": decision.isoformat(),
        "weights": {s: float(weights.loc[decision, ASSET[s]]) for s in SYMBOLS},
        "distance": {
            s: float(closes.loc[decision, ASSET[s]] / average[ASSET[s]] - 1) for s in SYMBOLS
        },
    }


# ------------------------------------------------------------------- planning
@dataclass
class Step:
    symbol: str
    side: str
    qty: Decimal
    reduce_only: bool
    purpose: str  # close | open | increase | reduce


@dataclass
class Plan:
    symbol: str
    current_qty: Decimal
    current_weight: float
    target_weight: float
    target_qty: Decimal
    steps: list[Step] = field(default_factory=list)
    skipped: str | None = None


def plan_symbol(
    symbol: str,
    current_qty: Decimal,
    target_weight: float,
    price: Decimal,
    config: LiveConfig,
    flt: dict[str, Decimal],
) -> Plan:
    cap = config.cap
    current_weight = float(current_qty * price / cap)
    raw_target = Decimal(str(target_weight)) * cap / price
    target_qty = floor_to(abs(raw_target), flt["step"]) * (1 if raw_target >= 0 else -1)
    plan = Plan(symbol, current_qty, current_weight, target_weight, target_qty)
    flip = current_qty != 0 and target_weight != 0 and (current_qty > 0) != (target_weight > 0)
    to_flat = target_weight == 0 and current_qty != 0
    if not (flip or to_flat or abs(target_weight - current_weight) >= config.threshold):
        return plan

    def opening_ok(qty: Decimal) -> bool:
        return qty >= flt["min_qty"] and qty * price >= flt["min_notional"]

    def side_for(delta: Decimal) -> str:
        return "BUY" if delta > 0 else "SELL"

    if flip or to_flat:
        plan.steps.append(Step(symbol, side_for(-current_qty), abs(current_qty), True, "close"))
        if flip and target_qty != 0:
            if opening_ok(abs(target_qty)):
                plan.steps.append(
                    Step(symbol, side_for(target_qty), abs(target_qty), False, "open")
                )
            else:
                plan.skipped = "open below minimum order"
        return plan
    delta = target_qty - current_qty
    if abs(delta) < flt["step"]:
        plan.skipped = "change below one lot"
        return plan
    if current_qty != 0 and abs(target_qty) < abs(current_qty):
        plan.steps.append(Step(symbol, side_for(delta), abs(delta), True, "reduce"))
    elif opening_ok(abs(delta)):
        purpose = "open" if current_qty == 0 else "increase"
        plan.steps.append(Step(symbol, side_for(delta), abs(delta), False, purpose))
    else:
        plan.skipped = "order below minimum notional"
    return plan


# ------------------------------------------------------------------ execution
def _client_id(
    config: LiveConfig, role: str, day: str, run: int, symbol: str, step: int, attempt: int
) -> str:
    """Deterministic per (role, day, run, symbol, step, attempt); role x=executor, g=guard."""
    env = "d" if config.environment == "demo" else "m"
    return f"ma{env}{role}{day[2:]}r{run}{symbol[:3]}s{step}a{attempt}"


def _limit_price(
    client: FuturesClient, symbol: str, side: str, cap_bps: Decimal, tick: Decimal
) -> Decimal:
    book = client.book(symbol)
    factor = cap_bps / Decimal(10_000)
    if side == "BUY":
        return ceil_to(book["ask"] * (1 + factor), tick)
    return floor_to(book["bid"] * (1 - factor), tick)


def _resolve_unknown(client: FuturesClient, symbol: str, client_id: str) -> dict[str, Any] | None:
    for _ in range(UNKNOWN_QUERIES):
        time.sleep(1.0)
        found = client.order_by_client_id(symbol, client_id)
        if found is not None:
            return found
    return None


def execute_step(
    client: FuturesClient,
    store: StateStore,
    config: LiveConfig,
    step: Step,
    flt: dict[str, Decimal],
    *,
    day: str,
    run: int,
    index: int,
    cap_bps: Decimal | None = None,
    attempts: int | None = None,
    role: str = "x",
) -> dict[str, Any]:
    remaining = step.qty
    filled = Decimal(0)
    notional = Decimal(0)
    orders = []
    price = Decimal(0)
    for attempt in range(attempts or config.attempts):
        client_id = _client_id(config, role, day, run, step.symbol, index, attempt)
        result = client.order_by_client_id(step.symbol, client_id)
        if result is None:
            price = _limit_price(
                client, step.symbol, step.side, cap_bps or config.price_cap_bps, flt["tick"]
            )
            store.journal(
                {
                    "event": "order_intent",
                    "client_id": client_id,
                    **_step_json(step),
                    "qty": str(remaining),
                    "price": str(price),
                }
            )
            try:
                result = client.place_ioc(
                    step.symbol,
                    step.side,
                    remaining,
                    price,
                    reduce_only=step.reduce_only,
                    client_id=client_id,
                )
            except ExchangeError as exc:
                if exc.status is None or exc.status >= 500:
                    result = _resolve_unknown(client, step.symbol, client_id)
                if result is None:
                    store.journal(
                        {
                            "event": "order_error",
                            "client_id": client_id,
                            "status": exc.status,
                            "code": exc.code,
                            "message": str(exc),
                        }
                    )
                    if exc.code == -2022:  # reduce-only rejected: nothing left to reduce
                        break
                    continue
        executed = Decimal(str(result.get("executedQty", "0")))
        avg = Decimal(str(result.get("avgPrice", "0") or "0"))
        if avg <= 0 and executed > 0:
            # The immediate reply can report avgPrice and cumQuote as 0 (seen on Demo);
            # the order query has the settled values.
            settled = client.order_by_client_id(step.symbol, client_id) or result
            executed = Decimal(str(settled.get("executedQty", executed)))
            avg = Decimal(str(settled.get("avgPrice", "0") or "0"))
            if avg <= 0:
                quote = Decimal(str(settled.get("cumQuote", "0") or "0"))
                avg = quote / executed if executed else Decimal(0)
            result = settled
        filled += executed
        notional += executed * avg
        remaining -= executed
        orders.append(
            {
                "client_id": client_id,
                "status": result.get("status"),
                "executed": str(executed),
                "avg_price": str(avg),
            }
        )
        store.journal(
            {
                "event": "order_result",
                "client_id": client_id,
                "symbol": step.symbol,
                "status": result.get("status"),
                "executed": str(executed),
                "avg_price": str(avg),
            }
        )
        if remaining < flt["step"]:
            break
        reference = avg if avg > 0 else price
        if not step.reduce_only and reference > 0 and remaining * reference < flt["min_notional"]:
            break
        remaining = floor_to(remaining, flt["step"])
    return {
        **_step_json(step),
        "filled": str(filled),
        "avg_price": str(notional / filled) if filled else None,
        "unfilled": str(max(remaining, Decimal(0))),
        "orders": orders,
    }


def _step_json(step: Step) -> dict[str, Any]:
    return {
        "symbol": step.symbol,
        "side": step.side,
        "step_qty": str(step.qty),
        "reduce_only": step.reduce_only,
        "purpose": step.purpose,
    }


# ------------------------------------------------------------------- equity
def strategy_equity(
    client: FuturesClient,
    config: LiveConfig,
    positions: dict[str, dict[str, Decimal]] | None = None,
) -> dict[str, Any]:
    positions = positions or client.positions()
    kinds = {"REALIZED_PNL": Decimal(0), "COMMISSION": Decimal(0), "FUNDING_FEE": Decimal(0)}
    for row in client.income(config.start_ms):
        kind = row.get("incomeType")
        if kind in kinds:
            kinds[kind] += Decimal(str(row["income"]))
    unrealized = sum((p["unrealized"] for p in positions.values()), Decimal(0))
    equity = config.starting_capital + sum(kinds.values(), Decimal(0)) + unrealized
    return {
        "equity": equity,
        "realized": kinds["REALIZED_PNL"],
        "commission": kinds["COMMISSION"],
        "funding": kinds["FUNDING_FEE"],
        "unrealized": unrealized,
        "stop_equity": config.stop_equity,
        "distance_to_stop": equity - config.stop_equity,
    }


# ------------------------------------------------------------------- executor
def run_executor(
    client: FuturesClient,
    store: StateStore,
    *,
    now: pd.Timestamp,
    override_weights: dict[str, float] | None = None,
) -> dict[str, Any]:
    config = store.config()
    if override_weights and config.environment != "demo":
        raise PermissionError("weight overrides are a Demo verification tool only")
    day = now.strftime("%Y%m%d")
    report: dict[str, Any] = {
        "kind": "executor",
        "now": now.isoformat(),
        "environment": config.environment,
    }
    halt = store.halt()
    if halt is not None:
        report.update(status="halted", halt=halt)
        store.save_report(f"executor-{day}.json", report)
        return report
    run = store.next_run_index(day)
    try:
        for symbol in SYMBOLS:
            client.ensure_isolated_2x(symbol)
        filters = client.filters()
        signal = live_signal(client, config, now)
        weights = dict(signal["weights"])
        if override_weights:
            weights.update(override_weights)
            report["override_weights"] = override_weights
        positions = client.positions()
        for symbol in SYMBOLS:
            if client.open_orders(symbol):
                raise RuntimeError(f"unexpected open orders on {symbol}")
        plans, results = [], []
        for symbol in SYMBOLS:
            book = client.book(symbol)
            mid = (book["bid"] + book["ask"]) / 2
            plan = plan_symbol(
                symbol, positions[symbol]["qty"], weights[symbol], mid, config, filters[symbol]
            )
            plans.append(plan)
            for index, step in enumerate(plan.steps):
                results.append(
                    execute_step(
                        client, store, config, step, filters[symbol], day=day, run=run, index=index
                    )
                )
        after = client.positions()
        mismatch = {}
        for plan in plans:
            if not plan.steps:
                continue
            gap = abs(after[plan.symbol]["qty"] - plan.target_qty)
            if gap > filters[plan.symbol]["step"] and plan.skipped is None:
                mismatch[plan.symbol] = str(gap)
        equity = strategy_equity(client, config, after)
        ok = not mismatch
        previous = store.heartbeat() or {}
        store.write_heartbeat(
            {
                "last_run": now.isoformat(),
                "last_success": now.isoformat() if ok else previous.get("last_success"),
                "consecutive_failures": 0
                if ok
                else int(previous.get("consecutive_failures", 0)) + 1,
                "positions": {s: str(after[s]["qty"]) for s in SYMBOLS},
                "steps": {s: str(filters[s]["step"]) for s in SYMBOLS},
                "decision_time": signal["decision_time"],
            }
        )
        report.update(
            status="ok" if ok else "mismatch",
            run=run,
            signal=signal,
            weights_used=weights,
            plans=[
                {
                    "symbol": p.symbol,
                    "current_qty": str(p.current_qty),
                    "current_weight": p.current_weight,
                    "target_weight": p.target_weight,
                    "target_qty": str(p.target_qty),
                    "steps": len(p.steps),
                    "skipped": p.skipped,
                }
                for p in plans
            ],
            results=results,
            positions={
                s: {"qty": str(after[s]["qty"]), "unrealized": str(after[s]["unrealized"])}
                for s in SYMBOLS
            },
            equity={k: str(v) for k, v in equity.items()},
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


# ---------------------------------------------------------------------- guard
def flatten_all(
    client: FuturesClient, store: StateStore, config: LiveConfig, reason: str
) -> list[dict[str, Any]]:
    filters = client.filters()
    day = datetime.now(UTC).strftime("%Y%m%d")
    run = store.next_run_index(f"guard-{day}")
    results = []
    for symbol in SYMBOLS:
        try:
            client.cancel_all(symbol)
        except ExchangeError as exc:
            store.journal({"event": "cancel_error", "symbol": symbol, "message": str(exc)})
    positions = client.positions()
    for symbol in SYMBOLS:
        qty = positions[symbol]["qty"]
        if qty == 0:
            continue
        step = Step(symbol, "SELL" if qty > 0 else "BUY", abs(qty), True, "close")
        outcome = execute_step(
            client,
            store,
            config,
            step,
            filters[symbol],
            day=day,
            run=run,
            index=0,
            cap_bps=GUARD_PRICE_CAP_BPS,
            attempts=GUARD_IOC_ATTEMPTS,
            role="g",
        )
        left = client.positions()[symbol]["qty"]
        if left != 0:
            market_id = _client_id(config, "g", day, run, symbol, 9, 9)
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
    positions = client.positions()
    held = {s: p["qty"] for s, p in positions.items() if p["qty"] != 0}
    report: dict[str, Any] = {
        "kind": "guard",
        "now": now.isoformat(),
        "positions": {s: str(q) for s, q in held.items()},
    }
    halt = store.halt()
    if halt is not None:
        report["status"] = "halted"
        if held:
            report["flatten"] = flatten_all(client, store, config, "halted_with_positions")
            report["status"] = "halted_flattened"
        store.save_report("guard-latest.json", report)
        return report
    equity = strategy_equity(client, config, positions)
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
        recorded = {s: Decimal(heartbeat.get("positions", {}).get(s, "0")) for s in SYMBOLS}
        steps = {s: Decimal(heartbeat.get("steps", {}).get(s, "0")) for s in SYMBOLS}
        for symbol in SYMBOLS:
            if abs(positions[symbol]["qty"] - recorded[symbol]) > steps[symbol]:
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
