#!/usr/bin/env bash

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

HOST_TIMEZONE="$(timedatectl show -p Timezone --value 2>/dev/null || true)"
if [[ "$HOST_TIMEZONE" != "Asia/Seoul" ]]; then
  echo "host timezone must be Asia/Seoul before installing the V3 schedule" >&2
  exit 2
fi

install -d -m 0700 reports reports/daily reports/weekly reports/logs
crontab deploy/freqtrade-v3.cron

echo "V3 cron installed for Asia/Seoul host time"
