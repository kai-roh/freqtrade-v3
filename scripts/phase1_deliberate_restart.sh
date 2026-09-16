#!/usr/bin/env bash
# Deliberate forced restart of the running Demo week runner during an open,
# hedged episode. This is the Phase 1E "forced termination -> restart recovery"
# exercise: kill the runner while inventory is open, then start a new container
# with the same run identity and image so it must resume the open episode.
#
# usage: scripts/phase1_deliberate_restart.sh <base-name> <label> <evidence-dir> [config] [timeout-seconds]
set -euo pipefail

cd "$(dirname "$0")/.."

RUN_NAME="${1:?base container name, e.g. phase1-demo-week-run-20260915}"
LABEL="${2:?restart label, e.g. restart2}"
EV_DIR="${3:?evidence directory relative to the project root}"
CONFIG="${4:-configs/phase1-week-run.json}"
TIMEOUT_SECONDS="${5:-14400}"
LOG="$EV_DIR/deliberate-restarts.log"

set -a
# shellcheck disable=SC1091
. ./.phase1-database.env
set +a

current="$(docker ps --filter "name=^${RUN_NAME}" --filter status=running --format '{{.Names}}' | head -1)"
if [[ -z "$current" ]]; then
  echo "no running runner matching ${RUN_NAME}" >&2
  exit 2
fi
IMG="$(docker inspect --format '{{.Config.Image}}' "$current")"
SHA="$(docker inspect --format '{{range .Config.Env}}{{println .}}{{end}}' "$current" | sed -n 's/^PHASE1_BUILD_SOURCE_SHA=//p')"
DIG="$(docker image inspect --format '{{.Id}}' "$IMG")"
START="$(cat "$EV_DIR/started-at.txt")"

psql_count() {
  docker exec phase1-postgres psql -U phase1 -d phase1 -Atc "$1"
}

# Wait for an open episode whose perp leg has filled, i.e. real two-leg inventory.
deadline=$((SECONDS + TIMEOUT_SECONDS))
hedged=0
while (( SECONDS < deadline )); do
  hedged="$(psql_count "select count(*) from intents i where i.state<>'CLOSED' and exists (select 1 from fills f join orders o on o.id=f.order_id join order_commands c on c.id=o.command_id where c.intent_id=i.id and c.leg='perp')")"
  if [[ "$hedged" == "1" ]]; then
    break
  fi
  sleep 10
done
if [[ "$hedged" != "1" ]]; then
  echo "$(date -u +%FT%TZ) ${LABEL}: no hedged open episode before timeout; nothing restarted" | tee -a "$LOG" >&2
  exit 3
fi

open_state="$(psql_count "select state from intents where state<>'CLOSED' limit 1")"
echo "$(date -u +%FT%TZ) ${LABEL}: killing ${current} during open episode (state ${open_state})" | tee -a "$LOG"
docker kill "$current" >/dev/null
sleep 3

docker run -d --name "${RUN_NAME}-${LABEL}" \
  --network phase1-demo-evidence --read-only \
  --tmpfs /tmp:rw,nosuid,nodev,size=128m --user 1002:1002 \
  -e PHASE1_DATABASE_DSN \
  -e PHASE1_BUILD_SOURCE_SHA="$SHA" \
  -e PHASE1_IMAGE_DIGEST="$DIG" \
  -v "$PWD/.env:/run/phase1.env:ro" \
  -v "$PWD/$EV_DIR:/evidence" \
  --entrypoint /app/.venv/bin/python "$IMG" scripts/run_phase1_demo_auto.py \
  --credentials-env-file /run/phase1.env \
  --output "/evidence/run-${LABEL}.json" \
  --started-at "$START" --execute-demo-auto \
  --engineering-config "$CONFIG" >/dev/null
echo "$(date -u +%FT%TZ) ${LABEL}: started ${RUN_NAME}-${LABEL} image=${DIG} source=${SHA}" | tee -a "$LOG"
