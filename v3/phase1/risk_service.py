"""Fail-closed subprocess wrapper around the Phase 1 risk decision."""

from __future__ import annotations

import hashlib
import json
import multiprocessing as mp
import queue
import threading
import time
import uuid
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .fee_input import policy_with_fee_snapshot
from .policy import load_phase1_policy
from .risk import CarryRiskContext, RiskDecision, evaluate_carry_risk


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class RiskServiceUnavailable(RuntimeError):
    pass


class Phase1RiskService:
    """Small RPC client; every service error becomes an explicit denial."""

    def __init__(
        self,
        *,
        policy_path: Path,
        fee_snapshot_path: Path | None = None,
        timeout_seconds: float = 1.0,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self.policy_path = policy_path
        self.fee_snapshot_path = fee_snapshot_path
        self.timeout_seconds = timeout_seconds
        self.policy_hash = file_sha256(policy_path)
        self.fee_snapshot_hash = file_sha256(fee_snapshot_path) if fee_snapshot_path else None
        self._closed = False
        self._lock = threading.Lock()
        spawn = mp.get_context("spawn")
        self._requests = spawn.Queue(maxsize=2)
        self._responses = spawn.Queue(maxsize=2)
        self._process = spawn.Process(
            target=_risk_worker,
            args=(str(policy_path), str(fee_snapshot_path) if fee_snapshot_path else None),
            kwargs={"requests": self._requests, "responses": self._responses},
            daemon=True,
        )
        self._process.start()

    def evaluate(self, context: CarryRiskContext) -> RiskDecision:
        with self._lock:
            try:
                return self._evaluate(context)
            except (OSError, ValueError, KeyError, TypeError, queue.Full):
                return _deny(context, "risk service communication or response invalid")

    def _evaluate(self, context: CarryRiskContext) -> RiskDecision:
        if self._closed or not self._process.is_alive():
            return _deny(context, "risk service is unavailable")
        request_id = str(uuid.uuid4())
        payload = _context_to_payload(context)
        request_hash = _stable_hash(payload)
        self._requests.put_nowait(
            {
                "type": "evaluate",
                "request_id": request_id,
                "policy_hash": self.policy_hash,
                "fee_snapshot_hash": self.fee_snapshot_hash,
                "request_hash": request_hash,
                "context": payload,
            }
        )
        started = time.monotonic()
        while time.monotonic() - started <= self.timeout_seconds:
            if not self._process.is_alive():
                return _deny(context, "risk service process exited")
            try:
                response = self._responses.get(timeout=0.02)
            except queue.Empty:
                continue
            if not isinstance(response, dict) or response.get("request_id") != request_id:
                return _deny(context, "risk service returned an unmatched response")
            return _decision_from_response(
                response,
                context=context,
                expected_policy_hash=self.policy_hash,
                expected_fee_snapshot_hash=self.fee_snapshot_hash,
                expected_request_hash=request_hash,
            )
        return _deny(context, "risk service timed out")

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._process.is_alive():
            try:
                self._requests.put_nowait({"type": "shutdown"})
            except queue.Full:
                pass
            self._process.join(timeout=0.5)
        if self._process.is_alive():
            self._process.terminate()
            self._process.join(timeout=0.5)
        for channel in (self._requests, self._responses):
            channel.cancel_join_thread()
            channel.close()

    def __enter__(self) -> Phase1RiskService:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()


def evaluate_with_subprocess(
    context: CarryRiskContext,
    *,
    policy_path: Path,
    fee_snapshot_path: Path | None = None,
    timeout_seconds: float = 1.0,
) -> RiskDecision:
    with Phase1RiskService(
        policy_path=policy_path,
        fee_snapshot_path=fee_snapshot_path,
        timeout_seconds=timeout_seconds,
    ) as service:
        return service.evaluate(context)


def _risk_worker(
    policy_path: str,
    fee_snapshot_path: str | None,
    *,
    requests: mp.Queue[dict[str, Any]],
    responses: mp.Queue[dict[str, Any]],
) -> None:
    try:
        policy_file = Path(policy_path)
        fee_file = Path(fee_snapshot_path) if fee_snapshot_path is not None else None
        policy_hash = file_sha256(policy_file)
        fee_snapshot_hash = file_sha256(fee_file) if fee_file else None
        policy = policy_with_fee_snapshot(load_phase1_policy(policy_file), fee_file)
    except Exception as exc:  # noqa: BLE001 - subprocess reports denial, not traceback.
        policy_hash = ""
        fee_snapshot_hash = None
        policy = None
        startup_error = f"risk service startup failed: {type(exc).__name__}"
    else:
        startup_error = None

    while True:
        message = requests.get()
        if not isinstance(message, dict):
            continue
        if message.get("type") == "shutdown":
            return
        request_id = message.get("request_id")
        context_payload = message.get("context")
        request_hash = message.get("request_hash")
        try:
            if startup_error is not None or policy is None:
                raise RiskServiceUnavailable(startup_error or "risk service unavailable")
            if message.get("policy_hash") != policy_hash:
                raise RiskServiceUnavailable("risk service policy hash mismatch")
            if message.get("fee_snapshot_hash") != fee_snapshot_hash:
                raise RiskServiceUnavailable("risk service fee snapshot hash mismatch")
            if _stable_hash(context_payload) != request_hash:
                raise RiskServiceUnavailable("risk service request hash mismatch")
            context = _context_from_payload(context_payload)
            evaluated_at = datetime.now(UTC)
            elapsed_ms = int((evaluated_at - context.evaluated_at).total_seconds() * 1000)
            if not 0 <= elapsed_ms <= 5000:
                raise RiskServiceUnavailable("risk observation is stale or from the future")
            context = replace(
                context,
                evaluated_at=evaluated_at,
                quote_age_ms=context.quote_age_ms + elapsed_ms
                if context.quote_age_ms is not None
                else None,
            )
            decision = evaluate_carry_risk(context, policy)
            responses.put(
                {
                    "schema_version": 1,
                    "request_id": request_id,
                    "policy_hash": policy_hash,
                    "fee_snapshot_hash": fee_snapshot_hash,
                    "request_hash": request_hash,
                    "decision": decision.to_dict(),
                }
            )
        except Exception as exc:  # noqa: BLE001 - fail closed for malformed requests.
            evaluated_at = datetime.now().astimezone()
            responses.put(
                {
                    "schema_version": 1,
                    "request_id": request_id,
                    "policy_hash": policy_hash,
                    "fee_snapshot_hash": fee_snapshot_hash,
                    "request_hash": request_hash,
                    "decision": {
                        "schema_version": 1,
                        "approved": False,
                        "reasons": [f"risk service denied request: {type(exc).__name__}"],
                        "observed_leverage": {},
                        "quote_age_ms": None,
                        "evaluated_at": evaluated_at.isoformat(),
                    },
                }
            )


def _context_to_payload(context: CarryRiskContext) -> dict[str, Any]:
    return {
        "intent_fields": dict(context.intent_fields),
        "cost_ledger_complete": context.cost_ledger_complete,
        "leverage_by_instrument": {
            key: str(value) for key, value in context.leverage_by_instrument.items()
        },
        "quote_age_ms": context.quote_age_ms,
        "leg_notional": str(context.leg_notional),
        "minimum_notional_by_instrument": {
            key: str(value) for key, value in context.minimum_notional_by_instrument.items()
        },
        "local_positions_match_venue": context.local_positions_match_venue,
        "unexplained_residual_usdt": str(context.unexplained_residual_usdt),
        "residual_unclassified_hours": str(context.residual_unclassified_hours),
        "daily_loss_usdt": str(context.daily_loss_usdt),
        "monthly_abort_cost_usdt": str(context.monthly_abort_cost_usdt),
        "abort_attempts_this_month": context.abort_attempts_this_month,
        "consecutive_aborts": context.consecutive_aborts,
        "idempotency_key_is_new": context.idempotency_key_is_new,
        "environment": context.environment,
        "live_orders": context.live_orders,
        "real_capital": context.real_capital,
        "evaluated_at": context.evaluated_at.isoformat(),
    }


def _context_from_payload(payload: Any) -> CarryRiskContext:
    if not isinstance(payload, dict):
        raise ValueError("context payload must be an object")
    data = dict(payload)
    for name in (
        "cost_ledger_complete",
        "local_positions_match_venue",
        "idempotency_key_is_new",
        "live_orders",
        "real_capital",
    ):
        if type(data.get(name)) is not bool:
            raise ValueError("risk flags must be booleans")
    data["evaluated_at"] = datetime.fromisoformat(str(data["evaluated_at"]))
    return CarryRiskContext(**data)


def _decision_from_response(
    response: dict[str, Any],
    *,
    context: CarryRiskContext,
    expected_policy_hash: str,
    expected_fee_snapshot_hash: str | None,
    expected_request_hash: str,
) -> RiskDecision:
    if response.get("policy_hash") != expected_policy_hash:
        return _deny(context, "risk service response policy hash mismatch")
    if response.get("fee_snapshot_hash") != expected_fee_snapshot_hash:
        return _deny(context, "risk service response fee snapshot hash mismatch")
    if response.get("request_hash") != expected_request_hash:
        return _deny(context, "risk service response request hash mismatch")
    decision = response.get("decision")
    if not isinstance(decision, dict) or decision.get("schema_version") != 1:
        return _deny(context, "risk service response is malformed")
    reasons = decision.get("reasons")
    observed = decision.get("observed_leverage")
    approved = decision.get("approved")
    if (
        type(approved) is not bool
        or not isinstance(reasons, list)
        or not isinstance(observed, dict)
    ):
        return _deny(context, "risk service decision payload is malformed")
    if not all(isinstance(reason, str) for reason in reasons) or (approved and reasons):
        return _deny(context, "risk service decision is inconsistent")
    if not approved and not reasons:
        return _deny(context, "risk service denial has no reason")
    evaluated_at = datetime.fromisoformat(str(decision["evaluated_at"]))
    if evaluated_at.tzinfo is None or abs((datetime.now(UTC) - evaluated_at).total_seconds()) > 5:
        return _deny(context, "risk service decision time is invalid")
    age = decision.get("quote_age_ms")
    if age is not None and (type(age) is not int or age < 0):
        return _deny(context, "risk service quote age is invalid")
    return RiskDecision(
        approved=approved,
        reasons=tuple(str(reason) for reason in reasons),
        observed_leverage={str(key): str(value) for key, value in observed.items()},
        quote_age_ms=decision.get("quote_age_ms"),
        evaluated_at=evaluated_at,
    )


def _stable_hash(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


def _deny(context: CarryRiskContext, reason: str) -> RiskDecision:
    return RiskDecision(
        approved=False,
        reasons=(reason,),
        observed_leverage={},
        quote_age_ms=context.quote_age_ms,
        evaluated_at=context.evaluated_at,
    )
