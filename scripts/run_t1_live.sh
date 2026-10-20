#!/usr/bin/env bash
# T1 taker-flow ensemble Demo executor / guard in the pinned image (Decision 0029). Demo only.
# Usage: run_t1_live.sh {execute|guard|status|init|clear-halt|set-stop|targets} [extra args...]
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

IMAGE="${V3_LIVE_IMAGE:-freqtrade-v3-live:current}"
STATE_DIR="${V3_T1_STATE_DIR:-evidence/t1-live-demo}"
COMMAND="${1:?command required}"
shift

mkdir -p "$STATE_DIR"
docker run --rm --read-only --tmpfs /tmp:rw,nosuid,nodev,size=64m --user 1002:1002 \
  -v "$PROJECT_ROOT/$STATE_DIR:/state" \
  -v "$PROJECT_ROOT/.env:/run/phase1.env:ro" \
  --entrypoint /app/.venv/bin/python "$IMAGE" scripts/run_t1_live.py "$COMMAND" \
  --state-dir /state --credentials-env-file /run/phase1.env --send-telegram "$@"
