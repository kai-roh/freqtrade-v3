# Server state — 2026-08-10

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

The common exchange and API values were transferred directly from the V2 `.env` into the ignored V3 `.env` without being printed. The prior V3 environment file is retained server-side as `.env.pre-v2-infra-migration-20260810T045545Z`, also with mode `0600`.

## Safety boundary

Milestone 1 remains `STOP_BEFORE_CLASSIFIER`. The running service is an infrastructure/API/health test only: `V3ShadowStrategy` deterministically emits zero long and short entries. No V2 trading logic, FreqAI model, or rejected deterministic candidate is active.

## Research data and result

The isolated V3 research directory contains complete Binance futures candles from 2025-08-10 through 2026-08-10:

- BTC and ETH 15-minute candles: 35,044 rows per pair;
- BTC and ETH one-hour candles: 8,761 rows per pair;
- cadence coverage: 100% for all four decision/regime datasets.

The final server walk-forward result is stored in `research_results/milestone-1` and remains `STOP_BEFORE_CLASSIFIER`.

## Verification commands

```bash
cd /home/kai/freqtrade-v3
docker compose config --quiet
docker compose ps
curl --fail http://127.0.0.1:8080/api/v1/ping
docker compose logs --tail 100 freqtrade_v3_shadow
```

Source checks run locally and in GitHub Actions through `./scripts/run_checks.sh`. Live-capital configuration is not part of this project state.
