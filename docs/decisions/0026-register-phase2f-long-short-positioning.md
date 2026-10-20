# 0026 — Register Phase 2f: regime long/short and positioning-data strategies

- Status: Accepted
- Date: 2026-10-20 (KST)

## Context

After Phase 2d (`STOP_NO_EDGE`) and Phase 2e (`FAIL`), the user asked for two things
on 2026-10-20. The first is strategies that switch between long and short with the
trend and hold mostly shorts in falling markets. The second is a search over
information not used yet.

The MA200 rule under observation is already long/short, and Phase 2d F4/F5 tested
symmetric perpetual long/short rules. What has not been tested:

- asymmetric sizing between regimes;
- shorting the weakest alts in down regimes;
- positioning and flow data: open interest, top-trader and all-account long/short
  ratios, and taker buy share.

No clean historical holdout remains. 2024 was in the Phase 2d development window,
and 2025-01..2026-09 has been seen through the Phase 2d benchmarks and Phase 2e.

## Decision

Register [PHASE2F_PREREGISTRATION.md](../PHASE2F_PREREGISTRATION.md) before
computing any result. The registration fixes the following:

- **Trials:** 66 configurations in six families: R1 regime long/short on BTC/ETH,
  R2 regime-conditional cross-section, and P1–P4 market-neutral positioning
  signals. Signal directions are fixed in advance.
- **Development:** 2020-07..2023-12. The positioning families use 2022-01..2023-12.
- **Validation:** 2024-01..2026-09, with its contamination disclosed. Validation must
  be positive in 2024 (up) and in 2025-01..2026-09 (down) separately, so a strategy
  cannot pass by being short in a period known to fall.
- **Deflated Sharpe:** at the cumulative M=187 (Phase 2d 120, Phase 2e 1, and these
  66), over development plus validation.
- **Outcomes:** `CANDIDATE` makes a strategy eligible for an order-free forward
  observation on post-registration data (3-month check, 6-month verdict). Server
  changes still need user approval. `STOP_NO_EDGE` otherwise.

The MA200 observation and the Demo executor keep running unchanged meanwhile.
