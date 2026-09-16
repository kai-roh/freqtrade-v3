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
no-trade control, a primary funding cross-section carry hypothesis with a
pre-registered minimum funding-spread entry filter at 8-hour decisions, and a
simple cross-sectional reversal baseline at daily decisions; a fixed eight-asset
universe over 450 days; taker-plus-slippage costs charged on actual quantity
changes with real funding cash flows; purged walk-forward on daily portfolio net
returns with per-hypothesis CSCV PBO ≤ 0.2; the Milestone 1 gates plus a
mandatory P&L decomposition; a per-symbol implementability gate; and a venue
separation rule under which Binance results never transfer to Hyperliquid
without Hyperliquid data.

Research runs in parallel with the Phase 1 week observation and does not depend
on it. Passing Phase 2 authorizes only a separate shadow observation, never real
capital or a venue change; Hyperliquid remains a candidate requiring its own ADR.

## Consequences

- Any change to hypotheses, universe, grids, costs, or gates after results are
  seen requires a new registration document and commit.
- "No edge" and "not implementable at this capital size" are accepted outcomes.
- New code lives under `v3/phase2/`, separate from Phase 1 execution modules.
