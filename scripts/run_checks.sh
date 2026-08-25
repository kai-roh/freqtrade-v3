#!/usr/bin/env bash

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

python3 -m ruff check .
python3 -m ruff format --check .
python3 -m pytest

for script in scripts/*.sh; do
  bash -n "$script"
done

for config in configs/*.json; do
  python3 -m json.tool "$config" >/dev/null
done

for example in examples/phase0/*.json; do
  python3 -m json.tool "$example" >/dev/null
done

if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
  docker compose config --quiet
else
  echo "Docker Compose unavailable; skipped compose configuration validation." >&2
fi
