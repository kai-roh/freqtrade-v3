# 0030 — Register Phase 2h: consistency-first intraday decision system

- Status: Accepted
- Date: 2026-10-20 (KST)

## Context

On 2026-10-20 the user set the criterion for any strategy. It must make small
returns consistently, by the day or the week, rather than rely on a few large wins.
The user also described the behavior: analyze each day's volume and trend, then do
one of the following:

- skip;
- trade small;
- bet more or add when conviction is high.

T1 (Decision 0028) is the opposite profile. Without its best 10 of 144 weeks, its
validation return falls from a log return of 1.57 to 0.17.

## Decision

Register [PHASE2H_PREREGISTRATION.md](../PHASE2H_PREREGISTRATION.md) before any
result is computed. It fixes the following:

- **Data:** 1-hour candles and hourly positioning metrics for the 195 perpetuals.
- **Model:** a walk-forward ridge model, refit monthly, that predicts each symbol's
  relative return over the next h hours.
- **Behavior:**
  - The trade is skipped unless conviction (the cross-sectional z-score) passes a
    threshold.
  - Size is proportional to conviction with a per-symbol cap, and a position grows
    when conviction rises.
  - The book is market-neutral.
- **Loss limits:** a volatility-based stop per symbol and a −2% daily loss limit.
- **Trials:** 8 configurations.
- **Out-of-sample period:** 2023-01..2026-09.
- **Gates:** judged on consistency rather than total return:
  - Sharpe at least 2;
  - at least 65% positive weeks;
  - at least 80% positive months;
  - worst week no lower than −5%;
  - a concentration limit;
  - every year positive;
  - double cost;
  - a deflated Sharpe at the cumulative M=196.
- **Outcomes:** `CANDIDATE` leads to a forward observation, and server changes need
  user approval. `STOP_NO_EDGE` otherwise.
