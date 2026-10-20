BEGIN;
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM fill_event_inbox) THEN
        RAISE EXCEPTION 'archive and reconcile fill inbox before rollback';
    END IF;
END $$;
DROP TABLE IF EXISTS fill_event_inbox;
COMMIT;
