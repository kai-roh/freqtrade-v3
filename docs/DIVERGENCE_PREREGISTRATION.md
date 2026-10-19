# RSI divergence scalp — retrospective research registration

Registered 2026-10-18 before downloading/scoring the minute data. Research only;
no server deployment, exchange order, MA200 change, or real-capital authorization.
This is a mechanical interpretation of the supplied discretionary article, not
an exact reproduction (the attached image URLs have no usable full URLs/images).

## Frozen hypotheses and scope

- BTCUSDT and ETHUSDT USD-M perpetuals; long only in an established rising trend.
- Two predeclared variants: 1-minute and 5-minute signals. Report both; no winner
  selected or parameter search. 5-minute bars aggregate the same minute source.
- Evaluation: 2025-10-01 00:00 UTC inclusive to 2026-10-01 00:00 UTC exclusive.
  September 2025 is indicator warmup only, never included in evaluation P&L.
- Official Binance monthly 1m kline ZIPs and published SHA256 checksums. Frozen
  local funding/mark data from Phase 2c; hash and check coverage before use.
- All this is retrospective development data. Earlier hourly research examined
  these assets/periods. Six fixed two-month slices describe stability; they are
  NOT an untouched holdout or parameter-selection walk-forward test.

## Mechanical rules (locked before scoring)

1. Trend: latest completed hourly EMA50 > EMA200 and EMA50 > its value three
   completed hours earlier. Minimum 200 completed hours. Do not use an unfinished
   hourly candle. RSI14 and ATR14 use Wilder smoothing.
2. Low pivot: strictly lower than the two preceding and two following lows.
   It is known only after those two following candles CLOSE. Compare successive
   low pivots 5–60 signal bars apart: price lower by >=0.05%, RSI higher by >=3.
3. Confirmation candle volume >=1.2 times the mean of the PREVIOUS 20 volumes.
4. Hidden bearish veto: latest two confirmed high pivots, 5–60 bars apart, lower
   price high by >=0.05%, higher RSI by >=3, with second pivot <=30 bars old.
   This blocks a long; it is not a short entry or additional buy.
5. At the next candle OPEN, buy only if stop is below entry and target above.
   Stop = second low pivot minus 0.25 confirmation ATR14. Target = highest high
   in 20 bars preceding the second low pivot, excluding that pivot. Require gross
   target distance >= stop distance AND >=0.20% of slipped entry price.
6. One position per asset; no averaging down, no pyramiding. One 1,000 USDT
   portfolio split into two 500 USDT sleeves; fixed max notional 500 each and
   fixed risk budget 2.5 USDT each. No compounding or leverage amplification.
   Conservative current-style quantity steps BTC .001, ETH .001; minimum opening
   notionals BTC100/ETH20 USDT. These are modeling assumptions, NOT historical
   instrument-filter reconstruction. Record rounding skips.
7. Entry/exit taker fee5bps EACH SIDE; adverse slippage2bps each side normal,
   5bps each side stress (round-trip14/20bps). A touched target exits as taker,
   not an assumed maker fill. Stop first when both levels touch in a candle;
   a gap below stop exits at the worse open. Gap above target gets no windfall.
   Entry candle can stop out. Exit after 10 completed holding candles at next
   open; force close at evaluation end, charged costs. No same-bar re-entry.
8. Funding on positions held into a settlement uses prior completed mark price.
   Apply before exit at that settlement open; do not charge a new position at
   the same settlement. Positive funding is a debit to longs.

## Evaluation and decision

Report all four timeframe/cost cells: closed trades, win rate, gross price P&L,
fees, adverse execution cost, funding, net P&L, profit factor, per-symbol,
monthly and six two-month P&L slices, mark-to-market maximum drawdown, skipped
entries and signal counts. Capital base is1,000 USDT; no-trade baseline is0.
Block bootstrap daily portfolio P&L in 7-day blocks, 2,000 samples, fixed seed42,
95% interval for mean daily P&L (diagnostic, does not correct model-selection bias).

Research pass requires >=100 closed trades, net profit>0 and PF>=1.15 in BOTH
cost regimes, MDD<=10%, >=4/6 positive two-month slices, neither asset contributes
>80% of total positive trade profit, and normal-cost bootstrap lower bound>0.
A variant with <100 trades is INSUFFICIENT_TRADES; otherwise any failure is
STOP_NO_EDGE. A pass means RESEARCH_ONLY_PASS, never trading authorization.
No changes based on this run: a changed rule needs a new registration and new
future observations. No claim of100% win rate, reliable daily multiples, or
liquidation safety. OHLC cannot establish actual order-book fill quality.

## Verification plan

Synthetic tests for indicator/signal prefix invariance, completed-hour alignment,
next-open execution, entry-bar stop, ambiguous stop/target, stop gap, fees and
funding, lot rounding and time exit. Verify data checksum, complete UTC cadence,
finite valid OHLCV, exact aggregation; then targeted tests, full available suite,
ruff and compile checks. Real PostgreSQL suites may be unavailable locally;
this research does not change execution or ledger paths.
