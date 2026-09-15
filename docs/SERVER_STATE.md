# Server state

## Latest verified Phase 1 state — 2026-09-15 19:29 KST

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
