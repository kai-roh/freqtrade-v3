BEGIN;

DROP TABLE IF EXISTS internal_transfers;
DROP TABLE IF EXISTS state_transitions;
DROP TABLE IF EXISTS incidents;
DROP TABLE IF EXISTS reconciliation_runs;
DROP TABLE IF EXISTS funding_events;
DROP TABLE IF EXISTS positions;
DROP TABLE IF EXISTS fills;
DROP TABLE IF EXISTS orders;
DROP TABLE IF EXISTS order_commands;
DROP TABLE IF EXISTS quote_observations;
DROP TABLE IF EXISTS instrument_snapshots;
DROP TABLE IF EXISTS risk_decisions;
DROP TABLE IF EXISTS cost_ledger_entries;
DROP TABLE IF EXISTS intents;

COMMIT;
