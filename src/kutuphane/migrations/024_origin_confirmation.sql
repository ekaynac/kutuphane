-- docs/25 §7: D70 R3 "my words" confirmation and R7 withdrawal, over the passkey act of 023.

-- The person an agent may enter words for: the user acted for, else the writer if it is a user. NULL for an agent on
-- its own rights. A confirmation request = a propose write whose human or assisted claim was refused (docs/24 §5.3).
ALTER TABLE write_record
    ADD COLUMN person text GENERATED ALWAYS AS
        (coalesce(on_behalf_of, CASE WHEN principal LIKE 'user:%' THEN principal END)) STORED,
    ADD COLUMN confirmable boolean GENERATED ALWAYS AS
        (CASE WHEN notice = 'origin-claim-refused' AND origin_requested IN ('human', 'assisted') THEN true END) STORED,
    ADD UNIQUE (seq, note_seq, confirmable),
    ADD UNIQUE (seq, person),
    ADD UNIQUE (seq, principal);
ALTER TABLE note ADD UNIQUE (seq, book, id);

CREATE TABLE origin_confirmation (
    seq          bigint PRIMARY KEY DEFAULT nextval('memory_seq'),
    note_seq     bigint NOT NULL,
    book         text NOT NULL,
    note_id      text NOT NULL,                     -- the digest of the confirmed bytes
    write_seq    bigint NOT NULL,                   -- the open request
    claim        text NOT NULL CHECK (claim IN ('human', 'assisted')),
    entered_by   text NOT NULL,                     -- the writer of that request
    confirmed_by text NOT NULL CHECK (confirmed_by LIKE 'user:%'),
    act          bigint NOT NULL UNIQUE,
    act_action   text NOT NULL GENERATED ALWAYS AS ('confirm') STORED,
    request      boolean NOT NULL GENERATED ALWAYS AS (true) STORED,
    human_by     text GENERATED ALWAYS AS (CASE WHEN claim = 'human' THEN confirmed_by END) STORED,
    at           timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (note_seq, book, note_id) REFERENCES note (seq, book, id),
    FOREIGN KEY (write_seq, note_seq, request) REFERENCES write_record (seq, note_seq, confirmable),
    FOREIGN KEY (write_seq, entered_by) REFERENCES write_record (seq, principal),
    FOREIGN KEY (write_seq, human_by) REFERENCES write_record (seq, person),   -- human: only the person (R3 a)
    FOREIGN KEY (act, confirmed_by) REFERENCES curator_act (seq, principal),
    FOREIGN KEY (act, act_action) REFERENCES curator_act (seq, action),
    UNIQUE (seq, confirmed_by)
);
CREATE INDEX origin_confirmation_note ON origin_confirmation (note_seq, seq DESC);

-- A confirmation is exactly the signed statement: this note and bytes, this request, this claim, this writer.
CREATE FUNCTION origin_confirmation_in_statement() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM curator_act a JOIN curator_challenge c ON c.id = a.challenge
         WHERE a.seq = NEW.act AND c.payload #>> '{item,ref}' = NEW.book || '@' || NEW.note_id
           AND (c.payload #>> '{item,write}')::bigint = NEW.write_seq AND c.payload ->> 'claim' = NEW.claim
           AND c.payload ->> 'entered_by' = NEW.entered_by) THEN
        RAISE EXCEPTION 'confirmation is not the statement of act %', NEW.act;
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER origin_confirmation_in_statement BEFORE INSERT ON origin_confirmation
    FOR EACH ROW EXECUTE FUNCTION origin_confirmation_in_statement();

-- R7: only the confirmer withdraws, with a passkey act of their own.
CREATE TABLE origin_withdrawal (
    seq          bigint PRIMARY KEY DEFAULT nextval('memory_seq'),
    confirmation bigint NOT NULL UNIQUE,
    withdrawn_by text NOT NULL,
    act          bigint NOT NULL UNIQUE,
    act_action   text NOT NULL GENERATED ALWAYS AS ('withdraw') STORED,
    at           timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (confirmation, withdrawn_by) REFERENCES origin_confirmation (seq, confirmed_by),
    FOREIGN KEY (act, withdrawn_by) REFERENCES curator_act (seq, principal),
    FOREIGN KEY (act, act_action) REFERENCES curator_act (seq, action)
);
