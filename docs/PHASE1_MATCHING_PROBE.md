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
