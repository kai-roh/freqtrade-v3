# Frozen V2 Source Database

The private SQLite source is copied read-only from:

`ft-tokyo:/home/kai/freqtrade-v2/user_data/tradesv3.sqlite`

It is intentionally ignored by Git. Only its hash, structural checks, and
derived non-secret aggregates are committed.

Frozen copy verification on 2026-08-25 KST:

- SHA-256: `3d19d73c869b85532c03f2e33a3e56112371b4c69fa28a276b715cee8f4793e2`
- closed trades: `194`
- filled closed orders: `388`
- open trades: `0`

The hash differs from the repository's 2026-08-10 baseline evidence. Results
derived from this copy must use the new hash and must not inherit the older
snapshot identity.
