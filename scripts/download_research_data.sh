#!/usr/bin/env bash

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

DAYS="${V3_DATA_DAYS:-365}"
PAIRS=("BTC/USDT:USDT" "ETH/USDT:USDT")
TIMEFRAMES=("15m" "1h")

if ! [[ "$DAYS" =~ ^[1-9][0-9]*$ ]]; then
  echo "V3_DATA_DAYS must be a positive integer" >&2
  exit 2
fi

if [[ ! -f .env ]]; then
  echo ".env is required by Docker Compose. Copy .env.example and use non-secret dry-run values." >&2
  exit 2
fi

docker compose run --rm --no-deps freqtrade_v3_shadow download-data \
  --config /freqtrade/configs/research.json \
  --pairs "${PAIRS[@]}" \
  --timeframes "${TIMEFRAMES[@]}" \
  --days "$DAYS" \
  --trading-mode futures

docker compose run --rm --no-deps freqtrade_v3_shadow list-data \
  --config /freqtrade/configs/research.json \
  --pairs "${PAIRS[@]}" \
  --trading-mode futures \
  --show-timerange
