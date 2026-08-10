# 0002 — Stop before classifier implementation

- Status: Accepted
- Date: 2026-08-10

## Context

Milestone 1 tested no-trade, trend-pullback, and volatility-breakout controls on one year of complete BTC/ETH futures data. Parameters were chosen from each fold's 90-day training window and evaluated on a separate 30-day window after a six-hour purge/embargo covering the longest candidate holding period. The six validation windows covered 2026-02-11 through 2026-08-10.

At 0.20% round-trip cost, every active same-side BTC/ETH portfolio had negative expectancy, profit factor below 0.67, drawdown above 35%, and zero positive folds. Every candidate also failed the 0.30% stress-cost review. These are broad failures, not threshold misses.

## Decision

Stop the implementation sequence before FreqAI or any other classifier. Keep `V3ShadowStrategy` fail-closed with zero entry signals and keep the V3 service stopped. Do not paper-trade a strategy that failed the offline promotion contract.

The V3 repository remains the clean foundation for future research, but the next candidate must begin with a different deterministic market hypothesis. Adding features, tuning the current thresholds, or using a model to rank the rejected signals does not satisfy this requirement.

## Next admissible research

A future milestone may evaluate lower-turnover hypotheses at one-hour or slower decision intervals, including directional regime persistence or market-neutral relative value. It must define the hypothesis before feature construction and preserve:

- no-trade and simple deterministic controls;
- causal, completed-candle features only;
- training-only parameter selection and untouched chronological folds;
- explicit 0.20% normal and 0.30% adverse round-trip costs;
- fixed 1x risk and conservative intrabar resolution;
- portfolio-level concentration, expectancy, profit-factor, drawdown, and fold gates.

Machine learning becomes admissible only after a deterministic portfolio passes both cost regimes. Even then, research promotion would authorize only a separate 60-day/100-trade shadow evaluation, never live capital.

## Evidence

- [`research_results/milestone-1/REPORT.md`](../../research_results/milestone-1/REPORT.md)
- [`research_results/milestone-1/results.json`](../../research_results/milestone-1/results.json)
- [`evidence/v2-baseline/v2-baseline-2026-08-10.md`](../../evidence/v2-baseline/v2-baseline-2026-08-10.md)
