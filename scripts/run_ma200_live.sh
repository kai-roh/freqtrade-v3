#!/usr/bin/env bash
# MA200 live executor / guard in the pinned image (Decision 0020). Demo by default.
# Usage: run_ma200_live.sh {execute|guard|status|init|clear-halt} [extra args...]
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

IMAGE="${V3_LIVE_IMAGE:-freqtrade-v3-live:current}"
ENVIRONMENT="${V3_LIVE_ENVIRONMENT:-demo}"
STATE_DIR="${V3_LIVE_STATE_DIR:-evidence/ma200-live-$ENVIRONMENT}"
COMMAND="${1:?command required}"
shift

mkdir -p "$STATE_DIR"
docker run --rm --read-only --tmpfs /tmp:rw,nosuid,nodev,size=64m --user 1002:1002 \
  -v "$PROJECT_ROOT/$STATE_DIR:/state" \
  -v "$PROJECT_ROOT/.env:/run/phase1.env:ro" \
  --entrypoint /app/.venv/bin/python "$IMAGE" scripts/run_ma200_live.py "$COMMAND" \
  --state-dir /state --credentials-env-file /run/phase1.env --environment "$ENVIRONMENT" \
  --send-telegram "$@"
