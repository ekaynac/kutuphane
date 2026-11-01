# HTTP API reference

Every HTTP route, for developers. The routes call the same code as the MCP tools; shared rules:
[mcp.md](mcp.md). Concepts: [concepts.md](concepts.md),
[agent-memory.md](agent-memory.md). Rights and tokens: [security.md](security.md).

## 1. Conventions

### 1.1 Base URL

The HTTP API, the MCP endpoint and the web UI are at `KUTUPHANE_PUBLIC_URL`.

### 1.2 Authentication

Every `/v1/*` route needs an access token from the identity provider (IdP): `Authorization: Bearer <token>`.

- The server verifies the token itself ([mcp.md](mcp.md#31-the-token)).
- The caller is only what the verified token says. No header can set or change the principal, or the user that an
  agent acts for.
- A missing token, another scheme, or a token that is not valid gets `401` with `WWW-Authenticate: Bearer`.

### 1.3 Errors

An error has a short JSON body, for example `{"error": "forbidden"}`, with no internal details. Status, body, cause
and fix:

- `400`: a validation message, for example `k must be an integer`. It names the field.
- `401` `unauthenticated`: no, expired, wrong-issuer or wrong-audience token, or a key not in the JWKS. Check with
  `echo "$TOKEN" | kutuphane whoami`.
- `403` `forbidden`: no needed right for this book and mode now, or the right was lost during the request. For an
  agent that acts for a person, check the delegation and the person's right. Agent instructions need `activate`;
  with it, a scan can block the skill: run `kutuphane skill show <book>`.
- `404` `not found`: the item does not exist, or the caller may not see it (also a job of another principal).
- `409` `authorization changed during the request; retry`: rights changed two times during one read. Send it again.
- `409` `idempotency_key reused with another request`: use a new key for a new request; reuse a key only for an
  exact retry ([mcp.md](mcp.md#7-idempotency-keys)).
- `429` `daily note write limit reached (<n>)` (default 500): too many notes, links or outcomes today. Wait, or raise
  `KUTUPHANE_NOTE_WRITES_PER_DAY`. `429` `at most 3 open jobs per principal`: wait, or cancel one with `job_cancel`
  ([mcp.md](mcp.md#8-rate-limits-and-other-limits)).
- `502` `model service unavailable or refused`: LLMDAP is down or refused, or the egress check refused (`local_only`
  book on a `cloud` route). Run `kutuphane explain <correlation-id>`.
- `503` `answers are not available: this install has no model gateway (LLMDAP); search is full text only`:
  `POST /v1/ask` on the [light install](install.md#light-install). Use search and citations, or move to the full stack.
- `500`: unexpected; see the server log.

An unknown path, or a known path with a method that it does not accept, gets `404` with the plain-text body
`Not Found` (the request goes on to the MCP application).

### 1.4 Response headers

Every response has `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, `X-Frame-Options: DENY` and
`Content-Security-Policy: default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self'; connect-src 'self'; font-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'`.

### 1.5 Correlation id

Each request gets a new correlation id (ours) for the audit. You may send your own in the header
`X-Correlation-Id` (#156): it is stored as `caller_correlation_id` in `access_event`, `model_call` and
`write_record` (and on a background job). It is a label only, never a right or an idempotency key.

- The pattern is `^[A-Za-z0-9][A-Za-z0-9._:-]{7,63}$`. Any other value gets `400`, and nothing is done.
- Every response of a route that needs a token (errors too, after the token is verified) has the header
  `X-Correlation-Id` with **our** id, and `X-Caller-Correlation-Id` with yours when you sent one.
- `GET /v1/search` and `POST /v1/ask` also give our id in the body as `correlation_id`.
- Model calls send `<your id>.<our id>.<n>` as the LLMDAP correlation id.
- `kutuphane explain <id>` accepts either id ([operations.md](operations.md)).

### 1.6 Text for a model

For an agent (`agent:…`), the kstd rights of each item apply: when `ai_use.ai_input` is not `y`, the result has
`"text": null` and `"withheld": "rights do not allow AI input"`. A person (`user:…`) gets the text
([kstd.md](kstd.md)).

### 1.7 Limits of the ingress proxy

The ingress proxy (`deploy/nginx.conf`) accepts a body of at most 1 MiB (`413` above it) and waits at most
300 seconds. For a long `POST /v1/ask`, use `"background": true`.

## 2. All routes

`GET` routes also answer `HEAD`. Each route has its own section below. Every route needs a bearer token, except
`GET /healthz`, `GET /ui/…` and `GET /.well-known/oauth-protected-resource`.

No route changes Standing or origin, ingests, indexes or approves an import (`POST /v1/packages` only receives).
Those are CLI actions ([operations.md](operations.md)) or curator web acts with a passkey.

## 3. Health and identity

### 3.1 `GET /healthz`

Liveness. No token; it does not check the database. **`200`:** `{"ok": true}`.

### 3.2 `GET /v1/whoami`

The principal read from your token. **`200`:** `{"principal": "agent:adc", "on_behalf_of": "user:ayse"}`
(`on_behalf_of` is `null` when the token does not act for a user). **Errors:** `401`.

### 3.3 `GET /v1/health`

Checks each dependency now. Any valid token, no grant. Booleans only (no route names, model names, addresses or
error texts): `db` (the database answers), `llmdap` (LLMDAP answered a model check, any HTTP status), `embedding`
(a valid vector), `rerank` (valid scores), `chat` (the answer model answered), `ok` (none is `false`). Not
configured: `null` (light install: `llmdap`, `embedding`, `rerank`, `chat`). When `db` is `false`, the others are
`null`: model calls are recorded in the database, so none is made. Each model check is a real LLMDAP call with a
fixed input and no book content (purpose `health`), recorded in `model_call` and the LLMDAP audit; the chat check
asks for one token. Call it at a low rate (for example once a minute), not per request.

**`200`** when all are up, **`503`** when one is `false`.

## 4. Web UI

`/ui/` serves the static files from the folder in `KUTUPHANE_UI_DIR` (`/ui/` gives `index.html`). The container
image sets `KUTUPHANE_UI_DIR=/app/ui`. When the variable is not set, the route does not exist. The static files need
no token; the UI calls `/v1/*` with the user's token.

## 5. Search and citations

### 5.1 `GET /v1/search`

Search the books that you may read now. MCP: `search_library` ([mcp.md](mcp.md#51-search_library)).

Query parameters:

- `q` (required): 1–1000 characters, not blank.
- `k`: an integer, 1–50. Default `8`.
- `book`: repeat for more; up to 50 book slugs.
- `path`: a relative path prefix. End it with `/` for a folder.
- `origin`: repeat for more. `human`, `assisted`, `model`, `tool`, `unknown`.
- `current_only`: `true`, `1`, `false` or `0`. Default `false`.
- `platform`, `version` (numbers with dots, `7.0.3`): the request context (#137). A file whose kstd `applies_to`
  names other platforms, or a version range that does not hold the version, is left out.
- `max_chars`: an integer, 80–4800. Each `text` becomes a snippet around the match, and each result gets
  `truncated`. Default: the full text. Snippet rules: [mcp.md](mcp.md#51-search_library).

A filter never adds a book. A book that you cannot read gives the same empty result as a missing book.
A journal in `book` gives `400` `journal: use query_notes for <journal>; notes are not in search_library or ask_library`
(use `GET /v1/notes`). The same applies to `POST /v1/ask`.

**`200`:** `{"correlation_id", "results", "retrieval"}`. Each result is
`{"citation", "page", "line", "score", "text", "item", "quoted_records"}`. `item` is the kstd item information of the
file, or `null` without `kstd.yaml`. `quoted_records` gives the handles of the JSONL records whose text the passage
repeats (G23) ([concepts.md](concepts.md#records-that-a-passage-repeats)).

`retrieval` gives each model stage (#136) as `ok`, `skipped`, or `failed` (the search went on without it, weaker:
check it before you trust an empty or short result).

- `embedding`: `ok` is hybrid search. `failed`: the call failed, or its vector does not fit the stored vectors
  (another width, or nothing indexed for that model): full text only. `skipped`: no embedding route.
- `translation`: `ok`, the answer model translated the query for passages in the other language. `failed`: the
  reranker used the question only. `skipped`: no reranker or answer model, or all passages in the question's language.
- `rerank`: `ok`, the reranker ordered the passages. `failed` (call failed or answer not valid): the hybrid order.
  `skipped`: no rerank route, or fewer than 2 passages that may go to a model.

**Errors:** `400` (`k must be an integer`, `k must be 1..50`, `max_chars must be an integer`,
`max_chars must be 80..4800`, `query must be 1..1000 characters`, `current_only must be true or false`, a filter
not valid, a journal in `book`), `401`, `409`.

### 5.2 `GET /v1/citation`

Open a passage handle or a note reference. MCP: `open_citation` ([mcp.md](mcp.md#52-open_citation)).

- `handle` (required): a passage handle `<book>@<content_id>/<profile_id>/<path>#<ordinal>`, or a note reference
  `<book>@nt_<64 hex>`.
- Note references only, the context: `repo` (a repository slug), `branch`, `path` (or a folder prefix that ends with
  `/`), `commit` (a full commit id; needs `repo`), `platform` and `version` (the kstd Scope context, #164, as
  `GET /v1/notes`).

**`200` for a passage:** `{"citation", "page", "line", "text", "item", "publication", "outcomes", "status"}`.
`publication` says who published or approved the
version ([mcp.md](mcp.md#518-list_books)); a passage of a note item has no `publication`. `status`
is `current`, `moved` (with `moved_to` and `match`) or `stale`.

**`200` for a note:** `{"citation", "note", "targets", "watermark"}`; `note` is as in `GET /v1/notes`.

**Errors:** `400` (`malformed passage handle`), `401`, `403`, `404`, `409`.

## 6. Ask, answers and jobs

### 6.1 `POST /v1/ask`

Answer from the library, with `[n]` citations. MCP: `ask_library` ([mcp.md](mcp.md#53-ask_library)).

JSON body:

- `question` (required): 1–1000 characters, not blank.
- `book` (string or list), `path`, `origin` (string or list), `current_only` (boolean, default `false`): as
  `GET /v1/search`.
- `context`: `{"platform": "vcenter", "version": "7.0.3"}`, both optional, no other keys; as `GET /v1/search`.
- `background`: boolean, default `false`. `true` starts a background job.
- `idempotency_key`: 8–128 characters of `A-Z a-z 0-9 . _ : -`. Only with `"background": true`.

**`200` (not background):** `{"id", "status", "body", "citations", "withheld", "retrieval", "correlation_id"}`.
Each citation is `{"n", "book", "content_id", "profile_id", "path", "ordinal", "line", "record", "quoted_records",
"item"}`.

- `status` is `answered` or `not_in_library` (then `body` is `null` and `citations` is empty).
- `retrieval` is as in `GET /v1/search`, and is stored with the answer.
- `line`: where the passage starts (`null` for HTML and PDF). `record`: the JSONL record number, from 1 (blank
  lines do not count); `null` for other files and `whole`-profile passages.
- `withheld` counts the passages not sent to the model because their kstd rights do not allow AI input.
- `quoted_records`: the JSONL records that the passage repeats, added to the evidence before it (at most 4; only
  with `read` on its book and AI input in its rights), else `[]`.

**`202` (background):** `{"job_id": "jb_…", "status": "queued", "correlation_id": "…"}`. A retry with the same
`idempotency_key` and the same request gets `200` with the same `job_id` and its current status.

**Errors:** `400` (`JSON body required`, `JSON object required`, `question is required`,
`background must be true or false`, `idempotency_key needs background: true`), `401`, `403`, `409`, `429`, `502`,
`503`. Without LLMDAP (the light install), `503` comes before the server reads the body.

### 6.2 `GET /v1/answers/{answer_id}`

A stored answer and its evidence, with no model call. Current rights apply.
MCP: `reopen_answer` ([mcp.md](mcp.md#54-reopen_answer)). The answer must be yours (the same principal acting for
the same user, or that user calling directly), and you need `read` now on every source book.

**`200`:** `{"id", "question", "status", "body", "evidence", "retrieval"}`. Each evidence entry is
`{"n", "citation", "line", "record", "text", "item", "quoted_records"}`. `retrieval` is `null` for an answer stored
before it existed (#136).

**Errors:** `401`, `403` (another principal's answer, or a source book is not readable now), `404`.

### 6.3 `GET /v1/jobs/{job_id}`

A background ask job's state. MCP: `job_status` ([mcp.md](mcp.md#56-job_status)).

**`200`:** `{"status", "created_at", "started_at", "finished_at", "error"}`. `status` is `queued`, `running`,
`succeeded`, `failed` or `cancelled`. A failed job has a short `error`, for example `interrupted`.

**Errors:** `401`, `404` (no such job, a malformed id, or a job of another principal).

### 6.4 `GET /v1/jobs/{job_id}/result`

The answer of a succeeded job, as `GET /v1/answers/{answer_id}`. Current rights apply.
MCP: `job_result` ([mcp.md](mcp.md#57-job_result)). **Errors:** `400` (`job has no result: <status>`), `401`,
`403`, `404`.

### 6.5 `POST /v1/jobs/{job_id}/cancel`

Cancel a background job; no body. A queued job stops at once; a running job stops before its model call or before
it stores its answer. MCP: `job_cancel` ([mcp.md](mcp.md#58-job_cancel)). **`200`:** the job status.
**Errors:** `401`, `404`. Job limits, lease and retention: [mcp.md](mcp.md#6-background-jobs).

## 7. Files

### 7.1 `GET /v1/files/{book}/{content_id}/{path}`

Download a file of one version; `{path}` may contain `/`. MCP: `read_document` (text files only)
([mcp.md](mcp.md#55-read_document)). **Needs:** `read` on the book. For an agent, the kstd rights of the file must
allow AI input, and an agent instruction file needs `activate` too.

**`200`:** the file bytes. `Content-Type` is the media type from the version manifest, else
`application/octet-stream`, with `Content-Disposition: attachment` and `X-Content-Type-Options: nosniff`.

**Errors:** `400` (an unsafe or non-canonical path), `401`, `403`, `404`.

### 7.2 `GET /v1/books`

The books and journals you may read now. MCP: `list_books` ([mcp.md](mcp.md#518-list_books)), with the same
entries and keys. Each listed book gets one `list_books` event in the audit log.

**`200`:** `{"books": [{"book", "title", "kind", "content_id", "profile_id", "policy_id", "publication"}]}`.
`kind` is `book` or `journal`; a journal has `"publication": null`. The `publication` keys are in
[mcp.md](mcp.md#518-list_books). **Errors:** `401`.

### 7.3 `GET /v1/books/{book}/files`

The files of a book's current version, a page at a time, with their kstd item information.
MCP: `list_files` ([mcp.md](mcp.md#519-list_files)). **Needs:** `read` on the book. A book that you may not read and
a book that does not exist give the same `403`.

Query: `cursor` (the `next_cursor` of the previous page), `limit` (1 to 500 files, default 100).

**`200`:** `{"book", "content_id", "profile_id", "publication", "files", "next_cursor"}`. Each file is
`{"path", "sha256", "size", "media_type", "passages", "item"}`, sorted by path. `next_cursor` is `null` on the last
page.

**Errors:** `400` (`limit` not an integer, or out of range), `401`, `403`, `404` (a journal: it has no files).

## 8. Notes (agent memory)

The note rules are in [agent-memory.md](agent-memory.md). The argument limits are those of the MCP tools
([mcp.md](mcp.md#59-propose_note)).

### 8.1 `POST /v1/notes`

Write a note into a journal. MCP: `propose_note`.

**Body:** `book`, `kind`, `text` (required), `citations`, `scope`, `commit`, `links`, `class_key`, `decision`,
`origin`, `idempotency_key`. Any other field is refused.

**Response:** `201` for a new write, `200` for an idempotent retry; the body is the receipt.

Over HTTP, the token sets the origin: a person (`user:…` without `act`) gets `unknown`, an agent path `model`. A
refused `human` or `assisted` request gives `confirmation` (`{"url", "expires_at"}`): the person confirms there with
a passkey ([mcp.md](mcp.md#515-confirm_origin)).

**Errors:** `400` (`JSON body required`, `fields: …`, validation, `text refused: credential-like content (…)`, a
code citation refused), `401`, `403`, `404`, `409`, `429`.

### 8.2 `POST /v1/notes/links`

Link a note to a note or passage. MCP: `link_notes` ([mcp.md](mcp.md#510-link_notes)).

**Body:** exactly `{"src", "type", "dst"}`. **Response:** `201` when the link is new, `200` when it exists; the body
is `{"src", "type", "dst", "status"}` with `status` `created` or `existing`.

**Errors:** `400` (`JSON body required`, `JSON object {src, type, dst} required`, validation), `401`, `403`,
`404`, `429`.

### 8.3 `GET /v1/notes`

List notes in the journals that you may read. No model call. MCP: `query_notes`
([mcp.md](mcp.md#512-query_notes)); the parameters have its meanings, defaults and limits.

- Repeat for more: `book` (default: all readable journals), `sets`, `kind`, `role`, `origin`, `paths`, `refs`.
- The context: `repo`, `branch`, `path`, `commit`, `platform`, `version` (#164); `commits` (`A..B`, needs `repo`).
- `class_key`, `text`, `written_after`, `written_before` (ISO 8601), `since`, `as_of`, `cursor`, `order`.
- Booleans (`true`, `1`, `false`, `0`): `unfixed`, `collapse`, `include_unverified`, `exclude_failed`.
- Integers: `min_passed`, `budget_tokens`, `max_bytes`.

**`200`:** `{"items", "left", "books", "watermark", "next_cursor", "excluded", "targets"}`. The correlation id is
in the header `X-Correlation-Id`.

**Errors:** `400` (`<name> must be an integer`, `<name> must be true or false`, validation), `401`, `409`.

### 8.4 `GET /v1/notes/{book}/{id}/neighbours`

The notes linked to the note `{book}@{id}` (`{id}` is `nt_` and 64 hex characters). MCP: `neighbours`
([mcp.md](mcp.md#513-neighbours)). Over HTTP, the root is always a note; to start from a passage, use the MCP tool.

Query (meanings, defaults and limits as the MCP tool): `types` and `sets` (repeat for more), `depth`, `direction`,
the context `repo`, `branch`, `path`, `commit`, `platform`, `version`, and `max_nodes`, `budget_tokens`,
`max_bytes`, `as_of`.

**`200`:** `{"root", "nodes", "edges", "targets", "watermark", "truncated"}`. The correlation id is in the header
`X-Correlation-Id`.

**Errors:** `400` (`depth and max_nodes must be integers`, validation), `401`, `403`, `404`, `409`.

### 8.5 `GET /v1/notes/{book}/{id}/confirmation`

The "my words" confirmation of the note `{book}@{id}`. MCP: `confirm_origin`
([mcp.md](mcp.md#515-confirm_origin)). Needs `read` on the book; writes nothing.

**`200`:** `{"ref", "origin", "confirmation": {"state", "url"?, "expires_at"?, "claim"?, "entered_by"?,
"confirmed_by"?}}`. `state` is `open`, `confirmed`, `expired` or `none`. **Errors:** `400`, `401`, `403`, `404`.

## 9. Code citations

### 9.1 `POST /v1/citations/verify`

Check a journal's code citations against a branch or commit. No code text is returned.
MCP: `verify_citations` ([mcp.md](mcp.md#511-verify_citations)).

**Body (all required):** `book` (the journal slug; you need `read` on it), `citations` (1–200 code citations
`<repo>@<commit>:<path>:<start>[-<end>][#<symbol>]`), `at` (a branch name or a full commit id).

**`200`:** `{"targets": {...}, "results": [{"citation", "status", "moved_to", "symbol_found_at", "reason"}]}`.

**Errors:** `400` (`JSON body required`, `JSON object required`, `give 1 to 200 citations`,
`malformed code citation`, `bad branch name`), `401`, `403`.

## 10. Outcomes

### 10.1 `POST /v1/outcomes`

How a note or passage worked in a task. Outcomes never change Standing.
MCP: `record_outcome` ([mcp.md](mcp.md#514-record_outcome)). **Needs:** `propose` and `read` on the book of `ref`.

**Body:** exactly these four fields, all required: `ref` (a note reference or a passage handle), `task_ref`
(`[A-Za-z0-9._:/#@+-]{1,200}`), `result` (`passed`, `failed`, `reverted`, `reopened`), `idempotency_key`
(`[A-Za-z0-9._:-]{8,128}`).

**Response:** `201` for a new outcome, `200` for an idempotent retry; the body is
`{"ref", "task_ref", "result", "origin"}`.

**Errors:** `400` (`JSON body required`, `fields: ref, task_ref, result, idempotency_key (…)`, validation), `401`,
`403`, `404`, `409`, `429`.

## 11. MCP and OAuth metadata

### 11.1 `POST /mcp`

The stateless MCP endpoint ([mcp.md](mcp.md)) for the protocol versions 2025-11-25 and 2026-07-28. The
MCP SDK does the token check and the transport checks.

### 11.2 `GET /.well-known/oauth-protected-resource`

The OAuth protected-resource metadata (RFC 9728). No token. When `KUTUPHANE_PUBLIC_URL` has a path, the route is
`/.well-known/oauth-protected-resource` followed by that path. It also answers `OPTIONS`. The body names the
resource (`KUTUPHANE_PUBLIC_URL`) and has one `authorization_servers` entry: exactly `KUTUPHANE_OIDC_ISSUER`. A
`401` from `/mcp` points to this URL in its `WWW-Authenticate` header.

## 12. Packages

A consumer application sends a package that it signed with `kutuphane export`. The whole flow is in
[operations.md](operations.md#packages-from-an-application-http-and-mcp-139).

### 12.1 `POST /v1/packages`

Receive a signed package, with the checks of `kutuphane receive` (a trusted and unrevoked key, the signature, every
digest, the content id, the origin lists, a sequence newer than any approved one), then the scan and the diff.
Nothing is published: a person approves it with `kutuphane approve-import`.
MCP: `submit_package` ([mcp.md](mcp.md#516-submit_package)).

**Body:** the package bytes (the tar file); any content type, usually `application/x-tar`. At most the package limit
(`MAX_PACKAGE_BYTES`: the source limit + 1 MiB). **Needs:** `propose` on the book that the manifest names; without
it, `403` and nothing is stored.

**`201`:** the import status (12.2). A package that fails a check is kept with status `refused` and its `reasons`.

**Errors:** `400` (`not a readable package: …`, the manifest book is a journal), `401`, `403`, `413` (too large).

### 12.2 `GET /v1/packages/{id}`

An import that you submitted (same principal, same user acted for); else `404`. Fields:

- `status`: `received` (verified, no findings), `findings` (verified, with findings), `approved` (published),
  `refused` (failed a check, or rejected).
- `issuer`: the fingerprint of the signing key; `null` when refused before verification.
- `book`, `sequence`, `content_id`: from the verified manifest. `findings`: the scan results for the approver.
- `diff`: `{"added", "removed", "changed"}` against the book's current version. Only with a current `read` on the
  book; else `null` (`propose` alone does not list the catalog's files).
- `reasons`: why it was refused. `received_at`, `decided_at`: ISO 8601 times.

For problems, read [troubleshooting.md](troubleshooting.md).
