# Documents

Start with [`../PROGRESS.md`](../PROGRESS.md) for the current state, open issues, and
next steps. Everything below is reference material; dated sections inside each
file are historical records and are not rewritten.

## Decisions (`decisions/`)

| # | Decision | Date |
|---|---|---|
| 0001 | Rebuild the strategy core, retain operations | 2026-08-10 |
| 0002 | Stop before classifier implementation | 2026-08-10 |
| 0003 | Reuse V2 infrastructure for the zero-entry shadow | 2026-08-10 |
| 0004 | Schedule reporting and research without automatic promotion | 2026-08-10 |
| 0005 | Cost and admission gates precede strategy implementation | 2026-08-25 |
| 0006 | Phase 1 carry uses Binance Demo | 2026-08-25 |
| 0007 | Settle unsellable residual inventory; project funding conservatively | 2026-09-15 |
| 0008 | Register the Phase 2 basket hypotheses before any code | 2026-09-16 |
| 0009 | Phase 2 basket result: STOP_NO_EDGE | 2026-09-17 |
| 0010 | Close the Phase 1E observation; Phase 1 gate has one unmet item | 2026-10-02 |
| 0011 | Amend Phase 1 gate item 5 (Demo): fail-closed, alerting, 24 h human recovery | 2026-10-02 |
| 0012 | Register the Phase 2b low-turnover maker funding carry | 2026-10-02 |
| 0013 | Phase 2b maker funding carry result: STOP_NO_EDGE | 2026-10-02 |
| 0014 | Shelve the funding cross-section family after the risk-neutralization diagnosis | 2026-10-02 |
| 0015 | Register the Phase 2c BTC/ETH low-frequency trend study | 2026-10-02 |
| 0016 | Phase 2c trend result: STOP_NO_EDGE | 2026-10-02 |
| 0017 | Fixed MA200 comparison: PAUSE_RESEARCH (implementability at a 500 USDT sleeve) | 2026-10-02 |
| 0018 | User decision: MA200 at a 1,000 USDT sleeve (plan departure) — OBSERVE_ELIGIBLE | 2026-10-02 |
| 0019 | Register the order-free MA200 forward observation with a 7-day operational dry run | 2026-10-02 |
| 0020 | MA200 live risk contract: −10% stop (incompatible at 1,000 USDT), automatic guard, Demo first, Mainnet locked | 2026-10-02 |
| 0021 | User decision: MA200 loss stop at −20% (800 USDT), Demo included; risk level stays at 25% | 2026-10-03 |

## Phase 1 (Binance Demo two-leg carry execution)

- `PHASE1_IMPLEMENTATION_PLAN.md` — the 1A–1E plan, 21 transitions, 6 invariants, exit gate.
- `PHASE1_IMPLEMENTATION_STATUS.md` — dated progress log; newest section on top.
- `PHASE1_DEMO_AUTO_RUNBOOK.md` — the automatic episode runner, residual settlement, verification runs.
- `PHASE1_WEEK_RUN.md` — week observation scope, stop conditions, Telegram, restart procedure, status.
- `PHASE1_INTEGRATION_RUNBOOK.md` — ledger/risk/Nautilus connection notes and remaining conditions.
- `PHASE1_MATCHING_PROBE.md` — the bounded accept-and-cancel order probe.

## Phase 2 (perp-only market-neutral basket research)

- `PHASE2_PREREGISTRATION.md` — frozen hypotheses, universe, costs, validation, gates.
- `PHASE2B_PREREGISTRATION.md` — Phase 2b follow-up: low-turnover maker funding carry, two-stage validation. Result `STOP_NO_EDGE` (Decision 0013); outputs in `../research_results/phase2b/`, evidence in `../evidence/phase2b/`.
- Results: `../research_results/phase2/REPORT.md`, evidence in `../evidence/phase2/`.
- `PHASE2B_RISK_DIAGNOSIS.md` — pre-committed risk-neutralization diagnosis (balance restoration, beta sizing); result `SHELVE_FAMILY` (Decision 0014), outputs in `../research_results/phase2b/risk-diagnosis/`.

## Phase 2c (BTC/ETH low-frequency trend)

- `PHASE2C_PREREGISTRATION.md` — daily trend persistence with conviction sizing, controls, continuous walk-forward. Result `STOP_NO_EDGE` (Decision 0016); outputs in `../research_results/phase2c/`.
- `MA200_FORWARD_OBSERVATION.md` — order-free daily MA200 observation from 2026-10-03, 7-day operational dry run, Telegram daily/weekly/monthly, change policy, real-trading prerequisites.
- `PHASE2C_MA200_COMPARISON.md` — pre-committed fixed-MA200 comparison against spot and perpetual holds with exchange-faithful orders. Result `PAUSE_RESEARCH` (Decision 0017); outputs in `../research_results/phase2c/ma200-comparison/`.

## Phase 0 and research foundations

- `STRATEGY_PHASE0_FINAL.md`, `PHASE0_DEVELOPMENT.md`, `MILESTONE_1.md`
- `REPORTING_AND_RESEARCH.md` — Telegram reports and the weekly walk-forward (capital-basis metrics since 2026-09-15).
- `BLOCK_BOOTSTRAP.md`, `V2_BOOTSTRAP_PREREGISTRATION.md`, `V2_BOOTSTRAP_RESULTS.md`, `V2_COUNTERFACTUAL.md`

## Operations

- `SERVER_STATE.md` — dated server snapshots; newest on top.
- `DEPENDENCY_POLICY.md`, `MIGRATION_V2_TO_V3.md`
