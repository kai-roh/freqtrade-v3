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

python3 -m json.tool configs/research.json >/dev/null
python3 -m json.tool configs/dry-run.json >/dev/null

if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
  docker compose config --quiet
else
  echo "Docker daemon unavailable; skipped compose runtime validation." >&2
fi
