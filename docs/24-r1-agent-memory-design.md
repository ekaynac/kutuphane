# R1 design — agent memory, first slice

**Status:** DESIGN 0.1, 2026-10-27. Branch `docs/r1-design`. For the operator's decision (§17). No code changes.
**Language:** ASD-STE100 Simplified Technical English.
**DDL check:** the SQL of §4 applies on top of migrations 001–015 (PostgreSQL 17, pgvector 0.8). The D70, `curate` and Standing checks refuse the forbidden rows (probe inserts, 2026-10-27).
**Basis:** issues #67–#73, #77, #79; `docs/09` (ontology v2, D54); `docs/22` §4 (R1–R7, D70); `docs/23` (vision 1.0, D69); the code at `0c33d12` (migrations 001–015, `mcp` 1.30.0); the MCP 2026-07-28 changelog and the MCP Python SDK v2 migration guide (sources in §12).

**Rule for this document (D53):** each field and each value has a "changes" note. If a field changes no behavior, it is not in R1.

## 1. Summary of the decisions

| # | Decision | Section |
|---|---|---|
| 1 | Agent writes get their own unit: the **note**. A note is content-addressed (`nt_` + SHA-256 of its exact canonical body). A journal is a book whose items are notes, ordered by one global sequence. A journal is **not** a series of content versions. | §3 |
| 2 | Three migrations: `016_notes` (notes, write records, links, standing events, two new modes), `017_code_repo` (registered repositories), `018_job` (durable jobs). | §4 |
| 3 | The server computes origin (D70 R1, R2, R4, R6). Agent paths always store `model`. Database checks enforce R2. R3/R7 get a data slot only: the note id is the digest that a passkey will sign later. | §5 |
| 4 | Duplicates: the same exact bytes = the same note (one more write). A whitespace or case variant = an automatic `same_as`. A vector neighbour = a candidate only. The server never merges different text. `contradicts` keeps both notes. | §7 |
| 5 | Standing for notes uses append-only annotation events (`docs/09` §3). Only `user:` principals with the new `curate` mode set them, over HTTP with a fresh user-verified login, or over the CLI. MCP has no tool that changes Standing. | §8 |
| 6 | `query_notes` and `neighbours` are the fast reads: SQL only, no model call, deterministic order, a token budget, a watermark. | §9 |
| 7 | Code citations `repo@commit:path:line[-end][#symbol]` point into repositories that an administrator registers per book. The verifier reads git objects only, with no request text in a path or an argument. | §10 |
| 8 | MCP SDK `mcp` 1.30 → 2.3 (`FastMCP` → `MCPServer`). It serves 2026-07-28 and 2025-11-25 clients. The SDK does not implement the Tasks extension, so long operations use a durable `job_id`. In R1, the one long tool is `ask_library` (about 63 s). | §12 |
| 9 | Headless clients use OAuth client credentials at the IdP. The token maps to an `agent:` principal. On-behalf-of work uses RFC 8693 token exchange (`act`) and a live delegation, as today. | §12.4 |

## 2. What the code has today, and what is missing

| Area | Today (`0c33d12`) | Missing for R1 |
|---|---|---|
| Content | books, immutable content versions (`ct_`), chunks per (content, profile), vectors | a write path that is not a whole-book ingest |
| Ontology v2 | approved (D54), **not implemented**: no block, annotation or Standing tables | Standing events for notes, at minimum |
| Modes | `discover`, `read`, `use`, `activate` (+ `member`) | a write right (`propose`) and `curate` |
| Origin | kstd item `origin` from `kstd.yaml` only | origin from the write path (D70) |
| Search | `search_library` (FTS + vector + rerank), `ask_library` (about 63 s) | filtered, deterministic reads with no model call |
| Identity | JWT from the IdP; `act` → agent on behalf of a user | `client_id`, `amr`/`auth_time` for R4 |
| MCP | `mcp` 1.30 `FastMCP`, `stateless_http=True` | 2026-07-28; durable jobs |

## 3. The unit of agent writes (#69)

**Decision:** agent writes do **not** fit the book content-version model. They get their own unit, the note. The note keeps the content-hash principle at the level of one entry.

**Reasons:**
1. **Cost.** A content id covers all files of a version (`ids.content_id`). `catalog.publish` writes all chunks again for each new content id. One entry per version makes each write O(book), and the storage O(n²).
2. **Stable identity.** Links, duplicates, Standing events and citations need an id that never changes. A per-entry digest gives that. A log-segment version changes with each entry.
3. **D70 R3 needs it.** The passkey challenge must contain the digest of the exact bytes. The note id is that digest.
4. **No continuity problem.** `docs/09` §1.2 (continuity links, `approved → pending` on a text change) does not apply. A note never changes. A correction is a new note with a `supersedes` link.

**Rejected alternative:** a journal version = an ordered log segment as a content version. It fails reasons 1 and 2.

**The journal profile.** A journal is a book with `current_content = NULL` and `current_profile` = the `journal` profile:
`{"name": "journal", "components": {"notes": "kutuphane.notes@1", "normalizer": "nfc-casefold-ws@1"}, "settings": {"fts": "turkish", "max_chars": 8000}}`.
The profile id covers the normalizer and the FTS configuration, as for other profiles (D26). Because `current_content` is NULL, `search_library` never sees a journal (its pre-filter joins on `current_content`).

**One note = one block.** The writer gives the boundary. The ontology block rule (§1.1) does not cut notes. A note longer than 8,000 characters is refused, and the agent must split it.

**Note reference:** `<book>@nt_<64 hex>`. It names one note in one book. The same bytes in two books are two notes, because the rights of the books are different.

## 4. Tables and migrations

All memory rows take their `seq` from one sequence, `memory_seq`. Memory writes take one transaction-level advisory lock (`pg_advisory_xact_lock`) before `nextval`. So the `seq` order is the commit order, and a watermark never skips a row (§9.4). Agent write rates are low (tens per minute), so one lock is enough.

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

CREATE TABLE journal (
    book       text PRIMARY KEY REFERENCES book(slug),
    ai_input   boolean NOT NULL,             -- stated at creation; there is no default (docs/22 §3: missing = deny)
    created_by text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE note (
    seq          bigint PRIMARY KEY DEFAULT nextval('memory_seq'),
    book         text NOT NULL REFERENCES journal(book),
    id           text NOT NULL CHECK (id ~ '^nt_[0-9a-f]{64}$'),
    profile_id   text NOT NULL REFERENCES profile_version(id),
    kind         text NOT NULL CHECK (kind IN ('finding', 'decision_proposal', 'dead_end', 'convention', 'lesson',
                                               'test_result')),
    body         text NOT NULL CHECK (char_length(body) BETWEEN 1 AND 8000),
    norm_sha256  bytea NOT NULL,
    class_key    text CHECK (class_key ~ '^[a-z0-9][a-z0-9._:/-]{0,79}$'),
    scope_repo   text,
    scope_branch text,
    scope_paths  text[] NOT NULL DEFAULT '{}' CHECK (cardinality(scope_paths) <= 20),
    scope_path_re text[] NOT NULL DEFAULT '{}',
    observed_commit text CHECK (observed_commit ~ '^[0-9a-f]{40}([0-9a-f]{24})?$'),
    cluster      bigint NOT NULL,
    written_at   timestamptz NOT NULL DEFAULT now(),
    tsv          tsvector NOT NULL,
    UNIQUE (book, id),
    CHECK (cardinality(scope_paths) = cardinality(scope_path_re)),
    CHECK (scope_repo IS NOT NULL OR (scope_branch IS NULL AND scope_paths = '{}' AND observed_commit IS NULL))
);
CREATE INDEX note_book_seq ON note (book, seq);
CREATE INDEX note_norm     ON note (book, norm_sha256);
CREATE INDEX note_class    ON note (book, class_key) WHERE class_key IS NOT NULL;
CREATE INDEX note_scope    ON note (book, scope_repo, scope_branch);
CREATE INDEX note_cluster  ON note (cluster);
CREATE INDEX note_tsv      ON note USING gin (tsv);

-- One row per write act: a propose (new note or the same bytes again) or a link.
CREATE TABLE write_record (
    seq              bigint PRIMARY KEY DEFAULT nextval('memory_seq'),
    at               timestamptz NOT NULL DEFAULT now(),
    correlation_id   text NOT NULL,
    action           text NOT NULL CHECK (action IN ('propose', 'link')),
    note_seq         bigint REFERENCES note(seq),
    principal        text NOT NULL,
    on_behalf_of     text,
    channel          text NOT NULL CHECK (channel IN ('mcp', 'http')),
    client_id        text,
    user_verified    boolean NOT NULL,
    origin_requested text CHECK (origin_requested IN ('human', 'assisted', 'model', 'tool', 'unknown')),
    origin           text NOT NULL CHECK (origin IN ('human', 'model', 'unknown')),
    notice           text CHECK (notice IN ('origin-claim-refused')),
    CHECK ((action = 'propose') = (note_seq IS NOT NULL)),
    -- D70 R2 as a database guarantee: an agent path stores model, and nothing else
    CHECK (origin = 'model' OR (principal LIKE 'user:%' AND on_behalf_of IS NULL AND channel <> 'mcp')),
    -- D70 R4: human only from the registered UI with a fresh user-verified login
    CHECK (origin <> 'human' OR (channel = 'http' AND user_verified AND client_id IS NOT NULL)),
    CHECK (notice IS NULL OR origin_requested IS NOT NULL)
);
CREATE INDEX write_record_note      ON write_record (note_seq, seq) WHERE note_seq IS NOT NULL;
CREATE INDEX write_record_principal ON write_record (principal, at);

CREATE TABLE note_citation (
    note_seq    bigint NOT NULL REFERENCES note(seq),
    n           smallint NOT NULL CHECK (n BETWEEN 1 AND 20),
    book        text NOT NULL,                                   -- = note.book (repository namespace)
    kind        text NOT NULL CHECK (kind IN ('passage', 'code')),
    -- passage: a version-pinned handle book@ct_…/pf_…/path#ordinal
    cite_book   text, content_id text, profile_id text, ordinal integer,
    path        text NOT NULL,
    -- code: repo@commit:path:start[-end][#symbol]
    repo        text, commit text, line_start integer, line_end integer, symbol text, excerpt_sha256 bytea,
    PRIMARY KEY (note_seq, n),
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
    seq       bigint PRIMARY KEY DEFAULT nextval('memory_seq'),
    src       bigint NOT NULL REFERENCES note(seq),
    type      text NOT NULL CHECK (type IN ('derived_from', 'same_as', 'about', 'fixed_by', 'violates', 'decided_by',
                                            'supersedes', 'contradicts')),
    dst_note  bigint REFERENCES note(seq),
    dst_cite  text,                                               -- a passage handle; derived_from and about only
    write_seq bigint NOT NULL REFERENCES write_record(seq),
    CHECK ((dst_note IS NULL) <> (dst_cite IS NULL)),
    CHECK (dst_cite IS NULL OR type IN ('derived_from', 'about')),
    CHECK (dst_note IS DISTINCT FROM src)
);
CREATE UNIQUE INDEX note_link_note ON note_link (src, type, dst_note) WHERE dst_note IS NOT NULL;
CREATE UNIQUE INDEX note_link_cite ON note_link (src, type, dst_cite) WHERE dst_cite IS NOT NULL;
CREATE INDEX note_link_dst ON note_link (dst_note, type) WHERE dst_note IS NOT NULL;
CREATE INDEX note_link_dst_cite ON note_link (dst_cite) WHERE dst_cite IS NOT NULL;

-- docs/09 §3: append-only annotation events. R1 uses one facet (Standing) on notes only.
CREATE TABLE annotation_event (
    seq            bigint PRIMARY KEY DEFAULT nextval('memory_seq'),
    note_seq       bigint NOT NULL REFERENCES note(seq),
    facet          text NOT NULL CHECK (facet = 'standing'),
    value          text NOT NULL CHECK (value IN ('approved', 'pending', 'rejected', 'retired')),
    set_by         text NOT NULL CHECK (set_by LIKE 'user:%' OR set_by = 'system'),  -- a user event is confirmed by set_by
    cause_seq      bigint REFERENCES annotation_event(seq),
    reason         text NOT NULL CHECK (char_length(reason) BETWEEN 1 AND 500),
    correlation_id text NOT NULL,
    at             timestamptz NOT NULL DEFAULT now(),
    CHECK ((set_by = 'system') = (cause_seq IS NOT NULL)),
    CHECK (set_by <> 'system' OR value = 'retired')               -- the system only tightens (docs/09 §3.2)
);
CREATE INDEX annotation_note ON annotation_event (note_seq, facet, seq DESC);

CREATE TABLE note_vector (
    note_seq  bigint NOT NULL REFERENCES note(seq),
    model     text NOT NULL,
    embedding vector NOT NULL,
    PRIMARY KEY (note_seq, model)
);
```

### 4.2 Field → behavior (016)

| Field | Changes |
|---|---|
| mode `propose` | who may write notes and links into a journal. Agents get it by a direct grant or a delegation. Off by default. |
| mode `curate` | who may set Standing. A database check allows only `user:` subjects. Delegation cannot carry it. |
| `journal.ai_input` | `false`: the note text is withheld from model readers (MCP, agents), and no embedding call is made. |
| `note.id` | identity, exact-duplicate merge, the note reference, the future R3 passkey challenge |
| `note.profile_id` | which normalizer and FTS configuration made `norm_sha256` and `tsv`. Hashes compare only within one profile. |
| `note.kind` | the default Role and Time (§8.1), the #77 risk order, the `kind` filter |
| `note.body` | the content; FTS |
| `note.norm_sha256` | the automatic `same_as` for whitespace and case variants (§7) |
| `note.class_key` | grouping (`class_count`), the `class_key` filter, `guard_due` (§7) |
| `scope_repo`, `scope_branch`, `scope_paths` | the Scope facet: current only when the request context matches (§9.2) |
| `scope_path_re` | the SQL match of the globs (derived from `scope_paths` by one deterministic function) |
| `observed_commit` | the `commits` range filter (§9.1) |
| `cluster` | `same_as` component: recurrence, `collapse`, #77 groups. A new note takes one `nextval` for both `seq` and `cluster`. |
| `written_at` | the time filters |
| `tsv` | the `text` filter, with no model call |
| `write_record.*` | origin (§5); the per-principal daily write limit; the #79 report; "own links" (below) |
| `note_citation` | citation display; the verifier (§10); passage citations need `read` at write and at read |
| `note_link.type` | see §6.3 |
| `note_link.write_seq` | who claimed the link. A link whose `write_seq` is the propose of its `src` note is an **own link**. #79 rollback can follow own `derived_from` links only, so another agent cannot attach notes to a poisoned note to get them retired. |
| `annotation_event.*` | effective Standing = the latest event, else `pending`; `cause_seq` names the root of a system move (supersession now, #79 rollback later) |
| `note_vector` | vector candidates (§7) |

### 4.3 `017_code_repo.sql` (slice C)

```sql
CREATE TABLE code_repo (
    book          text NOT NULL REFERENCES journal(book),
    slug          text NOT NULL CHECK (slug ~ '^[a-z0-9][a-z0-9._-]{0,62}$'),
    git_dir       text NOT NULL CHECK (git_dir LIKE '/%'),
    object_format text NOT NULL CHECK (object_format IN ('sha1', 'sha256')),
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
| `(book, slug)` | the repository namespace of a journal's scopes and code citations; the verifier needs `read` on `book` |
| `git_dir` | where the verifier reads objects. It must be inside `KUTUPHANE_REPO_ROOTS` (checked at `add` and at each open). |
| `object_format` | the commit id length that the parser accepts (40 or 64 hex) |
| `removed_at` | the verifier answers `unverifiable: repo_removed`; new scopes and citations into the repository are refused |

### 4.4 `018_job.sql` (slice D)

```sql
CREATE TABLE job (
    id                  text PRIMARY KEY CHECK (id ~ '^jb_[0-9a-f]{32}$'),
    kind                text NOT NULL CHECK (kind IN ('ask')),
    principal           text NOT NULL,
    on_behalf_of        text,
    correlation_id      text NOT NULL,
    params              jsonb NOT NULL,
    status              text NOT NULL CHECK (status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')),
    created_at          timestamptz NOT NULL DEFAULT now(),
    started_at          timestamptz,
    lease_until         timestamptz,
    finished_at         timestamptz,
    cancel_requested_at timestamptz,
    answer_id           text REFERENCES answer(id),
    error               text CHECK (char_length(error) <= 500),
    CHECK (status <> 'succeeded' OR answer_id IS NOT NULL)
);
CREATE INDEX job_owner ON job (principal, created_at DESC);
CREATE INDEX job_open  ON job (created_at) WHERE status IN ('queued', 'running');
```

| Field | Changes |
|---|---|
| `kind` | which operation runs. Only `ask` in R1; a new kind needs a migration and a rights decision (Q2). |
| `principal`, `on_behalf_of` | only this caller can see, read or cancel the job. Others get "not found". |
| `params` | the request, run by the worker with the caller's rights at run time |
| `status`, timestamps | `job_status` |
| `lease_until` | a running job whose lease ended (a crashed or stopped server) becomes `failed: interrupted`. `ask` is not idempotent (model cost), so it does not run again. |
| `cancel_requested_at` | the worker checks it before the model call and before it stores the result |
| `answer_id` | `job_result` reopens the stored answer through the normal gate (current rights, AT-07) |
| `error` | a short, safe message (the same classes as HTTP errors) |

## 5. Origin from the write path (D70)

### 5.1 Inputs

| Input | Source | Never from |
|---|---|---|
| `principal`, `on_behalf_of` | the verified JWT (`identity.py`) | headers, tool arguments |
| `channel` | the server entry point: `mcp` or `http` | the client |
| `client_id` | the JWT claim `client_id` (RFC 9068), else `azp` | `_meta.io.modelcontextprotocol/clientInfo` (it is not authenticated) |
| `user_verified` | `amr` contains a value of `KUTUPHANE_UV_AMR` (default `pin,fpt,face,mfa`) **and** `now - auth_time ≤ KUTUPHANE_UV_MAX_AGE` (default 300 s) | — |
| `origin_requested` | the optional `origin` argument | — |

`gate.Actor` gets three fields with safe defaults: `client_id=None`, `user_verified=False`, `channel="cli"`.

### 5.2 Rules

```
computed:
  R2  principal is agent:*, or on_behalf_of is set, or channel = mcp      -> model
  R4  channel = http, principal is user:*, client_id in KUTUPHANE_UI_CLIENT_IDS, user_verified -> human
  R6  else                                                                  -> unknown
stored:
  requested is None or requested = computed  -> computed
  requested = model                          -> model           (a lower value is always allowed, R1)
  requested = unknown                        -> computed if computed = model, else unknown
  any other requested value                  -> computed, notice = origin-claim-refused   (R1, R2)
note origin (shown) = the lowest stored origin over all propose writes of the note (model < unknown < human)
```

`unknown` is shown as `unknown` and handled as `model` everywhere (kstd `AI_GENERATED`).

### 5.3 R3 and R7: a data slot only

R1 builds no confirmation path. The data model allows it later without a change to R1 tables:
- the note id is the SHA-256 of the exact canonical body, so a passkey challenge can contain it;
- `write_record.origin_requested` with `notice = origin-claim-refused` is the open confirmation request. It is a derived view, not a row;
- a later migration adds `origin_confirmation (note_seq, note_id, confirmed_by user:, choice human|assisted, credential_id, at, withdrawn_at)`. Then the shown origin = the latest live confirmation, else §5.2. `withdrawn_at` is R7.
- MCP 2026-07-28 removes `notifications/elicitation/complete`. R3 will use URL-mode elicitation inside a multi-round-trip request, with the note id in `requestState`.

## 6. The write path

### 6.1 `propose_note` (MCP) / `POST /v1/notes` (HTTP)

```
propose_note(book: str, kind: str, text: str,
             citations: list[str] = [],            # ≤ 20: passage handles or code citations (§10.1)
             scope: {repo: str, branch?: str, paths?: list[str]} | None = None,
             commit: str | None = None,             # observed_commit; needs scope.repo
             links: list[{type: str, ref: str}] = [],  # ≤ 20; from the new note to ref
             class_key: str | None = None,
             origin: str | None = None) -> dict
```

Steps (the order matters):
1. Validate the arguments. Run `secretscan.findings(text)`. A finding refuses the note and returns the rule names, never the matched text.
2. Check the daily limit: `KUTUPHANE_NOTE_WRITES_PER_DAY` per principal (default 500), counted in `write_record`.
3. Build the canonical body `{v:1, kind, text (NFC), class_key, scope, commit, citations (canonical, in order)}` and `id = nt_ + sha256(canonical JSON)`.
4. For each code citation, read the excerpt at the cited commit (§10.3). An unknown repository, commit, path or line refuses the note.
5. If `journal.ai_input` is true and an embeddings route exists: embed the text **before** the transaction (no lock during a model call). `source_books` = the journal + every book that a citation or a `derived_from` link names, so the strictest egress applies (`llmdap._check_egress`). A refusal or a failure does not stop the write; the result says `vector: skipped:<reason>`.
6. `gate.guard(book:<journal>, ["propose"])` with the insert as its work, as `feedback.record` does. Inside the transaction: the advisory lock; `read` on every cited or linked book (`gate.check_many`); insert or find the note; insert `write_record`, citations, links, vector; the automatic `same_as` (§7); collect the candidates. The final decision is in the same transaction: a revoked right rolls everything back.

Result:

```json
{"ref": "adc-memory@nt_3f…", "status": "created", "standing": "pending",
 "origin": "model", "origin_notice": null,
 "candidates": [{"ref": "adc-memory@nt_9a…", "match": "vector", "similarity": 0.93, "kind": "finding",
                 "standing": "approved", "text": "first 300 characters, or null", "withheld": null}],
 "linked": [{"type": "same_as", "ref": "adc-memory@nt_77…"}],
 "recurrence": 1, "class_count": 2, "guard_due": true, "vector": "stored"}
```

`status: existing` means the same bytes were already in the book: one more `write_record`, `recurrence` + 1, no new note.

### 6.2 `link_notes` (MCP) / `POST /v1/notes/links` (HTTP)

```
link_notes(src: str, type: str, dst: str) -> {"link": int, "src": str, "type": str, "dst": str}
```

Needs `propose` on the book of `src` and `read` on the book of `dst`. It writes one `write_record` (`action = link`) and one `note_link`. Links are append-only in R1. A `supersedes` link that closes a cycle is refused. A finding that a later note fixes: `link_notes(src=finding, type=fixed_by, dst=fix)`.

### 6.3 Link types

| Type | Direction | Changes in R1 | Later |
|---|---|---|---|
| `derived_from` | new → source (note or passage) | `neighbours`; embedding egress (§6.1 step 5) | #79 rollback (own links), restriction follows derivation |
| `same_as` | either | `cluster`, recurrence, `collapse`, #77 groups | — |
| `contradicts` | either | never in one collapsed item; both notes show it in `links` counts | #77 shows both |
| `about` | note → note or passage | `neighbours` from a passage handle | — |
| `fixed_by` | finding → fix | the `unfixed` filter | — |
| `violates` | finding → rule note | `neighbours`; counts on the rule | #77 risk |
| `decided_by` | note → decision note | `neighbours` | — |
| `supersedes` | successor → predecessor | system retirement on approval (§8.3) | — |

`contradicts` is not in the list of #71. #72 needs it ("keep both, link them"), so it is here (Q3).

## 7. Duplicates and equal concerns (#72)

| Match | Test | Result |
|---|---|---|
| same bytes | the same `id` in the same book | the same note; one more write; `recurrence` + 1 |
| same text | equal `norm_sha256` (NFC, case fold, white space collapsed), the same `kind`, `class_key` and scope, in the same book | a new note **and** an automatic `same_as` link (`write_seq` = this propose) |
| similar text | cosine similarity ≥ `KUTUPHANE_NOTE_DUP_SIMILARITY` (default 0.90, Q6) on `note_vector` of the same model, in books the writer may `read` | a candidate only (top 5) |
| same class | the same `class_key` in the same book | a candidate (`match: class`, the 5 newest) |

Rules:
- **Never swallow a contradiction.** The server merges only identical bytes. It links only identical normalized text. It never decides that two different texts say the same thing. "X is safe" and "X is not safe" can be close vectors; they stay two notes. The agent decides with `link_notes` (`same_as` or `contradicts`).
- **No leaks.** Candidates come only from books that the writer may `read` now (one `authz.allowed` statement). Candidate text passes the `ai_input` gate.
- **Clusters.** A `same_as` link merges two components: `UPDATE note SET cluster = least(a, b) WHERE cluster IN (a, b)`, in the same transaction.
- **Recurrence** = the number of `propose` write records in the cluster. **`class_count`** = the number of distinct clusters with the class key in the book. **`guard_due`** = `class_count ≥ 2` and no note with that class key and kind `convention` is `approved`.
- **The guard itself:** Kütüphane records the need (`guard_due`) and, once accepted, the guard as a `convention` note with the class key. The orchestrator builds the test or the lint, and keeps the owner and the due condition in its own event log (#67 boundary; Q4).

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

`lesson` and `dead_end` differ only in the `kind` filter. That is a presentation behavior that the customers ask for (#68). R1 has no Role, Time or Scope events: the approval confirms the kind and the scope of the note as written. Changing them at approval is #77 (R2).

### 8.2 Transitions

| From → to | Actor | Path |
|---|---|---|
| (new note) → `pending` | system | implicit: no event = `pending` |
| `pending` → `approved` / `rejected` | curator | `POST /v1/notes/{book}/{id}/standing`, `kutuphane note standing` |
| `approved` → `retired` | curator | the same |
| `rejected` / `retired` → `pending` | curator (reopen) | the same |
| `approved` → `retired` | system | supersession (§8.3) |

**Who is a curator:** a `user:` principal with `curate` on the book, with no `on_behalf_of`. Over HTTP it also needs a registered UI `client_id` and `user_verified` (§5.1), so a script that holds a person's token cannot approve. The CLI is the operator's path. MCP has **no** tool for Standing. The database refuses an event whose `set_by` is an agent, a `curate` grant to an agent, and a delegation of `curate`.

When a curator approves a `rule` note, the response lists the current `rule` notes with the same `scope_repo` (`docs/09` §2.1). The curator decides; there is no automatic conflict decision.

### 8.3 Supersession (system, stricter)

When a curator approves note S, the system retires note P in the same transaction if all are true:
- S has an own `supersedes` link to P;
- the role of S is `rule`;
- P is `approved`, in the same book, with exactly the same scope (repo, branch, paths).

The event has `set_by = system`, `cause_seq` = the approval event of S. A partial scope overlap does nothing; the curator narrows or retires P. A successor that loses approval does not reopen P (`docs/09` §3.3).

## 9. The read path (#71)

### 9.1 `query_notes` (MCP) / `GET /v1/notes` (HTTP)

```
query_notes(book: list[str] | None = None,       # intersected with the readable books
            sets: list[str] = ["current"],       # current | open | history (§9.2); the Standing filter
            kind: list[str] | None = None, role: list[str] | None = None, origin: list[str] | None = None,
            class_key: str | None = None,
            repo: str | None = None, branch: str | None = None, path: str | None = None,
            commit: str | None = None,           # verification target; without it, `branch` resolves to its head
            commits: str | None = None,          # "A..B": observed_commit in git rev-list A..B (≤ 10,000)
            written_after: str | None = None, written_before: str | None = None,
            since: int | None = None,            # changes after this watermark (§9.4)
            text: str | None = None,             # websearch_to_tsquery over tsv; no model
            unfixed: bool = False,               # findings with no fixed_by link
            collapse: bool = False,              # one item per same_as cluster
            include_stale: bool = False,
            order: str = "newest",               # newest | oldest | relevance (text only)
            max_tokens: int = 2000,              # 200..16000
            as_of: int | None = None, cursor: str | None = None) -> dict
```

Result:

```json
{"items": [{"ref": "…@nt_…", "kind": "finding", "role": "evidence", "standing": "approved", "current": true,
            "origin": "model", "text": "…", "withheld": null, "class_key": "cwe-89",
            "scope": {"repo": "adc", "branch": "main", "paths": ["src/db/**"]}, "observed_commit": "…",
            "written_at": "2026-10-27T10:00:00Z", "recurrence": 3, "links": {"contradicts": 1, "fixed_by": 0},
            "citations": [{"ref": "adc@…:src/db/q.py:40-52", "status": "stale", "moved_to": 61}]}],
 "watermark": 81234, "next_cursor": null,
 "excluded": {"stale": 2, "needs_context": 1}, "target": {"repo": "adc", "commit": "…"}}
```

- **No model call.** No embedding, no reranker. `ask_library` stays the escalation path.
- **Deterministic.** The same request on the same data gives the same bytes. Order: `newest` = `seq` descending; `oldest` = ascending; `relevance` = `ts_rank_cd` descending, then `seq` descending. Keys are in a fixed order. The correlation id goes in `_meta` (MCP) or a header (HTTP), not in the result body, so the body can stay in a provider prompt cache.
- **Token budget.** The size of an item = its canonical JSON in UTF-8 bytes ÷ 4, rounded up. Items are added in order until the next item does not fit. If the first item alone does not fit, its text is cut and `text_cut: true` is set. `next_cursor` (opaque: watermark + last sort key) continues at the next item. A cursor implies `as_of`.
- **Item `links`** gives only the counts per type (non-zero). The agent calls `neighbours` for the edges.

### 9.2 Sets and "current" for notes

A note is **current** for a request when all are true (`docs/09` §2.3):
1. its effective Standing is `approved`;
2. its Time is `durable` (so a `test_result` is never current);
3. its scope matches the request: for each dimension that the note bounds (repo, branch, paths), the request value must match, if the request gives it. If the request does not give it: a `rule` note is excluded (`needs_context`); an `evidence` note is shown with its scope;
4. when the request has a code target (`repo` + `commit` or `branch`), no code citation of the note into that repository is `stale` or `missing`. Excluded notes are counted in `excluded.stale` and returned only with `include_stale` (with `current: false`).

| Set | Contains |
|---|---|
| `current` | the notes above |
| `open` | `pending` notes, marked "not accepted" |
| `history` | `rejected`, `retired` (with the successor by `supersedes`), and `test_result` notes |

**A pending note is never in `current`.** One SQL predicate defines `current`; `query_notes`, `neighbours` and the candidates all use it.

Path matching: a glob in `scope_paths` uses `**` (any characters), `*` (any except `/`), `?` (one character except `/`). The request `path` is one path, or a directory prefix that ends with `/`.

### 9.3 `neighbours` (MCP) / `GET /v1/notes/{book}/{id}/neighbours` (HTTP)

```
neighbours(ref: str,                            # a note reference or a passage handle
           types: list[str] | None = None,      # default: all link types
           depth: int = 1,                      # 1 or 2
           direction: str = "both",             # out | in | both
           sets: list[str] = ["current"],
           max_nodes: int = 50, max_tokens: int = 2000, as_of: int | None = None) -> dict
-> {"root": item | null, "nodes": [item], "edges": [{"src": ref, "type": str, "dst": ref}],
    "watermark": int, "truncated": bool}
```

Postgres only: two joins on `note_link` (depth 2), no graph database. Order: breadth first, then link `seq` ascending. An edge whose other end the caller may not read, or which is outside `sets`, is dropped and not counted. With a passage handle as `ref`, `root` is null and the nodes are the notes linked to it (`about`, `derived_from`).

### 9.4 Watermark, `as_of`, `since`

- `watermark` = the highest `memory_seq` visible to the request. The advisory lock (§4) makes `seq` order equal to commit order, so no row with a lower `seq` can appear later.
- `as_of = w` evaluates notes, links and Standing events with `seq ≤ w`. Rights and code targets are evaluated now (they can only remove items).
- `since = w` returns notes that were written, linked, or had a Standing event after `w`. This is the R1 change feed by polling. `subscriptions/listen` waits (§12.3).

### 9.5 Notes in `open_citation`

`open_citation(handle)` accepts a note reference too. It returns one item with the full text, any Standing, with `current` computed for a request with no context. It needs `read`.

**Notes are not in `search_library` or `ask_library` in R1.** Q1 asks whether approved notes should join them.

## 10. Code citations and the verifier (#70)

### 10.1 Syntax

`<repo>@<commit>:<path>:<start>[-<end>][#<symbol>]`, for example `adc@3f2c…e1:src/run.py:40-52#retry_job`.
- `repo`: a registered slug of the note's book; `commit`: the full hex id (no short ids, no branch names);
- `path`: `ids.normalize_path` (relative, NFC, no `.`/`..`); parsed from the right, so a path can contain `:`;
- at most 200 lines; `symbol` is a label for the search after a move.

### 10.2 Repositories

- `kutuphane repo add <book> <slug> <git_dir>` (CLI, administrator only). `realpath(git_dir)` must be inside one of `KUTUPHANE_REPO_ROOTS`. The command reads `git rev-parse --show-object-format`. `kutuphane repo remove` sets `removed_at`.
- **Kütüphane never fetches.** The operator keeps the mirror current (a cron `git fetch`), or mounts the orchestrator's own repository read-only. So the verifier needs no network and no credentials, and it works air-gapped. A commit that the mirror does not have is `unverifiable: commit_unknown`.
- The container mounts the repository roots read-only and has the `git` binary.

### 10.3 How it reads

- Commands: `git rev-parse --verify --end-of-options <id>^{commit}`, `git cat-file --batch` (objects named on **stdin** as `<commit>:<path>`), `git rev-list --max-count=10001 A..B`. No other command.
- No shell. Argument vectors only. Request text never reaches an argument: commit ids pass a hex regex; a branch passes `git check-ref-format --branch` and is used as `refs/heads/<branch>`; paths go on stdin after `normalize_path`.
- Environment: `GIT_CONFIG_NOSYSTEM=1`, `GIT_CONFIG_GLOBAL=/dev/null`, `GIT_NO_REPLACE_OBJECTS=1`, `GIT_TERMINAL_PROMPT=0`, `GIT_OPTIONAL_LOCKS=0`, `HOME` unset; `-c safe.directory=<git_dir> -c core.fsmonitor=false`.
- Limits: 5 s per command; a blob above 2 MiB, or with a NUL byte, is `unverifiable: too_large` or `binary`; 200 citations per request. One `cat-file` process per (request, repository); blobs are cached per request by (commit, path).
- **Excerpt hash:** the cited lines, CRLF → LF, trailing white space removed per line, joined with `\n`, SHA-256. The write path stores it (§6.1 step 4).

### 10.4 Statuses

| Status | Condition | Changes |
|---|---|---|
| `verified` | the excerpt hash at the same lines in the target equals the stored one | — |
| `stale` | the file exists, the lines differ. `moved_to` = the first line where the same excerpt starts, if it occurs exactly once. If the excerpt is not found and a symbol is given: `symbol_found_at` (whole-word matches, at most 5 lines). | the note is not current for this target (§9.2) |
| `missing` | the path does not exist at the target | the same |
| `unverifiable` + reason | `repo_not_registered`, `repo_removed`, `outside_roots`, `commit_unknown`, `branch_unknown`, `too_large`, `binary`, `timeout` | shown; it does **not** make a note current or not current. It never counts as `verified` (R1). |
| `not_checked` | the request has no code target for that repository | — |

The status is a machine signal. It never changes Standing (#70, R1). No output ever contains code text.

### 10.5 `verify_citations` (MCP) / `POST /v1/citations/verify` (HTTP)

```
verify_citations(book: str, citations: list[str], at: str) -> dict   # at: a branch name or a full commit id
-> {"targets": {"adc": {"commit": "…", "branch": "main"}},
    "results": [{"citation": "…", "status": "stale", "moved_to": 61, "reason": null}]}
```

It needs `read` on `book`. It is logged as `action = verify` with the citations as items.

## 11. Gates on every new path

All new reads use the gates of `search_library`: one `authz.allowed` statement as the pre-filter, one more as the final check at the linearization point, one rerun when a book was lost, then `SearchChanged`. Each delivery is an `access_event` with the delivered references as `items`.

| Path | Modes | Text gate | Standing | Model call |
|---|---|---|---|---|
| `propose_note` | `propose` on the journal; `read` on cited and linked books | candidate text: `ai_input` | always `pending` | embedding only; journal `ai_input` true; egress = journal + cited and derived books |
| `link_notes` | `propose` on the `src` book; `read` on the `dst` book | — | unchanged | none |
| `query_notes` | `read` | `ai_input` for model readers | `sets` (§9.2) | none |
| `neighbours` | `read` on the root and on every node | `ai_input` | `sets` | none |
| `open_citation` (note) | `read` | `ai_input` | shown | none |
| `verify_citations` | `read` on the book of the repository | no code text | — | none |
| set Standing | `curate`; `user:` only; HTTP: UI client + `user_verified`; never MCP | — | the act itself | none |
| `job_status` / `job_result` / `job_cancel` | the submitter only; `job_result` uses the `reopen_answer` gate | as `reopen_answer` | — | none |

"Model reader" is unchanged: `server._for_model` (MCP callers and `agent:` principals). A note is never an agent instruction in R1: skills stay in file books with `activate` (D37).

## 12. MCP 2026-07-28, long operations, headless auth (#73)

### 12.1 What 2026-07-28 changes for our server

Verified against the spec changelog (<https://modelcontextprotocol.io/specification/2026-07-28/changelog>) and the Python SDK v2 guides (<https://py.sdk.modelcontextprotocol.io/whats-new/>, <https://py.sdk.modelcontextprotocol.io/migration/>). `mcp` 2.3.0 is the latest release (2026-10-02).

| Change | Effect on Kütüphane | Action |
|---|---|---|
| SDK v2: `FastMCP` → `MCPServer` (`from mcp.server import MCPServer`); `stateless_http`, `transport_security` move to `streamable_http_app(...)`; `ToolError` from `mcp.server.mcpserver.exceptions` | `server.build_mcp` does not import | pin `mcp>=2.3,<3`; move the two arguments; keep the host lifespan that enters `mcp.session_manager.run()` |
| auth surface (`TokenVerifier`, `AccessToken`, `AuthSettings`, `get_access_token`) | unchanged | `_Verifier` puts `client_id` and `user_verified` into the claims |
| no `initialize`, no `Mcp-Session-Id`; `_meta` per request; `server/discover` | we are already stateless; the SDK serves both eras from one app | none. Cross-call state is explicit handles: note refs, watermarks, cursors, job ids, answer ids |
| `Mcp-Method` / `Mcp-Name` headers required | the SDK checks them | the reverse proxy must pass them |
| `_meta` `clientInfo` | not authenticated | never used for origin or rights (§5.1) |
| `resultType`; `structuredContent` any JSON | the SDK sets it | our tools return JSON objects in a fixed key order |
| `tools/list` deterministic, `ttlMs`/`cacheScope` | good for prompt caches | register tools in a fixed order; set `cache_hints` |
| Tasks moved to the `io.modelcontextprotocol/tasks` extension; **the Python SDK does not implement it** | no native tasks | the durable `job_id` (§12.2) is the only path in R1. When the SDK has the extension, a task maps one-to-one to a `job` row. |
| MRTR replaces server-initiated elicitation; `elicitation/complete` removed | needed only for R3 (passkey) | none in R1 (§5.3). R3 needs a shared `RequestStateSecurity` key across replicas. |
| `subscriptions/listen` replaces GET streams and `resources/subscribe` | we have no subscriptions | R1 uses `since` polling (§9.4). A scope-filtered feed waits for R2: each event needs a rights check per subscriber. |
| sampling, roots, logging deprecated; `ping` removed | not used | none |
| 4 MiB default body limit | our largest input is about 200 KB | none |
| RFC 9207 `iss`, CIMD over DCR, credentials bound to the issuer | client and IdP matters | none in the resource server |

### 12.2 Long operations: durable jobs

- `ask_library(…, background: bool = False)`. With `background = true`, it returns `{"job_id": "jb_…", "status": "queued"}` at once. HTTP: `POST /v1/ask` with `"background": true` → `202`.
- `job_status(job_id) -> {status, created_at, started_at, finished_at, error}`; `job_result(job_id)` = the `reopen_answer` output of the stored answer; `job_cancel(job_id)`. HTTP: `GET /v1/jobs/{id}`, `GET /v1/jobs/{id}/result`, `POST /v1/jobs/{id}/cancel`.
- Workers run in the server process (`KUTUPHANE_JOB_WORKERS`, default 1: the answer model is one GPU). They claim with `FOR UPDATE SKIP LOCKED`, so many replicas are safe. The worker renews `lease_until`. At most 3 open jobs per principal.
- Finished jobs are deleted after 7 days. The answer and its audit rows stay.
- **Not in R1:** `ingest`, `index` and `approve-import` over MCP or HTTP. They change book content or accept packages, and no mode allows that today. `approve-import` is a human act and must never be on MCP (Q2).

### 12.3 What does not change

`search_library`, `open_citation` (except note refs), `reopen_answer`, `read_document`, `record_runbook_feedback` keep their signatures.

### 12.4 Headless authentication

The IdP issues all tokens. Kütüphane stores no client secrets and accepts no static API keys.

| Client | Token | Actor | Needs |
|---|---|---|---|
| an orchestrator on its own rights | OAuth client credentials (client secret or `private_key_jwt`; MCP extension `io.modelcontextprotocol/oauth-client-credentials`); the IdP mapper sets `kutuphane/principal_type: agent`, `sub` = the agent name | `agent:adc`, no `on_behalf_of` | direct grants to `agent:adc` (`read`, `propose`) |
| an orchestrator for a person, headless | RFC 8693 token exchange at the IdP: subject token = the person's (from a one-time interactive consent), actor token = the client-credentials token → `sub` = person, `act.sub` = agent | `agent:adc` on behalf of `user:ayse` | a live delegation `user:ayse → agent:adc` per mode, and Ayşe's own right (unchanged, AT-05) |

- `client_id` (RFC 9068) or `azp` goes into `Actor.client_id` and `write_record.client_id`.
- **Defense in depth:** if an IdP maps a machine client to a `user:` principal by mistake, it still cannot store `human` (R4 needs a UI client id and `user_verified`) and cannot curate over HTTP (the same check).
- The server advertises the extension in `server/discover`.

## 13. HTTP equivalents

| MCP tool | HTTP | Success status |
|---|---|---|
| `propose_note` | `POST /v1/notes` | 201 |
| `link_notes` | `POST /v1/notes/links` | 201 |
| `query_notes` | `GET /v1/notes?…` (list parameters repeat) | 200 |
| `neighbours` | `GET /v1/notes/{book}/{id}/neighbours?…` | 200 |
| `open_citation` (note) | `GET /v1/citation?handle=…` | 200 |
| `verify_citations` | `POST /v1/citations/verify` | 200 |
| — (no MCP tool) | `POST /v1/notes/{book}/{id}/standing` `{value, reason}` | 200 |
| `ask_library(background=true)` | `POST /v1/ask` `{…, "background": true}` | 202 |
| `job_status` / `job_result` / `job_cancel` | `GET /v1/jobs/{id}`, `GET /v1/jobs/{id}/result`, `POST /v1/jobs/{id}/cancel` | 200 |

New error class: the daily write limit and the open-job limit → 429. Others use the existing classes (400, 401, 403, 404).

## 14. Not in R1, and why R2 is not blocked

| Item | R1 | What R1 keeps ready |
|---|---|---|
| #77 curator queue | the single-note Standing act only | `kind` risk order (§8.1), `cluster` groups, one event per item. A batch act writes one event per note with one reason. A later column records a model suggestion and its confidence. |
| #79 rollback | none | own `derived_from` links (`write_seq`), `cause_seq` for the root, `access_event.items` with note refs for the report. Embedding egress already follows derivation. |
| R3/R7 confirmation | none | §5.3 |
| change feed | `since` polling | `memory_seq` order = commit order |
| journal export | `kutuphane export` refuses a journal | — |
| notes in `search_library`/`ask_library` | no | Q1 |

## 15. Test plan (consumer-visible regressions)

| # | Test | Slice |
|---|---|---|
| T1 | An agent (delegation) proposes over MCP: `pending`, origin `model`; `query_notes(sets=["open"])` finds it in the next call; `sets=["current"]` does not. | A, B |
| T2 | An agent requests `origin: human`: stored `model`, notice `origin-claim-refused`. A direct SQL insert of `human` for an `agent:` principal fails on the check. | A |
| T3 | A `user:` token without `act` over MCP: `model`. Over HTTP from a non-UI client: `unknown`. UI client + fresh UV: `human`. UV older than the maximum age: `unknown`. A user who requests `model` gets `model`. | A, D |
| T4 | No `propose` right: refused, logged, nothing stored. A delegation revoked during the write: rolled back, logged. | A |
| T5 | Credential-like text: refused; the response and the logs do not contain the value. | A |
| T6 | Same bytes twice: one note, `status: existing`, `recurrence: 2`. A case/white-space variant: two notes and one `same_as`. A similar text: a candidate, two notes, no link. | A |
| T7 | `contradicts` between two notes of one cluster: `collapse` shows both. | A, B |
| T8 | Candidates never come from a book that the writer cannot read. | A |
| T9 | Journal `ai_input: false`: no `model_call` row; agents get `text: null` with the reason; a person over HTTP gets the text. | A, B |
| T10 | A note derived from a `local_only` book on a cloud embeddings route: no call is sent; the note is stored with `vector: skipped:egress`. | A |
| T11 | No MCP tool changes Standing. HTTP Standing by an agent token, by a user without UV, or from a non-UI client: refused. `curate` grant to an agent or a delegation of `curate`: the database refuses. | A |
| T12 | Approve → current. Reject → only `history`. Supersession retires a predecessor with the same scope, not one with another scope. A `supersedes` cycle is refused. | A, B |
| T13 | The same `query_notes` request twice gives byte-identical results. After new writes, `as_of` gives the old result again. | B |
| T14 | `max_tokens` is never exceeded (except one cut first item); `next_cursor` pages without gaps or duplicates. | B |
| T15 | Each filter: kind, role, origin, class key, repo/branch/path glob, `commits` range, time, `text`, `unfixed`. | B, C |
| T16 | A bounded `rule` note without request context: excluded, `needs_context` counted. A bounded `evidence` note: shown with its scope. | B |
| T17 | A right revoked during a query: the book is dropped, the query runs again, the loss is logged (as AT-04). | B |
| T18 | `query_notes` and `neighbours` make no model call (`model_call` unchanged, no LLMDAP traffic). | B |
| T19 | `neighbours`: depth 3 is refused; an edge to an unreadable note is dropped and not counted. | B |
| T20 | `since`: with concurrent writers, a poller that follows the watermark sees every change once. | B |
| T21 | Verifier: `verified`; `stale` with `moved_to`; `missing`; `unverifiable` for an unregistered repository, an unknown commit or branch. | C |
| T22 | Paths `../x`, `/etc/passwd`, a NUL byte, `--upload-pack=x` as a branch, a short commit id: refused. A `git_dir` outside the roots: refused at `add` and at open (symlink swap). | C |
| T23 | A query with a code target excludes notes with stale citations, counts them, and returns them with `include_stale`. | B, C |
| T24 | `verify_citations` needs `read` on the book; no output contains code text. | C |
| T25 | A 2026-07-28 client (no `initialize`) and a 2025-11-25 client both list the tools and call `search_library` and `propose_note`. `tools/list` order is stable. | D |
| T26 | `ask_library(background=true)`: job id at once; status and result after a server restart; another principal gets "not found"; cancel before run → `cancelled`; an expired lease → `failed: interrupted`. | D |
| T27 | A client-credentials token with the agent claim → `agent:`; a token-exchange token with `act` → `on_behalf_of`; `client_id` is in `write_record`; `_meta.clientInfo` changes nothing. | D |
| T28 | Migrations 016–018 apply to a database at 015 with data; grants and delegations stay. | A, C, D |

## 16. Implementation slices

**P0 (main agent, before the slices, one small commit):** `gate.Actor` gets `client_id=None`, `user_verified=False`, `channel="cli"`; `server.py` gets a loop that calls `register_mcp(mcp, deps)` and `http_routes(deps, endpoint)` of each feature module. After P0, the slices touch `server.py` only through these hooks (except D).

| Slice | Issues | Migration | Owns (files) | Exposes |
|---|---|---|---|---|
| **A — notes write core** | #68, #69, #72, D70 | `016_notes.sql` | `notes.py` (new: journal, propose, link, Standing, supersession, duplicates), `origin.py` (new), `authz.py` (modes), `profiles.py` (`journal` spec), `cli.py` (`journal create`, `note standing`), `tests/test_notes.py`, `tests/test_origin.py` | the 016 DDL (this document is the contract); `notes.parse_ref`; `notes.CURRENT_SQL` (the one predicate of §9.2, without the code-target part); `notes.effective_standing(conn, seqs, as_of)`; `notes.item_info(conn, book)` (a kstd-shaped info for `_text`); `origin.compute(actor, requested)` |
| **B — notes read path** | #71 | — | `notesquery.py` (new: `query_notes`, `neighbours`, note `open_citation`, budget, cursor, watermark), `tests/test_notes_query.py` | the tools and routes of §9 |
| **C — code citations** | #70 | `017_code_repo.sql` | `coderepo.py` (new: parse, registry, git reader, verify, `rev_list`), `cli.py` (`repo add/remove`), `Dockerfile`/compose (git, read-only mount), `tests/test_coderepo.py` | `coderepo.parse(text) -> CodeCitation`; `coderepo.excerpt(conn, book, cite) -> bytes` (raises `CitationRefused`); `coderepo.verify_many(conn, book, cites, at) -> list[Status]`; `coderepo.rev_list(conn, book, repo, range) -> list[str]`; `verify_citations` tool and route |
| **D — protocol, jobs, auth** | #73 | `018_job.sql` | `pyproject.toml`, `server.py` (SDK v2, `background` ask, job tools), `jobs.py` (new), `identity.py` (`client_id`, `amr`, `auth_time`), `devauth.py` (dev tokens with these claims), `tests/test_server.py`, `tests/test_identity.py`, `tests/test_jobs.py`, README (auth) | the SDK v2 server; `Actor` values from tokens; the job API |

Dependencies: B reads A's tables and calls C's `verify_many`/`rev_list`; A calls C's `parse`/`excerpt`. Each slice codes against the contracts above and tests with the DDL of this document. Shared files: `cli.py` (A and C each add one subcommand group). Merge order for the least friction: P0, then D, A, C, B. After all slices: one full test run (`pytest`, with `KUTUPHANE_TEST_DSN`), and the T25 client test against a running server.

## 17. Questions for the operator

1. **Notes in `search_library`/`ask_library`:** should approved, current notes join them in R1? Proposal: **no** in R1. The fast reads are `query_notes` and `neighbours`; this keeps `search.py` and `retrieval.py` unchanged. Add them in R2 with the same `current` predicate.
2. **Long operations over MCP:** R1 runs only `ask` as a job. Should `ingest`, `index` and `approve-import` be on HTTP/MCP later? They need a new right. Proposal: `approve-import` never on MCP; `ingest`/`index` only for a `user:` with a new `publish` mode, in R3 (#75).
3. **`contradicts`:** accept the eighth link type (#72 needs it)?
4. **Guard owner and due condition:** proposal: the orchestrator keeps them; Kütüphane keeps `guard_due` and the accepted `convention` note.
5. **Stale code citations:** proposal: a note with a `stale` or `missing` citation at the request target is not current (the stricter move, #70), and it is returned only with `include_stale`. The alternative is to show it as current with a mark.
6. **Thresholds:** duplicate similarity 0.90, note size 8,000 characters, 500 writes per principal per day, 3 open jobs. Proposal: start with these and measure on the orchestrators' first two weeks.
7. **Curation over HTTP in R1:** proposal: yes, with a registered UI client id and a fresh user-verified login (the R4 check), plus the CLI. The alternative is the CLI only until #77.
