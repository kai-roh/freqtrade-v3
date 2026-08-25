# freqtrade-v3

The repository name is historical. Freqtrade is retained only for legacy
research comparison and a zero-entry shadow runtime; the Phase 1 execution
engine is NautilusTrader.

Clean-room rebuild of the Kai crypto strategy research and execution stack.

V3 keeps the proven Freqtrade/Docker operations boundary, but does not inherit the V2 prediction target, feature expansion, entry score, dynamic stake, exit stack, models, or trade database.

## Safety state

- Research and dry-run only.
- Real-money trading is not configured or authorized.
- Default leverage is 1x and stake size is fixed.
- BTC and ETH are the only initial research pairs.
- After V2 retirement, V3 reuses its `freqtrade_kai` container identity and localhost port 8080 so the existing host tunnel and monitoring continue to work. The V3 database, strategy, data, logs, and results remain separate.
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

The shadow container runs as a dry-run infrastructure test on the retired V2 endpoint. Its current strategy adapter emits zero entries, so starting the service cannot activate a rejected trading policy.

## Project layout

```text
configs/                 Isolated research and dry-run configuration
examples/phase0/         Non-authoritative Phase 0 CLI input schemas
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

Milestone 1 completed on 2026-08-10 with `STOP_BEFORE_CLASSIFIER`. A near-full-year run with 180 training days and six 30-day validation folds reached the same decision: the strongest active portfolio had profit factor 0.601, negative expectancy, 49.0% maximum drawdown, and zero positive folds out of six. The Freqtrade runtime is active only for infrastructure validation; its fail-closed adapter emits no entries.

Phase 0 foundation development started on 2026-08-25. The repository now has
an exact cost ledger, seven-field run manifest, instrument/order preflight,
read-only Hyperliquid metadata capture, pre-registered block-bootstrap runner,
snapshot-to-order preflight generation, and a fail-closed check in front of the
retained Freqtrade shadow runtime. These are infrastructure controls, not a
promoted strategy.

See the [Milestone 1 report](research_results/milestone-1/REPORT.md), [Decision 0001](docs/decisions/0001-clean-rebuild.md) for the architecture boundary, and [Decision 0002](docs/decisions/0002-stop-before-classifier.md) for the research stop decision.

The verified host migration and fail-closed runtime state are recorded in [Server state](docs/SERVER_STATE.md) and [Decision 0003](docs/decisions/0003-reuse-v2-infrastructure.md).

The full retirement, backup, environment handoff, and rollback boundary are documented in [V2 to V3 infrastructure migration](docs/MIGRATION_V2_TO_V3.md).

Daily and weekly Telegram reports, along with the locked weekly one-year walk-forward pipeline, are documented in [Reporting and scheduled research](docs/REPORTING_AND_RESEARCH.md).

[Decision 0004](docs/decisions/0004-report-without-auto-promotion.md) records why scheduled measurement can never promote or deploy a strategy automatically.

The Phase 0 final strategy contract and first development slice are recorded in
[V3 Strategy Contract - Phase 0 Final](docs/STRATEGY_PHASE0_FINAL.md) and
[Phase 0 Development Notes](docs/PHASE0_DEVELOPMENT.md).

The dependent-return validation contract and completed V2 result are documented
in [Block Bootstrap Contract](docs/BLOCK_BOOTSTRAP.md) and
[V2 Fee-only Block Bootstrap Results](docs/V2_BOOTSTRAP_RESULTS.md).

The V2 daily portfolio bootstrap choices were frozen before execution in
[V2 Fee-only Block Bootstrap Pre-registration](docs/V2_BOOTSTRAP_PREREGISTRATION.md).

The hash-verified V2 fee-only preparation and the strict boundary between
fixed-entry exit replay and full-strategy reruns are documented in
[V2 Fee-only Counterfactual Preparation](docs/V2_COUNTERFACTUAL.md).

Execution dependencies and the future NautilusTrader image are governed by the
[Dependency and Execution-Engine Pinning Policy](docs/DEPENDENCY_POLICY.md).

The approved 6-8 week implementation sequence, simulation-only boundary,
Binance Demo venue decision, 13-table ledger, 18-transition state machine, and
fault-injection gates are defined in
[Phase 1 Carry Execution Infrastructure](docs/PHASE1_IMPLEMENTATION_PLAN.md) and
[Decision 0006](docs/decisions/0006-phase1-binance-demo-carry.md).
