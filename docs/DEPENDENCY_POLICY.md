# Dependency and Execution-Engine Pinning Policy

Phase 0 did not install NautilusTrader. Phase 1A now has a separate, exact-pinned
execution dependency set for the Binance Demo path. A successful local import is
necessary compatibility evidence, but it is not proof of credentialed connectivity
or permission to submit orders.

## Deployment rule

A deployable run manifest requires both:

- an exact resolved dependency file (`uv.lock`, `poetry.lock`,
  `Pipfile.lock`, or exact `package==version` requirements); and
- the SHA-256 of that file in the seven-field run manifest.

`uv.lock` is the canonical deployment lock. `requirements-dev.txt` mirrors the
top-level exact pins for bootstrap convenience but is not the transitive deployment
record. The execution manifest must reference the SHA-256 of `uv.lock`.

## NautilusTrader policy

Phase 1A pins NautilusTrader `1.231.0` with Python `3.12.12` in the dedicated
execution image.
The image itself will be referenced by digest. No floating `latest`, compatible
range, or automatic dependency upgrade is allowed in the order path.

An upgrade is a dedicated reviewed change. It must rerun instrument parsing,
order submit/cancel/modify, delayed-fill reconciliation, liquidation/ADL,
restart recovery, leverage fail-closed, quote-age, and emergency-hedge tests
before replacing the prior image digest.

## Phase 1A selection evidence

- Python: `3.12.12`
- NautilusTrader: `1.231.0`
- PostgreSQL: `16.14-bookworm`, pinned by ARM64 manifest digest
- Resolver: `uv.lock`, checked with `uv lock --check`
- Adapter smoke: distinct Binance Spot and USD-M `DEMO` data/execution configs

The checked-in Dockerfile is buildable before registry publication, but runtime
admission remains closed until the deployed image's immutable registry digest is
recorded. A local image ID is not a substitute for that digest.
