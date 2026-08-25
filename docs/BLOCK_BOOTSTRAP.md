# Block Bootstrap Contract

The Phase 0 fee-only counterfactual is not promoted from an IID trade-level
test. Its final confidence interval must be produced from ordered daily
portfolio returns or exposure clusters.

## Pre-registration

The following values are fixed before looking at a bootstrap result:

- sample unit;
- moving contiguous-period block definition;
- block length and any sensitivity lengths;
- iteration count and random seed;
- two-sided test direction and alpha.

`examples/phase0/block-bootstrap.preregister.json` is an input schema, not an
approved V2 registration. The chosen block length still requires the frozen V2
exposure chronology and a written sensitivity rule.

## Input Contract

The runner accepts a CSV with unique, ascending `timestamp` rows and a finite
`net_return` value for each independent period. It rejects duplicate or
unsorted rows and refuses `individual_trade` as a sample unit.

```bash
python3 scripts/run_block_bootstrap.py \
  --input-csv evidence/v2-counterfactual/daily-net-returns.csv \
  --registration configs/block-bootstrap.preregister.json \
  --output evidence/v2-counterfactual/bootstrap-result.json
```

The local `/Users/seop/freqtrade-v2/user_data/tradesv3.sqlite` currently has no
trade rows, so it cannot support the final V2 calculation. A frozen export of
the 194-trade database must be supplied and hash-checked against the evidence
record before an actual result is generated.

`scripts/prepare_v2_counterfactual.py` performs that hash and trade-count gate,
restores the original simulated fee from filled-order costs, applies the
predefined fee-only scenario, and emits every calendar day including zero-close
days. Its exact assumptions and the separate two-layer exit analysis are
recorded in `docs/V2_COUNTERFACTUAL.md`.
