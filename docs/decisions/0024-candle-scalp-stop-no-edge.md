# 0024 — Keep candle scalping in research after all registered variants lose

- Status: Research conclusion; no promotion to execution
- Date: 2026-10-18
- Registration: [CANDLE_SCALP_PREREGISTRATION](../CANDLE_SCALP_PREREGISTRATION.md)
- Results: [REPORT](../../research_results/candle-scalp/REPORT.md)
- Validation: [evidence](../../evidence/candle-scalp/validation.json)

## Context and fixed interpretation

The user requested research on candle-based scalping, including two large bearish
candles, range rebounds, bullish breakouts and averaging down. We separated these
into pullback, range and breakout hypotheses before scoring. Each uses closed
30m signals, completed 1h/4h context and 1m execution bars. News judgments,
community popularity and discretionary chart interpretation are not reproduced.

The fixed study reuses hash-frozen official BTC/ETH USD-M data: September 2025
warmup, October 2025 through September 2026 evaluation. All of this is development
data already inspected, not an untouched validation sample. Starting capital is
1,000 USDT split into independent 500 USDT sleeves. Single entry and averaging
both start with a 200 USDT gross budget; averaging may add 150 twice, subject to
lot/minimum-notional constraints and a 5 USDT campaign stop-risk budget.
The original stop never moves down. There is no leverage escalation. This bounded
interpretation does not test the article's unlimited averaging or rare-stop approach.

Entry/add/target orders use conservative passive-fill proxies, including expiry,
penetration and rejection when marketable. Protective exits use taker fees and
adverse slippage. Funding is included. Target is 0.3% of current entry VWAP;
timeout is four hours from first fill. Sleeve and daily loss guards apply.

## Evidence

All 12 registered strategy/sizing/cost combinations lose. Each has at least 100
closed campaigns; all six strategy/sizing decisions are **STOP_NO_EDGE** because
profitability, profit factor, positive two-month slices and bootstrap gates fail.
The portfolio drawdown gate passes, which does not establish profitability.

| Strategy | Normal single net USDT | Normal averaging net USDT | Single campaigns | Single win rate |
|---|---:|---:|---:|---:|
| Pullback | -41.20 | -48.36 | 140 | 58.6% |
| Range | -84.39 | -92.09 | 299 | 59.5% |
| Breakout | -64.70 | -65.22 | 273 | 56.8% |

Stress-cost net results are respectively single/averaging -47.99/-51.38,
-91.12/-93.79 and -70.75/-71.36 USDT. Normal profit factors range from 0.454
to 0.525. Losses already exist before transaction costs in all 12 cells;
fees, slippage and net funding further reduce performance. A roughly 60% win
rate is therefore compatible with negative expectancy here.

Averaging has worse realized net P&L in every strategy/cost pair. These pairs
have equal first-entry budgets but unequal subsequent capital and risk, so they
are not equal-risk superiority tests. Five of six paired daily-difference
bootstrap intervals include zero; the normal pullback interval is wholly
negative. Do not generalize these descriptive comparisons into a universal
claim that all averaging loses. Some ETH sleeves hit their permanent loss guard,
so the published results include the ensuing no-trade periods.

## Decision and limits

Do not promote these fixed candidates to MA200 paper observation, Demo execution
or real trading. Do not tune them on these outcomes and relabel this same period
as a holdout. Any revision requires separate registration and new-data evaluation.
No trading configuration, server cron, credentials or exchange state was changed.

This study does not prove the inverse strategy profitable: reversing entries
changes fill selection, costs and path-dependent exits and would require its own
registered counterfactual. It also does not reproduce the discretionary author.

OHLC data cannot reconstruct order queues, latency or intrabar tick chronology.
Historical instrument-filter changes and liquidation are not modeled. Drawdown
and average exposure use minute-close marks; filled-notional bounds separately
capture same-minute positions and are conservative sums, not synchronized tick
portfolio exposure. The full local suite passes except PostgreSQL integration
cases skipped without a test DSN; fresh counts and artifact hashes are in the
validation evidence. Tests cover positive signals, causal prefixes, future-data
mutation, fill chronology, costs, funding, fixed stops, sizing, halts and reporting.
