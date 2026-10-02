# 0015 — Register the Phase 2c BTC/ETH low-frequency trend persistence study

- Status: Accepted
- Date: 2026-10-02

## Context

Decision 0014 shelved the funding cross-section family. The user then chose to
accept directional risk and study trend persistence (2026-10-02). Decision 0002
allows low-turnover directional regime persistence at one-hour or slower
decisions, with the hypothesis fixed before any feature construction.

## Decision

Register `docs/PHASE2C_PREREGISTRATION.md` as the frozen Phase 2c contract.

- **Signal.** BTC and ETH USD-M perpetuals, decided daily. The trend strength is
  `z = ln(C_t/C_{t−L}) / (σ_60d · √L)`, mapped either to a binary position with a
  0.5 dead band or to a linear conviction `clip(z/2, −1, 1)`.
- **Sizing.** Positions are scaled to 25% annual volatility, at most 1x, with
  half the sleeve per asset. The grid is L ∈ {20, 60, 120} days times the two
  mappings, six configurations in all.
- **Conviction is net exposure.** Holding long and short together in the same
  asset only adds fees and funding, so conviction sets the size of one net
  position instead.
- **Controls.** No trade; risk-matched long hold (BH-VT); and a MA200 baseline.
- **Costs.** Taker 5 bps plus 2 or 5 bps slippage, with real funding.
- **Development stage.** The whole 2020-01 to 2026-10-01 dataset is declared
  contaminated. It is evaluated as one continuous walk-forward account over
  nine validation windows, with no overlapping folds, plus PBO and a 20-day
  block bootstrap.
- **Gates, under both cost regimes.**
  - At least 8% a year net on the sleeve under stress costs.
  - MDD at most 30%.
  - A Sharpe ratio no lower and an MDD no higher than BH-VT.
  - At least 5 of 9 validation windows positive.
  - At least 4 of 6 configurations positive.
  - Still positive after removing the best year and after removing the best
    episode.
  - PBO at most 0.2.
  - Positive under exchange lot and minimum-notional limits at a 500 USDT
    sleeve.
- **Verdicts.** `STOP_NO_EDGE`, `PASS_DEV`, or `INCONCLUSIVE_DEV` when the gates
  pass but the bootstrap interval includes zero.
- **Confirmation.** Only an order-free forward observation of at least 182 days
  on data after 2026-10-02 can confirm.

## Consequences

- The 500 USDT sleeve (50% of total capital) and the 8% a year threshold are
  stated assumptions and can be changed before results are seen. Research
  metrics are sleeve ratios, so only gate 8 depends on the sleeve size.
- Code lives under `v3/phase2c/`. Nothing here authorizes orders, real capital,
  leverage above 1x, or a venue change.
