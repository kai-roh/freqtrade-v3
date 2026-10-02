# 0014 — Shelve the funding cross-section family after the risk-neutralization diagnosis

- Status: Accepted
- Date: 2026-10-02

## Context

Decision 0013 (with its corrections) traced the two H3 episodes. Price loss came
mostly from a long-beta tilt and from a basket left with unequal legs while
entries were blocked. A review asked whether fixing those two defects would let
the carry pay. The diagnosis plan `docs/PHASE2B_RISK_DIAGNOSIS.md` was committed
before any diagnostic code ran (`22bbc77`). The code followed in `e5ab00d`.

The diagnosis used only already-seen data and is never a promotion basis. The
H3 rules, threshold, windows, universe, and costs were unchanged. Four variants
were compared, in ideal mode and in exchange-constrained mode (2026-10-02 lot
and minimum-notional filters):

- **V0:** baseline.
- **V1:** balance restoration, which shrinks the larger side and exits all if a
  side empties.
- **V2:** beta sizing from trailing 30-day betas.
- **V3:** V1 and V2 combined.

Output: `research_results/phase2b/risk-diagnosis/`.

## Result

### Stage 1: the two traced episodes (fold 0, H3 W=168h k=3, normal cost)

| Ideal mode | Net | Price | Mean abs net $ | Mean abs net β$ |
|---|---:|---:|---:|---:|
| V0 baseline (reproduces the record) | −6.678 | −6.622 | 24.9 | 52.1 |
| V1 balance | −5.976 | −5.872 | 2.1 | 25.0 |
| V2 beta | −5.471 | −5.358 | 28.1 | 26.0 |
| V3 both | −4.895 | −4.741 | 21.8 | 3.2 |

Attribution in ideal mode:

- Balance restoration is worth +0.70 USDT.
- Beta sizing is worth +1.21 USDT.
- Both together are worth +1.78 USDT, with an interaction of −0.13.

The fixes cut both exposures as intended. Still, about three quarters of the
loss remains, and the variant stays negative. In constrained mode, V3 avoided the
02-05 daily stop and finished at +9.95 USDT in a single episode. That is a
different path, not an attributable effect. It shows how strongly two episodes
depend on small sizing differences.

### Stage 2: one continuous account per grid point, 2025-07-07 to 2026-07-30

- **The risk fixes help consistently.** In ideal mode V1, V2, and V3 each beat V0
  in all 8 grid-point and cost cells. Drawdown also falls in every cell; for
  example, W=336h k=2 drops from 15.2% to 7.9%. The structural defects are real
  and material.
- **The carry does not pay.** Funding minus costs over the whole year is between
  −0.78 and +0.78 USDT in every V3 cell, about ±0.4% of the 200 USDT sleeve. Net
  results are driven by price P&L, which ranges from −16 to +12 USDT and changes
  sign across neighbouring grid points: W=336h k=2 is −15.8 while W=336h k=3 is
  +9.9 in ideal V3. Price P&L that flips sign between neighbouring grid points
  is noise, not carry.
- **Opportunities are scarce.** Entries were allowed on 4–9% of daily decisions,
  giving 2–8 episodes in the year depending on the grid point and variant.
- **Exchange limits at this capital matter.** In constrained mode, legs below
  the lot or minimum notional were skipped 1–14 times per run. The same rule can flip sign between ideal and constrained
  modes, for example W=168h k=3 V3 at −6.6 versus +11.0.

### Pre-committed verdict (constrained V3)

| Check | Result |
|---|---|
| Opportunity: at least 6 episodes on 3 of 4 grid points | **Fail.** No grid point reached 6; counts were 5, 2, 4, and 3 |
| Economics: net > 0 and funding > costs + max(0, −price), both costs, 3 of 4 points | Pass formally on 3 points. Their price P&L was positive, so the test reduced to funding > costs, with margins of 0.02–0.78 USDT a year |
| Not dependent on the best episode | Pass on those 3 points, by small margins |

Decision under the plan: **SHELVE_FAMILY**.

## Decision

1. The funding cross-section family on this eight-symbol Binance USD-M universe
   is shelved. Do not lower the threshold or shorten the windows to buy
   opportunities. With risk neutralized, the carry is about equal to costs, and
   what remains is relative-price noise.
2. Two lessons become requirements for any future multi-leg strategy in this
   repository, whatever its signal:
   - Risk reduction must be authorized separately from new entries. When a side
     shrinks, the other side is scaled down. Nothing is forced into the basket.
   - Exposure limits are set on beta-weighted and dollar notional, not on leg
     counts, and are checked at the real lot and minimum-notional sizes of the
     sleeve.
3. Phase 3 still has no candidate. Nothing here authorizes orders, real capital,
   or a venue change.

## Limits

- The data has been seen before. The betas are trailing estimates, and the
  2026-10 exchange filters are applied to past prices. Episode P&L excludes
  entry costs.
- Only H3's four grid points were tested. The Phase 2 H1 grid was not
  re-simulated with these variants, because that would mean modifying the
  frozen Phase 2 simulator. H1's validation folds carried taker costs four times
  larger than its funding, so neutralizing its price risk would not make it pay.
