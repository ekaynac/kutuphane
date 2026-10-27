# Troubleshooting

Find the message or the symptom in the left column. Do the step in the right column.

## The server does not start

| Message | Cause and fix |
|---|---|
| `server not configured: set KUTUPHANE_ANSWER_MODEL, KUTUPHANE_PUBLIC_URL` | Set both. Without LLMDAP, the answer model can be any name; no call is made. |
| `identity not configured: set …` | Set `KUTUPHANE_OIDC_ISSUER`, `KUTUPHANE_OIDC_AUDIENCE` and `KUTUPHANE_OIDC_JWKS`. |
| `database needs migrations (…): run kutuphane migrate` | Run `kutuphane migrate` with the owner DSN, then apply `deploy/db-roles.sql`. |
| `issuer '…' would be advertised as '…'` | The MCP SDK writes the issuer in another form (lowercase host, no default port, a trailing `/`). Configure the IdP and `KUTUPHANE_OIDC_ISSUER` with the form that the message shows. Tokens must carry exactly that string. |
| `LLMDAP not configured: set …` | `KUTUPHANE_LLMDAP_URL` is set, so the other LLMDAP settings are needed: `KUTUPHANE_LLMDAP_KEY`, `KUTUPHANE_LLMDAP_ROUTE`. |
| `LLMDAP route not configured: set KUTUPHANE_EMBED_MODEL` (or `_RERANK_MODEL`) | An embedding or rerank route is set without its model name. Set both or neither. |
| `KUTUPHANE_DSN is not set` | Export the DSN. The server and the CLI use it. |

## HTTP and MCP errors

| Status | Body | Cause and fix |
|---|---|---|
| 401 | `unauthenticated` | No token, an expired token, another issuer or audience, or a key that is not in the JWKS. Check the token with `echo "$TOKEN" \| kutuphane whoami`. |
| 403 | `forbidden` | The principal has no right for this book and mode now. For an agent that acts for a person: check the delegation and the person's own right. For agent instructions: the agent needs `activate`. If the agent has `activate`, the file can be in a skill that a scan blocks: run `kutuphane skill show <book>`. |
| 404 | `not found` | The object does not exist, or the caller may not see it. A job of another principal is also "not found". |
| 409 | `authorization changed during the request; retry` | Rights changed twice during one read. Send the request again. |
| 409 | `idempotency_key reused with another request` | Use a new key for a new request. Use the same key only for an exact retry. |
| 429 | `daily note write limit reached (500)` | The principal wrote too many notes, links or outcomes today. Wait, or raise `KUTUPHANE_NOTE_WRITES_PER_DAY`. |
| 429 | `at most 3 open jobs per principal` | Wait for a job to finish, or cancel one with `job_cancel`. |
| 502 | `model service unavailable or refused` | No model route, LLMDAP is down, LLMDAP refused the call, or the egress check refused it (`local_only` book on a `cloud` route). Run `kutuphane explain <correlation-id>`. |
| 400 | a specific message | The request is malformed. The message names the field. |

MCP tools return the same messages as tool errors. An MCP 2026-07-28 client that gets `-32020` sent an `Mcp-Name`
or `Mcp-Method` header that differs from the body. Check that your reverse proxy passes both headers unchanged.

## Ingest and index

| Symptom | Cause and fix |
|---|---|
| ingest refused: a path, line and rule such as `api-key` | The secret scan found a credential. Remove it. If it is a reviewed false positive, add `--accept-finding <path>@sha256:<sha256sum of the file>:<rule>`. |
| ingest refused: `kstd.yaml` | The manifest has an error. Run `kutuphane kstd-check <folder>` to see the errors. A warning does not refuse the book. |
| a notice such as `kstd.yaml <path>: origin 'assisted' not trusted` | The claim has no evidence, so the file counts as origin `unknown`. Add `reviewed_by` (for `assisted`) or `software_agent: {name, version}` (for `tool`), or remove the unknown field. |
| no file is searched after `kstd-init` | `kstd-init` states no `ai_use` term, so every term counts as `n`. Set `ai_use` in `kstd.yaml`. |
| a file is in `quarantined` | It cannot be extracted (a PDF without a text layer, an encrypted PDF, text that is not UTF-8). It is stored and listed, not searched. Fix the file and ingest again. |
| a file is not found by search | Its `ai_use.search` is not `y`, it is a format that is not searched, or it is under a hidden path. See `operations.md`. |
| `ingest` or `index` exits with code 3 | The book is published, but some vectors are missing (`index_error`, `failed`, `not_attempted`). Run `kutuphane index <book>` later. |
| search is slow while indexing | The CPU embedder serves one call at a time. Index at a quiet time with smaller batches (`KUTUPHANE_INDEX_BATCH`, `KUTUPHANE_INDEX_BATCH_CHARS`). Keep the concurrency at 1. |
| `restricted content cannot be cloud_ok` | `--sensitivity restricted` needs `--egress local_only`. |
| `skill blocked for agents (…): <skill-folder>` | A SkillSpector scan gave `DO_NOT_INSTALL`, did not cover the whole skill, or failed. People can still read it. Run `kutuphane skill show <book>` and read the findings. Fix the skill and ingest again, or let a curator lift the block: `kutuphane skill clear <book> <skill-folder> --curator user:<name> --reason '…'` with `KUTUPHANE_CURATOR_DSN`. |
| `skill blocked … scan failed: timeout after 120 s` | The scan took too long. Raise `KUTUPHANE_SKILLSPECTOR_TIMEOUT`, then run `kutuphane skill rescan --book <book>`. The block stays until a curator clears it. |
| `skill not scanned: … KUTUPHANE_SKILLSPECTOR_BIN is not set` | SkillSpector is not configured. This does not block. To scan, install it (`install.md`) and run `kutuphane skill rescan`. |
| `skill not scanned: skillspector <version> is not the tested <version>` | The installed SkillSpector is not the pinned version. Install the pin with `deploy/skillspector/install.sh`, or allow that exact version with `KUTUPHANE_SKILLSPECTOR_ALLOW_VERSION=<version>`. |
| `install.sh`: `refused: sha256 mismatch` | The downloaded tarball is not the pinned one. Do not install it. Use a verified copy with `SKILLSPECTOR_TARBALL=<file>`. |

## Notes and curation

| Symptom | Cause and fix |
|---|---|
| `KUTUPHANE_CURATOR_DSN is not set (the curator credential)` | `note standing`, `note rollback` and `skill clear` need the owner DSN. Type it at the prompt; do not store it where an agent can read it. |
| a curator is refused | The user needs `curate` on the book now: `kutuphane grant book:<journal> curate user:<name>`. |
| `skill clear`: `no block on skill '<folder>'` | The current version has no uncleared block for that folder. Give the folder of the `SKILL.md` (`.` for the book root), as `kutuphane skill show <book>` lists it. |
| `curate is held only by users, directly` | You cannot grant `curate` to an agent or a role. |
| `… was approved before: rejected means never accepted (D68); use retired` | Use `retired`. |
| `<from> -> <to> is not a Standing transition` | Allowed: `pending` → `approved`/`rejected`, `approved` → `retired`, `rejected`/`retired` → `pending`. |
| an approved note is not in `query_notes` | It is a `test_result` (always history); or it is a scoped `rule` and the request has no context (`excluded.needs_context`); or a code citation is not `verified` at the target (`excluded.code`; try `include_unverified: true`). |
| a pending note is not in `query_notes` | The default set is `current`. Ask for `sets: ["open"]`. |
| the propose receipt has only `ref`, `status: recorded`, `origin` | The writer has `propose` but not `read` on the journal. Grant `read` to get the full receipt. |
| `origin_notice: origin-claim-refused` | The writer asked for `human`, `assisted` or `tool`. The server stored the computed origin. This is correct. |
| `vector: skipped:<reason>` | The note was stored without a vector. `search` or `ai_input`: the note's rights forbid it; `no_route`: no embedding route; `egress`: the egress check refused; `error`: the call failed; `dimensions`: a wrong vector width. Text search still works. |

## Code citations

| Status or reason | Fix |
|---|---|
| `unverifiable: repo_invalid` | The mirror failed a confinement check: a symlink in the path, not under `KUTUPHANE_REPO_ROOTS`, not bare, alternates, grafts, a promisor pack, or a config key that is not allowed. Make a plain bare mirror. |
| `unverifiable: commit_not_published` | No registered ref reaches the commit. Push and fetch the branch into the mirror, or add a `--ref` pattern. |
| `unverifiable: commit_unknown`, `branch_unknown` | The mirror is not current. Run `git fetch` in the mirror. Kütüphane never fetches. |
| `unverifiable: timeout` | A git command took more than 5 s. Check the disk and the size of the repository. |
| `stale` with `moved_to` | The cited lines moved. Propose a new note with the new lines and a `supersedes` link. |

## Background jobs

| Symptom | Cause and fix |
|---|---|
| `failed` with error `interrupted` | The server stopped while the job ran, and the lease ended. Jobs never run twice. Submit again. |
| `queued` for a long time | `KUTUPHANE_JOB_WORKERS` is 0, or the workers are busy. The default is 1 worker. |
| a job is "not found" | Another principal or another delegation context made it, or it finished more than 7 days ago. The answer stays: use `reopen_answer` with its id. |

## Get more detail

- `kutuphane explain <correlation-id>` shows every gate decision and model call of one request.
  `kutuphane explain --answer <answer-id>` does the same for an answer. Add `--llmdap-export <file.jsonl>` to join
  the LLMDAP audit.
- `docker compose --profile app logs core` shows the server log. An unexpected error is logged there; the caller
  gets only "internal error".
- `python3 deploy/mcp_probe.py <url>` and `deploy/egress_probe.py` check MCP and the network (see `install.md`).
