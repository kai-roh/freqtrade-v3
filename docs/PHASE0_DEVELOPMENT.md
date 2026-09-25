# Phase 0 Development Notes

This document tracks the local implementation started from the final V3 strategy
contract.

## Implemented Slice

The first Phase 0 code slice adds pure, testable primitives:

- `v3.costs`: exact cost-ledger calculation from explicitly sourced fee rates.
- `v3.bootstrap`: pre-registered contiguous block bootstrap for dependent net
  returns.
- `v3.reproducibility`: validated seven-field manifest, artifact hashing,
  deterministic run identity, and dirty-tree deployment rejection.
- `v3.instruments`: Decimal-based minimum-notional, precision, asset-index,
  leverage, quote-age, and reject-probe conformance checks.
- `v3.hyperliquid`: read-only `metaAndAssetCtxs` capture, exact-response hash,
  asset-index mapping, delisting state, and venue precision derivation.
- `v3.v2_counterfactual`: hash- and trade-count-gated fee-only daily return
  preparation for the dependent-return bootstrap.
- `v3.preflight`: runtime order admission that combines instrument conformance
  with the mandatory six-field intent record.
- `scripts/build_hyperliquid_preflight_input.py`: converts a captured
  Hyperliquid evidence snapshot into order-preflight JSON without submitting an
  order.
- `scripts/check_order_preflight.py`: validates final order admission including
  the six-field intent record.
- `v3.runtime_preflight`: retains the old Freqtrade service only when its
  fail-closed shadow config, strategy, isolated database, and image digest pass.

## Test Contract

The new tests intentionally describe behavior rather than implementation:

- `tests/test_costs.py` verifies fee and non-fee ledger accounting.
- `tests/test_bootstrap.py` verifies forbidden trade-level resampling,
  deterministic seeded output, and minimum sample length.
- `tests/test_reproducibility.py` verifies mandatory metadata, artifact hashes,
  dirty-tree rejection, and stable manifest identity.
- `tests/test_instruments.py` and `tests/test_preflight.py` verify min-notional
  headroom, precision, max leverage, quote freshness, reject probes, and intent
  completeness.
- `tests/test_hyperliquid.py` verifies metadata parsing, response hashing,
  precision derivation, missing symbols, delisting state, and snapshot-to-order
  preflight conversion.
- `tests/test_v2_counterfactual.py` verifies immutable DB identity, trade-count
  gating, fee reconciliation, time-zone grouping, and zero-close calendar days.

## Operator Commands

The example files are schemas, not current venue evidence.

```bash
python3 scripts/calculate_cost_gate.py --input examples/phase0/cost-gate.json
python3 scripts/check_instrument_conformance.py \
  --input examples/phase0/instrument-preflight.json
python3 scripts/capture_hyperliquid_instruments.py \
  --environment testnet --symbol BTC \
  --raw-output evidence/instruments/hyperliquid-testnet-raw.json \
  --output evidence/instruments/hyperliquid-testnet-btc.json
python3 scripts/build_hyperliquid_preflight_input.py --help
python3 scripts/check_order_preflight.py --input examples/phase0/order-preflight.json
python3 scripts/run_block_bootstrap.py --help
python3 scripts/prepare_v2_counterfactual.py --help
python3 scripts/check_shadow_runtime.py
```

The only supported shadow startup path is `scripts/start_shadow_runtime.sh`,
which runs the runtime preflight before Docker Compose.

`scripts/build_run_manifest.py` requires a real image digest, dependency lock,
config, data files, and timerange. It rejects a dirty Git tree unless
`--allow-dirty` is explicitly used for a non-deployable development artifact.
It also rejects loose requirements; `--allow-unlocked-dependencies` records an
explicitly non-deployable development manifest.

## Phase 0 Completion Update

- The private Oracle Tokyo V2 database was copied, hash-checked, and excluded
  from Git. It contains 194 closed trades and 388 filled closed orders.
- The fee-only daily series and pre-registered 1/3/5/7/10-day block bootstrap
  were generated. All registered 95% intervals are below zero.
- The baseline implementation is fixed at tag `phase0-baseline`.
- The bootstrap result does not block Phase 1 simulated execution work.

## Remaining Credentialed Checks

- Add a no-fill reject-code smoke probe after testnet credentials and a dedicated
  account are available. Metadata capture itself is already implemented and
  cannot submit an order.
- Add run-manifest output to research/reporting artifacts.
- Implement the fixed-entry V2 exit replay and full-strategy rerun only after
  the frozen V2 artifacts are restored; their causal boundary is already fixed
  in `docs/V2_COUNTERFACTUAL.md`.
- Select and pin the NautilusTrader/Python pair as the first Phase 1A
  compatibility task; the current Freqtrade research environment is not the
  Nautilus execution environment.

The Phase 1 implementation contract is in `docs/PHASE1_IMPLEMENTATION_PLAN.md`.
