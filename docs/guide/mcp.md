# MCP reference

The Model Context Protocol (MCP) server, for agent developers and operators. Plain HTTP: [http-api.md](http-api.md).
Concepts: [concepts.md](concepts.md), [agent-memory.md](agent-memory.md). Rights: [security.md](security.md).
Design: [../24-r1-agent-memory-design.md](../24-r1-agent-memory-design.md).

## 1. Endpoint

`/mcp` under `KUTUPHANE_PUBLIC_URL`, streamable HTTP: one `POST /mcp` per JSON-RPC message. The server is
**stateless** (no `Mcp-Session-Id`): state between calls is an explicit handle (note reference, watermark, cursor,
job id, answer id). The tool list changes only with a deployment.

### 1.1 Request headers

| Header | Value | When |
|---|---|---|
| `Authorization` | `Bearer <access token>` | Always. |
| `Content-Type` | `application/json` | Always. |
| `Accept` | `application/json, text/event-stream` | Always. |
| `MCP-Protocol-Version` | `2025-11-25` or `2026-07-28` | After `initialize` (2025-11-25); always (2026-07-28). |
| `Mcp-Method` | The JSON-RPC method, for example `tools/call` | 2026-07-28. |
| `Mcp-Name` | The tool name of a `tools/call`, or the URI of a `resources/read` | 2026-07-28. |

The response is JSON, or a `text/event-stream` with the message in a `data:` line. Read both.

### 1.2 Transport checks

The MCP SDK checks before a tool runs:

| Condition | Status | Body |
|---|---|---|
| The token is missing or not valid. | `401` | `{"error": "invalid_token", "error_description": "Authentication required"}` |
| A `POST` `Content-Type` is not `application/json`. | `400` | `Invalid Content-Type header` |
| `Host` is not the host of `KUTUPHANE_PUBLIC_URL`. | `421` | `Invalid Host header` |
| An `Origin` is not the origin of `KUTUPHANE_PUBLIC_URL`. | `403` | `Invalid Origin header` |
| The body is larger than 4 MiB. | `413` | `Request body too large` |
| 2026-07-28: `Mcp-Name` differs from the tool name or URI in the body. | `400` | JSON-RPC code `-32020` |

The `Host` and `Origin` checks stop DNS rebinding: set `KUTUPHANE_PUBLIC_URL` to the URL that clients use, and let
the proxy pass `Host` unchanged. The ingress proxy (`deploy/nginx.conf`) adds `client_max_body_size 1m` and
`proxy_read_timeout 300s`; run a long `ask_library` as a background job (section 6).

## 2. Protocol versions

### 2.1 2025-11-25 (with `initialize`)

Send `initialize`, then each request with `MCP-Protocol-Version: 2025-11-25`. A client may send `initialize` before
each request (as `deploy/mcp_probe.py` does).

```json
{"jsonrpc": "2.0", "id": 1, "method": "initialize",
 "params": {"protocolVersion": "2025-11-25", "capabilities": {},
            "clientInfo": {"name": "my-agent", "version": "1"}}}
```

### 2.2 2026-07-28 (without `initialize`)

No `initialize`: put the protocol data in `params._meta`, and send `MCP-Protocol-Version: 2026-07-28`, `Mcp-Method`
and `Mcp-Name` (the proxy must pass both).

```json
{"jsonrpc": "2.0", "id": 2, "method": "tools/call",
 "params": {"name": "search_library", "arguments": {"query": "backup retention"},
            "_meta": {"io.modelcontextprotocol/protocolVersion": "2026-07-28",
                      "io.modelcontextprotocol/clientCapabilities": {},
                      "io.modelcontextprotocol/clientInfo": {"name": "my-agent", "version": "1"}}}}
```

`clientInfo` is not authenticated and never decides rights or origin. **`server/discover`** lists
`io.modelcontextprotocol/oauth-client-credentials` (headless clients get tokens with OAuth client credentials at the
identity provider, IdP) and `io.modelcontextprotocol/skills` in `capabilities.extensions`; a 2025-11-25 `initialize`
result has no `extensions`. `tools/list` and `server/discover` results carry `ttlMs: 300000` and
`cacheScope: "public"`.

## 3. Authentication

Kütüphane is an OAuth resource server. The IdP issues all tokens. Kütüphane stores no client secret and accepts no
static API key.

### 3.1 The token

Send `Authorization: Bearer <token>`. Kütüphane verifies it:

| Check | Rule |
|---|---|
| Signature | A key of the issuer's JWKS file (`KUTUPHANE_OIDC_JWKS` for the primary issuer). With a `kid`, exactly one key has that id. |
| Algorithm | `RS256`, `ES256` or `EdDSA`. |
| Required claims | `exp`, `iat`, `iss`, `aud`, `sub`. |
| `iss` | Exactly `KUTUPHANE_OIDC_ISSUER` or an issuer of `KUTUPHANE_OIDC_ISSUERS`. No normalization. |
| `aud` | That issuer's audience (`KUTUPHANE_OIDC_AUDIENCE` for the primary issuer). |
| Clock leeway | 30 seconds. |

The caller is only what the verified token says. No header sets the principal or the user acted for.

### 3.2 Who the caller is

- A person (the IdP's interactive OAuth flow) is `user:<sub>`.
- A headless agent (OAuth client credentials; the IdP mapper sets `kutuphane/principal_type: agent` and `sub` = the
  agent name) is `agent:<sub>`.
- An agent for a person (RFC 8693 token exchange: subject token = the person's token from a one-time consent, actor
  token = the client-credentials token; result `sub` = person, `act.sub` = agent) is `agent:<act.sub>`, acting for
  `user:<sub>`.
- `kutuphane/principal_type` is `user` (default) or `agent`; another value, or a nested `act`, is refused.
- A token gives no right. An agent for a person also needs a live delegation, and the person needs the right
  ([security.md](security.md)).
- The token client (`client_id`, RFC 9068, else `azp`) is recorded with each write; it never changes rights or
  origin. `GET /v1/whoami` shows a token's principal.

### 3.3 Protected-resource metadata

RFC 9728 metadata is at `/.well-known/oauth-protected-resource` (plus the path of `KUTUPHANE_PUBLIC_URL`, if any),
without a token. `authorization_servers` is exactly `KUTUPHANE_OIDC_ISSUER`. `/mcp` without a valid token gets `401`:

```
WWW-Authenticate: Bearer error="invalid_token", error_description="Authentication required", resource_metadata="https://kutuphane.example/.well-known/oauth-protected-resource"
```

The server does not start if the SDK would advertise the issuer in another form (uppercase host, default port):
write `KUTUPHANE_OIDC_ISSUER` exactly as in the tokens.

### 3.4 More than one issuer

`KUTUPHANE_OIDC_ISSUERS` is a JSON file of more issuers (#157), each with its exact `iss`, audience, JWKS and
**principal prefixes** ([operations.md](operations.md#more-than-one-token-issuer)):

- Its tokens may name only principals (and users acted for) under its prefixes; else `401`.
- No other issuer may name those principals; else `401`.
- Its principals never get `curate` unless the entry says `"curate": true` (`kutuphane grant … curate` refuses).

Only the primary issuer is in the metadata.

## 4. Results and errors

### 4.1 Result shape

An object result is JSON text in `result.content[0].text`, without `structuredContent`. A list (`search_library`,
`list_books`) or a string (`read_document`) is in `result.structuredContent.result` and also in `result.content`.
On 2026-07-28, `result._meta` also has `io.modelcontextprotocol/serverInfo`.

### 4.2 Text for a model

Every MCP caller feeds a model. When the kstd `ai_use.ai_input` of an item is not `y`, the result has `"text": null`
and `"withheld": "rights do not allow AI input"`. A file without `kstd.yaml` follows its book policy
([kstd.md](kstd.md)).

### 4.3 Errors

A tool error has `isError: true` and the text `Error executing tool <name>: <message>`, with no internal details.
Messages, with the HTTP equivalent: `forbidden` (`403`: no needed right now, or lost during the request);
`not found` (`404`: missing, or not visible to you); `authorization changed during the request; retry` (`409`:
rights changed two times during one read); `idempotency_key reused with another request` (`409`, section 7);
`daily note write limit reached (<n>)` and `at most 3 open jobs per principal` (`429`, section 8);
`model service unavailable or refused` (`502`); a validation message such as `query must be 1..1000 characters`
(`400`); `internal error` (`500`, details in the server log). Without LLMDAP, `POST /v1/ask` gives `503`
`answers are not available: this install has no model gateway (LLMDAP); search is full text only`, and MCP does not
list `ask_library` ([light install](install.md#light-install)). The SDK refuses an argument of the wrong type with
its own message.

### 4.4 Handling labels in `_meta`

`search_library`, `open_citation`, `read_document`, `query_notes`, each skill entry and each `skill://` read put
labels in `_meta["kutuphane/handling"]`:

```json
{"_meta": {"kutuphane/handling": {
  "books": {"runbooks": {"sensitivity": "normal", "egress": "local_only"},
            "adc-memory": {"sensitivity": "restricted", "egress": "local_only"}},
  "sensitivity": "restricted", "egress": "local_only",
  "skill_scans": [{"book": "runbooks", "content_id": "ct_9f…", "skill_path": "skills/backup", "scan_id": 42,
                   "status": "scanned", "recommendation": "SAFE", "blocking": false}]}}}
```

| Key | Value |
|---|---|
| `books` | The E5 policy now (Sensitivity, Egress) of each readable book in the result: of each passage or file, each note's journal and `source_books`. |
| `unnamed_sources` | Notes only, when not 0: the count of unreadable source books (never named). |
| `sensitivity`, `egress` | The strictest value over all books, unnamed ones included (`restricted` before `normal`, `local_only` before `cloud_ok`). Absent when the result has no content: no claim, not `normal`. |
| `skill_scans` | When one applies: the latest scan record of each skill folder in the result. `scan_id` is the `id` in `kutuphane skill show <book>`. A record is a proposal, never an approval ([security.md](security.md#skill-scan-skillspector)). |

Labels describe the content; they give no right and refuse nothing. HTTP has no labels. SEP-1913 trust annotations
are not used ([../14-contributions.md](../14-contributions.md)).

### 4.5 Retrieval status

`search_library` reports each model stage in `_meta["kutuphane/retrieval"]`, for example
`{"embedding": "ok", "translation": "skipped", "rerank": "failed"}`; `ask_library`, `reopen_answer` and
`job_result` store it as the answer's `retrieval` key. A stage is `ok`, `failed` (the search went on without it) or
`skipped` ([stages](http-api.md#51-get-v1search)).

### 4.6 Correlation id

Each `tools/call`, `resources/read`, `skills/list` and `skills/get` gets a new id. Send your own in the request
`_meta["kutuphane/correlation-id"]` (#156), pattern `^[A-Za-z0-9][A-Za-z0-9._:-]{7,63}$`; another value gets
`-32602` and nothing is done. Every result `_meta`, also of an error, has ours under that key and yours under
`kutuphane/caller-correlation-id`. Your id is stored as for HTTP ([http-api.md](http-api.md#15-correlation-id)). It
is never a right or an idempotency key.

## 5. Tools

`tools/list` gives the same order to every principal, also one with no grant:
[`search_library`](#51-search_library), [`open_citation`](#52-open_citation), [`ask_library`](#53-ask_library),
[`reopen_answer`](#54-reopen_answer), [`read_document`](#55-read_document), [`list_books`](#518-list_books),
[`list_files`](#519-list_files), [`job_status`](#56-job_status), [`job_result`](#57-job_result),
[`job_cancel`](#58-job_cancel), [`propose_note`](#59-propose_note), [`link_notes`](#510-link_notes),
[`verify_citations`](#511-verify_citations), [`query_notes`](#512-query_notes), [`neighbours`](#513-neighbours),
[`record_outcome`](#514-record_outcome), [`confirm_origin`](#515-confirm_origin),
[`submit_package`](#516-submit_package), [`package_status`](#517-package_status). Without LLMDAP
([light install](install.md#light-install)), `ask_library` and the three job tools are not listed. Each description
names its grant (for example `needs read on the book`). HTTP routes: [http-api.md](http-api.md). Call examples:
[agent-memory.md](agent-memory.md).

No tool changes Standing or origin: a curator changes Standing ([operations.md](operations.md)); a person confirms
an origin with a passkey (section 5.15).

**Agent gate.** For instruction passages and agent files, an agent also needs `activate`. An agent never gets
content of a skill that a SkillSpector scan blocks ([security.md](security.md#skill-scan-skillspector)).

**Tables.** An argument is a string unless a type is given. Default "**req**" marks a required argument. Error
codes are the HTTP equivalents (section 4.3).

| Handle | Form | Example |
|---|---|---|
| Passage handle | `<book>@<content_id>/<profile_id>/<path>#<ordinal>` | `runbooks@ct_9f…/pf_41…/backup.md#3` |
| Note reference | `<book>@nt_<64 hex>` | `adc-memory@nt_3f…` |
| Code citation | `<repo>@<commit>:<path>:<start>[-<end>][#<symbol>]` | `adc@3f2c…e1:src/run.py:40-52#retry_job` |

### 5.1 `search_library`

Search the books that you may read now; hits carry passage handles. Filters act before ranking and never add a
book: an unreadable book gives the same empty result as a missing one. Notes are not in `search_library` or
`ask_library` (docs/24): a journal in `book` gives
`journal: use query_notes for <journal>; notes are not in search_library or ask_library`.

**Needs:** `read` on each book; agent gate.

| Argument | Default | Limits |
|---|---|---|
| `query` | **req** | 1–1000 characters, not blank. |
| `k` (integer) | `8` | 1–50. |
| `book` (list of strings) | none | Up to 50 book slugs. |
| `path` | none | A relative path prefix; a folder ends with `/` (`data/`). |
| `origin` (list of strings) | none | `human`, `assisted`, `model`, `tool`, `unknown` (a book without `kstd.yaml`). |
| `current_only` (boolean) | `false` | Only files whose kstd validity includes now. |
| `context` (object) | none | `{"platform": "vcenter", "version": "7.0.3"}`, both optional (#137). A file whose kstd `applies_to` the context contradicts is left out. `item.scope` is `unbounded`, `match` or `needs_context` (a bound with no context value; the file stays). |
| `max_chars` (integer) | none (full text) | 80–4800. A snippet of each passage. |

**Snippets.** With `max_chars`, `text` is a window of at most that many characters (`…` marks included) around the
best span of query words (most different words, then most matches, then first position; else the start), cut at
white space. The same request gives the same bytes (no clock, randomness or model), so prompt caches stay valid.
Hits, order, scores and gates do not change.

**Result:** a list. Each entry has `citation` (the handle; open it for the full passage), `page` (PDF) and `line`
(text file) or `null`, `score` (4 decimals), `text` (or snippet, or `null` with `withheld`), `truncated` (only with
`max_chars`; not for a withheld passage), `item` (the kstd item information, or `null` without `kstd.yaml`) and
`quoted_records`: handles of JSONL records whose text the passage repeats (G23), from readable books that pass the
filters ([concepts.md](concepts.md#records-that-a-passage-repeats)). `_meta` has the labels and the retrieval
status.

**Errors:** `400` (query, `k`, `max_chars`, a filter; a journal), `409`. A failed embedding, translation or reranking
route skips its stage; the search does not fail.

### 5.2 `open_citation`

Open a passage handle (the exact passage of that version) or a note reference (full text, Standing, and `current`
for the context). **Needs:** `read` on the book; agent gate.

Arguments: `handle` (**req**, a passage handle or a note reference). For a note reference only, the context:
`repo` (a slug), `branch` (not empty, no control characters, at most 1000 characters), `path` (a relative path or a
folder prefix ending with `/`; no `..`), `commit` (a full id; needs `repo`), `platform`, `version` (as
`query_notes`).

**Result for a passage:** `{"citation", "page", "line", "text", "item", "publication", "outcomes", "status",
"moved_to", "match"}`.

`outcomes`: the non-zero `record_outcome` counts. `status` (#140), in the book's current version: `current`;
`moved` with `moved_to` (the passage of the same path that replaces it) and `match` (`exact`: same text; `overlap`:
at least half of the word pairs, or the whole old text with its operators and case when the content changed); or
`stale`. The text is always that of your handle. `publication`: who published or approved the version (section
5.18), or `null`.

**Result for a note:** `{"citation", "note", "targets", "watermark"}`; `note` is a `query_notes` item. The labels
cover its journal and source books.

**Errors:** `400` (`malformed citation handle`, a context value), `403`, `404`, `409`.

### 5.3 `ask_library`

Answer a question through LLMDAP with `[n]` citations, in the question's language (Turkish or English), or
`not_in_library`. Only passages with AI input in their kstd rights go to the model, in rank order. The model is told
to base the answer on `[1]` when it answers, to put each `[n]` after its claim, and to say what the passages do not
show. A named document (a file name, or a name before `§`: `access-policy §5.3`) must be in a passage path, and a
named section (`§5.3`, `section 5.3`, `bölüm 5.3`) must start a passage line; else the prompt says so, and the model
answers `not_in_library` or says that the passages only refer to it.

**Needs:** `read` on the passages' books; agent gate. Rights are decided again after the model call.

| Argument | Default | Limits |
|---|---|---|
| `question` | **req** | 1–1000 characters, not blank. |
| `book`, `path`, `origin`, `current_only`, `context` | | As `search_library`. |
| `background` (boolean) | `false` | `true` starts a background job (section 6). |
| `idempotency_key` | none | 8–128 characters of `A-Z a-z 0-9 . _ : -`; only with `background: true`. |

**Result:** `id` (the answer id, for `reopen_answer`), `status` (`answered` or `not_in_library`), `body` (or `null`),
`withheld` (passages not sent: kstd rights), and `citations`: per cited passage
`{n, book, content_id, profile_id, path, ordinal, line, record, quoted_records, item}`. `line`: the first line
(`null` for HTML, PDF). `record`: the JSONL record number from 1, else `null`. A repeated record (G23) goes into the
evidence before the passage (at most 4); `quoted_records` gives their handles, else `[]`. With
`background: true`: `{"job_id": "jb_…", "status": "queued"}` at once; a retry with the same key gives the same job.

**Errors:** `400` (`question is required`, `background must be true or false`,
`idempotency_key needs background: true`, a journal), `403`, `409`, `429`, `502`, `503`.

### 5.4 `reopen_answer`

A stored answer and its evidence, with no model call, under current rights. **Needs:** the same principal acting
for the same user, or that user directly; `read` now on every source book; agent gate. Argument: `answer_id`
(**req**, the `id` of an answer).

**Result:** `{"id", "question", "status", "body", "evidence"}`; an evidence entry has `n`, `citation`, `line`,
`record`, `text` (or `null` with `withheld`), `item`, `quoted_records`. **Errors:** `403` (another principal's
answer, a source book not readable now), `404`.

### 5.5 `read_document`

Read a text file of one content version. **Needs:** `read` on the book; agent gate. A file in a skill folder stands
for its innermost skill (section 10.3): for an agent, no file of that skill (a subfolder skill included) may be
blocked; for a model reader, every file of the skill must allow AI input. Another file needs only its own rights.
Arguments (all **req**): `book`, `content_id` (`ct_…`), `path` (relative; no `.` or `..` segments).

**Result:** the text, with labels. **Errors:** `400`
(`not a text document; use search_library and open_citation for its passages` when the media type is not
`text/markdown` or `text/plain`; an unsafe path), `403` (no right, or no AI input), `404`.

### 5.6 `job_status`

The state of your background `ask_library` job (section 6). **Needs:** no grant. Argument: `job_id` (**req**, `jb_`
and 32 hex characters).

**Result:** `{"status", "created_at", "started_at", "finished_at", "error"}`. `status`: `queued`, `running`,
`succeeded`, `failed`, `cancelled`. `error`: a short message, for example `interrupted` or `forbidden`.
**Errors:** `404` (no such job, a malformed id, not yours).

### 5.7 `job_result`

The answer of a succeeded job, as `reopen_answer`, under current rights. Keep its `id` for `reopen_answer`.
Argument: `job_id` (**req**). **Errors:** `400` (`job has no result: <status>`), `403`, `404`.

### 5.8 `job_cancel`

Cancel a job. A queued job stops at once; a running job stops before its model call or before it stores the answer;
a finished job does not change. Argument: `job_id` (**req**). **Result:** as `job_status` (it can still show
`running`). **Errors:** `404`.

### 5.9 `propose_note`

Write a note into a journal. It starts `pending`; a curator approves it. The same bytes in the same book are the
same note (`status: existing`, `recurrence` + 1). Use: [agent-memory.md](agent-memory.md#2-propose-a-note).

**Needs:** `propose` on the journal; `read` on the book of each citation and link target. `read` on the journal
gives the full receipt.

| Argument | Default | Limits |
|---|---|---|
| `book` | **req** | A journal slug. |
| `kind` | **req** | `finding`, `decision_proposal`, `dead_end`, `convention`, `lesson`, `test_result`. |
| `text` | **req** | 1–8000 characters, not blank, no NUL. Credential-like text is refused. |
| `citations` (list of strings) | `[]` | At most 20 passage handles or code citations (a repository of this journal, a published commit). |
| `scope` (object) | none | `{"repo", "branch", "paths": [<glob>]}`; `repo` (required) is a live repository of the journal. At most 20 `paths`: `**` any characters, `*` any except `/`, `?` one character except `/`. |
| `commit` | none | The observed full commit id (40 or 64 hex). Needs `scope`. |
| `applies_to` (object) | none | The note's kstd Scope bound (#164), as a file's: `{"platform": [<name>, …], "version": "<range>"}`, one or both (`{"platform": ["vcenter"], "version": ">=7,<8"}`). At most 20 platforms of 1–200 printable characters; a range of at most 100 characters. Part of the note id. |
| `links` (list of objects) | `[]` | At most 20 `{"type", "ref"}`: `derived_from`, `supersedes`, `same_as`, `contradicts`, `about`, `fixed_by`, `violates`, `decided_by`. `ref`: a note reference, or a passage for `derived_from` and `about`. `same_as` stays in one book. No duplicates. |
| `class_key` | none | `[a-z0-9][a-z0-9._:/-]{0,79}`. |
| `decision` (object) | none | `decision_proposal` only: `{"options": [...], "choice": "..."}`, 2–20 different options of 1–500 characters in the order offered; `choice` is one. |
| `origin` | none | `human`, `assisted`, `model`, `tool`, `unknown`. The server stores `model` over MCP and refuses a higher claim with a notice; a refused `human` or `assisted` opens a confirmation (section 5.15). |
| `idempotency_key` | none | `[A-Za-z0-9._:-]{8,128}` (section 7). |

`derived_from` and `supersedes` exist only here. `derived_from` makes the note's rights follow its sources.

| Receipt key | Value |
|---|---|
| `ref`, `origin` | The note reference; the stored origin. |
| `status`, `standing` | `created` or `existing`; the real Standing now (a re-proposal can be `rejected`). |
| `origin_notice` | `origin-claim-refused`, or `null`. |
| `confirmation` | After a `human` or `assisted` claim: `{"url", "expires_at"}` (24 hours). Show the URL to the person. `url` is `null` without `KUTUPHANE_CURATOR_URL`. |
| `licence_notice` | For a note derived (cited, `derived_from`, or through a `derived_from` note) from a `license: unknown` file: `{"paths": ["<book>/<path>", …], "note"}`; unreadable paths only count in `unreadable`. The write is permitted; the note is never exported (#143). |
| `candidates` | Possible duplicates `{ref, match, similarity, kind, standing, text, withheld}` (text: the first 300 characters), at most 5 per match, from readable books: `normalized` (same text after case and white space folding), `vector` (similarity ≥ `KUTUPHANE_NOTE_DUP_SIMILARITY`, default 0.90), `class` (same `class_key`). The server never merges; decide with `link_notes`. |
| `recurrence` | Propose writes over the note's `same_as` cluster. |
| `class_count` | Distinct clusters of evidence notes (`finding`, `lesson`, `dead_end`, `test_result`) with this `class_key` in the book. |
| `guard_due` | `class_count` ≥ 2 and no approved `convention` in the book has the key. |
| `vector` | `stored`, `skipped:search`, `skipped:ai_input`, `skipped:no_route`, `skipped:egress`, `skipped:error`, `skipped:dimensions`. A skip does not stop the write. |

**Minimal receipt** (no `read` on the journal): `{"ref", "status": "recorded", "origin", "origin_notice"}` plus
`confirmation` and `licence_notice`. It does not tell if the note existed.

**Errors:** `400` (validation; `text refused: credential-like content (<rules>)`; a refused code citation, as
`code citation refused: commit_not_published`), `403`, `404` (not a journal; a missing passage or note), `409`,
`429`.

### 5.10 `link_notes`

Link an existing note to a note or a passage; a repeated link is kept once. **Needs:** `propose` on the book of
`src`, `read` on the book of `dst`.

Arguments (all **req**): `src` (a note reference), `type` (`same_as`, `contradicts`, `about`, `fixed_by`,
`violates`, `decided_by`), `dst` (a note reference, or a passage for `about`; `same_as` needs a note in the same
book).

**Result:** `{"src", "type", "dst", "status"}`, `status` `created` or `existing`. **Errors:** `400`
(`<type> exists only as a creation link (propose_note links)`, `a note cannot link to itself`,
`same_as stays inside one book`), `403`, `404`, `429`.

### 5.11 `verify_citations`

Check code citations of a journal's repositories at a branch or commit. No code text is returned. **Needs:** `read`
on the book.

Arguments (all **req**): `book` (the journal slug), `citations` (list of strings: 1–200 code citations of at most
200 lines), `at` (a branch name or a full commit id).

**Result:** `{"targets": {"<journal>/<repo>": <commit>}, "results": [{citation, status, moved_to, symbol_found_at,
reason}]}`.

| Status | Meaning |
|---|---|
| `verified` | The cited lines are the same at the target. |
| `stale` | The lines differ. `moved_to`: the new first line if they occur exactly once; else, with a symbol, `symbol_found_at` (up to 5 lines). |
| `missing` | No such path at the target. |
| `unverifiable` | `reason`: `repo_removed`, `repo_invalid`, `commit_unknown`, `commit_not_published`, `branch_unknown`, `not_a_file`, `too_large`, `binary`, `timeout`. |
| `not_checked` | The repository is not in this journal (no target). |

An unresolved target is `null`. **Errors:** `400` (`give 1 to 200 citations`, `malformed code citation`,
`bad branch name`, `book and at must be strings, citations a list of strings`), `403`.

### 5.12 `query_notes`

List notes of the journals you may read (others are left out silently): SQL filters, no model call, the same bytes
for the same request and data. Use: [agent-memory.md](agent-memory.md#4-read-memory-fast-no-model-call).

| Argument | Default | Limits |
|---|---|---|
| `book` (list of strings) | all readable journals | At most 50. |
| `sets` (list of strings) | `["current"]` | `current`, `open`, `history`. |
| `kind`, `role` (list of strings) | none | Note kinds; `rule`, `evidence`. |
| `origin` (list of strings) | none | `human`, `assisted`, `model`, `unknown` (the shown origin). |
| `class_key` | none | As `propose_note`. |
| `refs` (list of strings) | none | 1–50 note references: only these (unreadable ones are left out). Items add `standing_seq` (the event of the effective Standing, `null` before the first). Other filters and `sets` apply: for any Standing, give all three sets. |
| `repo`, `branch`, `commit` | none | Context. Without `commit`, the branch head is the code target. `commit` (full id) needs `repo`. |
| `path` | none | Context: a path, or a folder prefix ending with `/` that matches a scope glob only when a file below it can match (`*.log` does not match `src/`). |
| `paths` (list of strings) | none | 1–20 more context paths: one query, budget and order. A note is in when one path puts it in `sets`; items add `paths` (those paths). |
| `platform`, `version` | none | kstd Scope context (#164), as `search_library` `context`. A contradicted `applies_to` leaves the note out. A rule note with a bound and no context value is not current (`excluded.needs_context`); evidence stays. Items have `applies_to` only when set. |
| `commits` | none | `A..B`, full ids: observed commit in range. Needs `repo`. At most 10,000 commits. |
| `written_after`, `written_before` | none | ISO 8601; without a zone, UTC. |
| `since` (integer) | none | A watermark: changes after it, and `left` tombstones. |
| `text` | none | 1–1000 characters. Full text over notes that allow search. |
| `unfixed` (boolean) | `false` | Findings without `fixed_by` to an approved or pending note. |
| `collapse` (boolean) | `false` | One item per `same_as` cluster; never across `contradicts`. |
| `include_unverified` (boolean) | `false` | Add approved notes that a failed code check excludes, `current: false`. |
| `min_passed` (integer) | `0` | 0–100 `passed` outcomes ([`record_outcome`](#514-record_outcome)). |
| `exclude_failed` (boolean) | `false` | Leave out notes whose latest outcome is `failed` or `reverted`. |
| `order` | `newest` | `newest`, `oldest`, `relevance` (needs `text`). |
| `budget_tokens` (integer) | `2000` | 200–16000, estimated as bytes ÷ 4. |
| `max_bytes` (integer) | `32768` | 8192–131072, a hard limit. |
| `as_of` (integer) | now | A watermark. |
| `cursor` | none | `next_cursor` of the page before; it sets `as_of`. |

**Sets:** `current`: approved notes current in the context; never a `test_result`; a `rule` needs the context for
each dimension that its scope bounds; a code citation with a target must be `verified`. `open`: pending notes.
`history`: rejected and retired notes, and `test_result` notes.

**Result:** `{"items", "left", "books", "watermark", "next_cursor", "excluded": {"code", "needs_context"},
"targets": {"<journal>/<repo>": <commit>}}`. An item has `ref`, `kind`, `role`, `standing`, `current`, `origin`,
`text`, `withheld`, `class_key`, `scope`, `observed_commit`, `written_at`, `recurrence`, `links` and `outcomes`
(counts), and `citations` (`{ref, status, moved_to, match}`).

- A passage citation keeps its stored handle, with `status` as in `open_citation`; a re-index never drops it.
- A retired item has `successor` (or `null`). `approved_by`: the approving curator (`user:…`), else `null` (also in
  `neighbours` and `open_citation`). With a live confirmation: `entered_by` and `confirmed_by`. An item too large
  alone has its text cut and `text_cut: true`.
- `left`: `{ref, standing, seq, successor}` for notes that a Standing change after `since` moved out. `books`: the
  journals you may read now; drop cached notes of others. `excluded`: notes passed over by the code rule or a
  missing context. Follow `cursor` until `next_cursor` is `null`. `_meta` has the labels.

**Errors:** `400` (`invalid cursor`, `cursor implies its own as_of`, `order relevance needs text`, limits), `409`.

### 5.13 `neighbours`

The notes linked to a note or passage, to depth 1 or 2. Nodes are readable notes in `sets` in your context; edges to
other nodes are dropped. **Needs:** `read` on the book of `ref`.

Arguments: `ref` (**req**, a note reference or a passage handle), `types` (list of strings, default all: link
types, and `cites` for a passage root), `depth` (integer, default `1`, 1–2), `direction` (default `both`, or `out`,
`in`), `max_nodes` (integer, default `50`, 1–200), and `sets`, `repo`, `branch`, `path`, `commit`, `platform`,
`version`, `budget_tokens`, `max_bytes`, `as_of` as `query_notes`.

**Result:** `{"root", "nodes", "edges": [{src, type, dst}], "targets", "watermark", "truncated"}`.

Nodes are `query_notes` items. From a passage, `root` is `null`; the nodes are the notes linked to it (`about`,
`derived_from`) and the notes that cite it (`cites`, after the links); `direction: out` gives none. After a
re-index, a handle also stands for the passages that the passage map joins to it, both ways; such an edge has `dst`
= your handle and `original` = the stored handle (#140). `truncated: true` when `max_nodes` or a size limit cut the
graph. **Errors:** `400`, `403`, `404`, `409`.

### 5.14 `record_outcome`

Record how a note or passage version worked in a task. Outcomes are counts; they never change Standing, and the
`current` rule never reads them. **Needs:** `propose` and `read` on the book.

Arguments (all **req**): `ref` (a note reference or a passage handle), `task_ref` (`[A-Za-z0-9._:/#@+-]{1,200}`),
`result` (`passed`, `failed`, `reverted`, `reopened`), `idempotency_key` (`[A-Za-z0-9._:-]{8,128}`).

**Result:** `{"ref", "task_ref", "result", "origin": "model"}`; a retry gives the first receipt. **Errors:** `400`,
`403`, `404`, `409`, `429`.

### 5.15 `confirm_origin`

The state of the "my words" confirmation of a note (D70 R3), and the URL of its page. A token never stores `human`:
only the person confirms, in curator web, with a passkey act over the exact note id
([who may confirm](operations.md#my-words-confirm-the-origin-of-a-note-d70-r3-r7)). One changed byte is another
note, with origin `model`. **Needs:** `read` on the book; it writes nothing. Argument: `ref` (**req**, a note
reference).

**Result:** `{"ref", "origin", "confirmation": {"state", "url", "expires_at", "claim", "entered_by",
"confirmed_by"}}`; the keys present depend on `state`:

| `state` | Meaning |
|---|---|
| `open` | A propose asked for `human` or `assisted` less than 24 hours ago (`KUTUPHANE_CONFIRM_HOURS`). Has `expires_at`, and `url` when `KUTUPHANE_CURATOR_URL` is set. |
| `confirmed` | Has `claim`, `entered_by`, `confirmed_by`; `origin` is the confirmed value. |
| `expired` | The latest request is older than 24 hours. Propose the same bytes with the same `origin` again. |
| `none` | No request. |

**URL-mode elicitation (2026-07-28).** If the client declares `elicitation.url` and the state is `open`, the first
call returns an `InputRequiredResult` with one URL-mode `elicitation/create` request and a sealed `requestState`.
The person opens the URL in their own browser; retry with the `requestState`. `accept` only means "opened"; it
confirms nothing. Form mode is never used. Other clients: show `url`.

**Errors:** `400`, `403`, `404`.

### 5.16 `submit_package`

Submit a package signed with `kutuphane export`, with the checks of `kutuphane receive`. Nothing is published until a
person runs `kutuphane approve-import` ([operations.md](operations.md#packages-from-an-application-http-and-mcp-139)).
**Needs:** `propose` on the manifest's book; without it nothing is stored. Argument: `package_base64` (**req**, the
package in base64, within the package limit).

**Result:** as `GET /v1/packages/{id}` ([http-api.md](http-api.md#122-get-v1packagesid)): `{"id", "status",
"issuer", "book", "sequence", "content_id", "findings", "diff", "reasons", "received_at", "decided_at"}`; `status`
`received`, `findings` or `refused`; `diff` is `null` without `read` now. **Errors:** `400` (not base64, not a
package, a journal), `403`, too large.

### 5.17 `package_status`

The status of your package (`GET /v1/packages/{id}`): `received`, `findings`, `approved` or `refused`. **Needs:** no
grant; another principal's (or user's) package is not found. Argument: `import_id` (**req**, integer, the `id` of
`submit_package`).

### 5.18 `list_books`

The books and journals that you may read now (#159), sorted by slug; nothing names another book. **Needs:** `read`;
one `list_books` audit event per listed book. No arguments.

**Result:** a list of `{"book", "title", "kind", "content_id", "profile_id", "policy_id", "publication":
{"content_id", "published_at", "channel", "approved_by", "issuer_key", "sequence"}}`.

`kind`: `book`, or `journal` (no files, no publication; `content_id` is `null`; use `query_notes`). `publication`
(#160): the latest publication of the current version. `channel` `ingest`: `approved_by` ran `kutuphane ingest`;
`import`: `approved_by` ran `kutuphane approve-import`, with the signing key fingerprint (`issuer_key`) and package
`sequence`. Before migration 045 these four are `null`. **Errors:** `401`.

### 5.19 `list_files`

The files of a book's current version, a page at a time, with kstd item information (#159). **Needs:** `read`; an
unreadable and a missing book give the same `forbidden`. One `list_files` audit event. Arguments: `book` (**req**),
`cursor` (`next_cursor` of the previous page), `limit` (integer, default 100, 1 to 500 files).

**Result:** `{"book", "content_id", "profile_id", "publication", "files", "next_cursor"}`. A file has `path`,
`sha256`, `size`, `media_type`, `passages` and `item` (kstd: `issuer`, `origin`, `license`, `ai_use`,
`personal_data`, `valid_from`, `valid_to`, `applies_to`, `current`, `scope`, …).

Sorted by path; `next_cursor` is `null` on the last page. `passages`: in the served profile (0: not indexed, for
example quarantined or `ai_use.search` not `y`). `item`: as in `search_library`, `null` without `kstd.yaml` and for
`kstd.yaml`. No file content. **Errors:** `400` (`limit`), `403`, `404` (a journal).

## 6. Background jobs

`ask_library` with `background: true` returns a job at once. Poll `job_status` until `succeeded`, `failed` or
`cancelled`, then call `job_result`. At most 3 `queued` or `running` jobs per principal (one more: `429`).
`KUTUPHANE_JOB_WORKERS` threads in the server process run them (default `1`; `0` runs none; none without LLMDAP,
and then `tools/list` has no job tools). The worker runs as the job's principal and user acted for, so the rights at
run time apply. The lease is 60 seconds, renewed while running; when it ends (for example, the server stopped), the
job is `failed` with `error: interrupted` and never runs again. A cancel or a lease end that commits before the
answer rolls the answer back. Finished jobs and their idempotency keys are deleted after 7 days; the answer stays
(`reopen_answer`). Only the same principal acting for the same user, or that user, sees a job; others get
`not found`.

## 7. Idempotency keys

A key makes a retry safe. `ask_library` (`background: true`, optional), `propose_note` (optional) and
`record_outcome` (**required**) take `[A-Za-z0-9._:-]{8,128}`. The scope is the principal and the user acted for;
the server stores a SHA-256 digest of the other arguments. The same key and request give the first result and
write nothing; another request is refused: `idempotency_key reused with another request` (`409`). Rights are
decided again on each retry. A note or outcome key lives as long as its write; an ask key as long as its job.
Without a key, a retried `propose_note` is one more write (`recurrence` + 1).

## 8. Rate limits and other limits

Memory writes (`propose_note`, `link_notes`, `record_outcome`): `KUTUPHANE_NOTE_WRITES_PER_DAY` per principal per
24 hours (default 500), then `429` `daily note write limit reached (<n>)`. An idempotent retry does not count again.
Open background jobs: 3 per principal (`429` `at most 3 open jobs per principal`). `search_library` `max_chars`:
80–4800, the largest passage of the chunked profile (`400`). MCP request body: 4 MiB (SDK), 1 MiB through the
ingress proxy (`413`). The argument tables give the other limits.

## 9. Check the server with `deploy/mcp_probe.py`

Run on the host against the ingress (Python standard library only), for both protocol versions:

```sh
KUTUPHANE_PROBE_TOKEN=<access token> python3 deploy/mcp_probe.py http://127.0.0.1:8080 [--journal <book>] \
    [--skill skill://<book>/<folder>/SKILL.md]
```

The token comes from `KUTUPHANE_PROBE_TOKEN` and is never printed. `--journal` also writes a real `test_result`
note (needs `propose`). `--skill` declares and tests the Skills extension (needs `read` and `activate`).

Checks, for each version: `tools/list stable` (two calls, same tools, same order),
`search_library structuredContent.result` (the query `probe` gives a list), `search_library _meta kutuphane/handling`,
`no token -> 401 with resource metadata` (`resource_metadata=` in `WWW-Authenticate`), and on 2026-07-28
`Mcp-Name mismatch -> -32020` (`400`: the proxy passes the headers). With `--journal`: `propose_note`. With
`--skill`: `skills/list has <uri>` (one time), `skills/get gives the listed entry`,
`resources/read <uri> size and sha256`. Each prints `ok` or `FAIL`. Exit `0`: all pass; `1`: a check failed; `2`: no
URL or token. Without `propose` or `activate`, those checks fail; that is correct. More:
[troubleshooting.md](troubleshooting.md).

## 10. Skills (SEP-2640)

Kütüphane serves skill folders with the MCP Skills extension (`io.modelcontextprotocol/skills`,
[SEP-2640](https://modelcontextprotocol.io/seps/2640-skills-extension), Final;
[client matrix](https://modelcontextprotocol.io/extensions/client-matrix)). Other clients use `read_document` under
the same gate.

### 10.1 What is a skill here

A folder of the book's current version with a file named exactly `SKILL.md` whose frontmatter has `name` (1–64
characters of `a-z`, `0-9` and single hyphens: the folder name, or the book slug at the root) and `description`
(1–1024 characters); at most 512 files and 16 MiB. A skill holds every file below it, subfolder skills included.
`AGENTS.md`, rules and prompts are not skills; `read_document` reads them.

### 10.2 URIs

`skill://<book>/<folder>/<file>`, each segment percent-encoded, for example
`skill://runbooks/skills/backup/references/restore.md`. It names the file in the current version: a new version
gives new bytes and digests.

### 10.3 Gate

For `skills/list`, `skills/get` and `resources/read`: `read` and `activate` on the book for every principal (a
person too; an agent for a user needs both delegated); AI input in the kstd rights of every file; no blocked file
in the skill or a subfolder skill ([security.md](security.md#skill-scan-skillspector)). Rights and blocks are read
in one statement at the end.

A failing skill is not listed; `skills/get` and `resources/read` refuse it with `forbidden`. `access_event` records
`skills_list` and `skills_get` (mode `read`, skill URIs as items), `activate`, and `read` per file; a blocked listed
skill gives one refused `activate` for its `SKILL.md`; a later refusal (no AI input, not in a served skill), a
refused event per mode with the reason. Events and labels name the version served. The calls read the frontmatter
stored at publication (migration 033).

### 10.4 Declaration

On 2026-07-28, declare
`"io.modelcontextprotocol/clientCapabilities": {"extensions": {"io.modelcontextprotocol/skills": {}}}` in each
request; else `skills/list` and `skills/get` give `-32021` (a required client capability is missing). On 2025-11-25
the server cannot see a declaration and answers any caller. `resources/read` of `skill://` needs none.

### 10.5 `skills/list`

`skills/list` (empty `params`) gives every skill that you may load now, in one page (no `nextCursor`; a `cursor`
gives `-32602`). On 2026-07-28: `ttlMs: 0`, `cacheScope: "private"`.

```json
{"skills": [{
  "uri": "skill://runbooks/skills/backup/SKILL.md",
  "frontmatter": {"name": "backup", "description": "Back up a database the way this team does it"},
  "resources": [{"uri": "skill://runbooks/skills/backup/SKILL.md", "digest": "sha256:5c1f…", "size": 2314}],
  "_meta": {"kutuphane/source": {"book": "runbooks", "content_id": "ct_9f…", "path": "skills/backup/SKILL.md"},
            "kutuphane/handling": {…}}}]}
```

- `frontmatter`: every field as JSON; a YAML date is ISO 8601 text.
- `resources`: every file in path order; `digest` is `sha256:` and the SHA-256 in the content manifest; `size` in
  bytes.
- `_meta.kutuphane/source`: book, `content_id` and path of `SKILL.md`. `_meta.kutuphane/handling`: the labels.

No file content: bytes go out only on `resources/read` (SEP-2640: no fetch ahead of need).

### 10.6 `skills/get`

`skills/get` with `params.uri` = a `SKILL.md` URI gives `{"skill": <entry>}`, as listed (with `ttlMs` and
`cacheScope` on 2026-07-28), to refresh one skill's digests. Not a served `SKILL.md`: `-32602` `not found`; gate
failed: `-32602` `forbidden`.

### 10.7 `resources/read`

`resources/read` with `params.uri` = a `skill://` URI gives one item with the file's media type: `text`, or `blob`
(base64). HTML, JavaScript, SVG and any XML go out as
`text/plain` (`application/octet-stream` when not UTF-8) so a host does not render or run them; bytes and digest do
not change. The item `_meta["kutuphane/handling"]` has the labels. The SHA-256 of the bytes (UTF-8 of `text`) is
the entry's `digest`. A file outside a served skill: `-32602` `not found`. Loading a skill is the host's act.
`resources/list` does not list skill files, and no `resources/directory/read` is declared (`directoryRead` is not
set): the entry lists every file.
