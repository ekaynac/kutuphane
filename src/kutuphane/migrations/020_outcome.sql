-- docs/24 §21 (#74): outcome feedback on an exact item version, decision fields, and the `train` right that the
-- decision export needs. Rows made before 020 never stated `train`: false (missing = deny).
ALTER TABLE journal ADD COLUMN train boolean NOT NULL DEFAULT false;
ALTER TABLE note ADD COLUMN train boolean NOT NULL DEFAULT false,
                 ADD COLUMN options text[],
                 ADD COLUMN choice text,
                 ADD CONSTRAINT note_decision CHECK ((options IS NULL) = (choice IS NULL) AND (options IS NULL OR
                     (kind = 'decision_proposal' AND cardinality(options) BETWEEN 2 AND 20
                      AND choice = ANY(options))));

-- Append-only (deploy/db-roles.sql). An outcome never changes Standing: it is a measurement, not an approval.
CREATE TABLE outcome (
    seq             bigint PRIMARY KEY DEFAULT nextval('memory_seq'),
    at              timestamptz NOT NULL DEFAULT now(),
    correlation_id  text NOT NULL,
    book            text NOT NULL,
    note_seq        bigint,                                                 -- a note, or
    content_id      text, profile_id text, path text, ordinal integer,      -- a passage at its version
    task_ref        text NOT NULL CHECK (task_ref ~ '^[A-Za-z0-9._:/#@+-]{1,200}$'),
    result          text NOT NULL CHECK (result IN ('passed', 'failed', 'reverted', 'reopened')),
    principal       text NOT NULL,
    on_behalf_of    text,
    channel         text NOT NULL CHECK (channel IN ('mcp', 'http')),
    client_id       text,
    origin          text NOT NULL CHECK (origin IN ('model', 'unknown')),
    idempotency_key text NOT NULL CHECK (idempotency_key ~ '^[A-Za-z0-9._:-]{8,128}$'),
    request_sha256  bytea NOT NULL,
    FOREIGN KEY (note_seq, book) REFERENCES note (seq, book),
    FOREIGN KEY (book, content_id, profile_id, path, ordinal)
        REFERENCES chunk (book, content_id, profile_id, path, ordinal),
    CHECK ((note_seq IS NULL) <> (content_id IS NULL)),
    CHECK (content_id IS NULL OR (profile_id IS NOT NULL AND path IS NOT NULL AND ordinal IS NOT NULL)),
    -- D70 R2 as a database guarantee, as write_record: an agent path stores model
    CHECK (origin = 'model' OR (principal LIKE 'user:%' AND on_behalf_of IS NULL AND channel = 'http'))
);
CREATE UNIQUE INDEX outcome_idempotency ON outcome (principal, coalesce(on_behalf_of, ''), idempotency_key);
CREATE INDEX outcome_note      ON outcome (note_seq, seq) WHERE note_seq IS NOT NULL;
CREATE INDEX outcome_passage   ON outcome (book, content_id, profile_id, path, ordinal) WHERE content_id IS NOT NULL;
CREATE INDEX outcome_principal ON outcome (principal, at);

-- docs/24 §20.3 and §21.3: `train` follows derivation as search and ai_input do. The view of 019 gets the AND of the
-- current `train` of every journal in the note's source_books (a column appended, so 019 readers do not change).
CREATE OR REPLACE VIEW note_journal AS
SELECT n.seq, j.search, j.ai_input, j.train
  FROM note n
 CROSS JOIN LATERAL (SELECT bool_and(search) AS search, bool_and(ai_input) AS ai_input, bool_and(train) AS train
                       FROM journal WHERE book = ANY(n.source_books)) j;
