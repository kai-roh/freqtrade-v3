#!/usr/bin/env bash
# Daily order-free MA200 forward observation (docs/MA200_FORWARD_OBSERVATION.md).
# 1) refresh public BTC/ETH perpetual and spot candles, 2) recompute the virtual
# accounts in the pinned image and send the Telegram report. No account access.
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

IMAGE="${V3_OBSERVE_IMAGE:-freqtrade-v3-observe:current}"
SINCE="${V3_OBSERVE_SINCE:-20250801}"
PERP_DIR=user_data/data-ma200-observe
SPOT_DIR=user_data/data-ma200-observe-spot
OUT_DIR=evidence/ma200-observation

V3_PHASE2_DATADIR="$PERP_DIR" V3_PHASE2_TIMERANGE="${SINCE}-" \
  V3_PHASE2_PAIRS="BTC/USDT:USDT ETH/USDT:USDT" bash scripts/download_phase2_data.sh
V3_PHASE2_DATADIR="$SPOT_DIR" V3_PHASE2_TIMERANGE="${SINCE}-" \
  V3_PHASE2_PAIRS="BTC/USDT ETH/USDT" V3_PHASE2_TRADING_MODE=spot bash scripts/download_phase2_data.sh

mkdir -p "$OUT_DIR" evidence/ma200-live-demo
docker run --rm --read-only --tmpfs /tmp:rw,nosuid,nodev,size=64m \
  --user 1002:1002 --group-add 1000 \
  -v "$PROJECT_ROOT/$PERP_DIR/binance/futures:/data/perp:ro" \
  -v "$PROJECT_ROOT/$SPOT_DIR/binance:/data/spot:ro" \
  -v "$PROJECT_ROOT/evidence/phase2b/implementability.json:/filters/perp.json:ro" \
  -v "$PROJECT_ROOT/evidence/phase2c/spot-filters-20261002.json:/filters/spot.json:ro" \
  -v "$PROJECT_ROOT/.env:/run/phase1.env:ro" \
  -v "$PROJECT_ROOT/$OUT_DIR:/out" \
  -v "$PROJECT_ROOT/evidence/ma200-live-demo:/live:ro" \
  --entrypoint /app/.venv/bin/python "$IMAGE" scripts/run_ma200_observation.py \
  --perp-dir /data/perp --spot-dir /data/spot \
  --perp-filters /filters/perp.json --spot-filters /filters/spot.json \
  --output-dir /out --credentials-env-file /run/phase1.env --send-telegram --live-state-dir /live
