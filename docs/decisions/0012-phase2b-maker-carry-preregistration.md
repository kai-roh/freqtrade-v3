# 0012 — Register the Phase 2b low-turnover maker funding carry before any code

- Status: Accepted
- Date: 2026-10-02

## Context

Decision 0009 rejected the Phase 2 basket hypotheses. Funding carry (H1) earned
positive funding, but taker costs from frequent replacement and rebalancing were
about four times larger. Decision 0009 named the only admissible follow-up: a new
registration that changes execution, decision cadence, or turnover. The user
chose that path on 2026-10-02.

## Decision

Register `docs/PHASE2B_PREREGISTRATION.md` as the frozen Phase 2b contract.

- **H3:** the H1 funding cross-section signal with daily decisions, a fixed
  1.0 bp spread filter, a five-day minimum hold, a 14-day cap, a 50% rebalance
  band, and post-only maker execution. The grid is W ∈ {168h, 336h} × k ∈ {2, 3}.
- **Fill model:** a maker fill needs a trade-through of 2 bps (normal) or 5 bps
  (stress) within the next hourly candle. Unfilled legs fall back to taker one
  hour later. Risk-reducing exits are always taker with stress slippage.
- **H3T:** the same rules with taker execution, as a diagnostic control only.
- **Two-stage validation.** Stage A reuses the Phase 2 folds. It is declared
  contaminated, because the redesign was made after seeing those results.
  Stage B is the decisive test: a single 62-day evaluation from 2026-07-31 to
  2026-10-01, which no Phase 2 run used. It requires positive net return, MDD at
  most 10%, funding above fees plus slippage, and at least two completed cycles.
- H3 must pass both stages under both cost regimes. Passing earns only a Demo or
  shadow observation of at least 90 days and 12 completed cycles.

## Consequences

- Data is extended from 2026-09-16 to 2026-10-01 with a new manifest. The
  existing panel must match its recorded hashes.
- Simulator changes live under `v3/phase2/`. Regression tests must show that the
  Phase 2 H1 and H2 results do not change.
- Stage B can be used once. Any rerun after seeing Stage B needs a new
  registration and fresh untouched data.
- Nothing here authorizes orders, real capital, or a venue change.

## Correction (2026-10-02)

Stage B was described as data "no Phase 2 run used". In fact 2026-07-31 to 09-16
was inside the Phase 2 PBO matrix. Only 2026-09-17 to 10-01 was fully unused.
See Decision 0013, "Corrections".
