# 0029 — Run T1 on the Demo account; retire the MA200 Demo executor

- Status: Accepted
- Date: 2026-10-20 (KST)

## Context

T1, the taker-flow ensemble, failed Phase 2g only on the deflated Sharpe (Decision
0028). No historical window is left, so it can only be checked forward. On
2026-10-20 the user asked to observe it with real Demo orders. They chose to stop the
MA200 Demo executor and give its account to T1, because two strategies on one
one-way account would net their BTC/ETH positions. The order-free MA200 observation
keeps running.

## Decision

- **Retire the MA200 Demo executor and guard.** The new audited `retire` command
  halts the executor and closes its positions reduce-only. Its cron jobs are
  removed. Without a Demo line, the MA200 observation report carries only the
  virtual accounts.
- **Run T1 on Demo** with `v3/t1live` and `scripts/run_t1_live.py`:
  - **Signal:** the T1 rule from Mainnet public daily candles. It matches the
    backtest weights on the last 29 archive decision days.
  - **Schedule:** a daily run at 09:05 KST. On Mondays it rebalances to the Sunday
    decision, closing and reducing positions before opening new ones. Orders are IOC
    limits with a 30 bps cap. On other days it only records equity and sends a
    Telegram status.
  - **Account:** cross margin at leverage 2 and gross exposure 1, so no single
    position can be liquidated on its own. Strategy equity is the 1,000 USDT start
    plus all income since the T1 start, plus unrealized P&L.
  - **Guard:** every 10 minutes. It flattens and halts on any of the following:
    - the loss stop, set at **650 USDT (−35%)**, beyond T1's historical maximum
      drawdown (21–33%) so that ordinary drawdowns do not end the observation;
    - a stale executor;
    - a position mismatch.
    Executor and guard share a file lock.
- **Demo is execution evidence, not the profit verdict.** Demo funding and order
  books differ from Mainnet, and symbols missing on Demo stay in cash. On
  2026-10-18, BTW and PUMP were missing. The T1 forward verdict uses the Mainnet
  archive under the Phase 2f/2g forward criteria: a 3-month check and a 6-month
  verdict.
- **First rebalance:** Monday 2026-10-26 09:05 KST, after a Demo execution check
  in a separate state directory.

Nothing here touches Mainnet. The client still refuses Mainnet without a
real-capital decision.
