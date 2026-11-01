# Troubleshooting

## The server does not start

- `server not configured: set KUTUPHANE_PUBLIC_URL` (or `KUTUPHANE_ANSWER_MODEL`): set it. The answer model is
  needed only with `KUTUPHANE_LLMDAP_URL`.
- `identity not configured: set …`: set `KUTUPHANE_OIDC_ISSUER` and `KUTUPHANE_OIDC_JWKS`.
  `KUTUPHANE_OIDC_AUDIENCE` defaults to `kutuphane`.
- `database needs migrations (…): run kutuphane migrate`: run `kutuphane migrate` with the owner DSN, then apply
  `deploy/db-roles.sql`.
- `issuer '…' would be advertised as '…'`: the MCP SDK normalizes the issuer (lowercase host, no default port,
  trailing `/`). Use the shown form in the IdP, `KUTUPHANE_OIDC_ISSUER` and the tokens.
- `KUTUPHANE_OIDC_ISSUERS: …`: the extra-issuers file breaks a rule: a missing or unknown key, a prefix that is not
  `user:`/`agent:` and a name start, two issuers with one prefix, or the primary issuer again
  ([operations.md](operations.md#more-than-one-token-issuer)).
- `401` for a token of an extra issuer: its `sub` (or `act.sub`) is not under its `principal_prefixes`, or it names
  a principal under another issuer's prefixes. `kutuphane whoami` with the token prints the reason
  (`issuer … may not name …`).
- `curate is refused to the principals of issuer …`: set `"curate": true` on that issuer only if its people must
  curate.
- `400` `the caller's correlation id must match …`: the `X-Correlation-Id` header (MCP:
  `_meta["kutuphane/correlation-id"]`, `-32602`) is not 8–64 characters of `A-Z a-z 0-9 . _ : -` that start with a
  letter or digit.
- `LLMDAP not configured: set …`: with `KUTUPHANE_LLMDAP_URL`, also set `KUTUPHANE_LLMDAP_KEY` and
  `KUTUPHANE_LLMDAP_ROUTE`. Or an embedding or rerank route is set without LLMDAP: set LLMDAP or remove the route
  ([light install](install.md#light-install)).
- `LLMDAP not configured: set KUTUPHANE_LLMDAP_…ROUTE_CLASS (…)`: often the host CLI (compose sets `local`; the host
  has no default, G13). Set `local` only for a route that keeps data on premises, else `cloud`. A wrong `local` sends
  `local_only` text to a cloud route.
- `KUTUPHANE_LLMDAP_…ROUTE_CLASS must be local or cloud`.
- `LLMDAP route not configured: set KUTUPHANE_EMBED_MODEL` (or `_RERANK_MODEL`): set the route and its model name
  both, or neither.
- `KUTUPHANE_DSN is not set`: export the DSN (server and CLI).

## HTTP and MCP errors

Causes and fixes: [http-api.md](http-api.md#13-errors).

MCP tools give the same messages as tool errors. MCP `-32020`: the `Mcp-Name` or `Mcp-Method` header differs from
the body; your reverse proxy must pass both unchanged.

## Ingest and index

- ingest refused with a path, line and rule such as `api-key`: the secret scan found a credential. Remove it. For a
  reviewed false positive, add `--accept-finding <path>@sha256:<sha256sum of the file>:<rule>`.
- ingest refused: `kstd.yaml`: run `kutuphane kstd-check <folder>`. A warning does not refuse the book.
- `kstd.yaml <path>: origin 'assisted' not trusted` (or a similar notice): the claim has no evidence, so the file
  counts as `unknown`. Add `reviewed_by` (`assisted`) or `software_agent: {name, version}` (`tool`), or remove the
  unknown field.
- no file is searched after `kstd-init`: it states no `ai_use` term, so every term counts as `n`. Set `ai_use`.
- ingest or `approve-import` refused: `personal-data findings in a cloud_ok book`: a cloud book file has personal or
  fleet data (`receive` lists them as `personal_data`). Review each, then add
  `--accept-finding <path>@sha256:<digest>:<rule>`, set `ai_use.ai_input: n` for the file, or publish with
  `--egress local_only`.
- `kstd-init --source-repo` gives `origin: unknown`, `the content differs`: give the copy's commit with
  `--commit <rev>`.
- a file is in `quarantined`: not extractable (PDF without text layer, encrypted PDF, not UTF-8); stored and
  listed, not searched. Fix it and ingest again.
- a file is not found by search: its `ai_use.search` is not `y`, its format is not searched, or its path is hidden
  (`operations.md`).
- `ingest` or `index` exits with code 3: published, some vectors missing (`index_error`, `failed`,
  `not_attempted`). Run `kutuphane index <book>` later.
- search is slow while indexing: the CPU embedder serves one call at a time. Index when quiet, in smaller
  batches (`KUTUPHANE_INDEX_BATCH`, `KUTUPHANE_INDEX_BATCH_CHARS`). Keep concurrency at 1.
- search is slow, mostly in the rerank call: the CPU reranker reads 30 passages per search (11–25 s). Use profile
  `gpu-rerank` and `KUTUPHANE_LLMDAP_RERANK_ROUTE=rerank-gpu` ([install.md](install.md#gpu-reranker)).
- log `reranking failed, keeping the hybrid order` with `rerank-gpu`, or `"rerank": "failed"` in `retrieval`:
  `reranker-gpu` is not running or not ready (about one minute after start). Start it
  ([install.md](install.md#reboot-and-restart)), or set `KUTUPHANE_LLMDAP_RERANK_ROUTE=rerank`.
- `reranker-gpu` exits with `CUDA error: out of memory` or `Free memory on device`: GPU memory is shared; Docker
  retries 5 times (`restart: on-failure:5`). Then check `free -g` (`available`) and `nvidia-smi`; with 15 GB or more
  available, start it. Do not stop the host's vLLM.
- `restricted content cannot be cloud_ok`: use `--egress local_only` with `--sensitivity restricted`.
- `skill blocked for agents (…): <skill-folder>`: a SkillSpector scan gave `DO_NOT_INSTALL`, was partial, or failed.
  People can still read it. See `kutuphane skill show <book>`. Fix and ingest again, or a curator lifts the block:
  `kutuphane skill clear <book> <skill-folder> --curator user:<name> --reason '…'` with `KUTUPHANE_CURATOR_DSN`.
- `skill blocked … scan failed: timeout after 120 s`: raise `KUTUPHANE_SKILLSPECTOR_TIMEOUT`, then run
  `kutuphane skill rescan --book <book>`. The block stays until a curator clears it.
- `skill not scanned: … KUTUPHANE_SKILLSPECTOR_BIN is not set`: this does not block. To scan, install SkillSpector
  (`install.md`) and run `kutuphane skill rescan`.
- `skill not scanned: skillspector <version> is not the tested <version>`: install the pin with
  `deploy/skillspector/install.sh`, or allow that version with `KUTUPHANE_SKILLSPECTOR_ALLOW_VERSION=<version>`.
- `install.sh`: `refused: sha256 mismatch`: the tarball is not the pinned one. Do not install it. Use a verified copy
  with `SKILLSPECTOR_TARBALL=<file>`.

## Notes and curation

- `KUTUPHANE_CURATOR_DSN is not set (the curator credential)`: `note standing`, `note rollback` and `skill clear`
  need the owner DSN. Type it at the prompt; do not store it where an agent can read it.
- a curator is refused: the user needs `curate` on the book now:
  `kutuphane grant book:<journal> curate user:<name>`.
- `skill clear`: `no block on skill '<folder>'`: the current version has no uncleared block there. Give the
  `SKILL.md` folder (`.` for the root) as `kutuphane skill show <book>` lists it.
- `curate is held only by users, directly`: you cannot grant `curate` to an agent or a role.
- `… was approved before: rejected means never accepted (D68); use retired`: use `retired`.
- `<from> -> <to> is not a Standing transition`: allowed are `pending` → `approved`/`rejected`, `approved` →
  `retired`, `rejected`/`retired` → `pending`.
- an approved note is not in `query_notes`: a `test_result` (always history); a scoped `rule` without request
  context (`excluded.needs_context`); or a code citation not `verified` at the target (`excluded.code`; try
  `include_unverified: true`).
- a pending note is not in `query_notes`: the default set is `current`; ask for `sets: ["open"]`.
- the propose receipt has only `ref`, `status: recorded`, `origin`: the writer lacks `read` on the journal. Grant
  `read` for the full receipt.
- `origin_notice: origin-claim-refused`: the writer asked for `human`, `assisted` or `tool`; the server correctly
  stored the computed origin.
- `vector: skipped:<reason>`: no vector; text search still works. `search` or `ai_input`: the note's rights forbid
  it; `no_route`: no embedding route; `egress`: the egress check refused; `error`: the call failed; `dimensions`:
  wrong vector width.
- `journal: use query_notes for <journal>; notes are not in search_library or ask_library`: a journal in the `book`
  filter of `search_library`, `ask_library` or `GET /v1/search`. Use `query_notes` (`text` for full text) and
  `neighbours`.
- `note … is written: its citations and creation links are part of its id and are fixed`: the database refuses
  changes to a stored note (migration 039). Propose a new note, or add a later link with `link_notes`.
- `curator verify-acts` lists the problem `contents`: an approved or confirmed note no longer has the parts of its
  signed id, so the act no longer counts. Find who wrote the extra rows (`kutuphane explain`); treat the app
  credential as leaked.

## Code citations

- `unverifiable: repo_invalid`: the mirror failed a confinement check (a symlink in the path, not under
  `KUTUPHANE_REPO_ROOTS`, not bare, alternates, grafts, a promisor pack, or a config key that is not allowed). Make
  a plain bare mirror.
- `unverifiable: commit_not_published`: no registered ref reaches the commit. Fetch the branch into the mirror, or
  add a `--ref` pattern.
- `unverifiable: commit_unknown`, `branch_unknown`: run `git fetch` in the mirror. Kütüphane never fetches.
- `unverifiable: timeout`: a git command took over 5 s. Check the disk and repository size.
- `stale` with `moved_to`: the lines moved. Propose a new note with them and a `supersedes` link.

## Background jobs

- `failed` with error `interrupted`: the server stopped during the job; the lease ended. Jobs never run twice.
  Submit again.
- `queued` for a long time: `KUTUPHANE_JOB_WORKERS` is 0, or the workers are busy (default: 1 worker).
- a job is "not found": another principal or delegation context made it, or it ended over 7 days ago. The answer
  stays: use `reopen_answer`.

## Get more detail

- `kutuphane explain <correlation-id>` shows every gate decision and model call of one request;
  `kutuphane explain --answer <answer-id>` does it for an answer. `--llmdap-export <file.jsonl>` joins the LLMDAP
  audit.
- `docker compose --profile app logs core`: the server log with unexpected errors (the caller gets only
  "internal error").
- `python3 deploy/mcp_probe.py <url>` and `deploy/egress_probe.py` check MCP and the network (`install.md`).
