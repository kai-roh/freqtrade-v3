# Phase 2c follow-up — fixed MA200 comparison

- generated_at: `2026-10-02T09:38:28Z`
- plan: `docs/PHASE2C_MA200_COMPARISON.md` (diagnosis on already-seen data; never a promotion basis)
- decision: **PAUSE_RESEARCH**
- sleeve 500 USDT, half per asset, at most 1x; spot taker fee 10 bps, perpetual taker fee 5 bps

## normal cost — 2022-08-01 → 2026-10-01 (judged)

| Strategy | Mode | Net USDT | Ann. return | Sharpe | MDD | Return/MDD | Worst year | Price | Funding | Fees | Slippage | Orders/yr | Skipped/attempts |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| MA200-perp | ideal | 340.54 | 13.26% | 0.80 | 13.41% | 0.99 | -16.60 | 402.97 | -50.62 | 8.43 | 3.37 | 21.3 | 0/87 |
| BHVT-perp | ideal | 339.60 | 13.23% | 0.78 | 24.81% | 0.53 | -46.62 | 416.35 | -75.29 | 1.04 | 0.42 | 8.1 | 0/32 |
| BHVT-spot | ideal | 413.85 | 15.55% | 0.92 | 22.68% | 0.69 | -46.17 | 416.35 | 0.00 | 2.09 | 0.42 | 8.1 | 0/32 |
| MA200-perp | constrained | 318.21 | 12.53% | 0.76 | 14.32% | 0.88 | -5.33 | 377.69 | -48.99 | 7.50 | 3.00 | 21.6 | 234/322 |
| BHVT-perp | constrained | 340.90 | 13.27% | 0.81 | 22.39% | 0.59 | -44.35 | 413.03 | -70.44 | 1.21 | 0.48 | 7.7 | 229/259 |
| BHVT-spot | constrained | 423.44 | 15.84% | 0.93 | 22.60% | 0.70 | -46.11 | 426.17 | 0.00 | 2.27 | 0.45 | 8.9 | 0/35 |

MA200 direction changes: BTC 33, ETH 25.

| Constrained P&L by year | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---:|---:|---:|---:|---:|
| MA200-perp | 44.10 | 57.51 | 117.11 | -5.33 | 104.82 |
| BHVT-perp | -44.35 | 230.29 | 154.72 | -0.19 | 0.43 |
| BHVT-spot | -46.11 | 255.25 | 212.82 | -1.47 | 2.96 |

## normal cost — 2020-08-01 → 2026-10-01 (reference only)

| Strategy | Mode | Net USDT | Ann. return | Sharpe | MDD | Return/MDD | Worst year | Price | Funding | Fees | Slippage | Orders/yr | Skipped/attempts |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| MA200-perp | ideal | 655.20 | 14.53% | 1.03 | 16.97% | 0.86 | -16.60 | 794.40 | -123.86 | 10.95 | 4.38 | 20.7 | 0/126 |
| BHVT-perp | ideal | 561.31 | 12.97% | 0.88 | 24.81% | 0.52 | -164.17 | 717.00 | -153.67 | 1.44 | 0.58 | 7.5 | 0/44 |
| BHVT-spot | ideal | 713.55 | 15.45% | 1.09 | 22.30% | 0.69 | -159.96 | 717.00 | 0.00 | 2.88 | 0.58 | 7.5 | 0/44 |
| MA200-perp | constrained | 631.68 | 14.15% | 1.01 | 16.17% | 0.87 | -5.33 | 761.60 | -116.47 | 9.61 | 3.84 | 20.7 | 245/371 |
| BHVT-perp | constrained | 563.30 | 13.00% | 0.89 | 24.40% | 0.53 | -149.43 | 714.62 | -149.06 | 1.61 | 0.64 | 7.0 | 238/279 |
| BHVT-spot | constrained | 723.02 | 15.59% | 1.10 | 22.27% | 0.70 | -159.69 | 726.70 | 0.00 | 3.07 | 0.61 | 7.9 | 0/47 |

MA200 direction changes: BTC 52, ETH 34.

**Criteria (normal, MA200-perp vs BHVT-spot, constrained):** C1_retention PASS, C2_drawdown PASS, C3_efficiency PASS, C4_worst_year PASS, C5_implementable FAIL

Reference against BHVT-perp: C1_retention PASS, C2_drawdown PASS, C3_efficiency PASS, C4_worst_year PASS, C5_implementable FAIL

Phase 2c H4 walk-forward, constrained with the corrected order rule (gate 8 reference): net 184.89 USDT, Sharpe 0.57, MDD 17.93%.

## stress cost — 2022-08-01 → 2026-10-01 (judged)

| Strategy | Mode | Net USDT | Ann. return | Sharpe | MDD | Return/MDD | Worst year | Price | Funding | Fees | Slippage | Orders/yr | Skipped/attempts |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| MA200-perp | ideal | 335.48 | 13.09% | 0.79 | 13.50% | 0.97 | -18.69 | 402.97 | -50.62 | 8.43 | 8.43 | 21.3 | 0/87 |
| BHVT-perp | ideal | 338.97 | 13.21% | 0.78 | 24.83% | 0.53 | -46.67 | 416.35 | -75.29 | 1.04 | 1.04 | 8.1 | 0/32 |
| BHVT-spot | ideal | 413.22 | 15.53% | 0.92 | 22.70% | 0.68 | -46.23 | 416.35 | 0.00 | 2.09 | 1.04 | 8.1 | 0/32 |
| MA200-perp | constrained | 313.71 | 12.38% | 0.76 | 14.41% | 0.86 | -7.02 | 377.69 | -48.99 | 7.50 | 7.50 | 21.6 | 234/322 |
| BHVT-perp | constrained | 340.17 | 13.24% | 0.81 | 22.42% | 0.59 | -44.41 | 413.03 | -70.44 | 1.21 | 1.21 | 7.7 | 229/259 |
| BHVT-spot | constrained | 422.76 | 15.82% | 0.93 | 22.62% | 0.70 | -46.17 | 426.17 | 0.00 | 2.27 | 1.14 | 8.9 | 0/35 |

MA200 direction changes: BTC 33, ETH 25.

| Constrained P&L by year | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---:|---:|---:|---:|---:|
| MA200-perp | 44.04 | 56.24 | 116.03 | -7.02 | 104.42 |
| BHVT-perp | -44.41 | 230.11 | 154.60 | -0.29 | 0.16 |
| BHVT-spot | -46.17 | 255.06 | 212.64 | -1.52 | 2.74 |

## stress cost — 2020-08-01 → 2026-10-01 (reference only)

| Strategy | Mode | Net USDT | Ann. return | Sharpe | MDD | Return/MDD | Worst year | Price | Funding | Fees | Slippage | Orders/yr | Skipped/attempts |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| MA200-perp | ideal | 648.63 | 14.42% | 1.02 | 17.12% | 0.84 | -18.69 | 794.40 | -123.86 | 10.95 | 10.95 | 20.7 | 0/126 |
| BHVT-perp | ideal | 560.45 | 12.95% | 0.88 | 24.82% | 0.52 | -164.22 | 717.00 | -153.67 | 1.44 | 1.44 | 7.5 | 0/44 |
| BHVT-spot | ideal | 712.68 | 15.43% | 1.09 | 22.31% | 0.69 | -160.01 | 717.00 | 0.00 | 2.88 | 1.44 | 7.5 | 0/44 |
| MA200-perp | constrained | 625.91 | 14.05% | 1.01 | 16.29% | 0.86 | -7.02 | 761.60 | -116.47 | 9.61 | 9.61 | 20.7 | 245/371 |
| BHVT-perp | constrained | 562.34 | 12.99% | 0.89 | 24.41% | 0.53 | -149.47 | 714.62 | -149.06 | 1.61 | 1.61 | 7.0 | 238/279 |
| BHVT-spot | constrained | 722.10 | 15.58% | 1.10 | 22.28% | 0.70 | -159.74 | 726.70 | 0.00 | 3.07 | 1.53 | 7.9 | 0/47 |

MA200 direction changes: BTC 52, ETH 34.

**Criteria (stress, MA200-perp vs BHVT-spot, constrained):** C1_retention PASS, C2_drawdown PASS, C3_efficiency PASS, C4_worst_year PASS, C5_implementable FAIL

Reference against BHVT-perp: C1_retention PASS, C2_drawdown PASS, C3_efficiency PASS, C4_worst_year PASS, C5_implementable FAIL

Phase 2c H4 walk-forward, constrained with the corrected order rule (gate 8 reference): net 177.81 USDT, Sharpe 0.55, MDD 18.18%.

## Interpretation

OBSERVE_ELIGIBLE means only that an order-free forward observation of the fixed MA200 may be registered; it is not evidence of an edge, because MA200 was singled out after the Phase 2c results. PAUSE_RESEARCH means the drawdown advantage does not survive the spot comparison or the exchange constraints. Constrained mode applies the 2026-10 filters to past prices; the end-of-window close ignores the filters.
