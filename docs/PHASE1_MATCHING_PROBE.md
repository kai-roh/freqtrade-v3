# Bounded actual Demo order probe

This is an explicit user-authorized engineering diagnostic, not the carry strategy,
Nautilus gateway validation, profitability evidence, or a Phase 1E episode.

The probe submits **one actual matching-engine order**, then immediately cancels it.
Spot uses BTCUSDT BUY LIMIT_MAKER 1% below bid. USD-M uses BTCUSDT SELL LIMIT GTX
1% above ask. Each order is at most 180 mock USDT notional. No deliberate fill,
market order, transfer, broad cancellation, Mainnet mutation, or recurring loop is allowed.
Test sizing is deliberately separate from the economic strategy's headroom gate.

Before either operation: both Demo wallets must be prefunded, BTC futures must be
flat and isolated at no more than 2x, BTC open orders and active strategy commands
must be absent, and the fill inbox and prior probes must have no unresolved rows.
A PostgreSQL session lock excludes concurrent probes. A committed reservation
precedes POST. Lost responses never trigger another POST: cancel/query by the same
precommitted ID, then block further runs if the outcome cannot be established.

Passing requires matching venue order identity, price and quantity; CANCELED status;
zero executed quantity; no remaining BTC orders; and unchanged BTC inventories.
An unexpected fill or unknown outcome is BLOCKED, not successful, and prohibits
another probe. Preserve its evidence and reconcile/handle that Demo exposure before
proceeding. This is deliberately **not** unattended two-leg recovery.

Execution source must be committed/tagged and baked into an immutable image.
The runner records source SHA and the host-resolved image ID in PostgreSQL.
No credentials are baked into images or committed. Telegram reports the diagnostic,
not an invented strategy trade. Economic policy remains unchanged and order-free.

Official API references:

- [Binance Spot REST API](https://github.com/binance/binance-spot-api-docs/blob/master/rest-api.md): POST/DELETE `/api/v3/order`, LIMIT_MAKER, ambiguous execution status.
- [Binance USD-M connector](https://github.com/binance/binance-futures-connector-python/blob/main/binance/um_futures/account.py): new/cancel/query order endpoint contracts.

Any successful run only proves Demo account order acceptance and cancellation via
the bounded REST probe. The production-intended Nautilus approval/dispatch/recovery
path and a week-long automatic trading run remain separate unfinished work.

## Actual Oracle Demo results — 2026-09-14

| Product | Venue order ID | Quantity BTC | Limit USDT | Outcome |
|---|---|---:|---:|---|
| Spot BUY LIMIT_MAKER | 64634141675 | 0.00020000 | 76950.72 | CANCELED, zero fill |
| USD-M SELL LIMIT GTX | 28585069232 | 0.0008 | 78574.30 | CANCELED, zero fill |

Spot's first order query returned NEW even though the open-order snapshot was empty.
The probe correctly blocked further orders. A subsequent GET confirmed CANCELED;
the read-only reconciler resolved its ledger row and preserved the initial failed
report. No duplicate POST was sent. The updated probe allows up to ten bounded GET
reads after cancellation; unresolved states still block, rather than imply success.

Both probe rows are CANCELED in PostgreSQL. Both runs confirmed unchanged BTC
inventory, zero BTC open orders and flat BTC futures. Telegram delivery succeeded.
The probe containers exited; only PostgreSQL and the unchanged old bot remain up.

Execution source/image:

- Spot: `219c657d9f6704aa5dc46cb581f751924fa05bb2`,
  `sha256:c18c8e852546feb304b1c7142674e8be4df1117591260f774ed325900861d5c1`.
- Read-only resolution and Futures: `b32ee678a7665e67c1a196cd822989d6d17d0fa2`,
  `sha256:8ad6fa2c6a838417c024315faf50b9eeffe1b665d36d1a9a7e98147b555510d4`.

Evidence under `evidence/phase1/`: `matching-spot-initial-2026-09-14.json`,
`matching-spot-reconciled-2026-09-14.json`, `matching-perp-2026-09-14.json`.
Verification: 301 tests passed including PostgreSQL, Ruff passed.

There were **2 actual Demo order submissions, 0 fills, 0 strategy episodes**.
These results do not establish the Nautilus risk/dispatch connection, hedging,
partial-fill recovery, autonomous trading, or Phase 1 completion.
