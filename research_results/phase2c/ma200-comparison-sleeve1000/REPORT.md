# Phase 2c follow-up — fixed MA200 comparison

- generated_at: `2026-10-02T09:55:36Z`
- plan: `docs/PHASE2C_MA200_COMPARISON.md` (diagnosis on already-seen data; never a promotion basis)
- decision: **OBSERVE_ELIGIBLE**
- **plan departure:** Decision 0018: sleeve chosen by the user after the 500 USDT result
- sleeve 1000 USDT, half per asset, at most 1x; spot taker fee 10 bps, perpetual taker fee 5 bps

## normal cost — 2022-08-01 → 2026-10-01 (judged)

| Strategy | Mode | Net USDT | Ann. return | Sharpe | MDD | Return/MDD | Worst year | Price | Funding | Fees | Slippage | Orders/yr | Skipped/attempts |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| MA200-perp | ideal | 681.08 | 13.26% | 0.80 | 13.41% | 0.99 | -33.21 | 805.94 | -101.25 | 16.86 | 6.75 | 21.3 | 0/87 |
| BHVT-perp | ideal | 679.20 | 13.23% | 0.78 | 24.81% | 0.53 | -93.24 | 832.70 | -150.58 | 2.09 | 0.83 | 8.1 | 0/32 |
| BHVT-spot | ideal | 827.70 | 15.55% | 0.92 | 22.68% | 0.69 | -92.34 | 832.70 | 0.00 | 4.17 | 0.83 | 8.1 | 0/32 |
| MA200-perp | constrained | 675.15 | 13.16% | 0.80 | 13.25% | 0.99 | -21.41 | 792.75 | -94.75 | 16.33 | 6.53 | 23.5 | 3/99 |
| BHVT-perp | constrained | 725.95 | 13.97% | 0.83 | 23.30% | 0.60 | -98.61 | 872.19 | -142.74 | 2.50 | 1.00 | 9.3 | 3/40 |
| BHVT-spot | constrained | 847.12 | 15.84% | 0.93 | 22.62% | 0.70 | -92.28 | 852.58 | 0.00 | 4.55 | 0.91 | 8.9 | 0/35 |

MA200 direction changes: BTC 33, ETH 25.

| Constrained P&L by year | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---:|---:|---:|---:|---:|
| MA200-perp | 98.14 | 137.87 | 244.80 | -21.41 | 215.76 |
| BHVT-perp | -98.61 | 503.48 | 325.89 | -15.70 | 10.89 |
| BHVT-spot | -92.28 | 510.72 | 425.92 | -2.98 | 5.75 |

## normal cost — 2020-08-01 → 2026-10-01 (reference only)

| Strategy | Mode | Net USDT | Ann. return | Sharpe | MDD | Return/MDD | Worst year | Price | Funding | Fees | Slippage | Orders/yr | Skipped/attempts |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| MA200-perp | ideal | 1310.41 | 14.53% | 1.03 | 16.97% | 0.86 | -33.21 | 1588.80 | -247.73 | 21.90 | 8.76 | 20.7 | 0/126 |
| BHVT-perp | ideal | 1122.62 | 12.97% | 0.88 | 24.81% | 0.52 | -328.34 | 1434.00 | -307.35 | 2.88 | 1.15 | 7.5 | 0/44 |
| BHVT-spot | ideal | 1427.09 | 15.45% | 1.09 | 22.30% | 0.69 | -319.93 | 1434.00 | 0.00 | 5.75 | 1.15 | 7.5 | 0/44 |
| MA200-perp | constrained | 1325.45 | 14.65% | 1.06 | 14.31% | 1.02 | -21.41 | 1587.84 | -233.06 | 20.96 | 8.38 | 22.0 | 3/137 |
| BHVT-perp | constrained | 1190.85 | 13.55% | 0.94 | 24.56% | 0.55 | -304.38 | 1490.40 | -294.91 | 3.31 | 1.32 | 8.1 | 3/51 |
| BHVT-spot | constrained | 1446.42 | 15.60% | 1.10 | 22.29% | 0.70 | -319.70 | 1453.78 | 0.00 | 6.13 | 1.23 | 7.9 | 0/47 |

MA200 direction changes: BTC 52, ETH 34.

**Criteria (normal, MA200-perp vs BHVT-spot, constrained):** C1_retention PASS, C2_drawdown PASS, C3_efficiency PASS, C4_worst_year PASS, C5_implementable PASS

Reference against BHVT-perp: C1_retention PASS, C2_drawdown PASS, C3_efficiency PASS, C4_worst_year PASS, C5_implementable PASS

Phase 2c H4 walk-forward, constrained with the corrected order rule (gate 8 reference): net 435.99 USDT, Sharpe 0.62, MDD 17.58%.

## stress cost — 2022-08-01 → 2026-10-01 (judged)

| Strategy | Mode | Net USDT | Ann. return | Sharpe | MDD | Return/MDD | Worst year | Price | Funding | Fees | Slippage | Orders/yr | Skipped/attempts |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| MA200-perp | ideal | 670.96 | 13.09% | 0.79 | 13.50% | 0.97 | -37.38 | 805.94 | -101.25 | 16.86 | 16.86 | 21.3 | 0/87 |
| BHVT-perp | ideal | 677.95 | 13.21% | 0.78 | 24.83% | 0.53 | -93.35 | 832.70 | -150.58 | 2.09 | 2.09 | 8.1 | 0/32 |
| BHVT-spot | ideal | 826.45 | 15.53% | 0.92 | 22.70% | 0.68 | -92.46 | 832.70 | 0.00 | 4.17 | 2.09 | 8.1 | 0/32 |
| MA200-perp | constrained | 665.35 | 13.00% | 0.79 | 13.34% | 0.97 | -25.27 | 792.75 | -94.75 | 16.33 | 16.33 | 23.5 | 3/99 |
| BHVT-perp | constrained | 724.45 | 13.95% | 0.83 | 23.33% | 0.60 | -98.71 | 872.19 | -142.74 | 2.50 | 2.50 | 9.3 | 3/40 |
| BHVT-spot | constrained | 845.76 | 15.82% | 0.93 | 22.64% | 0.70 | -92.39 | 852.58 | 0.00 | 4.55 | 2.27 | 8.9 | 0/35 |

MA200 direction changes: BTC 33, ETH 25.

| Constrained P&L by year | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---:|---:|---:|---:|---:|
| MA200-perp | 98.04 | 135.26 | 242.38 | -25.27 | 214.94 |
| BHVT-perp | -98.71 | 503.00 | 325.63 | -15.84 | 10.37 |
| BHVT-spot | -92.39 | 510.34 | 425.58 | -3.08 | 5.31 |

## stress cost — 2020-08-01 → 2026-10-01 (reference only)

| Strategy | Mode | Net USDT | Ann. return | Sharpe | MDD | Return/MDD | Worst year | Price | Funding | Fees | Slippage | Orders/yr | Skipped/attempts |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| MA200-perp | ideal | 1297.27 | 14.42% | 1.02 | 17.12% | 0.84 | -37.38 | 1588.80 | -247.73 | 21.90 | 21.90 | 20.7 | 0/126 |
| BHVT-perp | ideal | 1120.90 | 12.95% | 0.88 | 24.82% | 0.52 | -328.44 | 1434.00 | -307.35 | 2.88 | 2.88 | 7.5 | 0/44 |
| BHVT-spot | ideal | 1425.37 | 15.43% | 1.09 | 22.31% | 0.69 | -320.02 | 1434.00 | 0.00 | 5.75 | 2.88 | 7.5 | 0/44 |
| MA200-perp | constrained | 1312.87 | 14.55% | 1.05 | 14.44% | 1.01 | -25.27 | 1587.84 | -233.06 | 20.96 | 20.96 | 22.0 | 3/137 |
| BHVT-perp | constrained | 1188.87 | 13.53% | 0.94 | 24.57% | 0.55 | -304.44 | 1490.40 | -294.91 | 3.31 | 3.31 | 8.1 | 3/51 |
| BHVT-spot | constrained | 1444.58 | 15.58% | 1.10 | 22.30% | 0.70 | -319.79 | 1453.78 | 0.00 | 6.13 | 3.07 | 7.9 | 0/47 |

MA200 direction changes: BTC 52, ETH 34.

**Criteria (stress, MA200-perp vs BHVT-spot, constrained):** C1_retention PASS, C2_drawdown PASS, C3_efficiency PASS, C4_worst_year PASS, C5_implementable PASS

Reference against BHVT-perp: C1_retention PASS, C2_drawdown PASS, C3_efficiency PASS, C4_worst_year PASS, C5_implementable PASS

Phase 2c H4 walk-forward, constrained with the corrected order rule (gate 8 reference): net 419.39 USDT, Sharpe 0.60, MDD 17.84%.

## Interpretation

OBSERVE_ELIGIBLE means only that an order-free forward observation of the fixed MA200 may be registered; it is not evidence of an edge, because MA200 was singled out after the Phase 2c results. PAUSE_RESEARCH means the drawdown advantage does not survive the spot comparison or the exchange constraints. Constrained mode applies the 2026-10 filters to past prices; the end-of-window close ignores the filters.
