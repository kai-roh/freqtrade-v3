#!/usr/bin/env bash

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

PERIOD="${1:-}"
if [[ "$PERIOD" != "daily" && "$PERIOD" != "weekly" ]]; then
  echo "usage: $0 {daily|weekly}" >&2
  exit 2
fi

if [[ ! -f .env ]]; then
  echo ".env is required for API and Telegram credentials" >&2
  exit 2
fi

set -a
# shellcheck disable=SC1091
source .env
set +a

export FT_API_BASE="${FT_API_BASE:-http://127.0.0.1:8080/api/v1}"
export REPORT_TZ="${REPORT_TZ:-Asia/Seoul}"
export V3_RESEARCH_RESULTS="${V3_RESEARCH_RESULTS:-research_results/scheduled/latest/results.json}"

exec python3 scripts/send_operations_report.py "$PERIOD" --telegram-always
