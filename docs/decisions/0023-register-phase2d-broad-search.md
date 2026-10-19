# 0023 — Register Phase 2d: broad multi-asset, long-history strategy search

- Status: Accepted
- Date: 2026-10-19 (KST)

## Context

On 2026-10-19 the user asked for a strategy with a high return net of fees before any
live trading, using more data and new strategies if needed. Every earlier study used
BTC and ETH from 2020 to 2026 only, and every one stopped without an edge
(Decisions 0009, 0013, 0016, 0017). The MA200 forward observation cannot measure
profitability on any practical horizon, because a Sharpe near 0.8 needs about six years
of live data.

## Decision

Register [PHASE2D_PREREGISTRATION.md](../PHASE2D_PREREGISTRATION.md) before looking at
any result. The registration fixes the following:

- **Data:** every Binance USDT spot pair from 2017-08 and every USD-M perpetual from
  2019-09, delisted pairs included, frozen by SHA-256.
- **Trials:** six strategy families, 120 configurations in all.
- **Costs:** fees plus liquidity-tiered slippage, and actual funding on perpetuals.
- **Development window:** 2018 to 2024, or 2020-07 to 2024 for perpetuals. The
  following selection checks are applied here:
  - PBO
  - Deflated Sharpe at M=120
  - a cost-doubling check
  - drawdown and yearly checks
- **Holdout:** 2025-01 to 2026-09, computed once after selection.
- **Outcomes:** `PASS` leads to an order-free forward observation of the selected
  strategy. `STOP_NO_EDGE` otherwise.

The MA200 observation and the Demo executor keep running unchanged meanwhile.
