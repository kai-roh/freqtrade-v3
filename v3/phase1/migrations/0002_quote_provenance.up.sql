BEGIN;

ALTER TABLE quote_observations
    ALTER COLUMN venue_timestamp DROP NOT NULL,
    ALTER COLUMN age_ms DROP NOT NULL,
    ADD COLUMN transport_rtt_ms BIGINT CHECK (transport_rtt_ms IS NULL OR transport_rtt_ms >= 0),
    ADD COLUMN timestamp_source TEXT NOT NULL DEFAULT 'exchange_event'
        CHECK (timestamp_source IN ('exchange_event', 'rest_received_at', 'unavailable'));

ALTER TABLE quote_observations
    ADD CONSTRAINT quote_observations_timestamp_consistency
        CHECK (
            (timestamp_source = 'exchange_event' AND venue_timestamp IS NOT NULL AND age_ms IS NOT NULL)
            OR (timestamp_source IN ('rest_received_at', 'unavailable') AND venue_timestamp IS NULL AND age_ms IS NULL)
        );

COMMIT;
