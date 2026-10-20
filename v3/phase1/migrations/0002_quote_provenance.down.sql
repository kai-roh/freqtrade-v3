BEGIN;

ALTER TABLE quote_observations
    DROP CONSTRAINT quote_observations_timestamp_consistency,
    DROP COLUMN timestamp_source,
    DROP COLUMN transport_rtt_ms,
    ALTER COLUMN venue_timestamp SET NOT NULL,
    ALTER COLUMN age_ms SET NOT NULL;

COMMIT;
