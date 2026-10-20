BEGIN;
CREATE TABLE episode_baselines (
    intent_id UUID PRIMARY KEY REFERENCES intents(id),
    spot_base NUMERIC NOT NULL CHECK (spot_base >= 0),
    observed_at TIMESTAMPTZ NOT NULL,
    close_requested_at TIMESTAMPTZ,
    evidence JSONB NOT NULL
);
COMMIT;
