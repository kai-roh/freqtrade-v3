# 0018 — User decision: evaluate the fixed MA200 at a 1,000 USDT sleeve (plan departure)

- Status: Accepted
- Date: 2026-10-02

## Context

Decision 0017 paused research under the pre-committed MA200 comparison. MA200
passed the four risk criteria C1–C4 against a spot hold. It failed
implementability (C5) at a 500 USDT sleeve, because the BTC perpetual lot
(0.001 BTC, about 64 USDT) was too coarse for volatility-scaled sizing with a
250 USDT per-asset cap. An information-only figure already showed 3 of 99
skipped orders at a 1,000 USDT sleeve.

On 2026-10-02 the user decided to use a 1,000 USDT sleeve.

## Decision

1. The fixed MA200 follow-up uses a **1,000 USDT sleeve**: 500 USDT per asset,
   at most 1x. This is the whole account in `configs/phase1-policy.json`
   (`capital.total = 1000`), so the account would carry directional exposure up
   to its full value.
2. This is a **departure from the plan** in `docs/PHASE2C_MA200_COMPARISON.md`.
   That plan fixed 500 USDT before any results. The 1,000 USDT figure was chosen
   after seeing that C5 failed at 500 USDT and roughly how it behaves at 1,000.
   A pass at 1,000 USDT is therefore weaker evidence than a pre-committed pass.
3. Nothing else changes. The rule, criteria C1–C5, costs, filters, comparison
   period, and controls stay as they were. The comparison is rerun once at
   1,000 USDT into `research_results/phase2c/ma200-comparison-sleeve1000/`. The
   500 USDT result and Decision 0017 stay as recorded.
4. Phase 1 sleeve fractions in `configs/phase1-policy.json` are not changed.
   Those fractions are carry 45% and basket 20%, and both families are shelved
   or paused. Any change to the account allocation is a separate decision
   before execution work.
5. A pass makes MA200 eligible for an order-free forward observation only. It
   authorizes no orders, no real capital, and no leverage above 1x. Whether to
   register that observation is a further user decision.
