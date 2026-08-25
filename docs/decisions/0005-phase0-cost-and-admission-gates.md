# Decision 0005: Cost and admission gates precede strategy implementation

Date: 2026-08-25

## Status

Accepted for Phase 0.

## Decision

V3 does not add a carry, relative-value, or directional execution policy until
four machine-readable controls exist and pass independently:

1. a complete strategy cost ledger with an explicit source for every fee or
   estimate;
2. the seven reproducibility identifiers and a clean deployable source state;
3. instrument conformance for minimum notional, precision, asset index,
   leverage, quote age, and rejection probes;
4. the six-field intent record at final order admission.

The retained Freqtrade container remains a zero-entry shadow infrastructure
test. Its supported startup wrapper checks the dry-run configuration, exact
strategy, isolated database, and image digest before Docker Compose runs.

## Constraints

- Phase 0 cannot produce or submit an exchange order.
- Example JSON files are schemas, not venue evidence.
- `requirements-dev.txt` is not an exact dependency lock and therefore is not
  sufficient for a deployable run manifest.
- The local V2 SQLite file has no trade rows; the final 194-trade block
  bootstrap awaits a frozen, hash-matched export.

## Rejected alternatives

- Reusing aggregate cost stress as the operational ledger: it cannot attribute
  maker/taker, legging, funding, transfer, or repricing costs.
- Allowing unknown leverage or stale/missing quote state: both fail closed.
- Treating the IID V2 interval as final: dependent returns require the
  pre-registered block bootstrap.

## Consequences

An honest Phase 0 result may remain “not testable from current evidence.” No
control in this decision authorizes live trading or automatic strategy
promotion.

## Evidence update: 2026-08-25

The previously missing Oracle Tokyo V2 SQLite snapshot was retrieved and
hash-checked. It contains 194 closed trades and 388 filled closed orders. The
fee-only block bootstrap was pre-registered in commit `e22dcda` and then run;
the primary and every registered sensitivity interval were below zero.

This closes the evidence gap recorded above without changing the decision's
live-trading prohibition. The result gates V2 diagnostic wording, not Phase 1
simulation plumbing.
