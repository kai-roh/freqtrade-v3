# V2 Fee-only Block Bootstrap Pre-registration

Frozen before reading any bootstrap result on 2026-08-25 KST.

## Evidence identity

- source database SHA-256:
  `3d19d73c869b85532c03f2e33a3e56112371b4c69fa28a276b715cee8f4793e2`
- closed trades: 194
- filled closed orders: 388
- reporting period: 87 calendar days, including zero-close days
- reference capital: 1,000 USDT
- fee scenario: every filled limit order is treated as maker; market and
  stop-market orders are treated as taker

The fee scenario is an optimistic-cost counterfactual. It is not a claim about
live maker fills or a lower bound on realized net performance.

## Frozen statistical choices

| Choice | Registration |
|---|---|
| sample unit | daily realized portfolio PnL divided by fixed reference capital |
| calendar handling | include every date from first close to last close; zero when no trade closes |
| primary block | moving contiguous 5-day blocks |
| sensitivity blocks | 1, 3, 7, and 10 days |
| iterations | 10,000 per block length |
| seed | 20260819 |
| interval | two-sided percentile interval, alpha 0.05 |

Daily aggregation is fixed because V2 allowed two simultaneous positions and
individual-trade resampling would split dependent exposure. The primary
five-day block is a conservative operating-week window after intraday overlap
has already been aggregated. Sensitivity lengths test whether the sign of the
interval depends on that choice. The one-day result is a daily IID boundary,
not the primary result.

## Interpretation rule

- The primary five-day interval determines the Phase 0 wording.
- Sensitivity intervals are reported together and may weaken, but may not
  upgrade, the conclusion.
- If any sensitivity interval includes zero, the result is described as not
  robust to block length.
- These results do not gate testnet infrastructure work. They gate only the V2
  diagnostic wording and any future attempt to revive the V2-style directional
  strategy.

No block length, seed, alpha, fee rate, daily grouping, or interpretation rule
may be changed after result generation without creating a new registration and
an untouched holdout.
