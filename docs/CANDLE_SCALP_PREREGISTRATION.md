# Candle scalping — fixed retrospective research registration

Registered 2026-10-18 BEFORE implementing/scoring this candidate. Research only.
Existing uncommitted divergence work, its evidence, and MA200 runtime are preserved.
This mechanically interprets the supplied discretionary account; it cannot
reproduce unavailable news judgments, social popularity or chart-reading skill.

## Scope and hypotheses

BTCUSDT/ETHUSDT USD-M perpetuals only; long only. Reuse the checksum-verified
minute archive in evidence/divergence/data-manifest.json: September 2025 warmup,
2025-10-01 00:00 UTC inclusive to 2026-10-01 00:00 UTC exclusive evaluation.
Thirty-minute candles generate signals; one-minute candles ONLY simulate order
execution/protection. One-hour and four-hour completed candles filter trend.
Daily/weekly regimes are descriptive context, not fitted entry filters. No 1m
entry signal. No news/popularity filter without timestamped historical inputs.

Three independent strategies, each with single-entry and bounded-averaging variants:

- PULLBACK: hourly EMA20>EMA50 AND completed 4h EMA20>EMA50; two consecutive
  bearish 30m bodies each >=0.5 Wilder ATR14, RSI14<=45, confirmation volume
  >=previous20-bar mean. Minimum50 completed4h candles for trend warmup.
- RANGE: previous48 30m high/low channel width1–6% of midpoint; close in lower
  20% of channel; RSI14<=40; absolute completed1h EMA20−EMA50<=0.5 hourly ATR14;
  confirmation volume>=previous20-bar mean. No upward-trend requirement.
- BREAKOUT: same upward filter as PULLBACK; close exceeds preceding20-bar high
  by0.1 ATR14, bullish body>=0.5 ATR14, volume>=1.5 previous20-bar mean. A later
  completed30m close below the original breakout level invalidates the campaign:
  cancel orders and exit at the following minute open, before any addition.

RSI14/ATR14 Wilder seeded by simple means. No future pivot confirmations or
unfinished higher-timeframe bars. All signals become available at candle CLOSE;
orders first eligible at the following minute OPEN. No parameter search or winner
selection: all3 strategies ×2 sizing variants ×2 execution regimes are reported.

## Passive execution and bounded additions

1. New campaign: post-only-style buy limit at signal close*(1−0.0002), good for
   five one-minute bars. Proxy reject if limit>=placement minute open (would
   cross the observed price); do not assume it rests or fills. No automatic
   chase/requote. If later open gaps below a resting limit, fill conservatively
   at limit when the strict trade-through condition is met, never at a better price.
2. A limit fills ONLY after candle low trades BELOW buy limit by2bps normal,
   5bps stress. Take-profit sell requires high ABOVE target by the same amount.
   Mere touch never fills. These conservative proxies do NOT reconstruct queue
   priority or guarantee actual fills; OHLC cannot establish post-only acceptance.
3. Initial gross notional budget200 USDT in BOTH variants. Single has no adds.
   Averaging has at most two additional fills, budgets150+150 (total max500),
   with no increase in leverage. A subsequent completed bearish30m candle can
   request the next add only if close is below first fill by0.5/1.0 INITIAL ATR,
   respectively, and below current VWAP. The same close−2bps limit and expiry
   apply. No add at/below stop. At most one pending entry/add order; no retry on
   the same closed candle. New campaign never starts while another is open.
4. Original stop=initial order limit−1.5 INITIAL signal ATR, fixed; never moved
   downward after averaging. Profit target=current cost VWAP*(1+0.003), reset
   only AFTER each fill, active from the NEXT minute after any fill. Additions
   canceled on exit. Any stop touch exits before add or target; ambiguous bars
   choose stop first; a gap below stop uses worse open. Entry-minute stop applies,
   entry/add-minute profit target is not assumed filled. Target gap gets no
   windfall. If old target and pending add could both fill within one minute,
   assume add first and no target that minute (adverse sequence).
5. Initial and additional quantities are floored to static modeling steps
   BTC.001/ETH.001; opening minimum notionals BTC100/ETH20 USDT. No rounding up.
   These are current-style assumptions, not reconstructed historical filters.
6. Total filled cost notional<=500 USDT per sleeve AND<=available marked equity
   (1x exposure cap); shrink/refuse adds if breached. Worst stop loss including
   entry fees, estimated taker stop fee/slippage and funding already paid must
   fit a5 USDT campaign budget BEFORE EVERY fill. Use all actual paid entry fees
   and current VWAP in the check. If even one lot cannot fit, skip. Gaps may
   exceed budgets; record actual worst campaign loss. Stop is not liquidation.

## Protection and costs

Two independent500 USDT sleeves per portfolio (1,000 total), no cross-capital
reuse/compounding above fixed budgets. Exposure stops at1x; liquidation and
leverage escalation are NOT simulated. This tests the entry/averaging thesis
without silently inheriting unbounded leverage from the source.

- Maker entry/add/profit-exit fee2bps. Safety exits (stop, timeout, breakout
  invalidation, risk halt, forced final close) are taker5bps plus adverse slippage
  2bps normal/5bps stress. Passive limits have no invented favorable slippage.
- Max holding4h from FIRST fill, not reset by adds; exit next minute open when
  duration elapsed, capped at current target for upside gaps.
- Sleeve equity<=450USDT: cancel, market exit, permanently halt that sleeve.
- Sleeve equity falls10USDT from the prior UTC day's closing equity (initial500
  on first day): cancel, market exit, pause until next UTC day. Measure marked
  equity, not closed P&L only. Both protections evaluate minute open before
  fills and minute close after activity; downside gaps can overshoot limits.
- Funding at actual settlement on positions already held into settlement,
  before open-time exit/entry; prior completed hourly mark closes value payment.
- Force-close all survivors at final evaluation candle close with taker costs.
  All fills, not just winning closures, are in the ledger. Pending unfilled
  orders expire/cancel; failed stop-limit assumptions cannot hide losses.

## Measures, comparisons and decisions

Report all12 cells: net/price P&L, fees, slippage, funding, campaign count, entry
and add fills, win rate, PF, minute-close MDD, max exposure, worst campaign,
max holding, passive rejection/unfilled/rounding/risk refusal counts, risk halts,
monthly and six fixed two-month slices, per-asset P&L, no-trade baseline0.
Same initial200 budget isolates the decision to add; the averaging variant uses
more capital and its raw P&L must NOT be presented as equal-risk superiority.
Report average exposure and worst loss alongside return.

Daily marked-P&L circular7-day block bootstrap2,000 samples seed42; 95% mean-daily
interval is descriptive. A matched seven-day BLOCK bootstrap of averaging minus
single daily P&L is diagnostic, NOT a claim of prospective causal improvement.
Worst10 BTC daily-return dates (computed from raw evaluation prices, ties sorted
by date) are a disclosed ex-post stress diagnostic, not an independent holdout;
report campaign P&L/marked daily loss, add fills and exposure on those dates.

Research gates per strategy/sizing: >=100 closed campaigns in BOTH execution
regimes; both net>0 and PF>=1.15; both minute-close MDD<=10%; >=4/6 positive
slices in BOTH; <=80% concentration of positive campaign profit in one asset;
normal bootstrap lower bound>0. Under100: INSUFFICIENT_TRADES; otherwise any
failure: STOP_NO_EDGE. Pass: RESEARCH_ONLY_PASS; no deployment authorization.
No tuning on these outputs. All reused periods are development data, already
examined for prior strategies; new future observations are required to confirm.

## Verification before conclusions

Synthetic causal-prefix and timeframe-close alignment tests, strict passive
trade-through/expiry/rejection, stop/target ambiguity and add-bar sequence,
no leverage/quantity/risk overflow, unchanged stop and bounded two adds, breakout
failure before additions,4h timeout, funding chronology, daily/account halt,
forced final loss realization and ledger/marked-equity reconciliation. Reverify
frozen hashes and registration checksum; run targeted/full available tests,
Ruff and compile checks. Any skipped infrastructure tests are disclosed.
