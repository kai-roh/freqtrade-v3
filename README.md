# freqtrade-v3

Clean-room rebuild of the Kai Freqtrade strategy research stack.

V3 keeps the proven Freqtrade/Docker operations boundary, but does not inherit the V2 prediction target, feature expansion, entry score, dynamic stake, exit stack, models, or trade database.

## Safety state

- Research and dry-run only.
- Real-money trading is not configured or authorized.
- Default leverage is 1x and stake size is fixed.
- BTC and ETH are the only initial research pairs.
- V2 and V3 use different container names, ports, databases, model identifiers, logs, and result directories.
- Machine-learning work is blocked because the deterministic baselines failed the promotion review.

## First milestone

1. Freeze a reproducible V2 evidence manifest.
2. Validate data coverage and create purged chronological folds.
3. Compare no-trade, trend/pullback, and volatility-breakout baselines on 15-minute candles.
4. Apply 0.20% and 0.30% round-trip cost stress.
5. Decide whether there is enough stable edge to justify a cost-aware classifier.

On a host with Docker:

```bash
cp .env.example .env
./scripts/download_research_data.sh
./scripts/run_walk_forward.sh
```

The shadow container is deliberately configured in the `stopped` state. Its current strategy adapter emits zero entries, so research results cannot accidentally activate trading.

## Project layout

```text
configs/                 Isolated research and dry-run configuration
evidence/                Hashes and aggregate metrics; never raw secrets/runtime data
user_data/strategies/    Thin Freqtrade adapter
v3/                      Pure features, baseline, risk, metrics, and validation logic
scripts/                 Evidence, data, walk-forward, and verification entry points
tests/                   Causal, isolation, and reproducibility tests
docs/decisions/          Decision records and stop conditions
```

## Promotion policy

A candidate must show positive post-cost expectancy, profit factor at least 1.15, maximum drawdown at most 10%, at least four positive folds out of six, and no dominant fold/pair contribution above 50%. A separate shadow dry-run must then run for at least 60 days and 100 closed trades, whichever takes longer.

Passing research gates does not authorize live trading.

## Status

Milestone 1 completed on 2026-08-10 with `STOP_BEFORE_CLASSIFIER`. At 0.20% round-trip cost, every active BTC/ETH baseline had negative expectancy, profit factor below 0.67, and zero positive portfolio folds. The fail-closed Freqtrade adapter remains stopped and emits no entries.

See the [Milestone 1 report](research_results/milestone-1/REPORT.md), [Decision 0001](docs/decisions/0001-clean-rebuild.md) for the architecture boundary, and [Decision 0002](docs/decisions/0002-stop-before-classifier.md) for the research stop decision.

The verified host layout and intentionally stopped runtime state are recorded in [Server state](docs/SERVER_STATE.md).
