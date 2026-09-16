# 0007 — Settle unsellable residual inventory and project funding conservatively

- Status: Accepted
- Date: 2026-09-15

## Context

The first automatic Demo episode ended with `0.00000715 BTC` of Spot inventory,
below the venue sell lot. The lifecycle only closed an episode when both legs were
exactly zero, and every entry path refused to start while a non-CLOSED intent
existed. The residual therefore parked the whole pipeline in `ABORTING` with no
audited way forward except manual SQL, which the project forbids.

Separately, the scanner multiplied the single latest funding settlement by the
number of settlements in the holding period. A funding spike could pass the
20 bps net gate for a 720-hour hold even though nothing supported holding that
rate for 30 days, which is the same "enter on a transient signal" failure the
rebuild exists to avoid.

## Decision

1. A closing episode whose futures are flat, whose orders are all terminal and
   applied, and whose remaining Spot cannot be sold by a bounded order is settled
   as an **owned residual**. Settlement writes `episode_residuals`, a realized
   `residual_inventory` cost entry, a resolved incident, a reconciliation run, and
   audited transitions to `CLOSED`. It never sells, never resets the baseline, and
   is refused while any bounded close remains possible. The next episode records
   the residual as inherited pre-existing inventory and never treats it as its own.
2. The scanner projects funding as the smaller of the current settlement and the
   trailing mean over a policy window (21 settlements). Missing history keeps the
   scanner observation-only. A deterministic reversal rule exits when funding stops
   paying the short leg. Current-rate extrapolation is rejected by the policy loader.
3. The Demo action risk worker reads its ceilings from the committed engineering
   config and refuses payloads that declare a different config hash.
4. The lifecycle enforces the six state-machine invariants on every reconciliation.
5. Phase 0 metrics are computed on a capital basis with an explicit per-trade
   fraction, and fold-boundary trades resolve their exits on later causal rows.

## Consequences

- `CLOSED` may now hold a settled residual on the account; the ledger records who
  owns it. Exact flat and settled-residual close are reported distinctly.
- A funding spike alone cannot produce an actionable carry target.
- Research drawdown figures are no longer comparable with the milestone-1 report,
  which assumed 100% of capital per trade; the promotion gate itself is unchanged.
- Adopting a measured quote-age SLA still requires a reviewed policy commit; the
  evidence script only proposes a value.

## Rejected alternatives

- Manual `UPDATE intents SET state='CLOSED'`: no audit trail, violates the
  "dust is not flat" invariant.
- Selling residual by rounding up to a lot: sells inventory the episode does not own.
- Allowing a new episode while the predecessor stays `ABORTING`: hides the residual
  and breaks the one-open-intent invariant that guards against duplicate exposure.
