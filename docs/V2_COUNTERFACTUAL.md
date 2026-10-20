# V2 Fee-only Counterfactual Preparation

The Phase 0 bootstrap input is generated only from the frozen 194-trade SQLite
database whose SHA-256 is recorded independently. The local empty V2 database
is deliberately rejected by the expected trade-count gate.

## Frozen assumptions

- The original price path, entries, exits, funding, and order costs do not
  change.
- Original simulated trading fees are restored from each filled order's
  `orders.cost` using the explicitly supplied original rate.
- The optimistic-fee Hyperliquid scenario classifies every filled `limit`
  order as maker and `market` / `stop-market` orders as taker. It is a
  lower-cost fee-only counterfactual, not a claim about transferable live fills
  or a lower bound on realized net performance.
- Closed trades are grouped by close date in Asia/Seoul by default. Every
  calendar date from first close to last close is emitted; dates without a
  close receive zero realized PnL.
- Daily net return is counterfactual realized PnL divided by an explicit fixed
  reference capital. It is not mark-to-market portfolio return.

## Preparation command

```bash
python3 scripts/prepare_v2_counterfactual.py \
  --database /path/to/frozen/tradesv3.sqlite \
  --expected-database-sha256 <independently-recorded-sha256> \
  --expected-closed-trade-count 194 \
  --original-fee-rate 0.00067 \
  --maker-fee-rate 0.00015 \
  --taker-fee-rate 0.00045 \
  --reference-capital 1000 \
  --daily-output evidence/v2-counterfactual/daily-net-returns.csv \
  --summary-output evidence/v2-counterfactual/fee-only-summary.json
```

The emitted CSV is the input to `scripts/run_block_bootstrap.py`. The
registration file must already be frozen; this command does not choose block
length or interpret statistical significance.

## Exit analysis boundary

Fee-only preparation does not evaluate exit logic. Exit work remains two
separate analyses:

1. fixed-entry trade-level replay compares hypothetical exits on the same
   entry set;
2. full strategy reruns measure changed slot occupancy, later entry
   opportunities, and the resulting capital path.

Because V2 used `max_open_trades=2`, a changed exit has a first-order effect on
future opportunity availability. Results from the two layers must never be
merged into a single causal claim.
