-- Astra review #19 finding 2 (D70 R3, docs/24 §3, §6.3, docs/25 §5.2): the canonical parts of a note are fixed
-- when the note is written. The note id is the SHA-256 of the canonical body, and the body holds the citations and
-- the creation links, so a person who confirms or approves a note signs exactly these parts. Before, the app role
-- (INSERT without UPDATE or DELETE) could append a citation, or a creation link of the original creating write, to a
-- confirmed note: the stored id stayed and the shown origin stayed `human`. Now a citation or a creation link is
-- written only in the transaction that wrote its note (also from a savepoint of it). A later link (`creation =
-- false`, its own `link` write) is not part of the body and stays possible (§6.3).

-- The transaction that wrote the note: set by the database, never by the writer (the app has no UPDATE on note).
-- A savepoint has the same top-level id. Notes written before this migration have none: they take no new parts.
ALTER TABLE note ADD COLUMN written_xact xid8;

CREATE FUNCTION note_written_xact() RETURNS trigger LANGUAGE plpgsql
SET search_path = pg_catalog, public, pg_temp AS $$
BEGIN
    NEW.written_xact := pg_current_xact_id();
    RETURN NEW;
END $$;
CREATE TRIGGER note_written_xact BEFORE INSERT ON note
    FOR EACH ROW EXECUTE FUNCTION note_written_xact();

CREATE FUNCTION note_part_at_creation(p_seq bigint) RETURNS void LANGUAGE plpgsql
SET search_path = pg_catalog, public, pg_temp AS $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM public.note WHERE seq = p_seq AND written_xact = pg_current_xact_id()) THEN
        RAISE EXCEPTION 'note % is written: its citations and creation links are part of its id and are fixed', p_seq;
    END IF;
END $$;

CREATE FUNCTION note_citation_at_creation() RETURNS trigger LANGUAGE plpgsql
SET search_path = pg_catalog, public, pg_temp AS $$
BEGIN
    PERFORM public.note_part_at_creation(NEW.note_seq);
    RETURN NEW;
END $$;
CREATE TRIGGER note_citation_at_creation BEFORE INSERT ON note_citation
    FOR EACH ROW EXECUTE FUNCTION note_citation_at_creation();

CREATE FUNCTION note_link_at_creation() RETURNS trigger LANGUAGE plpgsql
SET search_path = pg_catalog, public, pg_temp AS $$
BEGIN
    PERFORM public.note_part_at_creation(NEW.src);
    RETURN NEW;
END $$;
CREATE TRIGGER note_link_at_creation BEFORE INSERT ON note_link
    FOR EACH ROW WHEN (NEW.creation) EXECUTE FUNCTION note_link_at_creation();
