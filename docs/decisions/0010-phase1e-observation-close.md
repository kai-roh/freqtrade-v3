# 0010 — Close the Phase 1E observation; Phase 1 gate has one unmet item

- Status: Accepted
- Date: 2026-10-02
- Amended by: [0011](0011-amend-phase1-gate-item5.md) — item 5 redefined for Demo; Phase 1 is now complete for Demo

## Context

Phase 1E repeated the synthetic Demo two-leg engineering episode (Spot buy, perp
hedge, 300 s hold, reduce-only perp close, Spot sell, residual settlement) under
`configs/phase1-week-run.json`. The first week run started 2026-09-15 12:07 UTC.
The extension run started 2026-09-28 07:03 UTC. The extension run was stopped on
user instruction on 2026-10-02 03:38 UTC, during an idle interval with no open
episode, after the 50-episode requirement was exceeded.

Evidence: `evidence/phase1/phase1e-close-20261002/` (SLA summary, fee snapshot,
connectivity probe). The per-event run logs stay on the server under
`evidence/phase1/demo-week-run-20260915/` and `evidence/phase1/demo-week-run-20260928/`.
All ledger figures below come from read-only queries (`default_transaction_read_only=on`)
against `phase1-postgres` on 2026-10-02.

## Observation result

| Item | Value |
|---|---|
| Intents in the ledger | 70, all `CLOSED` |
| Week-run episodes (manifests `2ad58440`, `8f3072d6`, `3b3038e9`, `5a07e153`, `41683c98`) | 67 |
| Earlier engineering and verify-repeat episodes (`1376587d`, `9f134acd`) | 3 |
| Order commands / dispatches / orders | 289 / 289 / 289, all dispatches `OBSERVED` |
| Fills | 296 (orders `FILLED` 274, `EXPIRED` 15) |
| Episodes needing a fifth or sixth IOC command | 6 and 3 |
| Settled residuals | 69, total `0.00050308 BTC`, equal to the Demo Spot BTC balance |
| Demo account at close | perp `0`, open orders none |

Earlier progress notes counted "cumulative CLOSED" over all 70 intents. The
week-run count alone is 67. The gate requires 50 synthetic two-leg attempts, so
either count passes.

### SLA evidence (`sla-evidence-20261002.json`)

| Measure | Samples | Median | p99 |
|---|---:|---:|---:|
| USD-M quote exchange age | 307,696 | 10 ms | 48 ms |
| Hedge latency, first Spot fill to first perp fill | 69 | 4,437 ms | 7,340 ms |

- The quote-age rule ceil(2 × p99) gives 96 ms. This equals the adopted
  `maximum_quote_age_ms=96`, so the policy stays unchanged.
- Spot bookTicker has no exchange timestamp and remains unmeasured (403,739 quotes).
- Hedge latency is dominated by this runner's 2-second management tick, fill
  confirmation, and the independent risk round trip. It describes this
  engineering runner on Demo. It is not a venue latency and never becomes an
  operating SLA.

## Halts during the observation

| Halt (UTC) | Cause | Exposure left open | Closed | Fix |
|---|---|---|---|---|
| 09-17 16:41 | Spot close IOC denied with `quote transport stale`; the runner treated a transient freshness denial as fatal | Spot long `0.00286713 BTC` (about 220 USDT), perp flat | 09-25 11:01, about 186 h later | `1a124d1`: retry freshness denials next tick, cap 5 consecutive |
| 09-25 08:08 (resume attempt) | The unhedged notional-duration invariant integrated the stopped days and fired before the Spot sell; no order | unchanged | same as above | `1a124d1`: in the closing phase, record the exceedance as baseline evidence and keep closing |
| 09-29 18:31 | A closing perp IOC filled `0.0025` of `0.0026`; the planner called the `0.0001 BTC` remainder dust because it was under the 50 USDT minimum, and settlement refused because futures were not flat | Spot long `0.00262737 BTC`, perp short `0.0001` | 09-30 06:37, about 12 h later | `5e8afe1`: close any whole-lot short remainder reduce-only (Binance -4164 exempts reduce-only orders; Nautilus 1.231 skips notional checks for margin accounts; Demo minQty is `0.0001`) |

Each halt was fail-closed: no new entry, no duplicate order, no rejected
transition. Each open episode was closed later by an approved close-only
takeover. After `5e8afe1` the runner closed 22 more episodes and the takeover
without a halt. The transient-denial retry and the closing-phase budget rule
have unit and integration tests. Neither has been exercised by a live Demo
denial since deployment.

## Phase 1 exit gate (`PHASE1_IMPLEMENTATION_PLAN.md` §10)

| # | Item | Result | Evidence |
|---|---|---|---|
| 1 | Mainnet orders 0, real capital 0 | Met | 289 dispatch payloads: `environment=demo`, `live_orders=false`, `real_capital=false` |
| 2 | No approval with unknown leverage or above 2x | Met | 219 position decisions record `perp_leverage=2`, `ISOLATED`. The 70 entry decisions bind a dispatch payload with account leverage 2 and `ISOLATED`; the entry decision row itself does not store leverage |
| 3 | Unexplained reconciliation residual below threshold and classified in time | Met | 69 reconciliation runs, unexplained residual 0; 69 residual settlements, incidents all resolved |
| 4 | No duplicate venue order, no orphan fill | Met | 0 duplicate venue order IDs, client order IDs, or venue fill IDs; 0 fills without an order; fill inbox fully applied |
| 5 | No unhedged exposure left open after a failure | **Not met** | Two failures left unhedged Demo exposure open for about 186 h and 12 h. None remains now. See below |
| 6 | Every order command references intent, cost ledger, manifest | Met | 0 commands without an intent; 0 intents missing a manifest or cost ledger ID |
| 7 | At least three forced-termination recoveries | Met | Three deliberate mid-episode kills on 2026-09-15, each resumed with `RESUMING` and closed without re-hedging |
| 8 | 21 transitions and 6 invariants tested | Met | `tests/test_phase1_state_machine.py`; full suite 441 passed |
| 9 | 13 fault scenarios pass | Met | `run_fault_suite()` on `5e8afe1`: 13/13 |
| 10 | Hedge-latency lower bound and quote-age SLA recorded with counts and percentiles | Met | table above |
| 11 | Profitability not used as a completion criterion | Met | no PnL figure is used here |
| 12 | Mainnet fee snapshot within 24 h and matching its source | Met | `binance-mainnet-fees-20261002.json`, GET-only, captured 03:40 UTC: Spot 10/10 bps, USD-M 2/5 bps, unchanged |

## Decision

1. The Phase 1E observation is closed. No further week run is started.
2. Phase 1 is **not** marked complete. The plan requires every gate item, and
   item 5 failed twice. The runner is fail-closed by design: on a fatal error it
   stops new orders but does not unwind, and a person restarts it. Exposure can
   therefore stay open for as long as nobody responds.
3. Item 5 can be closed in exactly one of two ways. Either is a new decision:
   - **Automatic close-only recovery.** On a fatal error with an open episode,
     the runner hands off to a bounded close-only path. This is new execution
     code and needs its own tests and a Demo verification with forced faults.
   - **Explicit amendment.** Item 5 is redefined as "fail-closed with alerting
     and a documented human recovery". This also needs a stated maximum response
     time. Telegram already delivered every halt notification in this run.
4. The quote-age policy stays at 96 ms. Nothing in this ADR authorizes Mainnet
   orders, real capital, or Phase 3 (Decision 0006 §Constraints).

## Consequences

- There is no runner on the server. The Demo account holds only settled
  residual BTC and no futures position.
- The open Phase 1 work is the item-5 choice above. Phase 3 still has no
  candidate strategy (Decision 0009), so the choice is not urgent.
- The decision row for an entry should also store the observed leverage, so that
  item 2 can be read from `risk_decisions` alone. This is a small audit gap, not
  a gate failure.
