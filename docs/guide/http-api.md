# HTTP API reference

This guide is for developers who call Kütüphane over HTTP. It lists every route of the server.
The HTTP routes call the same code as the MCP tools. For the MCP tools, read [mcp.md](mcp.md).
For the concepts, read [concepts.md](concepts.md) and [agent-memory.md](agent-memory.md).
For rights and tokens, read [security.md](security.md).

## 1. Conventions

### 1.1 Base URL

One server serves the HTTP API, the MCP endpoint and the web UI. Use the public URL of the installation
(`KUTUPHANE_PUBLIC_URL`). The examples use this variable:

```sh
export KUTUPHANE_PUBLIC_URL=https://kutuphane.example
export TOKEN=<access token from the IdP>
```

### 1.2 Authentication

Every `/v1/*` route needs an access token from the identity provider (IdP):

```
Authorization: Bearer <token>
```

- The server verifies the token itself. The token rules are in [mcp.md](mcp.md#31-the-token).
- The caller is only what the verified token says. No header can set or change the principal, or the user that an
  agent acts for.
- A missing token, another scheme, or a token that is not valid gets `401` with `WWW-Authenticate: Bearer`.

### 1.3 Errors

An error has a short JSON body. It never contains internal details.

```json
{"error": "forbidden"}
```

| Status | Body `error` | Cause |
|---|---|---|
| `400` | A validation message, for example `k must be an integer` | The input is not valid. |
| `401` | `unauthenticated` | No valid bearer token. |
| `403` | `forbidden` | The caller does not hold a needed right now, or lost it during the request. |
| `404` | `not found` | The item does not exist, or the caller may not see it. |
| `409` | `authorization changed during the request; retry` | Rights changed two times during one read. |
| `409` | `idempotency_key reused with another request` | The same idempotency key with another request ([mcp.md](mcp.md#7-idempotency-keys)). |
| `429` | `daily note write limit reached (<n>)` or `at most 3 open jobs per principal` | A limit ([mcp.md](mcp.md#8-rate-limits-and-other-limits)). |
| `502` | `model service unavailable or refused` | LLMDAP failed or refused the call. |
| `503` | `answers are not available: this install has no model gateway (LLMDAP); search is full text only` | `POST /v1/ask` on a server without LLMDAP ([light install](install.md#light-install)). |
| `500` | — | An unexpected failure. The server log has the details. |

An unknown path gets `404` with the plain-text body `Not Found`. A known path with a method that the route does not
accept also gets this `404`: the request goes on to the MCP application, which has no such route.

### 1.4 Response headers

Every response has these headers:

| Header | Value |
|---|---|
| `Content-Security-Policy` | `default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self'; connect-src 'self'; font-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'` |
| `X-Content-Type-Options` | `nosniff` |
| `Referrer-Policy` | `no-referrer` |
| `X-Frame-Options` | `DENY` |

### 1.5 Correlation id

Each request gets a new correlation id: ours. The audit records use it.

You can also send your own id in the request header `X-Correlation-Id` (#156). Kütüphane stores it next to ours, as
`caller_correlation_id`, in `access_event`, `model_call` and `write_record` (and on a background job, for its model
calls). It is a label only: it never changes a right, and it is never an idempotency key.

- The pattern is `^[A-Za-z0-9][A-Za-z0-9._:-]{7,63}$`. Any other value gets `400`, and nothing is done.
- Every response of a route that needs a token (errors too, after the token is verified) has the header
  `X-Correlation-Id` with **our** id, and `X-Caller-Correlation-Id` with yours when you sent one.
- `GET /v1/search` and `POST /v1/ask` also give our id in the body as `correlation_id`.
- The model calls of the request send `<your id>.<our id>.<n>` as the LLMDAP correlation id, so the LLMDAP chain
  holds your id too.
- `kutuphane explain <id>` accepts either id ([operations.md](operations.md)).

### 1.6 Text for a model

When the principal is an agent (`agent:…`), the server assumes that the text goes into a model's context. So the
kstd rights of each item apply: when `ai_use.ai_input` is not `y`, the text is not sent. The result has
`"text": null` and `"withheld": "rights do not allow AI input"`. For a person (`user:…`), the text is sent.
Read [kstd.md](kstd.md).

### 1.7 Limits of the ingress proxy

The ingress proxy (`deploy/nginx.conf`) accepts a body of at most 1 MiB (`413` above it). It waits at most
300 seconds for a response. For a long `POST /v1/ask`, use `"background": true` (section 6).

## 2. All routes

`GET` routes also answer `HEAD`.

| Method | Path | Auth | Purpose | Success |
|---|---|---|---|---|
| `GET` | `/healthz` | none | Liveness. | `200` |
| `GET` | `/v1/whoami` | bearer | The caller of the token. | `200` |
| `GET` | `/v1/health` | bearer | Is each dependency up now (booleans only). | `200`, `503` |
| `GET` | `/ui/…` | none | The web UI (static files). Only when `KUTUPHANE_UI_DIR` is set. | `200` |
| `GET` | `/v1/search` | bearer | Search the books you may read. | `200` |
| `GET` | `/v1/citation` | bearer | Open a passage handle or a note reference. | `200` |
| `POST` | `/v1/ask` | bearer | Answer a question with citations, now or as a job. | `200`, `202` |
| `GET` | `/v1/answers/{answer_id}` | bearer | Show a stored answer again. | `200` |
| `GET` | `/v1/jobs/{job_id}` | bearer | The state of a background job. | `200` |
| `GET` | `/v1/jobs/{job_id}/result` | bearer | The answer of a succeeded job. | `200` |
| `POST` | `/v1/jobs/{job_id}/cancel` | bearer | Cancel a background job. | `200` |
| `GET` | `/v1/files/{book}/{content_id}/{path}` | bearer | Download a file of one version. | `200` |
| `POST` | `/v1/notes` | bearer | Write a note into a journal. | `201`, `200` |
| `POST` | `/v1/notes/links` | bearer | Link a note to a note or a passage. | `201`, `200` |
| `POST` | `/v1/citations/verify` | bearer | Check code citations. | `200` |
| `GET` | `/v1/notes` | bearer | List notes with filters. | `200` |
| `GET` | `/v1/notes/{book}/{id}/neighbours` | bearer | The notes linked to a note. | `200` |
| `GET` | `/v1/notes/{book}/{id}/confirmation` | bearer | The "my words" confirmation state of a note and its page URL. | `200` |
| `POST` | `/v1/outcomes` | bearer | Record how a note or passage worked in a task. | `201`, `200` |
| `POST` | `/v1/packages` | bearer | Submit a signed package for a person to approve. | `201` |
| `GET` | `/v1/packages/{id}` | bearer | The status of a package that you submitted. | `200` |
| `POST` | `/mcp` | bearer | The MCP endpoint ([mcp.md](mcp.md)). | `200` |
| `GET` | `/.well-known/oauth-protected-resource` | none | OAuth protected-resource metadata (RFC 9728). | `200` |

No route changes Standing or origin. No route ingests, indexes or approves an import (`POST /v1/packages` only
receives a package). These are command-line
actions ([operations.md](operations.md)), and curator web acts with a passkey (Standing and the origin confirmation).

## 3. Health and identity

### 3.1 `GET /healthz`

Shows that the process answers. It needs no token. It does not check the database.

**Response `200`:** `{"ok": true}`

```sh
curl -s "$KUTUPHANE_PUBLIC_URL/healthz"
```

### 3.2 `GET /v1/whoami`

Shows the principal that the server reads from your token.

**Response `200`:**

```json
{"principal": "agent:adc", "on_behalf_of": "user:ayse"}
```

`on_behalf_of` is `null` when the token does not act for a user.

**Errors:** `401`.

```sh
curl -s -H "Authorization: Bearer $TOKEN" "$KUTUPHANE_PUBLIC_URL/v1/whoami"
```

### 3.3 `GET /v1/health`

Checks each dependency now. Any valid token can call it; it needs no grant. It gives booleans only: no route names,
no model names, no addresses and no error texts.

| Key | `true` when |
|---|---|
| `db` | The database answers. |
| `llmdap` | LLMDAP answered at least one of the model checks below (any HTTP status). |
| `embedding` | The embedding route returned a valid vector. |
| `rerank` | The rerank route returned valid scores. |
| `chat` | The answer model's chat route answered. |
| `ok` | No dependency is `false`. |

A dependency that the server does not configure is `null` (the light install: `llmdap`, `embedding`, `rerank` and
`chat`). When the database does not answer, `db` is `false` and the others are `null`: every model call is recorded
in the database, so the server does not make one.

Each model check is a real call through LLMDAP with a fixed input and no book content (purpose `health`), so it is
in `model_call` and in the LLMDAP audit. The chat check asks for one token. Call it from monitoring at a low rate
(for example once a minute), not per request.

**Response `200`** (all up) or **`503`** (one is `false`):

```json
{"ok": false, "db": true, "llmdap": true, "embedding": true, "rerank": false, "chat": true}
```

```sh
curl -s -H "Authorization: Bearer $TOKEN" "$KUTUPHANE_PUBLIC_URL/v1/health"
```

## 4. Web UI

`/ui/` serves the static files of the web UI from the folder in `KUTUPHANE_UI_DIR`. `/ui/` gives `index.html`.
The container image sets `KUTUPHANE_UI_DIR=/app/ui`. When the variable is not set, the route does not exist.

The static files need no token. The UI calls the `/v1/*` routes with the user's token.

```sh
curl -s "$KUTUPHANE_PUBLIC_URL/ui/"
```

## 5. Search and citations

### 5.1 `GET /v1/search`

Search the books that you may read now. MCP: `search_library` ([mcp.md](mcp.md#51-search_library)).

| Query parameter | Required | Default | Limits |
|---|---|---|---|
| `q` | yes | — | 1–1000 characters, not blank. |
| `k` | no | `8` | An integer, 1–50. |
| `book` | no | none | Repeat for more books. Up to 50 book slugs. |
| `path` | no | none | A relative path prefix. End it with `/` for a folder. |
| `origin` | no | none | Repeat for more. `human`, `assisted`, `model`, `tool`, `unknown`. |
| `current_only` | no | `false` | `true`, `1`, `false` or `0`. |
| `platform` | no | none | The request context (#137): a file whose kstd `applies_to` names other platforms is left out. |
| `version` | no | none | The request context: numbers with dots (`7.0.3`). A file whose `applies_to` version range does not hold it is left out. |
| `max_chars` | no | none (the full text) | An integer, 80–4800. Each `text` becomes a snippet around the match. |

A filter never adds a book. A book that you cannot read gives the same empty result as a book that does not exist.
Notes are not searched here (use `GET /v1/notes`): a journal that you may read in `book` gives `400`
`journal: use query_notes for <journal>; notes are not in search_library or ask_library`. The same applies to
`POST /v1/ask`.

**Response `200`:**

```json
{"correlation_id": "4b0e…",
 "results": [{"citation": "runbooks@ct_9f…/pf_41…/backup.md#3", "page": null, "line": 40, "score": 0.0325,
              "text": "…", "item": null, "quoted_records": []}],
 "retrieval": {"embedding": "ok", "translation": "skipped", "rerank": "ok"}}
```

`retrieval` tells what each model stage of this search did (#136). A stage that fails never stops the search, but
the result is weaker, so check it before you trust an empty or short result:

| Stage | `ok` | `failed` (the search went on without it) | `skipped` |
|---|---|---|---|
| `embedding` | The query vector was used (hybrid search). | The embedding call failed, or its vector does not fit the stored vectors (another width, or nothing indexed for that model): full text only. | No embedding route. |
| `translation` | The answer model translated the query for the passages in the other language. | The translation call failed: the reranker used the question only. | No reranker, no answer model, or all passages in the question's language. |
| `rerank` | The reranker ordered the passages. | The rerank call failed or its answer was not valid: the hybrid order. | No rerank route, or fewer than 2 passages that may go to a model. |

`item` is the kstd item information of the file, or `null` when the version has no `kstd.yaml`. `quoted_records`
gives the handles of the JSONL records whose text the passage repeats (G23), from books that you may read now and
that pass the filters ([concepts.md](concepts.md#records-that-a-passage-repeats)).

With `max_chars`, each `text` is a deterministic snippet of at most `max_chars` characters around the words that
match the query, cut at white space, with `…` on each cut side, and each result has `truncated` (`true` when the
text is cut). The results, their order and their scores do not change, and a withheld text stays `null`. Open the
`citation` for the full passage. The rules are in [mcp.md](mcp.md#51-search_library). Without `max_chars`, the
response is as before.

**Errors:** `400` (`k must be an integer`, `k must be 1..50`, `max_chars must be an integer`,
`max_chars must be 80..4800`, `query must be 1..1000 characters`, `current_only must be true or false`, a filter
not valid, a journal in `book`), `401`, `409`.

```sh
curl -s -G -H "Authorization: Bearer $TOKEN" "$KUTUPHANE_PUBLIC_URL/v1/search" \
  --data-urlencode "q=backup retention" -d k=5 -d book=runbooks -d current_only=true
```

```sh
curl -s -G -H "Authorization: Bearer $TOKEN" "$KUTUPHANE_PUBLIC_URL/v1/search" \
  --data-urlencode "q=backup retention" -d max_chars=300
```

### 5.2 `GET /v1/citation`

Open a passage handle, or a note reference. MCP: `open_citation` ([mcp.md](mcp.md#52-open_citation)).

| Query parameter | Required | Limits |
|---|---|---|
| `handle` | yes | A passage handle `<book>@<content_id>/<profile_id>/<path>#<ordinal>`, or a note reference `<book>@nt_<64 hex>`. |
| `repo` | no | Note references only. The context: a repository slug. |
| `branch` | no | Note references only. The context: a branch. |
| `path` | no | Note references only. The context: a path, or a folder prefix that ends with `/`. |
| `commit` | no | Note references only. The context: a full commit id. Needs `repo`. |
| `platform`, `version` | no | Note references only. The kstd Scope context (#164), as `GET /v1/notes`. |

**Response `200` for a passage:**

```json
{"citation": "runbooks@ct_9f…/pf_41…/backup.md#3", "page": null, "line": 40, "text": "…", "item": null,
 "outcomes": {"passed": 2}, "status": "current"}
```

`status` is `current`, `moved` (with `moved_to` and `match`) or `stale`: where the passage is in the book's current
version after a re-index ([mcp.md](mcp.md#52-open_citation)). A passage citation of a note item has the same keys.

**Response `200` for a note:** `{"citation", "note", "targets", "watermark"}`. `note` is a note item, as in
`GET /v1/notes`.

**Errors:** `400` (`malformed citation handle`), `401`, `403`, `404`, `409`.

```sh
curl -s -G -H "Authorization: Bearer $TOKEN" "$KUTUPHANE_PUBLIC_URL/v1/citation" \
  --data-urlencode "handle=runbooks@ct_9f…/pf_41…/backup.md#3"
```

## 6. Ask, answers and jobs

### 6.1 `POST /v1/ask`

Answer a question from the library, with `[n]` citations. MCP: `ask_library` ([mcp.md](mcp.md#53-ask_library)).

**Body (JSON object):**

| Field | Type | Required | Default | Limits |
|---|---|---|---|---|
| `question` | string | yes | — | 1–1000 characters, not blank. |
| `book` | string or list of strings | no | none | As `GET /v1/search`. |
| `path` | string | no | none | As `GET /v1/search`. |
| `origin` | string or list of strings | no | none | As `GET /v1/search`. |
| `current_only` | boolean | no | `false` | |
| `context` | object | no | none | `{"platform": "vcenter", "version": "7.0.3"}`, both optional, no other keys. As `platform` and `version` of `GET /v1/search`. |
| `background` | boolean | no | `false` | `true` starts a background job. |
| `idempotency_key` | string | no | none | 8–128 characters of `A-Z a-z 0-9 . _ : -`. Only with `"background": true`. |

**Response `200` (`background` is `false`):**

```json
{"id": "5e1c…", "status": "answered", "body": "Backups are kept for 30 days [1].",
 "citations": [{"n": 1, "book": "runbooks", "content_id": "ct_9f…", "profile_id": "pf_41…", "path": "backup.md",
                "ordinal": 3, "line": 12, "record": null, "quoted_records": [], "item": null}],
 "withheld": 0, "retrieval": {"embedding": "ok", "translation": "skipped", "rerank": "ok"},
 "correlation_id": "4b0e…"}
```

- `retrieval` is the status of the search that found the evidence, as in `GET /v1/search`. It is stored with the
  answer.

- `line` is the line where the passage starts, as in `GET /v1/search` (`null` for HTML and PDF). `record` is the
  number of the JSONL record that the passage is in, from 1 (blank lines are not records); `null` for other files and
  for a passage of many records (the `whole` profile).
- `status` is `answered` or `not_in_library`. For `not_in_library`, `body` is `null` and `citations` is empty.
- `withheld` is the number of passages found but not sent to the model, because their kstd rights do not allow AI
  input.
- When a passage repeats the text of a JSONL record, the record is in the evidence right before the passage (at
  most 4 records are added; only with `read` on its book and AI input in its rights). `quoted_records` of a citation
  gives the handles of those records; else it is `[]`.

**Response `202` (`background` is `true`):** `{"job_id": "jb_…", "status": "queued", "correlation_id": "…"}`.
A retry with the same `idempotency_key` and the same request gets `200` with the same `job_id` and its current
status.

**Errors:** `400` (`JSON body required`, `JSON object required`, `question is required`,
`background must be true or false`, `idempotency_key needs background: true`), `401`, `403`, `409`, `429`, `502`,
`503`. The server gives `503` before it reads the body when it has no LLMDAP (the light install).

```sh
curl -s -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  "$KUTUPHANE_PUBLIC_URL/v1/ask" \
  -d '{"question": "How long do we keep backups?", "book": ["runbooks"], "background": true, "idempotency_key": "run-42.ask-1"}'
```

### 6.2 `GET /v1/answers/{answer_id}`

Show a stored answer and its evidence again. There is no model call. Current rights apply.
MCP: `reopen_answer` ([mcp.md](mcp.md#54-reopen_answer)).

The answer must be yours: the same principal acting for the same user, or the user that the answer was made for,
calling directly. You need `read` now on every source book of the answer.

**Response `200`:**

```json
{"id": "5e1c…", "question": "How long do we keep backups?", "status": "answered", "body": "… [1].",
 "evidence": [{"n": 1, "citation": "runbooks@ct_9f…/pf_41…/backup.md#3", "line": 12, "record": null, "text": "…",
               "item": null, "quoted_records": []}],
 "retrieval": {"embedding": "ok", "translation": "skipped", "rerank": "failed"}}
```

`retrieval` is the stored status of the answer's search (`GET /v1/search`); it is `null` for an answer stored before
it existed (#136). `line` and `record` are as in the `citations` of `POST /v1/ask`. They are read from the passage, so an answer that
was stored before they existed has them too.

**Errors:** `401`, `403` (another principal's answer, or a source book is not readable now), `404`.

```sh
curl -s -H "Authorization: Bearer $TOKEN" "$KUTUPHANE_PUBLIC_URL/v1/answers/5e1c…"
```

### 6.3 `GET /v1/jobs/{job_id}`

The state of a background ask job. MCP: `job_status` ([mcp.md](mcp.md#56-job_status)).

**Response `200`:**

```json
{"status": "succeeded", "created_at": "2026-10-27T10:00:00.123456+00:00",
 "started_at": "2026-10-27T10:00:01.002345+00:00", "finished_at": "2026-10-27T10:00:09.871234+00:00", "error": null}
```

`status` is `queued`, `running`, `succeeded`, `failed` or `cancelled`. A failed job has a short `error`, for
example `interrupted`.

**Errors:** `401`, `404` (no such job, a malformed id, or a job of another principal).

```sh
curl -s -H "Authorization: Bearer $TOKEN" "$KUTUPHANE_PUBLIC_URL/v1/jobs/jb_0123456789abcdef0123456789abcdef"
```

### 6.4 `GET /v1/jobs/{job_id}/result`

The answer of a succeeded job, in the shape of `GET /v1/answers/{answer_id}`. Current rights apply.
MCP: `job_result` ([mcp.md](mcp.md#57-job_result)).

**Errors:** `400` (`job has no result: <status>`), `401`, `403`, `404`.

```sh
curl -s -H "Authorization: Bearer $TOKEN" \
  "$KUTUPHANE_PUBLIC_URL/v1/jobs/jb_0123456789abcdef0123456789abcdef/result"
```

### 6.5 `POST /v1/jobs/{job_id}/cancel`

Cancel a background job. A queued job stops at once. A running job stops before its model call or before it
stores its answer. MCP: `job_cancel` ([mcp.md](mcp.md#58-job_cancel)).

**Response `200`:** the job status, as `GET /v1/jobs/{job_id}`. No body is needed.

**Errors:** `401`, `404`.

```sh
curl -s -X POST -H "Authorization: Bearer $TOKEN" \
  "$KUTUPHANE_PUBLIC_URL/v1/jobs/jb_0123456789abcdef0123456789abcdef/cancel"
```

The job rules (limits, lease, retention) are in [mcp.md](mcp.md#6-background-jobs).

## 7. Files

### 7.1 `GET /v1/files/{book}/{content_id}/{path}`

Download one file of one content version. `{path}` can contain `/`.
MCP: `read_document` (text files only) ([mcp.md](mcp.md#55-read_document)).

**Needs:** `read` on the book. An agent needs `activate` too for an agent instruction file. For an agent, the kstd
rights of the file must allow AI input.

**Response `200`:** the file bytes. `Content-Type` is the media type from the version manifest, else
`application/octet-stream`. The headers include `Content-Disposition: attachment` and
`X-Content-Type-Options: nosniff`.

**Errors:** `400` (an unsafe or non-canonical path), `401`, `403`, `404`.

```sh
curl -s -H "Authorization: Bearer $TOKEN" -o backup.md \
  "$KUTUPHANE_PUBLIC_URL/v1/files/runbooks/ct_9f…/backup.md"
```

## 8. Notes (agent memory)

The note rules (kinds, links, Standing, the `current` set) are in [agent-memory.md](agent-memory.md).
The argument limits are the same as for the MCP tools ([mcp.md](mcp.md#59-propose_note)).

### 8.1 `POST /v1/notes`

Write a note into a journal. MCP: `propose_note`.

**Body (JSON object):** the fields `book`, `kind`, `text`, `citations`, `scope`, `commit`, `links`, `class_key`,
`decision`, `origin`, `idempotency_key`. `book`, `kind` and `text` are required. Any other field is refused.

**Response:** `201` for a new write, `200` for an idempotent retry. The body is the receipt
([mcp.md](mcp.md#59-propose_note)).

Over HTTP, the server computes the origin from the token: a person (`user:…` without `act`) gets `unknown`; an agent
path gets `model`. A refused `human` or `assisted` request gives the key `confirmation` (`{"url", "expires_at"}`):
the person confirms on that curator web page with a passkey ([mcp.md](mcp.md#515-confirm_origin)).

**Errors:** `400` (`JSON body required`, `fields: …`, validation, `text refused: credential-like content (…)`, a
code citation refused), `401`, `403`, `404`, `409`, `429`.

```sh
curl -s -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  "$KUTUPHANE_PUBLIC_URL/v1/notes" \
  -d '{"book": "adc-memory", "kind": "finding", "text": "The retry job ignores the backoff limit.", "idempotency_key": "run-42.note-1"}'
```

### 8.2 `POST /v1/notes/links`

Link a note to a note or a passage. MCP: `link_notes` ([mcp.md](mcp.md#510-link_notes)).

**Body (JSON object):** exactly `{"src", "type", "dst"}`.

**Response:** `201` when the link is new, `200` when it exists. The body is
`{"src", "type", "dst", "status"}` with `status` `created` or `existing`.

**Errors:** `400` (`JSON body required`, `JSON object {src, type, dst} required`, validation), `401`, `403`,
`404`, `429`.

```sh
curl -s -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  "$KUTUPHANE_PUBLIC_URL/v1/notes/links" \
  -d '{"src": "adc-memory@nt_3f…", "type": "same_as", "dst": "adc-memory@nt_9a…"}'
```

### 8.3 `GET /v1/notes`

List notes in the journals that you may read. No model call. MCP: `query_notes`
([mcp.md](mcp.md#512-query_notes)).

| Query parameter | Default | Notes |
|---|---|---|
| `book` | all readable journals | Repeat for more. |
| `sets` | `current` | Repeat for more: `current`, `open`, `history`. |
| `kind` | none | Repeat for more. |
| `role` | none | Repeat for more: `rule`, `evidence`. |
| `origin` | none | Repeat for more: `human`, `assisted`, `model`, `unknown` (the shown origin). |
| `class_key` | none | |
| `repo`, `branch`, `path`, `commit`, `platform`, `version` | none | The context. `platform` and `version` are the kstd Scope context of a note's `applies_to` (#164), as `query_notes`. |
| `paths` | none | Repeat for more: 1–20 context paths, as `query_notes` `paths`. |
| `refs` | none | Repeat for more: 1–50 note references, as `query_notes` `refs`. |
| `commits` | none | `A..B`. Needs `repo`. |
| `written_after`, `written_before` | none | ISO 8601 times. |
| `since` | none | An integer watermark. |
| `text` | none | Full-text search. |
| `unfixed`, `collapse`, `include_unverified` | `false` | `true`, `1`, `false` or `0`. |
| `order` | `newest` | `newest`, `oldest`, `relevance`. |
| `budget_tokens` | `2000` | An integer, 200–16000. |
| `max_bytes` | `32768` | An integer, 8192–131072. |
| `as_of` | now | An integer watermark. |
| `cursor` | none | `next_cursor` of the page before. |

**Response `200`:** `{"items", "left", "books", "watermark", "next_cursor", "excluded", "targets"}`
([mcp.md](mcp.md#512-query_notes)). The correlation id is in the header `X-Correlation-Id`.

**Errors:** `400` (`<name> must be an integer`, `<name> must be true or false`, validation), `401`, `409`.

```sh
curl -s -G -H "Authorization: Bearer $TOKEN" "$KUTUPHANE_PUBLIC_URL/v1/notes" \
  -d book=adc-memory -d sets=current -d sets=open -d repo=adc -d branch=main
```

### 8.4 `GET /v1/notes/{book}/{id}/neighbours`

The notes linked to the note `{book}@{id}`. `{id}` is `nt_` and 64 hex characters. MCP: `neighbours`
([mcp.md](mcp.md#513-neighbours)). Over HTTP, the root is always a note. To start from a passage, use the MCP tool.

| Query parameter | Default | Notes |
|---|---|---|
| `types` | all | Repeat for more link types. |
| `depth` | `1` | 1–2. |
| `direction` | `both` | `out`, `in`, `both`. |
| `sets` | `current` | Repeat for more. |
| `repo`, `branch`, `path`, `commit`, `platform`, `version` | none | The context. |
| `max_nodes` | `50` | 1–200. |
| `budget_tokens` | `2000` | 200–16000. |
| `max_bytes` | `32768` | 8192–131072. |
| `as_of` | now | An integer watermark. |

**Response `200`:** `{"root", "nodes", "edges", "targets", "watermark", "truncated"}`. The correlation id is in
the header `X-Correlation-Id`.

**Errors:** `400` (`depth and max_nodes must be integers`, validation), `401`, `403`, `404`, `409`.

```sh
curl -s -G -H "Authorization: Bearer $TOKEN" \
  "$KUTUPHANE_PUBLIC_URL/v1/notes/adc-memory/nt_3f…/neighbours" -d depth=2 -d direction=out
```

### 8.5 `GET /v1/notes/{book}/{id}/confirmation`

The "my words" confirmation of the note `{book}@{id}` (D70 R3). MCP: `confirm_origin`
([mcp.md](mcp.md#515-confirm_origin)). It needs `read` on the book and writes nothing.

**Response `200`:** `{"ref", "origin", "confirmation": {"state", "url"?, "expires_at"?, "claim"?, "entered_by"?,
"confirmed_by"?}}`. `state` is `open`, `confirmed`, `expired` or `none`.

**Errors:** `400`, `401`, `403`, `404`.

```sh
curl -s -H "Authorization: Bearer $TOKEN" "$KUTUPHANE_PUBLIC_URL/v1/notes/adc-memory/nt_3f…/confirmation"
```

## 9. Code citations

### 9.1 `POST /v1/citations/verify`

Check code citations of the repositories of a journal against a branch or a commit. No code text is returned.
MCP: `verify_citations` ([mcp.md](mcp.md#511-verify_citations)).

**Body (JSON object):**

| Field | Type | Required | Limits |
|---|---|---|---|
| `book` | string | yes | The journal slug. You need `read` on it. |
| `citations` | list of strings | yes | 1–200 code citations `<repo>@<commit>:<path>:<start>[-<end>][#<symbol>]`. |
| `at` | string | yes | A branch name or a full commit id. |

**Response `200`:** `{"targets": {...}, "results": [{"citation", "status", "moved_to", "symbol_found_at", "reason"}]}`.

**Errors:** `400` (`JSON body required`, `JSON object required`, `give 1 to 200 citations`,
`malformed code citation`, `bad branch name`), `401`, `403`.

```sh
curl -s -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  "$KUTUPHANE_PUBLIC_URL/v1/citations/verify" \
  -d '{"book": "adc-memory", "citations": ["adc@3f2c…e1:src/run.py:40-52#retry_job"], "at": "main"}'
```

## 10. Outcomes

### 10.1 `POST /v1/outcomes`

Record how a note or a passage worked in a task. Outcomes never change Standing.
MCP: `record_outcome` ([mcp.md](mcp.md#514-record_outcome)).

**Body (JSON object):** exactly these four fields. All are required.

| Field | Limits |
|---|---|
| `ref` | A note reference or a passage handle. |
| `task_ref` | `[A-Za-z0-9._:/#@+-]{1,200}`. |
| `result` | `passed`, `failed`, `reverted`, `reopened`. |
| `idempotency_key` | `[A-Za-z0-9._:-]{8,128}`. |

**Needs:** `propose` and `read` on the book of `ref`.

**Response:** `201` for a new outcome, `200` for an idempotent retry. The body is
`{"ref", "task_ref", "result", "origin"}`.

**Errors:** `400` (`JSON body required`, `fields: ref, task_ref, result, idempotency_key (…)`, validation), `401`,
`403`, `404`, `409`, `429`.

```sh
curl -s -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  "$KUTUPHANE_PUBLIC_URL/v1/outcomes" \
  -d '{"ref": "adc-memory@nt_3f…", "task_ref": "run-42", "result": "passed", "idempotency_key": "run-42.outcome-1"}'
```

## 11. MCP and OAuth metadata

### 11.1 `POST /mcp`

The MCP endpoint. It is stateless and serves the protocol versions 2025-11-25 and 2026-07-28. The MCP SDK does
the token check and the transport checks. Read [mcp.md](mcp.md).

```sh
curl -s -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "MCP-Protocol-Version: 2026-07-28" -H "Mcp-Method: tools/list" \
  "$KUTUPHANE_PUBLIC_URL/mcp" \
  -d '{"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {"_meta": {"io.modelcontextprotocol/protocolVersion": "2026-07-28", "io.modelcontextprotocol/clientCapabilities": {}}}}'
```

### 11.2 `GET /.well-known/oauth-protected-resource`

The OAuth protected-resource metadata (RFC 9728). It needs no token. When `KUTUPHANE_PUBLIC_URL` has a path, the
route is `/.well-known/oauth-protected-resource` followed by that path. The route also answers `OPTIONS`.

The body names the resource (`KUTUPHANE_PUBLIC_URL`) and has one `authorization_servers` entry: exactly
`KUTUPHANE_OIDC_ISSUER`. A `401` from `/mcp` points to this URL in its `WWW-Authenticate` header.

```sh
curl -s "$KUTUPHANE_PUBLIC_URL/.well-known/oauth-protected-resource"
```

## 12. Packages

A consumer application sends a package that it signed with `kutuphane export`. The guide for the whole flow is in
[operations.md](operations.md#packages-from-an-application-http-and-mcp-139).

### 12.1 `POST /v1/packages`

Receive a signed package. The checks are the same as `kutuphane receive`: a trusted and unrevoked key, the
signature, every digest, the content id, the origin lists, a sequence newer than any approved one. Then the scan
and the diff. Nothing is published: a person approves it with `kutuphane approve-import`.
MCP: `submit_package` ([mcp.md](mcp.md#516-submit_package)).

**Body:** the package bytes (the tar file). Any content type; `application/x-tar` is usual. At most the package
limit (`MAX_PACKAGE_BYTES`: the source limit + 1 MiB).

**Needs:** `propose` on the book that the manifest names. Without it: `403`, and nothing is stored.

**Response:** `201`. The body is the import status (section 12.2). A package that fails a check is kept and its
status is `refused`, with the `reasons`.

**Errors:** `400` (`not a readable package: …`, the manifest book is a journal), `401`, `403`, `413` (too large).

### 12.2 `GET /v1/packages/{id}`

The status of an import that you submitted (the same principal and the same user acted for). For anyone else:
`404`.

| Field | Meaning |
|---|---|
| `status` | `received` (verified, no findings), `findings` (verified; a person reads the findings), `approved` (published), `refused` (failed a check, or a person rejected it). |
| `issuer` | The fingerprint of the key that signed it. `null` when the package was refused before verification. |
| `book`, `sequence`, `content_id` | From the verified manifest. |
| `findings` | The scan results for the person who approves. |
| `diff` | `{"added", "removed", "changed"}` against the current version of the book. Only with a current `read` on the book; else `null` (`propose` alone does not list the catalog's files). |
| `reasons` | Why it was refused. |
| `received_at`, `decided_at` | ISO 8601 times. |

For problems, read [troubleshooting.md](troubleshooting.md).
