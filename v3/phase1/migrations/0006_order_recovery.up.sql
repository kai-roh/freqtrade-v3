BEGIN;
CREATE TABLE order_recovery_checks (
    id UUID PRIMARY KEY,
    command_id UUID NOT NULL REFERENCES order_commands(id),
    status TEXT NOT NULL CHECK (status IN ('PENDING','APPLIED','BLOCKED','RESOLVED')),
    snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
    error_type TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    completed_at TIMESTAMPTZ
);
COMMIT;
