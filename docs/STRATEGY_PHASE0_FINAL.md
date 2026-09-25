# V3 Strategy Contract - Phase 0 Final

Baseline date: 2026-08-19 KST. Working capital: 1,000 USDT. Runtime target:
Oracle Tokyo ARM64, Ubuntu 24.04.

This document is the repository copy of the final Phase 0 strategy contract. It
freezes the project direction before any new live execution work.

## Core Conclusion

V2 did not prove positive gross alpha, and high leveraged execution cost turned
that weak signal into a clearly negative net result. The V2 dry-run database
showed 194 closed trades, -183.8396 USDT cumulative PnL, approximately 169.07
USDT simulated fees, and approximately -14.77 USDT gross PnL after fee
restoration.

The V3 goal is therefore not "build a profitable bot first." The goal is a
judgment-capable research and execution pipeline. "No edge" and "not
implementable at this capital size" are valid outputs.

## Phase 0 Admission Rules

- No strategy research starts without a cost ledger.
- No reviewed or promoted run is valid without the seven reproducibility fields:
  Git commit SHA, container image digest, dependency lock hash, config hash,
  model artifact hash, data snapshot ID, and timerange.
- IID trade-level confidence intervals are not sufficient for dependent trades.
  Block bootstrap must use daily portfolio PnL or exposure clusters, never
  individual trades as the resampling unit.
- Instrument conformance is checked before execution design: min notional,
  size precision, asset-index availability, reject behavior, leverage, quote
  freshness, and full intent record.
- Passing research gates does not authorize live trading.

## Cost Ledger Scope

Every strategy proposal must account for:

- leg turnover and venue fee tier;
- market impact and adverse selection;
- funding or borrow cost;
- legging loss;
- rebalance cost;
- transfer and conversion cost;
- post-only rejection, cancellation, and repricing cost.

The first implementation lives in `v3.costs`.

## Block Bootstrap Registration

Before running a bootstrap, the operator must fix:

- sample unit: daily portfolio PnL or exposure cluster;
- block definition and block length;
- iterations and seed;
- two-sided test direction.

The first implementation lives in `v3.bootstrap`.

The V2 run was registered before reading results and then completed on
2026-08-25. The primary five-day 95% interval and every registered sensitivity
interval were below zero. The exact evidence and interpretation boundary are in
`docs/V2_BOOTSTRAP_RESULTS.md`.

## Instrument Preflight

Standard Hyperliquid perps use a 10 USD minimum notional baseline. The project
policy requires 3x headroom, so a standard perps leg must be at least 30 USD
unless the instrument-specific preflight proves a different threshold.

Preflight fails closed when:

- leg notional is below min-notional headroom;
- leverage exceeds 2x;
- quote age exceeds the strategy SLA;
- any intent field is blank.

Static venue conformance lives in `v3.instruments`; final order admission and
the mandatory six-field intent record live in `v3.preflight`. Hyperliquid
instrument metadata is captured read-only by `v3.hyperliquid`; its response hash
is retained alongside the derived asset index and precision rules. Per venue
rules, a perpetual price has at most five significant figures and no more than
`6 - szDecimals` decimal places, while integer prices remain valid regardless
of significant-figure count.

## Phase 1 Entry Condition

Phase 1 is an infrastructure verification stage, not a profit gate. It can start
after the following Phase 0 controls are present:

- leverage fail-closed behavior is verified;
- quote freshness and emergency hedge behavior are verified;
- cost ledger and reproducibility manifest are attached to the run.

The completed V2 bootstrap gates the V2 diagnostic wording and any future
V2-style directional revival. It does not gate Binance Demo plumbing, ledger,
state-machine, or fault-injection work. Credentialed venue checks gate only the
integration tests that require them.

Phase 1 uses Binance Demo Spot plus USD-M perpetuals. Hyperliquid order
submission is deferred because its UI BTC spot maps to UBTC on HyperCore and
would add bridge and UBTC/BTC basis risks to the infrastructure PoC.
