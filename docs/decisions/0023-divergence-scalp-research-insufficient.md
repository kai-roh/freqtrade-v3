# 0023 — Keep the divergence scalp out of deployment after a losing, sparse backtest

- Status: Research conclusion; deployment not approved
- Date: 2026-10-18
- Registration: [DIVERGENCE_PREREGISTRATION](../DIVERGENCE_PREREGISTRATION.md)
- Results: [REPORT](../../research_results/divergence/REPORT.md)

## Context

The user requested a newly developed research candidate and historical backtest
of an article describing high-volume, rising-trend, minute-chart divergence
scalping. Its indicator, pivot, supply-zone, stop and sizing definitions were
incomplete, and its 100% win-rate claim was unsupported. The registered study
makes those choices explicit rather than pretending to reproduce discretionary
judgment or the unavailable chart images.

## Evidence

Official Binance USD-M BTC/ETH 1m candles, SHA256 verified against published
checksums: September 2025 warmup and October 2025–September 2026 evaluation.
Each asset has 568,800 complete minute rows including warmup. Five-minute bars
are exact aggregates of the same minute data. Funding and prior hourly marks
are hash-frozen from the existing Phase 2c dataset. Both timeframes and both
predeclared cost regimes are reported without selecting a winner.

Capital is 1,000 USDT, split into independent 500 USDT sleeves; no leverage
amplification. Costs include taker fees and adverse slippage each way. No
position crossed a funding settlement in the realized trade sample, so observed
funding P&L is zero despite funding support being tested.

| Timeframe | Cost | Closed trades | Net USDT | Win rate | Profit factor |
|---|---|---:|---:|---:|---:|
| 1m | normal | 30 | -30.72 | 13.3% | 0.020 |
| 1m | stress | 26 | -33.93 | 3.8% | 0.001 |
| 5m | normal | 9 | -12.27 | 11.1% | 0.043 |
| 5m | stress | 9 | -13.62 | 11.1% | 0.016 |

All variants had zero positive two-month slices out of six. Normal-cost 1m
price P&L was already -11.53 USDT before fees/slippage; fees -13.70 and
slippage -5.48 compounded it. This is not solely a fee problem. Signals are
sparse: 87 across assets at 1m, 33 at 5m, before price/risk/lot entry checks.
The registered 0.20% minimum target, trend, volume and causal pivot conditions
intentionally exclude many discretionary-looking setups. Conditions were not
relaxed after seeing the result.

## Decision

Both timeframes are **INSUFFICIENT_TRADES** (<100 closes), with observed negative
net expectancy and failed profitability/stability gates. Do not interpret the
small samples as precise estimates of future win rates. Neither candidate is
promoted to paper execution, Demo orders or real trading.

This rejects promotion of the fixed mechanical interpretation, not every
possible divergence strategy. A revision must be separately registered; these
results cannot become its untouched holdout. The already-running MA200 paper
observation and Demo runtime are unchanged. No changes to trading configuration,
cron, credentials, exchange state, or Mainnet authorization were made.

## Verification and limits

Tests cover causal prefix invariance, completed-hour alignment, delayed pivot
confirmation, next-open entries, conservative stop/target ambiguity, gap stops,
timeout gap caps, fees, funding, lot constraints, data integrity and gates.
The local full suite passes except PostgreSQL integration cases intentionally
skipped without a test DSN; details are recorded in the validation evidence.

These OHLC simulations do not reconstruct queues, actual order latency, maker
fills, historical instrument-filter changes or liquidation paths. Drawdown is
marked at candle closes. Historical periods are development data, not an
independent prospective performance trial.
