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

`examples/phase0/block-bootstrap.preregister.json` remains an input schema. The
approved V2 registration, evidence identity, primary five-day block, and
sensitivity rule are frozen in `docs/V2_BOOTSTRAP_PREREGISTRATION.md` and the
`configs/v2-fee-bootstrap-*.json` files.

## Input Contract

The runner accepts a CSV with unique, ascending `timestamp` rows and a finite
`net_return` value for each independent period. It rejects duplicate or
unsorted rows and refuses `individual_trade` as a sample unit.

```bash
python3 scripts/run_block_bootstrap.py \
  --input-csv evidence/v2-counterfactual/daily-net-returns.csv \
  --registration configs/v2-fee-bootstrap-primary.json \
  --output evidence/v2-counterfactual/bootstrap-primary-5d.json
```

The original local `/Users/seop/freqtrade-v2/user_data/tradesv3.sqlite` has no
trade rows. A private frozen copy containing 194 closed trades and 388 filled
orders was retrieved from Oracle Tokyo and hash-checked on 2026-08-25. Its raw
SQLite file is deliberately excluded from Git; only the source hash, structural
checks, registration, and derived aggregates are versioned.

`scripts/prepare_v2_counterfactual.py` performs that hash and trade-count gate,
restores the original simulated fee from filled-order costs, applies the
predefined fee-only scenario, and emits every calendar day including zero-close
days. Its exact assumptions and the separate two-layer exit analysis are
recorded in `docs/V2_COUNTERFACTUAL.md`.

## Completed Result

The primary five-day interval was
`[-0.0015174672, -0.0001156719]` in daily-return units. The registered
1/3/7/10-day sensitivity intervals were also below zero. The sign is robust to
the registered block lengths.

The full table and narrow interpretation are recorded in
`docs/V2_BOOTSTRAP_RESULTS.md`. This conclusion does not gate Phase 1 simulated
execution infrastructure.
