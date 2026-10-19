# RSI divergence scalp — retrospective backtest

Generated: 2026-10-18T11:35:36.049764+00:00

Research only. Fixed rules; no parameter search, no exchange orders or MA200 changes.
Evaluation: 2025-10-01 through 2026-09-30 UTC; September 2025 warmup excluded.
Capital: 1,000 USDT; 500 per asset, no leverage amplification. All cells shown.

| Variant | Cost | Net USDT | Return | Trades | Win rate | PF | MDD | Positive slices |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| 1m | normal | -30.72 | -3.07% | 30 | 13.3% | 0.020 | 3.07% | 0/6 |
| 1m | stress | -33.93 | -3.39% | 26 | 3.8% | 0.001 | 3.39% | 0/6 |
| 5m | normal | -12.27 | -1.23% | 9 | 11.1% | 0.043 | 1.24% | 0/6 |
| 5m | stress | -13.62 | -1.36% | 9 | 11.1% | 0.016 | 1.36% | 0/6 |

## 1m: INSUFFICIENT_TRADES

- at_least_100_trades: FAIL
- both_costs_positive: FAIL
- both_pf_at_least_1_15: FAIL
- both_mdd_at_most_10pct: PASS
- both_at_least_4_positive_folds: FAIL
- both_concentration_at_most_80pct: FAIL
- normal_bootstrap_lower_positive: FAIL

## 5m: INSUFFICIENT_TRADES

- at_least_100_trades: FAIL
- both_costs_positive: FAIL
- both_pf_at_least_1_15: FAIL
- both_mdd_at_most_10pct: PASS
- both_at_least_4_positive_folds: FAIL
- both_concentration_at_most_80pct: FAIL
- normal_bootstrap_lower_positive: FAIL

## 1m/normal

| Asset | Net USDT | Trades |
|---|---:|---:|
| BTC | -13.08 | 14 |
| ETH | -17.64 | 16 |

Funding P&L: 0.0000; fees: 13.7040; slippage cost: 5.4816 USDT.
Skipped entry signals (price/risk/lot constraints): 57.
Signals while already holding are ignored; these are not included in skips.
Daily mean P&L bootstrap 95%: [-0.1314, -0.0412] USDT/day.

Monthly marked P&L (USDT): 2025-10: -1.19; 2025-11: -1.15; 2025-12: -5.81; 2026-01: 0.00; 2026-02: -1.58; 2026-03: -5.47; 2026-04: -2.67; 2026-05: -0.09; 2026-06: -2.02; 2026-07: -2.18; 2026-08: -6.25; 2026-09: -2.30

Two-month marked P&L (USDT): 2025-10..2025-11: -2.34; 2025-12..2026-01: -5.81; 2026-02..2026-03: -7.05; 2026-04..2026-05: -2.76; 2026-06..2026-07: -4.21; 2026-08..2026-09: -8.55

## 1m/stress

| Asset | Net USDT | Trades |
|---|---:|---:|
| BTC | -14.27 | 12 |
| ETH | -19.65 | 14 |

Funding P&L: 0.0000; fees: 11.8506; slippage cost: 11.8506 USDT.
Skipped entry signals (price/risk/lot constraints): 61.
Signals while already holding are ignored; these are not included in skips.
Daily mean P&L bootstrap 95%: [-0.1433, -0.0479] USDT/day.

Monthly marked P&L (USDT): 2025-10: -2.09; 2025-11: -1.18; 2025-12: -6.07; 2026-01: 0.00; 2026-02: -1.86; 2026-03: -6.06; 2026-04: -1.98; 2026-05: -0.38; 2026-06: -2.57; 2026-07: -2.23; 2026-08: -7.14; 2026-09: -2.38

Two-month marked P&L (USDT): 2025-10..2025-11: -3.27; 2025-12..2026-01: -6.07; 2026-02..2026-03: -7.92; 2026-04..2026-05: -2.36; 2026-06..2026-07: -4.80; 2026-08..2026-09: -9.51

## 5m/normal

| Asset | Net USDT | Trades |
|---|---:|---:|
| BTC | -2.30 | 3 |
| ETH | -9.98 | 6 |

Funding P&L: 0.0000; fees: 3.7368; slippage cost: 1.4947 USDT.
Skipped entry signals (price/risk/lot constraints): 24.
Signals while already holding are ignored; these are not included in skips.
Daily mean P&L bootstrap 95%: [-0.0664, -0.0078] USDT/day.

Monthly marked P&L (USDT): 2025-10: 0.00; 2025-11: 0.00; 2025-12: -2.47; 2026-01: -3.95; 2026-02: -2.50; 2026-03: 0.00; 2026-04: 0.55; 2026-05: -1.09; 2026-06: 0.00; 2026-07: 0.00; 2026-08: -1.35; 2026-09: -1.46

Two-month marked P&L (USDT): 2025-10..2025-11: 0.00; 2025-12..2026-01: -6.42; 2026-02..2026-03: -2.50; 2026-04..2026-05: -0.55; 2026-06..2026-07: 0.00; 2026-08..2026-09: -2.81

## 5m/stress

| Asset | Net USDT | Trades |
|---|---:|---:|
| BTC | -2.95 | 3 |
| ETH | -10.67 | 6 |

Funding P&L: 0.0000; fees: 3.4207; slippage cost: 3.4207 USDT.
Skipped entry signals (price/risk/lot constraints): 24.
Signals while already holding are ignored; these are not included in skips.
Daily mean P&L bootstrap 95%: [-0.0726, -0.0098] USDT/day.

Monthly marked P&L (USDT): 2025-10: 0.00; 2025-11: 0.00; 2025-12: -2.49; 2026-01: -4.52; 2026-02: -2.49; 2026-03: 0.00; 2026-04: 0.23; 2026-05: -1.15; 2026-06: 0.00; 2026-07: 0.00; 2026-08: -1.62; 2026-09: -1.57

Two-month marked P&L (USDT): 2025-10..2025-11: 0.00; 2025-12..2026-01: -7.02; 2026-02..2026-03: -2.49; 2026-04..2026-05: -0.93; 2026-06..2026-07: 0.00; 2026-08..2026-09: -3.19

## Interpretation and limits

The no-trade control earns 0. The source's 100% win claim is not an assumption.
This is one mechanical RSI interpretation; the source leaves indicator, pivots, stops and supply-zone exits undefined.
All periods are development data, including dates previously examined at hourly resolution. Stability slices are not an independent holdout.
Normal cost is 14bps and stress is 20bps round-trip (5bps fee plus 2/5bps slippage each side).
Targets are taker executions on touch; OHLC cannot prove actual liquidity, latency or maker fills. Both-hit bars choose stop first.
MDD uses bar-close marked equity, not tick-level or liquidation-engine marks. Futures contract prices mark intrabar P&L; funding uses prior hourly mark closes.
Static current-style lot/notional assumptions are not reconstructed historical exchange rules. Small-account rounding materially affects results.
Separate per-asset sleeves prevent capital reuse; no leverage amplification, averaging down, or compounding. Liquidations are not modeled.
A negative result rejects these fixed rules; it does not establish that every divergence strategy fails.
No live deployment follows automatically, even if a research gate passes.

## Reproduction

```bash
.venv/bin/python scripts/build_divergence_dataset.py
.venv/bin/python scripts/run_divergence_research.py
```

Inputs and registration are SHA256-verified before simulation. summary.json records source hashes, manifest and rules.
Official dataset/schema: https://github.com/binance/binance-public-data
