BEGIN;
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM order_recovery_checks) THEN
        RAISE EXCEPTION 'archive and reconcile recovery evidence before rollback';
    END IF;
END $$;
DROP TABLE order_recovery_checks;
COMMIT;
