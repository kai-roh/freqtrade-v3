#!/usr/bin/env bash

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

python3 scripts/check_shadow_runtime.py
docker compose -f docker-compose.yml --env-file .env up -d freqtrade_v3_shadow
