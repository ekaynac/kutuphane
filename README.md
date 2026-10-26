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

Identity and egress (M1c) are configured by environment:
`KUTUPHANE_OIDC_ISSUER`, `KUTUPHANE_OIDC_AUDIENCE`, `KUTUPHANE_OIDC_JWKS` (path to a JWKS file);
`KUTUPHANE_LLMDAP_URL`, `KUTUPHANE_LLMDAP_KEY` (Core's LLMDAP subject key; LLMDAP runs with
`GATEWAY_AUTH_MODE=subject-keys` and grants that subject `llm:invoke` on the routes), `KUTUPHANE_LLMDAP_ROUTE`,
`KUTUPHANE_LLMDAP_ROUTE_CLASS` (`local` or `cloud`; local_only books never go to a cloud route).
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
`KUTUPHANE_RERANK_MODEL` (e.g. `bge-reranker-v2-m3`); the top 30 hybrid hits are reordered.
`echo "$TOKEN" | kutuphane whoami` verifies a token; `kutuphane explain <correlation-id> --llmdap-export audit.jsonl`
prints the unified audit.
