# 0020 — MA200 live risk contract: −10% stop, risk sizing, automatic protection, Demo first

- Status: Accepted (risk-level selection result appended below)
- Date: 2026-10-02

## Context

On 2026-10-02 the user decided four things for moving the fixed MA200 toward
real trading:

1. The account loss stop is −10%.
2. The risk level is left to the implementer.
3. The strategy uses perpetuals only, and leverage is acceptable.
4. Failures are handled automatically, because the user is unlikely to be able
   to intervene.

The user asked to start development and Demo verification now. No real account
exists yet.

## Decisions

### Loss stop

**Strategy equity** is 1,000 USDT plus the cumulative strategy P&L on
BTCUSDT and ETHUSDT perpetuals since the start. The P&L includes realized P&L,
unrealized P&L, commissions, and funding. When strategy equity is at or below
**900 USDT**, the system closes every position with reduce-only orders, cancels
open orders, writes a halt marker, and alerts. Trading resumes only after an
explicit decision.

The stop is measured from starting capital, not from a running peak. On a real
1,000 USDT account it equals the account equity.

### Risk level (fixed here before computing)

The 25% volatility target had historical maximum drawdowns of 13–17%, so the
stop would fire in ordinary drawdowns. The target is chosen by this rule:

- **Candidates:** 8%, 10%, 12%, 15%, 20%, 25%.
- **Measure:** MA200 constrained mode, 1,000 USDT sleeve, normal cost.
- **Choose the largest candidate** whose maximum drawdown is at most **6%**
  (60% of the stop) in both 2022-08-01..2026-10-01 and 2020-08-01..2026-10-01,
  and whose skipped-order share is at most 10%.
- If no candidate qualifies, the −10% stop and this strategy are incompatible,
  and that is reported instead.

This is risk sizing. A lower target scales positions down and leaves the signal
unchanged. It does not search for higher return.

### Leverage and margin

Exposure stays at most 1x of the sleeve per asset (|weight| ≤ 1). Margin is
**isolated 2x** to reduce collateral use. Raising exposure with leverage would
require a volatility target above the assets' own volatility, which conflicts
with the −10% stop.

### Automatic protection (gate 5 for real capital)

This answers gate 5 for real capital with the automatic option. A guard runs
every 10 minutes. It closes everything reduce-only and halts when any of these
happens:

- the loss stop is reached;
- the daily executor has not succeeded for more than 50 hours;
- positions differ from the executor's record by more than one lot;
- repeated order failures are recorded.

While halted, the executor does not trade.

### Execution

A daily job runs at 01:05 UTC.

- **Signal.** The MA200 signal is computed from Binance USD-M mainnet public
  daily closes. Its target weights must match the forward observation.
- **Orders.** IOC limit orders with a 10 bps price cap and up to three attempts
  for any unfilled remainder. Reductions are reduce-only. A flip is a reduce-only
  close followed by an open.
- **Lot rules.** Lot and minimum-notional rules use live `exchangeInfo`.
- **Idempotency.** Client order IDs are deterministic, and the job queries an ID
  before sending it, so a rerun never duplicates an order.
- **Records.** A JSONL journal plus a daily Telegram report.

### Demo first; Mainnet locked

The executor runs only on Binance Demo. Mainnet orders are refused unless an
authorization file names a real-capital decision. No such decision exists. Demo
verification covers:

- unit tests against a fake exchange;
- on Demo: initial entry, an idempotent rerun, a forced flip, a forced stop and
  halt, and a stale-heartbeat halt;
- daily Demo runs during the observation's dry run, reconciled against the
  observation.

### Observation

The forward observation has not started yet. It is amended to the chosen
volatility target, for both MA200 and the holds, so that it remains the
reconciliation baseline.
