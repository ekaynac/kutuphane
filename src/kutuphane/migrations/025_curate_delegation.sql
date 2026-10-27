-- docs/25 §6, §8: decider suggestions (#77 pre-sort, measured, never a confirmation) and D73 delegated curate.
-- The database owns every rule it can see: liveness, threshold, class, a fresh note, no contradiction, the model-input
-- gate, the sample (it draws it), the pause, the approval event, and the end on a disagreement.

ALTER TABLE note ADD UNIQUE (seq, book, kind);

-- One suggestion per (note, decider, spec), written before any person decides the note (§6.4).
CREATE TABLE note_suggestion (
    seq         bigint PRIMARY KEY DEFAULT nextval('memory_seq'),
    note_seq    bigint NOT NULL REFERENCES note (seq),
    decider     text NOT NULL CHECK (decider ~ '^[a-z0-9][a-z0-9._-]{0,62}@[A-Za-z0-9._+-]{1,64}$'),   -- name@version
    spec_sha256 bytea NOT NULL CHECK (octet_length(spec_sha256) = 32),
    value       text NOT NULL CHECK (value IN ('approved', 'rejected', 'abstain')),
    confidence  real NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    model_call  bigint NOT NULL REFERENCES model_call (id),
    at          timestamptz NOT NULL DEFAULT now(),
    UNIQUE (note_seq, decider, spec_sha256),
    UNIQUE (seq, note_seq, decider, spec_sha256)
);

-- D73. Created only by a signed `delegate` act (D56). Role evidence only: never a rule kind.
CREATE TABLE curate_delegation (
    id             text PRIMARY KEY CHECK (id ~ '^cd_[0-9a-f]{32}$'),
    book           text NOT NULL REFERENCES journal (book),
    kind           text NOT NULL CHECK (kind IN ('finding', 'lesson', 'dead_end', 'test_result')),
    decider        text NOT NULL,
    spec_sha256    bytea NOT NULL CHECK (octet_length(spec_sha256) = 32),
    approver       text NOT NULL GENERATED ALWAYS AS ('model:' || decider) STORED,
    min_confidence real NOT NULL CHECK (min_confidence >= 0.5 AND min_confidence <= 1),
    sample_every   integer NOT NULL CHECK (sample_every BETWEEN 2 AND 100),
    created_by     text NOT NULL,
    act            bigint NOT NULL UNIQUE,
    act_action     text NOT NULL GENERATED ALWAYS AS ('delegate') STORED,
    created_at     timestamptz NOT NULL DEFAULT now(),
    expires_at     timestamptz NOT NULL,
    CHECK (expires_at > created_at AND expires_at <= created_at + interval '30 days'),
    FOREIGN KEY (act, created_by) REFERENCES curator_act (seq, principal),
    FOREIGN KEY (act, act_action) REFERENCES curator_act (seq, action),
    UNIQUE (id, book, kind, decider, spec_sha256, approver)
);

CREATE FUNCTION curate_delegation_in_statement() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM curator_act a JOIN curator_challenge c ON c.id = a.challenge
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
CREATE TRIGGER curate_delegation_in_statement BEFORE INSERT ON curate_delegation
    FOR EACH ROW EXECUTE FUNCTION curate_delegation_in_statement();

-- At most one end per delegation; an end is final (a new delegation is a new signed act).
CREATE TABLE delegation_end (
    delegation text PRIMARY KEY REFERENCES curate_delegation (id),
    cause      text NOT NULL CHECK (cause IN ('disagreement', 'revoked')),
    ended_by   text NOT NULL CHECK (ended_by LIKE 'user:%' OR ended_by = 'system'),
    event      bigint UNIQUE REFERENCES standing_event (seq),   -- the human verdict that disagreed with a sample
    act        bigint UNIQUE REFERENCES curator_act (seq),      -- a revoke on the phone; NULL: by the CLI
    at         timestamptz NOT NULL DEFAULT now(),
    CHECK ((cause = 'disagreement') = (event IS NOT NULL)),
    CHECK ((cause = 'disagreement') = (ended_by = 'system')),
    CHECK (act IS NULL OR cause = 'revoked')
);

-- One row per note that a delegation decided. The database draws `sampled`; a sampled note waits for a person.
CREATE TABLE delegation_use (
    seq            bigint PRIMARY KEY DEFAULT nextval('memory_seq'),
    delegation     text NOT NULL,
    book           text NOT NULL,
    kind           text NOT NULL,
    decider        text NOT NULL,
    spec_sha256    bytea NOT NULL,
    approver       text NOT NULL,
    note_seq       bigint NOT NULL UNIQUE,
    suggestion     bigint NOT NULL,
    sampled        boolean NOT NULL DEFAULT false,      -- set by delegation_use_check, never by the runner
    unsampled      boolean GENERATED ALWAYS AS (CASE WHEN NOT sampled THEN true END) STORED,
    correlation_id text NOT NULL,
    at             timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (delegation, book, kind, decider, spec_sha256, approver)
        REFERENCES curate_delegation (id, book, kind, decider, spec_sha256, approver),
    FOREIGN KEY (note_seq, book, kind) REFERENCES note (seq, book, kind),
    FOREIGN KEY (suggestion, note_seq, decider, spec_sha256)
        REFERENCES note_suggestion (seq, note_seq, decider, spec_sha256),
    UNIQUE (seq, note_seq, approver, unsampled)
);
CREATE INDEX delegation_use_delegation ON delegation_use (delegation, seq);

CREATE FUNCTION delegation_use_check() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    d curate_delegation;
    s note_suggestion;
    open_samples integer;
    last_verdict bigint;
    run integer;
BEGIN
    SELECT * INTO d FROM curate_delegation WHERE id = NEW.delegation;
    IF clock_timestamp() >= d.expires_at OR EXISTS (SELECT 1 FROM delegation_end WHERE delegation = d.id) THEN
        RAISE EXCEPTION 'delegation % is not live', d.id;
    END IF;
    SELECT * INTO s FROM note_suggestion WHERE seq = NEW.suggestion;
    IF s.value <> 'approved' OR s.confidence < d.min_confidence THEN
        RAISE EXCEPTION 'suggestion % is under the delegation threshold', s.seq;
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
    NEW.sampled := run >= 2 * d.sample_every
                   OR ('x' || substr(md5(gen_random_uuid()::text), 1, 8))::bit(32)::bigint % d.sample_every = 0;
    RETURN NEW;
END $$;
CREATE TRIGGER delegation_use_check BEFORE INSERT ON delegation_use
    FOR EACH ROW EXECUTE FUNCTION delegation_use_check();

-- The approval of an unsampled use is written here, in the same statement: the runner holds no INSERT on
-- standing_event, so it cannot write an approval that this function did not decide.
CREATE FUNCTION delegation_use_approve() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER
SET search_path = public, pg_temp AS $$
BEGIN
    IF NOT NEW.sampled THEN
        INSERT INTO standing_event (note_seq, value, set_by, reason, correlation_id, delegation_use)
        VALUES (NEW.note_seq, 'approved', NEW.approver, 'delegated: ' || NEW.delegation, NEW.correlation_id, NEW.seq);
    END IF;
    RETURN NULL;
END $$;
CREATE TRIGGER delegation_use_approve AFTER INSERT ON delegation_use
    FOR EACH ROW EXECUTE FUNCTION delegation_use_approve();

-- The approver of record of a delegated approval is the decider (model id + version), never a writer.
ALTER TABLE standing_event DROP CONSTRAINT standing_event_set_by_check;
ALTER TABLE standing_event
    ADD CONSTRAINT standing_event_set_by_check CHECK (set_by LIKE 'user:%' OR set_by = 'system' OR set_by LIKE 'model:%'),
    ADD COLUMN delegation_use bigint UNIQUE,
    ADD COLUMN delegated boolean GENERATED ALWAYS AS (CASE WHEN delegation_use IS NOT NULL THEN true END) STORED,
    ADD FOREIGN KEY (delegation_use, note_seq, set_by, delegated)
        REFERENCES delegation_use (seq, note_seq, approver, unsampled),
    ADD CHECK ((set_by LIKE 'model:%') = (delegation_use IS NOT NULL)),
    ADD CHECK (delegation_use IS NULL OR value = 'approved');

-- The first event of a sampled note is its verdict. A person's verdict other than `approved` ends the delegation in
-- the same transaction, whatever path wrote it (phone, `note standing`, `note rollback`). A first event by the system
-- closes the sample with no verdict.
CREATE FUNCTION standing_event_sample_verdict() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER
SET search_path = public, pg_temp AS $$
BEGIN
    IF NEW.set_by LIKE 'user:%' AND NEW.value <> 'approved' THEN
        INSERT INTO delegation_end (delegation, cause, ended_by, event)
        SELECT u.delegation, 'disagreement', 'system', NEW.seq
          FROM delegation_use u
         WHERE u.note_seq = NEW.note_seq AND u.sampled
           AND NOT EXISTS (SELECT 1 FROM delegation_end e WHERE e.delegation = u.delegation)
           AND NOT EXISTS (SELECT 1 FROM standing_event p WHERE p.note_seq = NEW.note_seq AND p.seq < NEW.seq);
    END IF;
    RETURN NULL;
END $$;
CREATE TRIGGER standing_event_sample_verdict AFTER INSERT ON standing_event
    FOR EACH ROW EXECUTE FUNCTION standing_event_sample_verdict();
