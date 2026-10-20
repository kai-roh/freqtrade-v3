# 0032 — Register Phase 2i: the intraday signal with maker execution

- Status: Accepted
- Date: 2026-10-20 (KST)

## Context

Phase 2h found a real intraday cross-sectional signal before costs. Its edge per
unit of turnover was 1–7 bps, below the 5 bps taker fee (Decision 0031). On
2026-10-20 the user asked to test maker (limit-order) execution, which pays 2 bps
and does not cross the spread.

## Decision

Register [PHASE2I_PREREGISTRATION.md](../PHASE2I_PREREGISTRATION.md) before
computing any result. The registration fixes the following:

- **Signal:** the Phase 2h signal, model, and data.
- **Fill rule:** conservative trade-through. A limit at the hour's open fills only if
  price trades at least 1 bp through it within W minutes (15 or 60). A touch is not a
  fill, and an unfilled order leaves the old position.
- **Costs:** maker 2 bps. Stops and loss-limit exits are taker orders at 5 bps plus
  measured slippage of 2 or 4 bps.
- **Trials:** 16 configurations.
- **Development check:** 2022-04..2022-12. The out-of-sample run goes ahead only if a
  configuration reaches a net Sharpe of at least 1.5 with at least 55% positive weeks.
- **Out-of-sample:** 2023-01..2026-09, computed once, under the Phase 2h consistency
  gates G1–G8 at M=300.

Demo order books cannot validate maker fills, so a `CANDIDATE` is observed forward
on Mainnet public data with the same fill rule.
