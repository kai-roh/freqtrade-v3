# Server state — 2026-08-10

## Verified deployment boundary

- V3 project path: `/home/kai/freqtrade-v3`
- V3 container name: `freqtrade_v3_shadow`
- V3 API binding if deliberately started later: `127.0.0.1:8081`
- V3 trade database: `user_data/tradesv3_v3.sqlite`
- V3 strategy: `V3ShadowStrategy`
- V3 configuration: dry-run, fixed 50 USDT stake, 1x leverage, `initial_state: stopped`
- Research/runtime image: Freqtrade 2026.7, pinned to image digest `sha256:50720a4a...a35486`

V3 does not reuse the V2 container name, API port, database, strategy, FreqAI identifier, models, predictions, or logs. Exchange and API credentials remain only in the ignored host `.env` file.

## Runtime decision

The V3 long-running container is intentionally not started. Milestone 1 returned `STOP_BEFORE_CLASSIFIER`, and the strategy adapter emits zero entries. Starting a shadow service with a rejected signal family would add operational activity without producing valid research evidence.

The existing V2 container `freqtrade_kai` was not restarted or reconfigured during the V3 build. At final validation it remained running, healthy, and at zero restarts.

## Research data and result

The isolated V3 data directory contains complete Binance futures candles from 2025-08-10 through 2026-08-10:

- BTC and ETH 15-minute candles: 35,044 rows per pair;
- BTC and ETH one-hour candles: 8,761 rows per pair;
- cadence coverage: 100% for all four decision/regime datasets.

The deterministic walk-forward was executed on the server with a fixed artifact timestamp. Outputs are stored in `research_results/milestone-1`, with owner/group-only write permission. Raw candles remain ignored and are not copied to GitHub.

## Safe verification commands

```bash
cd /home/kai/freqtrade-v3
docker compose config --quiet
docker compose run --rm --no-deps freqtrade_v3_shadow list-strategies \
  --config /freqtrade/configs/dry-run.json
V3_GENERATED_AT=2026-08-10T01:50:01Z ./scripts/run_walk_forward.sh
```

These commands validate configuration, load the stopped strategy in a transient container, and reproduce research; they do not start the long-running trading service. Source tests run locally and in GitHub Actions through `./scripts/run_checks.sh`. Live-capital setup is not part of this project state.
