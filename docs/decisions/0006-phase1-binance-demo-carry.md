# Decision 0006: Phase 1 carry uses Binance Demo

Date: 2026-08-25

## Status

Accepted for Phase 1.

## Decision

Phase 1 uses Binance Demo with separate Spot and USD-M NautilusTrader clients.
The two economic legs are BTCUSDT spot long and BTCUSDT perpetual short.
NautilusTrader is the execution engine; the retained Freqtrade process remains
a zero-entry legacy shadow only.

Hyperliquid order submission is deferred. Its public metadata remains a
read-only research input, and Hyperliquid remains a Phase 2 perp-only candidate.

## Context

Hyperliquid documents that the BTC/USDC label in its UI maps to UBTC/USDC on
HyperCore. This adds raw-symbol remapping, Unit bridge/custody exposure, and
UBTC/BTC basis risk to what was intended to be a simple spot-perp carry PoC.

Hyperliquid portfolio margin is pre-alpha and its current eligible collateral
and borrow caps are constrained. The documentation does not establish that the
specific UBTC spot balance used by the proposed leg will reliably offset the
BTC perp for this automated account.

Binance provides native BTCUSDT Spot and USD-M products. Its Spot API supports
`LIMIT_MAKER`, and USD-M supports `GTX` post-only. NautilusTrader supports both
products, recommends Demo for new simulated setups, and exposes order, fill,
position, balance, and commission-rate reconciliation paths.

## Constraints

- Demo only; live orders and real capital are not authorized.
- Spot and USD-M are separate clients and must have separate account/client IDs.
- Exact commission, leverage, margin mode, symbol filters, funding interval, and
  reject behavior are captured from timestamped venue responses.
- A synthetic target can bypass the scanner only in Demo/Testnet.
- Phase 1 completion does not authorize Phase 3.

## Rejected alternatives

- Hyperliquid UBTC spot plus BTC perp: bridge and basis risks obscure the Phase 1
  infrastructure objective.
- Cross-venue perp/perp carry: it adds transfer, collateral fragmentation, and
  two independent venue failure domains.
- Legacy Binance Testnet as the default: NautilusTrader recommends Binance Demo
  for new simulated trading setups.

## Reversal condition

Changing the Phase 1 venue requires a new ADR and evidence that the replacement
passes the same 13 fault scenarios, 18 transitions, six invariants, quote-age
SLA, restart recovery, fee query, leverage gate, and reconciliation checks.

Hyperliquid spot carry additionally requires account-level proof that UBTC is
the actual instrument and collateralizes the BTC perp under the selected account
mode, plus an explicit UBTC/BTC basis and bridge-risk budget.

## Sources

- <https://nautilustrader.io/docs/latest/integrations/binance/>
- <https://developers.binance.com/docs/binance-spot-api-docs/rest-api/trading-endpoints>
- <https://developers.binance.com/docs/derivatives/usds-margined-futures/common-definition>
- <https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint>
- <https://hyperliquid.gitbook.io/hyperliquid-docs/trading/account-abstraction-modes>
- <https://hyperliquid.gitbook.io/hyperliquid-docs/trading/portfolio-margin>
