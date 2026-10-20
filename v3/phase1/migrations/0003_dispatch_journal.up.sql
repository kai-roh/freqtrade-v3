BEGIN;
CREATE TABLE order_dispatches (
    command_id UUID PRIMARY KEY REFERENCES order_commands(id),
    risk_decision_id UUID NOT NULL REFERENCES risk_decisions(id),
    client_order_id VARCHAR(32) NOT NULL UNIQUE,
    payload JSONB NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('CLAIMED', 'ENQUEUED', 'UNKNOWN', 'OBSERVED')),
    claimed_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    error_type TEXT
);
COMMIT;
