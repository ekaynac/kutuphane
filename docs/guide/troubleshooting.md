# Troubleshooting

Find the message or the symptom in the left column. Do the step in the right column.

## The server does not start

| Message | Cause and fix |
|---|---|
| `server not configured: set KUTUPHANE_PUBLIC_URL` (or `KUTUPHANE_ANSWER_MODEL`) | Set it. The answer model is needed only with `KUTUPHANE_LLMDAP_URL`. |
| `identity not configured: set …` | Set `KUTUPHANE_OIDC_ISSUER` and `KUTUPHANE_OIDC_JWKS`. `KUTUPHANE_OIDC_AUDIENCE` is `kutuphane` when it is not set. |
| `database needs migrations (…): run kutuphane migrate` | Run `kutuphane migrate` with the owner DSN, then apply `deploy/db-roles.sql`. |
| `issuer '…' would be advertised as '…'` | The MCP SDK writes the issuer in another form (lowercase host, no default port, a trailing `/`). Configure the IdP and `KUTUPHANE_OIDC_ISSUER` with the form that the message shows. Tokens must carry exactly that string. |
| `LLMDAP not configured: set …` | `KUTUPHANE_LLMDAP_URL` is set, so the other LLMDAP settings are needed: `KUTUPHANE_LLMDAP_KEY`, `KUTUPHANE_LLMDAP_ROUTE`. Or an embedding or rerank route is set without LLMDAP: Core calls models only through LLMDAP, so set LLMDAP or remove the route ([light install](install.md#light-install)). |
| `LLMDAP not configured: set KUTUPHANE_LLMDAP_…ROUTE_CLASS (…)` | Often the CLI on the host: compose sets each route class to `local`, the host has no default (G13). Set `local` for a route that keeps the data on premises, else `cloud`. A wrong `local` sends `local_only` text to a cloud route. |
| `KUTUPHANE_LLMDAP_…ROUTE_CLASS must be local or cloud` | Set one of the two values. |
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
| 502 | `model service unavailable or refused` | LLMDAP is down, LLMDAP refused the call, or the egress check refused it (`local_only` book on a `cloud` route). Run `kutuphane explain <correlation-id>`. |
| 503 | `answers are not available: this install has no model gateway (LLMDAP); search is full text only` | The server has no LLMDAP (the light install). Use `search_library` and `open_citation`, or move to the full stack. |
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
| ingest or `approve-import` refused: `personal-data findings in a cloud_ok book` | The book sends passages to cloud models, and the file has personal data or fleet data. Review each finding (`receive` lists them for a package as `personal_data`), then add `--accept-finding <path>@sha256:<digest>:<rule>`, set `ai_use.ai_input: n` for the file in `kstd.yaml`, or publish with `--egress local_only`. |
| `kstd-init --source-repo` gives `origin: unknown`, `the content differs` | The copy is older or newer than the commit. Give the commit that the copy was taken at with `--commit <rev>`. |
| a file is in `quarantined` | It cannot be extracted (a PDF without a text layer, an encrypted PDF, text that is not UTF-8). It is stored and listed, not searched. Fix the file and ingest again. |
| a file is not found by search | Its `ai_use.search` is not `y`, it is a format that is not searched, or it is under a hidden path. See `operations.md`. |
| `ingest` or `index` exits with code 3 | The book is published, but some vectors are missing (`index_error`, `failed`, `not_attempted`). Run `kutuphane index <book>` later. |
| search is slow while indexing | The CPU embedder serves one call at a time. Index at a quiet time with smaller batches (`KUTUPHANE_INDEX_BATCH`, `KUTUPHANE_INDEX_BATCH_CHARS`). Keep the concurrency at 1. |
| search is slow, and most of the time is the rerank call | The CPU reranker reads 30 passages per search (11–25 s). Use the GPU reranker: profile `gpu-rerank` and `KUTUPHANE_LLMDAP_RERANK_ROUTE=rerank-gpu` ([install.md](install.md#gpu-reranker)). |
| the log shows `reranking failed, keeping the hybrid order` with `rerank-gpu`, or a result has `"rerank": "failed"` in `retrieval` | `reranker-gpu` is not running or not ready yet (about one minute after the start). Start it ([install.md](install.md#reboot-and-restart)), or switch back to the CPU route with `KUTUPHANE_LLMDAP_RERANK_ROUTE=rerank`. |
| `reranker-gpu` exits with `CUDA error: out of memory` or `Free memory on device` | The GPU memory is shared; Docker tries the start again up to 5 times (`restart: on-failure:5`). If it stays stopped, check `free -g` (`available`) and `nvidia-smi`; with 15 GB or more available, start it again. Do not stop the host's vLLM for it. |
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
| `journal: use query_notes for <journal>; notes are not in search_library or ask_library` | You named a journal in the `book` filter of `search_library`, `ask_library` or `GET /v1/search`. Notes are not searched there. Use `query_notes` (`text` for full text) and `neighbours`. |
| `note … is written: its citations and creation links are part of its id and are fixed` | A writer tried to add a citation or a creation link to a stored note. The database refuses it (migration 039): propose a new note with the parts, or add a later link with `link_notes`. |
| `curator verify-acts` lists the problem `contents` | A note that an act approved or confirmed no longer has the parts of its signed id. Its approval and its confirmation no longer count. Find who wrote the extra rows (`kutuphane explain`), and treat the app credential as leaked. |

## Code citations

| Status or reason | Fix |
|---|---|
| `unverifiable: repo_invalid` | The mirror failed a confinement check: a symlink in the path, not under `KUTUPHANE_REPO_ROOTS`, not bare, alternates, grafts, a promisor pack, or a config key that is not allowed. Make a plain bare mirror. |
| `unverifiable: commit_not_published` | No registered ref reaches the commit. Push and fetch the branch into the mirror, or add a `--ref` pattern. |
| `unverifiable: commit_unknown`, `branch_unknown` | The mirror is not current. Run `git fetch` in the mirror. Kütüphane never fetches. |
| `unverifiable: timeout` | A git command took more than 5 s. Check the disk and the size of the repository. |
| `stale` with `moved_to` | The cited lines moved. Propose a new note with the new lines and a `supersedes` link. |

## Decider and delegations

| Message | Cause and fix |
|---|---|
| `N shadow decisions of … a delegation needs at least 30` | Too few notes of the class have a suggestion before a person's verdict at this threshold. Run the decider in shadow mode longer, or choose a lower threshold. |
| `stopped: … waits for 3 open samples` | Three sampled notes wait for a person. Decide them on the phone; the next run continues. |
| `stopped: user:… no longer holds curate on book:…` | The creator lost `curate`. The delegation does nothing; end it and sign a new one. |
| `failed: the answer names revision …` | The model server reports another revision than the spec. Check the model server; for a planned change, write a new spec version. |
| `spec: route locality 'cloud': a decider uses local routes only` | A decider spec must name a `local` LLMDAP route. |

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
