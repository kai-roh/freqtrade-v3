"""Fail-closed admission checks for the Phase 1 execution process."""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from v3.costs import DecimalInput, as_decimal

from .policy import Phase1Policy

SHA256 = re.compile(r"^[0-9a-f]{64}$")
IMAGE_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")


@dataclass(frozen=True)
class ExecutionRuntimeFacts:
    git_sha: str
    source_dirty: bool
    image_digest: str
    dependency_lock_sha256: str
    environment: str
    live_orders: bool
    real_capital: bool
    spot_client_id: str
    perp_client_id: str
    instruments: frozenset[str]
    leverage_by_instrument: dict[str, DecimalInput]
    order_submission_enabled: bool = False


@dataclass(frozen=True)
class ExecutionRuntimeCheck:
    code: str
    passed: bool
    detail: str

    def to_dict(self) -> dict[str, str | bool]:
        return {"code": self.code, "passed": self.passed, "detail": self.detail}


@dataclass(frozen=True)
class ExecutionRuntimeResult:
    checks: tuple[ExecutionRuntimeCheck, ...]

    @property
    def passed(self) -> bool:
        return all(check.passed for check in self.checks)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "passed": self.passed,
            "checks": [check.to_dict() for check in self.checks],
        }


def validate_execution_runtime(
    facts: ExecutionRuntimeFacts,
    policy: Phase1Policy,
) -> ExecutionRuntimeResult:
    checks: list[ExecutionRuntimeCheck] = []

    def add(code: str, passed: bool, detail: str) -> None:
        checks.append(ExecutionRuntimeCheck(code, passed, detail))

    add("git_sha", bool(re.fullmatch(r"[0-9a-f]{40,64}", facts.git_sha)), "Git SHA is required")
    add("clean_tree", not facts.source_dirty, "working tree must be clean")
    add(
        "image_digest",
        bool(IMAGE_DIGEST.fullmatch(facts.image_digest)),
        "execution image digest must be pinned",
    )
    add(
        "dependency_lock",
        bool(SHA256.fullmatch(facts.dependency_lock_sha256)),
        "dependency lock SHA-256 is required",
    )
    add(
        "environment",
        facts.environment == policy.environment == "demo",
        "Phase 1 execution environment must be Demo",
    )
    add(
        "authorization",
        not facts.live_orders
        and not facts.real_capital
        and not policy.live_orders
        and not policy.real_capital,
        "live orders and real capital must remain disabled",
    )
    add(
        "submission_mode",
        not facts.order_submission_enabled,
        "Phase 1A smoke must remain order-free",
    )
    add(
        "client_identity",
        bool(facts.spot_client_id.strip())
        and bool(facts.perp_client_id.strip())
        and facts.spot_client_id != facts.perp_client_id,
        "Spot and USD-M clients need distinct non-empty IDs",
    )
    add(
        "instruments",
        facts.instruments == policy.allowed_instruments,
        "runtime instruments must exactly match policy",
    )

    leverages: dict[str, Decimal] = {}
    invalid_leverage = False
    for instrument in policy.allowed_instruments:
        raw = facts.leverage_by_instrument.get(instrument)
        if raw is None:
            invalid_leverage = True
            continue
        try:
            leverage = as_decimal(raw, field_name=f"leverage[{instrument}]")
        except (TypeError, ValueError):
            invalid_leverage = True
            continue
        leverages[instrument] = leverage
        if leverage <= 0 or leverage > policy.maximum_leverage:
            invalid_leverage = True
    add(
        "leverage",
        not invalid_leverage and set(leverages) == policy.allowed_instruments,
        "all instrument leverage values must be known, positive, and at most 2x",
    )
    return ExecutionRuntimeResult(tuple(checks))
