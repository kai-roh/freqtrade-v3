# 0013 — Phase 2b maker funding carry result: STOP_NO_EDGE

- Status: Accepted; corrected 2026-10-02 after review (see the last two sections)
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

## Corrections (2026-10-02, after an external review)

The decision stands: `STOP_NO_EDGE`, no promotion. The statements above are
corrected as follows.

1. **Stage B was not fully untouched.** Phase 2 (Decision 0009) computed its PBO
   matrix to the panel end, 2026-09-16, over 437 rows. So 2026-07-31 to 09-16
   entered a Phase 2 gate statistic. It was used only inside that one aggregate,
   never for training, selection, or exits, but "no Phase 2 run used it" is false.
   Only 2026-09-17 to 10-01 was fully unused. The Phase 2 PBO matrix now ends at
   the last fold's exit observation (`Phase2Config.pbo_through_panel_end=False`).
   The flag `--historical-pbo-through-panel-end` reproduces the recorded run
   exactly. With the bounded window, Phase 2 PBO is H1 0.79 (normal) and 0.77
   (stress), and H2 0.39 and 0.17. The Phase 2 decision does not change.
2. **Stage A day counts.** "270 days" is six overlapping 45-day windows joined
   together: 30 validation days, 14 exit-observation days, and one boundary day.
   It is not one continuous account. Per-day expectancy, drawdown, and annual
   turnover share that denominator. The Decision 0009 figures have the same
   limitation. Stage B's 62 days are recorded as 63 for the same boundary reason.
3. **"0/6 positive folds".** Only fold 0 traded. Folds 1 to 5 had no trade and a
   0% return. There were two episodes in total. This is not repeated loss across
   six regimes. PBO 0.60 on a grid that rarely trades is dominated by ties. It is
   not a probability of failure.
4. **"94% maker fills"** is 17 of 18 judgements by the hourly trade-through model.
   It is not an observed rate. The model cannot see queue position, partial
   fills, or whether a post-only order at the open would be rejected for
   crossing (Binance rejects post-only orders that would take liquidity). The
   result supports "lower cost under the registered approximation", not "maker
   execution verified".
5. **347 to 24 trades** cannot be credited to low turnover. The filter (fixed
   1 bp), window set (48h removed), cadence, minimum hold, rebalance band, and
   execution all changed at once, and the opportunity set itself shrank. The
   maker effect proper is H3 against H3T: costs 0.423 USDT lower, price result
   0.246 worse, net 0.177 better.
6. **Lower filters.** "Cannot cover even maker round trips plus price risk" was
   too strong. At 0.5 bp per settlement, an all-maker round trip (0.12 USDT on
   300 USDT gross) is repaid by funding in about 5.3 days. The binding constraint
   is price risk, taker fallback, and stop costs. The 4.1% a year is gross on the
   sleeve. At a 20% allocation it is about 0.8% of total capital, before costs
   and price P&L.
7. **"The family failed twice"** overstates the evidence. Phase 2 H1 is a tested
   failure with 15 episodes. Phase 2b produced two episodes: a gate failure with
   weak evidence about the edge. The accurate summary is that the registered
   gate was not met and the recent window had no opportunity. In the few trades
   taken, price risk overwhelmed the carry. Confirmation independence and some
   aggregate metrics are limited, as listed here.
8. **Reproducing Phase 2 is not the same as verifying the contract.** The Phase 2b
   simulator inherits Phase 2's structure. The stop is checked at hourly opens.
   When entries are blocked, held legs stay without replacement, which can leave
   unequal leg counts. That happened in episode 2 below.

## Episode diagnosis (`research_results/phase2b/EPISODE_TRACE.md`)

The H3 normal-cost fold 0 replay matches the recorded fold decomposition exactly.

| | Episode 1 | Episode 2 | Total |
|---|---|---|---:|
| Window (UTC) | 02-05 01:00 to 16:00 (15 h) | 02-07 01:00 to 02-21 02:00 (337 h) | |
| Price P&L | −4.337 | −2.284 | −6.622 |
| Funding | +0.002 | +0.419 | +0.421 |
| Costs | 0.334 | 0.143 | 0.477 |
| Net | −4.670 | −2.008 | −6.678 |
| Long basket price / short basket price | −14.94 / +10.60 | −4.41 / +2.12 | |
| Net beta-weighted notional (30-day beta to BTC) | +35.0 USDT | +30.8 USDT | |

- **Beta mismatch is the main cause.** The low-funding names chosen as longs had
  higher BTC beta than the shorts: SOL 1.29, XRP 1.21, and DOGE 1.37 against
  BTC 1.00 and BNB 0.86 in episode 1. Both baskets were dollar-neutral but net
  long about 10–12% of gross in beta terms. In episode 1 the universe fell 8.6%
  in 15 hours. The long basket fell further, and the daily stop closed
  everything at −2.2%. This one episode is 70% of the total loss, and funding
  played no part in it.
- **A partial basket made episode 2 worse.** On 02-14 the ranking dropped the BTC
  short while new entries were blocked (spread 0.91 bp, falling to 0.54 bp). For
  169 of 338 hours the basket held two shorts against three longs, net long 25
  USDT on average and 59 at most. Price P&L in those hours was −2.88 USDT, more
  than the episode's whole price result.
- **Funding came in at half of what was expected.** Realized funding was 0.421
  USDT against 0.804 implied by the trailing scores at entry. For example, the
  SOL long earned 0.196 against an implied 0.436. Trailing funding overstated
  forward funding.
- **The minimum hold is inconclusive.** The lock kept two legs against the
  ranking. During the locked window the BTC short earned +1.92 and the ETH long
  lost −3.58. The replacement legs were not simulated, so there is no net
  verdict.
- **Costs were minor:** 0.477 USDT, 7% of the loss.

Any future cross-sectional registration needs:

- beta-neutral sizing or same-beta pairing, instead of dollar neutrality alone;
- a full-basket exit or forced replacement whenever entries are blocked, so leg
  counts never become unequal;
- non-overlapping aggregation of fold returns;
- forward rather than trailing funding in the economic check;
- confirmation data strictly after 2026-10-01.
