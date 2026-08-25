# Dependency and Execution-Engine Pinning Policy

Phase 0 does not install NautilusTrader. The current Python environment belongs
to the retained Freqtrade research and shadow tooling; it is not evidence that
the future Nautilus execution path is ready.

## Deployment rule

A deployable run manifest requires both:

- an exact resolved dependency file (`uv.lock`, `poetry.lock`,
  `Pipfile.lock`, or exact `package==version` requirements); and
- the SHA-256 of that file in the seven-field run manifest.

`requirements-dev.txt` is intentionally loose and is not a deployment lock.
The manifest command rejects it unless
`--allow-unlocked-dependencies` is explicitly used; that output remains marked
non-deployable.

## NautilusTrader policy

When the Phase 1 PoC begins, the selected NautilusTrader release and Python
minor version will be exact-pinned together in a dedicated execution image.
The image itself will be referenced by digest. No floating `latest`, compatible
range, or automatic dependency upgrade is allowed in the order path.

An upgrade is a dedicated reviewed change. It must rerun instrument parsing,
order submit/cancel/modify, delayed-fill reconciliation, liquidation/ADL,
restart recovery, leverage fail-closed, quote-age, and emergency-hedge tests
before replacing the prior image digest.

The exact Nautilus version remains deliberately unselected in Phase 0; choosing
it without the execution PoC would create a nominal pin without compatibility
evidence.

## Phase 1A selection procedure

Phase 1 has selected the Binance Demo adapter path, but not an untested package
version. The first Phase 1A change must build an ARM64 compatibility matrix for
the current stable NautilusTrader release and Python 3.12, run the order-free
Binance Spot/USD-M smoke tests, and then commit the exact resolved version and
lock hash. No execution entry point may run before that commit is clean and its
image digest is recorded.
