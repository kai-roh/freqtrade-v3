# 0022 — MA200 reporting fix, retired shadow reports, guard failure alerts

- Status: Accepted
- Date: 2026-10-07 (KST)
- Amends: Decision 0019 (observation report), Decision 0020 (guard)

## Context

On 2026-10-07 the user reported that the daily and weekly reports showed no values.
The review found three separate things:

1. **The 23:00 daily and Sunday weekly reports** come from the old freqtrade
   `V3ShadowStrategy` dry run. The research gate has stayed `STOP_BEFORE_CLASSIFIER`,
   so that bot never trades and the reports showed 0 trades and 0 P&L every day.
   They say nothing about MA200.
2. **The MA200 observation report** measured "today" and the week from the 00:00 UTC
   equity point, one hour before the 01:00 UTC valuation. The 10-03 to 10-06 reports
   showed one hour of P&L (for example +0.63 instead of +8.48 on 10-05). Equity,
   total P&L, and positions were correct.
3. **One guard run failed** on 2026-10-06 04:20 UTC. The Demo venue timed out on the
   position read (408, -1007). The failure sent no alert, and a run of failures would
   have left the loss stop unwatched without notice.

The user approved all three fixes.

## Decision

1. **Observation periods follow the daily reports.** Each report covers the 24 hours
   since the previous report's valuation. The week starts with Monday's report and the
   month with the report on the 1st (KST). Period rows add up to the total, and the
   current period is marked "진행 중". The rule, costs, and accounts do not change.
2. **The report carries the Demo actual account.** It shows equity at each executor
   run, 24h/week/month P&L, and the distance to the stop, plus a Demo column in the
   weekly and monthly tables. A new check, `live_executor_fresh`, fails when the newest
   executor run is older than 26 hours.
3. **The shadow reports are retired.** The `0 23 * * *` operations report and the
   `10 23 * * 0` scheduled research are removed from the crontab. The scripts stay for
   manual use. The `freqtrade_kai` shadow container is left as it is.
4. **The guard hardens:**
   - Reads (GET) are retried twice on timeouts, rate limits, 5xx, and network errors.
     Orders are never resent by the client.
   - A guard run that raises is counted in `guard-health.json` and journaled.
   - Telegram alerts at 2 consecutive failures (20 minutes), then every 6 (hourly),
     and once more on recovery.
5. Executor reports now record the Telegram delivery after sending.
