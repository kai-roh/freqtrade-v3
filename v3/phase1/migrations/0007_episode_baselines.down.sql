BEGIN;
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM episode_baselines) THEN
        RAISE EXCEPTION 'archive episode inventory evidence before rollback';
    END IF;
END $$;
DROP TABLE episode_baselines;
COMMIT;
