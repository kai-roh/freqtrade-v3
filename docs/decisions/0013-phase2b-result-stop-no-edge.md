# 0013 — Phase 2b maker funding carry result: STOP_NO_EDGE

- Status: Accepted
- Date: 2026-10-02

## Context

The contract registered in Decision 0012 (`docs/PHASE2B_PREREGISTRATION.md`, frozen
in `db96fb8`, pre-results clarifications in `aeb2828`) was run unchanged.

- Data: the frozen Phase 2 panel (all 24 hashes verified) extended to
  2026-10-01 23:00 UTC (`evidence/phase2b/data-manifest.json`). The fresh download
  matched the frozen rows exactly where they overlapped.
- Artifacts: `research_results/phase2b/REPORT.md` and `results.json`.
- The Phase 2 simulator was not modified. It reproduces the recorded Phase 2
  results exactly, and a regression test pins one fold.

## Result

| Hypothesis | Cost | Stage A PF | Stage A positive folds | Stage A PBO | Stage B trades | Stage B verdict |
|---|---|---:|---:|---:|---:|---|
| H3 (maker) | normal | 0.577 | 0/6 | 0.60 | 0 | UNDECIDABLE |
| H3 (maker) | stress | 0.576 | 0/6 | 0.60 | 0 | UNDECIDABLE |
| H3T (taker, diagnostic) | normal | 0.566 | 0/6 | 0.63 | 0 | UNDECIDABLE |
| H3T (taker, diagnostic) | stress | 0.553 | 0/6 | 0.57 | 0 | UNDECIDABLE |

H3 fails Stage A on expectancy, profit factor, positive folds, fold
concentration, and PBO. Stage B produced no trade, so it cannot be judged.
Under the registration (§8), H3 must pass both stages, so it is rejected.

### Why there were almost no trades

The registered entry filter needs a short-minus-long trailing funding spread of
at least 1.0 bp per settlement. Measured at each 00:00 decision on this
eight-symbol universe:

| Window, legs per side | Stage A validation: days at or above 1 bp | Stage B: median spread | Stage B: days at or above 1 bp |
|---|---:|---:|---:|
| 168h, k=2 | 13% | 0.40 bp | 0% |
| 168h, k=3 | 5% | 0.31 bp | 0% |
| 336h, k=2 | 7% | 0.32 bp | 0% |
| 336h, k=3 | 3% | 0.27 bp | 0% |

Funding dispersion across these large-cap perps narrowed in August and
September 2026. In the confirmatory window the filter never opened, for any
registered grid point. Over Stage A, H3 traded only in fold 0: 24 trades, two
episodes, gross funding 0.42 USDT, and a price loss of 6.62 USDT.

### What the maker change did and did not do

- Execution worked as intended in the model. 94% of maker attempts filled on
  the trade-through rule, and 72% of traded notional was maker. Over the same 24
  trades, fees fell from 0.58 to 0.33 USDT against the taker diagnostic.
- Turnover dropped as intended: 24 trades against 347 for Phase 2 H1 on the same
  folds.
- Neither change can matter while gross funding is this small. With 150 USDT
  per side, a spread of 0.5 bp per settlement earns about 0.02 USDT a day, about
  4% a year on the 200 USDT sleeve. That is before costs, and the price risk of
  a dollar-neutral but not beta-neutral basket is larger.

## Decision

`STOP_NO_EDGE`. H3 is rejected, and H3T was only a diagnostic. No shadow
observation, no parameter change, and no machine learning follow from this
result (Decision 0002).

## What this does and does not say

- It says that on eight Binance USD-M large-cap perpetuals, at a 1 bp per
  settlement filter, the cross-sectional funding spread was too rare and too
  small to fund a basket. In the untouched window it never reached the filter.
  Cheaper execution and lower turnover do not create the missing gross carry.
- It does not test lower filters, shorter windows, or a wider or less liquid
  universe. Each of those would be a new registration. Lowering the filter would
  admit spreads whose funding cannot cover even maker round trips plus price
  risk, judged by the numbers above. A wider universe brings in less liquid
  symbols, with their own selection, liquidity, and minimum-notional problems.
- Stage B data (2026-07-31 to 2026-10-01) has now been used once. Any future
  confirmatory test needs data after 2026-10-01.

## Consequences

- The funding cross-section family on this universe has failed two
  registrations: taker at 8-hour decisions (Decision 0009), and maker at daily
  decisions (this decision). Further work on this family is not recommended
  without a materially different source of carry.
- Phase 3 still has no candidate strategy.
