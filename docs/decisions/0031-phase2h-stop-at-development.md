# 0031 — Phase 2h stopped at development: the intraday edge is smaller than taker costs

- Status: Accepted
- Date: 2026-10-20 (KST)

## What was run

All runs used development data only, 2022-04..2022-12, inside the training period.
The models were walk-forward with monthly refits, so each month's predictions come
from earlier data. The registered out-of-sample window, 2023-01..2026-09, was **not
computed**. Data manifest: `3808c769…` (390 files). Scans are in
`research_results/phase2h/dev-scan-2022*.csv`.

## Findings

- **The signal is real before costs.** The 1-hour cross-sectional IC was 0.055
  (t = 13.5 in 2022-H2). The 4-hour IC was 0.031, or 0.042 with the positioning
  features. Before costs, the books reached a Sharpe of 1.5–2.4, and 70–78% of weeks
  were positive in 2022-H2.
- **The edge is too small per trade.** Gross P&L per unit of turnover was 1–7 bps at
  the registered thresholds. The taker fee alone is 5 bps a side. Each 4-hour
  decision turned over about half the book.
- **Costs dominate.** At the registered costs (5 bps fee plus 5/10 bps slippage),
  every one of the 24 turnover-control variants lost money net.
- **Measured costs do not change this.** Mainnet half-spreads for small orders on the
  current top 20 were 0.01–1.5 bps for most symbols, 4–5 bps for two. The scan was
  repeated with 2/4 bps of slippage over 64 variants (h ∈ {1, 2, 4, 8}). The best
  had a net Sharpe of 0.26, and no variant had more than 45% positive weeks.
- **High-conviction trading is too rare.** Trading only at |z| ≥ 2 raised the edge
  to 11–50 bps per unit of turnover. But the book was invested at about 1–3% gross,
  so the net return over 9 months was 2–4%, with fewer than half of weeks positive.
- **Smoothing removes the signal.** An EMA over the predictions halved turnover, but
  the pre-cost edge fell to about zero. The signal lives for hours.

## Decision

Stop Phase 2h before the out-of-sample run. No configuration came close to the
consistency gates on development data. The cost scans were run after the
registration and are recorded here as development work; they are not a new
hypothesis. The 2023-01..2026-09 window stays unspent for intraday hypotheses.

## What it means

At retail taker fees, on Binance perpetuals, this kind of consistent small edge is
consumed by execution cost. The remaining routes all change the execution economics:

- maker (limit) execution, at a 2 bps fee with no spread crossing, which brings fill
  uncertainty and adverse selection;
- lower fee tiers.

Neither can be verified on Demo order books. Both need Mainnet trade data, such as
aggTrades, to simulate queue fills conservatively.
