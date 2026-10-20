#!/usr/bin/env bash

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

if command -v uv >/dev/null 2>&1; then
  uv lock --check
  expected_lock_hash="$(awk 'NR == 1 {print $1}' evidence/phase1/dependency-lock.sha256)"
  if command -v sha256sum >/dev/null 2>&1; then
    actual_lock_hash="$(sha256sum uv.lock | awk '{print $1}')"
  else
    actual_lock_hash="$(shasum -a 256 uv.lock | awk '{print $1}')"
  fi
  if [[ "$actual_lock_hash" != "$expected_lock_hash" ]]; then
    echo "uv.lock hash does not match evidence/phase1/dependency-lock.sha256" >&2
    exit 1
  fi
  uv run --frozen ruff check .
  uv run --frozen ruff format --check .
  uv run --frozen python -m pytest
else
  python3 -m ruff check .
  python3 -m ruff format --check .
  python3 -m pytest
fi

for script in scripts/*.sh; do
  bash -n "$script"
done

for config in configs/*.json; do
  python3 -m json.tool "$config" >/dev/null
done

for example in examples/phase0/*.json; do
  python3 -m json.tool "$example" >/dev/null
done

for example in examples/phase1/*.json; do
  python3 -m json.tool "$example" >/dev/null
done

if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
  docker compose config --quiet
  PHASE1_POSTGRES_PASSWORD=validation-only \
    PHASE1_EXECUTION_IMAGE=freqtrade-v3-phase1-execution@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa \
    docker compose -f docker-compose.phase1.yml config --quiet
else
  echo "Docker Compose unavailable; skipped compose configuration validation." >&2
fi
