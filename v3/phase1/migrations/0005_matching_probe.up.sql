BEGIN;
CREATE TABLE demo_matching_probes (
    id VARCHAR(32) PRIMARY KEY,
    source_sha CHAR(40) NOT NULL,
    image_digest TEXT NOT NULL,
    product TEXT NOT NULL CHECK (product IN ('spot', 'perp')),
    payload JSONB NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('RESERVED','CANCEL_PENDING','CANCELED','BLOCKED')),
    report JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);
COMMIT;
