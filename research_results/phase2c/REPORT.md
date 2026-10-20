# Phase 2c Research Report — BTC/ETH low-frequency trend

- generated_at: `2026-10-02T08:44:42Z`
- decision: **STOP_NO_EDGE**
- registration: `docs/PHASE2C_PREREGISTRATION.md`
- panel: 2020-01-01 → 2026-10-01T23:00 (all development data; confirmation only on data after 2026-10-02)
- sleeve: 500 USDT, half per asset, at most 1x

## Walk-forward continuous account (2022-08-01 → 2026-10-01)

| Cost | Mode | Net USDT | Ann. return | Sharpe | PF | MDD | Price | Funding | Fees | Slippage | Long price | Short price | Trades | Turnover x/yr |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| normal | ideal | 200.63 | 8.42% | 0.54 | 1.100 | 19.23% | 260.86 | -37.06 | 16.55 | 6.62 | 340.48 | -79.62 | 284 | 15.9 |
| normal | constrained | 270.81 | 10.93% | 0.74 | 1.146 | 16.28% | 326.50 | -38.20 | 12.49 | 5.00 | 368.86 | -42.36 | 248 | 12.0 |
| stress | ideal | 190.70 | 8.05% | 0.52 | 1.096 | 19.56% | 260.86 | -37.06 | 16.55 | 16.55 | 340.48 | -79.62 | 284 | 15.9 |
| stress | constrained | 263.32 | 10.67% | 0.72 | 1.142 | 16.50% | 326.50 | -38.20 | 12.49 | 12.49 | 368.86 | -42.36 | 248 | 12.0 |

## Controls over the same period

| Cost | Strategy | Net USDT | Ann. return | Sharpe | MDD | Time in market BTC/ETH |
|---|---|---:|---:|---:|---:|---|
| normal | H4 walk-forward | 200.63 | 8.42% | 0.54 | 19.23% | 73% / 73% |
| normal | H0 | 0.00 | 0.00% | 0.00 | 0.00% | 0% / 0% |
| normal | BH-VT | 339.60 | 13.23% | 0.78 | 24.81% | 100% / 100% |
| normal | MA200 | 340.54 | 13.26% | 0.80 | 13.41% | 100% / 100% |
| stress | H4 walk-forward | 190.70 | 8.05% | 0.52 | 19.56% | 73% / 73% |
| stress | H0 | 0.00 | 0.00% | 0.00 | 0.00% | 0% / 0% |
| stress | BH-VT | 338.97 | 13.21% | 0.78 | 24.83% | 100% / 100% |
| stress | MA200 | 335.48 | 13.09% | 0.79 | 13.50% | 100% / 100% |

## Gates

- **normal**: net_positive PASS, max_drawdown PASS, beats_bh_vt_sharpe FAIL, beats_bh_vt_drawdown PASS, constrained_net_positive PASS, positive_windows PASS, positive_configs PASS, without_best_year PASS, without_best_episode PASS, pbo FAIL
- **stress**: net_positive PASS, max_drawdown PASS, beats_bh_vt_sharpe FAIL, beats_bh_vt_drawdown PASS, constrained_net_positive PASS, annual_return_stress PASS
- PBO (normal): 0.34 over 6 configurations
- Block bootstrap of daily net returns (normal, 20-day blocks): mean 0.00027, 95% CI [-0.00014, 0.00068]

## Window selections (normal cost)

| Window | Validation | Selected on training | Validation P&L |
|---:|---|---|---:|
| 0 | 2022-08-01 → 2023-01-30 | H4 L=60d binary | 26.65 |
| 1 | 2023-01-30 → 2023-07-31 | H4 L=60d binary | -47.66 |
| 2 | 2023-07-31 → 2024-01-29 | H4 L=60d binary | 57.83 |
| 3 | 2024-01-29 → 2024-07-29 | H4 L=60d binary | 13.88 |
| 4 | 2024-07-29 → 2025-01-27 | H4 L=120d linear | -3.39 |
| 5 | 2025-01-27 → 2025-07-28 | H4 L=60d binary | 61.26 |
| 6 | 2025-07-28 → 2026-01-26 | H4 L=60d binary | -10.18 |
| 7 | 2026-01-26 → 2026-07-27 | H4 L=60d binary | 7.79 |
| 8 | 2026-07-27 → 2026-10-01 | H4 L=60d binary | 94.45 |

## Full-period configurations (2020-07-01 → 2026-10-01, normal cost)

| Configuration | Net USDT | Ann. return | Sharpe | MDD | Episodes BTC/ETH |
|---|---:|---:|---:|---:|---|
| H4 L=20d binary | 256.41 | 6.84% | 0.55 | 22.16% | 185 / 175 |
| H4 L=20d linear | 225.86 | 6.14% | 0.66 | 14.94% | 251 / 253 |
| H4 L=60d binary | 687.40 | 14.82% | 1.12 | 12.22% | 98 / 93 |
| H4 L=60d linear | 375.99 | 9.38% | 0.92 | 8.30% | 97 / 93 |
| H4 L=120d binary | 292.37 | 7.64% | 0.61 | 19.29% | 72 / 90 |
| H4 L=120d linear | 323.54 | 8.30% | 0.82 | 12.42% | 61 / 45 |

## Walk-forward P&L by calendar year (normal cost, USDT)

| 2022 | 2023 | 2024 | 2025 | 2026 |
|---:|---:|---:|---:|---:|
| -42.49 | 97.53 | -16.88 | 86.38 | 76.09 |

## Interpretation

All data here is development data that had been seen before; the verdict can at most earn an order-free forward observation on data after 2026-10-02. Conviction is expressed as one net position per asset, never as simultaneous long and short. Constrained mode applies the 2026-10 lot step and minimum notional to past prices.
