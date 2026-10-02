# Phase 2b Research Report

- generated_at: `2026-10-02T04:18:11Z`
- decision: **STOP_NO_EDGE**
- registration: `docs/PHASE2B_PREREGISTRATION.md`
- universe: BTC, ETH, SOL, BNB, XRP, DOGE, ADA, LINK
- panel: 2025-06-23T00:00 → 2026-10-01T23:00
- Stage B evaluation: 2026-07-31 → 2026-10-01 (untouched by Phase 2)

## Stage A — Phase 2 folds (contaminated, diagnostic)

| Hypothesis | Cost | Days | PF | Expectancy/day | MDD | Positive folds | Fold conc. | Asset conc. | PBO | Pass |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| H3 | normal | 270 | 0.577 | -0.000123 | 3.41% | 0 | 1.00 | 0.36 | 0.60 | FAIL |
| H3 | stress | 270 | 0.576 | -0.000123 | 3.41% | 0 | 1.00 | 0.36 | 0.60 | FAIL |
| H3T | normal | 270 | 0.566 | -0.000126 | 3.56% | 0 | 1.00 | 0.37 | 0.63 | FAIL |
| H3T | stress | 270 | 0.553 | -0.000131 | 3.65% | 0 | 1.00 | 0.37 | 0.57 | FAIL |

## Stage B — confirmatory window

| Hypothesis | Cost | Selected | Net PnL | Funding | Fees | Slippage | MDD | Cycles | Verdict |
|---|---|---|---:|---:|---:|---:|---:|---:|---|
| H3 | normal | H3 W=336h k=3 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00% | 0 | UNDECIDABLE |
| H3 | stress | H3 W=336h k=3 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00% | 0 | UNDECIDABLE |
| H3T | normal | H3T W=336h k=3 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00% | 0 | UNDECIDABLE |
| H3T | stress | H3T W=336h k=3 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00% | 0 | UNDECIDABLE |

## P&L decomposition and activity (USDT; Stage A sums over validation folds)

| Hypothesis | Cost | Stage | Total | Price | Funding | Fees | Slippage | Trades | Episodes | Maker fill rate | Maker notional share | Turnover x sleeve/yr |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| H3 | normal | A | -6.68 | -6.62 | 0.42 | 0.33 | 0.15 | 24 | 2 | 94.4% | 72.4% | 7.9 |
| H3 | normal | B | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0 | 0 | n/a | n/a | 0.0 |
| H3 | stress | A | -6.69 | -6.62 | 0.42 | 0.33 | 0.16 | 24 | 2 | 94.4% | 72.4% | 7.9 |
| H3 | stress | B | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0 | 0 | n/a | n/a | 0.0 |
| H3T | normal | A | -6.85 | -6.38 | 0.42 | 0.58 | 0.32 | 24 | 2 | n/a | 0.0% | 7.9 |
| H3T | normal | B | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0 | 0 | n/a | n/a | 0.0 |
| H3T | stress | A | -7.12 | -6.38 | 0.42 | 0.58 | 0.58 | 24 | 2 | n/a | 0.0% | 7.9 |
| H3T | stress | B | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0 | 0 | n/a | n/a | 0.0 |

## Phase 2 H1 reference (same Stage A folds, taker, 8-hour decisions)

| Cost | Trades | Episodes | Funding | Fees | Slippage | Total |
|---|---:|---:|---:|---:|---:|---:|
| normal | 347 | 15 | 3.38 | 9.45 | 4.36 | -14.14 |
| stress | 347 | 15 | 3.17 | 9.45 | 9.45 | -25.02 |

## Stage A fold selections (H3)

| Cost | Fold | Selected on training | Train Sharpe | Validation return | PF |
|---|---:|---|---:|---:|---:|
| normal | 0 | H3 W=168h k=3 | -0.16 | -3.34% | 0.577 |
| normal | 1 | H3 W=168h k=3 | -0.16 | 0.00% | 0.000 |
| normal | 2 | H3 W=336h k=3 | 0.10 | 0.00% | 0.000 |
| normal | 3 | H3 W=336h k=3 | 0.10 | 0.00% | 0.000 |
| normal | 4 | H3 W=336h k=3 | 0.64 | 0.00% | 0.000 |
| normal | 5 | H3 W=336h k=3 | 0.64 | 0.00% | 0.000 |
| stress | 0 | H3 W=168h k=3 | -0.21 | -3.35% | 0.576 |
| stress | 1 | H3 W=168h k=3 | -0.21 | 0.00% | 0.000 |
| stress | 2 | H3 W=336h k=3 | 0.05 | 0.00% | 0.000 |
| stress | 3 | H3 W=336h k=3 | 0.05 | 0.00% | 0.000 |
| stress | 4 | H3 W=336h k=3 | 0.64 | 0.00% | 0.000 |
| stress | 5 | H3 W=336h k=3 | 0.64 | 0.00% | 0.000 |

## Interpretation

H3 passes only if Stage A and Stage B both pass under both cost regimes. Stage A reuses folds whose Phase 2 results were known when H3 was designed, so it cannot pass H3 alone. H3T is a taker diagnostic and is never promoted. Maker fills use a trade-through rule on hourly candles, which cannot see queue position; live fill rates can be lower. Passing authorizes only a Demo/shadow observation, never real capital.
