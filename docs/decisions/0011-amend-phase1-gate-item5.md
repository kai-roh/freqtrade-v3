# 0011 — Amend Phase 1 gate item 5 to fail-closed with alerting and bounded human recovery

- Status: Accepted
- Date: 2026-10-02
- Amends: `PHASE1_IMPLEMENTATION_PLAN.md` §10 item 5; follows Decision 0010

## Context

Gate item 5 read "no unhedged exposure left open after a failure". Decision 0010
found it unmet: two runner halts left Demo exposure open for about 186 h
(2026-09-17 to 09-25) and about 12 h (2026-09-29 to 09-30). The runner is
fail-closed by design. On a fatal error it stops new orders, does not unwind,
and waits for a person. As written, item 5 can only be met by automatic
unwinding, which the runner deliberately does not do.

The user chose to amend the item rather than build automatic close-only
recovery now (2026-10-02). No strategy is a Phase 3 candidate (Decision 0009),
so there is no near-term real-capital use that would need automatic recovery.

## Decision

Item 5 is replaced, **for Demo only**, by four conditions:

| Condition | Evidence required | Status at 2026-10-02 |
|---|---|---|
| (a) Every fatal error halts new orders without a duplicate or replacement order | Run events, ledger | Met. Three halts; 0 rejected transitions, 0 duplicate orders |
| (b) Every halt produces a delivered Telegram notification | `telegram_delivered` on each error event | Met. Every error event in the three halts was delivered |
| (c) A documented recovery procedure closes the open episode without a new entry | `PHASE1_WEEK_RUN.md` "Recovery after a fatal halt" | Met. Written today; exercised on 2026-09-25 and 2026-09-30, both exit 0 |
| (d) The open episode is closed within 24 h of the notification while a runner is active | Halt and close timestamps | Rule from today on. Recorded breach: 2026-09-17, about 186 h. The 2026-09-29 halt closed in about 12 h |

24 hours is the bound because notifications reach a phone and one daily check
always covers it. A Demo episode carries at most about 300 USDT of notional.

## Verdict

With item 5 amended, all twelve Phase 1 gate items are met. Phase 1 is
**complete for Demo**, with one recorded exception. The 2026-09-17 halt would
breach condition (d); it predates the rule. That halt stayed open past the end
of the run window because nobody was assigned to respond. Its two root causes
are fixed in `1a124d1`.

## Constraints

- This amendment does not carry over to real capital. Before any Phase 3 order,
  item 5 is decided again. Either automatic close-only recovery is built and
  verified with forced faults, or a much tighter response bound is set with an
  on-call owner. Phase 1 completion still does not authorize Phase 3
  (Decision 0006).
- If a future Demo run breaches condition (d), the breach is recorded and the
  amendment is reviewed. It is not silently tolerated.
- Automatic close-only recovery remains a valid later option and needs no change
  to this decision to be added.
