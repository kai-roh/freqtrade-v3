# 0027 — Phase 2f result STOP_NO_EDGE; register Phase 2g single-hypothesis check

- Status: Accepted
- Date: 2026-10-20 (KST)

## Phase 2f result

No family passed the development gates, so the verdict is **`STOP_NO_EDGE`**. The
development windows were 2020-07..2023-12 for price and flow, and 2022-01..2023-12
for positioning. They covered 66 configurations with costs and funding. Results are
in `research_results/phase2f/dev-results.json`. Metrics manifest: `ed1585c1…`.

| Family (best) | Sharpe | CAGR | MDD | PBO | Gates D1 D3 D4 D5 D6 | Family Sharpe range |
|---|---|---|---|---|---|---|
| R1 regime L/S BTC/ETH (SMA100, U1 D0.5, BTC regime) | 1.32 | 78% | 41% | 0.44 | O x O O O | 0.35–1.32 |
| R2 regime cross-section (SMA100 L14 K5, top-K up) | 0.94 | 53% | 80% | 0.72 | x x x x O | 0.31–0.94 |
| P1 top-trader crowding fade (L14 K5) | 0.91 | 16% | 17% | 0.38 | O x O O O | 0.26–0.91 |
| P2 account crowding fade (L3 K5) | 1.21 | 32% | 18% | 0.82 | O x O O O | 0.61–1.21 |
| P3 taker-flow follow (L7 K3) | 1.83 | 91% | 33% | 0.73 | O x O O O | 1.47–1.83 |
| P4 OI build-up fade (L14 K5) | 0.57 | 12% | 17% | 0.03 | O O x O O | −1.47–0.57 |

The benchmarks were:

- **Price window:** BTC Sharpe 1.00 and BTC/ETH 1.19.
- **Positioning window:** BTC Sharpe 0.28.

What the user asked about, holding mostly shorts in falling markets, is answered by
R1 and R2.

- **The short side did not pay.** R1's short legs returned −4% over 2020-07..2023-12,
  which includes the 2022 bear market. R2's short legs returned −53%.
- **In every R1 cell, the short-heavy sizing (U0.5 D1) was the worst of the three.**
  The long-heavy sizing (U1 D0.5) was the best.

## Decision

Register [PHASE2G_PREREGISTRATION.md](../PHASE2G_PREREGISTRATION.md) as one
hypothesis drawn from the development results. The hypothesis, T1, is the
equal-weight ensemble of the six P3 taker-flow configurations. All six beat the best
benchmark Sharpe and BTC's drawdown, and P3's only failed gate was PBO.

T1 is evaluated once on the Phase 2f validation window against V1–V5, with a
cumulative M=188. Most of P3's development return came from long legs in 2020–2021.
That is disclosed in the registration.
