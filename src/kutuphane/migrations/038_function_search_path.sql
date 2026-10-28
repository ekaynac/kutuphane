-- Astra review #19 finding 1: every function and trigger function of migrations 016–037 pins its search path and
-- names its objects with their schema. Before, a function without `SET search_path` resolved `standing_event` and
-- `memory_seq` through the caller's path, where PostgreSQL looks in the session's temporary schema first: a decider
-- role with the default TEMP right could shadow them (an empty temporary `standing_event`, a temporary `memory_seq`
-- that gives negative numbers) and write a suggestion after a person's verdict that counts as earlier shadow
-- evidence (docs/25 §8.7). Now the path is `pg_catalog, public, pg_temp`: the temporary schema is last (PostgreSQL
-- searches it first when the path does not name it), and every relation, sequence, type and function of ours is
-- `public.`-qualified. The deploy scripts also revoke TEMP (deploy/db-roles*.sql). Each body is the one of its last
-- migration (021, 022, 023, 024, 025, 026, 029), with no other change.

CREATE OR REPLACE FUNCTION skill_blocked(p_book text, p_content text, p_path text) RETURNS boolean
LANGUAGE sql STABLE SET search_path = pg_catalog, public, pg_temp AS $$
    SELECT EXISTS (SELECT 1 FROM public.skill_block b
                    WHERE b.book = p_book AND b.content_id = p_content
                      AND (b.skill_path = '.' OR starts_with(p_path, b.skill_path || '/')))
$$;

CREATE OR REPLACE FUNCTION note_skill_blocked(p_seq bigint) RETURNS boolean
LANGUAGE sql STABLE SET search_path = pg_catalog, public, pg_temp AS $$
    WITH RECURSIVE dep(seq) AS (
        SELECT p_seq
        UNION
        SELECT l.dst_note FROM public.note_link l JOIN dep ON l.src = dep.seq
         WHERE l.type = 'derived_from' AND l.dst_note IS NOT NULL)
    SELECT EXISTS (SELECT 1 FROM dep JOIN public.note_citation c ON c.note_seq = dep.seq
                    WHERE c.kind = 'passage' AND public.skill_blocked(c.cite_book, c.content_id, c.path))
        OR EXISTS (SELECT 1 FROM dep JOIN public.note_link l ON l.src = dep.seq
                    WHERE l.type = 'derived_from' AND l.dst_book IS NOT NULL
                      AND public.skill_blocked(l.dst_book, l.dst_content_id, l.dst_path))
$$;

CREATE OR REPLACE FUNCTION passkey_enrollment_live() RETURNS trigger LANGUAGE plpgsql
SET search_path = pg_catalog, public, pg_temp AS $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM public.curator_enrollment
                    WHERE id = NEW.enrollment AND clock_timestamp() < expires_at AND cancelled_at IS NULL) THEN
        RAISE EXCEPTION 'enrollment % is not live', NEW.enrollment;
    END IF;
    RETURN NEW;
END $$;

CREATE OR REPLACE FUNCTION standing_event_in_statement() RETURNS trigger LANGUAGE plpgsql
SET search_path = pg_catalog, public, pg_temp AS $$
BEGIN
    IF NEW.act IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM public.curator_act a
          JOIN public.curator_challenge c ON c.id = a.challenge
          JOIN public.note n ON n.seq = NEW.note_seq
         CROSS JOIN jsonb_array_elements(c.payload -> 'items') i
         WHERE a.seq = NEW.act AND i ->> 'ref' = n.book || '@' || n.id AND i ->> 'to' = NEW.value
           AND c.payload ->> 'reason' = NEW.reason) THEN
        RAISE EXCEPTION 'event is not in the statement of act %', NEW.act;
    END IF;
    RETURN NEW;
END $$;

CREATE OR REPLACE FUNCTION origin_confirmation_in_statement() RETURNS trigger LANGUAGE plpgsql
SET search_path = pg_catalog, public, pg_temp AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM public.curator_act a JOIN public.curator_challenge c ON c.id = a.challenge
         WHERE a.seq = NEW.act AND c.payload #>> '{item,ref}' = NEW.book || '@' || NEW.note_id
           AND (c.payload #>> '{item,write}')::bigint = NEW.write_seq AND c.payload ->> 'claim' = NEW.claim
           AND c.payload ->> 'entered_by' = NEW.entered_by) THEN
        RAISE EXCEPTION 'confirmation is not the statement of act %', NEW.act;
    END IF;
    RETURN NEW;
END $$;

CREATE OR REPLACE FUNCTION curate_delegation_in_statement() RETURNS trigger LANGUAGE plpgsql
SET search_path = pg_catalog, public, pg_temp AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM public.curator_act a JOIN public.curator_challenge c ON c.id = a.challenge
         WHERE a.seq = NEW.act AND c.payload #>> '{delegation,id}' = NEW.id
           AND c.payload #>> '{delegation,book}' = NEW.book AND c.payload #>> '{delegation,kind}' = NEW.kind
           AND c.payload #>> '{delegation,decider}' = NEW.decider
           AND c.payload #>> '{delegation,spec_sha256}' = encode(NEW.spec_sha256, 'hex')
           AND (c.payload #>> '{delegation,min_confidence}')::real = NEW.min_confidence
           AND (c.payload #>> '{delegation,sample_every}')::integer = NEW.sample_every
           AND (c.payload #>> '{delegation,expires_at}')::timestamptz = NEW.expires_at) THEN
        RAISE EXCEPTION 'delegation is not the statement of act %', NEW.act;
    END IF;
    RETURN NEW;
END $$;

CREATE OR REPLACE FUNCTION delegation_use_approve() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp AS $$
BEGIN
    IF NOT NEW.sampled THEN
        INSERT INTO public.standing_event (note_seq, value, set_by, reason, correlation_id, delegation_use)
        VALUES (NEW.note_seq, 'approved', NEW.approver, 'delegated: ' || NEW.delegation, NEW.correlation_id, NEW.seq);
    END IF;
    RETURN NULL;
END $$;

CREATE OR REPLACE FUNCTION standing_event_sample_verdict() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp AS $$
BEGIN
    IF NEW.set_by LIKE 'user:%' AND NEW.value <> 'approved' THEN
        INSERT INTO public.delegation_end (delegation, cause, ended_by, event)
        SELECT u.delegation, 'disagreement', 'system', NEW.seq
          FROM public.delegation_use u
         WHERE u.note_seq = NEW.note_seq AND u.sampled
           AND NOT EXISTS (SELECT 1 FROM public.delegation_end e WHERE e.delegation = u.delegation)
           AND NOT EXISTS (SELECT 1 FROM public.standing_event p WHERE p.note_seq = NEW.note_seq AND p.seq < NEW.seq);
    END IF;
    RETURN NULL;
END $$;

CREATE OR REPLACE FUNCTION standing_event_retires_signed() RETURNS trigger LANGUAGE plpgsql
SET search_path = pg_catalog, public, pg_temp AS $$
DECLARE
    cause_act bigint;
BEGIN
    SELECT act INTO cause_act FROM public.standing_event WHERE seq = NEW.cause_seq;
    IF cause_act IS NULL THEN
        RETURN NEW;
    END IF;
    IF NEW.set_by <> 'system' OR NEW.value <> 'retired' OR NEW.act IS NOT NULL
       OR NOT EXISTS (SELECT 1 FROM public.standing_event c
                       WHERE c.seq = NEW.cause_seq AND c.xmin = pg_current_xact_id()::xid)
       OR NOT EXISTS (
            SELECT 1 FROM public.curator_act a
              JOIN public.curator_challenge ch ON ch.id = a.challenge
              JOIN public.note n ON n.seq = NEW.note_seq
             CROSS JOIN jsonb_array_elements(coalesce(ch.payload -> 'retires', '[]'::jsonb)) r
             WHERE a.seq = cause_act AND r ->> 'ref' = n.book || '@' || n.id AND r ->> 'id' = n.id) THEN
        RAISE EXCEPTION 'system event is not a retirement signed by act %', cause_act;
    END IF;
    RETURN NEW;
END $$;

CREATE OR REPLACE FUNCTION holds_direct(p_principal text, p_object text, p_mode text) RETURNS boolean
LANGUAGE sql STABLE SET search_path = pg_catalog, public, pg_temp AS $$
    SELECT EXISTS (
        SELECT 1 FROM public.grant_tuple g
          LEFT JOIN public.grant_tuple mem ON mem.relation = 'member' AND mem.subject = p_principal
               AND mem.revoked_at IS NULL AND g.subject = mem.object || '#member'
         WHERE g.object = p_object AND g.relation = p_mode AND g.revoked_at IS NULL
           AND (g.subject = p_principal OR mem.id IS NOT NULL))
$$;

CREATE OR REPLACE FUNCTION note_suggestion_check() RETURNS trigger LANGUAGE plpgsql
SET search_path = pg_catalog, public, pg_temp AS $$
BEGIN
    PERFORM pg_advisory_xact_lock(461532067184);
    NEW.seq := nextval('public.memory_seq'::regclass);
    NEW.at := now();
    IF EXISTS (SELECT 1 FROM public.standing_event WHERE note_seq = NEW.note_seq) THEN
        RAISE EXCEPTION 'note % has a Standing event: a suggestion comes before any decision', NEW.note_seq;
    END IF;
    RETURN NEW;
END $$;

CREATE OR REPLACE FUNCTION suggestion_of_this_transaction(p_xmin xid, p_at timestamptz) RETURNS boolean
LANGUAGE sql STABLE SET search_path = pg_catalog, public, pg_temp AS $$
    SELECT coalesce(p_xmin = pg_current_xact_id_if_assigned()::xid, false) OR p_at >= now()
$$;

CREATE OR REPLACE FUNCTION decider_notes(p_books text[], p_decider text, p_spec bytea, p_max_chars integer,
                                         p_limit integer, p_seq bigint)
RETURNS TABLE (seq bigint, book text, id text, kind text, body text, scope_repo text, scope_branch text,
               scope_paths text[], options text[], choice text, source_books text[])
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public, pg_temp AS $$
    SELECT n.seq, n.book, n.id, n.kind, n.body, n.scope_repo, n.scope_branch, n.scope_paths, n.options, n.choice,
           n.source_books
      FROM public.note n JOIN public.note_journal j ON j.seq = n.seq
     WHERE n.book = ANY(p_books) AND (p_seq IS NULL OR n.seq = p_seq)
       AND (public.holds_direct('agent:kutuphane-decider', 'book:' || n.book, 'read')
            OR EXISTS (SELECT 1 FROM public.curate_delegation d
                        WHERE d.book = n.book AND clock_timestamp() < d.expires_at
                          AND NOT EXISTS (SELECT 1 FROM public.delegation_end e WHERE e.delegation = d.id)))
       AND NOT EXISTS (SELECT 1 FROM public.standing_event e WHERE e.note_seq = n.seq)
       AND NOT EXISTS (SELECT 1 FROM public.note_suggestion s WHERE s.note_seq = n.seq AND s.decider = p_decider
                                                                AND s.spec_sha256 = p_spec)
       AND n.ai_input AND j.ai_input AND NOT public.note_skill_blocked(n.seq)
       AND char_length(n.body) <= p_max_chars
     ORDER BY n.seq
     LIMIT p_limit
$$;

CREATE OR REPLACE FUNCTION delegation_next(p_delegation text) RETURNS TABLE (note_seq bigint, ref text, suggestion bigint)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public, pg_temp AS $$
    SELECT n.seq, n.book || '@' || n.id, s.seq
      FROM public.curate_delegation d
      JOIN public.note n ON n.book = d.book AND n.kind = d.kind
      JOIN public.note_journal j ON j.seq = n.seq
      JOIN public.note_suggestion s ON s.note_seq = n.seq AND s.decider = d.decider AND s.spec_sha256 = d.spec_sha256
     WHERE d.id = p_delegation AND s.value = 'approved' AND s.confidence >= d.min_confidence
       AND NOT public.suggestion_of_this_transaction(s.xmin, s.at)
       AND NOT EXISTS (SELECT 1 FROM public.delegation_use u WHERE u.note_seq = n.seq)
       AND NOT EXISTS (SELECT 1 FROM public.standing_event e WHERE e.note_seq = n.seq)
       AND NOT EXISTS (SELECT 1 FROM public.note_link l
                        WHERE l.type = 'contradicts' AND (l.src = n.seq OR l.dst_note = n.seq))
       AND n.ai_input AND j.ai_input AND NOT public.note_skill_blocked(n.seq)
       AND NOT EXISTS (SELECT 1 FROM public.write_record w
                        WHERE w.note_seq = n.seq AND w.action = 'propose'
                          AND w.principal IN ('agent:kutuphane-decider',
                                              (SELECT c.principal FROM public.model_call c WHERE c.id = s.model_call)))
     ORDER BY n.seq
     LIMIT 1
$$;

CREATE OR REPLACE FUNCTION delegation_use_check() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp AS $$
DECLARE
    d public.curate_delegation;
    s public.note_suggestion;
    s_xmin xid;
    next_note bigint;
    open_samples integer;
    last_verdict bigint;
    run integer;
    draw bigint;
BEGIN
    PERFORM pg_advisory_xact_lock(461532067184);   -- notes.MEMORY_LOCK: the counts below cannot race
    NEW.seq := nextval('public.memory_seq'::regclass);
    NEW.at := now();
    SELECT * INTO d FROM public.curate_delegation WHERE id = NEW.delegation;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'no delegation %', NEW.delegation;
    END IF;
    IF clock_timestamp() >= d.expires_at OR EXISTS (SELECT 1 FROM public.delegation_end WHERE delegation = d.id) THEN
        RAISE EXCEPTION 'delegation % is not live', d.id;
    END IF;
    IF NOT public.holds_direct(d.created_by, 'book:' || d.book, 'curate') THEN
        RAISE EXCEPTION '% no longer holds curate on book:%', d.created_by, d.book;
    END IF;
    SELECT * INTO s FROM public.note_suggestion WHERE seq = NEW.suggestion;
    SELECT xmin INTO s_xmin FROM public.note_suggestion WHERE seq = NEW.suggestion;
    IF s.value <> 'approved' OR s.confidence < d.min_confidence THEN
        RAISE EXCEPTION 'suggestion % is under the delegation threshold', s.seq;
    END IF;
    IF public.suggestion_of_this_transaction(s_xmin, s.at) THEN
        RAISE EXCEPTION 'suggestion % is not committed before its use', s.seq;
    END IF;
    IF EXISTS (SELECT 1 FROM public.standing_event WHERE note_seq = NEW.note_seq) THEN
        RAISE EXCEPTION 'note % has a Standing event: a person decides it', NEW.note_seq;
    END IF;
    IF EXISTS (SELECT 1 FROM public.note_link
                WHERE type = 'contradicts' AND (src = NEW.note_seq OR dst_note = NEW.note_seq)) THEN
        RAISE EXCEPTION 'note % is in a contradiction: a person decides it', NEW.note_seq;
    END IF;
    IF NOT (SELECT n.ai_input AND j.ai_input FROM public.note n JOIN public.note_journal j USING (seq)
             WHERE n.seq = NEW.note_seq)
       OR public.note_skill_blocked(NEW.note_seq) THEN
        RAISE EXCEPTION 'the text of note % may not go to a model', NEW.note_seq;
    END IF;
    IF EXISTS (SELECT 1 FROM public.write_record w
                WHERE w.note_seq = NEW.note_seq AND w.action = 'propose'
                  AND w.principal IN ('agent:kutuphane-decider',
                                      (SELECT c.principal FROM public.model_call c WHERE c.id = s.model_call))) THEN
        RAISE EXCEPTION 'note % has a propose write by the runner''s principal', NEW.note_seq;
    END IF;
    SELECT x.note_seq INTO next_note FROM public.delegation_next(d.id) x;
    IF next_note IS DISTINCT FROM NEW.note_seq THEN
        RAISE EXCEPTION 'note % is not the next note of delegation %: a use takes the oldest eligible note (%)',
            NEW.note_seq, d.id, coalesce(next_note::text, 'none');
    END IF;
    SELECT count(*) INTO open_samples FROM public.delegation_use u
     WHERE u.delegation = d.id AND u.sampled
       AND NOT EXISTS (SELECT 1 FROM public.standing_event e WHERE e.note_seq = u.note_seq);
    IF open_samples >= 3 THEN
        RAISE EXCEPTION 'delegation % waits for 3 open samples', d.id;
    END IF;
    -- forced sample: at most 2N unsampled uses after the last human verdict on a sample
    SELECT max(u.seq) INTO last_verdict FROM public.delegation_use u
     WHERE u.delegation = d.id AND u.sampled
       AND EXISTS (SELECT 1 FROM public.standing_event e WHERE e.note_seq = u.note_seq AND e.set_by LIKE 'user:%');
    SELECT count(*) INTO run FROM public.delegation_use u
     WHERE u.delegation = d.id AND NOT u.sampled AND u.seq > coalesce(last_verdict, 0);
    SELECT ('x' || encode(substr(public.hmac(convert_to(d.id || ':' || NEW.note_seq, 'UTF8'), k.key, 'sha256'), 1, 4),
                          'hex'))::bit(32)::bigint
      INTO draw FROM public.delegation_sample_key k;
    NEW.sampled := run >= 2 * d.sample_every OR draw % d.sample_every = 0;
    RETURN NEW;
END $$;

CREATE OR REPLACE FUNCTION origin_confirmation_by_confirmer() RETURNS trigger LANGUAGE plpgsql
SET search_path = pg_catalog, public, pg_temp AS $$
DECLARE
    live_by text;
BEGIN
    PERFORM pg_advisory_xact_lock(461532067184);   -- notes.MEMORY_LOCK
    SELECT c.confirmed_by INTO live_by FROM public.origin_confirmation c
     WHERE c.seq = (SELECT max(seq) FROM public.origin_confirmation WHERE note_seq = NEW.note_seq)
       AND NOT EXISTS (SELECT 1 FROM public.origin_withdrawal x WHERE x.confirmation = c.seq);
    IF live_by IS NOT NULL AND live_by <> NEW.confirmed_by THEN
        RAISE EXCEPTION 'note % has a live confirmation by %: only the confirmer withdraws it (R7)',
            NEW.note_seq, live_by;
    END IF;
    RETURN NEW;
END $$;
