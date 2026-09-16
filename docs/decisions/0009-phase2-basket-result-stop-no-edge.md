# 0009 — Phase 2 basket research result: STOP_NO_EDGE

- Status: Accepted
- Date: 2026-09-17

## Context

The pre-registered Phase 2 contract (`docs/PHASE2_PREREGISTRATION.md`, frozen in
commit `3a836f8`, data frozen in `evidence/phase2/data-manifest.json`) was run
unchanged on Binance USD-M data for eight perpetuals from 2025-06-23 to
2026-09-16 with six purged walk-forward folds (validation windows 2026-01-17 to
2026-07-16). Result artifacts: `research_results/phase2/REPORT.md` and
`results.json`.

## Result

Neither hypothesis passed any cost regime. Daily portfolio net returns on the
200 USDT sleeve:

| Hypothesis | Cost | PF | Expectancy/day | MDD | Positive folds | PBO |
|---|---|---:|---:|---:|---:|---:|
| H1 funding carry | normal | 0.869 | −0.027% | 12.4% | 4/6 | 0.77 |
| H1 funding carry | stress | 0.766 | −0.047% | 16.6% | 3/6 | 0.76 |
| H2 simple reversal | normal | 0.755 | −0.075% | 25.4% | 2/6 | 0.43 |
| H2 simple reversal | stress | 0.728 | −0.085% | 26.5% | 2/6 | 0.20 |

The mandatory decomposition answers the registered questions:

- H1 collected funding (+3.38 USDT over the validation folds) but paid 13.81 USDT
  in fees and slippage and lost 3.70 USDT on price. Costs exceeded funding by
  about four times; the carry was real but too small for taker execution at this
  size and turnover.
- H1's training selection did not transfer: PBO 0.77 means the in-sample best
  grid point was usually below the out-of-sample median. Selected windows flipped
  between 48h and 168h and between k=2 and k=3 across folds.
- H1 profit concentrated in one asset (BTC under normal costs, ETH under stress,
  each above the 50% share), so even the positive folds were not a basket effect.
- H2 lost mainly on price (−21.5 USDT) with fees of 13.3 USDT; the daily stop
  fired in most episodes. Simple cross-sectional reversal at daily cadence has no
  edge here after costs.

## Decision

`STOP_NO_EDGE`. No shadow observation, no venue change, no machine learning, and
no parameter tuning on these results. Both hypotheses are rejected under the
registered contract.

## What this does and does not say

- It says: with taker execution, hourly data, an eight-asset universe, and a
  200 USDT sleeve, neither registered basket family has a positive post-cost
  expectancy on Binance USD-M in this period.
- It does not say that funding carry has no economic content. Funding income
  was positive; costs and price risk consumed it. Any follow-up that changes
  execution (maker/post-only), decision cadence, universe, or sizing is a **new
  hypothesis** and needs a new registration document before code changes.
- Two months of data after the last validation window (2026-07-16 to 2026-09-16)
  were unused because folds anchor at the start of the panel; they remain
  available for an untouched forward check of any future registration.

## Consequences

- Phase 3 (small real capital) has no candidate strategy. The Phase 1 Demo
  observation continues as infrastructure evidence only.
- The next admissible research step is a new pre-registration, not a rerun.
