BEGIN;
-- Audited settlement of sub-minimum-order Spot inventory after both legs are
-- otherwise flat. A settled residual stays owned by the account, is recorded as
-- realized cost, and is inherited by the next episode baseline. It is never
-- treated as an unexplained reconciliation error and never sold below lot size.
CREATE TABLE episode_residuals (
    intent_id UUID PRIMARY KEY REFERENCES intents(id),
    residual_base NUMERIC NOT NULL CHECK (residual_base > 0),
    residual_mark_usdt NUMERIC NOT NULL CHECK (residual_mark_usdt >= 0),
    reason TEXT NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL,
    evidence JSONB NOT NULL
);
ALTER TABLE episode_baselines
    ADD COLUMN inherited_residual_base NUMERIC NOT NULL DEFAULT 0
        CHECK (inherited_residual_base >= 0);
COMMIT;
