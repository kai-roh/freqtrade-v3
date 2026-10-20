# 0021 — User decision: MA200 loss stop at −20% (800 USDT), Demo included

- Status: Accepted
- Date: 2026-10-03 (KST)
- Amends: Decision 0020 (loss stop level)

## Context

Decision 0020 found the user's −10% stop incompatible with the fixed MA200 at a
1,000 USDT sleeve. It showed the risk levels side by side, as the past worst
drop from an unlucky start:

- 25% target: 17.8% in 2022–26 and 24.8% in 2020–26.
- 20% target: 13.8% and 20.9%.
- Targets low enough for the −10% stop could not trade BTC at this capital.

After seeing that table, the user chose a **−20% stop** and asked for it to
apply to the Demo run as well.

## Decision

1. **Loss stop: strategy equity 800 USDT.** That is −20% from the 1,000 USDT
   starting capital. The guard closes everything reduce-only at or below this
   level and halts, as in Decision 0020. The Demo state is changed with the
   audited `set-stop` command, and the journal records the change.
2. **The risk level stays at the 25% volatility target.** The user delegated the
   risk level. There are three reasons:
   - The order-free observation started on 2026-10-03 at 25%. Changing it would
     discard that forward evidence and the Demo reconciliation.
   - A 20% target would not make the stop safe either: its past worst drop of
     20.9% is about the same as the stop.
   - At 25%, orders stay executable, with 2–3% skipped.
3. **The residual risk is accepted knowingly.** At 25%, an unlucky start in
   2020–26 would have lost 24.8% at worst, so the −20% stop would have fired in
   the 2021–22 stretch for someone who started near the May 2021 peak. Starts
   in 2022–26 stayed within 17.8%. Decision 0020 asked for a 60% margin, a worst
   drop of at most 12%. That margin is not met, and the user chose this level
   after seeing the numbers.
4. Everything else in Decision 0020 is unchanged:
   - Demo first and Mainnet locked.
   - Automatic protection.
   - Exposure at most 1x on isolated 2x margin.
   - Real trading still needs a real-capital decision, the account, and an API
     key.
