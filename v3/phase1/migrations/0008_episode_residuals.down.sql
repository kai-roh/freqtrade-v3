BEGIN;
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM episode_residuals) THEN
        RAISE EXCEPTION 'archive settled residual evidence before rollback';
    END IF;
END $$;
ALTER TABLE episode_baselines DROP COLUMN inherited_residual_base;
DROP TABLE episode_residuals;
COMMIT;
