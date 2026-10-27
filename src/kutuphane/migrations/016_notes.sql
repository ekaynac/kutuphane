-- R1 agent memory (docs/24 §4.1). Slice A owns this file; contract copy for slice B.
CREATE SEQUENCE memory_seq;

-- Two new modes. curate: only user principals, directly (a role can hold agents; docs/09 §3.2).
ALTER TABLE grant_tuple DROP CONSTRAINT grant_tuple_relation_check;
ALTER TABLE grant_tuple ADD CONSTRAINT grant_tuple_relation_check
    CHECK (relation IN ('discover', 'read', 'use', 'activate', 'member', 'propose', 'curate'));
ALTER TABLE grant_tuple ADD CONSTRAINT grant_tuple_curate_user CHECK (relation <> 'curate' OR subject LIKE 'user:%');
ALTER TABLE delegation DROP CONSTRAINT delegation_mode_check;           -- agents never get curate
ALTER TABLE delegation ADD CONSTRAINT delegation_mode_check
    CHECK (mode IN ('discover', 'read', 'use', 'activate', 'propose'));

-- AT-09 for notes: the watermark a delivery was evaluated at. items holds [{ref, standing_seq}].
ALTER TABLE access_event ADD COLUMN memory_seq bigint;

CREATE TABLE journal (
    book       text PRIMARY KEY REFERENCES book(slug),
    search     boolean NOT NULL,             -- both stated at creation; no default (docs/22 §3: missing = deny)
    ai_input   boolean NOT NULL,
    created_by text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE note (
    seq             bigint PRIMARY KEY DEFAULT nextval('memory_seq'),
    book            text NOT NULL REFERENCES journal(book),
    id              text NOT NULL CHECK (id ~ '^nt_[0-9a-f]{64}$'),
    profile_id      text NOT NULL REFERENCES profile_version(id),
    kind            text NOT NULL CHECK (kind IN ('finding', 'decision_proposal', 'dead_end', 'convention', 'lesson',
                                                  'test_result')),
    body            text NOT NULL CHECK (char_length(body) BETWEEN 1 AND 8000),
    norm_sha256     bytea NOT NULL,
    class_key       text CHECK (class_key ~ '^[a-z0-9][a-z0-9._:/-]{0,79}$'),
    scope_repo      text,
    scope_branch    text,
    scope_paths     text[] NOT NULL DEFAULT '{}' CHECK (cardinality(scope_paths) <= 20),
    scope_path_re   text[] NOT NULL DEFAULT '{}',
    observed_commit text CHECK (observed_commit ~ '^[0-9a-f]{40}([0-9a-f]{24})?$'),
    search          boolean NOT NULL,        -- journal.search AND every dependency allows search
    ai_input        boolean NOT NULL,        -- journal.ai_input AND every dependency allows ai_input
    source_books    text[] NOT NULL,         -- the journal + every book of the dependency closure
    written_at      timestamptz NOT NULL DEFAULT now(),
    tsv             tsvector,
    UNIQUE (book, id),
    UNIQUE (seq, book),
    CHECK (search = (tsv IS NOT NULL)),
    CHECK (cardinality(scope_paths) = cardinality(scope_path_re)),
    CHECK (scope_repo IS NOT NULL OR (scope_branch IS NULL AND scope_paths = '{}' AND observed_commit IS NULL))
);
CREATE INDEX note_book_seq ON note (book, seq);
CREATE INDEX note_norm     ON note (book, norm_sha256) WHERE search;
CREATE INDEX note_class    ON note (book, class_key) WHERE class_key IS NOT NULL;
CREATE INDEX note_scope    ON note (book, scope_repo, scope_branch);
CREATE INDEX note_tsv      ON note USING gin (tsv);

-- One row per write act: a propose (a new note, or the same bytes again) or a later link.
CREATE TABLE write_record (
    seq              bigint PRIMARY KEY DEFAULT nextval('memory_seq'),
    at               timestamptz NOT NULL DEFAULT now(),
    correlation_id   text NOT NULL,
    action           text NOT NULL CHECK (action IN ('propose', 'link')),
    note_seq         bigint REFERENCES note(seq),
    creates          boolean NOT NULL,
    principal        text NOT NULL,
    on_behalf_of     text,
    channel          text NOT NULL CHECK (channel IN ('mcp', 'http')),
    client_id        text,
    origin_requested text CHECK (origin_requested IN ('human', 'assisted', 'model', 'tool', 'unknown')),
    origin           text NOT NULL CHECK (origin IN ('model', 'unknown')),   -- R1 never stores human (D70 R3)
    notice           text CHECK (notice IN ('origin-claim-refused')),
    idempotency_key  text CHECK (idempotency_key ~ '^[A-Za-z0-9._:-]{8,128}$'),
    request_sha256   bytea,
    CHECK ((action = 'propose') = (note_seq IS NOT NULL)),
    CHECK (NOT creates OR action = 'propose'),
    -- D70 R2 as a database guarantee: an agent path stores model
    CHECK (origin = 'model' OR (principal LIKE 'user:%' AND on_behalf_of IS NULL AND channel = 'http')),
    CHECK (notice IS NULL OR origin_requested IS NOT NULL),
    CHECK ((idempotency_key IS NULL) = (request_sha256 IS NULL)),
    UNIQUE (seq, action),
    UNIQUE (seq, note_seq, creates)
);
CREATE UNIQUE INDEX write_record_creates ON write_record (note_seq) WHERE creates;
CREATE UNIQUE INDEX write_record_idempotency ON write_record (principal, coalesce(on_behalf_of, ''), idempotency_key)
    WHERE idempotency_key IS NOT NULL;
CREATE INDEX write_record_note      ON write_record (note_seq, seq) WHERE note_seq IS NOT NULL;
CREATE INDEX write_record_principal ON write_record (principal, at);

CREATE TABLE note_citation (
    note_seq       bigint NOT NULL,
    book           text NOT NULL,                       -- the note's book: the repository namespace
    n              smallint NOT NULL CHECK (n BETWEEN 1 AND 20),
    kind           text NOT NULL CHECK (kind IN ('passage', 'code')),
    -- passage: book@ct_…/pf_…/path#ordinal
    cite_book      text, content_id text, profile_id text, ordinal integer,
    path           text NOT NULL CHECK (path !~ '[[:cntrl:]]'),
    -- code: repo@commit:path:start[-end][#symbol]
    repo           text, commit text, line_start integer, line_end integer, symbol text, excerpt_sha256 bytea,
    PRIMARY KEY (note_seq, n),
    FOREIGN KEY (note_seq, book) REFERENCES note (seq, book),
    FOREIGN KEY (cite_book, content_id, profile_id, path, ordinal)
        REFERENCES chunk (book, content_id, profile_id, path, ordinal),
    CHECK (kind <> 'passage' OR (cite_book IS NOT NULL AND content_id IS NOT NULL AND profile_id IS NOT NULL
                                 AND ordinal IS NOT NULL AND repo IS NULL)),
    CHECK (kind <> 'code' OR (repo IS NOT NULL AND commit IS NOT NULL AND line_start IS NOT NULL
                              AND line_end IS NOT NULL AND excerpt_sha256 IS NOT NULL AND cite_book IS NULL
                              AND commit ~ '^[0-9a-f]{40}([0-9a-f]{24})?$'
                              AND line_start >= 1 AND line_end BETWEEN line_start AND line_start + 199)),
    CHECK (symbol IS NULL OR (kind = 'code' AND symbol ~ '^[A-Za-z_][A-Za-z0-9_.:$]{0,127}$'))
);
CREATE INDEX note_citation_code ON note_citation (book, repo, path) WHERE kind = 'code';

CREATE TABLE note_link (
    seq            bigint PRIMARY KEY DEFAULT nextval('memory_seq'),
    src            bigint NOT NULL,
    src_book       text NOT NULL,
    type           text NOT NULL CHECK (type IN ('derived_from', 'same_as', 'about', 'fixed_by', 'violates',
                                                 'decided_by', 'supersedes', 'contradicts')),
    dst_note       bigint,
    dst_note_book  text,
    dst_book       text, dst_content_id text, dst_profile_id text, dst_path text, dst_ordinal integer,
    creation       boolean NOT NULL,
    write_seq      bigint NOT NULL,
    write_action   text GENERATED ALWAYS AS (CASE WHEN creation THEN 'propose' ELSE 'link' END) STORED,
    creation_src   bigint GENERATED ALWAYS AS (CASE WHEN creation THEN src END) STORED,
    creation_flag  boolean GENERATED ALWAYS AS (CASE WHEN creation THEN true END) STORED,
    FOREIGN KEY (src, src_book) REFERENCES note (seq, book),
    FOREIGN KEY (dst_note, dst_note_book) REFERENCES note (seq, book),
    FOREIGN KEY (dst_book, dst_content_id, dst_profile_id, dst_path, dst_ordinal)
        REFERENCES chunk (book, content_id, profile_id, path, ordinal),
    FOREIGN KEY (write_seq, write_action) REFERENCES write_record (seq, action),
    -- a creation link belongs to the write that created its source note, and to no other write
    FOREIGN KEY (write_seq, creation_src, creation_flag) REFERENCES write_record (seq, note_seq, creates),
    CHECK ((dst_note IS NULL) = (dst_note_book IS NULL)),
    CHECK ((dst_note IS NULL) <> (dst_book IS NULL)),
    CHECK (dst_book IS NULL OR (dst_content_id IS NOT NULL AND dst_profile_id IS NOT NULL AND dst_path IS NOT NULL
                                AND dst_ordinal IS NOT NULL)),
    CHECK (dst_book IS NULL OR type IN ('derived_from', 'about')),
    CHECK (type NOT IN ('derived_from', 'supersedes') OR creation),       -- only at creation (§6.3)
    CHECK (NOT creation OR dst_note IS NULL OR dst_note < src),           -- creation links point back: no cycle
    CHECK (type <> 'same_as' OR dst_note_book = src_book),                -- same_as stays in one book
    CHECK (dst_note IS DISTINCT FROM src)
);
CREATE UNIQUE INDEX note_link_note ON note_link (src, type, dst_note) WHERE dst_note IS NOT NULL;
CREATE UNIQUE INDEX note_link_passage ON note_link (src, type, dst_book, dst_content_id, dst_profile_id, dst_path,
                                                    dst_ordinal) WHERE dst_book IS NOT NULL;
CREATE INDEX note_link_dst ON note_link (dst_note, type) WHERE dst_note IS NOT NULL;
CREATE INDEX note_link_dst_passage ON note_link (dst_book, dst_content_id, dst_profile_id, dst_path, dst_ordinal)
    WHERE dst_book IS NOT NULL;

-- docs/09 §3 for one facet: append-only Standing events of notes.
CREATE TABLE standing_event (
    seq            bigint PRIMARY KEY DEFAULT nextval('memory_seq'),
    note_seq       bigint NOT NULL REFERENCES note(seq),
    value          text NOT NULL CHECK (value IN ('approved', 'pending', 'rejected', 'retired')),
    set_by         text NOT NULL CHECK (set_by LIKE 'user:%' OR set_by = 'system'),  -- a user event is confirmed by set_by
    cause_seq      bigint REFERENCES standing_event(seq),
    reason         text NOT NULL CHECK (char_length(reason) BETWEEN 1 AND 500),
    correlation_id text NOT NULL,
    at             timestamptz NOT NULL DEFAULT now(),
    CHECK ((set_by = 'system') = (cause_seq IS NOT NULL)),
    CHECK (set_by <> 'system' OR value = 'retired')               -- the system only tightens (docs/09 §3.2)
);
CREATE INDEX standing_event_note ON standing_event (note_seq, seq DESC);

CREATE TABLE note_vector (
    note_seq  bigint NOT NULL REFERENCES note(seq),
    model     text NOT NULL,
    embedding vector NOT NULL,
    PRIMARY KEY (note_seq, model)
);
