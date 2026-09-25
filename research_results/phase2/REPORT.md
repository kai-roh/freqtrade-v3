# Phase 2 Research Report

- generated_at: `2026-09-17T00:30:00Z`
- decision: **STOP_NO_EDGE**
- registration: `docs/PHASE2_PREREGISTRATION.md`
- universe: BTC, ETH, SOL, BNB, XRP, DOGE, ADA, LINK
- panel: 2025-06-23 → 2026-09-16

## Gate results (daily portfolio net returns, sleeve basis)

| Hypothesis | Cost | Days | PF | Expectancy/day | MDD | Positive folds | Fold conc. | Asset conc. | PBO | Blocked entries | Pass |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| H1 | normal | 270 | 0.869 | -0.000271 | 12.41% | 4 | 0.38 | 0.52 | 0.77 | 276 | FAIL |
| H1 | stress | 270 | 0.766 | -0.000473 | 16.60% | 3 | 0.60 | 0.50 | 0.76 | 276 | FAIL |
| H2 | normal | 270 | 0.755 | -0.000753 | 25.38% | 2 | 0.74 | 0.29 | 0.43 | 0 | FAIL |
| H2 | stress | 270 | 0.728 | -0.000854 | 26.46% | 2 | 0.79 | 0.29 | 0.20 | 0 | FAIL |

## P&L decomposition (USDT, sum over validation folds)

| Hypothesis | Cost | Total | Price | Funding | Fees | Slippage | Trades | Episodes |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| H1 | normal | -14.14 | -3.70 | 3.38 | 9.45 | 4.36 | 347 | 15 |
| H1 | stress | -25.02 | -9.28 | 3.17 | 9.45 | 9.45 | 347 | 15 |
| H2 | normal | -40.34 | -21.51 | 0.85 | 13.34 | 6.34 | 376 | 16 |
| H2 | stress | -45.63 | -19.80 | 0.85 | 13.34 | 13.34 | 376 | 16 |

## Fold selections

### H1

| Cost | Fold | Selected on training | Train Sharpe | Validation return | Validation PF |
|---|---:|---|---:|---:|---:|
| normal | 0 | H1 W=168h k=3 s_min=0.5bp | 0.99 | -7.48% | 0.398 |
| normal | 1 | H1 W=48h k=3 s_min=0.5bp | 2.24 | 1.71% | 1.205 |
| normal | 2 | H1 W=48h k=3 s_min=0.5bp | 2.43 | 2.62% | 1.348 |
| normal | 3 | H1 W=48h k=3 s_min=0.5bp | 2.49 | -8.71% | 0.402 |
| normal | 4 | H1 W=48h k=2 s_min=1.0bp | 2.42 | 1.34% | 1.222 |
| normal | 5 | H1 W=48h k=2 s_min=1.0bp | 1.40 | 3.46% | 1.648 |
| stress | 0 | H1 W=168h k=3 s_min=0.5bp | 0.89 | -7.33% | 0.399 |
| stress | 1 | H1 W=48h k=3 s_min=0.5bp | 1.77 | 1.06% | 1.127 |
| stress | 2 | H1 W=48h k=3 s_min=0.5bp | 2.17 | -1.46% | 0.765 |
| stress | 3 | H1 W=48h k=3 s_min=0.5bp | 2.18 | -9.11% | 0.379 |
| stress | 4 | H1 W=48h k=2 s_min=1.0bp | 1.80 | 1.11% | 1.184 |
| stress | 5 | H1 W=48h k=2 s_min=1.0bp | 1.21 | 3.21% | 1.587 |

### H2

| Cost | Fold | Selected on training | Train Sharpe | Validation return | Validation PF |
|---|---:|---|---:|---:|---:|
| normal | 0 | H2 L=3d k=3 H=3d | 0.94 | -3.85% | 0.739 |
| normal | 1 | H2 L=3d k=2 H=3d | 2.20 | 1.90% | 1.182 |
| normal | 2 | H2 L=3d k=2 H=3d | 1.39 | 5.29% | 1.667 |
| normal | 3 | H2 L=3d k=2 H=3d | 2.86 | -7.22% | 0.516 |
| normal | 4 | H2 L=5d k=3 H=1d | 1.51 | -5.71% | 0.609 |
| normal | 5 | H2 L=10d k=2 H=3d | 1.11 | -10.58% | 0.434 |
| stress | 0 | H2 L=3d k=3 H=3d | 0.63 | -3.92% | 0.733 |
| stress | 1 | H2 L=3d k=2 H=3d | 1.66 | 1.27% | 1.124 |
| stress | 2 | H2 L=3d k=2 H=3d | 1.19 | 4.69% | 1.572 |
| stress | 3 | H2 L=3d k=2 H=3d | 2.58 | -7.44% | 0.504 |
| stress | 4 | H2 L=5d k=3 H=1d | 1.00 | -6.42% | 0.573 |
| stress | 5 | H2 L=10d k=2 H=3d | 0.91 | -10.98% | 0.422 |

## Interpretation

H0 (no trade) is the control. A hypothesis passes only if every gate holds under both cost regimes and its PBO is at or below 0.20. Results are conditional on the eight symbols chosen in 2026-09 and on Binance USD-M funding; they do not transfer to another venue. Passing authorizes only a separate Demo/shadow observation, never real capital.
