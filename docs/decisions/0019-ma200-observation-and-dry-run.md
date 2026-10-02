# 0019 — Register the order-free MA200 forward observation with a 7-day operational dry run

- Status: Accepted
- Date: 2026-10-02

## Context

After Decision 0018, the MA200 follow-up was `OBSERVE_ELIGIBLE` at a 1,000 USDT
sleeve. On 2026-10-02 the user made four choices:

- Register the observation.
- Run it for a few days rather than six months, then move to real trading.
- Approve installing the daily job on the server.
- Receive a daily Telegram report.

The user also asked about two further things. One was raising the annual return
before starting. The other was judging the strategy on weekly and monthly P&L
tables instead of annual figures.

## Decision

1. **Register** `docs/MA200_FORWARD_OBSERVATION.md`.
   - The MA200 rule is fixed, with a 1,000 USDT sleeve.
   - Exchange-faithful order constraints apply.
   - The controls are a spot hold and a perpetual hold.
   - The observation starts with the 2026-10-03 00:00 UTC decision.
2. **The first 7 days are an operational dry run, not a performance test.** A
   200-day trend rule may not change direction at all in a week. The pass
   conditions are therefore operational only:
   - a report delivered every day;
   - fresh data and funding;
   - no skipped virtual orders;
   - deterministic recomputation;
   - no exceptions.
3. **Monitoring is daily, with weekly and monthly tables.** Telegram carries a
   daily report, adds a weekly P&L table on Mondays, and adds a monthly table on
   the 1st. These tables are for monitoring. The rule is not changed from one
   week's or month's result. An improvement is considered at most monthly, needs
   a new registration, and is judged only on data after the change.
4. **Return is not raised by tuning on seen data.** Choosing the MA length,
   bands, or thresholds that would have earned more raises the backtest without
   raising expected future return. That is the failure mode PBO measured in
   Phase 2c. There are two honest levers, and either needs its own decision:
   - **Risk level.** The 25% volatility target can be raised. Return and
     drawdown would rise together, still within 1x.
   - **Cost.** Holding the long side in spot instead of perpetuals avoids the
     funding the perpetual long pays. Over 2022–2026 that funding cost about
     95 USDT on 1,000 USDT, roughly 2% a year. This needs a spot wallet and a
     separate order path.
5. **Real trading stays unauthorized.** It needs everything in §5 of the
   observation document: a real-capital ADR with an account loss limit, the
   gate 5 decision for real capital, a Demo-verified single-asset execution
   path, the account setup, and daily reconciliation.

## Consequences

- A new daily cron entry runs at 11:10 KST (`deploy/freqtrade-v3.cron`), in the
  image `freqtrade-v3-observe:current`. It uses public data only, with no
  account access and no orders.
- The observation remains the shadow benchmark after the dry run, including
  after any real trading starts.
