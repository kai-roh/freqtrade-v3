# Phase 1 Demo Week Run

기준일: 2026-09-15 KST

Status: **finished; window expired.** The runner halted 2026-09-17 16:41 UTC, the
7-day window expired 2026-09-22 12:07 UTC, and the open episode was closed by a
close-only takeover on 2026-09-25 11:01 UTC (no open intents). The run started 2026-09-15 12:07:24 UTC on explicit user
instruction after Telegram notifications were confirmed on every event.

- Outcome: 30 episodes closed (1 under manifest `20a581d`, 28 under `81999bd`,
  1 transferred to `1a124d1` for its close), 128 fills, zero rejected
  transitions, zero unresolved recovery, three forced-restart recoveries (see
  "Deliberate restarts"). Gate item "50 episodes" is **not met**.
- Halt cause: in episode 26 the Spot close IOC was denied by the action risk
  worker with `quote transport stale` (receive gap over 2 s) and the runner
  treated the denial as fatal (exit 2). Intent
  `1fe50ea6-3e97-4fd8-b1dc-32f06384ef6b` is `ABORTING` with `0.00286713 BTC`
  Spot long unhedged on the Demo account (futures flat). Telegram error events
  were delivered at the time.
- Resume attempt 2026-09-25 08:08 UTC (`…-resume4`, image `81999bd`, user-approved):
  `RESUMING` was reached, then the unhedged notional-duration invariant fired
  before any order because it integrates exposure over the eight stopped days
  (budget 300 USDT × 900 s). Exit 2, zero orders, evidence `run-resume4.json`.
- Fixes in `1a124d1`: transient freshness denials retry next tick with a cap of
  five consecutive denials; in the closing phase a budget exceedance is recorded
  as `episode_baselines.evidence->'unhedged_budget_exceeded'` and closing
  continues. Image `freqtrade-v3-demo-auto:1a124d1` (`sha256:5d2dd045…`) is built.
- Close-only takeover 2026-09-25 11:01 UTC (`…-resume5`, image `1a124d1`,
  user-approved): same `--started-at`, `--resume-intent 1fe50ea6…`,
  `--previous-manifest 8f3072d6…`. `RESUMING` 11:01:26, Spot sell IOC enqueued
  11:01:29, filled `0.00286 BTC @ 84734.00` 11:01:32, residual `0.00000713 BTC`
  (0.60 USDT) settled 11:01:35, intent `CLOSED`, exit 0, no new entry. The
  budget exceedance was recorded once in the baseline evidence
  (`unhedged_notional_milliseconds` 1.63e11 vs budget 2.7e8). Ledger after:
  30 `CLOSED`, 128 fills, 30 settled residuals totalling `0.00021362 BTC`,
  rejected transitions 0, unresolved recovery 0, active commands 0.
  Evidence `run-resume5.json`.
- Containers `phase1-demo-week-run-20260915-restart3`, `…-resume4` (exited 2) and
  `…-resume5` (exited 0), config `configs/phase1-week-run.json`, run identity in
  `evidence/phase1/demo-week-run-20260915/started-at.txt`.

## Readiness — 2026-09-15

- Residual ownership: implemented and exercised on the server (Decision 0007).
- Repetition runner: `scripts/run_phase1_demo_auto.py --engineering-config
  configs/phase1-week-run.json` runs bounded episodes (60 episodes, 2 h interval,
  7-day window, Telegram pause after 3 consecutive delivery failures). An open
  episode is always resumed; every notification records its delivery result.
- Quote-age SLA: `maximum_quote_age_ms=96` adopted from 259 USD-M exchange-age
  samples (p99 47.68 ms, rule ceil(2 x p99)). Spot bookTicker stays unmeasured.
- Forced-restart and two-episode repetition verification on Demo: see
  `docs/PHASE1_DEMO_AUTO_RUNBOOK.md` ("반복·재시작 검증").

The 2026-09-15 engineering run produced four actual fills in one episode, with
a timestamp fix and close-only takeover between the futures and Spot exits.
It stopped with `0.00000715 BTC` residual inventory. Futures and open orders
were zero at the final account check. This is not an uninterrupted completed
episode, a week-run start, or four episodes toward the count below.

Before starting the week run:

1. ~~Define and implement residual ownership/accounting~~ Implemented on
   2026-09-15 (Decision 0007): unsellable closing dust is settled as an audited
   owned residual and inherited by the next baseline. The stuck episode was
   settled on the server the same day (`residual-settlement-20260915.json`).
2. ~~Complete bounded cancellation, partial-fill and restart recovery
   verification.~~ Restart recovery was verified with a forced kill on Demo on
   2026-09-15. The runner is IOC-only: an unfilled or partially filled IOC ends
   as a terminal order, REST recovery deactivates its command, and the next tick
   re-plans from confirmed inventory within the six-command cap. Cancellation of
   resting orders is outside this runner and remains covered by the matching probe.
3. ~~Record Telegram delivery results and implement the corresponding pause
   rule.~~ Done: every event stores `telegram_delivered`; three consecutive
   failures stop new entries after the open episode closes.
4. ~~Explicitly revise the current one-episode engineering runner for bounded
   repetition.~~ Done via run bounds; run identity (`--started-at`) is reused on
   restart and the episode budget is per manifest.

See [latest status](PHASE1_IMPLEMENTATION_STATUS.md) and
[execution evidence and recovery](PHASE1_DEMO_AUTO_RUNBOOK.md).

## Scope

Phase 1 Demo week run is an operational observation period for the Binance Demo
carry execution stack. It is not a profitability test, a Phase 3 promotion gate,
or evidence that live fill quality has been measured.

Allowed evidence:

- Demo start, stop, trade, and error notifications.
- State-machine correctness.
- Intent, command, dispatch, fill inbox, and reconciliation persistence.
- Restart recovery before new command admission.
- Quote collection timestamps and transport health.

Excluded evidence:

- Real fill rate.
- Queue priority.
- Adverse selection.
- Live hedge latency.
- Actual slippage.
- Profitability or expected return.

## Telegram Notifications

Runner notifications are short: `[DEMO][PHASE1][KIND] title` on the first line and
a one-line summary with the KST time on the second. Full details stay in the
evidence file. Example: `[DEMO][PHASE1][TRADE] 체결 현물 매수` / `0.00285 BTC @
76950.16 · 09-15 21:26:01 KST`.

Telegram is operational telemetry only. A notification failure must return a
failed delivery result and must not retry orders, resubmit commands, unblock a
blocked inbox receipt, or change risk approval.

The Phase 1 notification helper reads only:

- `TELEGRAM_TOKEN`
- `TELEGRAM_CHAT_ID`

Messages must mark Demo mode in the first line:

```text
[DEMO][PHASE1][TRADE] two-leg episode accepted
```

Do not include API keys, secrets, tokens, signatures, balances, raw exchange
payloads, or account identifiers in notification details. Sensitive detail keys
are redacted before formatting, but callers should still pass compact operational
summaries instead of raw payloads.

## Stop Conditions

Stop the Demo runner and preserve evidence when any of these occur:

- A fill inbox receipt becomes `BLOCKED`.
- A dispatch remains unresolved after restart recovery.
- A risk decision is stale, malformed, or disagrees with the current policy or
  fee snapshot hash.
- Either leg is partially filled and bounded cancel or hedge handling cannot
  complete.
- A timestamp required by the configured SLA path becomes unavailable. Spot
  bookTicker has no exchange timestamp by design: retain NULL exchange age and
  measure receive-gap separately. The engineering policy explicitly uses
  receive-gap. The economic policy's `maximum_quote_age_ms=96` applies to USD-M
  exchange age; the economic entry path still denies while Spot age is unmeasured.
- Run bounds are exhausted (`episode_budget_complete`, `run_window_exhausted`) or
  the Telegram pause rule fires (`telegram_pause`); both are recorded as `stop` events.
- Telegram delivery repeatedly fails while the runner is otherwise healthy.

The last condition is an observability failure, not a trading failure. It should
pause unattended operation because the user expects Demo trade history through
Telegram during this run.

## Success Criteria

The week run can support Phase 1E completion only if the final report includes:

- At least 50 Demo episodes counted from accepted dispatch/fill evidence, not
  fixture replay.
- At least 3 restart recovery events with no duplicate command admission.
- Zero unresolved dispatches.
- Zero blocked fill inbox receipts at close.
- Full state transition, order command, order, fill, transfer, incident, quote,
  and cost evidence for each episode.
- Explicit separation of Demo-observed fees from injected Mainnet fee policy.

Passing this run means the Demo execution pipeline is operable enough for the
next review. It does not mean the strategy is profitable or ready for Mainnet
capital.


## Starting the week run

Only after the readiness items above are re-checked on the day of the run:

```bash
cd /home/kai/freqtrade-v3
set -a; . ./.phase1-database.env; set +a
IMG=freqtrade-v3-demo-auto:<short-sha>
START=$(date -u +%Y-%m-%dT%H:%M:%S+00:00)   # keep this value for every restart
mkdir -p evidence/phase1/demo-week-run-$(date +%Y%m%d)
docker run -d --name phase1-demo-week-run-$(date +%Y%m%d) \
  --network phase1-demo-evidence --read-only \
  --tmpfs /tmp:rw,nosuid,nodev,size=128m --user 1002:1002 \
  -e PHASE1_DATABASE_DSN -e PHASE1_BUILD_SOURCE_SHA=<full-sha> \
  -e PHASE1_IMAGE_DIGEST="$(docker image inspect --format '{{.Id}}' "$IMG")" \
  -v /home/kai/freqtrade-v3/.env:/run/phase1.env:ro \
  -v /home/kai/freqtrade-v3/evidence/phase1/demo-week-run-$(date +%Y%m%d):/evidence \
  --entrypoint /app/.venv/bin/python "$IMG" scripts/run_phase1_demo_auto.py \
  --credentials-env-file /run/phase1.env --output /evidence/run.json \
  --started-at "$START" --execute-demo-auto \
  --engineering-config configs/phase1-week-run.json
```

The container does not auto-restart. Each deliberate restart uses the same
`--started-at` and a new container name; the runner resumes any open episode
first. Three or more such restarts are required for the Phase 1E gate.


## Telegram commands

`scripts/run_phase1_telegram_bot.py` answers, for the configured chat only:

- `/status` — run start, episodes closed vs budget, open episode state, last event, ledger integrity.
- `/profit` — realized USDT cash flow per episode net of USDT fees; settled BTC residual listed separately and unvalued. Demo only, not a profitability claim.
- `/balance` — Demo Spot USDT/BTC, futures available USDT, perp position, leverage, open orders.
- `/daily` — today's (KST) episodes, fills, realized PnL, residual, errors, undelivered notifications.
- `/help` — this list.

The bot opens the ledger with `default_transaction_read_only=on`, mounts the
evidence directory read-only, and has no order transport. Messages from any other
chat are ignored without reply.


## Deliberate restarts

`scripts/phase1_deliberate_restart.sh <base-name> <label> <evidence-dir>` waits
until the running week runner has an open episode with a filled perp leg, kills
that container, and starts `<base-name>-<label>` with the same image, source
hash, run identity, and config. The new container must resume the open episode
(`RESUMING`) and close it without re-hedging. Each run appends to
`<evidence-dir>/deliberate-restarts.log` and writes `run-<label>.json`.

Executed on 2026-09-15 (UTC), each while the open episode was `HEDGE_REQUIRED`
(Spot long held, perp short filled, sub-lot remainder unhedged by design):

| Restart | Killed at | Resumed at | Outcome |
|---|---|---|---|
| 1 (version change, between episodes) | 12:25 | 12:25:56 | new manifest; started its own episode 1 |
| 2 (`restart2`, mid-hold) | 14:31:18 | 14:31:27 `RESUMING` | perp closed in 3 IOC partial fills (0.0010+0.0010+0.0008), Spot sold, residual 0.00000712 settled, CLOSED |
| 3 (`restart3`, mid-hold) | 16:36:43 | 16:36:52 `RESUMING` | perp closed in one fill, Spot sold, residual 0.00000713 settled, CLOSED |

After restart 3 the ledger held 7 intents all `CLOSED`, 30 fills, zero rejected
transitions, zero unresolved recovery checks, zero unapplied inbox rows, zero
active commands. No re-hedge or duplicate entry occurred on any resume. Restart 2
also exercised the IOC partial-fill re-plan path for real. This satisfies the
"three forced-termination recoveries" item of the Phase 1E gate; the episode
count (50) and the end-of-run aggregation remain.
Log: `evidence/phase1/demo-week-run-20260915/deliberate-restarts.log`.
