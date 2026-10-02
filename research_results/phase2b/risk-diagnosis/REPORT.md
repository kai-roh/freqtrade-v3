# Phase 2b risk-neutralization diagnosis

- generated_at: `2026-10-02T06:45:44Z`
- plan: `docs/PHASE2B_RISK_DIAGNOSIS.md` (diagnosis on already-seen data; never a promotion basis)
- decision: **SHELVE_FAMILY**

## Stage 1 — the two traced episodes

### normal cost — fold 0, `H3 W=168h k=3`

| Variant | Net | Price | Funding | Costs | Trades | Episodes | Mean abs net $ | Mean abs net β$ | Min-notional skips | Full exits |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| V0-ideal | -6.678 | -6.622 | 0.421 | 0.477 | 24 | 2 | 24.9 | 52.1 | 0 | 0 |
| V1-ideal | -5.976 | -5.872 | 0.373 | 0.477 | 27 | 2 | 2.1 | 25.0 | 0 | 0 |
| V2-ideal | -5.471 | -5.358 | 0.374 | 0.487 | 24 | 2 | 28.1 | 26.0 | 0 | 0 |
| V3-ideal | -4.895 | -4.741 | 0.332 | 0.487 | 27 | 2 | 21.8 | 3.2 | 0 | 0 |
| V0-constrained | -12.004 | -11.647 | 0.297 | 0.654 | 22 | 2 | 28.8 | 52.9 | 4 | 0 |
| V1-constrained | -9.820 | -9.487 | 0.223 | 0.556 | 26 | 2 | 2.1 | 16.6 | 4 | 0 |
| V2-constrained | -10.149 | -9.784 | 0.268 | 0.633 | 22 | 2 | 25.3 | 31.7 | 4 | 0 |
| V3-constrained | 9.946 | 9.792 | 0.335 | 0.181 | 27 | 1 | 15.3 | 3.7 | 5 | 0 |

| Mode | Effect on net | Balance (V1−V0) | Beta (V2−V0) | Both (V3−V0) | Interaction |
|---|---|---:|---:|---:|---:|
| ideal | net | +0.701 | +1.207 | +1.783 | -0.126 |
| ideal | price | +0.750 | +1.264 | +1.881 | -0.133 |
| constrained | net | +2.184 | +1.855 | +21.950 | +17.911 |
| constrained | price | +2.160 | +1.863 | +21.439 | +17.416 |

### stress cost — fold 0, `H3 W=168h k=3`

| Variant | Net | Price | Funding | Costs | Trades | Episodes | Mean abs net $ | Mean abs net β$ | Min-notional skips | Full exits |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| V0-ideal | -6.692 | -6.622 | 0.421 | 0.492 | 24 | 2 | 24.9 | 52.1 | 0 | 0 |
| V1-ideal | -5.991 | -5.872 | 0.373 | 0.492 | 27 | 2 | 2.1 | 25.0 | 0 | 0 |
| V2-ideal | -5.489 | -5.358 | 0.374 | 0.505 | 24 | 2 | 28.1 | 26.0 | 0 | 0 |
| V3-ideal | -4.914 | -4.741 | 0.332 | 0.505 | 27 | 2 | 21.8 | 3.2 | 0 | 0 |
| V0-constrained | -12.004 | -11.647 | 0.297 | 0.654 | 22 | 2 | 28.8 | 52.9 | 4 | 0 |
| V1-constrained | -9.820 | -9.487 | 0.223 | 0.556 | 26 | 2 | 2.1 | 16.6 | 4 | 0 |
| V2-constrained | -10.149 | -9.784 | 0.268 | 0.633 | 22 | 2 | 25.3 | 31.7 | 4 | 0 |
| V3-constrained | 8.715 | 8.648 | 0.339 | 0.272 | 25 | 1 | 14.4 | 2.3 | 5 | 0 |

| Mode | Effect on net | Balance (V1−V0) | Beta (V2−V0) | Both (V3−V0) | Interaction |
|---|---|---:|---:|---:|---:|
| ideal | net | +0.701 | +1.203 | +1.779 | -0.126 |
| ideal | price | +0.750 | +1.264 | +1.881 | -0.133 |
| constrained | net | +2.184 | +1.855 | +20.719 | +16.680 |
| constrained | price | +2.160 | +1.863 | +20.295 | +16.272 |

## Stage 2 — one continuous account per grid point, 2025-07-07 → 2026-07-30

| Grid point | Cost | Variant | Net | Price | Funding | Costs | Episodes | Entry-allowed decisions | Net − best episode | MDD | Min-notional skips |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| H3 W=168h k=2 | normal | V0-ideal | -1.70 | -1.95 | 2.04 | 1.79 | 6 | 33/384 | -15.92 | 12.61% | 0 |
| H3 W=168h k=2 | normal | V1-ideal | 6.53 | 6.05 | 1.90 | 1.42 | 6 | 33/386 | -7.07 | 10.19% | 0 |
| H3 W=168h k=2 | normal | V2-ideal | -0.57 | -0.08 | 1.56 | 2.05 | 7 | 32/383 | -11.12 | 6.52% | 0 |
| H3 W=168h k=2 | normal | V3-ideal | 3.99 | 4.23 | 1.45 | 1.69 | 7 | 32/385 | -6.02 | 5.93% | 0 |
| H3 W=168h k=2 | normal | V0-constrained | 3.10 | 3.14 | 1.99 | 2.04 | 7 | 32/382 | -12.06 | 9.52% | 1 |
| H3 W=168h k=2 | normal | V1-constrained | 11.68 | 10.87 | 1.74 | 0.92 | 5 | 35/387 | 1.34 | 6.51% | 13 |
| H3 W=168h k=2 | normal | V2-constrained | -5.48 | -4.89 | 1.61 | 2.21 | 8 | 30/381 | -17.84 | 10.47% | 2 |
| H3 W=168h k=2 | normal | V3-constrained | 12.63 | 11.85 | 1.70 | 0.92 | 5 | 35/387 | 2.99 | 6.00% | 13 |
| H3 W=168h k=2 | stress | V0-ideal | -2.53 | -2.60 | 2.04 | 1.97 | 6 | 33/384 | -16.52 | 12.90% | 0 |
| H3 W=168h k=2 | stress | V1-ideal | 5.53 | 5.27 | 1.90 | 1.64 | 6 | 33/386 | -7.84 | 10.22% | 0 |
| H3 W=168h k=2 | stress | V2-ideal | -2.33 | -1.53 | 1.56 | 2.37 | 7 | 32/383 | -12.62 | 7.27% | 0 |
| H3 W=168h k=2 | stress | V3-ideal | 2.07 | 2.66 | 1.44 | 2.04 | 7 | 32/385 | -7.67 | 6.34% | 0 |
| H3 W=168h k=2 | stress | V0-constrained | -1.05 | -0.81 | 1.97 | 2.21 | 7 | 32/382 | -16.04 | 11.47% | 1 |
| H3 W=168h k=2 | stress | V1-constrained | 10.27 | 9.59 | 1.74 | 1.06 | 5 | 35/387 | -0.05 | 7.09% | 13 |
| H3 W=168h k=2 | stress | V2-constrained | -10.21 | -9.37 | 1.59 | 2.43 | 8 | 30/381 | -22.40 | 12.75% | 2 |
| H3 W=168h k=2 | stress | V3-constrained | 11.23 | 10.57 | 1.69 | 1.04 | 5 | 35/387 | 1.61 | 6.58% | 13 |
| H3 W=168h k=3 | normal | V0-ideal | -8.24 | -7.63 | 0.60 | 1.22 | 4 | 14/385 | -14.13 | 9.02% | 0 |
| H3 W=168h k=3 | normal | V1-ideal | -7.54 | -6.88 | 0.55 | 1.22 | 4 | 14/385 | -13.43 | 9.02% | 0 |
| H3 W=168h k=3 | normal | V2-ideal | -7.82 | -7.70 | 0.66 | 0.78 | 3 | 16/386 | -6.90 | 8.20% | 0 |
| H3 W=168h k=3 | normal | V3-ideal | -6.64 | -6.29 | 0.51 | 0.86 | 3 | 16/386 | -6.30 | 7.64% | 0 |
| H3 W=168h k=3 | normal | V0-constrained | -11.67 | -10.83 | 0.47 | 1.31 | 4 | 14/384 | -18.77 | 11.13% | 7 |
| H3 W=168h k=3 | normal | V1-constrained | -7.50 | -7.14 | 0.37 | 0.73 | 3 | 16/386 | -9.86 | 5.69% | 8 |
| H3 W=168h k=3 | normal | V2-constrained | -10.00 | -9.19 | 0.43 | 1.24 | 4 | 14/384 | -16.75 | 10.11% | 7 |
| H3 W=168h k=3 | normal | V3-constrained | 10.96 | 10.81 | 0.49 | 0.35 | 2 | 17/388 | 0.97 | 2.74% | 9 |
| H3 W=168h k=3 | stress | V0-ideal | -8.61 | -7.94 | 0.60 | 1.27 | 4 | 14/385 | -14.50 | 9.19% | 0 |
| H3 W=168h k=3 | stress | V1-ideal | -7.91 | -7.19 | 0.55 | 1.27 | 4 | 14/385 | -13.80 | 9.19% | 0 |
| H3 W=168h k=3 | stress | V2-ideal | -7.85 | -7.70 | 0.66 | 0.80 | 3 | 16/386 | -6.91 | 8.22% | 0 |
| H3 W=168h k=3 | stress | V3-ideal | -6.67 | -6.29 | 0.51 | 0.89 | 3 | 16/386 | -6.31 | 7.65% | 0 |
| H3 W=168h k=3 | stress | V0-constrained | -12.00 | -11.13 | 0.47 | 1.34 | 4 | 14/384 | -19.10 | 11.28% | 7 |
| H3 W=168h k=3 | stress | V1-constrained | -7.61 | -7.23 | 0.37 | 0.75 | 3 | 16/386 | -9.86 | 5.69% | 8 |
| H3 W=168h k=3 | stress | V2-constrained | -10.34 | -9.48 | 0.43 | 1.28 | 4 | 14/384 | -17.08 | 10.27% | 7 |
| H3 W=168h k=3 | stress | V3-constrained | 9.45 | 9.42 | 0.50 | 0.47 | 2 | 17/388 | 0.70 | 2.79% | 9 |
| H3 W=336h k=2 | normal | V0-ideal | -28.68 | -27.32 | 0.96 | 2.32 | 7 | 25/381 | -31.61 | 15.17% | 0 |
| H3 W=336h k=2 | normal | V1-ideal | -25.03 | -23.92 | 1.02 | 2.13 | 7 | 25/383 | -27.96 | 12.52% | 0 |
| H3 W=336h k=2 | normal | V2-ideal | -22.97 | -22.12 | 0.96 | 1.81 | 5 | 27/383 | -26.09 | 11.48% | 0 |
| H3 W=336h k=2 | normal | V3-ideal | -15.85 | -15.24 | 1.03 | 1.64 | 5 | 27/384 | -18.97 | 7.92% | 0 |
| H3 W=336h k=2 | normal | V0-constrained | -33.46 | -32.40 | 0.91 | 1.98 | 7 | 25/381 | -35.79 | 17.35% | 4 |
| H3 W=336h k=2 | normal | V1-constrained | -12.64 | -12.53 | 0.77 | 0.88 | 4 | 28/386 | -15.71 | 6.32% | 14 |
| H3 W=336h k=2 | normal | V2-constrained | -32.29 | -31.33 | 0.88 | 1.85 | 6 | 26/382 | -34.52 | 16.15% | 4 |
| H3 W=336h k=2 | normal | V3-constrained | -10.20 | -10.06 | 0.75 | 0.90 | 4 | 28/386 | -14.49 | 5.10% | 14 |
| H3 W=336h k=2 | stress | V0-ideal | -29.58 | -28.08 | 0.96 | 2.46 | 7 | 25/381 | -31.84 | 15.63% | 0 |
| H3 W=336h k=2 | stress | V1-ideal | -25.96 | -24.68 | 1.02 | 2.30 | 7 | 25/383 | -28.22 | 12.98% | 0 |
| H3 W=336h k=2 | stress | V2-ideal | -24.06 | -23.05 | 0.96 | 1.97 | 5 | 27/383 | -26.45 | 12.03% | 0 |
| H3 W=336h k=2 | stress | V3-ideal | -16.94 | -16.17 | 1.03 | 1.80 | 5 | 27/384 | -19.33 | 8.47% | 0 |
| H3 W=336h k=2 | stress | V0-constrained | -34.02 | -32.88 | 0.91 | 2.05 | 7 | 25/381 | -35.79 | 17.63% | 4 |
| H3 W=336h k=2 | stress | V1-constrained | -13.12 | -12.94 | 0.77 | 0.95 | 4 | 28/386 | -15.73 | 6.56% | 14 |
| H3 W=336h k=2 | stress | V2-constrained | -32.85 | -31.81 | 0.88 | 1.92 | 6 | 26/382 | -34.52 | 16.43% | 4 |
| H3 W=336h k=2 | stress | V3-constrained | -10.83 | -10.60 | 0.75 | 0.98 | 4 | 28/386 | -14.66 | 5.42% | 14 |
| H3 W=336h k=3 | normal | V0-ideal | 0.49 | 0.89 | 0.75 | 1.16 | 4 | 15/385 | -3.82 | 6.22% | 0 |
| H3 W=336h k=3 | normal | V1-ideal | 6.89 | 7.18 | 0.76 | 1.05 | 4 | 15/386 | 2.27 | 4.78% | 0 |
| H3 W=336h k=3 | normal | V2-ideal | 3.45 | 3.55 | 0.70 | 0.79 | 3 | 16/386 | -1.35 | 5.03% | 0 |
| H3 W=336h k=3 | normal | V3-ideal | 9.85 | 9.83 | 0.71 | 0.68 | 3 | 16/387 | 5.04 | 4.06% | 0 |
| H3 W=336h k=3 | normal | V0-constrained | -6.04 | -5.64 | 0.59 | 0.99 | 4 | 15/385 | -11.40 | 8.73% | 14 |
| H3 W=336h k=3 | normal | V1-constrained | 2.14 | 2.11 | 0.54 | 0.51 | 3 | 16/387 | -0.12 | 2.79% | 14 |
| H3 W=336h k=3 | normal | V2-constrained | -0.43 | -0.40 | 0.69 | 0.73 | 4 | 15/386 | -6.65 | 6.86% | 14 |
| H3 W=336h k=3 | normal | V3-constrained | 2.81 | 2.77 | 0.54 | 0.50 | 3 | 16/387 | 0.74 | 2.76% | 14 |
| H3 W=336h k=3 | stress | V0-ideal | -0.07 | 0.43 | 0.75 | 1.25 | 4 | 15/385 | -4.38 | 6.49% | 0 |
| H3 W=336h k=3 | stress | V1-ideal | 6.29 | 6.68 | 0.76 | 1.14 | 4 | 15/386 | 1.98 | 4.94% | 0 |
| H3 W=336h k=3 | stress | V2-ideal | 3.03 | 3.18 | 0.70 | 0.85 | 3 | 16/386 | -1.78 | 5.23% | 0 |
| H3 W=336h k=3 | stress | V3-ideal | 9.39 | 9.43 | 0.71 | 0.75 | 3 | 16/387 | 4.59 | 4.06% | 0 |
| H3 W=336h k=3 | stress | V0-constrained | -6.31 | -5.88 | 0.59 | 1.01 | 4 | 15/385 | -11.67 | 8.86% | 14 |
| H3 W=336h k=3 | stress | V1-constrained | 1.73 | 1.73 | 0.54 | 0.54 | 3 | 16/387 | -0.35 | 2.82% | 14 |
| H3 W=336h k=3 | stress | V2-constrained | -0.70 | -0.64 | 0.69 | 0.75 | 4 | 15/386 | -6.92 | 6.98% | 14 |
| H3 W=336h k=3 | stress | V3-constrained | 2.63 | 2.60 | 0.54 | 0.52 | 3 | 16/387 | 0.74 | 2.85% | 14 |

## Verdict (V3-constrained)

- Grid points with at least 6 episodes: none
- Grid points economic under both costs: ['H3 W=168h k=2', 'H3 W=168h k=3', 'H3 W=336h k=3']
- Of those, robust to removing the best episode: ['H3 W=168h k=2', 'H3 W=168h k=3', 'H3 W=336h k=3']
- Checks: {'opportunity': False, 'economics': True, 'not_few_trades': True}
- Decision: **SHELVE_FAMILY**

Episode P&L is the equity change from the first held hour, so it excludes entry costs. Exchange filters are the 2026-10-02 values applied to past prices. Betas are trailing 30-day hourly estimates clipped to [0.25, 4].
