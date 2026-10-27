# Kütüphane

Versioned, explainable knowledge access for people and LLM agents, on-prem and air-gapped.
Decisions: `docs/01-direction-decisions.md`. Product: `docs/05`–`07`. Code: Apache-2.0 (`LICENSE`); specification text: CC-BY-4.0 (`NOTICE`).

## Development (M1a)

```sh
python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'
printf 'KUTUPHANE_DB_PASSWORD=%s\n' "$(python3 -c 'import secrets;print(secrets.token_urlsafe(24))')" > .env
docker compose up -d --wait postgres
docker compose exec -T postgres psql -U kutuphane -c 'CREATE DATABASE kutuphane_test'

set -a; . ./.env; set +a
export KUTUPHANE_DSN="postgresql://kutuphane:${KUTUPHANE_DB_PASSWORD}@127.0.0.1:55432/kutuphane"
export KUTUPHANE_TEST_DSN="${KUTUPHANE_DSN}_test"
.venv/bin/python -m pytest -q

.venv/bin/kutuphane migrate
.venv/bin/kutuphane ingest tests/fixtures/okf-kitap --book ornek \
  --sensitivity normal --egress local_only --protection standard
.venv/bin/kutuphane show ornek
```

What `ingest` takes from a folder (`src/kutuphane/source.py`, `profiles.py`, `agentfiles.py`, `secretscan.py`):

- **Searched:** markdown; PDF text layers; `.txt`, `.json`, `.jsonl`/`.ndjson` (one passage per record), `.yaml`,
  `.toml`, `.sh`, `.py`, `.js`, `.ts`, `.xml`, `.csv`, `.mdc` as plain text; `.html` by its visible text only (no
  scripts or styles). A file is text only if it is UTF-8 without NUL bytes. Text passages carry their start `line`.
  Other files are stored and can be read, but are not searched.
- **Quarantined, not refused:** a file that cannot be extracted (a PDF without a text layer, an unreadable or
  encrypted PDF, a text file that is not UTF-8) is stored and listed but not indexed. `ingest` and `approve-import`
  report it in `quarantined` (and on stderr), `show` lists it. The version that fixes the file indexes it.
- **Refused (the whole book):** an invalid `kstd.yaml`; a symlink, a path or size violation; markdown that is not
  UTF-8 or has invalid frontmatter; a credential-like file name (`credentials.json`, `*.env`, `id_rsa`, key stores,
  `settings.local.json`) or credential-like text (keys, tokens, passwords, private key blocks). The scan reads the
  original text and the extracted text that is cut into passages (HTML with entities decoded, PDF text layers),
  JSON/JSONL key-value pairs with escapes decoded, and quoted literals whatever characters they hold. Placeholders
  (`${PASSWORD}`, `<your-key>`, `changeme`) and semantic constants (`token: refresh_token`) are not credentials. The
  error names the path, the line and the rule (e.g. `assigned-credential`, `api-key`), never the matched text.
- **A reviewed false positive** can be accepted, narrowly: `ingest … --accept-finding <path>@sha256:<digest>:<rule>`
  (repeatable; `<digest>` is `sha256sum <file>`). It covers that rule's findings in exactly that file content; a
  changed file has another digest and is refused again, and an acceptance that matches no finding refuses the
  ingest. Accepted findings are recorded in the publication (`accepted_findings` in the result and in `show`) and
  printed on stderr. `kstd-init` and `kstd-check` scan the same way and take the same `--accept-finding` values.
  Package receipt accepts nothing: the receiving node scans again.
- **Hidden paths** stay out (`.git/`, `.env*`, dotfiles), except the agent folders `.claude/` (`agents`,
  `commands`, `rules`, `skills`, `hooks`, and `CLAUDE.md`), `.cursor/rules/`, `.github/` (`copilot-instructions.md`,
  `instructions/`, `prompts/`, `agents/`, `chatmodes/`), `.agents/` and `.codex/`.
- **Agent instructions** (K3): files in those folders, files in a skill folder (next to a `SKILL.md`), files whose
  names start with `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, `SKILL.md` or `copilot-instructions.md`, Cursor `.mdc`
  rules, Copilot `.instructions.md`/`.prompt.md`/`.agent.md`/`.chatmode.md`, and frontmatter types such as `skill`.
  People read them with `read`; an agent also needs `activate`.

A book published by an older reader keeps its old index until it is ingested again (a new profile id). Migration
011 marks the stored passages that the wider K3 rule makes instructions, so they need `activate` at once.

A folder can carry a `kstd.yaml` manifest (the kstd standard, L0): rights, origin and validity of its files, which
Kütüphane then enforces and shows. See `kstd/README.md` (`kutuphane kstd-init`, `kutuphane kstd-check`).

Disk encryption is a deployment requirement at the volume level (D48); the application does not encrypt.

Run the API + MCP server (M1e) behind the ingress proxy, with core isolated on an internal network:

```sh
KUTUPHANE_PUBLIC_URL=http://127.0.0.1:8080 KUTUPHANE_OIDC_ISSUER=<issuer> KUTUPHANE_ANSWER_MODEL=<model> \
KUTUPHANE_OIDC_JWKS_FILE=<jwks.json> docker compose --profile app up -d --build
docker compose --profile app exec -T core python -I - < deploy/egress_probe.py   # AT-10 network check
```

Real local models (D61; nothing leaves the machine): Qwen3.8-27B on the host's vLLM for answers, bge-m3 and
bge-reranker-v2-m3 on CPU for vectors and reranking. Download the pinned weights once (`deploy/llmdap/README.md`), then:

```sh
docker compose -f compose.yaml -f deploy/compose.local-models.yaml \
  --profile app --profile decision-models --profile local-models up -d --build
```

Agent memory (R1, `docs/24`): a **journal** is a book whose items are notes that agents write with `propose_note`
(MCP) or `POST /v1/notes`, and link with `link_notes` / `POST /v1/notes/links`. Writers need the `propose` mode.
A note starts `pending`; only a curator changes its Standing, and only on the command line:

```sh
.venv/bin/kutuphane journal create adc-memory --search y --ai-input y \
  --sensitivity normal --egress local_only --protection standard --by user:admin
.venv/bin/kutuphane grant book:adc-memory propose agent:adc
.venv/bin/kutuphane grant book:adc-memory curate user:ayse      # users only; never delegated
KUTUPHANE_CURATOR_DSN=… .venv/bin/kutuphane note standing adc-memory@nt_… approved --curator user:ayse --reason "…"
```

Database roles: the server and every process an agent can reach connect as `kutuphane_app`
(`KUTUPHANE_APP_DB_PASSWORD` in `.env`), which cannot write Standing. `KUTUPHANE_CURATOR_DSN` is the owner role
(`kutuphane migrate`, `kutuphane note standing`); keep it out of every environment an agent can read. Create the
app role once (`CREATE ROLE kutuphane_app LOGIN PASSWORD '…'`), then apply `deploy/db-roles.sql` as the owner
after every `kutuphane migrate`. Without `KUTUPHANE_CURATOR_DSN`, `migrate` uses `KUTUPHANE_DSN` (one-role
development databases). `KUTUPHANE_NOTE_WRITES_PER_DAY` (500) limits writes (notes, links, outcomes) per principal;
`KUTUPHANE_NOTE_DUP_SIMILARITY` (0.90) is the vector candidate threshold.

Outcomes and decision records (R2 #74, `docs/24` §19): `record_outcome` / `POST /v1/outcomes` records
`passed`, `failed`, `reverted` or `reopened` for a task on one exact note or passage version (needs `propose` and
`read` on its book, and an `idempotency_key`). Reads show the counts; Standing never changes. A `decision_proposal`
note can carry `decision: {options, choice}`. `kutuphane decisions export <principal> --out FILE` writes JSONL
decision records; their text, options and choice are present only when the note allows `ai_input` and `train`
(`journal create --train y`, default `n`), else only references and hashes.

Identity and egress (M1c) are configured by environment:
`KUTUPHANE_OIDC_ISSUER`, `KUTUPHANE_OIDC_AUDIENCE`, `KUTUPHANE_OIDC_JWKS` (path to a JWKS file);
`KUTUPHANE_LLMDAP_URL`, `KUTUPHANE_LLMDAP_KEY` (Core's LLMDAP subject key; LLMDAP runs with
`GATEWAY_AUTH_MODE=subject-keys` and grants that subject `llm:invoke` on the routes), `KUTUPHANE_LLMDAP_ROUTE`,
`KUTUPHANE_LLMDAP_ROUTE_CLASS` (`local` or `cloud`; local_only books never go to a cloud route).

Authentication (docs/24 §12.4): the IdP issues every token; Kütüphane stores no client secret and accepts no static
API key.

- A person: an interactive login; the principal is `user:<sub>`.
- A headless client on its own rights (an orchestrator): OAuth client credentials at the IdP (a client secret or
  `private_key_jwt`). The IdP mapper sets `kutuphane/principal_type: agent` and `sub` = the agent name, so the
  principal is `agent:<name>`. Grant it what it needs directly (`kutuphane grant book:<slug> read agent:<name>`).
- A headless client for a person: an RFC 8693 token exchange at the IdP (the person's token from a one-time
  interactive consent, the client-credentials token as the actor token). The token has `sub` = the person and
  `act.sub` = the agent; the agent also needs a live delegation from the person, as for any agent.
- The token's `client_id` (RFC 9068), else `azp`, is recorded as the client. It never changes rights or origin.
  `kutuphane dev-token <sub> --client-id <id>` makes such a development token.

MCP (`/mcp`) is stateless and serves 2025-11-25 clients (with `initialize`) and 2026-07-28 clients (no `initialize`;
the reverse proxy must pass the `Mcp-Method` and `Mcp-Name` headers). `server/discover` advertises the
`io.modelcontextprotocol/oauth-client-credentials` extension. `python3 deploy/mcp_probe.py <ingress URL>` checks both
versions through the proxy (`KUTUPHANE_PROBE_TOKEN`; `--journal <book>` also proposes a note).
MCP tools, in `tools/list` order: `search_library`, `open_citation`, `ask_library`, `reopen_answer`,
`read_document`, `record_runbook_feedback`, `job_status`, `job_result`, `job_cancel`, `propose_note`, `link_notes`,
`verify_citations`, `query_notes`, `neighbours`, `record_outcome`. `query_notes` lists notes (`sets`: `current`,
`open`, `history`; context `repo`/`branch`/`path`/`commit`; `collapse` merges only `same_as` groups) with no model
call; HTTP `GET /v1/notes` and `GET /v1/notes/{book}/{id}/neighbours`.

Hybrid search (optional): `KUTUPHANE_LLMDAP_EMBED_ROUTE` (an LLMDAP `surface: "embeddings"` route, openai schema),
`KUTUPHANE_LLMDAP_EMBED_ROUTE_CLASS`, `KUTUPHANE_EMBED_MODEL` (the route's pinned model, e.g. `bge-m3`). `ingest` and
`approve-import` then embed the new version; `kutuphane index <book>` fills in missing vectors.

- **Only changed passages are embedded (G17).** A vector records the sha256 of the text that was embedded. A new
  version copies the vector of each passage whose embedded text, model and vector width are unchanged in the same
  book and profile; vectors never go from one book to another. The result shows `vectors_added` and `vectors_reused`.
- **The book is live when it is published (G12).** An embedding settings error stops `ingest`/`approve-import`
  before the publication. When indexing fails after the publication, the command still prints the publication
  result, adds `index_error` or `failed` (path, ordinal, error) and `not_attempted`, and exits with code 3;
  `kutuphane index <book>` adds the missing vectors later (it also exits with code 3 while passages are missing).
  A failed embedding call is tried 2 more times (after 5 s and 10 s); a batch that still fails is reported and
  indexing continues. After 3 failed batches in a row the embedder is taken as down and the rest is not attempted.
- **Indexing load (G18).** The local CPU embedder runs one request at a time, so a search waits for the index call
  in front of it. `KUTUPHANE_INDEX_BATCH` (passages per call, default 8), `KUTUPHANE_INDEX_BATCH_CHARS` (embedded
  characters per call, default 8,000; a longer passage goes alone) and `KUTUPHANE_INDEX_CONCURRENCY` (calls in
  flight, default 1, at most 4) set the load; `index --batch/--batch-chars/--concurrency` override them.
  To index at a low priority, publish first and index later with smaller calls:

  ```bash
  env -u KUTUPHANE_LLMDAP_EMBED_ROUTE kutuphane ingest <dir> --book <slug> …   # live now, full text search
  KUTUPHANE_INDEX_BATCH=4 KUTUPHANE_INDEX_BATCH_CHARS=4000 kutuphane index <slug> # later, or at a quiet time
  ```

  Smaller calls make the wait of a search shorter; they do not make indexing faster. Keep the concurrency at 1 on
  the CPU embedder: more calls in flight only wait in the embedder in front of the searches. `nice`/`ionice` on the
  `kutuphane` process do not help, because the embedding work runs in the embedder container.

Reranking (optional): `KUTUPHANE_LLMDAP_RERANK_ROUTE` (an LLMDAP `surface: "rerank"` route), `_RERANK_ROUTE_CLASS`,
`KUTUPHANE_RERANK_MODEL` (e.g. `bge-reranker-v2-m3`); the top 30 hybrid hits are reordered. The reranker reads the
first 1,200 characters of each passage (the target passage size; G26).
`echo "$TOKEN" | kutuphane whoami` verifies a token; `kutuphane explain <correlation-id> --llmdap-export audit.jsonl`
prints the unified audit.

Code repositories of a journal (docs/24 §10): `kutuphane repo add <journal> <slug> <git_dir> --ref 'refs/heads/*'
--by user:admin` registers a bare mirror; `kutuphane repo remove <journal> <slug>` stops its use. Kütüphane never
fetches: keep the mirror current yourself (for example a cron `git fetch`). The mirror must be inside
`KUTUPHANE_REPO_ROOTS` (absolute directories, `:`-separated; compose mounts `KUTUPHANE_REPO_DIR`, default
`./deploy/repos`, read-only at `/srv/repos`), with no symlink in its path, no alternates, no `commondir`, no promisor
pack and only plain `core.*`, `extensions.objectformat` and `remote.*` url/fetch/mirror keys in its `config`. Only
commits that the `--ref` patterns reach can be cited. `verify_citations` (MCP) and `POST /v1/citations/verify`
(`{"book", "citations", "at"}`, `at` = a branch name or a full commit id) report `verified`, `stale` (with
`moved_to`), `missing` or `unverifiable` with a reason, and never return code text. The server needs git ≥ 2.45.

Search and answers (`kutuphane search`, `kutuphane ask`, `GET /v1/search`, `POST /v1/ask`, MCP `search_library`
and `ask_library`):

- **Scope filters (G14)** narrow the evidence before ranking: `--book <slug>` (repeatable), `--path <prefix>`
  (`data/` = the files below `data/`), `--origin <kstd origin>` (repeatable: `human`, `assisted`, `model`, `tool`,
  `unknown`; a book without `kstd.yaml` counts as `unknown`), `--current-only` (the kstd validity includes now).
  HTTP: the query parameters `book`, `path`, `origin` (repeatable) and `current_only=true`; `POST /v1/ask` takes the
  same names in its JSON body. MCP: the same tool arguments. A filter never adds a book: a book that the caller
  cannot read gives the same empty result as a book that does not exist.
- **Answers** are in the language of the question (Turkish or English; G20) and short (about 150 words). Each
  passage goes to the answer model by its first 2,400 characters; the stored sources and the citations keep the
  whole passage (G26). A reference can name one or more passages: `[2]`, `[2,3]`, `[2-4]`, `[2–4]` (G21). Every
  number is checked before a range is expanded; one unknown number or one malformed group (`[1-2-3]`) refuses the
  answer.
- **Background answers (docs/24 §12.2).** `ask_library(…, background: true)` and `POST /v1/ask` with
  `"background": true` (202) return `{job_id, status: "queued"}` at once. Then `job_status` / `GET /v1/jobs/{id}`,
  `job_result` / `GET /v1/jobs/{id}/result` (the stored answer, as `reopen_answer` shows it, with current rights) and
  `job_cancel` / `POST /v1/jobs/{id}/cancel`. An `idempotency_key` (8–128 characters of `A-Z a-z 0-9 . _ : -`) makes a
  retried submission return the same job (200); the same key with another request is refused (409). Only the same
  principal acting for the same user, or that user directly, sees a job; anyone else gets 404. At most 3 open jobs
  per principal (429). The server runs `KUTUPHANE_JOB_WORKERS` workers (default 1; 0 runs none). A job whose worker
  stopped is `failed: interrupted` when its lease ends and never runs again. Finished jobs are deleted after 7 days;
  their answers stay.
- **Two languages (G19).** When the passages found are in Turkish and in English, the answer model translates the
  question (`KUTUPHANE_ANSWER_MODEL` on `KUTUPHANE_LLMDAP_ROUTE`; `ask --model`). Only the question goes to the
  model. A second search runs with the translation, the merged passages are authorized again in one statement (a
  book the caller lost meanwhile drops out), and each passage is reranked against the question in its own
  language. Without a translation, up to 2 passages in the other language from the hybrid top 8 keep a place.
- **Recent things (G22).** A question with "recent", "latest", "son", "en yeni" and similar words ranks the 16 most
  relevant passages by relevance rank + date rank. The date is the kstd `valid_from`, else the first date or ISO week
  in the path (`brief-2026-W40.json`), else the `classified_at` field of a JSONL record. A date elsewhere in the
  text is never used, and a date later than tomorrow is ignored.
- kstd `valid_from`/`valid_to` keep their time: `2026-10-27T23:59:00Z` is not current at noon that day; a date alone
  means 00:00 UTC.
- A question or query is at most 1,000 characters; it is checked before it is embedded. Query vectors are kept in
  memory per process (256 queries, 4 MiB at most), so a repeated query needs no embedding call (G26).
