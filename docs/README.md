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

## Phase 1 (Binance Demo two-leg carry execution)

- `PHASE1_IMPLEMENTATION_PLAN.md` — the 1A–1E plan, 21 transitions, 6 invariants, exit gate.
- `PHASE1_IMPLEMENTATION_STATUS.md` — dated progress log; newest section on top.
- `PHASE1_DEMO_AUTO_RUNBOOK.md` — the automatic episode runner, residual settlement, verification runs.
- `PHASE1_WEEK_RUN.md` — week observation scope, stop conditions, Telegram, restart procedure, status.
- `PHASE1_INTEGRATION_RUNBOOK.md` — ledger/risk/Nautilus connection notes and remaining conditions.
- `PHASE1_MATCHING_PROBE.md` — the bounded accept-and-cancel order probe.

## Phase 2 (perp-only market-neutral basket research)

- `PHASE2_PREREGISTRATION.md` — frozen hypotheses, universe, costs, validation, gates.
- Results: `../research_results/phase2/REPORT.md`, evidence in `../evidence/phase2/`.

## Phase 0 and research foundations

- `STRATEGY_PHASE0_FINAL.md`, `PHASE0_DEVELOPMENT.md`, `MILESTONE_1.md`
- `REPORTING_AND_RESEARCH.md` — Telegram reports and the weekly walk-forward (capital-basis metrics since 2026-09-15).
- `BLOCK_BOOTSTRAP.md`, `V2_BOOTSTRAP_PREREGISTRATION.md`, `V2_BOOTSTRAP_RESULTS.md`, `V2_COUNTERFACTUAL.md`

## Operations

- `SERVER_STATE.md` — dated server snapshots; newest on top.
- `DEPENDENCY_POLICY.md`, `MIGRATION_V2_TO_V3.md`
