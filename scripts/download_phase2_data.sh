#!/usr/bin/env bash
# Download the Phase 2 universe: 8 USDT perpetuals, 1h candles plus funding rate
# and mark price (freqtrade fetches all three in futures mode), 450 days.
# Uses the same Compose service and env file as the weekly research download so
# freqtrade's config validation sees the injected non-secret dry-run values, but
# writes to a separate datadir so the cron dataset stays untouched.
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

DAYS="${V3_PHASE2_DATA_DAYS:-450}"
DATADIR="${V3_PHASE2_DATADIR:-user_data/data-phase2}"
PAIRS=(BTC/USDT:USDT ETH/USDT:USDT SOL/USDT:USDT BNB/USDT:USDT XRP/USDT:USDT DOGE/USDT:USDT ADA/USDT:USDT LINK/USDT:USDT)

if [[ ! -f .env ]]; then
  echo ".env is required by Docker Compose. Copy .env.example and use non-secret dry-run values." >&2
  exit 2
fi

# The image runs as uid/gid 1000; make the datadir writable for that group.
mkdir -p "$DATADIR"
chgrp 1000 "$DATADIR" 2>/dev/null || true
chmod 2770 "$DATADIR"

docker compose run --rm --no-deps freqtrade_v3_shadow download-data \
  --config /freqtrade/configs/research.json \
  --datadir "/freqtrade/$DATADIR/binance" \
  --pairs "${PAIRS[@]}" \
  --timeframes 1h \
  --days "$DAYS" \
  --trading-mode futures
