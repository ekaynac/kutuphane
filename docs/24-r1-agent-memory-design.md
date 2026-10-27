# R1 design — agent memory, first slice

**Status:** DESIGN 0.2, 2026-10-27. Branch `docs/r1-design`. 0.2 applies the operator's answers to the 0.1 questions (§17) and the 22 findings of Astra's review (§18). No code changes.
**Language:** ASD-STE100 Simplified Technical English.
**DDL check:** the SQL of §4 applies on top of migrations 001–015 (PostgreSQL 17, pgvector 0.8). Probe inserts show that the D70, `curate`, Standing, link and citation checks refuse the forbidden rows.
**Basis:** issues #67–#73, #77, #79; `docs/09` (ontology v2, D54); `docs/22` §4 (R1–R7, D70); `docs/23` (vision 1.0, D69); D68 (`rejected`); the code at `0c33d12` (migrations 001–015, `mcp` 1.30.0); the MCP 2026-07-28 changelog and the MCP Python SDK v2 guides (sources in §12).

**Rule for this document (D53):** each field and each value has a "changes" note. If a field changes no behavior, it is not in R1.

## 1. Summary of the decisions

| # | Decision | Section |
|---|---|---|
| 1 | Agent writes get their own unit: the **note**. A note is content-addressed: `nt_` + SHA-256 of its canonical body, and the body includes its creation links. A journal is a book whose items are notes. A journal is **not** a series of content versions. | §3 |
| 2 | Three migrations: `016_notes`, `017_code_repo`, `018_ask_job`. | §4 |
| 3 | The server computes origin (D70 R1, R2, R6, and R4 in its "otherwise `unknown`" form). An agent path stores `model`. A direct user write stores `unknown`. **R1 never stores `human`.** `human` comes only from the R3 passkey confirmation (later). | §5 |
| 4 | The rights of a note follow its derivation: `search` and `ai_input` are the AND of the journal and every dependency; the egress books are the union. | §6.2 |
| 5 | Only identical canonical bytes are the same note. A normalized match, a vector match or a class match is a **candidate**. Only an agent or a person makes `same_as` or `contradicts`. `same_as` and clusters stay inside one book. | §7 |
| 6 | Standing has its own append-only event table. **Curation is CLI-only in R1**, with a separate database credential that agent hosts never hold. No MCP tool and no HTTP route changes Standing. `rejected` (never accepted, D68) and `retired` (accepted before) are separate. | §8 |
| 7 | `query_notes` and `neighbours` are the fast reads: SQL only, no model call, one shared "current" predicate with request context, deterministic order, an estimated token budget plus a hard byte limit, a watermark, and tombstones for notes that leave a set. | §9 |
| 8 | Code citations point into repositories that an administrator registers per journal, with an allowlist of refs. The verifier reads only commits that those refs reach, through a confined git process. | §10 |
| 9 | MCP SDK `mcp` 1.30 → 2.3 (`FastMCP` → `MCPServer`), 2026-07-28 and 2025-11-25 clients. Long `ask_library` runs as a durable job. `propose_note` and job submission take an idempotency key. | §12 |
| 10 | Headless clients use OAuth client credentials at the IdP → an `agent:` principal; on-behalf-of work uses RFC 8693 token exchange and a live delegation, as today. | §12.4 |

## 2. What the code has today, and what is missing

| Area | Today (`0c33d12`) | Missing for R1 |
|---|---|---|
| Content | books, immutable content versions (`ct_`), chunks per (content, profile), vectors | a write path that is not a whole-book ingest |
| Ontology v2 | approved (D54), **not implemented**: no block, annotation or Standing tables | Standing events for notes |
| Modes | `discover`, `read`, `use`, `activate` (+ `member`) | a write right (`propose`) and `curate` |
| Origin | kstd item `origin` from `kstd.yaml` only | origin from the write path (D70) |
| Search | `search_library` (FTS + vector + rerank), `ask_library` (about 63 s) | filtered, deterministic reads with no model call |
| Gate | `gate.guard` decides **one** object; `gate.check_many` decides many objects but runs no work | one decision for many objects around a write (`gate.guard_many`, P0) |
| Identity | JWT from the IdP; `act` → agent on behalf of a user | `client_id` |
| MCP | `mcp` 1.30 `FastMCP`, `stateless_http=True` | 2026-07-28; durable jobs; idempotent retries |

## 3. The unit of agent writes (#69)

**Decision:** agent writes do **not** fit the book content-version model. They get their own unit, the note. The note keeps the content-hash principle at the level of one entry.

**Reasons:**
1. **Cost.** A content id covers all files of a version (`ids.content_id`). `catalog.publish` writes all chunks again for each new content id. One entry per version makes each write O(book), and the storage O(n²).
2. **Stable identity.** Links, Standing events and citations need an id that never changes. A per-entry digest gives that. A log-segment version changes with each entry.
3. **D70 R3 needs it.** The passkey challenge must contain the digest of the exact bytes. The note id is that digest.
4. **No continuity problem.** `docs/09` §1.2 (continuity links, `approved → pending` on a text change) does not apply. A note never changes. A correction is a new note with a `supersedes` link.

**Rejected alternative:** a journal version = an ordered log segment as a content version. It fails reasons 1 and 2.

**Canonical body:** `{v: 1, kind, text (NFC), class_key, scope, commit, citations (in order), links (sorted by type, then target)}`. The creation links are part of the identity (§6.3): the same text with other links is another note.

**The journal profile.** A journal is a book with `current_content = NULL` and `current_profile` = the `journal` profile:
`{"name": "journal", "components": {"notes": "kutuphane.notes@1", "normalizer": "nfc-casefold-ws@1"}, "settings": {"fts": "turkish", "max_chars": 8000}}`.
The profile id covers the normalizer and the FTS configuration (D26). Because `current_content` is NULL, `search_library` never sees a journal.

**One note = one block.** The writer gives the boundary. The ontology block rule (§1.1) does not cut notes. A note longer than 8,000 characters is refused.

**Note reference:** `<book>@nt_<64 hex>`. The same bytes in two books are two notes, because the rights of the books are different.

## 4. Tables and migrations

All memory rows take their `seq` from one sequence, `memory_seq`. Each memory write takes one transaction-level advisory lock (`pg_advisory_xact_lock`) before its first `nextval`. So `seq` order is commit order, and a watermark never skips a row (§9.5). Agent write rates are low (tens per minute).

### 4.1 `016_notes.sql` (slice A)

```sql
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
```

**Database roles (slice A, deployment):** the server and every process that an agent can reach connect with `KUTUPHANE_DSN` as role `kutuphane_app`. This role has `SELECT` on `standing_event`, and no `INSERT`, `UPDATE` or `DELETE`. It has no `UPDATE` or `DELETE` on `note`, `write_record`, `note_link` and `note_citation`. Only the owner role (`KUTUPHANE_CURATOR_DSN`, used by `kutuphane migrate` and `kutuphane note standing`) can write Standing (§8.2).

### 4.2 Field → behavior (016)

| Field | Changes |
|---|---|
| mode `propose` | who may write notes and links into a journal. Agents get it by a direct grant or a delegation. Off by default. |
| mode `curate` | who may be named as a curator by the CLI. A database check allows only `user:` subjects. Delegation cannot carry it. |
| `access_event.memory_seq` + `items[].standing_seq` | the audit names the Standing event in force for each delivered note (null = the initial `pending`) and the watermark (AT-09) |
| `journal.search` | `false`: notes get no `tsv` and no vector; no `text` match, no relevance order, no candidates |
| `journal.ai_input` | `false`: note text is withheld from model readers; no embedding call |
| `note.id` | identity, exact-duplicate merge, the note reference, the future R3 passkey challenge |
| `note.profile_id` | which normalizer and FTS configuration made `norm_sha256` and `tsv` |
| `note.kind` | the default Role and Time (§8.1), the #77 risk order, the `kind` filter |
| `note.body` | the content; FTS |
| `note.norm_sha256` | the `normalized` candidate (§7) |
| `note.class_key` | `class_count`, the `class_key` filter, `guard_due` (§7) |
| `scope_repo`, `scope_branch`, `scope_paths` | the Scope facet: current only when the request context matches (§9.2) |
| `scope_path_re` | the SQL match of the globs (derived from `scope_paths` by one deterministic function) |
| `observed_commit` | the `commits` range filter (§9.1) |
| `note.search`, `note.ai_input` | the restrictions of the note, derived at creation (§6.2); reads AND them with the journal's current values |
| `note.source_books` | the egress check of every model call with this note (embedding now; answers in R2) |
| `written_at` | the time filters |
| `tsv` | the `text` filter, with no model call; NULL when search is not allowed |
| `write_record.action`, `note_seq`, `creates` | recurrence (propose writes); the creation write owns the creation links |
| `write_record.principal`, `on_behalf_of`, `channel` | origin (§5); the daily write limit; idempotency scope; the #79 report |
| `write_record.client_id` | shown in the #77 queue and the #79 report: which client wrote it (never used for origin or rights) |
| `origin_requested`, `origin`, `notice` | the stored origin and the `origin-claim-refused` notice; the R3 confirmation requests (§5.3) |
| `idempotency_key`, `request_sha256` | a retried propose returns the original receipt (§6.4) |
| `note_citation.book` + composite key | a citation always uses the repository namespace of its own note's book |
| `note_citation` (others) | citation display; the verifier (§10); passage citations need `read` at write and at read |
| `note_link.type` | §6.3 |
| `note_link.creation`, `write_seq` | creation links are part of the note identity and are the only "own" links (#79). Later links have their own write. |
| `note_link.src_book`, `dst_note_book` | `same_as` stays in one book; endpoint books for the rights filter of every graph read |
| `standing_event.*` | effective Standing = the latest event with `seq ≤ w`, else `pending`; `cause_seq` names the root of a system move |
| `note_vector` | vector candidates (§7) |

### 4.3 `017_code_repo.sql` (slice C)

```sql
CREATE TABLE code_repo (
    book          text NOT NULL REFERENCES journal(book),
    slug          text NOT NULL CHECK (slug ~ '^[a-z0-9][a-z0-9._-]{0,62}$'),
    git_dir       text NOT NULL CHECK (git_dir LIKE '/%' AND git_dir !~ '[[:cntrl:]]'),
    object_format text NOT NULL CHECK (object_format IN ('sha1', 'sha256')),
    refs          text[] NOT NULL CHECK (cardinality(refs) BETWEEN 1 AND 10),
    added_by      text NOT NULL,
    added_at      timestamptz NOT NULL DEFAULT now(),
    removed_at    timestamptz,
    PRIMARY KEY (book, slug)
);
ALTER TABLE note ADD FOREIGN KEY (book, scope_repo) REFERENCES code_repo (book, slug);
ALTER TABLE note_citation ADD FOREIGN KEY (book, repo) REFERENCES code_repo (book, slug);
```

| Field | Changes |
|---|---|
| `(book, slug)` | the repository namespace of one journal; targets and caches use the pair (§9.2, §10.3) |
| `git_dir` | where the verifier reads objects; checked at `add` and at each open (§10.2) |
| `object_format` | the commit id length that the parser accepts (40 or 64 hex) |
| `refs` | ref patterns (for example `refs/heads/*`, `refs/tags/v*`). Only commits that these refs reach can be cited or verified; a branch target must match them. |
| `removed_at` | new scopes and citations into the repository are refused; verification is `unverifiable: repo_removed` |

### 4.4 `018_ask_job.sql` (slice D)

```sql
CREATE TABLE ask_job (
    id                  text PRIMARY KEY CHECK (id ~ '^jb_[0-9a-f]{32}$'),
    principal           text NOT NULL,
    on_behalf_of        text,
    correlation_id      text NOT NULL,
    question            text NOT NULL,
    scope               jsonb NOT NULL,
    idempotency_key     text CHECK (idempotency_key ~ '^[A-Za-z0-9._:-]{8,128}$'),
    request_sha256      bytea,
    status              text NOT NULL CHECK (status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')),
    created_at          timestamptz NOT NULL DEFAULT now(),
    started_at          timestamptz,
    lease_until         timestamptz,
    finished_at         timestamptz,
    cancel_requested_at timestamptz,
    answer_id           text REFERENCES answer(id),
    error               text CHECK (char_length(error) <= 500),
    CHECK (status <> 'succeeded' OR answer_id IS NOT NULL),
    CHECK ((idempotency_key IS NULL) = (request_sha256 IS NULL))
);
CREATE UNIQUE INDEX ask_job_idempotency ON ask_job (principal, coalesce(on_behalf_of, ''), idempotency_key)
    WHERE idempotency_key IS NOT NULL;
CREATE INDEX ask_job_owner ON ask_job (principal, created_at DESC);
CREATE INDEX ask_job_open  ON ask_job (created_at) WHERE status IN ('queued', 'running');
```

| Field | Changes |
|---|---|
| `principal`, `on_behalf_of` | visibility (§12.2: the same policy as `reopen_answer`); the worker runs with these rights at run time |
| `question`, `scope` | the request |
| `idempotency_key`, `request_sha256` | a retried submission returns the original job |
| `status`, timestamps | `job_status` |
| `lease_until` | a running job whose lease ended becomes `failed: interrupted`. It does not run again (model cost). |
| `cancel_requested_at` | the worker checks it before the model call and before it stores the result |
| `answer_id` | `job_result` = `reopen_answer` of this answer |
| `error` | a short, safe message (the HTTP error classes) |

## 5. Origin from the write path (D70)

### 5.1 Inputs

| Input | Source | Never from |
|---|---|---|
| `principal`, `on_behalf_of` | the verified JWT (`identity.py`) | headers, tool arguments |
| `channel` | set **only** by the server entry point: `mcp` or `http` | the client, any argument |
| `client_id` | the JWT claim `client_id` (RFC 9068), else `azp`; recorded only | `_meta.io.modelcontextprotocol/clientInfo` |
| `origin_requested` | the optional `origin` argument | — |

`gate.Actor` gets two fields with safe defaults: `client_id=None`, `channel="cli"`.

### 5.2 Rules (R1 builds R1, R2, R4 in its "otherwise" form, R6)

```
computed:
  R2  principal is agent:*, or on_behalf_of is set, or channel = mcp   -> model
  R4/R6  else (a user:, no act, over HTTP)                              -> unknown
stored:
  requested is None, or requested = computed        -> computed
  requested = model                                 -> model        (a lower value is always allowed)
  requested = unknown and computed = model          -> model
  requested in (human, assisted, tool)              -> computed, notice = origin-claim-refused
note origin (shown) = the lowest stored origin over its propose writes with seq <= w (model < unknown)
```

**Why no `human` in R1:** a client id and a recent login identify a token, not a human act on these bytes. An agent that holds a fresh UI token passes both tests. R1 has no trusted UI session that binds a person's act to the exact bytes. So every direct user write is `unknown` (D70 R4: "otherwise `unknown`"). `unknown` is shown as `unknown` and handled as `model` everywhere (kstd `AI_GENERATED`).

### 5.3 R3 and R7: a data slot only

R1 builds no confirmation path. The data model allows it later without a change to R1 tables:
- the note id is the SHA-256 of the exact canonical body, so a passkey challenge can contain it;
- a `write_record` with `notice = origin-claim-refused` is an open confirmation request (a derived view, not a row);
- a later migration adds `origin_confirmation (note_seq, note_id, confirmed_by user:, choice human|assisted, credential_id, at, withdrawn_at)`. The shown origin = the latest live confirmation, else §5.2. `withdrawn_at` is R7. `write_record.origin` stays the write-path value.
- MCP 2026-07-28 removes `notifications/elicitation/complete`. R3 will use URL-mode elicitation inside a multi-round-trip request, with the note id in `requestState`.

## 6. The write path

### 6.1 `propose_note` (MCP) / `POST /v1/notes` (HTTP)

```
propose_note(book: str, kind: str, text: str,
             citations: list[str] = [],                 # ≤ 20: passage handles or code citations (§10.1)
             scope: {repo: str, branch?: str, paths?: list[str]} | None = None,
             commit: str | None = None,                  # observed_commit; needs scope.repo
             links: list[{type: str, ref: str}] = [],    # ≤ 20 creation links (§6.3)
             class_key: str | None = None,
             origin: str | None = None,
             idempotency_key: str | None = None) -> dict
```

Steps. **No repository access and no model call happens before step 5.**
1. **Validate** the arguments (no I/O). Refuse control characters (U+0000–U+001F, U+007F) in every path, branch and reference.
2. **Scan** the text with `secretscan.findings` (local). A finding refuses the note and returns the rule names, never the matched text.
3. **Idempotency** (§6.4).
4. **Daily limit:** `KUTUPHANE_NOTE_WRITES_PER_DAY` per principal (default 500), counted in `write_record`.
5. **Pre-decision:** one `authz.allowed` statement for every need: `propose` on the journal; `read` on the book of every cited passage and every linked note or passage. A missing need refuses the request and is logged. `read` on the journal is also decided here; it only sets the receipt level (§6.1 result).
6. **Dependencies** (database only, §6.2): the new note's `search`, `ai_input` and `source_books`.
7. **Code excerpts:** read each cited excerpt at its commit (§10.3). An unknown repository, an unreachable commit, a missing path or line refuses the note.
8. **Embedding:** only if the note's `search` and `ai_input` are true and an embeddings route exists. `source_books` = the note's `source_books`, so `llmdap._check_egress` applies the strictest egress. A refusal or failure does not stop the write; the receipt says `vector: skipped:<reason>`.
9. **Transaction** with `gate.guard_many` (P0): the advisory lock; one final `authz.allowed` statement for **all** needs of step 5; insert or find the note, the `write_record`, citations, creation links, vector; collect candidates (§7) with the read set of the final decision. A lost right rolls everything back and is logged. Repository reads and an embedding call are the only effects that a refusal cannot undo; both happen only after step 5 allowed them.

**Receipt** (the caller holds `read` on the journal):

```json
{"ref": "adc-memory@nt_3f…", "status": "created", "standing": "pending",
 "origin": "model", "origin_notice": null,
 "candidates": [{"ref": "adc-memory@nt_9a…", "match": "vector", "similarity": 0.93, "kind": "finding",
                 "standing": "approved", "text": "first 300 characters, or null", "withheld": null}],
 "recurrence": 1, "class_count": 2, "guard_due": true, "vector": "stored"}
```

- `status: existing`: the same bytes were already in the book. One more `write_record`, `recurrence` + 1. **Standing is unchanged** and the receipt gives its real value, for example `rejected`. A re-proposal never reopens a note; only a curator reopens (§8.2). The #77 queue shows "proposed again after rejection: n times" from the write records.
- **Propose-only caller** (no `read` on the journal): the receipt is `{ref, status: "recorded", origin, origin_notice}`. It does not say whether the note existed, and it has no candidates or counts.

### 6.2 Rights follow derivation

The **dependencies** of a new note are its passage citations and its `derived_from` targets (notes and passages). Code citations point into the journal's own repositories and add no book.

| Note field | Value |
|---|---|
| `search` | `journal.search` AND every dependency allows search |
| `ai_input` | `journal.ai_input` AND every dependency allows AI input |
| `source_books` | the journal ∪ every dependency's book ∪ every dependency note's `source_books` |

- A passage dependency uses the kstd item of its pinned file version (`kstd.Rights.info` → `allows(…, "search")`, `allows(…, "ai_input")`). Versions are immutable, so the value is stable.
- A note dependency uses the stored `search`, `ai_input` and `source_books` of that note. Each note stores its closure, so one level of lookup gives the transitive result (a chain of derived notes keeps the restriction).
- Book policy egress (`local_only`) is read at call time for every book in `source_books`.
- Every read and every model call ANDs the note values with the journal's **current** `search` and `ai_input`. An administrator can only tighten a journal in R1 (`kutuphane journal restrict`); loosening needs a new journal.

### 6.3 Links

| Type | Direction | When | Changes in R1 | Later |
|---|---|---|---|---|
| `derived_from` | new → source (note or passage) | creation only | rights (§6.2); `neighbours` | #79 rollback |
| `supersedes` | successor → predecessor | creation only | system retirement on approval (§8.3) | — |
| `same_as` | either; same book only | creation or later | clusters, recurrence, `collapse`, #77 groups | — |
| `contradicts` | either | creation or later | never collapsed together; shown in link counts | #77 shows both |
| `about` | note → note or passage | creation or later | `neighbours` from a passage handle | — |
| `fixed_by` | finding → fix | creation or later | the `unfixed` filter | — |
| `violates` | finding → rule note | creation or later | `neighbours`; counts on the rule | #77 risk |
| `decided_by` | note → decision note | creation or later | `neighbours` | — |

- **Creation links** are in the canonical body (§3), so they are part of the note identity. The creation `write_record` owns them (database key, §4.1). A duplicate proposal has the same bytes, so it has the same links and adds none. Only creation links are "own" links (#79).
- `derived_from` and `supersedes` exist only as creation links. They change rights, retirement and rollback, so they must be part of what the curator approves. A creation link points to an older note (`dst < src`), so these links can never form a cycle.
- **Later links:** `link_notes(src, type, dst)` (MCP) / `POST /v1/notes/links` (HTTP), for `same_as`, `contradicts`, `about`, `fixed_by`, `violates`, `decided_by`. It needs `propose` on the book of `src` and `read` on the book of `dst`, decided before and again in one statement at commit. Each later link has its own `write_record` (`action = link`). The same link again returns the existing link (no new row).
- **Passage endpoints** are structured columns with a foreign key to `chunk`. Both endpoints are checked to exist and to be readable.

### 6.4 Idempotency

- `idempotency_key` scope: `(principal, on_behalf_of)`. `request_sha256` = SHA-256 of the canonical JSON of all arguments except the key.
- A retry with the same key and the same digest returns the original receipt: the same `ref` and `status`, with current counts. The pre-decision (step 5) runs again, so a revoked right still refuses. No new `write_record`.
- The same key with another digest → 409 `idempotency_key reused with another request`.
- The key lives as long as its `write_record` (no expiry). Without a key, a retry is one more write (`recurrence` + 1).

## 7. Duplicates and equal concerns (#72)

| Match | Test | Result |
|---|---|---|
| same bytes | the same `id` in the same book | the same note; one more write; `recurrence` + 1 |
| `normalized` | equal `norm_sha256` (NFC, case fold, white space collapsed) | a candidate |
| `vector` | cosine similarity ≥ `KUTUPHANE_NOTE_DUP_SIMILARITY` (0.90) on `note_vector` of the same model | a candidate (top 5) |
| `class` | the same `class_key` in the same book | a candidate (the 5 newest) |

Rules:
- **Only identical bytes are automatic.** Case and white space can change the meaning of code (identifiers, indentation, string contents). A normalized match is a candidate, as a vector match is. The agent or a person decides with `link_notes` (`same_as` or `contradicts`).
- **Never swallow a contradiction.** The server never decides that two different texts say the same thing.
- **Candidate rights:** candidates come only from books in the read set of the final decision, and only from notes whose own `search` and journal `search` are true. Candidate text passes the `ai_input` gate.
- **Clusters are book-local.** `same_as` links are allowed only inside one book (database check). A cluster = a connected component of `same_as` links with `seq ≤ w`, computed at read time (a recursive query in one book). No cluster value is stored or overwritten, so `as_of` gives the old clusters (§9.5).
- **Recurrence** = the number of `propose` write records with `seq ≤ w` over the cluster. **`class_count`** = the number of distinct clusters with the class key in the book. **`guard_due`** = `class_count ≥ 2` and no `approved` `convention` note with that class key in the book. All of these stay inside one book, so a reader sees only the activity of a book that it can read.
- **The guard itself:** Kütüphane records `guard_due` and, once accepted, the guard as a `convention` note with the class key. The orchestrator builds the test or the lint, and keeps the owner and the due condition in its own event log (operator decision, §17).

## 8. Standing and curation in R1

### 8.1 Kind → Role, Time, risk

| Kind | Role | Time | #77 risk order |
|---|---|---|---|
| `decision_proposal` | `rule` | `durable` | 1 |
| `convention` | `rule` | `durable` | 2 |
| `finding` | `evidence` | `durable` | 3 |
| `lesson` | `evidence` | `durable` | 4 |
| `dead_end` | `evidence` | `durable` | 4 |
| `test_result` | `evidence` | `as_of(written_at)`: history at any later time (`docs/09` §2.1) | 5 |

`lesson` and `dead_end` differ only in the `kind` filter, a presentation behavior that #68 asks for. R1 has no Role, Time or Scope events: an approval confirms the kind, scope and creation links of the note as written.

### 8.2 Transitions and the curator path

| From → to | Actor |
|---|---|
| (new note) → `pending` | system, implicit: no event = `pending` |
| `pending` → `approved` | curator |
| `pending` → `rejected` (never accepted, D68) | curator |
| `approved` → `retired` (accepted before; withdrawn or replaced) | curator, or the system by supersession (§8.3) |
| `rejected` / `retired` → `pending` (reopen) | curator |

**`rejected` and `retired` are separate (D68):** `retired` shows its successor (`supersedes`) and keeps "was accepted from … to …"; `rejected` was never accepted, and an agent that proposes the same bytes again gets `standing: rejected` in its receipt, so it can stop. #77 counts them apart.

**Curation is CLI-only in R1** (operator decision):
```
kutuphane note standing <ref> approved|rejected|retired|pending --curator user:ayse --reason "…"
```
- The CLI checks that `user:ayse` holds `curate` on the book now (`authz.direct`; `curate` cannot be delegated) and that the transition is in the table above.
- **Trust boundary:** the CLI trusts its operator. It records the curator that the operator names. So the credential that can write Standing is the boundary:
  - only the owner role can insert into `standing_event`; the app role (`KUTUPHANE_DSN`) cannot (§4.1);
  - the command needs `KUTUPHANE_CURATOR_DSN`. The operator keeps it out of every environment that an agent can read: not in the server container, not in orchestrator containers, not in a shell profile that an agent session inherits (enter it at the prompt, or read it from a secret store that asks the person);
  - OAuth tokens, the only credentials that agents get, reach only MCP and HTTP, and **neither has a Standing path**.
- An agent that can read the curator credential can curate as any user. This is a deployment error, the same as an agent with database owner access, and R1 cannot detect it.

When a curator approves a `rule` note, the CLI lists the current `rule` notes with the same `scope_repo` (`docs/09` §2.1). The curator decides; there is no automatic conflict decision.

### 8.3 Supersession (system, stricter)

When a curator approves note S, the system retires note P in the same transaction if all are true:
- S has a creation `supersedes` link to P;
- the role of S is `rule`;
- P is `approved`, in the same book, with exactly the same scope (repo, branch, paths).

The event has `set_by = system`, `cause_seq` = the approval event of S. A partial scope overlap does nothing; the curator narrows or retires P. A successor that loses approval does not reopen P (`docs/09` §3.3).

## 9. The read path (#71)

### 9.1 `query_notes` (MCP) / `GET /v1/notes` (HTTP)

```
query_notes(book: list[str] | None = None,       # intersected with the readable books
            sets: list[str] = ["current"],       # current | open | history (§9.2)
            kind: list[str] | None = None, role: list[str] | None = None, origin: list[str] | None = None,
            class_key: str | None = None,
            repo: str | None = None, branch: str | None = None, path: str | None = None,   # the context
            commit: str | None = None,           # code target; without it, `branch` resolves to its head
            commits: str | None = None,          # "A..B": two full commit ids; observed_commit in rev-list A..B
            written_after: str | None = None, written_before: str | None = None,
            since: int | None = None,            # changes after this watermark (§9.5)
            text: str | None = None,             # websearch_to_tsquery over tsv; search-permitted notes only
            unfixed: bool = False, collapse: bool = False, include_unverified: bool = False,
            order: str = "newest",               # newest | oldest | relevance (text only)
            budget_tokens: int = 2000,           # 200..16000, an estimate
            max_bytes: int = 32768,              # 8192..131072, a hard limit
            as_of: int | None = None, cursor: str | None = None) -> dict
```

Result:

```json
{"items": [{"ref": "…@nt_…", "kind": "finding", "role": "evidence", "standing": "approved", "current": true,
            "origin": "model", "text": "…", "withheld": null, "class_key": "cwe-89",
            "scope": {"repo": "adc", "branch": "main", "paths": ["src/db/**"]}, "observed_commit": "…",
            "written_at": "2026-10-27T10:00:00Z", "recurrence": 3, "links": {"contradicts": 1},
            "citations": [{"ref": "adc@…:src/db/q.py:40-52", "status": "stale", "moved_to": 61}]}],
 "left": [], "books": ["adc-memory"], "watermark": 81234, "next_cursor": null,
 "excluded": {"code": 2, "needs_context": 1}, "targets": {"adc-memory/adc": "3f2c…"}}
```

- **No model call.** No embedding, no reranker. `ask_library` stays the escalation path.
- **Deterministic.** The same request on the same memory rows, rights and targets gives the same bytes. Order: `newest` = `seq` descending; `oldest` = ascending; `relevance` = `ts_rank_cd` descending, then `seq` descending. Keys are in a fixed order. The correlation id goes in `_meta` (MCP) or a header (HTTP), not in the body, so the body can stay in a provider prompt cache.
- **Size.** The server counts the **whole** serialized response, envelope included. `budget_tokens` is an **estimate** (UTF-8 bytes ÷ 4, rounded up); `max_bytes` is a hard limit. Items are added in order while both hold. If the first item alone does not fit, its text is cut until the whole response fits and `text_cut: true` is set (`max_bytes ≥ 8192` leaves room for one item with all its metadata: 20 citations, counts, scope). `next_cursor` (opaque: watermark + last sort key) continues at the next item and implies `as_of`.
- **Counts over the visible graph.** `links` counts, `unfixed`, `collapse` and contradiction handling use only edges whose other end the caller may read now. `unfixed` = a finding with no `fixed_by` edge to a readable note that is `approved` or `pending`. `collapse` = one item per book-local cluster (the newest current member); two members joined by `contradicts` are never collapsed together. If the final decision loses a book, the whole query, counts included, runs again (as `search.search`).
- **Item `links`** gives only non-zero counts per type. The agent calls `neighbours` for the edges.

### 9.2 One "current" predicate for every read

`query_notes`, `neighbours` and `open_citation` take the same **context** (`repo`, `branch`, `path`, `commit`) and call one function, `notesquery.current(note, ctx, w)`. A note is current when all are true (`docs/09` §2.3):
1. its effective Standing at `w` is `approved`;
2. its Time is `durable` (a `test_result` is never current);
3. **scope:** for each dimension that the note bounds (repo, branch, paths), the context value must match if the request gives it. If the request does not give it: a `rule` note is excluded (`needs_context`); an `evidence` note is shown with its scope;
4. **code:** for each code citation into a repository that has a target in the context, the status must be `verified`. `stale`, `missing` and `unverifiable` all exclude the note (`excluded.code`). A failed check never restores authority. Citations into repositories without a target are `not_checked` and do not change the result.

**Targets** are per `(book, repo)`: with `repo` and `commit`, each requested book where the slug is registered gets that commit as its target; with `repo` and `branch`, each such book resolves `refs/heads/<branch>` in its own repository. The response lists the targets under `"<book>/<repo>"`.

`include_unverified: true` returns the notes excluded by rule 4 with `current: false` and their statuses. Standing never changes (R1).

| Set | Contains |
|---|---|
| `current` | the notes above |
| `open` | `pending` notes, marked "not accepted" |
| `history` | `rejected`, `retired` (with the successor by `supersedes`), and `test_result` notes |

**A pending note is never in `current`.**

Path matching: a glob in `scope_paths` uses `**` (any characters), `*` (any except `/`), `?` (one character except `/`). The request `path` is one path, or a directory prefix that ends with `/`.

### 9.3 `neighbours` (MCP) / `GET /v1/notes/{book}/{id}/neighbours` (HTTP)

```
neighbours(ref: str,                            # a note reference or a passage handle
           types: list[str] | None = None, depth: int = 1,       # depth 1 or 2
           direction: str = "both",             # out | in | both
           sets: list[str] = ["current"],
           repo: str | None = None, branch: str | None = None, path: str | None = None, commit: str | None = None,
           max_nodes: int = 50, budget_tokens: int = 2000, max_bytes: int = 32768,
           as_of: int | None = None) -> dict
-> {"root": item | null, "nodes": [item], "edges": [{"src": ref, "type": str, "dst": ref}],
    "targets": {…}, "watermark": int, "truncated": bool}
```

Postgres only (two joins on `note_link`), no graph database. Order: breadth first, then link `seq` ascending. A node is included only when the caller may read its book now and it is in `sets` under the shared predicate (§9.2). An edge to an excluded node is dropped and not counted. With a passage handle, `root` is null and the nodes are the notes linked to it (`about`, `derived_from`).

### 9.4 Notes in `open_citation`

`open_citation(handle)` accepts a note reference too, with the optional context. It returns one item with the full text and any Standing, and `current` from the shared predicate. It needs `read`.

**Notes are not in `search_library` or `ask_library` in R1** (operator decision).

### 9.5 Watermark, `as_of`, `since`, tombstones

- `watermark` = the highest `memory_seq` visible to the request. The advisory lock (§4) makes `seq` order equal to commit order.
- **`as_of = w`** evaluates every memory row with `seq ≤ w`: notes, links (so clusters), write records (so recurrence and origin), Standing events. Rights, journal restrictions, repository registrations and code targets are evaluated **now**. So a replay gives the same bytes only when those did not change; otherwise it can only lose items or change citation statuses.
- **`since = w`** returns:
  - `items`: notes in the requested sets now that have a memory event after `w` (written, linked, a Standing event, or a recurrence);
  - `left`: tombstones `{ref, standing, seq, successor}` for readable notes that a Standing event after `w` moved **out** of the requested sets (retired, rejected, reopened to `pending`, superseded);
  - `books`: the books that the caller may read now. A client drops cached items of any other book.
- **Code targets:** a `since` result is complete only for the same targets. The response gives `targets`; when a branch head moved (another commit for a `"<book>/<repo>"`), the client queries again without `since`. Git objects do not change, so for a fixed commit the statuses change only through a repository removal or a ref change (`unverifiable`), which the next full query shows.
- `subscriptions/listen` waits for R2 (§12.1).

## 10. Code citations and the verifier (#70)

### 10.1 Syntax

`<repo>@<commit>:<path>:<start>[-<end>][#<symbol>]`, for example `adc@3f2c…e1:src/run.py:40-52#retry_job`.
- `repo`: a registered slug **of the note's own book**; `commit`: the full hex id (no short ids, no branch names);
- `path`: `ids.normalize_path`, plus no control characters (U+0000–U+001F, U+007F; `normalize_path` alone accepts LF, CR and NUL); parsed from the right, so a path can contain `:`;
- at most 200 lines; `symbol` is a label for the search after a move.

### 10.2 Repositories

- `kutuphane repo add <book> <slug> <git_dir> --ref 'refs/heads/*' [--ref …]` (CLI, administrator only). `kutuphane repo remove` sets `removed_at`. Each `--ref` passes `git check-ref-format --normalize --allow-onelevel` with `*` allowed once.
- **Kütüphane never fetches.** The operator keeps a bare mirror current (a cron `git fetch`) or mounts one read-only. The verifier needs no network and no credentials, and works air-gapped.
- **Confinement checks** (Python file APIs, at `add` and at each open; a failure is `unverifiable: repo_invalid`):
  - `realpath(git_dir) == git_dir` (no symlink in the path), inside one of `KUTUPHANE_REPO_ROOTS`;
  - a **bare** repository directory: `HEAD`, `config`, `objects/` exist; `git_dir` is a directory, not a gitfile;
  - no `commondir`, no `objects/info/alternates`, no `objects/info/http-alternates`, no `objects/pack/*.promisor`; `realpath(objects)` is inside `git_dir`;
  - every key of `config` (read by `git config --file <git_dir>/config --null --list`, with no includes) is in an allowlist: `core.repositoryformatversion`, `core.bare`, `core.filemode`, `core.ignorecase`, `core.precomposeunicode`, `core.logallrefupdates`, `extensions.objectformat`, `remote.<name>.url`, `remote.<name>.fetch`, `remote.<name>.mirror`. Any other key (for example `extensions.partialclone`, `remote.*.promisor`, `include.*`, `includeIf.*`, `core.alternateRefsCommand`) refuses the repository.
- **Which commits are visible:** a commit can be cited or verified only if one of the registered `refs` reaches it. Existence in the object store is not enough: a mirror can hold unreachable objects (for example a force-pushed secret).
- The container mounts the repository roots read-only and has `git` ≥ 2.45 (`GIT_NO_LAZY_FETCH`, `cat-file -z`).

### 10.3 How it reads

- **Process:** no shell; argument vectors only; `git --git-dir=<git_dir> -c safe.directory=<git_dir> -c core.fsmonitor=false …`.
- **Environment:** built from nothing, not inherited: `PATH=/usr/bin:/bin`, `LC_ALL=C`, `HOME=/nonexistent`, `GIT_CONFIG_NOSYSTEM=1`, `GIT_CONFIG_GLOBAL=/dev/null`, `GIT_NO_REPLACE_OBJECTS=1`, `GIT_NO_LAZY_FETCH=1`, `GIT_TERMINAL_PROMPT=0`, `GIT_OPTIONAL_LOCKS=0`, `GIT_PROTOCOL_FROM_USER=0`, `GIT_ALLOW_PROTOCOL=` (empty). So `GIT_DIR`, `GIT_OBJECT_DIRECTORY`, `GIT_ALTERNATE_OBJECT_DIRECTORIES` and `GIT_COMMON_DIR` never reach git.
- **Commands** (only these; hex values pass a regex first; every argument list ends options with `--end-of-options` where git accepts it):
  - commit: `rev-parse --verify --end-of-options <hex>^{commit}`;
  - reachability: `for-each-ref --format=%(objectname) -- <patterns>` (at most 50 tips), then `merge-base --is-ancestor <commit> <tip>` until one succeeds; else `unverifiable: commit_not_published` (a write is refused);
  - branch: the name passes `git check-ref-format --branch`, `refs/heads/<name>` must match a registered pattern, then `rev-parse --verify --end-of-options refs/heads/<name>^{commit}`;
  - object: `cat-file --batch-check -z` with `<commit>:<path>` and a NUL terminator on stdin (control characters are refused before, so one input is one request). The output must be `<oid> blob <size>` with `size ≤ 2 MiB`; else `unverifiable: not_a_file` or `too_large`. Then `cat-file blob <oid>` with the validated `oid`. A NUL byte in the content is `unverifiable: binary`;
  - range: `commits = "A..B"` is split into two full hex ids; both must be reachable; then `rev-list --max-count=10001 --end-of-options <B> ^<A>` (more than 10,000 → 400).
- **Limits:** 5 s per command (`unverifiable: timeout`); 200 citations per request. Caches live for one request and use the key `(book, repo, commit, path)`.
- **Excerpt hash:** the cited lines, CRLF → LF, trailing white space removed per line, joined with `\n`, SHA-256. The write path stores it (§6.1 step 7).

### 10.4 Statuses

| Status | Condition | Effect when the repository has a target |
|---|---|---|
| `verified` | the excerpt hash at the same lines in the target equals the stored one | none |
| `stale` | the file exists, the lines differ. `moved_to` = the first line where the same excerpt starts, if it occurs exactly once; else, with a symbol, `symbol_found_at` (whole-word matches, at most 5 lines) | not current |
| `missing` | the path does not exist at the target | not current |
| `unverifiable` + reason | `repo_removed`, `repo_invalid`, `commit_unknown`, `commit_not_published`, `branch_unknown`, `not_a_file`, `too_large`, `binary`, `timeout` | **not current** (a failed check never restores authority) |
| `not_checked` | the repository has no target in the request | — |

The status is a machine signal. It never changes Standing (#70, R1). No output contains code text.

### 10.5 `verify_citations` (MCP) / `POST /v1/citations/verify` (HTTP)

```
verify_citations(book: str, citations: list[str], at: str) -> dict   # at: a branch name or a full commit id
-> {"targets": {"adc-memory/adc": "…"}, "results": [{"citation": "…", "status": "stale", "moved_to": 61, "reason": null}]}
```

It needs `read` on `book` (the repositories are that book's). It is logged as `action = verify` with the citations as items.

## 11. Gates on every new path

All new reads use the gates of `search_library`: one `authz.allowed` statement as the pre-filter, one more as the final check at the linearization point, one rerun when a book was lost, then `SearchChanged`. Each delivery is an `access_event` with `memory_seq` = the watermark and `items` = `[{ref, standing_seq}]`.

| Path | Modes (before **and** at the final decision) | Text gate | Standing | Model call |
|---|---|---|---|---|
| `propose_note` | `propose` on the journal; `read` on every cited and linked book; `read` on the journal sets the receipt level | candidate text: `ai_input` | new: `pending`; existing: unchanged | embedding only, after authorization; note `search` and `ai_input`; egress = note `source_books` |
| `link_notes` | `propose` on the `src` book; `read` on the `dst` book | — | unchanged | none |
| `query_notes` | `read` | `ai_input` (note AND journal) for model readers | `sets`, shared predicate | none |
| `neighbours` | `read` on the root and every node | `ai_input` | `sets`, shared predicate | none |
| `open_citation` (note) | `read` | `ai_input` | shown | none |
| `verify_citations` | `read` on the book of the repositories | no code text | — | none |
| set Standing | CLI only, curator credential (§8.2) | — | the act | none |
| `job_status` / `job_result` / `job_cancel` | the `reopen_answer` visibility (§12.2); `job_result` decides current rights | as `reopen_answer` | — | none |

"Model reader" is unchanged: `server._for_model` (MCP callers and `agent:` principals). The `text` filter, relevance order and candidates use only notes whose note and journal `search` are true. A note is never an agent instruction in R1: skills stay in file books with `activate` (D37).

## 12. MCP 2026-07-28, long operations, headless auth (#73)

### 12.1 What 2026-07-28 changes for our server

Verified against the spec changelog (<https://modelcontextprotocol.io/specification/2026-07-28/changelog>) and the Python SDK v2 guides (<https://py.sdk.modelcontextprotocol.io/whats-new/>, <https://py.sdk.modelcontextprotocol.io/migration/>). `mcp` 2.3.0 is the latest release (2026-10-02).

| Change | Effect on Kütüphane | Action |
|---|---|---|
| SDK v2: `FastMCP` → `MCPServer` (`from mcp.server import MCPServer`); `stateless_http`, `transport_security` move to `streamable_http_app(...)`; `ToolError` from `mcp.server.mcpserver.exceptions` | `server.build_mcp` does not import | pin `mcp>=2.3,<3`; move the two arguments; keep the host lifespan that enters `mcp.session_manager.run()` |
| SDK v2: `MCPServer.call_tool()` returns a `CallToolResult`; a `ToolError` becomes `is_error=True`, not an exception | `tests/test_server.py::call_tool` unpacks `(content, structured)` and expects raised errors | migrate the test adapter: return `(result.content, result.structured_content)`, raise on `result.is_error` with the message text |
| SDK v2 wraps a `list` return as `{"result": [...]}` in `structuredContent`, as v1 did | `search_library` clients read `structuredContent.result` | keep it on purpose; a test asserts the exact shape for both protocol versions |
| auth surface (`TokenVerifier`, `AccessToken`, `AuthSettings`, `get_access_token`) | unchanged | `_Verifier` adds `client_id` to the claims |
| no `initialize`, no `Mcp-Session-Id`; `_meta` per request; `server/discover` | we are already stateless; the SDK serves both eras from one app | none. Cross-call state is explicit handles: note refs, watermarks, cursors, job ids, answer ids |
| `Mcp-Method` / `Mcp-Name` headers required; mismatch → `-32020` | the SDK checks them | the reverse proxy must pass them; a boundary test (T33) |
| a broken response stream loses the request; the client re-sends it with a new id | a committed propose or job could run twice | idempotency keys (§6.4, §12.2) |
| `_meta` `clientInfo` | not authenticated | never used for origin or rights (§5.1) |
| `tools/list` deterministic, `ttlMs`/`cacheScope` | good for prompt caches | register tools in a fixed order; set `cache_hints` |
| Tasks moved to the `io.modelcontextprotocol/tasks` extension; **the Python SDK does not implement it** | no native tasks | the durable job (§12.2). When the SDK has the extension, a task maps one-to-one to an `ask_job` row. |
| MRTR replaces server-initiated elicitation; `elicitation/complete` removed | needed only for R3 | none in R1 (§5.3) |
| `subscriptions/listen` replaces GET streams and `resources/subscribe` | we have no subscriptions | R1 uses `since` polling with tombstones (§9.5); a feed waits for R2 |
| sampling, roots, logging deprecated; `ping` removed | not used | none |
| 4 MiB default body limit | our largest input is about 200 KB | none |
| RFC 9207 `iss`, CIMD over DCR, credentials bound to the issuer | client and IdP matters | none in the resource server |

### 12.2 Long operations: durable jobs

- `ask_library(…, background: bool = False, idempotency_key: str | None = None)`. With `background = true`, it returns `{"job_id": "jb_…", "status": "queued"}` at once. HTTP: `POST /v1/ask` with `"background": true` → `202`.
- **Idempotency:** the same rules as §6.4, scoped to `(principal, on_behalf_of)`. A retry returns the original job. The key lives as long as the job row.
- `job_status(job_id) -> {status, created_at, started_at, finished_at, error}`; `job_result(job_id)` = `reopen_answer` of the stored answer; `job_cancel(job_id)`. HTTP: `GET /v1/jobs/{id}`, `GET /v1/jobs/{id}/result`, `POST /v1/jobs/{id}/cancel`.
- **One visibility policy for both handles**, the one of `answers.reopen`: the same context (the same principal **and** the same `on_behalf_of`), or the user that the job was made for, calling directly. Anyone else gets "not found". `job_result` and `reopen_answer` then decide current rights on every source book in one statement, so a revoked delegation sees the status but gets no result. After the job row is deleted, the answer id stays reopenable under the same policy.
- Workers run in the server process (`KUTUPHANE_JOB_WORKERS`, default 1). They claim with `FOR UPDATE SKIP LOCKED` and renew `lease_until`. The worker runs `answers.ask` with the job's principal and `on_behalf_of`, so a right lost before the run fails the job. At most 3 open jobs per principal.
- Finished jobs are deleted after 7 days (with their idempotency keys). The answer and its audit rows stay.
- **Not in R1:** `ingest`, `index`, `approve-import` over MCP or HTTP (operator decision; `approve-import` never on MCP).

### 12.3 What does not change

`search_library`, `reopen_answer`, `read_document`, `record_runbook_feedback` keep their signatures and result shapes. `open_citation` also accepts note references (§9.4).

### 12.4 Headless authentication

The IdP issues all tokens. Kütüphane stores no client secrets and accepts no static API keys.

| Client | Token | Actor | Needs |
|---|---|---|---|
| an orchestrator on its own rights | OAuth client credentials (client secret or `private_key_jwt`; MCP extension `io.modelcontextprotocol/oauth-client-credentials`); the IdP mapper sets `kutuphane/principal_type: agent`, `sub` = the agent name | `agent:adc`, no `on_behalf_of` | direct grants to `agent:adc` (`read`, `propose`) |
| an orchestrator for a person, headless | RFC 8693 token exchange at the IdP: subject token = the person's (from a one-time interactive consent), actor token = the client-credentials token → `sub` = person, `act.sub` = agent | `agent:adc` on behalf of `user:ayse` | a live delegation `user:ayse → agent:adc` per mode, and Ayşe's own right (unchanged, AT-05) |

- `client_id` (RFC 9068) or `azp` is recorded in `write_record.client_id`. It never changes origin or rights.
- If an IdP maps a machine client to a `user:` principal by mistake, its writes are still at most `unknown` (§5.2), and it cannot curate, because no Standing path exists on MCP or HTTP (§8.2).
- The server advertises the extension in `server/discover`.

## 13. HTTP equivalents

| MCP tool | HTTP | Success status |
|---|---|---|
| `propose_note` | `POST /v1/notes` | 201 (200 for an idempotent retry) |
| `link_notes` | `POST /v1/notes/links` | 201 (200 when the link exists) |
| `query_notes` | `GET /v1/notes?…` (list parameters repeat) | 200 |
| `neighbours` | `GET /v1/notes/{book}/{id}/neighbours?…` | 200 |
| `open_citation` (note) | `GET /v1/citation?handle=…` | 200 |
| `verify_citations` | `POST /v1/citations/verify` | 200 |
| `ask_library(background=true)` | `POST /v1/ask` `{…, "background": true}` | 202 (200 for an idempotent retry) |
| `job_status` / `job_result` / `job_cancel` | `GET /v1/jobs/{id}`, `GET /v1/jobs/{id}/result`, `POST /v1/jobs/{id}/cancel` | 200 |

There is **no** Standing route. New error classes: an idempotency key reused with another request → 409; the daily write limit and the open-job limit → 429. Others use the existing classes (400, 401, 403, 404).

## 14. Not in R1, and why R2 is not blocked

| Item | R1 | What R1 keeps ready |
|---|---|---|
| #77 curator queue | the CLI Standing act only | the risk order (§8.1), book-local clusters, one event per item, `client_id`, "proposed again after rejection". A batch act writes one event per note with one reason. |
| #79 rollback | none | creation-only `derived_from` (own links, database key), `cause_seq` for the root, `access_event.items` with note refs and `standing_seq`. Restriction already follows derivation (§6.2). |
| R3/R7 confirmation | none; R1 never stores `human` | §5.3 |
| change feed | `since` polling with tombstones | `memory_seq` order = commit order |
| journal export | `kutuphane export` refuses a journal | — |
| notes in `search_library`/`ask_library` | no | `note.source_books` for the egress check |

## 15. Test plan (consumer-visible regressions)

| # | Test | Slice |
|---|---|---|
| T1 | An agent (delegation) proposes over MCP: `pending`, origin `model`; `query_notes(sets=["open"])` finds it in the next call; `sets=["current"]` does not. | A, B |
| T2 | An agent requests `origin: human`: stored `model`, notice `origin-claim-refused`. A direct SQL insert of `human` fails; `unknown` for an `agent:` principal or with `on_behalf_of` fails. | A |
| T3 | A `user:` token without `act`: over MCP `model`; over HTTP `unknown`, also with a fresh login from the UI client id. Requesting `model` gives `model`. | A, D |
| T4 | No `propose` right, or no `read` on a cited book: refused and logged; **no git process ran and no `model_call` row exists**. | A, C |
| T5 | A delegation revoked between the pre-decision and the commit (for the journal **or** for a cited book): rolled back and logged. | A |
| T6 | Credential-like text: refused; the response and the logs do not contain the value. | A |
| T7 | Same bytes twice: one note, `status: existing`, `recurrence: 2`, Standing unchanged. Same bytes after rejection: receipt `standing: rejected`; still `rejected`. | A |
| T8 | A case or white-space variant: a `normalized` candidate, two notes, no link. A similar text: a `vector` candidate, no link. | A |
| T9 | Re-proposing an existing note's text with other links creates another note; the original note's link set is unchanged. `link_notes` refuses `derived_from` and `supersedes`. | A |
| T10 | Database: a creation link with the `write_seq` of another note's propose, or of a non-creating propose, fails; a `same_as` link across books fails; a passage link to a missing chunk fails. | A |
| T11 | Idempotency: a retry with the same key gives the same receipt and no new write record; the same key with another body → 409; another principal or another `on_behalf_of` with the same key is independent. | A |
| T12 | A propose-only caller (no `read`) gets `status: recorded` for a new and for an existing note, with no candidates or counts. | A |
| T13 | Candidates never come from a book that the writer cannot read, nor from a `search: false` journal. | A |
| T14 | Journal `search: false`: no `tsv`, no vector; the `text` filter and relevance order never match its notes; `kind` filters still list them. | A, B |
| T15 | Journal `ai_input: false`: no `model_call` row; model readers get `text: null` with the reason; a person over HTTP gets the text. | A, B |
| T16 | A note citing an `ai_input: n` passage in an AI-enabled journal: `ai_input` false, no embedding; a note derived from that note: also false (transitive). A note derived from a `local_only` book on a cloud route: no call, `vector: skipped:egress`. | A |
| T17 | The app database role cannot insert, update or delete `standing_event`. No MCP tool and no HTTP route changes Standing (tool list and route list snapshot). | A, D |
| T18 | CLI: a curator without `curate` is refused; `curate` to an agent or a role, or as a delegation: the database refuses. | A |
| T19 | Approve → current. Reject → `history`, `standing: rejected`. Retire → `history`. Supersession retires a predecessor with the same scope, not one with another scope. | A, B |
| T20 | The same `query_notes` request twice gives byte-identical results. After new writes and a new `same_as` link, `as_of` gives the old clusters, recurrence and origin. | B |
| T21 | The whole response never exceeds `max_bytes`; the estimate never exceeds `budget_tokens` except one cut first item; `next_cursor` pages without gaps or duplicates. | B |
| T22 | Each filter: kind, role, origin, class key, repo/branch/path glob, `commits` range, time, `text`, `unfixed`. | B, C |
| T23 | A bounded `rule` without context: excluded in **both** `query_notes` and `neighbours`, `needs_context` counted. A bounded `evidence` note: shown with its scope. | B |
| T24 | Counts: a `contradicts` or `fixed_by` edge to a note in an unreadable book is not counted, does not mark a finding fixed, and is not in `neighbours`. | B |
| T25 | A right revoked during a query: the book is dropped, the query (counts included) runs again, the loss is logged. | B |
| T26 | `query_notes` and `neighbours` make no model call (`model_call` unchanged). | B |
| T27 | `since`: with concurrent writers, a poller sees every change once; after a retirement, the note is in `left`; after a lost right, its book is missing from `books`. | B |
| T28 | Audit: each delivered note has `standing_seq` (null before any event) and the event has `memory_seq`. | B |
| T29 | Verifier: `verified`; `stale` with `moved_to`; `missing`; `unverifiable` for an unknown commit, an unpublished commit (only reachable from an unregistered ref) and an unknown branch. | C |
| T30 | With a code target, a note whose citation is `stale`, `missing` or `unverifiable` (repository removed, timeout) is not current; `include_unverified` returns it with `current: false`. Two books with the same repo slug get two targets. | B, C |
| T31 | Paths with LF, CR, NUL, `../x`, `/etc/passwd`; `--upload-pack=x` as a branch; a short commit id; `A..B` with a branch name: refused. A path `a.py\nHEAD:secret` cannot cause a second object read. | C |
| T32 | Repository refusal at `add` and at open: a symlinked `git_dir`, a gitfile, `objects/info/alternates`, `commondir`, a `.promisor` pack, `extensions.partialclone`, `include.path` in `config`. A tree object or a blob above 2 MiB: `unverifiable`. | C |
| T33 | Both protocol versions (2025-11-25 with `initialize`, 2026-07-28 without), through the deployed reverse proxy: list tools (stable order), call `search_library` (`structuredContent.result` shape) and `propose_note`; no token → 401 with the resource metadata; `Mcp-Name` different from the body → `-32020`; an internal error gives only "internal error". | D |
| T34 | `tests/test_server.py` runs on SDK v2 with the migrated `call_tool` adapter; the error tests still check the safe messages. | D |
| T35 | `ask_library(background=true)`: a job id at once; status and result after a server restart; an expired lease → `failed: interrupted`; cancel before run → `cancelled`; a retry with the same key → the same job id, one model call. | D |
| T36 | Job visibility: agent X for user A submits. X for A: status and result. A directly: status and result. X for B: not found. X directly: not found. After A's delegation to X is revoked: X for A gets the status but no result. After cleanup, `reopen_answer` gives the same answers for the same callers. | D |
| T37 | A client-credentials token with the agent claim → `agent:`; a token-exchange token with `act` → `on_behalf_of`; `client_id` is in `write_record`; `_meta.clientInfo` changes nothing. | D |
| T38 | Migrations 016–018 apply to a database at 015 with data; grants and delegations stay. | A, C, D |

## 16. Implementation slices

**P0 (main agent, before the slices, one small commit):**
- `gate.Actor` gets `client_id=None`, `channel="cli"`;
- `gate.guard_many(conn, actor, needs: {object: {modes}}, work, *, action, items)`: one decision for all needs, the work in a transaction, one final decision for all needs in the same transaction, rollback and log on a loss (the many-object form of `gate.guard`);
- `ids.request_digest(args) -> bytes` (SHA-256 of `ids.canonical`);
- a loop in `server.py` that calls `register_mcp(mcp, deps)` and `http_routes(deps, endpoint)` of each feature module. After P0, slices A–C touch `server.py` only through these hooks.

| Slice | Issues | Migration | Owns (files) | Exposes |
|---|---|---|---|---|
| **A — notes write core** | #68, #69, #72, D70 | `016_notes.sql` | `notes.py` (new: journal, propose, rights by derivation, candidates, link, idempotency, Standing, supersession), `origin.py` (new), `authz.py` (modes), `profiles.py` (`journal` spec), `cli.py` (`journal create/restrict`, `note standing`), `deploy/` (the two database roles), `tests/test_notes.py`, `tests/test_origin.py` | the 016 DDL (this document is the contract); `notes.parse_ref`; `notes.effective_standing(conn, seqs, w) -> {seq: (value, event_seq)}`; `notes.clusters(conn, book, w)`; `notes.item_info(conn, note)` (kstd-shaped rights for `_text`); `origin.compute(actor, requested)` |
| **B — notes read path** | #71 | — | `notesquery.py` (new: `Context`, `current`, `query_notes`, `neighbours`, note `open_citation`, size limits, cursor, `since`/`left`, audit items), `tests/test_notes_query.py` | the tools and routes of §9; `notesquery.current(note, ctx, w)` is the only "current" predicate |
| **C — code citations** | #70 | `017_code_repo.sql` | `coderepo.py` (new: parse, registry, confinement checks, git runner, reachability, verify, `rev_list`), `cli.py` (`repo add/remove`), `Dockerfile`/`compose.yaml` (git ≥ 2.45, read-only mount), `tests/test_coderepo.py` | `coderepo.parse(text) -> CodeCitation`; `coderepo.excerpt(conn, book, cite) -> bytes` (raises `CitationRefused`); `coderepo.resolve_targets(conn, books, repo, branch, commit) -> {(book, repo): commit}`; `coderepo.verify_many(conn, targets, cites) -> list[Status]`; `coderepo.rev_list(conn, book, repo, a, b) -> list[str]`; the `verify_citations` tool and route |
| **D — protocol, jobs, auth** | #73 | `018_ask_job.sql` | `pyproject.toml`, `server.py` (SDK v2, `background` ask, job tools), `jobs.py` (new), `identity.py` (`client_id`), `devauth.py` (dev tokens with `client_id`), `tests/test_server.py` (adapter migration), `tests/test_identity.py`, `tests/test_jobs.py`, `deploy/` proxy test, README (auth) | the SDK v2 server; `Actor.client_id` from tokens; the job API |

Dependencies: B reads A's tables and calls `notes.effective_standing`, `notes.clusters`, `notes.item_info` and C's `resolve_targets`/`verify_many`/`rev_list`; A calls C's `parse`/`excerpt`. Each slice codes against these contracts and tests with the DDL of this document. Shared files: `cli.py` (A and C each add one command group) and `deploy/` (A: database roles; C: mount; D: proxy). Merge order: P0, then D, A, C, B. After all slices: one full test run (`pytest` with `KUTUPHANE_TEST_DSN`), then T33 against a running server behind the proxy.

## 17. Operator decisions (2026-10-27)

| # | Question in 0.1 | Decision |
|---|---|---|
| Q1 | notes in `search_library`/`ask_library` | no, not in R1 |
| Q2 | long operations over MCP | only `ask` as a job; `approve-import` never on MCP; `ingest`/`index` later with a new mode |
| Q3 | `contradicts` | yes, the eighth link type |
| Q4 | guard owner and due condition | the orchestrator keeps them; Kütüphane keeps `guard_due` and the accepted `convention` note |
| Q5 | stale code citations | not current at that target; returned only on request (now `include_unverified`, §9.2) |
| Q6 | thresholds | 0.90 similarity, 8,000 characters, 500 writes per day, 3 open jobs; measure in the first two weeks |
| Q7 | curation over HTTP | **no**: CLI only in R1 (§8.2) |

Decisions on the review: no `human` origin in R1 (#2); `same_as` and clusters inside one book (#6); only identical canonical bytes are automatic (#13); tombstones for readable notes that leave a set (#16); idempotency keys for propose and job submission (#19); no generic facet or job kind, and `rejected` stays a separate state (#22, D68).

## 18. Changes from 0.1 (Astra review)

| # | Finding | Change |
|---|---|---|
| 1 | HTTP curation | Standing route and its tests removed; CLI-only with a separate curator database credential; the app role cannot write `standing_event` (§4.1, §8.2, T17). |
| 2 | UI client id is not a human act | No `human` in R1: a direct user write is `unknown`; `user_verified`, `amr`, `auth_time` and the UI client list removed; `channel` set only by entry points (§5). |
| 3 | work before authorization | Pre-decision before any git process or embedding; one final decision over all needs (`gate.guard_many`) (§6.1, T4, T5). |
| 4 | source `ai_input` not enforced | `search`/`ai_input`/`source_books` derived from the dependency closure, transitive through notes (§6.2, T16). |
| 5 | no journal search permission | `journal.search` (no default), `note.search`; no `tsv`, vector, `text` match or candidates without it (§4.1, §7, T14). |
| 6 | graph counts cross books | `same_as` and clusters in one book (database check); all counts over the readable graph; minimal receipt for propose-only callers (§6.1, §7, §9.1, T12, T24). |
| 7 | repository namespace | `(note_seq, book)` composite key; targets and caches per `(book, repo)` (§4.1, §9.2, §10.3, T30). |
| 8 | `cat-file` injection | Control characters refused; `-z` framing; type and size checked before content; `A..B` split into two validated ids (§10.1, §10.3, T31). |
| 9 | git confinement | Built environment, `GIT_NO_LAZY_FETCH`, bare repositories only, no alternates/commondir/promisor, config allowlist, reachability from registered refs (§10.2, §10.3, T32). |
| 10 | manufactured own links | Creation links are in the canonical body; a database key binds them to the creating write; `derived_from`/`supersedes` only at creation (§3, §6.3, T9, T10). |
| 11 | duplicate vs lifecycle | A duplicate keeps and returns its real Standing; renewed sightings are write records; reopen is curator-only (§6.1, T7). |
| 12 | link integrity | Structured passage endpoints with a foreign key; the link-to-write relation as database keys; `dst < src` makes creation links acyclic (§4.1, T10). |
| 13 | normalized merge | Normalized matches are candidates only (§7, T8). |
| 14 | "current" differs per API | One context-bearing predicate for all reads; any non-`verified` status at a target is not current (§9.2, §10.4, T23, T30). |
| 15 | `as_of` and clusters | No stored cluster; clusters, recurrence and origin from rows `≤ w`; the replay promise is narrowed (§7, §9.5, T20). |
| 16 | polling misses removals | `left` tombstones, `books`, and target rules for `since` (§9.5, T27). |
| 17 | audit lacks Standing | `access_event.memory_seq` and `items[].standing_seq` (§4.1, §11, T28). |
| 18 | job vs answer visibility | One policy, the one of `answers.reopen`, for jobs and answers, also after cleanup (§12.2, T36). |
| 19 | retries | Idempotency keys for `propose_note` and background `ask` (§6.4, §12.2, T11, T35). |
| 20 | SDK test break | Adapter migration, the list wrapper kept on purpose, boundary tests for both versions through the proxy (§12.1, T33, T34). |
| 21 | token budget | `budget_tokens` is an estimate over the whole response; `max_bytes` is a hard limit (§9.1, T21). |
| 22 | distinctions without behavior | `standing_event` (no facet column), `ask_job` (no kind column); `rejected` kept with its D68 behavior (§4, §8.2). |
