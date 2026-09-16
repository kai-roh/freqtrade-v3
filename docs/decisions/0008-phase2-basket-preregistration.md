# 0008 — Register the Phase 2 perp-only basket hypotheses before any code

- Status: Accepted
- Date: 2026-09-16

## Context

Phase 1 proved the two-leg Demo execution stack (three forced-restart recoveries,
automatic residual settlement, zero rejected transitions) but the single-asset
carry gate rarely opens economically. Decision 0002 restricts the next research
candidate to lower-turnover hypotheses: regime persistence or market-neutral
relative value at one-hour or slower decisions, with the hypothesis fixed before
feature construction.

## Decision

Register `docs/PHASE2_PREREGISTRATION.md` as the frozen Phase 2 contract: a
no-trade control plus two deterministic market-neutral perp-only basket
families (funding cross-section carry at 8-hour decisions, residual reversal at
daily decisions), a fixed eight-asset universe, explicit taker-plus-slippage
costs with real funding cash flows, purged walk-forward with PBO ≤ 0.2, the
Milestone 1 promotion gates, and an implementability gate that already shows a
1,000 USDT account cannot run a four-leg basket on Binance USD-M.

Research runs in parallel with the Phase 1 week observation and does not depend
on it. Passing Phase 2 authorizes only a separate shadow observation, never real
capital or a venue change; Hyperliquid remains a candidate requiring its own ADR.

## Consequences

- Any change to hypotheses, universe, grids, costs, or gates after results are
  seen requires a new registration document and commit.
- "No edge" and "not implementable at this capital size" are accepted outcomes.
- New code lives under `v3/phase2/`, separate from Phase 1 execution modules.
