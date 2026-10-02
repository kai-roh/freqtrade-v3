# Server state

## Latest verified state — 2026-10-03 00:17 KST

- Demo loss stop changed 900 → 800 USDT with `set-stop` (Decision 0021, journaled); image `freqtrade-v3-live:current`
  = `sha256:e3497210…` (source `c34544c`). Guard uses 800: strategy equity 990.46 USDT, 190.46 above the stop.
- Guard ran every 10 minutes since 22:40 KST, all `ok`; no halt. First scheduled executor run 10:05 KST, observation 11:10 KST.

## Latest verified state — 2026-10-02 22:33 KST

- MA200 Demo executor and guard deployed (Decision 0020). Image `freqtrade-v3-live:current` =
  `freqtrade-v3-observe:current` = `sha256:0b453043…` (source `20561ad`). State in `evidence/ma200-live-demo/`
  (config: start 2026-10-02 13:28 UTC, capital 1,000, vol 25%, stop 900).
- Demo USD-M positions: BTCUSDT 0.0034 long, ETHUSDT 0.080 long, isolated 2x; strategy equity 998.5 USDT.
- Crontab (backup under `/tmp/crontab.before.*`): operations report 23:00, weekly research Sun 23:10,
  MA200 observation 11:10, MA200 Demo executor 10:05, MA200 Demo guard every 10 minutes.
- Mainnet orders impossible: the client refuses Mainnet without a real-capital authorization record.

## Latest verified state — 2026-10-02 19:10 KST

- MA200 forward observation deployed (Decision 0019). Source `2648efb` synced; image
  `freqtrade-v3-observe:current` = `sha256:cb90aea1…` (also tagged `:2648efb`).
- Crontab reinstalled from `deploy/freqtrade-v3.cron` (previous crontab saved under `/tmp/crontab.before.*`):
  the two existing entries plus `10 11 * * *` → `scripts/run_ma200_observation.sh`.
- Manual run 19:09 KST: public BTC/ETH perpetual and spot candles from 2025-08-01 into
  `user_data/data-ma200-observe*`; status `not_started` (starts 2026-10-03 09:00 KST); checks all pass;
  Telegram preview delivered. Current MA200 signal: BTC and ETH long. Reports in `evidence/ma200-observation/`.
- No week runner, no orders, no account access by the observation job.

## Latest verified state — 2026-10-02 12:45 KST

- No week runner. `phase1-demo-week-run-20260928-restart1` stopped at 03:38 UTC
  (idle, zero open intents). `phase1-telegram-bot`, `phase1-postgres`, and the
  `freqtrade_kai` shadow are running.
- Ledger: 70 intents `CLOSED`; commands/dispatches/orders 289; fills 296;
  rejected transitions, unresolved recovery, unapplied inbox, active commands all 0.
- Demo account: perp `0`, open orders none, Spot BTC `0.00050308`.
- Phase 1E close evidence written to `evidence/phase1/phase1e-close-20261002/`
  (SLA summary in a read-only DB session; GET-only fee and connectivity probe).

## Latest verified state — 2026-09-30 15:45 KST

- Takeover `phase1-demo-week-run-20260928-takeover1` exited 0 (episode `b265fcf7…`
  closed); `phase1-demo-week-run-20260928-restart1` running on image `5e8afe1`
  since 06:37:39 UTC. Ledger: 49 `CLOSED`, 0 open; fills 210; 48 settled
  residuals; rejected transitions, unresolved recovery, active commands all 0.

## Before the recovery — 2026-09-30 KST

- `phase1-demo-week-run-20260928` exited 2 at 2026-09-29 18:31:45 UTC (sub-minimum
  perp remainder misclassified as dust). Ledger: 47 `CLOSED` + 1 `ABORTING`
  (`b265fcf7…`), fills 202, rejected transitions 0, unresolved recovery 0, active
  commands 0. Demo account: Spot `0.00296052 BTC`, perp `-0.0001`, no open orders.
- Source `5e8afe1` synced (`git archive | tar -xm`); image
  `freqtrade-v3-demo-auto:5e8afe1` = `sha256:ef02aba8…`, source SHA baked in.

## Latest verified state — 2026-09-28 16:15 KST

- `phase1-demo-week-run-20260928` running (image `1a124d1`, started
  2026-09-28 07:03:08 UTC, manifest `5a07e153…`). Episode 1 closed at 07:08:25 UTC
  with four fills and a settled residual of `0.00000736 BTC`; next entry due
  ~09:08 UTC. Readiness check before start: 6/6 passed, no orders.
- Ledger: intents 31 `CLOSED`, 0 open; fills 132. `phase1-telegram-bot` up 12 days
  (image `81999bd`, read-only); `phase1-postgres` up 13 days; `freqtrade_kai` shadow running.

## Latest verified state — 2026-09-25 20:10 KST

- Close-only takeover `phase1-demo-week-run-20260915-resume5` (image `1a124d1`,
  user-approved) exited 0 at 11:01:35 UTC: Spot `0.00286 BTC` sold at 84734,
  residual `0.00000713 BTC` settled, intent `1fe50ea6…` `ABORTING → CLOSED`.
- Ledger: intents 30 `CLOSED`, 0 open; fills 128; settled residuals 30 totalling
  `0.00021362 BTC`; rejected transitions 0; unresolved recovery 0; active
  commands 0; fill inbox fully applied. No week runner is running.
- `phase1-telegram-bot` up (image `81999bd`, read-only); `phase1-postgres` up;
  `freqtrade_kai` shadow running.

## Before the takeover — 2026-09-25 17:30 KST

- Resume attempt `phase1-demo-week-run-20260915-resume4` (image `81999bd`,
  08:08 UTC) exited 2 before any order: the unhedged notional-duration invariant
  fired on the eight stopped days. Ledger unchanged: 29 `CLOSED` + 1 `ABORTING`,
  `0.00286713 BTC` Spot long, futures flat.
- Source `1a124d1` (+ `05faa73` dockerignore) synced via `git archive | tar -xm`;
  image `freqtrade-v3-demo-auto:1a124d1` = `sha256:5d2dd045…`, source SHA baked in.
  Test image not built/run on the host this time (permission classifier denied
  the isolated-schema run); the suite passed locally against PostgreSQL 16.14
  (438 passed).
- Next state change (needs approval): close-only takeover with image `1a124d1`,
  see `PROGRESS.md` 다음 할 일 1.

## Latest verified state — 2026-09-25 16:57 KST

- `phase1-demo-week-run-20260915-restart3` exited 2 on 2026-09-17 16:41 UTC
  (Spot close denied for stale quote transport; fail-closed). One intent
  `ABORTING` with `0.00286713 BTC` Spot long unhedged; futures flat. Resume
  requires user approval (see `docs/PHASE1_WEEK_RUN.md`).
- Ledger: intents 29 `CLOSED` + 1 `ABORTING`, fills 127, rejected transitions 0,
  unresolved recovery 0, active commands 0, settled residuals 29 totalling
  `0.00020649 BTC`. USD-M quote-age samples 120,702.
- `phase1-telegram-bot` up 9 days; `phase1-postgres` up 11 days; `freqtrade_kai`
  (zero-entry shadow) healthy. Weekly cron research ran 2026-09-20
  (`STOP_BEFORE_CLASSIFIER`, best PF 0.639).
- Phase 2 data lives in `user_data/data-phase2/` (not in Git); cron dataset untouched.
- The non-git working copy is synced to `c778875`; later commits are docs/research
  only except `v3/phase2/` and `scripts/run_phase2_research.py`, which the server
  does not need to run.

## Week observation run — started 2026-09-15 21:07 KST

- Container `phase1-demo-week-run-20260915` running image
  `freqtrade-v3-demo-auto:20a581d` (`sha256:8db85012…`), source `20a581d`, config
  `configs/phase1-week-run.json`; run identity in
  `evidence/phase1/demo-week-run-20260915/started-at.txt`; events in `run.json`.
- Deliberate restart 1 at 12:25:56 UTC: now running as
  `phase1-demo-week-run-20260915-restart1` on image `freqtrade-v3-demo-auto:81999bd`
  (`sha256:b5f2ebf7…`, source `81999bd`); the first container exited 137 by design.
- Deliberate mid-episode restarts 2 and 3 fired at 14:31:18 and 16:36:43 UTC
  (`scripts/phase1_deliberate_restart.sh`); both resumed the open episode and
  closed it cleanly. Now running as `phase1-demo-week-run-20260915-restart3`;
  `-restart1` and `-restart2` exited 137 by design. Ledger at 16:52 UTC: 7 intents
  all `CLOSED`, 30 fills, 0 rejected transitions, 0 unresolved recovery.
- `phase1-telegram-bot` (same image, `--restart unless-stopped`, read-only) serves
  the Telegram commands; menu registered for bot `kais_freqtrade_bot`.
- No auto-restart for the runner. Restart with the same `--started-at` and a new
  container name (see `docs/PHASE1_WEEK_RUN.md`). Do not run any other program or
  manual order on the Demo BTCUSDT account while it runs.

## Latest verified Phase 1 state before the week run — 2026-09-15 21:01 KST

- Image `freqtrade-v3-demo-auto:66bf69d` (`sha256:41fb5c67…`) and test image built
  from source `66bf69d`; host-side suite against an isolated schema:
  `415 passed, 1 failed` (manifest CLI test needs a `.git` directory the image
  does not ship).
- Two-episode repetition verification with a forced kill and same-identity
  restart completed on Demo: containers `phase1-demo-verify-repeat-20260915`
  (exit 137, killed deliberately) and `…-restart1` (exit 0). Eight fills, two
  automatic residual settlements, stop reason `run_window_exhausted`.
- Ledger: intents `3`, all `CLOSED`; rejected transitions `0`; unresolved recovery
  `0`; unapplied inbox `0`; active commands `0`; open incidents `0`; fills `12`
  all FILLED; settled residuals `0.00000715 + 0.00000715 + 0.00000714 BTC`.
- Policy on the image carries `maximum_quote_age_ms=96`. The week run has not
  been started. Evidence: `evidence/phase1/demo-verify-repeat-20260915/`.

## State after the residual settlement — 2026-09-15 19:29 KST

- Source `b6d3bbd` was shipped via `git archive` and built into
  `freqtrade-v3-demo-auto:b6d3bbd` (image `sha256:afed612e…`) and a test image
  `freqtrade-v3-tests:b6d3bbd`. The regression suite ran on the host against an
  isolated schema of `phase1-postgres`: `404 passed, 1 failed`; the failure was the
  manifest CLI test needing `git` inside the test image, fixed in `42b1a76`.
- Residual settlement (user-approved, order-free): intent
  `09a7f1cf-51d1-43ab-b8a6-fa65041ba6ed` `ABORTING → CLOSED`, `episode_residuals`
  `0.00000715 BTC`, migration 0008 applied, open intents `0`, rejected transitions `0`.
  Account GET before and after: futures `0`, open BTC orders `0`, Spot
  `0.00000715 BTC` unchanged. Container `phase1-residual-settle-20260915` exited 0.
  Evidence: `evidence/phase1/residual-settlement-20260915.json`.
- SLA evidence (read-only): 259 futures exchange-age samples, median 13 ms,
  p99 47.68 ms, proposed `maximum_quote_age_ms=96`; hedge-latency samples `1`
  (insufficient). Policy unchanged. Evidence: `evidence/phase1/sla-evidence-20260915.json`.
- The non-git working copy at `/home/kai/freqtrade-v3` used by the cron jobs was
  synced to the same tracked source (`.env`, reports, and data untouched).
- Walk-forward validation of the updated research code on the server's one-year
  data (180 training days, six 30-day folds, validation 2026-03-17 → 2026-09-13):
  `STOP_BEFORE_CLASSIFIER`, unchanged. Trade counts are identical to the
  2026-09-13 scheduled run; profit factors moved by at most 0.005 from resolving
  fold-boundary exits; drawdowns are now 2.2%–4.2% on the 5%-of-capital basis
  instead of 45%–85% on the 100%-per-trade basis. Profit factor (0.52–0.57),
  negative expectancy, and 0–1 positive folds remain the binding rejections.
  Result: `research_results/validation-b6d3bbd/`. The scheduled `latest` link
  was not changed.
- `phase1-postgres` and `freqtrade_kai` were not modified. No new trading run.

## Phase 1 state before the settlement — 2026-09-15

This section records the last verified state, not a fresh server inspection
performed during the documentation update.

- Project path: `/home/kai/freqtrade-v3`; Phase 1 uses its own PostgreSQL and
  Nautilus Demo execution containers, not the legacy Freqtrade order path.
- `phase1-demo-auto-20260915`: exited 2 after a REST/stream timestamp conflict.
- `phase1-demo-auto-recovery-20260915`: exited 0 after close-only recovery and
  residual detection. Exit 0 does not mean flat or continuous trading enabled.
- Four strategy orders were FILLED/OBSERVED; all four fill-inbox receipts applied.
  Three blocked recovery checks were resolved with the original evidence retained.
- Final Demo account GET: futures `0 BTC`, open BTC orders `0`, Spot
  `0.00000715 BTC`; intent `ABORTING / DUST_REMAINS`. Automatic entries are stopped.
- `phase1-postgres` remained running. The existing `freqtrade_kai` service was not
  modified by this work. The older service description below is historical.
- Source/images, execution times and recovery details:
  [Demo auto runbook](PHASE1_DEMO_AUTO_RUNBOOK.md).
- Evidence: [final account](../evidence/phase1/demo-auto-final-account-20260915.json),
  [initial run](../evidence/phase1/demo-auto-initial-20260915.json),
  [recovery](../evidence/phase1/demo-auto-recovery-20260915.json).

## Historical server snapshot — 2026-08-10

The remaining sections preserve the original dated snapshot. They are not proof
of current container configuration, credentials, schedules, or backup contents.

## Active runtime

- Project path: `/home/kai/freqtrade-v3`
- Container identity: `freqtrade_kai` (inherited from retired V2)
- Local API binding: `127.0.0.1:8080`
- Trade database: `user_data/tradesv3_v3.sqlite`
- Strategy: `V3ShadowStrategy`
- Configuration: dry-run, fixed 50 USDT stake, 1x leverage, `initial_state: running`
- Image: Freqtrade 2026.7 pinned to digest `sha256:50720a4a...a35486`

The active service reuses the former V2 host endpoint, restart policy, health-check pattern, and container identity. It does not reuse the V2 database, models, predictions, strategy, market-data path, logs, or FreqAI image.

Verified startup state:

- container start: `2026-08-10T05:00:16Z`;
- worker state: `RUNNING`;
- Docker health: `healthy`;
- restart count: `0`;
- API ping: `{"status":"pong"}`;
- V3 database: `0` trades, `0` open trades.

## V2 retirement and backup

V2 was stopped and removed with zero open trades. Its SQLite database passed `PRAGMA integrity_check` immediately after shutdown. Its legacy daily-report cron entry was removed; no V2 Compose container, systemd timer, or scheduled command remains active.

The complete V2 project is preserved only on the server:

- archive: `/home/kai/backups/freqtrade-v2/freqtrade-v2-full-20260810T045545Z.tar.zst`
- compressed size: `3,615,018,524` bytes
- SHA-256: `971e4d77ceeebb9b5f1682b8a873ab598d84b5b715338ecd9327141398734bef`
- permissions: `0600`, owner `kai:kai`
- validation: zstd stream test and full tar listing both passed

The archive contains runtime configuration and therefore may contain secrets. It must remain server-local and must never be added to Git or copied into research artifacts.

The common exchange, API, and Telegram report values were transferred directly from the V2 `.env` into the ignored V3 `.env` without being printed. The prior V3 environment files are retained server-side with mode `0600`. The original V2 `.env` was also restricted to mode `0600`.

## Safety boundary

Milestone 1 remains `STOP_BEFORE_CLASSIFIER`. The running service is an infrastructure/API/health test only: `V3ShadowStrategy` deterministically emits zero long and short entries. No V2 trading logic, FreqAI model, or rejected deterministic candidate is active.

## Research data and result

The isolated V3 research directory contains complete Binance futures candles from 2025-08-10 through 2026-08-10:

- BTC and ETH 15-minute candles: 35,084 rows per pair, ending at `2026-08-10T10:45:00Z`;
- BTC and ETH one-hour candles: 8,771 rows per pair, ending at `2026-08-10T10:00:00Z`;
- cadence coverage: 100% for all four decision/regime datasets.

The final server walk-forward result is stored in `research_results/milestone-1` and remains `STOP_BEFORE_CLASSIFIER`.

The verified full-year scheduled walk-forward is stored under `research_results/scheduled/20260810T110441Z`, with `latest` pointing to that immutable run. It used 180 training days, six 30-day validation folds, and a six-hour embargo, covering `2025-08-15T04:45:00Z` through `2026-08-10T10:45:00Z`. No portfolio was promoted. The strongest active diagnostic was trend-pullback short with profit factor `0.601`, negative expectancy, maximum drawdown `49.0%`, and zero positive folds out of six. This remains a rejection, not a deployable strategy.

## Reports and schedules

The host timezone is verified as `Asia/Seoul`. The host crontab contains only V3 jobs and was installed through `deploy/install_server_cron.sh`, which also creates the private report and log directories:

- daily operations report at `23:00` KST;
- weekly data refresh, research run, and report at `23:10` KST every Sunday.

Manual daily and weekly Telegram deliveries both succeeded. Host-owned Markdown copies use mode `0600` under `reports/daily` and `reports/weekly`; cron logs use `reports/logs`. Research and report jobs return non-zero on infrastructure or Telegram delivery failure. No job modifies the active strategy or promotes a research candidate.

## Verification commands

```bash
cd /home/kai/freqtrade-v3
docker compose config --quiet
docker compose ps
curl --fail http://127.0.0.1:8080/api/v1/ping
docker compose logs --tail 100 freqtrade_v3_shadow
./scripts/run_operations_report.sh daily
crontab -l
```

Source checks run locally and in GitHub Actions through `./scripts/run_checks.sh`. Live-capital configuration is not part of this project state.
