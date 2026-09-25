#!/usr/bin/env bash

set -Eeuo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

OUTPUT_ROOT="${V3_SCHEDULED_OUTPUT_ROOT:-research_results/scheduled}"
LOCK_FILE="${V3_RESEARCH_LOCK_FILE:-/tmp/freqtrade-v3-research.lock}"
DATA_DAYS="${V3_DATA_DAYS:-365}"
TRAIN_DAYS="${V3_TRAIN_DAYS:-180}"
VALIDATION_DAYS="${V3_VALIDATION_DAYS:-30}"
FOLD_COUNT="${V3_FOLD_COUNT:-6}"
RUN_ID="${V3_RESEARCH_RUN_ID:-$(date -u +%Y%m%dT%H%M%SZ)}"
GENERATED_AT="${V3_GENERATED_AT:-$(date -u +%Y-%m-%dT%H:%M:%SZ)}"
STAGING_DIR="$OUTPUT_ROOT/.${RUN_ID}.tmp"
FINAL_DIR="$OUTPUT_ROOT/$RUN_ID"
LATEST_TMP="$OUTPUT_ROOT/.latest.${RUN_ID}"

if ! [[ "$RUN_ID" =~ ^[0-9]{8}T[0-9]{6}Z$ ]]; then
  echo "V3_RESEARCH_RUN_ID must use YYYYMMDDTHHMMSSZ" >&2
  exit 2
fi

if ! command -v flock >/dev/null 2>&1; then
  echo "flock is required for scheduled research" >&2
  exit 2
fi

mkdir -p "$OUTPUT_ROOT"
exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  echo "another V3 research run is already active" >&2
  exit 75
fi

if [[ -e "$STAGING_DIR" || -e "$FINAL_DIR" ]]; then
  echo "research run id already exists: $RUN_ID" >&2
  exit 2
fi

cleanup() {
  rm -rf -- "$STAGING_DIR"
  rm -f -- "$LATEST_TMP"
}
trap cleanup EXIT

V3_DATA_DAYS="$DATA_DAYS" ./scripts/download_research_data.sh
V3_GENERATED_AT="$GENERATED_AT" \
  V3_RESEARCH_OUTPUT="$STAGING_DIR" \
  ./scripts/run_walk_forward.sh \
  --train-days "$TRAIN_DAYS" \
  --validation-days "$VALIDATION_DAYS" \
  --fold-count "$FOLD_COUNT"

mv "$STAGING_DIR" "$FINAL_DIR"
ln -s "$RUN_ID" "$LATEST_TMP"
mv -Tf "$LATEST_TMP" "$OUTPUT_ROOT/latest"
trap - EXIT

V3_RESEARCH_RESULTS="$FINAL_DIR/results.json" \
  ./scripts/run_operations_report.sh weekly

echo "scheduled_research=$FINAL_DIR"
