# V2 Fee-only Block Bootstrap Results

Generated on 2026-08-25 KST after commit `e22dcda` froze the statistical
choices. No result was read before the registration commit.

## Evidence

- database SHA-256:
  `3d19d73c869b85532c03f2e33a3e56112371b4c69fa28a276b715cee8f4793e2`
- closed trades: 194
- filled closed orders: 388
- calendar days: 87, including zero-close days
- reference capital: 1,000 USDT
- observed daily mean: `-0.0007781461` (`-0.0778146%`)

## Registered Method

- repetitions: `10,000`
- seed: `20260819`
- block family: non-circular moving contiguous blocks sampled with replacement
- boundary handling: start positions are `0..n-L`; blocks never wrap from the last
  observation to the first, and the final sampled block is trimmed to `n=87`
- interval: two-sided percentile interval at `alpha=0.05`, using the empirical
  `2.5%` and `97.5%` quantiles of bootstrap means

| Block length | Eligible moving-block starts |
|---:|---:|
| 1 day | 87 |
| 3 days | 85 |
| 5 days, primary | 83 |
| 7 days | 81 |
| 10 days | 78 |

## Pre-registered Results

| Block length | 95% CI in daily-return units | Percent form |
|---:|---:|---:|
| 1 day | `[-0.0015245204, -0.0000772536]` | `[-0.1524520%, -0.0077254%]` |
| 3 days | `[-0.0015334401, -0.0001141672]` | `[-0.1533440%, -0.0114167%]` |
| 5 days, primary | `[-0.0015174672, -0.0001156719]` | `[-0.1517467%, -0.0115672%]` |
| 7 days | `[-0.0014962381, -0.0001568801]` | `[-0.1496238%, -0.0156880%]` |
| 10 days | `[-0.0015731254, -0.0001521509]` | `[-0.1573125%, -0.0152151%]` |

All registered intervals are below zero. The sign is therefore robust across
the registered block-length sensitivity set.

## Dependence Diagnostic

The audit below was calculated after the registered bootstrap from the same 87
calendar-day series. It checks that the flat CI width was not being produced by
a block-length implementation error. ACF lag 8 is visibly positive, so the data
should not be described as independent. The Ljung-Box test through lag 10 did
not reject its no-autocorrelation null (`Q=13.7484`, `p=0.1848`). The precise
statement is therefore “material serial dependence was not detected at the
registered daily aggregation,” not “dependence is absent.”

| Lag | ACF | Ljung-Box Q | p-value |
|---:|---:|---:|---:|
| 1 | 0.0094 | 0.0080 | 0.9287 |
| 2 | -0.0976 | 0.8756 | 0.6455 |
| 3 | 0.0108 | 0.8863 | 0.8287 |
| 4 | -0.0155 | 0.9087 | 0.9233 |
| 5 | -0.0423 | 1.0774 | 0.9561 |
| 6 | -0.0707 | 1.5549 | 0.9558 |
| 7 | 0.0830 | 2.2218 | 0.9466 |
| 8 | 0.2746 | 9.6125 | 0.2933 |
| 9 | -0.1176 | 10.9847 | 0.2768 |
| 10 | -0.1658 | 13.7484 | 0.1848 |

## Fee-only Scenario Comparison

These values hold V2 orders and prices fixed and replace only the fee schedule.
The Hyperliquid schedule is included as the more favorable comparison, not as a
claim that V2 fills could have been transferred to Hyperliquid. Neither value is
a lower bound on live performance because queue position, adverse selection,
slippage, and changed fills remain unmodeled.

| Fee-only schedule | Repriced fee | Counterfactual net PnL |
|---|---:|---:|
| Hyperliquid-style maker 1.5 / taker 4.5 bps | 52.9460 USDT | -67.6987 USDT |
| Binance maker 2 / taker 5 bps | 65.5644 USDT | -80.3171 USDT |

## Interpretation Boundary

This result supports the narrow statement that the registered V2 fee-only
counterfactual daily portfolio return is negative under every registered block
length. It does not prove that a model was internally sound, does not reconstruct
live fills, and does not identify every cause of V2 loss.

The result does not gate Phase 1 simulated execution work. It gates the V2
diagnostic wording and any future attempt to revive the V2-style short-horizon
directional strategy.

## Artifacts

- `evidence/v2-counterfactual/fee-only-summary.json`
- `evidence/v2-counterfactual/daily-net-returns.csv`
- `evidence/v2-counterfactual/bootstrap-primary-5d.json`
- `evidence/v2-counterfactual/bootstrap-sensitivity-{1d,3d,7d,10d}.json`
- `evidence/v2-counterfactual/daily-return-dependence.json`
