#!/usr/bin/env bash
# Download the Phase 2 universe: 8 USDT perpetuals, 1h candles plus funding rate
# and mark price (freqtrade fetches all three in futures mode), 450 days.
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

DAYS="${V3_PHASE2_DATA_DAYS:-450}"
IMAGE="${V3_FREQTRADE_IMAGE:-freqtradeorg/freqtrade@sha256:50720a4af314a812be2cfbf5cc6331c63e9332b06f3f4372241f54bc61a35486}"
PAIRS=(BTC/USDT:USDT ETH/USDT:USDT SOL/USDT:USDT BNB/USDT:USDT XRP/USDT:USDT DOGE/USDT:USDT ADA/USDT:USDT LINK/USDT:USDT)

# Separate datadir: the weekly cron dataset under user_data/data stays untouched.
DATADIR="${V3_PHASE2_DATADIR:-user_data/data-phase2}"
HOST_GID="$(id -g)"
mkdir -p "$DATADIR"
# Keep the image's uid 1000 so its freqtrade install stays executable, and share
# the host group so the written files remain manageable from the host.
chgrp "$HOST_GID" "$DATADIR"
chmod 2770 "$DATADIR"
docker run --rm --user "1000:$HOST_GID" \
  -v "$PROJECT_ROOT/user_data:/freqtrade/user_data" \
  -v "$PROJECT_ROOT/configs:/freqtrade/configs:ro" \
  "$IMAGE" download-data \
  --config /freqtrade/configs/research.json \
  --datadir "/freqtrade/$DATADIR/binance" \
  --pairs "${PAIRS[@]}" \
  --timeframes 1h \
  --days "$DAYS" \
  --trading-mode futures
