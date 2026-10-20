# Milestone 1 — Evidence and deterministic edge review

## Goal

Decide whether BTC/ETH 15-minute trading contains a reproducible post-cost edge worth further engineering.

## Inputs

- At least 270 days, preferably 365 days, of BTC/USDT:USDT and ETH/USDT:USDT futures candles.
- 15-minute decision candles and 1-hour regime candles.
- Normal cost stress: 0.20% round trip.
- Adverse cost stress: 0.30% round trip.

## Candidates

- No trade.
- One-hour trend with a 15-minute pullback.
- Fifteen-minute volatility breakout with a one-hour regime filter.

Every active candidate uses the same fixed 1x risk contract, conservative same-candle stop/target resolution, a bounded holding period, and independent long/short switches.

## Validation

- Six or more chronological folds.
- Purge and embargo of at least the maximum label/trade horizon.
- No overlapping positions per pair.
- Fold, pair, and side metrics reported separately.
- Final comparison includes PF, expectancy, drawdown, turnover, cost, contribution concentration, and positive-fold count.

## Promotion gate

- Positive post-cost expectancy.
- PF at least 1.15.
- Maximum drawdown at most 10%.
- At least four positive folds out of six.
- No one fold or pair contributes more than 50% of profit.
- Result remains acceptable at 0.30% stress cost.

Failure is a valid result. If both deterministic families fail, classifier implementation is blocked. A new market hypothesis must first establish deterministic post-cost edge under this same validation contract.

## Result — 2026-08-10

The milestone used one year of complete Binance futures candles for BTC and ETH: 35,044 rows per pair at 15 minutes and 8,761 rows per pair at one hour. Six rolling folds each used 90 training days, a six-hour purge/embargo covering the longest candidate holding period, and 30 untouched validation days.

At the normal 0.20% round-trip cost assumption:

| Candidate | Side | Trades | Profit factor | Expectancy/trade | Drawdown | Positive folds |
|---|---:|---:|---:|---:|---:|---:|
| Trend pullback | Long | 314 | 0.491 | -0.2046% | 65.74% | 0/6 |
| Trend pullback | Short | 223 | 0.611 | -0.1605% | 37.04% | 0/6 |
| Volatility breakout | Long | 447 | 0.576 | -0.1916% | 93.03% | 0/6 |
| Volatility breakout | Short | 424 | 0.666 | -0.1563% | 69.99% | 0/6 |

All portfolios also failed the 0.30% stress-cost gate. The decision is `STOP_BEFORE_CLASSIFIER`: do not build FreqAI/classifier logic, do not paper-trade the rejected policy, and do not authorize live trading from this milestone. A later operator decision permits only a zero-entry infrastructure test; it does not promote any signal family.

The full machine-readable evidence is in [`research_results/milestone-1/results.json`](../research_results/milestone-1/results.json). A future research milestone may test a genuinely different, lower-turnover hypothesis, but it must retain the no-trade control, causal features, purged folds, conservative costs, 1x risk, and the same fail-closed promotion gates.
