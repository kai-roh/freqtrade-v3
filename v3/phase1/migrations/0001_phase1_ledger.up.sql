BEGIN;

CREATE TABLE intents (
    id UUID PRIMARY KEY,
    run_manifest_id CHAR(64) NOT NULL,
    cost_ledger_id CHAR(64) NOT NULL,
    strategy_id TEXT NOT NULL,
    target_notional NUMERIC NOT NULL CHECK (target_notional > 0),
    state TEXT NOT NULL,
    entry_reason TEXT NOT NULL,
    target_position TEXT NOT NULL,
    normal_exit TEXT NOT NULL,
    risk_exit TEXT NOT NULL,
    max_holding_or_review_at TIMESTAMPTZ NOT NULL,
    cost_and_risk_budget JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE cost_ledger_entries (
    id UUID PRIMARY KEY,
    intent_id UUID NOT NULL REFERENCES intents(id),
    cost_ledger_id CHAR(64) NOT NULL,
    category TEXT NOT NULL,
    expected_amount NUMERIC,
    realized_amount NUMERIC,
    currency TEXT NOT NULL,
    basis TEXT NOT NULL,
    source TEXT NOT NULL,
    observed_at TIMESTAMPTZ,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE risk_decisions (
    id UUID PRIMARY KEY,
    intent_id UUID NOT NULL REFERENCES intents(id),
    approved BOOLEAN NOT NULL,
    reasons JSONB NOT NULL,
    observed_leverage JSONB NOT NULL,
    quote_age_ms BIGINT,
    exposure_before NUMERIC NOT NULL,
    exposure_after NUMERIC NOT NULL,
    decision_latency_ms BIGINT NOT NULL CHECK (decision_latency_ms >= 0),
    decided_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE instrument_snapshots (
    id UUID PRIMARY KEY,
    venue TEXT NOT NULL,
    instrument_id TEXT NOT NULL,
    raw_symbol TEXT NOT NULL,
    price_precision INTEGER NOT NULL,
    size_precision INTEGER NOT NULL,
    minimum_notional NUMERIC NOT NULL CHECK (minimum_notional > 0),
    tick_size NUMERIC NOT NULL CHECK (tick_size > 0),
    lot_size NUMERIC NOT NULL CHECK (lot_size > 0),
    status TEXT NOT NULL,
    content_hash CHAR(64) NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL,
    UNIQUE (venue, instrument_id, content_hash)
);

CREATE TABLE quote_observations (
    id UUID PRIMARY KEY,
    instrument_snapshot_id UUID NOT NULL REFERENCES instrument_snapshots(id),
    bid NUMERIC NOT NULL CHECK (bid > 0),
    ask NUMERIC NOT NULL CHECK (ask >= bid),
    venue_timestamp TIMESTAMPTZ NOT NULL,
    received_at TIMESTAMPTZ NOT NULL,
    age_ms BIGINT NOT NULL CHECK (age_ms >= 0),
    collection_mode TEXT NOT NULL CHECK (collection_mode IN ('risk_decision', 'phase1e_sample'))
);

CREATE TABLE order_commands (
    id UUID PRIMARY KEY,
    intent_id UUID NOT NULL REFERENCES intents(id),
    leg TEXT NOT NULL CHECK (leg IN ('spot', 'perp')),
    attempt INTEGER NOT NULL CHECK (attempt >= 0),
    idempotency_key VARCHAR(32) NOT NULL UNIQUE,
    instrument_id TEXT NOT NULL,
    side TEXT NOT NULL CHECK (side IN ('buy', 'sell')),
    order_type TEXT NOT NULL,
    quantity NUMERIC NOT NULL CHECK (quantity > 0),
    price NUMERIC CHECK (price > 0),
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE UNIQUE INDEX one_active_command_per_intent_leg
    ON order_commands (intent_id, leg)
    WHERE active;

CREATE TABLE orders (
    id UUID PRIMARY KEY,
    command_id UUID NOT NULL UNIQUE REFERENCES order_commands(id),
    venue TEXT NOT NULL,
    venue_order_id TEXT,
    client_order_id VARCHAR(32) NOT NULL,
    status TEXT NOT NULL,
    filled_quantity NUMERIC NOT NULL DEFAULT 0 CHECK (filled_quantity >= 0),
    average_price NUMERIC,
    reject_code TEXT,
    updated_at TIMESTAMPTZ NOT NULL,
    UNIQUE (venue, venue_order_id)
);

CREATE TABLE fills (
    id UUID PRIMARY KEY,
    order_id UUID NOT NULL REFERENCES orders(id),
    venue TEXT NOT NULL,
    venue_fill_id TEXT NOT NULL,
    quantity NUMERIC NOT NULL CHECK (quantity > 0),
    price NUMERIC NOT NULL CHECK (price > 0),
    fee_amount NUMERIC NOT NULL,
    fee_token TEXT NOT NULL,
    liquidity_side TEXT,
    liquidation_type TEXT,
    filled_at TIMESTAMPTZ NOT NULL,
    UNIQUE (venue, venue_fill_id)
);

CREATE TABLE positions (
    id UUID PRIMARY KEY,
    intent_id UUID REFERENCES intents(id),
    venue TEXT NOT NULL,
    instrument_id TEXT NOT NULL,
    source TEXT NOT NULL CHECK (source IN ('venue', 'local')),
    quantity NUMERIC NOT NULL,
    notional NUMERIC NOT NULL,
    leverage NUMERIC NOT NULL CHECK (leverage > 0),
    margin_amount NUMERIC,
    liquidation_price NUMERIC,
    observed_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE funding_events (
    id UUID PRIMARY KEY,
    intent_id UUID REFERENCES intents(id),
    instrument_id TEXT NOT NULL,
    interval_minutes INTEGER NOT NULL CHECK (interval_minutes > 0),
    funding_rate NUMERIC NOT NULL,
    expected_amount NUMERIC,
    realized_amount NUMERIC,
    settlement_at TIMESTAMPTZ NOT NULL,
    source TEXT NOT NULL
);

CREATE TABLE reconciliation_runs (
    id UUID PRIMARY KEY,
    intent_id UUID REFERENCES intents(id),
    explained_residual NUMERIC NOT NULL,
    unexplained_residual NUMERIC NOT NULL,
    currency TEXT NOT NULL,
    result TEXT NOT NULL,
    detail JSONB NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ
);

CREATE TABLE incidents (
    id UUID PRIMARY KEY,
    intent_id UUID REFERENCES intents(id),
    category TEXT NOT NULL,
    severity TEXT NOT NULL,
    status TEXT NOT NULL,
    detail TEXT NOT NULL,
    opened_at TIMESTAMPTZ NOT NULL,
    resolved_at TIMESTAMPTZ,
    resolution_evidence TEXT
);

CREATE TABLE state_transitions (
    id UUID PRIMARY KEY,
    intent_id UUID NOT NULL REFERENCES intents(id),
    from_state TEXT,
    to_state TEXT NOT NULL,
    trigger TEXT NOT NULL,
    guard_results JSONB NOT NULL,
    accepted BOOLEAN NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE internal_transfers (
    id UUID PRIMARY KEY,
    intent_id UUID NOT NULL REFERENCES intents(id),
    asset TEXT NOT NULL,
    amount NUMERIC NOT NULL CHECK (amount > 0),
    from_wallet TEXT NOT NULL,
    to_wallet TEXT NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE,
    requested_at TIMESTAMPTZ NOT NULL,
    confirmed_at TIMESTAMPTZ,
    status TEXT NOT NULL CHECK (status IN ('requested', 'confirmed', 'failed')),
    venue_transfer_id TEXT,
    failure_reason TEXT
);

COMMIT;
