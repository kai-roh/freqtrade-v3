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
