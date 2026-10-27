-- Security review #17 (docs/25 §4.7): the database enforces the D73 sample against the decider runner role, the
-- decider role reads note text only through a gate, a live confirmation is replaced only by its confirmer (R7), and a
-- delegation end by an act names that act.

CREATE EXTENSION IF NOT EXISTS pgcrypto;   -- hmac(), gen_random_bytes()

-- A right that a principal holds directly: a tuple, or membership in a role that holds it (authz.direct in SQL).
CREATE FUNCTION holds_direct(p_principal text, p_object text, p_mode text) RETURNS boolean
LANGUAGE sql STABLE SET search_path = public, pg_temp AS $$
    SELECT EXISTS (
        SELECT 1 FROM grant_tuple g
          LEFT JOIN grant_tuple mem ON mem.relation = 'member' AND mem.subject = p_principal
               AND mem.revoked_at IS NULL AND g.subject = mem.object || '#member'
         WHERE g.object = p_object AND g.relation = p_mode AND g.revoked_at IS NULL
           AND (g.subject = p_principal OR mem.id IS NOT NULL))
$$;

-- The secret of the sample draw. Only the owner reads it (the deploy scripts revoke it from every login role); the
-- draw is computed in the SECURITY DEFINER trigger below, so no role can compute a draw in advance.
CREATE TABLE delegation_sample_key (
    one boolean PRIMARY KEY DEFAULT true CHECK (one),
    key bytea NOT NULL CHECK (octet_length(key) = 32)
);
INSERT INTO delegation_sample_key (key) VALUES (gen_random_bytes(32));
REVOKE ALL ON delegation_sample_key FROM PUBLIC;

-- A suggestion takes its seq and time from the database, under the memory lock (notes.MEMORY_LOCK), and only before
-- any Standing event of its note (§6.4): a late suggestion with a low seq cannot count as shadow evidence (§8.7).
CREATE FUNCTION note_suggestion_check() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    PERFORM pg_advisory_xact_lock(461532067184);
    NEW.seq := nextval('memory_seq');
    NEW.at := now();
    IF EXISTS (SELECT 1 FROM standing_event WHERE note_seq = NEW.note_seq) THEN
        RAISE EXCEPTION 'note % has a Standing event: a suggestion comes before any decision', NEW.note_seq;
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER note_suggestion_check BEFORE INSERT ON note_suggestion
    FOR EACH ROW EXECUTE FUNCTION note_suggestion_check();

-- A suggestion of this transaction: its xmin (the top transaction) or its time (a savepoint has its own xmin, but
-- `at` is the transaction start, set by note_suggestion_check).
CREATE FUNCTION suggestion_of_this_transaction(p_xmin xid, p_at timestamptz) RETURNS boolean
LANGUAGE sql STABLE AS $$
    SELECT coalesce(p_xmin = pg_current_xact_id_if_assigned()::xid, false) OR p_at >= now()
$$;

-- The note text that the decider runner may send to its model (§8.3 step 1, review #17 finding 5): the undecided
-- notes of the books where the runner's principal (`agent:kutuphane-decider`, decider.PRINCIPAL) holds `read`
-- directly or that have a live delegation, with no suggestion of this decider and spec, through the text gate:
-- `ai_input` of the note and of its journal, and no skill block (D71). `p_seq`: only this note (the check again just
-- before the model call).
CREATE FUNCTION decider_notes(p_books text[], p_decider text, p_spec bytea, p_max_chars integer, p_limit integer,
                              p_seq bigint)
RETURNS TABLE (seq bigint, book text, id text, kind text, body text, scope_repo text, scope_branch text,
               scope_paths text[], options text[], choice text, source_books text[])
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $$
    SELECT n.seq, n.book, n.id, n.kind, n.body, n.scope_repo, n.scope_branch, n.scope_paths, n.options, n.choice,
           n.source_books
      FROM note n JOIN note_journal j ON j.seq = n.seq
     WHERE n.book = ANY(p_books) AND (p_seq IS NULL OR n.seq = p_seq)
       AND (holds_direct('agent:kutuphane-decider', 'book:' || n.book, 'read')
            OR EXISTS (SELECT 1 FROM curate_delegation d
                        WHERE d.book = n.book AND clock_timestamp() < d.expires_at
                          AND NOT EXISTS (SELECT 1 FROM delegation_end e WHERE e.delegation = d.id)))
       AND NOT EXISTS (SELECT 1 FROM standing_event e WHERE e.note_seq = n.seq)
       AND NOT EXISTS (SELECT 1 FROM note_suggestion s WHERE s.note_seq = n.seq AND s.decider = p_decider
                                                         AND s.spec_sha256 = p_spec)
       AND n.ai_input AND j.ai_input AND NOT note_skill_blocked(n.seq)
       AND char_length(n.body) <= p_max_chars
     ORDER BY n.seq
     LIMIT p_limit
$$;
REVOKE EXECUTE ON FUNCTION decider_notes(text[], text, bytea, integer, integer, bigint) FROM PUBLIC;

-- The note that the next use of a delegation must take (§8.3 phase 2): the OLDEST note of its class with a committed
-- suggestion of its decider and spec at or over the threshold, no use, no Standing event, no contradiction, through
-- the text gate, and with no propose write by the runner's principal. The runner cannot skip a note.
CREATE FUNCTION delegation_next(p_delegation text) RETURNS TABLE (note_seq bigint, ref text, suggestion bigint)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $$
    SELECT n.seq, n.book || '@' || n.id, s.seq
      FROM curate_delegation d
      JOIN note n ON n.book = d.book AND n.kind = d.kind
      JOIN note_journal j ON j.seq = n.seq
      JOIN note_suggestion s ON s.note_seq = n.seq AND s.decider = d.decider AND s.spec_sha256 = d.spec_sha256
     WHERE d.id = p_delegation AND s.value = 'approved' AND s.confidence >= d.min_confidence
       AND NOT suggestion_of_this_transaction(s.xmin, s.at)
       AND NOT EXISTS (SELECT 1 FROM delegation_use u WHERE u.note_seq = n.seq)
       AND NOT EXISTS (SELECT 1 FROM standing_event e WHERE e.note_seq = n.seq)
       AND NOT EXISTS (SELECT 1 FROM note_link l WHERE l.type = 'contradicts' AND (l.src = n.seq OR l.dst_note = n.seq))
       AND n.ai_input AND j.ai_input AND NOT note_skill_blocked(n.seq)
       AND NOT EXISTS (SELECT 1 FROM write_record w
                        WHERE w.note_seq = n.seq AND w.action = 'propose'
                          AND w.principal IN ('agent:kutuphane-decider',
                                              (SELECT c.principal FROM model_call c WHERE c.id = s.model_call)))
     ORDER BY n.seq
     LIMIT 1
$$;
REVOKE EXECUTE ON FUNCTION delegation_next(text) FROM PUBLIC;

-- The use check, now SECURITY DEFINER (it reads the note and the key that the decider role cannot read). Against the
-- runner role: the database sets seq, at and sampled (also column grants, deploy/db-roles-decider.sql); the use is of
-- the next note (no skipping) and of a committed suggestion; the creator still holds `curate`; no propose write by
-- the runner's principal; the draw is an HMAC of (delegation, note) under the secret key, so a retry after a rollback
-- draws the same.
CREATE OR REPLACE FUNCTION delegation_use_check() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER
SET search_path = public, pg_temp AS $$
DECLARE
    d curate_delegation;
    s note_suggestion;
    s_xmin xid;
    next_note bigint;
    open_samples integer;
    last_verdict bigint;
    run integer;
    draw bigint;
BEGIN
    PERFORM pg_advisory_xact_lock(461532067184);   -- notes.MEMORY_LOCK: the counts below cannot race
    NEW.seq := nextval('memory_seq');
    NEW.at := now();
    SELECT * INTO d FROM curate_delegation WHERE id = NEW.delegation;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'no delegation %', NEW.delegation;
    END IF;
    IF clock_timestamp() >= d.expires_at OR EXISTS (SELECT 1 FROM delegation_end WHERE delegation = d.id) THEN
        RAISE EXCEPTION 'delegation % is not live', d.id;
    END IF;
    IF NOT holds_direct(d.created_by, 'book:' || d.book, 'curate') THEN
        RAISE EXCEPTION '% no longer holds curate on book:%', d.created_by, d.book;
    END IF;
    SELECT * INTO s FROM note_suggestion WHERE seq = NEW.suggestion;
    SELECT xmin INTO s_xmin FROM note_suggestion WHERE seq = NEW.suggestion;
    IF s.value <> 'approved' OR s.confidence < d.min_confidence THEN
        RAISE EXCEPTION 'suggestion % is under the delegation threshold', s.seq;
    END IF;
    IF suggestion_of_this_transaction(s_xmin, s.at) THEN
        RAISE EXCEPTION 'suggestion % is not committed before its use', s.seq;
    END IF;
    IF EXISTS (SELECT 1 FROM standing_event WHERE note_seq = NEW.note_seq) THEN
        RAISE EXCEPTION 'note % has a Standing event: a person decides it', NEW.note_seq;
    END IF;
    IF EXISTS (SELECT 1 FROM note_link WHERE type = 'contradicts' AND (src = NEW.note_seq OR dst_note = NEW.note_seq)) THEN
        RAISE EXCEPTION 'note % is in a contradiction: a person decides it', NEW.note_seq;
    END IF;
    IF NOT (SELECT n.ai_input AND j.ai_input FROM note n JOIN note_journal j USING (seq) WHERE n.seq = NEW.note_seq)
       OR note_skill_blocked(NEW.note_seq) THEN
        RAISE EXCEPTION 'the text of note % may not go to a model', NEW.note_seq;
    END IF;
    IF EXISTS (SELECT 1 FROM write_record w
                WHERE w.note_seq = NEW.note_seq AND w.action = 'propose'
                  AND w.principal IN ('agent:kutuphane-decider',
                                      (SELECT c.principal FROM model_call c WHERE c.id = s.model_call))) THEN
        RAISE EXCEPTION 'note % has a propose write by the runner''s principal', NEW.note_seq;
    END IF;
    SELECT x.note_seq INTO next_note FROM delegation_next(d.id) x;
    IF next_note IS DISTINCT FROM NEW.note_seq THEN
        RAISE EXCEPTION 'note % is not the next note of delegation %: a use takes the oldest eligible note (%)',
            NEW.note_seq, d.id, coalesce(next_note::text, 'none');
    END IF;
    SELECT count(*) INTO open_samples FROM delegation_use u
     WHERE u.delegation = d.id AND u.sampled AND NOT EXISTS (SELECT 1 FROM standing_event e WHERE e.note_seq = u.note_seq);
    IF open_samples >= 3 THEN
        RAISE EXCEPTION 'delegation % waits for 3 open samples', d.id;
    END IF;
    -- forced sample: at most 2N unsampled uses after the last human verdict on a sample
    SELECT max(u.seq) INTO last_verdict FROM delegation_use u
     WHERE u.delegation = d.id AND u.sampled
       AND EXISTS (SELECT 1 FROM standing_event e WHERE e.note_seq = u.note_seq AND e.set_by LIKE 'user:%');
    SELECT count(*) INTO run FROM delegation_use u
     WHERE u.delegation = d.id AND NOT u.sampled AND u.seq > coalesce(last_verdict, 0);
    SELECT ('x' || encode(substr(hmac(convert_to(d.id || ':' || NEW.note_seq, 'UTF8'), k.key, 'sha256'), 1, 4),
                          'hex'))::bit(32)::bigint
      INTO draw FROM delegation_sample_key k;
    NEW.sampled := run >= 2 * d.sample_every OR draw % d.sample_every = 0;
    RETURN NEW;
END $$;

-- R7: a live confirmation is replaced only by its confirmer; another person's confirmation needs the confirmer's
-- withdrawal first. This also holds for a request that a reader opens by proposing the same bytes again.
CREATE FUNCTION origin_confirmation_by_confirmer() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    live_by text;
BEGIN
    PERFORM pg_advisory_xact_lock(461532067184);   -- notes.MEMORY_LOCK
    SELECT c.confirmed_by INTO live_by FROM origin_confirmation c
     WHERE c.seq = (SELECT max(seq) FROM origin_confirmation WHERE note_seq = NEW.note_seq)
       AND NOT EXISTS (SELECT 1 FROM origin_withdrawal x WHERE x.confirmation = c.seq);
    IF live_by IS NOT NULL AND live_by <> NEW.confirmed_by THEN
        RAISE EXCEPTION 'note % has a live confirmation by %: only the confirmer withdraws it (R7)',
            NEW.note_seq, live_by;
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER origin_confirmation_by_confirmer BEFORE INSERT ON origin_confirmation
    FOR EACH ROW EXECUTE FUNCTION origin_confirmation_by_confirmer();

-- An end by an act is the end of that act's signer, by an `end_delegation` act (as the other act-bound rows).
ALTER TABLE delegation_end
    ADD COLUMN act_action text GENERATED ALWAYS AS (CASE WHEN act IS NOT NULL THEN 'end_delegation' END) STORED,
    ADD FOREIGN KEY (act, act_action) REFERENCES curator_act (seq, action),
    ADD FOREIGN KEY (act, ended_by) REFERENCES curator_act (seq, principal);
