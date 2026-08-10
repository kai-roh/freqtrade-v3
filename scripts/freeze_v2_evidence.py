#!/usr/bin/env python3
"""Freeze non-secret V2 baseline evidence for the V3 migration."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import sqlite3
import subprocess
from pathlib import Path
from typing import Any

DEFAULT_SOURCE_REPO = Path("/Users/seop/freqtrade-v2")
DEFAULT_REMOTE_HOST = "ft-tokyo"
DEFAULT_REMOTE_PATH = Path("/home/kai/freqtrade-v2")
DEFAULT_OUTPUT_DIR = Path("evidence/v2-baseline")

SAFE_CONFIG_SPEC: dict[str, Any] = {
    "max_open_trades": True,
    "stake_currency": True,
    "stake_amount": True,
    "tradable_balance_ratio": True,
    "fiat_display_currency": True,
    "timeframe": True,
    "dry_run": True,
    "dry_run_wallet": True,
    "cancel_open_orders_on_exit": True,
    "trading_mode": True,
    "margin_mode": True,
    "amend_last_stake_amount": True,
    "process_only_new_candles": True,
    "fee": True,
    "unfilledtimeout": True,
    "entry_pricing": True,
    "exit_pricing": True,
    "order_types": True,
    "order_time_in_force": True,
    "exchange": {
        "name": True,
        "pair_whitelist": True,
        "pair_blacklist": True,
    },
    "pairlists": True,
    "freqai": True,
    "telegram": {
        "enabled": True,
        "notification_settings": True,
        "balance_dust_level": True,
        "reload": True,
    },
    "api_server": {
        "enabled": True,
        "listen_port": True,
        "verbosity": True,
        "enable_openapi": True,
        "CORS_origins": True,
    },
    "bot_name": True,
    "initial_state": True,
    "force_entry_enable": True,
    "internals": True,
}

SECRET_WORDS = (
    "secret",
    "token",
    "password",
    "api_key",
    "apikey",
    "key",
    "chat_id",
    "jwt",
)

SELECTED_HASH_GLOBS = (
    "README.md",
    "docker-compose.yml",
    "pyproject.toml",
    "pytest.ini",
    "requirements*.txt",
    "docs/*.md",
    "scripts/*.py",
    "scripts/*.sh",
    "tests/*.py",
    "user_data/config.json",
    "user_data/evaluation_phase.json",
    "user_data/freqaimodels/*.py",
    "user_data/llm/*.py",
    "user_data/strategies/*.py",
)

PREDICTION_GLOBS = (
    "user_data/models/**/historic_predictions*.pkl",
    "user_data/models/**/historic_predictions*.parquet",
    "user_data/models/**/historic_predictions*.feather",
    "user_data/models/**/historic_predictions*.json",
)


def utc_now_iso() -> str:
    return dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def run_command(args: list[str], cwd: Path | None = None, timeout: int = 20) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            args,
            cwd=cwd,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except Exception as exc:  # pragma: no cover - exact exception type is platform dependent.
        return {"ok": False, "command": args, "error": str(exc), "stdout": "", "stderr": ""}
    return {
        "ok": completed.returncode == 0,
        "command": args,
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def text_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_json(path: Path, gaps: list[str]) -> Any | None:
    if not path.exists():
        gaps.append(f"missing_file:{path}")
        return None
    try:
        return json.loads(path.read_text())
    except Exception as exc:
        gaps.append(f"invalid_json:{path}:{exc}")
        return None


def filter_config(value: Any, spec: Any) -> Any:
    if spec is True:
        return redact_secret_keys(value)
    if isinstance(value, dict) and isinstance(spec, dict):
        return {
            key: filter_config(value[key], child_spec)
            for key, child_spec in sorted(spec.items())
            if key in value and not looks_secret(key)
        }
    return None


def looks_secret(key: str) -> bool:
    normalized = key.lower().replace("-", "_")
    return any(word in normalized for word in SECRET_WORDS)


def redact_secret_keys(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: ("<redacted>" if looks_secret(key) else redact_secret_keys(child))
            for key, child in sorted(value.items())
        }
    if isinstance(value, list):
        return [redact_secret_keys(item) for item in value]
    return value


def assert_no_secret_keys(value: Any, path: str = "") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            current = f"{path}.{key}" if path else key
            if looks_secret(key):
                raise ValueError(f"unsafe config key leaked into baseline: {current}")
            assert_no_secret_keys(child, current)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            assert_no_secret_keys(item, f"{path}[{index}]")


def collect_git(repo: Path) -> dict[str, Any]:
    sha = run_command(["git", "rev-parse", "HEAD"], cwd=repo)
    branch = run_command(["git", "branch", "--show-current"], cwd=repo)
    status = run_command(["git", "status", "--short", "--untracked-files=all"], cwd=repo)
    return {
        "path": str(repo),
        "sha": sha["stdout"].strip() if sha["ok"] else None,
        "branch": branch["stdout"].strip() if branch["ok"] else None,
        "status_short": sorted(line for line in status["stdout"].splitlines() if line.strip())
        if status["ok"]
        else [],
        "is_dirty": bool(status["stdout"].strip()) if status["ok"] else None,
        "gaps": [
            label
            for label, result in (("git_sha", sha), ("git_branch", branch), ("git_status", status))
            if not result["ok"]
        ],
    }


def collect_selected_hashes(repo: Path) -> list[dict[str, Any]]:
    paths: set[Path] = set()
    for pattern in SELECTED_HASH_GLOBS:
        paths.update(path for path in repo.glob(pattern) if path.is_file())

    entries = []
    for path in sorted(paths, key=lambda item: item.relative_to(repo).as_posix()):
        rel = path.relative_to(repo).as_posix()
        entries.append(
            {
                "path": rel,
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    return entries


def collect_config(repo: Path, gaps: list[str]) -> dict[str, Any]:
    config_path = repo / "user_data/config.json"
    raw = load_json(config_path, gaps)
    safe = filter_config(raw or {}, SAFE_CONFIG_SPEC)
    assert_no_secret_keys(safe)
    return {
        "path": "user_data/config.json",
        "sha256": sha256_file(config_path) if config_path.exists() else None,
        "safe_fields": safe,
    }


def collect_evaluation(repo: Path, gaps: list[str]) -> dict[str, Any]:
    eval_path = repo / "user_data/evaluation_phase.json"
    data = load_json(eval_path, gaps) or {}
    return {
        "path": "user_data/evaluation_phase.json",
        "sha256": sha256_file(eval_path) if eval_path.exists() else None,
        "metrics": data,
    }


def sqlite_query_dicts(db_path: Path, sql: str) -> list[dict[str, Any]]:
    connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(sql).fetchall()
        return [dict(row) for row in rows]
    finally:
        connection.close()


def collect_trade_metrics(repo: Path, gaps: list[str]) -> dict[str, Any]:
    db_path = repo / "user_data/tradesv3.sqlite"
    if not db_path.exists():
        gaps.append(f"missing_file:{db_path}")
        return {"path": "user_data/tradesv3.sqlite", "sha256": None, "metrics": None}

    try:
        summary = sqlite_query_dicts(
            db_path,
            """
            SELECT
              COUNT(*) AS trade_count,
              COALESCE(SUM(CASE WHEN is_open THEN 1 ELSE 0 END), 0) AS open_trade_count,
              MIN(open_date) AS first_open_date,
              MAX(open_date) AS last_open_date,
              MIN(close_date) AS first_close_date,
              MAX(close_date) AS last_close_date,
              ROUND(COALESCE(SUM(close_profit_abs), 0), 8) AS close_profit_abs_sum,
              ROUND(COALESCE(SUM(realized_profit), 0), 8) AS realized_profit_sum,
              ROUND(COALESCE(AVG(close_profit), 0), 8) AS close_profit_avg
            FROM trades
            """,
        )[0]
        by_pair = sqlite_query_dicts(
            db_path,
            """
            SELECT
              pair,
              COUNT(*) AS trade_count,
              COALESCE(SUM(CASE WHEN is_open THEN 1 ELSE 0 END), 0) AS open_trade_count,
              ROUND(COALESCE(SUM(close_profit_abs), 0), 8) AS close_profit_abs_sum
            FROM trades
            GROUP BY pair
            ORDER BY pair
            """,
        )
        by_strategy = sqlite_query_dicts(
            db_path,
            """
            SELECT
              COALESCE(strategy, '<null>') AS strategy,
              COUNT(*) AS trade_count,
              ROUND(COALESCE(SUM(close_profit_abs), 0), 8) AS close_profit_abs_sum
            FROM trades
            GROUP BY COALESCE(strategy, '<null>')
            ORDER BY strategy
            """,
        )
    except Exception as exc:
        gaps.append(f"sqlite_metrics_failed:{db_path}:{exc}")
        return {
            "path": "user_data/tradesv3.sqlite",
            "sha256": sha256_file(db_path),
            "metrics": None,
        }

    return {
        "path": "user_data/tradesv3.sqlite",
        "sha256": sha256_file(db_path),
        "metrics": {
            "summary": summary,
            "by_pair": by_pair,
            "by_strategy": by_strategy,
        },
    }


def collect_prediction_inventory(repo: Path) -> list[dict[str, Any]]:
    paths: set[Path] = set()
    for pattern in PREDICTION_GLOBS:
        paths.update(path for path in repo.glob(pattern) if path.is_file())
    inventory = []
    for path in sorted(paths, key=lambda item: item.relative_to(repo).as_posix()):
        inventory.append(
            {
                "path": path.relative_to(repo).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
                "mtime_utc": dt.datetime.fromtimestamp(path.stat().st_mtime, dt.UTC)
                .replace(microsecond=0)
                .isoformat()
                .replace("+00:00", "Z"),
            }
        )
    return inventory


def remote_python_metrics_command(remote_path: Path) -> str:
    script = r"""
import hashlib, json, os, sqlite3
root = __REMOTE_ROOT__
db = os.path.join(root, "user_data/tradesv3.sqlite")
out = {"path": "user_data/tradesv3.sqlite", "exists": os.path.exists(db)}
if os.path.exists(db):
    h = hashlib.sha256()
    with open(db, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    out["sha256"] = h.hexdigest()
    con = sqlite3.connect("file:" + db + "?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        out["summary"] = dict(con.execute("SELECT COUNT(*) AS trade_count, COALESCE(SUM(CASE WHEN is_open THEN 1 ELSE 0 END), 0) AS open_trade_count, MIN(open_date) AS first_open_date, MAX(open_date) AS last_open_date, MIN(close_date) AS first_close_date, MAX(close_date) AS last_close_date, ROUND(COALESCE(SUM(close_profit_abs), 0), 8) AS close_profit_abs_sum, ROUND(COALESCE(SUM(realized_profit), 0), 8) AS realized_profit_sum, ROUND(COALESCE(AVG(close_profit), 0), 8) AS close_profit_avg FROM trades").fetchone())
        out["by_pair"] = [dict(r) for r in con.execute("SELECT pair, COUNT(*) AS trade_count, COALESCE(SUM(CASE WHEN is_open THEN 1 ELSE 0 END), 0) AS open_trade_count, ROUND(COALESCE(SUM(close_profit_abs), 0), 8) AS close_profit_abs_sum FROM trades GROUP BY pair ORDER BY pair")]
    finally:
        con.close()
print(json.dumps(out, sort_keys=True))
""".replace("__REMOTE_ROOT__", repr(str(remote_path)))
    return f"python3 - <<'PY'\n{script}\nPY"


def collect_remote(host: str, remote_path: Path, gaps: list[str]) -> dict[str, Any]:
    git_cmd = (
        f"cd {shell_quote(str(remote_path))} && "
        "printf 'branch=%s\\n' \"$(git branch --show-current 2>/dev/null)\" && "
        "printf 'sha=%s\\n' \"$(git rev-parse HEAD 2>/dev/null)\" && "
        "git status --short --untracked-files=all 2>/dev/null"
    )
    git_result = run_command(
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", host, git_cmd], timeout=30
    )

    runtime_cmd = (
        f"cd {shell_quote(str(remote_path))} && "
        "docker ps --format '{{json .}}' 2>/dev/null | sort && "
        "printf '\\n--compose-ps--\\n' && docker compose ps 2>/dev/null && "
        "printf '\\n--checksums--\\n' && sha256sum docker-compose.yml user_data/config.json "
        "user_data/evaluation_phase.json 2>/dev/null"
    )
    runtime_result = run_command(
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", host, runtime_cmd],
        timeout=40,
    )

    metrics_result = run_command(
        [
            "ssh",
            "-o",
            "BatchMode=yes",
            "-o",
            "ConnectTimeout=10",
            host,
            remote_python_metrics_command(remote_path),
        ],
        timeout=40,
    )

    remote = {
        "host": host,
        "path": str(remote_path),
        "git": parse_remote_git(git_result["stdout"]) if git_result["ok"] else None,
        "runtime": parse_remote_runtime(runtime_result["stdout"]) if runtime_result["ok"] else None,
        "trade_metrics": parse_json_stdout(metrics_result["stdout"])
        if metrics_result["ok"]
        else None,
        "gaps": [],
    }
    if not git_result["ok"]:
        remote["gaps"].append(f"remote_git_failed:{git_result['stderr'].strip()}")
    if not runtime_result["ok"]:
        remote["gaps"].append(f"remote_runtime_failed:{runtime_result['stderr'].strip()}")
    if not metrics_result["ok"]:
        remote["gaps"].append(f"remote_trade_metrics_failed:{metrics_result['stderr'].strip()}")
    gaps.extend(remote["gaps"])
    return remote


def shell_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def parse_remote_git(stdout: str) -> dict[str, Any]:
    lines = stdout.splitlines()
    branch = ""
    sha = ""
    status = []
    for line in lines:
        if line.startswith("branch="):
            branch = line.removeprefix("branch=")
        elif line.startswith("sha="):
            sha = line.removeprefix("sha=")
        elif line.strip():
            status.append(line)
    return {
        "branch": branch or None,
        "sha": sha or None,
        "status_short": sorted(status),
        "is_dirty": bool(status),
    }


def parse_remote_runtime(stdout: str) -> dict[str, Any]:
    docker_ps, _, rest = stdout.partition("\n--compose-ps--\n")
    compose_ps, _, checksums = rest.partition("\n--checksums--\n")
    containers = []
    for line in docker_ps.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            raw = json.loads(line)
            containers.append(
                {
                    "id": raw.get("ID"),
                    "image": raw.get("Image"),
                    "names": raw.get("Names"),
                    "status": raw.get("Status"),
                    "ports": raw.get("Ports"),
                }
            )
        except json.JSONDecodeError:
            containers.append({"raw": line})
    return {
        "docker_ps": sorted(containers, key=lambda item: json.dumps(item, sort_keys=True)),
        "docker_compose_ps_sha256": text_sha256(compose_ps.strip()),
        "docker_compose_ps_text": compose_ps.strip(),
        "checksums": parse_sha256sum(checksums),
    }


def parse_sha256sum(stdout: str) -> list[dict[str, str]]:
    entries = []
    for line in stdout.splitlines():
        parts = line.strip().split(maxsplit=1)
        if len(parts) == 2:
            entries.append({"sha256": parts[0], "path": parts[1]})
    return sorted(entries, key=lambda item: item["path"])


def parse_json_stdout(stdout: str) -> Any | None:
    for line in reversed(stdout.splitlines()):
        line = line.strip()
        if not line:
            continue
        return json.loads(line)
    return None


def build_evidence(
    source_repo: Path,
    generated_at: str,
    evidence_cutoff: str,
    remote_host: str | None = None,
    remote_path: Path | None = None,
) -> dict[str, Any]:
    gaps: list[str] = []
    evidence = {
        "schema_version": 1,
        "generated_at": generated_at,
        "evidence_cutoff": evidence_cutoff,
        "source": {
            "local_repo": str(source_repo),
            "remote_host": remote_host,
            "remote_path": str(remote_path) if remote_path else None,
        },
        "local": {
            "git": collect_git(source_repo),
            "selected_file_hashes": collect_selected_hashes(source_repo),
            "config": collect_config(source_repo, gaps),
            "server_config_checksums": [
                entry
                for entry in collect_selected_hashes(source_repo)
                if entry["path"]
                in {
                    "docker-compose.yml",
                    "user_data/config.json",
                    "user_data/evaluation_phase.json",
                }
            ],
            "trade_metrics": collect_trade_metrics(source_repo, gaps),
            "evaluation_phase": collect_evaluation(source_repo, gaps),
            "historic_prediction_artifacts": collect_prediction_inventory(source_repo),
        },
        "remote": None,
        "evidence_gaps": [],
    }
    if remote_host and remote_path:
        evidence["remote"] = collect_remote(remote_host, remote_path, gaps)
    evidence["evidence_gaps"] = sorted(set(gap for gap in gaps if gap))
    return evidence


def write_outputs(evidence: dict[str, Any], output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    date = evidence["generated_at"][:10]
    json_path = output_dir / f"v2-baseline-{date}.json"
    md_path = output_dir / f"v2-baseline-{date}.md"
    json_path.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    md_path.write_text(render_markdown(evidence))
    return json_path, md_path


def render_markdown(evidence: dict[str, Any]) -> str:
    local_git = evidence["local"]["git"]
    local_trades = evidence["local"]["trade_metrics"]["metrics"]
    local_summary = local_trades["summary"] if local_trades else {}
    remote = evidence.get("remote") or {}
    remote_git = remote.get("git") or {}
    remote_trades = remote.get("trade_metrics") or {}
    remote_summary = remote_trades.get("summary") or {}
    prediction_count = len(evidence["local"]["historic_prediction_artifacts"])
    file_hash_count = len(evidence["local"]["selected_file_hashes"])
    gaps = evidence["evidence_gaps"]
    lines = [
        "# V2 Baseline Evidence",
        "",
        f"- generated_at: `{evidence['generated_at']}`",
        f"- evidence_cutoff: `{evidence['evidence_cutoff']}`",
        f"- local_git: `{local_git.get('branch')}` `{local_git.get('sha')}` dirty={local_git.get('is_dirty')}",
        f"- remote_git: `{remote_git.get('branch')}` `{remote_git.get('sha')}` dirty={remote_git.get('is_dirty')}",
        f"- selected_file_hashes: `{file_hash_count}`",
        f"- historic_prediction_artifacts: `{prediction_count}`",
        f"- evaluation_phase: `{evidence['local']['evaluation_phase']['metrics'].get('phase')}`",
        "",
        "## Trade Metrics",
        "",
        f"- local_trade_count: `{local_summary.get('trade_count')}` open=`{local_summary.get('open_trade_count')}`",
        f"- local_close_profit_abs_sum: `{local_summary.get('close_profit_abs_sum')}`",
        f"- local_first_close_date: `{local_summary.get('first_close_date')}`",
        f"- local_last_close_date: `{local_summary.get('last_close_date')}`",
        f"- local_db_sha256: `{evidence['local']['trade_metrics'].get('sha256')}`",
        f"- remote_trade_count: `{remote_summary.get('trade_count')}` open=`{remote_summary.get('open_trade_count')}`",
        f"- remote_close_profit_abs_sum: `{remote_summary.get('close_profit_abs_sum')}`",
        f"- remote_first_close_date: `{remote_summary.get('first_close_date')}`",
        f"- remote_last_close_date: `{remote_summary.get('last_close_date')}`",
        f"- remote_db_sha256: `{remote_trades.get('sha256')}`",
        "",
        "## Evidence Gaps",
        "",
    ]
    if gaps:
        lines.extend(f"- `{gap}`" for gap in gaps)
    else:
        lines.append("- None recorded.")
    lines.extend(
        [
            "",
            "## Secret Handling",
            "",
            "Only safe config fields, checksums, inventories, and aggregate metrics are recorded. "
            "Databases, model binaries, logs, and sensitive config values are not copied.",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-repo", type=Path, default=DEFAULT_SOURCE_REPO)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--generated-at", default=os.environ.get("V2_EVIDENCE_GENERATED_AT") or utc_now_iso()
    )
    parser.add_argument("--evidence-cutoff", default=os.environ.get("V2_EVIDENCE_CUTOFF"))
    parser.add_argument("--remote-host", default=DEFAULT_REMOTE_HOST)
    parser.add_argument("--remote-path", type=Path, default=DEFAULT_REMOTE_PATH)
    parser.add_argument("--no-remote", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    evidence_cutoff = args.evidence_cutoff or args.generated_at
    remote_host = None if args.no_remote else args.remote_host
    remote_path = None if args.no_remote else args.remote_path
    evidence = build_evidence(
        source_repo=args.source_repo,
        generated_at=args.generated_at,
        evidence_cutoff=evidence_cutoff,
        remote_host=remote_host,
        remote_path=remote_path,
    )
    json_path, md_path = write_outputs(evidence, args.output_dir)
    print(f"wrote {json_path}")
    print(f"wrote {md_path}")
    if evidence["evidence_gaps"]:
        print("evidence gaps:")
        for gap in evidence["evidence_gaps"]:
            print(f"- {gap}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
