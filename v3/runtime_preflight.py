"""Fail-closed checks for the retained Freqtrade shadow runtime."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

PINNED_IMAGE = re.compile(r"^[^@]+@sha256:[0-9a-f]{64}$")


@dataclass(frozen=True)
class RuntimeCheck:
    code: str
    passed: bool
    detail: str

    def to_dict(self) -> dict[str, str | bool]:
        return {"code": self.code, "passed": self.passed, "detail": self.detail}


@dataclass(frozen=True)
class RuntimePreflightResult:
    checks: tuple[RuntimeCheck, ...]

    @property
    def passed(self) -> bool:
        return all(check.passed for check in self.checks)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "passed": self.passed,
            "checks": [check.to_dict() for check in self.checks],
        }


def validate_shadow_runtime(
    config: dict[str, Any],
    compose: dict[str, Any],
) -> RuntimePreflightResult:
    checks: list[RuntimeCheck] = []

    def add(code: str, passed: bool, detail: str) -> None:
        checks.append(RuntimeCheck(code, passed, detail))

    add("dry_run", config.get("dry_run") is True, "dry_run must be true")
    add(
        "force_entry",
        config.get("force_entry_enable") is False,
        "force_entry_enable must be false",
    )
    add(
        "capital",
        config.get("dry_run_wallet") == 1000 and config.get("stake_amount") == 50,
        "dry_run_wallet must be 1000 and stake_amount must be 50",
    )
    add(
        "market_mode",
        config.get("trading_mode") == "futures" and config.get("margin_mode") == "isolated",
        "trading_mode must be futures with isolated margin",
    )
    services = compose.get("services", {}) if isinstance(compose, dict) else {}
    service = services.get("freqtrade_v3_shadow", {}) if isinstance(services, dict) else {}
    image = service.get("image", "") if isinstance(service, dict) else ""
    command = service.get("command", "") if isinstance(service, dict) else ""
    add("single_service", set(services) == {"freqtrade_v3_shadow"}, "unexpected service found")
    add("image_digest", bool(PINNED_IMAGE.fullmatch(image)), "image must use a sha256 digest")
    add(
        "isolated_database",
        "tradesv3_v3.sqlite" in command
        and "tradesv3.sqlite" not in command.replace("tradesv3_v3.sqlite", ""),
        "command must use only the V3 shadow database",
    )
    add(
        "isolated_config",
        "/freqtrade/configs/dry-run.json" in command,
        "command must use the V3 dry-run config",
    )
    add(
        "strategy_argument",
        "--strategy V3ShadowStrategy" in command and "${FREQTRADE_STRATEGY}" not in command,
        "compose must hard-code the fail-closed V3ShadowStrategy",
    )
    return RuntimePreflightResult(tuple(checks))


def load_and_validate(config_path: Path, compose_path: Path) -> RuntimePreflightResult:
    import json

    config = json.loads(config_path.read_text())
    compose = yaml.safe_load(compose_path.read_text())
    return validate_shadow_runtime(config, compose)
