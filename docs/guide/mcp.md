# MCP reference

This guide is for agent developers and operators. It describes the Model Context Protocol (MCP) server of
Kütüphane: the endpoint, the protocol versions, the authentication, and every tool.
For the same functions over plain HTTP, read [http-api.md](http-api.md).
For the concepts (books, journals, notes, Standing), read [concepts.md](concepts.md) and
[agent-memory.md](agent-memory.md). For rights and delegation, read [security.md](security.md).
The design is in [../24-r1-agent-memory-design.md](../24-r1-agent-memory-design.md).

## 1. Endpoint

The MCP endpoint is `/mcp` under the public URL of the installation (`KUTUPHANE_PUBLIC_URL`).
For example: `https://kutuphane.example/mcp`.

- The transport is streamable HTTP. The client sends each JSON-RPC message with `POST /mcp`.
- The server is **stateless**. It does not give an `Mcp-Session-Id`. Each request stands alone.
- State that continues between calls is always an explicit handle: a note reference, a watermark, a cursor,
  a job id or an answer id.
- The tool list is the same for every caller. It changes only with a new deployment.

### 1.1 Request headers

| Header | Value | When |
|---|---|---|
| `Authorization` | `Bearer <access token>` | Always. |
| `Content-Type` | `application/json` | Always. |
| `Accept` | `application/json, text/event-stream` | Always. |
| `MCP-Protocol-Version` | `2025-11-25` or `2026-07-28` | Every request after `initialize` (2025-11-25), or every request (2026-07-28). |
| `Mcp-Method` | The JSON-RPC method, for example `tools/call` | 2026-07-28 only. |
| `Mcp-Name` | The tool name of a `tools/call` | 2026-07-28 only. |

The response is JSON, or a `text/event-stream` with the JSON-RPC message in a `data:` line.
Read both forms.

### 1.2 Transport checks

The MCP SDK does these checks before a tool runs.

| Condition | HTTP status | Body |
|---|---|---|
| The token is missing or not valid. | `401` | `{"error": "invalid_token", "error_description": "Authentication required"}` |
| The `Content-Type` of a `POST` is not `application/json`. | `400` | `Invalid Content-Type header` |
| The `Host` header is not the host of `KUTUPHANE_PUBLIC_URL`. | `421` | `Invalid Host header` |
| An `Origin` header is present and is not the origin of `KUTUPHANE_PUBLIC_URL`. | `403` | `Invalid Origin header` |
| The body is larger than 4 MiB (SDK limit). | `413` | `Request body too large` |
| 2026-07-28: `Mcp-Name` is not the same as the tool name in the body. | `400` | JSON-RPC error code `-32020` |

The `Host` and `Origin` checks protect against DNS rebinding. Set `KUTUPHANE_PUBLIC_URL` to the URL that clients
use. The reverse proxy must pass the `Host` header unchanged.

The ingress proxy in `deploy/nginx.conf` adds two more limits:

- `client_max_body_size 1m`: a body larger than 1 MiB gets `413` from the proxy.
- `proxy_read_timeout 300s`: a request that takes longer than 300 seconds fails at the proxy.
  For a long `ask_library`, use a background job (section 6).

## 2. Protocol versions

One server serves two protocol versions.

### 2.1 2025-11-25 (with `initialize`)

1. Send `initialize`.
2. Send each request with the header `MCP-Protocol-Version: 2025-11-25`.

Because the server is stateless, a client can send `initialize` before each request. `deploy/mcp_probe.py` does
this.

```json
{"jsonrpc": "2.0", "id": 1, "method": "initialize",
 "params": {"protocolVersion": "2025-11-25", "capabilities": {},
            "clientInfo": {"name": "my-agent", "version": "1"}}}
```

### 2.2 2026-07-28 (without `initialize`)

- Do not send `initialize`.
- Put the protocol data in `params._meta` of each request.
- Send the headers `MCP-Protocol-Version: 2026-07-28`, `Mcp-Method`, and (for `tools/call`) `Mcp-Name`.
- The reverse proxy must pass `Mcp-Method` and `Mcp-Name`. The server refuses a request when `Mcp-Name` and the
  body do not agree (`-32020`).

```json
{"jsonrpc": "2.0", "id": 2, "method": "tools/call",
 "params": {"name": "search_library", "arguments": {"query": "backup retention"},
            "_meta": {"io.modelcontextprotocol/protocolVersion": "2026-07-28",
                      "io.modelcontextprotocol/clientCapabilities": {},
                      "io.modelcontextprotocol/clientInfo": {"name": "my-agent", "version": "1"}}}}
```

`clientInfo` is not authenticated. Kütüphane never uses it for rights or origin.

**`server/discover`** (2026-07-28) gives the server capabilities. Its `capabilities.extensions` contains
`io.modelcontextprotocol/oauth-client-credentials`. This tells headless clients that they get tokens with OAuth
client credentials at the identity provider (IdP).

**Cache hints.** The results of `tools/list` and `server/discover` carry `ttlMs: 300000` and
`cacheScope: "public"`. A client can keep them for 5 minutes.

## 3. Authentication

Kütüphane is an OAuth resource server. It does not issue tokens. The IdP issues all tokens.
Kütüphane stores no client secret and accepts no static API key.

### 3.1 The token

Send an access token from the IdP as `Authorization: Bearer <token>`. Kütüphane verifies it itself:

| Check | Rule |
|---|---|
| Signature | A key from the JWKS file in `KUTUPHANE_OIDC_JWKS`. If the token has a `kid`, exactly one key must have that id. |
| Algorithm | `RS256`, `ES256` or `EdDSA`. |
| Required claims | `exp`, `iat`, `iss`, `aud`, `sub`. |
| `iss` | Exactly the same string as `KUTUPHANE_OIDC_ISSUER`. There is no normalization. |
| `aud` | `KUTUPHANE_OIDC_AUDIENCE`. |
| Clock leeway | 30 seconds. |

The caller is only what the verified token says. No header can set or change the principal, or the user that an
agent acts for.

### 3.2 Who the caller is

| Caller | How it gets a token | Principal | Acts for |
|---|---|---|---|
| A person | The interactive OAuth flow of the IdP. | `user:<sub>` | — |
| A headless agent, on its own rights | OAuth client credentials at the IdP. The IdP mapper sets the claim `kutuphane/principal_type: agent` and `sub` = the agent name. | `agent:<sub>` | — |
| A headless agent, for a person | RFC 8693 token exchange at the IdP. The subject token is the person's token (from a one-time interactive consent). The actor token is the client-credentials token. The result has `sub` = the person and `act.sub` = the agent. | `agent:<act.sub>` | `user:<sub>` |

- The claim `kutuphane/principal_type` is `user` (default) or `agent`. Any other value is refused.
- Only one level of `act` is accepted. A nested `act` is refused.
- A token never gives a right by itself. An agent that acts for a person also needs a live delegation from that
  person, and the person must hold the right. Read [security.md](security.md).
- The client of the token is the claim `client_id` (RFC 9068), else `azp`. Kütüphane records it with each write.
  It never changes rights or origin.

To see the principal of a token, call `GET /v1/whoami` ([http-api.md](http-api.md)).

### 3.3 Protected-resource metadata

The server publishes OAuth protected-resource metadata (RFC 9728) at
`/.well-known/oauth-protected-resource` (followed by the path of `KUTUPHANE_PUBLIC_URL`, if it has one).
This route needs no token. Its `authorization_servers` list has one entry: exactly `KUTUPHANE_OIDC_ISSUER`.

A request to `/mcp` without a valid token gets `401`. The `WWW-Authenticate` header points to the metadata:

```
WWW-Authenticate: Bearer error="invalid_token", error_description="Authentication required", resource_metadata="https://kutuphane.example/.well-known/oauth-protected-resource"
```

The server does not start if the MCP SDK would advertise the issuer in another form (for example, an uppercase
host or a default port). Write `KUTUPHANE_OIDC_ISSUER` exactly as the IdP's tokens carry it.

## 4. Results and errors

### 4.1 Result shape

| The tool returns | Where the client finds it |
|---|---|
| An object | `result.content[0].text` holds the object as JSON text. There is no `structuredContent`. |
| A list (`search_library`) | `result.structuredContent.result`, and as JSON text in `result.content`. |
| A string (`read_document`) | `result.structuredContent.result`, and as text in `result.content[0].text`. |

### 4.2 Text for a model

Every MCP caller puts what it reads into a model's context. So the kstd rights of each item apply: when the kstd
`ai_use.ai_input` of an item is not `y`, the server does not send its text. The result has `"text": null` and
`"withheld": "rights do not allow AI input"`. A file without a `kstd.yaml` manifest follows its book policy only.
Read [kstd.md](kstd.md).

### 4.3 Errors

A tool error is a result with `isError: true`. The text is
`Error executing tool <name>: <message>`. The message is short. It never contains internal details.

| Message | Cause | HTTP equivalent |
|---|---|---|
| `forbidden` | The caller does not hold a needed right now, or lost it during the request. | `403` |
| `not found` | The item does not exist, or the caller may not see it. | `404` |
| `authorization changed during the request; retry` | Rights changed two times during one read. | `409` |
| `idempotency_key reused with another request` | Section 7. | `409` |
| `daily note write limit reached (<n>)` | Section 8. | `429` |
| `at most 3 open jobs per principal` | Section 6. | `429` |
| `model service unavailable or refused` | No model route is set, or LLMDAP failed or refused the call. | `502` |
| A validation message, for example `query must be 1..1000 characters` | The input is not valid. | `400` |
| `internal error` | An unexpected failure. The server log has the details. | `500` |

An argument of the wrong type is refused by the MCP SDK before the tool runs. That message comes from the SDK.

## 5. Tools

The tools are in this order in `tools/list`. The order does not change between calls.

| # | Tool | Purpose | HTTP equivalent |
|---|---|---|---|
| 1 | [`search_library`](#51-search_library) | Search the books you may read. | `GET /v1/search` |
| 2 | [`open_citation`](#52-open_citation) | Open a passage handle or a note reference. | `GET /v1/citation` |
| 3 | [`ask_library`](#53-ask_library) | Answer a question with citations. | `POST /v1/ask` |
| 4 | [`reopen_answer`](#54-reopen_answer) | Show a stored answer again. | `GET /v1/answers/{answer_id}` |
| 5 | [`read_document`](#55-read_document) | Read a text file of one version. | `GET /v1/files/{book}/{content_id}/{path}` |
| 6 | [`record_runbook_feedback`](#56-record_runbook_feedback) | Record how a runbook worked. | `POST /v1/feedback` |
| 7 | [`job_status`](#57-job_status) | The state of a background job. | `GET /v1/jobs/{job_id}` |
| 8 | [`job_result`](#58-job_result) | The answer of a succeeded job. | `GET /v1/jobs/{job_id}/result` |
| 9 | [`job_cancel`](#59-job_cancel) | Cancel a background job. | `POST /v1/jobs/{job_id}/cancel` |
| 10 | [`propose_note`](#510-propose_note) | Write a note into a journal. | `POST /v1/notes` |
| 11 | [`link_notes`](#511-link_notes) | Link a note to a note or a passage. | `POST /v1/notes/links` |
| 12 | [`verify_citations`](#512-verify_citations) | Check code citations against a branch or commit. | `POST /v1/citations/verify` |
| 13 | [`query_notes`](#513-query_notes) | List notes with filters. | `GET /v1/notes` |
| 14 | [`neighbours`](#514-neighbours) | The notes linked to a note or a passage. | `GET /v1/notes/{book}/{id}/neighbours` |
| 15 | [`record_outcome`](#515-record_outcome) | Record how a note or passage worked in a task. | `POST /v1/outcomes` |

No tool changes Standing. Only a curator changes Standing, on the command line ([operations.md](operations.md)).

**Handles used below:**

| Handle | Form | Example |
|---|---|---|
| Passage handle | `<book>@<content_id>/<profile_id>/<path>#<ordinal>` | `runbooks@ct_9f…/pf_41…/backup.md#3` |
| Note reference | `<book>@nt_<64 hex>` | `adc-memory@nt_3f…` |
| Code citation | `<repo>@<commit>:<path>:<start>[-<end>][#<symbol>]` | `adc@3f2c…e1:src/run.py:40-52#retry_job` |

### 5.1 `search_library`

Search the books that you may read now. The results carry passage handles for `open_citation`.
The filters narrow the evidence before ranking. A filter never adds a book: a book that you cannot read gives the
same empty result as a book that does not exist.

**Needs:** `read` on each book. An agent also needs `activate` to get instruction passages (agent files). An agent
never gets passages of a skill that a SkillSpector scan blocks ([security.md](security.md#skill-scan-skillspector)).

| Argument | Type | Required | Default | Limits |
|---|---|---|---|---|
| `query` | string | yes | — | 1–1000 characters, not blank. |
| `k` | integer | no | `8` | 1–50. |
| `book` | list of strings | no | none | Up to 50 book slugs. |
| `path` | string | no | none | A relative path prefix. End it with `/` for a folder (`data/`). |
| `origin` | list of strings | no | none | `human`, `assisted`, `model`, `tool`, `unknown`. A book without `kstd.yaml` counts as `unknown`. |
| `current_only` | boolean | no | `false` | Only files whose kstd validity includes now. |

**Result:** `structuredContent.result` is a list. Each entry:

| Key | Value |
|---|---|
| `citation` | The passage handle. |
| `page` | The PDF page, or `null`. |
| `line` | The first line of the passage in a text file, or `null`. |
| `score` | The rank score (4 decimals). |
| `text` | The passage text, or `null` with `withheld` (section 4.2). |
| `item` | The kstd item information of the file, or `null` when the version has no `kstd.yaml`. |

**Errors:** `400` (query, `k` or filter not valid), `409`. When the optional embedding, translation or reranking
route fails, the search continues without that stage. It does not fail.

```json
{"jsonrpc": "2.0", "id": 2, "method": "tools/call",
 "params": {"name": "search_library", "arguments": {"query": "backup retention", "k": 5, "book": ["runbooks"]}}}
```

### 5.2 `open_citation`

Open a passage handle: the exact passage of that version, if you may read it now. Or open a note reference: the
note with its full text, any Standing, and `current` for the optional context.

**Needs:** `read` on the book. For an instruction passage, an agent also needs `activate`, and the passage must not
be in a skill that a scan blocks.

| Argument | Type | Required | Default | Limits |
|---|---|---|---|---|
| `handle` | string | yes | — | A passage handle or a note reference. |
| `repo` | string | no | none | Note references only. A repository slug. |
| `branch` | string | no | none | Note references only. Not empty, no control characters, at most 1000 characters. |
| `path` | string | no | none | Note references only. A relative path, or a folder prefix that ends with `/`. No `..`. |
| `commit` | string | no | none | Note references only. A full commit id. Needs `repo`. |

**Result for a passage handle:**

```json
{"citation": "runbooks@ct_9f…/pf_41…/backup.md#3", "page": null, "line": 40,
 "text": "…", "item": {…}, "outcomes": {"passed": 2}}
```

`outcomes` has the non-zero counts of `record_outcome` for this passage.

**Result for a note reference:** `{"citation", "note", "targets", "watermark"}`. `note` is one note item, as in
`query_notes` (section 5.13).

**Errors:** `400` (`malformed citation handle`, or a context value not valid), `403`, `404`, `409`.

```json
{"jsonrpc": "2.0", "id": 3, "method": "tools/call",
 "params": {"name": "open_citation", "arguments": {"handle": "adc-memory@nt_3f…", "repo": "adc", "branch": "main"}}}
```

### 5.3 `ask_library`

Answer a question from the library. The answer cites passages as `[n]`. When the passages do not answer the
question, the status is `not_in_library`. The answer is in the language of the question (Turkish or English).

The server sends a passage to the answer model only when its kstd rights allow AI input. The answer model is
called through LLMDAP.

**Needs:** `read` on the books of the passages. An agent also needs `activate` for instruction passages. An agent is
refused when an instruction source is in a skill that a scan blocks.
The server decides the rights again after the model call.

| Argument | Type | Required | Default | Limits |
|---|---|---|---|---|
| `question` | string | yes | — | 1–1000 characters, not blank. |
| `book` | list of strings | no | none | As `search_library`. |
| `path` | string | no | none | As `search_library`. |
| `origin` | list of strings | no | none | As `search_library`. |
| `current_only` | boolean | no | `false` | As `search_library`. |
| `background` | boolean | no | `false` | `true` starts a background job (section 6). |
| `idempotency_key` | string | no | none | 8–128 characters of `A-Z a-z 0-9 . _ : -`. Only with `background: true` (section 7). |

**Result (`background: false`):**

| Key | Value |
|---|---|
| `id` | The answer id. Use it with `reopen_answer`. |
| `status` | `answered` or `not_in_library`. |
| `body` | The answer text, or `null`. |
| `citations` | A list of `{n, book, content_id, profile_id, path, ordinal, item}` for each cited passage. |
| `withheld` | The number of passages found but not sent to the model (kstd rights). |

**Result (`background: true`):** `{"job_id": "jb_…", "status": "queued"}` at once. A retry with the same
`idempotency_key` gives the same job and its current status.

**Errors:** `400` (`question is required`, `background must be true or false`,
`idempotency_key needs background: true`), `403`, `409`, `429` (open jobs), `502` (no model route, or the model
failed).

```json
{"jsonrpc": "2.0", "id": 4, "method": "tools/call",
 "params": {"name": "ask_library", "arguments": {"question": "How long do we keep backups?",
            "background": true, "idempotency_key": "run-42.ask-1"}}}
```

### 5.4 `reopen_answer`

Show a stored answer and its evidence again. There is no model call. Current rights apply.

**Needs:** The answer must be visible to you: the same principal acting for the same user, or the user that the
answer was made for, calling directly. You also need `read` now on every source book of the answer (and, for an
agent, `activate` for instruction passages). An agent is refused when a source is now in a skill that a scan blocks.

| Argument | Type | Required | Default | Limits |
|---|---|---|---|---|
| `answer_id` | string | yes | — | The `id` of an answer. |

**Result:**

```json
{"id": "5e1c…", "question": "…", "status": "answered", "body": "… [1]",
 "evidence": [{"n": 1, "citation": "runbooks@ct_…/pf_…/backup.md#3", "text": "…", "item": null}]}
```

An evidence entry can have `"text": null` with `withheld` (section 4.2).

**Errors:** `403` (the answer belongs to another principal, or a source book is not readable now), `404`.

```json
{"jsonrpc": "2.0", "id": 5, "method": "tools/call",
 "params": {"name": "reopen_answer", "arguments": {"answer_id": "5e1c…"}}}
```

### 5.5 `read_document`

Read a text file of one specific content version.

**Needs:** `read` on the book. An agent needs `activate` too for an agent instruction file, and the file must not be
in a skill that a scan blocks. The kstd rights of the
file must allow AI input.

| Argument | Type | Required | Default | Limits |
|---|---|---|---|---|
| `book` | string | yes | — | The book slug. |
| `content_id` | string | yes | — | The content version id (`ct_…`). |
| `path` | string | yes | — | A relative path. No `.` or `..` segments. |

**Result:** the file text, in `structuredContent.result`.

**Errors:** `400` (`not a text document; use search_library and open_citation for its passages` when the media
type is not `text/markdown` or `text/plain`; an unsafe path), `403` (no right, or the kstd rights do not allow AI
input), `404`.

```json
{"jsonrpc": "2.0", "id": 6, "method": "tools/call",
 "params": {"name": "read_document", "arguments": {"book": "runbooks", "content_id": "ct_9f…", "path": "backup.md"}}}
```

### 5.6 `record_runbook_feedback`

Record how applying a runbook went, for that exact file version.

**Needs:** `read` on the book.

| Argument | Type | Required | Default | Limits |
|---|---|---|---|---|
| `book` | string | yes | — | The book slug. |
| `content_id` | string | yes | — | The content version id. |
| `path` | string | yes | — | The file path in that version. |
| `outcome` | string | yes | — | `worked`, `failed` or `changed`. |
| `tested_on` | string | no | none | 1–200 characters, not blank. Where you tested it. |
| `note` | string | no | none | At most 2000 characters. |

**Result:** `{"id": <integer>}`.

**Errors:** `400`, `403`, `404` (the file is not in that version).

```json
{"jsonrpc": "2.0", "id": 7, "method": "tools/call",
 "params": {"name": "record_runbook_feedback", "arguments": {"book": "runbooks", "content_id": "ct_9f…",
            "path": "backup.md", "outcome": "worked", "tested_on": "staging-2"}}}
```

### 5.7 `job_status`

The state of a background `ask_library` job.

| Argument | Type | Required | Default | Limits |
|---|---|---|---|---|
| `job_id` | string | yes | — | `jb_` and 32 hex characters. |

**Result:**

```json
{"status": "running", "created_at": "2026-10-27T10:00:00.123456+00:00",
 "started_at": "2026-10-27T10:00:01.002345+00:00", "finished_at": null, "error": null}
```

`status` is `queued`, `running`, `succeeded`, `failed` or `cancelled`. `error` is a short message when the job
failed, for example `interrupted` or `forbidden`.

**Errors:** `404` (no such job, a malformed id, or a job that is not visible to you).

```json
{"jsonrpc": "2.0", "id": 8, "method": "tools/call",
 "params": {"name": "job_status", "arguments": {"job_id": "jb_0123456789abcdef0123456789abcdef"}}}
```

### 5.8 `job_result`

The answer of a succeeded job, in the same shape as `reopen_answer`. Current rights apply. The `id` in the result
is the answer id: keep it to call `reopen_answer` later.

| Argument | Type | Required | Default | Limits |
|---|---|---|---|---|
| `job_id` | string | yes | — | As `job_status`. |

**Errors:** `400` (`job has no result: <status>` when the job did not succeed), `403` (a source book is not
readable now), `404`.

```json
{"jsonrpc": "2.0", "id": 9, "method": "tools/call",
 "params": {"name": "job_result", "arguments": {"job_id": "jb_0123456789abcdef0123456789abcdef"}}}
```

### 5.9 `job_cancel`

Cancel a background job. A queued job stops at once. A running job stops before its model call, or before it
stores its answer. A finished job does not change.

| Argument | Type | Required | Default | Limits |
|---|---|---|---|---|
| `job_id` | string | yes | — | As `job_status`. |

**Result:** the job status, as `job_status`. A running job can still show `running` until its worker sees the
cancel.

**Errors:** `404`.

```json
{"jsonrpc": "2.0", "id": 10, "method": "tools/call",
 "params": {"name": "job_cancel", "arguments": {"job_id": "jb_0123456789abcdef0123456789abcdef"}}}
```

### 5.10 `propose_note`

Write a note into a journal. A note starts `pending`. Only a curator approves it. The same bytes again in the same
book are the same note: the receipt has `status: existing` and `recurrence` goes up by 1.

**Needs:** `propose` on the journal, and `read` on the book of every cited passage and every link target. With
`read` on the journal too, you get the full receipt. Without it, you get the minimal receipt.

| Argument | Type | Required | Default | Limits |
|---|---|---|---|---|
| `book` | string | yes | — | A journal slug. |
| `kind` | string | yes | — | `finding`, `decision_proposal`, `dead_end`, `convention`, `lesson`, `test_result`. |
| `text` | string | yes | — | 1–8000 characters, not blank, no NUL. Text that looks like a credential is refused. |
| `citations` | list of strings | no | `[]` | At most 20. Passage handles or code citations. A code citation must name a repository of this journal and a published commit. |
| `scope` | object | no | none | `{"repo": <slug>, "branch": <name>, "paths": [<glob>]}`. `repo` is required and must be a live repository of the journal. At most 20 `paths`. Globs: `**` any characters, `*` any except `/`, `?` one character except `/`. |
| `commit` | string | no | none | The observed commit: a full commit id (40 or 64 hex). Needs `scope`. |
| `links` | list of objects | no | `[]` | At most 20 `{"type", "ref"}`. Types: `derived_from`, `supersedes`, `same_as`, `contradicts`, `about`, `fixed_by`, `violates`, `decided_by`. `ref` is a note reference or a passage handle. A passage can be the target of `derived_from` or `about` only. `same_as` stays in one book. The same link two times is refused. |
| `class_key` | string | no | none | `[a-z0-9][a-z0-9._:/-]{0,79}`. |
| `decision` | object | no | none | `kind: decision_proposal` only. `{"options": [...], "choice": "..."}`: 2–20 different options of 1–500 characters, in the order offered; `choice` is one of them. |
| `origin` | string | no | none | `human`, `assisted`, `model`, `tool`, `unknown`. The server computes the origin. Over MCP it stores `model`. A request for a higher value is refused with a notice. |
| `idempotency_key` | string | no | none | `[A-Za-z0-9._:-]{8,128}` (section 7). |

`derived_from` and `supersedes` exist only as creation links. `derived_from` makes the rights of the note follow
its sources. Read [agent-memory.md](agent-memory.md).

**Full receipt:**

```json
{"ref": "adc-memory@nt_3f…", "status": "created", "standing": "pending",
 "origin": "model", "origin_notice": null,
 "candidates": [{"ref": "adc-memory@nt_9a…", "match": "vector", "similarity": 0.93, "kind": "finding",
                 "standing": "approved", "text": "first 300 characters", "withheld": null}],
 "recurrence": 1, "class_count": 2, "guard_due": true, "vector": "stored"}
```

| Key | Value |
|---|---|
| `status` | `created` or `existing`. |
| `standing` | The real Standing now. For a re-proposal it can be `rejected`. |
| `origin_notice` | `origin-claim-refused` when the requested origin was refused, else `null`. |
| `candidates` | Possible duplicates: `normalized` (same text after case and white space folding), `vector` (similarity at or above `KUTUPHANE_NOTE_DUP_SIMILARITY`, default 0.90), `class` (same `class_key` in the book). At most 5 per match type. Only from books you may read. The server never merges notes. Use `link_notes` to decide. |
| `recurrence` | The number of propose writes over the `same_as` cluster of the note. |
| `class_count` | The number of distinct clusters with this `class_key` in the book. |
| `guard_due` | `true` when `class_count` ≥ 2 and no approved `convention` note has this `class_key` in the book. |
| `vector` | `stored`, `skipped:search`, `skipped:ai_input`, `skipped:no_route`, `skipped:egress`, `skipped:error` or `skipped:dimensions`. A skipped vector does not stop the write. |

**Minimal receipt** (no `read` on the journal): `{"ref", "status": "recorded", "origin", "origin_notice"}`.
It does not tell if the note existed.

**Errors:** `400` (validation; `text refused: credential-like content (<rules>)`; a code citation refused, for
example `code citation refused: commit_not_published`), `403`, `404` (the book is not a journal; a cited passage
or linked note does not exist), `409`, `429`.

```json
{"jsonrpc": "2.0", "id": 11, "method": "tools/call",
 "params": {"name": "propose_note", "arguments": {"book": "adc-memory", "kind": "finding",
            "text": "The retry job ignores the backoff limit.",
            "scope": {"repo": "adc", "branch": "main", "paths": ["src/jobs/**"]},
            "idempotency_key": "run-42.note-1"}}}
```

### 5.11 `link_notes`

Link a note to a note or a passage, after the note exists. The same link again is kept once.

**Needs:** `propose` on the book of `src`, and `read` on the book of `dst`.

| Argument | Type | Required | Default | Limits |
|---|---|---|---|---|
| `src` | string | yes | — | A note reference. |
| `type` | string | yes | — | `same_as`, `contradicts`, `about`, `fixed_by`, `violates`, `decided_by`. |
| `dst` | string | yes | — | A note reference or a passage handle. A passage is allowed for `about` only. `same_as` needs a note in the same book. |

**Result:** `{"src": "<ref>", "type": "<type>", "dst": "<ref or handle>", "status": "created"}`.
`status` is `existing` when the link was there before.

**Errors:** `400` (`<type> exists only as a creation link (propose_note links)` for `derived_from` and
`supersedes`; `a note cannot link to itself`; `same_as stays inside one book`), `403`, `404`, `429`.

```json
{"jsonrpc": "2.0", "id": 12, "method": "tools/call",
 "params": {"name": "link_notes", "arguments": {"src": "adc-memory@nt_3f…", "type": "same_as",
            "dst": "adc-memory@nt_9a…"}}}
```

### 5.12 `verify_citations`

Check code citations of the repositories of a journal against a branch or a commit. No code text is returned.

**Needs:** `read` on the book.

| Argument | Type | Required | Default | Limits |
|---|---|---|---|---|
| `book` | string | yes | — | The journal slug. |
| `citations` | list of strings | yes | — | 1–200 code citations. At most 200 lines each. |
| `at` | string | yes | — | A branch name or a full commit id. |

**Result:**

```json
{"targets": {"adc-memory/adc": "3f2c…e1"},
 "results": [{"citation": "adc@…:src/run.py:40-52", "status": "stale", "moved_to": 61,
              "symbol_found_at": null, "reason": null}]}
```

| Status | Meaning |
|---|---|
| `verified` | The cited lines are the same at the target. |
| `stale` | The file exists, but the lines differ. `moved_to` is the new first line if the same lines occur exactly once. Else, with a symbol, `symbol_found_at` lists up to 5 lines with the symbol. |
| `missing` | The path does not exist at the target. |
| `unverifiable` | The check could not be made. `reason`: `repo_removed`, `repo_invalid`, `commit_unknown`, `commit_not_published`, `branch_unknown`, `not_a_file`, `too_large`, `binary`, `timeout`. |
| `not_checked` | The repository of the citation is not registered in this journal, so it has no target. |

A target is `null` in `targets` when it could not be resolved.

**Errors:** `400` (`give 1 to 200 citations`, `malformed code citation`, `bad branch name`,
`book and at must be strings, citations a list of strings`), `403`.

```json
{"jsonrpc": "2.0", "id": 13, "method": "tools/call",
 "params": {"name": "verify_citations", "arguments": {"book": "adc-memory",
            "citations": ["adc@3f2c…e1:src/run.py:40-52#retry_job"], "at": "main"}}}
```

### 5.13 `query_notes`

List agent notes in the journals that you may read. It uses fast SQL filters and makes no model call. The same
request on the same data gives the same bytes.

**Needs:** `read` on each journal. Other journals are left out without an error.

| Argument | Type | Required | Default | Limits |
|---|---|---|---|---|
| `book` | list of strings | no | all readable journals | At most 50 slugs. |
| `sets` | list of strings | no | `["current"]` | `current`, `open`, `history`. |
| `kind` | list of strings | no | none | The note kinds. |
| `role` | list of strings | no | none | `rule`, `evidence`. |
| `origin` | list of strings | no | none | `model`, `unknown`. |
| `class_key` | string | no | none | As `propose_note`. |
| `repo` | string | no | none | The context: a repository slug. |
| `branch` | string | no | none | The context: a branch. Without `commit`, its head is the code target. |
| `path` | string | no | none | The context: one path, or a folder prefix that ends with `/`. |
| `commit` | string | no | none | The context: a full commit id. Needs `repo`. |
| `commits` | string | no | none | `A..B` with two full commit ids. Notes whose observed commit is in that range. Needs `repo`. At most 10,000 commits. |
| `written_after` | string | no | none | ISO 8601 time. Without a time zone, UTC. |
| `written_before` | string | no | none | ISO 8601 time. |
| `since` | integer | no | none | A watermark from an earlier response. Gives the changes after it, and `left` tombstones. |
| `text` | string | no | none | 1–1000 characters. Full-text search over notes that allow search. |
| `unfixed` | boolean | no | `false` | Only findings without a `fixed_by` link to an approved or pending note. |
| `collapse` | boolean | no | `false` | One item per `same_as` cluster. Notes joined by `contradicts` are never collapsed. |
| `include_unverified` | boolean | no | `false` | Also give approved notes that a failed code check excludes, with `current: false`. |
| `order` | string | no | `newest` | `newest`, `oldest`, `relevance` (needs `text`). |
| `budget_tokens` | integer | no | `2000` | 200–16000. An estimate: response bytes ÷ 4. |
| `max_bytes` | integer | no | `32768` | 8192–131072. A hard limit on the whole response. |
| `as_of` | integer | no | now | A watermark from an earlier response. |
| `cursor` | string | no | none | `next_cursor` of the page before. It sets `as_of` itself. |

The sets:

| Set | Contains |
|---|---|
| `current` | Approved notes that are current in the context. A `test_result` is never current. A `rule` note needs the context for each dimension that its scope bounds. A code citation with a target must be `verified`. |
| `open` | Pending notes (not accepted). |
| `history` | Rejected and retired notes, and `test_result` notes. |

**Result:**

```json
{"items": [{"ref": "adc-memory@nt_…", "kind": "finding", "role": "evidence", "standing": "approved",
            "current": true, "origin": "model", "text": "…", "withheld": null, "class_key": "cwe-89",
            "scope": {"repo": "adc", "branch": "main", "paths": ["src/db/**"]}, "observed_commit": "…",
            "written_at": "2026-10-27T10:00:00Z", "recurrence": 3, "links": {"contradicts": 1},
            "outcomes": {"passed": 2}, "citations": [{"ref": "adc@…:src/db/q.py:40-52", "status": "stale",
            "moved_to": 61}]}],
 "left": [], "books": ["adc-memory"], "watermark": 81234, "next_cursor": null,
 "excluded": {"code": 2, "needs_context": 1}, "targets": {"adc-memory/adc": "3f2c…"}}
```

- A retired item has `successor`: the note that supersedes it, or `null`.
- An item that alone does not fit the limits has its text cut and `text_cut: true`.
- `left` holds tombstones `{ref, standing, seq, successor}` for notes that a Standing change after `since` moved
  out of the sets.
- `books` lists the journals that you may read now. Drop cached notes of other books.
- `excluded` counts the notes that this page passed over because of the code rule or a missing context.
- Keep calling with `cursor` until `next_cursor` is `null`.

**Errors:** `400` (`invalid cursor`, `cursor implies its own as_of`, `order relevance needs text`, limits), `409`.

```json
{"jsonrpc": "2.0", "id": 14, "method": "tools/call",
 "params": {"name": "query_notes", "arguments": {"book": ["adc-memory"], "sets": ["current", "open"],
            "repo": "adc", "branch": "main", "path": "src/db/q.py"}}}
```

### 5.14 `neighbours`

The notes linked to a note reference or a passage handle, to depth 1 or 2. Only notes that you may read and that
are in `sets` in your context are nodes. An edge to an excluded node is dropped.

**Needs:** `read` on the book of `ref`.

| Argument | Type | Required | Default | Limits |
|---|---|---|---|---|
| `ref` | string | yes | — | A note reference or a passage handle. |
| `types` | list of strings | no | all | Link types. |
| `depth` | integer | no | `1` | 1–2. |
| `direction` | string | no | `both` | `out`, `in`, `both`. |
| `sets` | list of strings | no | `["current"]` | As `query_notes`. |
| `repo`, `branch`, `path`, `commit` | string | no | none | The context, as `query_notes`. |
| `max_nodes` | integer | no | `50` | 1–200. |
| `budget_tokens` | integer | no | `2000` | 200–16000. |
| `max_bytes` | integer | no | `32768` | 8192–131072. |
| `as_of` | integer | no | now | A watermark. |

**Result:**

```json
{"root": {…}, "nodes": [{…}], "edges": [{"src": "adc-memory@nt_…", "type": "fixed_by", "dst": "adc-memory@nt_…"}],
 "targets": {}, "watermark": 81234, "truncated": false}
```

`root` and each node are note items, as in `query_notes`. With a passage handle, `root` is `null` and the nodes are
the notes linked to the passage (`about`, `derived_from`). `truncated` is `true` when `max_nodes` or the size
limits cut the graph.

**Errors:** `400`, `403`, `404`, `409`.

```json
{"jsonrpc": "2.0", "id": 15, "method": "tools/call",
 "params": {"name": "neighbours", "arguments": {"ref": "adc-memory@nt_3f…", "depth": 2, "direction": "out"}}}
```

### 5.15 `record_outcome`

Record how a note or a passage worked in a task. The outcome is for that exact version. Outcomes are counts on the
item. They never change its Standing, and the `current` rule never reads them.

**Needs:** `propose` and `read` on the book of the item.

| Argument | Type | Required | Default | Limits |
|---|---|---|---|---|
| `ref` | string | yes | — | A note reference or a passage handle. |
| `task_ref` | string | yes | — | Your task or run id: `[A-Za-z0-9._:/#@+-]{1,200}`. |
| `result` | string | yes | — | `passed`, `failed`, `reverted`, `reopened`. |
| `idempotency_key` | string | yes | — | `[A-Za-z0-9._:-]{8,128}` (section 7). |

**Result:** `{"ref": "...", "task_ref": "...", "result": "passed", "origin": "model"}`.
A retry with the same key gives the first receipt.

**Errors:** `400`, `403`, `404`, `409`, `429`.

```json
{"jsonrpc": "2.0", "id": 16, "method": "tools/call",
 "params": {"name": "record_outcome", "arguments": {"ref": "adc-memory@nt_3f…", "task_ref": "run-42",
            "result": "passed", "idempotency_key": "run-42.outcome-1"}}}
```

## 6. Background jobs

A long `ask_library` can run as a durable background job.

1. Call `ask_library` with `background: true`. You get `{"job_id": "jb_…", "status": "queued"}` at once.
2. Call `job_status` until `status` is `succeeded`, `failed` or `cancelled`.
3. Call `job_result` to get the answer.
4. To stop the job, call `job_cancel`.

| Item | Value |
|---|---|
| Open jobs | At most 3 `queued` or `running` jobs per principal. One more gets `429`. |
| Workers | `KUTUPHANE_JOB_WORKERS` threads in the server process (default `1`). `0` runs no jobs. With no model route, no worker starts. |
| Rights | The worker runs the ask with the principal and the user acted for of the job. So the rights at run time apply. |
| Lease | 60 seconds. The worker renews it while the job runs. |
| Interrupted job | When a running job's lease ends (for example, the server stopped), the job becomes `failed` with `error: interrupted`. It never runs again. |
| Cancel | A cancel or a lease end that commits before the answer rolls the answer back. |
| Retention | Finished jobs are deleted after 7 days, with their idempotency keys. The answer stays. Reopen it with `reopen_answer` and the `id` from `job_result`. |
| Visibility | The same principal acting for the same user, or that user calling directly. Anyone else gets `not found`. |

## 7. Idempotency keys

An idempotency key makes a retry safe. A broken response stream can make a client send the same request again.

| Tool | Key | Format |
|---|---|---|
| `ask_library` (`background: true`) | optional | 8–128 characters of `A-Z a-z 0-9 . _ : -` |
| `propose_note` | optional | `[A-Za-z0-9._:-]{8,128}` |
| `record_outcome` | **required** | `[A-Za-z0-9._:-]{8,128}` |

- The scope of a key is the principal and the user acted for.
- The server stores a SHA-256 digest of the request arguments (all except the key).
- The same key with the same request gives the first result. It writes nothing new.
- The same key with another request is refused: `idempotency_key reused with another request` (HTTP `409`).
- The rights are decided again on each retry. A revoked right still refuses.
- A `propose_note` key and a `record_outcome` key live as long as their write. An `ask_library` key lives as long
  as its job (7 days after the end).

Without a key, a retried `propose_note` is one more write, and `recurrence` goes up by 1.

## 8. Rate limits and other limits

| Limit | Value | Error |
|---|---|---|
| Memory writes per principal per 24 hours | `KUTUPHANE_NOTE_WRITES_PER_DAY` (default 500). Counts `propose_note`, `link_notes` and `record_outcome` writes. | `429` `daily note write limit reached (<n>)` |
| Open background jobs per principal | 3 | `429` `at most 3 open jobs per principal` |
| Query and question length | 1–1000 characters | `400` |
| `search_library` `k` | 1–50 | `400` |
| Note text | 8000 characters | `400` |
| Citations, links, scope paths, decision options per note | 20 each | `400` |
| Code citations per `verify_citations` | 200 | `400` |
| MCP request body | 4 MiB (SDK); 1 MiB through the ingress proxy | `413` |

An idempotent retry of `propose_note` or `record_outcome` does not count again.

## 9. Check the server with `deploy/mcp_probe.py`

`deploy/mcp_probe.py` checks MCP through the reverse proxy, for both protocol versions. It uses the Python
standard library only. Run it on the host against the ingress.

```sh
KUTUPHANE_PROBE_TOKEN=<access token> python3 deploy/mcp_probe.py http://127.0.0.1:8080 [--journal <book>]
```

- The script reads the token from `KUTUPHANE_PROBE_TOKEN`. It never prints the token.
- Give `--journal <book>` to also test `propose_note`. The token needs `propose` on that journal.
  The probe writes a real `test_result` note.

For each protocol version, it checks:

| Check | Pass condition |
|---|---|
| `tools/list stable` | Two calls give the same tools in the same order. |
| `search_library structuredContent.result` | `search_library` with the query `probe` answers with a list in `structuredContent.result`. |
| `propose_note` | Only with `--journal`. The call is not an error. |
| `no token -> 401 with resource metadata` | `tools/list` without a token gets `401` and `resource_metadata=` in `WWW-Authenticate`. |

For 2026-07-28 only, it also checks `Mcp-Name mismatch -> -32020`: an `Mcp-Name` header that is not the same as
the body gets `400` with code `-32020`. This shows that the proxy passes the MCP headers.

Each check prints `ok` or `FAIL`. The exit code is `0` only when every check passes. It is `1` when a check fails,
and `2` when the URL or the token is missing.

With a token that has no `propose` right, the two `propose_note` checks fail with `forbidden`. This is correct.

For other problems, read [troubleshooting.md](troubleshooting.md).
