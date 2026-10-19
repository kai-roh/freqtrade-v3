# 0024 — Phase 2d result STOP_NO_EDGE; register Phase 2e single-hypothesis confirmation

- Status: Accepted
- Date: 2026-10-19 (KST)

## Phase 2d result

The development window was 2018–2024, or 2020-07–2024 for perpetuals. It covered
120 configurations, with net costs and funding. No family passed the development
gates, so the verdict is **`STOP_NO_EDGE`**. Results are in
`research_results/phase2d/dev-results.json`.

| Family (best) | Sharpe | CAGR | MDD | PBO | DSR | Gates D1–D6 |
|---|---|---|---|---|---|---|
| F1 XS momentum spot (N10 L7 K3 BTC filter) | 1.11 | 72% | 76% | 0.47 | 0.55 | O x x O O O |
| F2 TS trend spot (N10 SMA50 inv-vol) | 0.94 | 42% | 55% | 0.38 | 0.37 | O x x O O O |
| F3 dual momentum (N10 L14 K5 SMA50) | 0.96 | 54% | 77% | 0.18 | 0.39 | O x O O O O |
| F4 XS momentum perp L/S (N30 L7 K5) | 1.02 | 37% | 40% | 0.71 | 0.45 | x x x x O O |
| F5 TS trend perp L/S (N10 SMA20) | 0.63 | 22% | 70% | 0.52 | 0.18 | x x x x O O |
| F6 short-term reversal (N10 L7 K5) | 0.31 | −12% | 93% | 0.01 | 0.02 | x x O x x O |

The benchmarks over 2018–2024 were:

- BTC: Sharpe 0.75, CAGR 31%, MDD 81%.
- BTC/ETH: Sharpe 0.77.
- Top-10 equal weight: Sharpe 0.47.

Over the perpetual window, BTC/ETH had a Sharpe of 1.21.

No best configuration had a Deflated Sharpe near 0.95 after 120 trials. Two
corrections were made before the holdout and changed no rule:

- The BTC-hold benchmark never bought in the perpetual window, because its single
  decision was on the anchor date. It is now rebalanced every 30 days, which holds
  100% BTC.
- The panel loader now keeps the timezone and float types when it reads the panels.

The registered holdout step evaluated the benchmarks only, since there were no
survivors. Over 2025-01 to 2026-09, BTC returned −19.6% with an MDD of 53%.

## Decision

Register [PHASE2E_PREREGISTRATION.md](../PHASE2E_PREREGISTRATION.md) as one
hypothesis drawn from the development results. The hypothesis, E1, is the
equal-weight ensemble of the ten F1 configurations with N=10 and the BTC filter.
Those ten configurations all beat BTC on the development Sharpe, with a median of
0.95. E1 is tested once on the untouched holdout against gates H1–H4.

The holdout is 21 months long, so a `PASS` means "not contradicted", not
"confirmed".
