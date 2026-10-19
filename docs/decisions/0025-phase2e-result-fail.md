# 0025 — Phase 2e result: E1 momentum ensemble FAIL on the holdout

- Status: Accepted
- Date: 2026-10-19 (KST)

## Result

E1 was tested once on 2025-01-01..2026-09-29, with net costs as registered in
[PHASE2E_PREREGISTRATION.md](../PHASE2E_PREREGISTRATION.md).

| | Total | CAGR | Sharpe | MDD |
|---|---|---|---|---|
| **E1** | **−3.7%** | −2.2% | 0.19 | 40% |
| E1, cost ×2 | −8.2% | −4.8% | 0.13 | 42% |
| BTC hold | −19.6% | −11.8% | −0.08 | 53% |
| BTC/ETH hold | −16.1% | −9.6% | 0.08 | 60% |
| Top-10 equal weight | −30.8% | −19.0% | −0.03 | 61% |

| Gate | Result |
|---|---|
| H1: return > 0 | fail |
| H2: Sharpe ≥ 0.5 | fail |
| H3: Sharpe ≥ BTC | pass |
| H4: MDD < BTC | pass |

The verdict is **`FAIL`**.

By year, E1 returned −10.6% in 2025 and +7.7% in 2026 through September. Over the
21 months it turned over 31 times its capital and paid 4.7% in costs.

E1 lost far less than holding through a falling market, which matches its
development record of a lower drawdown and a higher CAGR than BTC. It still did not
make money. The registered gates require a positive, risk-adjusted return, so the
hypothesis is rejected. The 2025-01..2026-09 holdout is now used and cannot confirm
any later hypothesis.

## Consequences

- Across Phases 2, 2b, 2c, 2d, and 2e, no daily-frequency strategy built from public
  Binance prices and funding has shown a reliable positive return after costs.
- Fresh evidence can only come from data after 2026-09-30, or from information not
  tested yet.
- The MA200 observation and the Demo executor continue unchanged.
