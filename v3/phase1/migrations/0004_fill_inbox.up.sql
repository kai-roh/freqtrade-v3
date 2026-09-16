BEGIN;
CREATE TABLE fill_event_inbox (
    id UUID PRIMARY KEY,
    payload JSONB NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('PENDING','APPLIED','BLOCKED')),
    received_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    processed_at TIMESTAMPTZ,
    error_type TEXT
);
COMMIT;
