# 0001 — Rebuild the strategy core, retain operations

- Status: Accepted
- Date: 2026-08-10

## Context

At the 2026-08-10 evidence cutoff, the authoritative V2 server dry-run had 194 closed trades, no open trades, a net loss of 183.8396 USDT, and profit factor 0.365. The post-change evaluation phase also failed with 36 additional trades and 44.2132 USDT of additional loss relative to its 158-trade baseline.

FreqAI retraining was operational, but the live prediction history showed negative R² on every active pair, near-zero correlation with realized returns, and negative fee-adjusted edge for both long and short selections. V2 entry ranking, rule scoring, and dynamic sizing reused this weak prediction.

## Decision

Create a separate `freqtrade-v3` repository. Retain the Freqtrade container/runtime pattern, environment-injected secrets, health checks, data-download tooling, isolated backtests, reporting, and evidence collection. Rebuild the label, features, model contract, entry policy, risk, exit policy, and validation from clean modules.

V2 remains a frozen dry-run evidence source. V3 must not import V2 strategy or model modules and must use separate runtime artifacts.

## Required sequence

1. Freeze V2 evidence without copying secrets, raw databases, models, predictions, or logs into Git.
2. Acquire sufficient BTC/ETH data and build purged chronological walk-forward folds.
3. Test deterministic 15-minute baselines at conservative costs and 1x fixed risk.
4. Build a cost-aware classifier only if the deterministic milestone justifies it.
5. Run V3 in an isolated dry-run for at least 60 days and 100 trades before any separate live-capital decision.

## Rejected alternatives

- Continue tuning V2 thresholds: rejected because no stable profitable cohort was found and attribution is already weak.
- Rename and copy the V2 strategy: rejected because it would preserve the failed coupling.
- Build a custom exchange/trading engine: rejected because the operations layer is not the root cause.

## Consequences

- Research restarts from simple controls and fail-closed promotion gates.
- Machine learning is optional, not a project requirement.
- Dynamic stake and leverage above 1x are disabled during discovery.
- Real-money trading remains outside the project scope.
