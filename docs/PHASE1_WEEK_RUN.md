# Phase 1 Demo Week Run

기준일: 2026-09-14 KST

Status: planned, **not running**. The bounded streaming collector and Telegram
connection test have passed; neither authorizes or starts the week trading run.

## Scope

Phase 1 Demo week run is an operational observation period for the Binance Demo
carry execution stack. It is not a profitability test, a Phase 3 promotion gate,
or evidence that live fill quality has been measured.

Allowed evidence:

- Demo start, stop, trade, and error notifications.
- State-machine correctness.
- Intent, command, dispatch, fill inbox, and reconciliation persistence.
- Restart recovery before new command admission.
- Quote collection timestamps and transport health.

Excluded evidence:

- Real fill rate.
- Queue priority.
- Adverse selection.
- Live hedge latency.
- Actual slippage.
- Profitability or expected return.

## Telegram Notifications

Telegram is operational telemetry only. A notification failure must return a
failed delivery result and must not retry orders, resubmit commands, unblock a
blocked inbox receipt, or change risk approval.

The Phase 1 notification helper reads only:

- `TELEGRAM_TOKEN`
- `TELEGRAM_CHAT_ID`

Messages must mark Demo mode in the first line:

```text
[DEMO][PHASE1][TRADE] two-leg episode accepted
```

Do not include API keys, secrets, tokens, signatures, balances, raw exchange
payloads, or account identifiers in notification details. Sensitive detail keys
are redacted before formatting, but callers should still pass compact operational
summaries instead of raw payloads.

## Stop Conditions

Stop the Demo runner and preserve evidence when any of these occur:

- A fill inbox receipt becomes `BLOCKED`.
- A dispatch remains unresolved after restart recovery.
- A risk decision is stale, malformed, or disagrees with the current policy or
  fee snapshot hash.
- Either leg is partially filled and bounded cancel or hedge handling cannot
  complete.
- A timestamp required by the configured SLA path becomes unavailable. Spot
  bookTicker has no exchange timestamp by design: retain NULL exchange age and
  measure receive-gap separately. A future engineering-only trial policy must
  explicitly authorize that freshness basis; do not invent a Spot SLA result.
- Telegram delivery repeatedly fails while the runner is otherwise healthy.

The last condition is an observability failure, not a trading failure. It should
pause unattended operation because the user expects Demo trade history through
Telegram during this run.

## Success Criteria

The week run can support Phase 1E completion only if the final report includes:

- At least 50 Demo episodes counted from accepted dispatch/fill evidence, not
  fixture replay.
- At least 3 restart recovery events with no duplicate command admission.
- Zero unresolved dispatches.
- Zero blocked fill inbox receipts at close.
- Full state transition, order command, order, fill, transfer, incident, quote,
  and cost evidence for each episode.
- Explicit separation of Demo-observed fees from injected Mainnet fee policy.

Passing this run means the Demo execution pipeline is operable enough for the
next review. It does not mean the strategy is profitable or ready for Mainnet
capital.
