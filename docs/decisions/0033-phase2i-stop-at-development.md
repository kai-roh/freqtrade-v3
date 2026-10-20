# 0033 — Phase 2i stopped at the development check: maker execution is not enough

- Status: Accepted
- Date: 2026-10-20 (KST)

## Result (2022-04-01..2022-12-30, training period; registered check)

No configuration reached the viability bar of a net Sharpe of at least 1.5 with at
least 55% positive weeks. The out-of-sample window, 2023-01..2026-09, was **not
computed**. Results are in `research_results/phase2i/dev-results.json`. The 15m
manifest is `a4027dc1…`.

| Best by horizon | Net Sharpe | Total (9 mo) | Positive weeks | Worst week | Fill rate | Same signal, taker |
|---|---|---|---|---|---|---|
| H4-B-Z1.5-W15 | 0.75 | +5.2% | 53% | −3.1% | 96% | Sharpe −1.93 |
| H4-B-Z1.5-W60 | 0.50 | +3.3% | 55% | −4.1% | 98% | −1.93 |
| H4-A-Z1.5-W60 | 0.47 | +3.6% | 53% | −3.3% | 98% | 0.26 |
| H1 (all 8) | −6.0 to −10.7 | −38% to −68% | 7–17% | | 96–98% | −13 to −23 |

- **Maker execution helps, but not enough.** At the 4-hour horizon, maker fills raised
  the net Sharpe from about −2 to 0.5–0.75 with the same signal. At 1.35–2.6 of
  turnover a day, the remaining edge still does not clear 2 bps plus adverse
  selection with any consistency.
- **The 1-hour horizon fails.** It turned over more than 6 times a day, and maker fees
  plus adverse selection consumed the edge.
- **Fill rates were 96–98% under the trade-through rule.** Prices almost always
  trade 1 bp through the hour's open within 15 minutes. The fills that matter are
  adverse ones, and the result includes them.

## Decision

`STOP` before the out-of-sample run, as registered. The out-of-sample window stays
unspent.

## What the Phase 2 program now shows

Every registered attempt has failed to deliver steady net returns at retail costs
with public data:

- daily and weekly price, trend, and momentum rules;
- positioning and flow data;
- intraday cross-sectional prediction;
- taker or maker execution.

The intraday signal is real before costs, but too small. T1 is the only historical
survivor, and its returns are lumpy. Its Demo observation continues
(Decision 0029).
