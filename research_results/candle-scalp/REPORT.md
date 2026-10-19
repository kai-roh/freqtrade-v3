# Candle scalp — three hypotheses and bounded averaging

Generated: 2026-10-18T12:47:08.840582+00:00

Fixed retrospective study, 2025-10-01..2026-09-30 UTC, BTC/ETH USD-M perpetuals.
1,000 USDT split500/500; 30m signals and completed1h/4h trend, minute execution only.
Initial entry budget200 in BOTH variants; averaging may add150+150, capped500 per asset.
Campaign stop-risk budget5 USDT; fixed stop,4h timeout, daily/sleeve protection. No leverage escalation.
This is a mechanical interpretation, not a reproduction of discretionary news/chart judgments.

| Strategy | Sizing | Execution | Net USDT | Trades | Win rate | PF | MDD | Add fills |
|---|---|---|---:|---:|---:|---:|---:|---:|
| pullback | single | normal | -41.20 | 140 | 58.6% | 0.484 | 4.98% | 0 |
| pullback | single | stress | -47.99 | 115 | 53.9% | 0.382 | 5.55% | 0 |
| pullback | averaging | normal | -48.36 | 140 | 58.6% | 0.454 | 5.74% | 20 |
| pullback | averaging | stress | -51.38 | 115 | 53.9% | 0.378 | 5.93% | 11 |
| range | single | normal | -84.39 | 299 | 59.5% | 0.493 | 8.63% | 0 |
| range | single | stress | -91.12 | 234 | 54.7% | 0.395 | 9.20% | 0 |
| range | averaging | normal | -92.09 | 284 | 59.9% | 0.471 | 9.29% | 46 |
| range | averaging | stress | -93.79 | 216 | 55.1% | 0.378 | 9.46% | 28 |
| breakout | single | normal | -64.70 | 273 | 56.8% | 0.525 | 6.82% | 0 |
| breakout | single | stress | -70.75 | 223 | 53.4% | 0.435 | 7.38% | 0 |
| breakout | averaging | normal | -65.22 | 261 | 57.1% | 0.518 | 6.96% | 18 |
| breakout | averaging | stress | -71.36 | 221 | 53.8% | 0.438 | 7.44% | 11 |

## Research gates

- **pullback/single: STOP_NO_EDGE**. Failed: both_costs_positive, both_pf_at_least_1_15, both_at_least_4_positive_folds, normal_bootstrap_lower_positive.
- **pullback/averaging: STOP_NO_EDGE**. Failed: both_costs_positive, both_pf_at_least_1_15, both_at_least_4_positive_folds, normal_bootstrap_lower_positive.
- **range/single: STOP_NO_EDGE**. Failed: both_costs_positive, both_pf_at_least_1_15, both_at_least_4_positive_folds, normal_bootstrap_lower_positive.
- **range/averaging: STOP_NO_EDGE**. Failed: both_costs_positive, both_pf_at_least_1_15, both_at_least_4_positive_folds, normal_bootstrap_lower_positive.
- **breakout/single: STOP_NO_EDGE**. Failed: both_costs_positive, both_pf_at_least_1_15, both_at_least_4_positive_folds, normal_bootstrap_lower_positive.
- **breakout/averaging: STOP_NO_EDGE**. Failed: both_costs_positive, both_pf_at_least_1_15, both_at_least_4_positive_folds, normal_bootstrap_lower_positive.

## Does bounded averaging improve the single entry?

Same first entry budget, but averaging consumes additional capital and risk; this is NOT an equal-risk superiority test.
Difference = averaging minus single, including all no-trade days. Bootstrap is descriptive, not new-data confirmation.

| Strategy/cost | Net difference USDT | Daily difference95% CI | Single mean exposure | Averaging mean exposure |
|---|---:|---|---:|---:|
| pullback/normal | -7.17 | [-0.0376, -0.0040] | 3.15 | 3.32 |
| pullback/stress | -3.39 | [-0.0203, 0.0004] | 2.74 | 2.84 |
| range/normal | -7.70 | [-0.0594, 0.0215] | 5.98 | 5.94 |
| range/stress | -2.67 | [-0.0400, 0.0267] | 4.52 | 4.27 |
| breakout/normal | -0.52 | [-0.0227, 0.0233] | 3.51 | 3.59 |
| breakout/stress | -0.61 | [-0.0167, 0.0172] | 2.92 | 3.03 |

## pullback/single/normal

Price P&L -25.3823 − fees 13.5506 − slippage 2.1642 + funding -0.0979 = net -41.1950 USDT.
Worst campaign -3.0679; maximum holding 240min; minute-close peak/mean exposure 394.22/3.15 USDT; within-minute filled-notional portfolio bound 393.60 USDT.
Entry/add fills 140/0; exits {"stop": 49, "target": 81, "timeout": 10}.
Monthly marked P&L: 2025-10: -9.24; 2025-11: 0.98; 2025-12: -7.00; 2026-01: -2.85; 2026-02: 0.51; 2026-03: -6.09; 2026-04: -6.38; 2026-05: -2.18; 2026-06: -3.72; 2026-07: -11.01; 2026-08: 2.94; 2026-09: 2.84
Two-month marked P&L: 2025-10..2025-11: -8.25; 2025-12..2026-01: -9.85; 2026-02..2026-03: -5.57; 2026-04..2026-05: -8.56; 2026-06..2026-07: -14.74; 2026-08..2026-09: 5.78

| Asset | Net USDT | Campaigns | Diagnostics |
|---|---:|---:|---|
| BTC | -11.91 | 69 | {"account_halts": 0, "add_fills": 0, "daily_halts": 0, "entry_fills": 69, "passive_rejections": 0, "risk_refusals": 0, "rounding_refusals": 0, "unfilled_orders": 17} |
| ETH | -29.29 | 71 | {"account_halts": 0, "add_fills": 0, "daily_halts": 0, "entry_fills": 71, "passive_rejections": 0, "risk_refusals": 0, "rounding_refusals": 0, "unfilled_orders": 21} |

Worst10 BTC daily-return dates, selected ex post for a disclosed stress diagnostic:

| UTC date | BTC return | Marked portfolio P&L | Adds | Minute-close peak / filled-notional bound |
|---|---:|---:|---:|---:|
| 2026-02-05 | -14.04% | 0.00 | 0 | 0.00 / 0.00 |
| 2025-10-10 | -7.29% | 0.00 | 0 | 0.00 / 0.00 |
| 2026-01-31 | -6.54% | 0.00 | 0 | 0.00 / 0.00 |
| 2026-06-02 | -6.53% | 0.00 | 0 | 0.00 / 0.00 |
| 2025-11-20 | -5.36% | 0.00 | 0 | 0.00 / 0.00 |
| 2026-01-29 | -5.22% | 0.00 | 0 | 0.00 / 0.00 |
| 2025-11-14 | -5.13% | 0.00 | 0 | 0.00 / 0.00 |
| 2025-11-04 | -4.78% | 0.00 | 0 | 0.00 / 0.00 |
| 2026-01-20 | -4.54% | 0.00 | 0 | 0.00 / 0.00 |
| 2025-12-01 | -4.52% | -6.45 | 0 | 377.60 / 377.91 |

## pullback/single/stress

Price P&L -31.4535 − fees 11.4922 − slippage 4.9567 + funding -0.0892 = net -47.9916 USDT.
Worst campaign -3.1266; maximum holding 240min; minute-close peak/mean exposure 394.22/2.74 USDT; within-minute filled-notional portfolio bound 393.60 USDT.
Entry/add fills 115/0; exits {"stop": 46, "target": 61, "timeout": 8}.
Monthly marked P&L: 2025-10: -9.52; 2025-11: 0.46; 2025-12: -8.34; 2026-01: -3.08; 2026-02: 0.51; 2026-03: -6.95; 2026-04: -8.92; 2026-05: -3.32; 2026-06: -3.90; 2026-07: -10.15; 2026-08: 3.12; 2026-09: 2.08
Two-month marked P&L: 2025-10..2025-11: -9.06; 2025-12..2026-01: -11.42; 2026-02..2026-03: -6.44; 2026-04..2026-05: -12.24; 2026-06..2026-07: -14.05; 2026-08..2026-09: 5.21

| Asset | Net USDT | Campaigns | Diagnostics |
|---|---:|---:|---|
| BTC | -15.81 | 53 | {"account_halts": 0, "add_fills": 0, "daily_halts": 0, "entry_fills": 53, "passive_rejections": 0, "risk_refusals": 0, "rounding_refusals": 0, "unfilled_orders": 36} |
| ETH | -32.18 | 62 | {"account_halts": 0, "add_fills": 0, "daily_halts": 0, "entry_fills": 62, "passive_rejections": 0, "risk_refusals": 0, "rounding_refusals": 0, "unfilled_orders": 31} |

Worst10 BTC daily-return dates, selected ex post for a disclosed stress diagnostic:

| UTC date | BTC return | Marked portfolio P&L | Adds | Minute-close peak / filled-notional bound |
|---|---:|---:|---:|---:|
| 2026-02-05 | -14.04% | 0.00 | 0 | 0.00 / 0.00 |
| 2025-10-10 | -7.29% | 0.00 | 0 | 0.00 / 0.00 |
| 2026-01-31 | -6.54% | 0.00 | 0 | 0.00 / 0.00 |
| 2026-06-02 | -6.53% | 0.00 | 0 | 0.00 / 0.00 |
| 2025-11-20 | -5.36% | 0.00 | 0 | 0.00 / 0.00 |
| 2026-01-29 | -5.22% | 0.00 | 0 | 0.00 / 0.00 |
| 2025-11-14 | -5.13% | 0.00 | 0 | 0.00 / 0.00 |
| 2025-11-04 | -4.78% | 0.00 | 0 | 0.00 / 0.00 |
| 2026-01-20 | -4.54% | 0.00 | 0 | 0.00 / 0.00 |
| 2025-12-01 | -4.52% | -6.68 | 0 | 375.92 / 377.91 |

## pullback/averaging/normal

Price P&L -30.3356 − fees 15.3342 − slippage 2.6061 + funding -0.0863 = net -48.3622 USDT.
Worst campaign -4.3883; maximum holding 240min; minute-close peak/mean exposure 777.90/3.32 USDT; within-minute filled-notional portfolio bound 779.97 USDT.
Entry/add fills 140/20; exits {"stop": 49, "target": 81, "timeout": 10}.
Monthly marked P&L: 2025-10: -11.61; 2025-11: 0.98; 2025-12: -7.00; 2026-01: -2.85; 2026-02: 0.51; 2026-03: -6.44; 2026-04: -7.72; 2026-05: -2.18; 2026-06: -3.72; 2026-07: -14.39; 2026-08: 3.21; 2026-09: 2.84
Two-month marked P&L: 2025-10..2025-11: -10.62; 2025-12..2026-01: -9.85; 2026-02..2026-03: -5.93; 2026-04..2026-05: -9.90; 2026-06..2026-07: -18.12; 2026-08..2026-09: 6.05

| Asset | Net USDT | Campaigns | Diagnostics |
|---|---:|---:|---|
| BTC | -13.68 | 69 | {"account_halts": 0, "add_fills": 6, "daily_halts": 0, "entry_fills": 69, "passive_rejections": 0, "risk_refusals": 0, "rounding_refusals": 12, "unfilled_orders": 25} |
| ETH | -34.68 | 71 | {"account_halts": 0, "add_fills": 14, "daily_halts": 0, "entry_fills": 71, "passive_rejections": 0, "risk_refusals": 0, "rounding_refusals": 0, "unfilled_orders": 28} |

Worst10 BTC daily-return dates, selected ex post for a disclosed stress diagnostic:

| UTC date | BTC return | Marked portfolio P&L | Adds | Minute-close peak / filled-notional bound |
|---|---:|---:|---:|---:|
| 2026-02-05 | -14.04% | 0.00 | 0 | 0.00 / 0.00 |
| 2025-10-10 | -7.29% | 0.00 | 0 | 0.00 / 0.00 |
| 2026-01-31 | -6.54% | 0.00 | 0 | 0.00 / 0.00 |
| 2026-06-02 | -6.53% | 0.00 | 0 | 0.00 / 0.00 |
| 2025-11-20 | -5.36% | 0.00 | 0 | 0.00 / 0.00 |
| 2026-01-29 | -5.22% | 0.00 | 0 | 0.00 / 0.00 |
| 2025-11-14 | -5.13% | 0.00 | 0 | 0.00 / 0.00 |
| 2025-11-04 | -4.78% | 0.00 | 0 | 0.00 / 0.00 |
| 2026-01-20 | -4.54% | 0.00 | 0 | 0.00 / 0.00 |
| 2025-12-01 | -4.52% | -6.45 | 0 | 377.60 / 377.91 |

## pullback/averaging/stress

Price P&L -33.4245 − fees 12.4213 − slippage 5.4566 + funding -0.0775 = net -51.3800 USDT.
Worst campaign -3.9630; maximum holding 240min; minute-close peak/mean exposure 543.60/2.84 USDT; within-minute filled-notional portfolio bound 542.52 USDT.
Entry/add fills 115/11; exits {"stop": 46, "target": 61, "timeout": 8}.
Monthly marked P&L: 2025-10: -10.53; 2025-11: 0.46; 2025-12: -8.34; 2026-01: -3.08; 2026-02: 0.51; 2026-03: -7.35; 2026-04: -9.83; 2026-05: -3.32; 2026-06: -3.90; 2026-07: -11.67; 2026-08: 3.58; 2026-09: 2.08
Two-month marked P&L: 2025-10..2025-11: -10.07; 2025-12..2026-01: -11.42; 2026-02..2026-03: -6.83; 2026-04..2026-05: -13.16; 2026-06..2026-07: -15.57; 2026-08..2026-09: 5.66

| Asset | Net USDT | Campaigns | Diagnostics |
|---|---:|---:|---|
| BTC | -16.51 | 53 | {"account_halts": 0, "add_fills": 3, "daily_halts": 0, "entry_fills": 53, "passive_rejections": 0, "risk_refusals": 0, "rounding_refusals": 8, "unfilled_orders": 46} |
| ETH | -34.87 | 62 | {"account_halts": 0, "add_fills": 8, "daily_halts": 0, "entry_fills": 62, "passive_rejections": 0, "risk_refusals": 0, "rounding_refusals": 0, "unfilled_orders": 42} |

Worst10 BTC daily-return dates, selected ex post for a disclosed stress diagnostic:

| UTC date | BTC return | Marked portfolio P&L | Adds | Minute-close peak / filled-notional bound |
|---|---:|---:|---:|---:|
| 2026-02-05 | -14.04% | 0.00 | 0 | 0.00 / 0.00 |
| 2025-10-10 | -7.29% | 0.00 | 0 | 0.00 / 0.00 |
| 2026-01-31 | -6.54% | 0.00 | 0 | 0.00 / 0.00 |
| 2026-06-02 | -6.53% | 0.00 | 0 | 0.00 / 0.00 |
| 2025-11-20 | -5.36% | 0.00 | 0 | 0.00 / 0.00 |
| 2026-01-29 | -5.22% | 0.00 | 0 | 0.00 / 0.00 |
| 2025-11-14 | -5.13% | 0.00 | 0 | 0.00 / 0.00 |
| 2025-11-04 | -4.78% | 0.00 | 0 | 0.00 / 0.00 |
| 2026-01-20 | -4.54% | 0.00 | 0 | 0.00 / 0.00 |
| 2025-12-01 | -4.52% | -6.68 | 0 | 375.92 / 377.91 |

## range/single/normal

Price P&L -51.7567 − fees 28.0948 − slippage 4.4049 + funding -0.1307 = net -84.3870 USDT.
Worst campaign -3.3011; maximum holding 240min; minute-close peak/mean exposure 399.19/5.98 USDT; within-minute filled-notional portfolio bound 398.84 USDT.
Entry/add fills 299/0; exits {"stop": 111, "target": 174, "timeout": 14}.
Monthly marked P&L: 2025-10: -4.53; 2025-11: -8.59; 2025-12: -9.87; 2026-01: 0.53; 2026-02: -3.31; 2026-03: -6.64; 2026-04: -5.25; 2026-05: -11.83; 2026-06: -9.75; 2026-07: -9.52; 2026-08: -3.81; 2026-09: -11.82
Two-month marked P&L: 2025-10..2025-11: -13.12; 2025-12..2026-01: -9.34; 2026-02..2026-03: -9.95; 2026-04..2026-05: -17.08; 2026-06..2026-07: -19.27; 2026-08..2026-09: -15.62

| Asset | Net USDT | Campaigns | Diagnostics |
|---|---:|---:|---|
| BTC | -37.31 | 155 | {"account_halts": 0, "add_fills": 0, "daily_halts": 0, "entry_fills": 155, "passive_rejections": 0, "risk_refusals": 0, "rounding_refusals": 0, "unfilled_orders": 63} |
| ETH | -47.08 | 144 | {"account_halts": 0, "add_fills": 0, "daily_halts": 0, "entry_fills": 144, "passive_rejections": 0, "risk_refusals": 0, "rounding_refusals": 0, "unfilled_orders": 40} |

Worst10 BTC daily-return dates, selected ex post for a disclosed stress diagnostic:

| UTC date | BTC return | Marked portfolio P&L | Adds | Minute-close peak / filled-notional bound |
|---|---:|---:|---:|---:|
| 2026-02-05 | -14.04% | 0.00 | 0 | 0.00 / 0.00 |
| 2025-10-10 | -7.29% | 0.00 | 0 | 0.00 / 0.00 |
| 2026-01-31 | -6.54% | 0.00 | 0 | 0.00 / 0.00 |
| 2026-06-02 | -6.53% | 0.00 | 0 | 0.00 / 0.00 |
| 2025-11-20 | -5.36% | -2.23 | 0 | 177.55 / 177.30 |
| 2026-01-29 | -5.22% | 0.46 | 0 | 176.50 / 175.97 |
| 2025-11-14 | -5.13% | 0.00 | 0 | 0.00 / 0.00 |
| 2025-11-04 | -4.78% | 0.00 | 0 | 0.00 / 0.00 |
| 2026-01-20 | -4.54% | 0.00 | 0 | 0.00 / 0.00 |
| 2025-12-01 | -4.52% | 0.45 | 0 | 174.86 / 174.42 |

## range/single/stress

Price P&L -59.0478 − fees 22.4678 − slippage 9.5069 + funding -0.0996 = net -91.1221 USDT.
Worst campaign -3.3594; maximum holding 240min; minute-close peak/mean exposure 397.03/4.52 USDT; within-minute filled-notional portfolio bound 396.43 USDT.
Entry/add fills 234/0; exits {"account_halt": 1, "stop": 95, "target": 126, "timeout": 12}.
Monthly marked P&L: 2025-10: -3.90; 2025-11: -11.20; 2025-12: -12.32; 2026-01: -1.12; 2026-02: -5.80; 2026-03: -3.66; 2026-04: -8.59; 2026-05: -15.00; 2026-06: -13.05; 2026-07: -8.60; 2026-08: -3.93; 2026-09: -3.96
Two-month marked P&L: 2025-10..2025-11: -15.10; 2025-12..2026-01: -13.45; 2026-02..2026-03: -9.46; 2026-04..2026-05: -23.59; 2026-06..2026-07: -21.65; 2026-08..2026-09: -7.88

| Asset | Net USDT | Campaigns | Diagnostics |
|---|---:|---:|---|
| BTC | -40.70 | 125 | {"account_halts": 0, "add_fills": 0, "daily_halts": 0, "entry_fills": 125, "passive_rejections": 0, "risk_refusals": 0, "rounding_refusals": 0, "unfilled_orders": 107} |
| ETH | -50.42 | 109 | {"account_halts": 1, "add_fills": 0, "daily_halts": 0, "entry_fills": 109, "passive_rejections": 0, "risk_refusals": 0, "rounding_refusals": 0, "unfilled_orders": 57} |

Worst10 BTC daily-return dates, selected ex post for a disclosed stress diagnostic:

| UTC date | BTC return | Marked portfolio P&L | Adds | Minute-close peak / filled-notional bound |
|---|---:|---:|---:|---:|
| 2026-02-05 | -14.04% | 0.00 | 0 | 0.00 / 0.00 |
| 2025-10-10 | -7.29% | 0.00 | 0 | 0.00 / 0.00 |
| 2026-01-31 | -6.54% | 0.00 | 0 | 0.00 / 0.00 |
| 2026-06-02 | -6.53% | 0.00 | 0 | 0.00 / 0.00 |
| 2025-11-20 | -5.36% | -2.29 | 0 | 177.55 / 177.30 |
| 2026-01-29 | -5.22% | 0.46 | 0 | 176.50 / 175.97 |
| 2025-11-14 | -5.13% | 0.00 | 0 | 0.00 / 0.00 |
| 2025-11-04 | -4.78% | 0.00 | 0 | 0.00 / 0.00 |
| 2026-01-20 | -4.54% | 0.00 | 0 | 0.00 / 0.00 |
| 2025-12-01 | -4.52% | 0.45 | 0 | 174.86 / 174.42 |

## range/averaging/normal

Price P&L -56.4197 − fees 30.4522 − slippage 5.0829 + funding -0.1306 = net -92.0853 USDT.
Worst campaign -4.7833; maximum holding 240min; minute-close peak/mean exposure 786.44/5.94 USDT; within-minute filled-notional portfolio bound 787.57 USDT.
Entry/add fills 284/46; exits {"account_halt": 1, "stop": 103, "target": 167, "timeout": 13}.
Monthly marked P&L: 2025-10: -5.25; 2025-11: -10.67; 2025-12: -9.87; 2026-01: 0.53; 2026-02: -6.68; 2026-03: -5.79; 2026-04: -5.22; 2026-05: -13.52; 2026-06: -12.28; 2026-07: -13.31; 2026-08: -3.75; 2026-09: -6.30
Two-month marked P&L: 2025-10..2025-11: -15.91; 2025-12..2026-01: -9.34; 2026-02..2026-03: -12.47; 2026-04..2026-05: -18.73; 2026-06..2026-07: -25.58; 2026-08..2026-09: -10.04

| Asset | Net USDT | Campaigns | Diagnostics |
|---|---:|---:|---|
| BTC | -41.62 | 155 | {"account_halts": 0, "add_fills": 26, "daily_halts": 0, "entry_fills": 155, "passive_rejections": 0, "risk_refusals": 0, "rounding_refusals": 9, "unfilled_orders": 77} |
| ETH | -50.46 | 129 | {"account_halts": 1, "add_fills": 20, "daily_halts": 0, "entry_fills": 129, "passive_rejections": 0, "risk_refusals": 0, "rounding_refusals": 0, "unfilled_orders": 39} |

Worst10 BTC daily-return dates, selected ex post for a disclosed stress diagnostic:

| UTC date | BTC return | Marked portfolio P&L | Adds | Minute-close peak / filled-notional bound |
|---|---:|---:|---:|---:|
| 2026-02-05 | -14.04% | 0.00 | 0 | 0.00 / 0.00 |
| 2025-10-10 | -7.29% | 0.00 | 0 | 0.00 / 0.00 |
| 2026-01-31 | -6.54% | 0.00 | 0 | 0.00 / 0.00 |
| 2026-06-02 | -6.53% | 0.00 | 0 | 0.00 / 0.00 |
| 2025-11-20 | -5.36% | -2.23 | 0 | 177.55 / 177.30 |
| 2026-01-29 | -5.22% | 0.46 | 0 | 176.50 / 175.97 |
| 2025-11-14 | -5.13% | 0.00 | 0 | 0.00 / 0.00 |
| 2025-11-04 | -4.78% | 0.00 | 0 | 0.00 / 0.00 |
| 2026-01-20 | -4.54% | 0.00 | 0 | 0.00 / 0.00 |
| 2025-12-01 | -4.52% | 0.45 | 0 | 174.86 / 174.42 |

## range/averaging/stress

Price P&L -60.6285 − fees 22.9480 − slippage 10.1359 + funding -0.0824 = net -93.7948 USDT.
Worst campaign -4.8859; maximum holding 240min; minute-close peak/mean exposure 533.33/4.27 USDT; within-minute filled-notional portfolio bound 533.59 USDT.
Entry/add fills 216/28; exits {"stop": 88, "target": 117, "timeout": 11}.
Monthly marked P&L: 2025-10: -4.11; 2025-11: -13.38; 2025-12: -12.32; 2026-01: -1.12; 2026-02: -9.33; 2026-03: -2.26; 2026-04: -7.81; 2026-05: -15.73; 2026-06: -15.70; 2026-07: -9.36; 2026-08: 1.29; 2026-09: -3.96
Two-month marked P&L: 2025-10..2025-11: -17.49; 2025-12..2026-01: -13.45; 2026-02..2026-03: -11.60; 2026-04..2026-05: -23.54; 2026-06..2026-07: -25.06; 2026-08..2026-09: -2.67

| Asset | Net USDT | Campaigns | Diagnostics |
|---|---:|---:|---|
| BTC | -43.49 | 125 | {"account_halts": 0, "add_fills": 17, "daily_halts": 0, "entry_fills": 125, "passive_rejections": 0, "risk_refusals": 0, "rounding_refusals": 6, "unfilled_orders": 122} |
| ETH | -50.31 | 91 | {"account_halts": 1, "add_fills": 11, "daily_halts": 0, "entry_fills": 91, "passive_rejections": 0, "risk_refusals": 0, "rounding_refusals": 0, "unfilled_orders": 52} |

Worst10 BTC daily-return dates, selected ex post for a disclosed stress diagnostic:

| UTC date | BTC return | Marked portfolio P&L | Adds | Minute-close peak / filled-notional bound |
|---|---:|---:|---:|---:|
| 2026-02-05 | -14.04% | 0.00 | 0 | 0.00 / 0.00 |
| 2025-10-10 | -7.29% | 0.00 | 0 | 0.00 / 0.00 |
| 2026-01-31 | -6.54% | 0.00 | 0 | 0.00 / 0.00 |
| 2026-06-02 | -6.53% | 0.00 | 0 | 0.00 / 0.00 |
| 2025-11-20 | -5.36% | -2.29 | 0 | 177.55 / 177.30 |
| 2026-01-29 | -5.22% | 0.46 | 0 | 176.50 / 175.97 |
| 2025-11-14 | -5.13% | 0.00 | 0 | 0.00 / 0.00 |
| 2025-11-04 | -4.78% | 0.00 | 0 | 0.00 / 0.00 |
| 2026-01-20 | -4.54% | 0.00 | 0 | 0.00 / 0.00 |
| 2025-12-01 | -4.52% | 0.45 | 0 | 174.86 / 174.42 |

## breakout/single/normal

Price P&L -34.6444 − fees 25.6917 − slippage 4.1834 + funding -0.1813 = net -64.7008 USDT.
Worst campaign -3.1789; maximum holding 240min; minute-close peak/mean exposure 397.22/3.51 USDT; within-minute filled-notional portfolio bound 396.57 USDT.
Entry/add fills 273/0; exits {"account_halt": 1, "breakout_failure": 53, "stop": 62, "target": 155, "timeout": 2}.
Monthly marked P&L: 2025-10: -8.33; 2025-11: -5.39; 2025-12: -2.69; 2026-01: -4.67; 2026-02: -1.49; 2026-03: -0.88; 2026-04: -10.86; 2026-05: -2.05; 2026-06: -5.07; 2026-07: -5.00; 2026-08: -14.70; 2026-09: -3.56
Two-month marked P&L: 2025-10..2025-11: -13.72; 2025-12..2026-01: -7.36; 2026-02..2026-03: -2.37; 2026-04..2026-05: -12.91; 2026-06..2026-07: -10.07; 2026-08..2026-09: -18.26

| Asset | Net USDT | Campaigns | Diagnostics |
|---|---:|---:|---|
| BTC | -14.56 | 148 | {"account_halts": 0, "add_fills": 0, "daily_halts": 0, "entry_fills": 148, "passive_rejections": 0, "risk_refusals": 0, "rounding_refusals": 0, "unfilled_orders": 49} |
| ETH | -50.14 | 125 | {"account_halts": 1, "add_fills": 0, "daily_halts": 0, "entry_fills": 125, "passive_rejections": 0, "risk_refusals": 0, "rounding_refusals": 0, "unfilled_orders": 39} |

Worst10 BTC daily-return dates, selected ex post for a disclosed stress diagnostic:

| UTC date | BTC return | Marked portfolio P&L | Adds | Minute-close peak / filled-notional bound |
|---|---:|---:|---:|---:|
| 2026-02-05 | -14.04% | 0.00 | 0 | 0.00 / 0.00 |
| 2025-10-10 | -7.29% | 0.00 | 0 | 0.00 / 0.00 |
| 2026-01-31 | -6.54% | 0.00 | 0 | 0.00 / 0.00 |
| 2026-06-02 | -6.53% | 0.00 | 0 | 0.00 / 0.00 |
| 2025-11-20 | -5.36% | 0.00 | 0 | 0.00 / 0.00 |
| 2026-01-29 | -5.22% | 0.00 | 0 | 0.00 / 0.00 |
| 2025-11-14 | -5.13% | 0.00 | 0 | 0.00 / 0.00 |
| 2025-11-04 | -4.78% | 0.00 | 0 | 0.00 / 0.00 |
| 2026-01-20 | -4.54% | 0.00 | 0 | 0.00 / 0.00 |
| 2025-12-01 | -4.52% | 0.00 | 0 | 0.00 / 0.00 |

## breakout/single/stress

Price P&L -40.3146 − fees 21.1782 − slippage 9.1106 + funding -0.1421 = net -70.7456 USDT.
Worst campaign -3.2379; maximum holding 240min; minute-close peak/mean exposure 396.50/2.92 USDT; within-minute filled-notional portfolio bound 396.30 USDT.
Entry/add fills 223/0; exits {"account_halt": 1, "breakout_failure": 45, "stop": 56, "target": 119, "timeout": 2}.
Monthly marked P&L: 2025-10: -9.85; 2025-11: -5.62; 2025-12: -5.15; 2026-01: -5.48; 2026-02: -1.55; 2026-03: -4.04; 2026-04: -10.01; 2026-05: 0.75; 2026-06: -5.31; 2026-07: -10.33; 2026-08: -15.89; 2026-09: 1.73
Two-month marked P&L: 2025-10..2025-11: -15.48; 2025-12..2026-01: -10.63; 2026-02..2026-03: -5.59; 2026-04..2026-05: -9.25; 2026-06..2026-07: -15.64; 2026-08..2026-09: -14.16

| Asset | Net USDT | Campaigns | Diagnostics |
|---|---:|---:|---|
| BTC | -20.46 | 123 | {"account_halts": 0, "add_fills": 0, "daily_halts": 0, "entry_fills": 123, "passive_rejections": 0, "risk_refusals": 0, "rounding_refusals": 0, "unfilled_orders": 75} |
| ETH | -50.28 | 100 | {"account_halts": 1, "add_fills": 0, "daily_halts": 0, "entry_fills": 100, "passive_rejections": 0, "risk_refusals": 0, "rounding_refusals": 0, "unfilled_orders": 49} |

Worst10 BTC daily-return dates, selected ex post for a disclosed stress diagnostic:

| UTC date | BTC return | Marked portfolio P&L | Adds | Minute-close peak / filled-notional bound |
|---|---:|---:|---:|---:|
| 2026-02-05 | -14.04% | 0.00 | 0 | 0.00 / 0.00 |
| 2025-10-10 | -7.29% | 0.00 | 0 | 0.00 / 0.00 |
| 2026-01-31 | -6.54% | 0.00 | 0 | 0.00 / 0.00 |
| 2026-06-02 | -6.53% | 0.00 | 0 | 0.00 / 0.00 |
| 2025-11-20 | -5.36% | 0.00 | 0 | 0.00 / 0.00 |
| 2026-01-29 | -5.22% | 0.00 | 0 | 0.00 / 0.00 |
| 2025-11-14 | -5.13% | 0.00 | 0 | 0.00 / 0.00 |
| 2025-11-04 | -4.78% | 0.00 | 0 | 0.00 / 0.00 |
| 2026-01-20 | -4.54% | 0.00 | 0 | 0.00 / 0.00 |
| 2025-12-01 | -4.52% | 0.00 | 0 | 0.00 / 0.00 |

## breakout/averaging/normal

Price P&L -34.6404 − fees 26.0522 − slippage 4.3551 + funding -0.1711 = net -65.2187 USDT.
Worst campaign -3.6879; maximum holding 240min; minute-close peak/mean exposure 640.67/3.59 USDT; within-minute filled-notional portfolio bound 640.11 USDT.
Entry/add fills 261/18; exits {"account_halt": 1, "breakout_failure": 50, "stop": 59, "target": 149, "timeout": 2}.
Monthly marked P&L: 2025-10: -8.83; 2025-11: -6.19; 2025-12: -2.69; 2026-01: -5.29; 2026-02: -1.49; 2026-03: -0.88; 2026-04: -11.64; 2026-05: -2.05; 2026-06: -6.23; 2026-07: -6.22; 2026-08: -14.92; 2026-09: 1.20
Two-month marked P&L: 2025-10..2025-11: -15.02; 2025-12..2026-01: -7.98; 2026-02..2026-03: -2.37; 2026-04..2026-05: -13.69; 2026-06..2026-07: -12.44; 2026-08..2026-09: -13.72

| Asset | Net USDT | Campaigns | Diagnostics |
|---|---:|---:|---|
| BTC | -15.03 | 148 | {"account_halts": 0, "add_fills": 3, "daily_halts": 0, "entry_fills": 148, "passive_rejections": 0, "risk_refusals": 0, "rounding_refusals": 6, "unfilled_orders": 56} |
| ETH | -50.19 | 113 | {"account_halts": 1, "add_fills": 15, "daily_halts": 0, "entry_fills": 113, "passive_rejections": 0, "risk_refusals": 0, "rounding_refusals": 0, "unfilled_orders": 43} |

Worst10 BTC daily-return dates, selected ex post for a disclosed stress diagnostic:

| UTC date | BTC return | Marked portfolio P&L | Adds | Minute-close peak / filled-notional bound |
|---|---:|---:|---:|---:|
| 2026-02-05 | -14.04% | 0.00 | 0 | 0.00 / 0.00 |
| 2025-10-10 | -7.29% | 0.00 | 0 | 0.00 / 0.00 |
| 2026-01-31 | -6.54% | 0.00 | 0 | 0.00 / 0.00 |
| 2026-06-02 | -6.53% | 0.00 | 0 | 0.00 / 0.00 |
| 2025-11-20 | -5.36% | 0.00 | 0 | 0.00 / 0.00 |
| 2026-01-29 | -5.22% | 0.00 | 0 | 0.00 / 0.00 |
| 2025-11-14 | -5.13% | 0.00 | 0 | 0.00 / 0.00 |
| 2025-11-04 | -4.78% | 0.00 | 0 | 0.00 / 0.00 |
| 2026-01-20 | -4.54% | 0.00 | 0 | 0.00 / 0.00 |
| 2025-12-01 | -4.52% | 0.00 | 0 | 0.00 / 0.00 |

## breakout/averaging/stress

Price P&L -39.8422 − fees 21.8858 − slippage 9.4886 + funding -0.1421 = net -71.3587 USDT.
Worst campaign -3.8283; maximum holding 240min; minute-close peak/mean exposure 534.31/3.03 USDT; within-minute filled-notional portfolio bound 535.86 USDT.
Entry/add fills 221/11; exits {"account_halt": 1, "breakout_failure": 43, "stop": 56, "target": 119, "timeout": 2}.
Monthly marked P&L: 2025-10: -10.40; 2025-11: -5.62; 2025-12: -5.15; 2026-01: -5.64; 2026-02: -1.55; 2026-03: -4.04; 2026-04: -10.26; 2026-05: 0.75; 2026-06: -6.54; 2026-07: -11.64; 2026-08: -13.00; 2026-09: 1.73
Two-month marked P&L: 2025-10..2025-11: -16.02; 2025-12..2026-01: -10.79; 2026-02..2026-03: -5.59; 2026-04..2026-05: -9.51; 2026-06..2026-07: -18.18; 2026-08..2026-09: -11.27

| Asset | Net USDT | Campaigns | Diagnostics |
|---|---:|---:|---|
| BTC | -21.00 | 123 | {"account_halts": 0, "add_fills": 1, "daily_halts": 0, "entry_fills": 123, "passive_rejections": 0, "risk_refusals": 0, "rounding_refusals": 3, "unfilled_orders": 86} |
| ETH | -50.36 | 98 | {"account_halts": 1, "add_fills": 10, "daily_halts": 0, "entry_fills": 98, "passive_rejections": 0, "risk_refusals": 0, "rounding_refusals": 0, "unfilled_orders": 56} |

Worst10 BTC daily-return dates, selected ex post for a disclosed stress diagnostic:

| UTC date | BTC return | Marked portfolio P&L | Adds | Minute-close peak / filled-notional bound |
|---|---:|---:|---:|---:|
| 2026-02-05 | -14.04% | 0.00 | 0 | 0.00 / 0.00 |
| 2025-10-10 | -7.29% | 0.00 | 0 | 0.00 / 0.00 |
| 2026-01-31 | -6.54% | 0.00 | 0 | 0.00 / 0.00 |
| 2026-06-02 | -6.53% | 0.00 | 0 | 0.00 / 0.00 |
| 2025-11-20 | -5.36% | 0.00 | 0 | 0.00 / 0.00 |
| 2026-01-29 | -5.22% | 0.00 | 0 | 0.00 / 0.00 |
| 2025-11-14 | -5.13% | 0.00 | 0 | 0.00 / 0.00 |
| 2025-11-04 | -4.78% | 0.00 | 0 | 0.00 / 0.00 |
| 2026-01-20 | -4.54% | 0.00 | 0 | 0.00 / 0.00 |
| 2025-12-01 | -4.52% | 0.00 | 0 | 0.00 / 0.00 |

## Limits

All data are retrospective development data, already used for prior candidate research. No prospective holdout or tuned winner.
Passive fills require strict trade-through2bps normal/5bps stress; mere touches do not fill. Placement rejects crossing limits using minute-open proxy.
A post-only order's actual queue, acceptance, latency and fills cannot be reconstructed from OHLC. These are deliberately explicit simulation assumptions.
Maker fees2bps each side; safety exits taker5bps plus2/5bps adverse slippage. Stress changes both fill eligibility and taker slippage, so trade samples can differ.
The entry/add minute cannot take profit; stops win ambiguous bars; pending adds can prevent assuming a same-minute target fill. Gaps can exceed stop budgets.
Not every claimed scalp is represented: no real-time news or social popularity data, no other coins, no unbounded martingale or rising leverage.
Daily/weekly candle context is descriptive; it was not used to fit filters. Twelve-hour context was not added as another fitted filter.
The unit steps/minimum notionals are static modeling assumptions. MDD and mean/peak marked exposure use minute-close marks, not tick-level liquidation risk.
Filled-notional bound retains same-minute round trips; it sums each asset's within-minute maximum cost notional and can overstate synchronized portfolio exposure. Campaign max_exposure is an OHLC high-price envelope, not observed tick exposure.
A pass authorizes research consideration only, never automatic paper/Demo/live execution. Existing MA200 operation remains unchanged.

## Reproduction

```bash
.venv/bin/python scripts/run_candle_scalp_research.py
```

study-manifest.json locks registration, source minute/funding/mark hashes. summary.json locks source code hashes and all12 configs/results.
CSV artifacts contain complete campaign/fill ledgers and daily marked-equity paths.
