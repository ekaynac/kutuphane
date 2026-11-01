-- Astra review #22 finding 1: D73 (the decider and delegated curate) is removed (#179), but an existing
-- `kutuphane_decider` role kept its grants: it could still write suggestions and delegation uses, and the
-- SECURITY DEFINER trigger of migration 025 approved a note for each unsampled use under a live delegation. The
-- tables of migration 025 are history now: no role writes a new row, and the decider role loses every right.
CREATE FUNCTION d73_history_only() RETURNS trigger LANGUAGE plpgsql
SET search_path = pg_catalog, public, pg_temp AS $$
BEGIN
    RAISE EXCEPTION '% is history: delegated curate (D73) is removed', TG_TABLE_NAME;
END $$;
-- Per row: a trigger of migration 025 on standing_event runs an INSERT … SELECT into delegation_end that adds no row. The
-- name starts with `a_` so that this refusal fires before the other BEFORE triggers of these tables.
CREATE TRIGGER a_d73_history_only BEFORE INSERT OR UPDATE OR DELETE ON note_suggestion
    FOR EACH ROW EXECUTE FUNCTION d73_history_only();
CREATE TRIGGER a_d73_history_only BEFORE INSERT OR UPDATE OR DELETE ON curate_delegation
    FOR EACH ROW EXECUTE FUNCTION d73_history_only();
CREATE TRIGGER a_d73_history_only BEFORE INSERT OR UPDATE OR DELETE ON delegation_use
    FOR EACH ROW EXECUTE FUNCTION d73_history_only();
CREATE TRIGGER a_d73_history_only BEFORE INSERT OR UPDATE OR DELETE ON delegation_end
    FOR EACH ROW EXECUTE FUNCTION d73_history_only();

-- The two read functions of the decider role (migration 029, 038): nobody calls them.
DROP FUNCTION decider_notes(text[], text, bytea, integer, integer, bigint);
DROP FUNCTION delegation_next(text);

DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'kutuphane_decider') THEN
        REVOKE ALL ON ALL TABLES IN SCHEMA public FROM kutuphane_decider;
        REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM kutuphane_decider;
        REVOKE ALL ON ALL FUNCTIONS IN SCHEMA public FROM kutuphane_decider;
        REVOKE ALL ON SCHEMA public FROM kutuphane_decider;
    END IF;
END $$;
