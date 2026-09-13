BEGIN;
-- Dropping dispatch evidence could permit duplicate submissions after restart.
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM order_dispatches) THEN
        RAISE EXCEPTION 'archive and reconcile dispatch evidence before rollback';
    END IF;
END $$;
DROP TABLE IF EXISTS order_dispatches;
COMMIT;
