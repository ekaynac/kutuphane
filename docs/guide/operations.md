# Operations

This guide is for the operator. It shows how to run Kütüphane from the command line (`kutuphane`).
Concepts: [concepts.md](concepts.md). Installation: [install.md](install.md). Problems:
[troubleshooting.md](troubleshooting.md).

Every command prints JSON on stdout. Errors go to stderr.

| Exit code | Meaning |
|---|---|
| `0` | The command succeeded. |
| `1` | `index`: no embeddings route is set. `show`: no such book. `kstd-check`: the check failed or there is no `kstd.yaml`. |
| `2` | An error (bad input, policy error, database error), or `KUTUPHANE_CURATOR_DSN` is not set for a curator command. |
| `3` | `read`, `reopen`, `decisions export`, `journal export`, `note standing`, `note rollback`: access denied. `ingest`, `approve-import`, `index`: the version is live, but its index is incomplete. |
| `4` | `whoami`: the token is not valid. |
| `5` | `receive`: the package is not verified. |

## 1. Environment

### Database connections

`KUTUPHANE_DSN` is the app role `kutuphane_app`, which cannot write Standing. The server and every command use it,
except the curator commands. `KUTUPHANE_CURATOR_DSN` is the owner role, for `migrate` and the curator commands. Keep
it out of every environment that an agent can read; the `core` container gets only `KUTUPHANE_DSN`. Without it,
`migrate` uses `KUTUPHANE_DSN` (one-role development database only), and the curator commands stop with exit code 2:

```
error: KUTUPHANE_CURATOR_DSN is not set (the curator credential)
```

Create the app role once as the owner (`CREATE ROLE kutuphane_app LOGIN PASSWORD '…'`) and put its password in
`.env` as `KUTUPHANE_APP_DB_PASSWORD`. After every `migrate`, apply the grants as the owner. The server does not
start while the schema does not match the code.

```sh
kutuphane migrate
psql "$KUTUPHANE_CURATOR_DSN" -v ON_ERROR_STOP=1 -f deploy/db-roles.sql
```

### Variables

All `KUTUPHANE_*` variables of the code, the compose files (`compose.yaml`, `deploy/compose.full.yaml`) and
`deploy/`. "full" means full stack compose.

| Variable | Default | Effect |
|---|---|---|
| `KUTUPHANE_DSN` | compose: app role at `postgres:5432/kutuphane` | Database connection as the app role. Required. |
| `KUTUPHANE_CURATOR_DSN` | none | Owner connection: `migrate`, `note standing`, `note rollback`, `note expire`, `skill clear`. |
| `KUTUPHANE_EVIDENCE_EXPIRY_DAYS` | `90` | `note expire`: days without use (1–36500). `--days` wins. |
| `KUTUPHANE_DB_PASSWORD` | none (compose stops) | Password of the Postgres owner `kutuphane` in compose. |
| `KUTUPHANE_APP_DB_PASSWORD` | empty | Password of `kutuphane_app` in the compose `KUTUPHANE_DSN`. |
| `KUTUPHANE_PUBLIC_URL` | none | Public URL of the server. Required. |
| `KUTUPHANE_BIND` | `127.0.0.1` | Compose: host address of the ingress port `8080`. |
| `KUTUPHANE_UI_DIR` | none | Web UI files that the server serves. Optional. |
| `KUTUPHANE_OIDC_ISSUER` | none | IdP issuer, exactly as the tokens carry it. Required by the server and `whoami`. |
| `KUTUPHANE_OIDC_AUDIENCE` | `kutuphane` | Expected token audience. |
| `KUTUPHANE_OIDC_JWKS` | compose: `/run/kutuphane/jwks.json` | Path of the JWKS file. Required. |
| `KUTUPHANE_OIDC_JWKS_FILE` | `./deploy/jwks.json` | Compose: the host file mounted as the JWKS. |
| `KUTUPHANE_OIDC_ISSUERS` | none | JSON file of more issuers ([below](#more-than-one-token-issuer)). Set it for the CLI too: `grant … curate` reads it. |
| `KUTUPHANE_LLMDAP_URL` | compose: `http://llmdap:8787` | LLMDAP gateway. Without it: no model call, full-text search only, no answers ([light install](install.md#light-install)). |
| `KUTUPHANE_LLMDAP_KEY` | none | Core's LLMDAP subject key. |
| `KUTUPHANE_LLMDAP_ROUTE` | full: `chat` | Route for answers and question translation. |
| `KUTUPHANE_LLMDAP_ROUTE_CLASS` | compose: `local` | `local` or `cloud`. A `local_only` book never goes to a `cloud` route. |
| `KUTUPHANE_ANSWER_MODEL` | full: `RadixArk/Qwen3.8-27B-NVFP4` | Answer model. Required by the server with `KUTUPHANE_LLMDAP_URL`. `ask --model` sets it for the CLI. |
| `KUTUPHANE_LLMDAP_EMBED_ROUTE` | full: `emb` | Embeddings route. Without it, search is full text only. |
| `KUTUPHANE_LLMDAP_EMBED_ROUTE_CLASS` | compose: `local` | Route class of the embeddings route. |
| `KUTUPHANE_EMBED_MODEL` | full: `BAAI/bge-m3` | Pinned embedding model. |
| `KUTUPHANE_LLMDAP_RERANK_ROUTE` | full: `rerank` | Rerank route; without it, no reranking. Local: `rerank` (CPU) or `rerank-gpu` ([install.md](install.md#gpu-reranker)). |
| `KUTUPHANE_LLMDAP_RERANK_ROUTE_CLASS` | compose: `local` | Route class of the rerank route. |
| `KUTUPHANE_RERANK_MODEL` | full: `BAAI/bge-reranker-v2-m3` | Pinned rerank model. |
| `KUTUPHANE_LLMDAP_ROUTES` | `routes.local.json` | Full compose: LLMDAP routes file in `deploy/llmdap/config/`: `routes.local.json`, `routes.json` (stub models) or `routes.hosted.json`. |
| `KUTUPHANE_LLMDAP_OFFLINE` | `true` | Full compose: `false` gives LLMDAP's network `outbound` a way out, for a hosted decision model ([install.md](install.md#local-models)). Any other value stops compose. |
| `KUTUPHANE_VLLM_IMAGE` | `vllm-node:latest` | Compose profile `gpu-rerank`: local vLLM image of `reranker-gpu`, never pulled. |
| `KUTUPHANE_INDEX_BATCH` | `8` | Passages per embedding call. |
| `KUTUPHANE_INDEX_BATCH_CHARS` | `8000` | Characters per call. A longer passage goes alone. |
| `KUTUPHANE_INDEX_CONCURRENCY` | `1` (at most 4) | Embedding calls in flight. |
| `KUTUPHANE_JOB_WORKERS` | `1` | Background answer workers. `0` runs no jobs. |
| `KUTUPHANE_NOTE_WRITES_PER_DAY` | `500` | Writes (notes, links, outcomes) per principal per day. |
| `KUTUPHANE_NOTE_DUP_SIMILARITY` | `0.90` | Similarity threshold for duplicate note candidates. |
| `KUTUPHANE_REPO_ROOTS` | compose: `/srv/repos` | Absolute directories, `:`-separated, that can hold code mirrors. |
| `KUTUPHANE_REPO_DIR` | `./deploy/repos` | Compose: host directory mounted read-only at `/srv/repos`. |
| `KUTUPHANE_SIGNING_KEY` | none | This installation's Ed25519 package signing key (`export`). |
| `KUTUPHANE_SKILLSPECTOR_BIN` | none | Installed SkillSpector. Without it, skills are not scanned. |
| `KUTUPHANE_SKILLSPECTOR_ALLOW_VERSION` | none | One SkillSpector version allowed in place of the tested one. |
| `KUTUPHANE_SKILLSPECTOR_TIMEOUT` | `120` | Seconds per SkillSpector call. A timeout is a failed scan, which blocks. |
| `KUTUPHANE_SKILLSPECTOR_PROXY` | none | Proxy for SkillSpector. A dead port (`http://127.0.0.1:9`) blocks its OSV.dev requests. |
| `KUTUPHANE_DEV` | none | `1` enables `dev-keys` and `dev-token`. Development machines only. |
| `KUTUPHANE_PROBE_TOKEN` | none | Access token for `deploy/mcp_probe.py`, never printed. |

Curator web settings (`KUTUPHANE_CURATOR_WEB_DSN`, `KUTUPHANE_WEBAUTHN_RP_ID`, `KUTUPHANE_WEBAUTHN_ORIGIN`,
`KUTUPHANE_CURATOR_URL`, `KUTUPHANE_CONFIRM_HOURS`): [install.md](install.md#curator-web).

The host CLI reads no compose file (G13); an empty value is not set. Only `KUTUPHANE_OIDC_AUDIENCE` and
`KUTUPHANE_CONFIRM_HOURS` (`24`) have their compose default in the code. On the host, set the addresses and paths
(`KUTUPHANE_DSN`, `KUTUPHANE_CURATOR_WEB_DSN`, `KUTUPHANE_OIDC_JWKS`, `KUTUPHANE_LLMDAP_URL`, `KUTUPHANE_REPO_ROOTS`),
routes, models and route classes; else the command stops and names the variable. A route class has no default:
`local` skips the egress check, so set it only for an on-premises route. Else the CLI stops before publishing:
`LLMDAP not configured: set KUTUPHANE_LLMDAP_EMBED_ROUTE_CLASS (…: local or cloud …)`.

### More than one token issuer

To trust more issuers (#157), for example an application that signs its own tokens, set `KUTUPHANE_OIDC_ISSUERS` to
a JSON file:

```json
[{"issuer": "<the exact iss of the application's tokens>",
  "audience": "<the aud of its tokens, for example kutuphane>",
  "jwks": "/etc/kutuphane/<application>-jwks.json",
  "principal_prefixes": ["user:<application>.", "agent:<application>-"],
  "curate": false}]
```

| Key | Rule |
|---|---|
| `issuer` | Required. Compared exactly with `iss`. Not the primary issuer; each issuer once. |
| `audience` | Required. The `aud` that its tokens must carry. |
| `jwks` | Required. Path of its JWKS file. |
| `principal_prefixes` | Required, one or more: `user:` or `agent:` and the start of a name (`a-z`, `0-9`, `.`, `_`, `@`, `-`). Its tokens name only principals under these prefixes, and only its tokens may name them. Prefixes of two issuers never overlap. |
| `curate` | Default `false`: `kutuphane grant <book> curate <principal>` refuses a principal under its prefixes. |

A file that breaks a rule stops the server, naming `KUTUPHANE_OIDC_ISSUERS`. Grant as usual
(`kutuphane grant book:<slug> read user:<application>.<name>`). With compose, mount the files into `core`.

### A shared LLMDAP (D76)

One LLMDAP can serve several products, each with its own subject key (D52); Kütüphane's is `svc-kutuphane`.

1. Set `KUTUPHANE_LLMDAP_URL`; Core must reach it. `deploy/compose.full.yaml` always starts its own `llmdap` (profile
   `app`, internal `gateway` network): put the shared gateway on a network that `core` joins.
2. Put the subject key in `KUTUPHANE_LLMDAP_KEY`; its hash goes in the gateway's keys file.
3. Set `KUTUPHANE_LLMDAP_ROUTE`, `KUTUPHANE_LLMDAP_EMBED_ROUTE`, `KUTUPHANE_LLMDAP_RERANK_ROUTE`, with class and
   model. Each route needs `p, svc-kutuphane, llm:invoke, llm/<route>`.
4. `GET /v1/health` makes one real call per route (purpose `health`).

Each call sends `x-llmdap-purpose` (`answer`, `search`, `index`, `translate`, `rerank`, `note`, `decide`, `health`).
The LLMDAP correlation id is `<our id>.<n>`, or `<caller id>.<our id>.<n>`
([http-api.md](http-api.md#15-correlation-id)).

## 2. Ingest a folder into a book

```sh
kutuphane ingest <folder> --book <slug> --sensitivity normal --egress local_only --protection standard
kutuphane show <slug>
```

| Option | Meaning |
|---|---|
| `path` | A folder or a single file. |
| `--book` | The book slug, for example `kvkk`. Required. |
| `--title` | The book title. |
| `--sensitivity` | `normal` or `restricted`. Required. |
| `--egress` | `local_only` or `cloud_ok`. Required. `local_only` text never goes to a `cloud` route. |
| `--protection` | `standard`. Required. |
| `--profile` | Reading profile: `chunked` or `whole`. |
| `--accept-finding` | `PATH@sha256:DIGEST:RULE`: accept one reviewed finding. Repeatable. |
| `--deny-names` | A file of names to find as personal data. |
| `--by` | Who publishes, default `user:<the CLI user>`. |

Each `ingest` publishes a new version. `show` lists the current versions and files. Each publication records
`approved_by` and `channel` (`ingest`, or `import` for `approve-import` with its `--by`) (#160); `show`,
`GET /v1/books`, `list_books`, the file list and `open_citation` show them (for a package also the signing key and
sequence). Publications from before migration 045 show `null`.

### What is searched

Markdown, PDF text layers, `.jsonl` and `.ndjson` (one passage per record), the visible text of `.html`, and as plain
text `.txt`, `.json`, `.yaml`, `.toml`, `.sh`, `.py`, `.js`, `.ts`, `.xml`, `.csv` and `.mdc`. Text must be UTF-8
without NUL bytes; passages record their start `line`. Other files are stored and readable, but not searched.

A file that cannot be extracted (a PDF without text layer, an unreadable or encrypted PDF, a text file that is not
UTF-8) is stored, not indexed. `ingest`, `approve-import` and `show` list it in `quarantined`, and stderr says
`quarantined (stored, not indexed): <path>: <reason>`. A new version that fixes it indexes it.

### What is refused

These refuse the whole book:

- a `kstd.yaml` that cannot be read (a `kstd-check` error; a warning does not refuse, [kstd.md](kstd.md#validation));
- a symlink, a path violation or a size violation;
- markdown that is not UTF-8 or has invalid frontmatter;
- a credential-like file name (`credentials.json`, `*.env`, `id_rsa`, key stores, `settings.local.json`) or text
  (keys, tokens, passwords, private key blocks; not placeholders such as `${PASSWORD}`, `<your-key>`, `changeme`, or
  constants such as `token: refresh_token`);
- in a `cloud_ok` book only: a personal-data finding in a file that can go to a model.

The scan reads the original and the extracted text. The error gives path, line and rule (for example
`assigned-credential`, `api-key`), never the matched text.

To accept a reviewed false positive for exactly that content, take its digest (`sha256sum <folder>/<path>`) and add
`--accept-finding '<path>@sha256:<digest>:<rule>'`. It covers only that rule in that content; a changed file is
refused again, and an acceptance that matches nothing refuses the ingest. The publication lists `accepted_findings`
(result, `show`, stderr). Give `kstd-init` and `kstd-check` the same values. `receive` accepts nothing.

### Personal-data and fleet-data findings

`ingest`, `kstd-init` and `kstd-check` also find personal and fleet data. A finding is a labelling question: it does
not refuse a `local_only` book.

| Rule | Finds | Is not a finding |
|---|---|---|
| `private-ipv4` | 10/8, 172.16/12, 192.168/16, 100.64/10 (for example a tailnet) | a version (`v10.0.0.1`, `version: …`, `==10.1.0.2`), an OID, the block itself (`10.0.0.0/8`), loopback, link-local, the RFC 5737 documentation ranges, public addresses |
| `private-ipv6` | unique local addresses (fc00::/7) | the block itself (`fd00::/8`), loopback, link-local, `2001:db8::/32` |
| `email` | an e-mail address | `example.com`, `*.example`, `*.test`, `*.invalid`, `*.localhost`; no-reply addresses; `git@github.com:org/repo`; `icon@2x.png` |
| `phone` | `+` and 8–15 digits, a `tel:` URI, or a number after `tel`, `phone`, `telefon`, `gsm`, `mobile`, `cep`, `fax` | a time zone (`+0300`), an amount (`+10 000 000`), digits without `+` or a phone word |
| `listed-name` | a name of the `--deny-names` file | a name inside a longer word |

The `--deny-names` file has one name per line (`#` comments), at least 3 characters; case is ignored, and a space
matches any space. Keep it outside the folder: it is personal data itself. Give all three commands the same file.

- Each finding: `personal-data finding (labelling, not refused): <path> line <n> (<rule>)`; then a count line such
  as `personal-data findings: email 1, listed-name 44 (12 files)` or `personal-data findings: none` (stderr for
  `ingest`, stdout for `kstd-init` and `kstd-check`). The matched text is never shown or stored.
- The publication records unaccepted findings in `data_findings` (path, digest, rule, lines). `kstd.yaml` is not
  scanned. `kstd-init` writes `personal_data: unknown` for such files ([kstd.md](kstd.md#personal-data-findings)).
- In a `cloud_ok` book, `ingest` and `approve-import` refuse a file with a finding unless its `ai_use.ai_input` is not
  `y`. Accept the reviewed finding (`--accept-finding '<path>@sha256:<digest>:email'`), set `ai_input: n`, or use
  `--egress local_only`.

### Agent instructions (K3)

Hidden paths stay out (`.git/`, `.env*`, dotfiles), except the agent folders `.claude/` (`agents`, `commands`,
`rules`, `skills`, `hooks`, `CLAUDE.md`), `.cursor/rules/`, `.github/` (`copilot-instructions.md`, `instructions/`,
`prompts/`, `agents/`, `chatmodes/`), `.agents/` and `.codex/`.

Agent instructions are: files in these folders or in a skill folder (next to `SKILL.md`); files whose names start
with `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, `SKILL.md` or `copilot-instructions.md`; `.mdc` rules;
`.instructions.md`, `.prompt.md`, `.agent.md`, `.chatmode.md`; files with a frontmatter type such as `skill`. People
read them with `read`; an agent also needs `activate`. Books from an older reader keep their old index until you
ingest them again (new profile id); migration 011 marks stored passages that the wider K3 rule makes instructions.

### Skill scan (SkillSpector, D71)

With `KUTUPHANE_SKILLSPECTOR_BIN` ([install](install.md#optional-skillspector); offline: `SKILLSPECTOR_TARBALL`,
`SKILLSPECTOR_WHEELS`), ingest, rescan and `receive` scan each skill folder. Without it, each skill is `not_scanned`.
`DO_NOT_INSTALL`, incomplete coverage and a failed scan block agents (the ingest continues); `CAUTION`, `SAFE` and
`not_scanned` do not. A scan is a proposal (origin `tool`), never an approval. Details:
[security.md](security.md#skill-scan-skillspector). `ingest` prints `skill_scans` and names blocked or unscanned
skills on stderr.

```sh
kutuphane skill show <book>                    # scans, findings, blocks and clearances of the current version
KUTUPHANE_CURATOR_DSN=… kutuphane skill clear <book> <skill-folder> --curator user:<name> --reason '…'
kutuphane skill rescan [--book <book>]         # scan again after a SkillSpector update
```

- `skill clear` (curator act) covers only those files and that report; one clear lifts the block and its copies
  (`carried_from`). A later `SAFE` scan never lifts a block.
- An untested version is refused unless `KUTUPHANE_SKILLSPECTOR_ALLOW_VERSION` names it. A new version marks old
  results `stale`; a stale block stays until cleared.
- After an upgrade to migration `022_skill_block_carry.sql`, run `kutuphane skill rescan` once.
- Check an installed SkillSpector: `KUTUPHANE_SKILLSPECTOR_BIN=… pytest tests/test_skillspector_contract.py`.

### kstd manifest

A `kstd.yaml` gives the rights, origin and validity of the files ([kstd.md](kstd.md)). These commands use no database:

```sh
kutuphane kstd-init <folder> --issuer 'ACME <kb@acme.example>' [--source-repo <repo> [--commit <rev>]]
kutuphane kstd-check <folder>
```

`kstd-init` states no `ai_use` term: until you state them, no file is indexed or sent to a model. `--source-repo`
proposes `origin: model` or `unknown` from commit trailers
([kstd.md](kstd.md#origin-proposals-from-a-source-repository)).

### Re-index and note citations

A new profile or content version gives passages new handles. The publication maps each passage that a note cites or
links (`about`, `derived_from`) to the same path in the new version (#140): `exact` (same text); else `overlap` (the
largest share of word pairs, at least half; when the content changed, the passage must hold the whole old text with
operators and case); else `none` (the citation shows `stale`). The result has `passage_map` (`passages`, `added`,
`exact`, `overlap`, `none`); stderr names passages with no successor. Readers add `status` (`current`, `moved` with
`moved_to` and `match`, `stale`) ([agent-memory.md](agent-memory.md#5-follow-links)).

For a book published before migration 040, run once (idempotent; then apply `deploy/db-roles.sql` again):

```sh
kutuphane reindex-map <book> [--dry-run]
```

## 3. Indexing

Set `KUTUPHANE_LLMDAP_EMBED_ROUTE`, `KUTUPHANE_LLMDAP_EMBED_ROUTE_CLASS` and `KUTUPHANE_EMBED_MODEL` for hybrid
search. `ingest` and `approve-import` then embed the new version; `index` adds missing vectors:

```sh
kutuphane index <book> [--batch N] [--batch-chars N] [--concurrency N]
```

Without the route, `index` exits 1: `no embeddings route: set KUTUPHANE_LLMDAP_EMBED_ROUTE`.

- **G17:** a vector whose text, model and width did not change is copied from the same book, never from another book
  (`vectors_reused`; new ones are `vectors_embedded`).
- **G12:** a settings error stops before publication. If indexing fails after it, the result adds `index_error` or
  `failed` and `not_attempted`, and the exit code is 3. Run `index` later.
- A failed call is retried twice (5 s, 10 s). After 3 failed batches in a row, the rest is `not_attempted`.
- **G18:** the CPU embedder serves one request at a time, so searches wait. The options override
  `KUTUPHANE_INDEX_*`. `nice` and `ionice` do not help: the embedder container does the work. For low priority,
  publish first, index later with small calls, concurrency 1:

```sh
env -u KUTUPHANE_LLMDAP_EMBED_ROUTE kutuphane ingest <dir> --book <slug> …   # live now, full text search
KUTUPHANE_INDEX_BATCH=4 KUTUPHANE_INDEX_BATCH_CHARS=4000 kutuphane index <slug> # later
```

### Reranking

Set `KUTUPHANE_LLMDAP_RERANK_ROUTE`, `KUTUPHANE_LLMDAP_RERANK_ROUTE_CLASS` and `KUTUPHANE_RERANK_MODEL`. The
reranker reorders the top 30 hybrid hits on their first 1,200 characters (G26). `rerank-gpu` takes 0.2–0.3 s instead
of 11–25 s on `rerank` (CPU), same top 8.

## 4. Search and ask from the CLI

```sh
kutuphane search <principal> '<query>' [-k K] [--on-behalf-of user:<name>]
kutuphane ask <principal> '<question>' --model <model> [--on-behalf-of user:<name>]
kutuphane reopen <principal> <answer_id>
kutuphane read <principal> <book> <content_id> <path>
```

The principal is `user:<name>` or `agent:<name>`. `search` returns `citation`, `page`, `line`, `score`, `text`,
`item` (kstd rights) and `quoted_records` ([concepts.md](concepts.md#records-that-a-passage-repeats)); `-k` is 1–50,
default 8. `ask` needs the LLMDAP variables and prints the answer and `correlation_id`. `reopen` shows a stored answer
without a model call. `read` writes the file bytes through the authorization gate. Queries are at most 1,000
characters; each process caches 256 query vectors (4 MiB).

### Scope filters (G14)

`search` and `ask` take the same filters, applied before ranking. A filter never adds a book; an unreadable book
gives the same empty result as a missing one.

| Option | Meaning |
|---|---|
| `--book <slug>` | Only this book. Repeatable. |
| `--path <prefix>` | Only paths with this prefix, for example `data/`. |
| `--origin <origin>` | Only this kstd origin: `human`, `assisted`, `model`, `tool`, `unknown` (also a book without `kstd.yaml`). Repeatable. |
| `--current-only` | Only files whose kstd validity includes now. |
| `--platform <name>` | Request context (#137): leave out files whose `applies_to` names other platforms. |
| `--version <version>` | Request context: leave out files whose `applies_to` range does not hold it (for example `7.0.3`). |

A file without `applies_to` matches every request. A file whose bound the context contradicts is left out (it takes
no place in `k`). A bound with no context value keeps the file with `item.scope` `needs_context`; else `item.scope` is
`unbounded` or `match`. `open_citation` and stored answers have no context. Book passages have no rule authority;
journal `rule` notes use the same test (`excluded.needs_context` in `query_notes`).

### One book per scope (#138)

Grants cover a whole book (G10). For roles that see one scope only: put each scope in its own book
(`site-kayseri`, `site-ankara`), shared content in one `shared` book (no copies), and give each role `read` on its
book and `shared`; same for journals. Search with no filter or `--book site-kayseri --book shared`. The pre-filter
reads only readable books, so scope A never gets a scope-B passage, note or link (`tests/test_book_per_scope.py`).

### Answers

- In the language of the question (Turkish or English, G20), about 150 words.
- The model gets the first 2,400 characters of each passage; stored sources keep all (G26).
- References: `[2]`, `[2,3]`, `[2-4]`, `[2–4]` (G21). An unknown number or malformed group (`[1-2-3]`) refuses the
  answer.
- Citations give `line` (`null` for HTML, PDF) and, for JSONL, `record` (from 1, blank lines not counted; `null` for a
  `whole` passage unless the file has one record, G15), also in `reopen` and job results.
- **Two languages (G19):** with Turkish and English passages, the model translates only the question
  (`temperature` 0), a second search runs, the merged passages are authorized again and reranked against the
  question in their language. Without a translation, up to 2 other-language passages of the top 8 keep a place.
- **Recent things (G22):** "recent", "latest", "son", "en yeni" rank the top 16 by relevance and date: kstd
  `valid_from`, else the first date or ISO week in the path (`brief-2026-W40.json`), else JSONL `classified_at`;
  never a date from the text, never after tomorrow. `valid_from` and `valid_to` keep their time; a date alone is 00:00
  UTC.

## 5. Trust, grants and delegations

### Grants

```sh
kutuphane grant book:<slug> <mode> <subject>          # prints the grant id
kutuphane revoke book:<slug> <mode> <subject>         # prints revoked
kutuphane grant role:<name> member user:<name>
kutuphane delegate user:<name> agent:<name> book:<slug> read --hours 8 --purpose '<why>'
kutuphane undelegate <id>
kutuphane keygen <private_key>
kutuphane trust <public_key> --fingerprint <fingerprint> --name <name> --by user:admin
kutuphane untrust <fingerprint>
```

| Mode | Meaning |
|---|---|
| `discover`, `use` | Reserved: grantable, but no code path checks them today. |
| `read` | Read and search the book. |
| `activate` | An agent can use agent instructions (K3) from the book. |
| `propose` | Write notes, links and outcomes in a journal. |
| `curate` | Change the Standing of notes. Users only, never delegated. Needs `KUTUPHANE_CURATOR_DSN`, else exit code 2. |
| `member` | With `role:<name>`: add the subject to the role. |

The subject is `user:<name>`, `agent:<name>` or `role:<name>#member`. An agent that acts for a person needs a live,
time-boxed, one-level delegation (`delegate` prints `id` and `expires_at`); it can carry every mode except `curate`.
Confirm a fingerprint out of band before `trust`.

Development machines only (`dev-keys` writes a mode-600 key and a JWKS for `KUTUPHANE_OIDC_JWKS`; production:
[security.md](security.md)):

```sh
KUTUPHANE_DEV=1 kutuphane dev-keys <directory>
KUTUPHANE_DEV=1 kutuphane dev-token <sub> --private-key <key> --issuer <issuer> [--audience <aud>] [--agent] [--act <agent>] [--client-id <id>]
```

## 6. Journals

A journal is a book of agent notes ([agent-memory.md](agent-memory.md)).

```sh
kutuphane journal create adc-memory --search y --ai-input y \
  --sensitivity normal --egress local_only --protection standard --by user:admin
kutuphane grant book:adc-memory propose agent:adc
KUTUPHANE_CURATOR_DSN=… kutuphane grant book:adc-memory curate user:ayse
```

`--search {y,n}` (full text and vectors) and `--ai-input {y,n}` (text may go to models) are required; `--train {y,n}`
(training export) defaults to `n`; `--title` defaults to the slug; `--sensitivity`, `--egress`, `--protection` and
`--by` (administrator) are required. `journal restrict <book>` tightens with `--no-search`, `--no-ai-input`,
`--no-train`; to loosen, create a new journal. `ingest` and `approve-import` refuse a journal slug.

### Private journals (customer-confidential project memory)

Create the journal with `--sensitivity restricted --egress local_only`. Then:

| Path | What Kütüphane does |
|---|---|
| Package (`export`) | Refused. |
| Decision export, journal export | The journal is refused for journal export. Its notes, and notes in any journal derived from them (`derived_from`, at any depth), are left out (`restricted` in the summary). |
| Training (`--train y`) | Refused at `journal create`. |
| Own model calls | Only `local` routes; a `cloud` route is refused before the call (`not_sent:egress_policy`), also for derived notes. |
| Agents through MCP and HTTP | Only principals with `read` get the text. Kütüphane cannot see where an agent's model runs: grant `read` only to local-model agents, or use `--ai-input n` (`text: null` for model readers). |

### Import a local memory

An orchestrator moves a local memory (for example nöbetçi-mcp in SQLite) into a journal once:

```sh
kutuphane grant book:nobetci-memory propose user:ayse
kutuphane note import nobetci-memory nobetci.jsonl --by user:ayse
```

- Format: [agent-memory.md](agent-memory.md), section 11. At most 10,000 records and 64 MiB; no daily write limit.
- `--by` needs `propose` on the journal and `read` on each cited book. A `user:` importer gives origin `unknown`, an
  `agent:` importer `model`. Each record becomes a `pending` note.
- The file is validated first (a wrong line writes nothing; the message names up to 5 lines), then written in one
  transaction. Imported ids are `unchanged` on a repeat.
- With an embeddings route, new notes get vectors after the commit (egress checked).
- No MCP tool or HTTP route imports; agents use `propose_note`.
- Report: `created`, `existing` (same bytes already a note), `unchanged`, `links`, one item per record. Exit 3: no
  right or not a journal; 2: file refused.

### Export a journal

```sh
kutuphane journal export adc-memory --out adc-memory.jsonl --by user:ayse
```

- The `note import` shape plus the Standing history, writers, outcomes and `ai_use`. `--out` must be a new file
  (mode 600).
- `--by` needs `read` on the journal and each cited book; the export is an `access_event` (`export_journal`) in the
  rollback report.
- A `restricted` journal is refused (exit 2). Notes derived from a private journal or a `license: unknown` file are
  left out (`restricted`, `licence_unknown`). A note on a blocked skill has `text` and `decision` `null` with
  `withheld` (counted), and `note import` refuses it.
- The file holds all text, also with `--train n` or `--ai-input n` (these limit models, not backups): keep it safe.
- Importing it into the same slug gives the same ids and links, each `pending`, with the latest Standing as a claim.
  Import never widens rights: journal AND sources AND the record's `ai_use`.

## 7. Curation

A note starts `pending`. Only a curator with `curate` (and `read` on the phone) changes its Standing, on the CLI with
`KUTUPHANE_CURATOR_DSN` or on the phone. Boundary: [security.md](security.md#curation-boundary).

```sh
KUTUPHANE_CURATOR_DSN=… kutuphane note standing adc-memory@nt_<64 hex> approved --curator user:ayse --reason '…'
KUTUPHANE_CURATOR_DSN=… kutuphane note rollback adc-memory@nt_<64 hex> --curator user:ayse --reason '…'
```

Allowed changes: `pending` → `approved` or `rejected`; `approved` → `retired`; `rejected` or `retired` → `pending`.

`note rollback` (a poisoned note), in one transaction: a root that was ever approved becomes `retired`, a pending
root `rejected`, and derived `approved` or `pending` notes `retired`. Use its report to tell the users and agents:

| Field | Content |
|---|---|
| `root`, `event_seq` | The note and its Standing event. |
| `notes` | Each note: `ref`, `was`, `standing`, `event_seq`, `writers` (`principal`, `on_behalf_of`, `client_id`). |
| `deliveries` | Reads that held the notes: `at`, `action`, `principal`, `on_behalf_of`, `correlation_id`, `memory_seq`, `items`. |
| `answers` | Answers that used them: `id`, `at`, `principal`, `on_behalf_of`, `refs`. |
| `exports` | Exports that held them, as `deliveries`. |

### Expiry of unused evidence (R1)

```sh
KUTUPHANE_CURATOR_DSN=… kutuphane note expire --dry-run   # list only
KUTUPHANE_CURATOR_DSN=… kutuphane note expire             # days: --days, else KUTUPHANE_EVIDENCE_EXPIRY_DAYS, else 90
```

A note's clock is the last of its write, Standing event and `passed` outcome (not other outcomes, not "my words").
An `evidence` note (`finding`, `lesson`, `dead_end`, `test_result`) with an older clock gets a system event (reason
`expired`, `set_by` `system`, one `correlation_id` per run): `pending` → `rejected` (or `retired` if ever approved),
`approved` → `retired`. `rule` notes (`convention`, `decision_proposal`) never expire. A rerun moves nothing;
`note standing … pending` reopens and restarts the clock. Output: `days`, `cutoff`, `dry_run`, `notes` (`ref`, `was`,
`standing`, `event_seq`, `null` in a dry run).

Run it daily from a systemd user timer; keep the env file away from agents:

```ini
# ~/.config/kutuphane/expire.env (mode 600)
KUTUPHANE_CURATOR_DSN=postgresql://kutuphane:<password>@127.0.0.1:55432/kutuphane
PYTHONPATH=<deploy dir>/src

# ~/.config/systemd/user/kutuphane-expire.service
[Service]
Type=oneshot
WorkingDirectory=<deploy dir>
EnvironmentFile=%h/.config/kutuphane/expire.env
ExecStart=<venv>/bin/python -m kutuphane.cli note expire
UMask=0077

# ~/.config/systemd/user/kutuphane-expire.timer
[Timer]
OnCalendar=daily
Persistent=true
[Install]
WantedBy=timers.target
```

Then `systemctl --user daemon-reload && systemctl --user enable --now kutuphane-expire.timer`; logs:
`journalctl --user -u kutuphane-expire`.

### The queue (#77)

The phone and the CLI show the same risk-ordered queue:

```sh
KUTUPHANE_CURATOR_DSN=… kutuphane curator queue --curator user:ayse [--book adc-memory] [--as-of W] [--cursor C]
```

- Books where the curator holds `curate` and `read` directly, now; `curate` without `read` is in `read_needed`
  ("grant read to curate this book").
- One `same_as` cluster is one group (all members, with Standing); `contradicts` members are in `pairs`. Groups by
  tier, then oldest pending note; members by seq.
- Tiers: 1 a rule whose approval retires an approved rule of the same scope (`supersedes`), or a `contradicts` link
  to an approved note; 2 `decision_proposal`; 3 `convention`; 4 `finding`; 5 `lesson`, `dead_end`; 6 `test_result`.
- The same `watermark` and rights give the same bytes; `next_cursor` pages at that watermark (20 groups; `--limit`).
- Each note shows every part its id covers, "why here", writers, origin, outcomes, recurrence and "proposed again
  after rejection". A readable passage citation has `path`, a 240-character `excerpt` (full text in `/api/note`) and
  a re-index `status`; a link has the full `text`. An unreadable part shows "a passage (note) in a book you cannot
  read" and counts in `hidden_parts`; such a note cannot be approved on the phone.
- Each page is an `access_event` (`curate_view`) for the rollback report.

### On the phone (curator web, D72)

After [install](install.md#curator-web), enroll each curator:

```sh
KUTUPHANE_CURATOR_DSN=… kutuphane curator enroll user:ayse
```

It prints a one-time URL (15 minutes, one passkey); send it privately. Ayşe opens it with Tailscale on, taps
**Create passkey**, then **Sign in with passkey**. Tabs: **To review** (the queue) and **My words**.

<img src="img/curator-queue.png" alt="The To review tab on a phone: a finding with its evidence and a warning" width="300">

A card has eight parts: 1. the text (hidden characters as marks such as `⟦U+202E⟧`); 2. the kind, who proposed it
for whom, the date, where it applies and the commit; 3. **Evidence** (**Show passage** opens it); 4. **Options**
with the **Proposed choice**; 5. **Replaces** and **Linked**; 6. a warning line; 7. **Approve**, **Reject**,
**Skip** (no **Approve** with an unreadable part); 8. **Details** (closed): id, kind, scope, class key, commit,
writers, origin, outcomes, "why here". A group card says "3 notes say the same thing" and adds **Approve all** (not
for contradicting members or more than one rule) and **Reject all**; each member keeps its own buttons.

<img src="img/curator-decision.png" alt="A decision proposal with its proposed choice marked" width="300">

The bottom bar counts the choices ("2 approve · 1 reject") and shows **Sign 3 decisions**. It asks **Why?**:
**Correct and useful**, **Wrong**, **Duplicate**, **Not useful now**, or her own words; **Not sure — skip** clears
the choices and signs nothing. **Continue** shows the stored statement and the rules it retires; **Sign with fingerprint**
decides all chosen notes (one reason, one Standing event each). One act: 1–50 notes, at most one rule-role note
approved, never two `contradicts` notes together. Synced passkeys are allowed and recorded.

<img src="img/curator-sign.png" alt="The sign sheet with the rule that the approval retires" width="300">

```sh
KUTUPHANE_CURATOR_DSN=… kutuphane curator passkeys [user:ayse]     # synced or not, last act; check after each enrollment
KUTUPHANE_CURATOR_DSN=… kutuphane curator revoke-passkey <id>      # a lost phone; also ends its sessions
KUTUPHANE_CURATOR_DSN=… kutuphane curator end-sessions user:ayse    # a stolen cookie
KUTUPHANE_CURATOR_DSN=… kutuphane curator cancel-enrollment <en_…>  # a leaked unused code; a used one: revoke its passkey
KUTUPHANE_CURATOR_DSN=… KUTUPHANE_WEBAUTHN_RP_ID=… KUTUPHANE_WEBAUTHN_ORIGIN=… kutuphane curator verify-acts
```

`verify-acts` checks every stored act offline (challenge, signature with user verification, rows and `retires`
against the statement, and that signed notes still give their id, else `contents`); it exits 1 on a failure. A
note's citations and creation links are part of its id (migration 039): an approval or confirmation counts only while
they match, else the note shows `pending` and the write-path origin. Design:
[security.md](security.md#curator-web-and-passkeys-d72).

### "My words": confirm the origin of a note (D70 R3, R7)

> **Frozen (D78).** "My words" works as described below, but it gets no new work.

The server never stores `human` from a token. A note proposed as `human` or `assisted` gets the write-path origin
with `origin-claim-refused`, and the receipt gets `<KUTUPHANE_CURATOR_URL>/c/<book>/<nt_id>` (also from the MCP tool
`confirm_origin`; no secret, no right). In curator web (or **My words**, `/requests`), the person reads the full text
first, then who typed it (writer and client) and the fields, and signs one choice with **Sign with fingerprint**:

| Choice | Origin | Who may choose it |
|---|---|---|
| "These are my words, verbatim (I wrote or dictated them)." | `human` | only the person the words were entered for: the user that the agent acted for, or the user who wrote (a database key) |
| "A model wrote or reworded this. I reviewed it in substance." | `assisted` | that person, or a curator of the book |

- `read` on the book is needed; otherwise every note gives the same refusal. Nothing is stored before the signature;
  leaving the page stores nothing.
- A request is open `KUTUPHANE_CONFIRM_HOURS` (24) hours; a confirmation does not expire. It never moves to another
  note, also not a successor.
- Readers see the shown origin, with `entered_by` and `confirmed_by` while live; the `origin` filter uses it;
  `write_record.origin` never changes; no Standing or right changes.
- Only the confirmer can withdraw (**Withdraw my confirmation**, R7); no older confirmation comes back, and `as_of`
  queries before it still show it. While live, nobody else can confirm.

### Measures

```sh
KUTUPHANE_CURATOR_DSN=… kutuphane curator report --from 2026-10-01 --to 2026-11-01
```

Read only; `--from` included, `--to` not; UTC.

| Key | Content |
|---|---|
| `curator_time` | `seconds_per_approved_note`: visible time of approving phone acts (first card display to **Continue**, at most 1 hour) ÷ notes approved; also medians per act and per decided note, acts with no time, synced-passkey acts. |
| `pending_after_7_days` | Share of notes written from `--from` to 7 days before `--to` with no Standing event after 7 days, by current tier and book. |
| `decided_by` | Standing events: `people_web`, `people_cli`, `system`, by value. |

## 8. Outcomes and decision export

Agents record outcomes with `record_outcome` (MCP) or `POST /v1/outcomes`; there is no CLI command. A `passed`
outcome restarts the expiry clock; no outcome changes Standing.

```sh
kutuphane decisions export <principal> --out decisions.jsonl [--book <journal>] [--on-behalf-of user:<name>]
```

- `--out` must be new (mode 600). Without `--book`: every readable journal.
- Text, options and choice only with `ai_input` and `train` (`journal create --train y`) and no blocked skill; else
  references, hashes and `withheld`.
- `context.passages` gives each handle `{"status": "current"}`, `{"status": "stale"}` or
  `{"status": "moved", "moved_to": …, "match": "exact"|"overlap"}` (#140).
- Left out: notes with a `restricted` source (`restricted`), and notes derived from a `license: unknown` file
  (#143; `licence_unknown`). Set `rights.license` in its `kstd.yaml` and publish again to export them.

## 9. Code repositories

A journal can cite code in a bare Git mirror. Kütüphane never fetches.

```sh
kutuphane repo add <journal> <slug> /srv/repos/<name>.git --ref 'refs/heads/*' --by user:admin
kutuphane repo remove <journal> <slug>
```

The absolute path has no symlink and is inside `KUTUPHANE_REPO_ROOTS` (compose mounts `KUTUPHANE_REPO_DIR` read-only
at `/srv/repos`). `--ref` (up to 10) limits which commits can be cited. The mirror has no alternates, `commondir` or
promisor pack, and its `config` only plain `core.*`, `extensions.objectformat` and `remote.*` url/fetch/mirror keys.
`repo remove` stops new scopes and citations; old ones verify as `unverifiable`. The server needs git 2.45+. Fetch
yourself, for example `*/15 * * * * git --git-dir=/srv/kutuphane/repos/app.git fetch --prune --quiet` in cron.

## 10. Packages

A package is a signed copy of a book's current version ([kstd.md](kstd.md)).

```sh
KUTUPHANE_SIGNING_KEY=/path/key.pem kutuphane export <book> --out <book>.pkg [--legal-basis 'eu-gdpr:A6-1-b']
kutuphane receive <book>.pkg
kutuphane imports
kutuphane approve-import <id> --by user:admin --sensitivity normal --egress local_only --protection standard
kutuphane reject-import <id> --by user:admin --reason '…'
```

- `export` needs `--legal-basis` when files are personal data `yes` or `unknown`. It refuses a journal, a
  `restricted` book, and a book with `license: unknown` files (#143, named; set a license such as
  `LicenseRef-InfraMedic-Internal` and publish again).
- `receive` verifies and quarantines; exit 5 if not `verified`. It adds `personal_data` and, with
  `KUTUPHANE_SKILLSPECTOR_BIN`, `skill_scan` findings.
- `imports` lists the last 50 with verdicts and diff (`added`, `removed`, `changed`), and `submitted_by`,
  `submitted_for`, `submitted_channel` for HTTP and MCP.
- `approve-import` publishes with this policy and indexes like `ingest` (exit 3 if incomplete). With
  `--egress cloud_ok` it refuses unaccepted findings as `ingest` does (`--accept-finding`; approve again).
  `reject-import` keeps the record.

### Packages from an application (HTTP and MCP, #139)

An application sends a package with `POST /v1/packages` ([http-api.md](http-api.md#12-packages)) or `submit_package`
([mcp.md](mcp.md#516-submit_package)). Checks are those of `receive`; a person still runs `approve-import`.

1. `trust` the application's signing key once.
2. Grant `propose` on the target book: `kutuphane grant book:<book> propose agent:<client>`. Without it: `403`,
   nothing stored. A journal target: `400`.
3. The signing key is the issuer (D74); origins come from the signed `kstd.yaml`; the caller is only recorded
   (`submitted_by`, D70).

```sh
curl -s -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/x-tar" \
  --data-binary @runbooks.pkg "$KUTUPHANE_PUBLIC_URL/v1/packages"
```

The response has the import `id` and `status` (`received`, `findings`, or `refused` with `reasons`);
`GET /v1/packages/<id>` repeats it (`approved` later). Run state (saga outcomes, task results) is not a book: use
`record_outcome` or a journal.

## 11. Audit and logs

```sh
echo "$TOKEN" | kutuphane whoami
kutuphane explain <correlation_id> --llmdap-export audit.jsonl
kutuphane explain <answer_id> --answer --llmdap-export audit.jsonl
```

`whoami` reads the token from stdin and prints `principal` and `on_behalf_of`. `explain` prints `access`,
`model_calls` and `complete` for our id or a caller's id (#156); rows have `correlation_id` and
`caller_correlation_id`. `--llmdap-export` takes `llmdap-audit-export` JSONL; `complete` is `false` when a call has no
LLMDAP record. The database keeps `access_event`, `model_call`, `answer`, `standing_event`; LLMDAP's signed chain is
in the `llmdap-audit` volume. Logs (full stack, [install.md](install.md#full-stack)):
`docker compose --profile app logs -f core` and `docker compose --profile app logs llmdap ingress`.

### Degraded searches and failed model calls (#136)

A failed model stage degrades the search; `retrieval` (`embedding`, `translation`, `rerank`: `ok`, `failed`,
`skipped`; [http-api.md](http-api.md#51-get-v1search)) and `answer.retrieval` say so. `GET /v1/health`
([http-api.md](http-api.md#33-get-v1health)) checks dependencies now. Failed calls and degraded answers, last 24 hours
(an HTTP 200 with an invalid answer is a failed stage, not a failed call):

```sql
SELECT route, model, count(*) AS failed FROM model_call
WHERE at > now() - interval '24 hours'
  AND (error IS NOT NULL OR http_status IS NULL OR http_status >= 400)
GROUP BY route, model ORDER BY failed DESC;

SELECT key AS stage, count(*) AS failed FROM answer, jsonb_each_text(retrieval)
WHERE created_at > now() - interval '24 hours' AND value = 'failed' GROUP BY key;
```

## 12. Backups

There is no backup command. Back up Postgres, the `llmdap-audit` volume, the signing key, the JWKS and the mirrors.
Disk encryption is a deployment duty (D48).

```sh
docker compose exec -T postgres pg_dump -U kutuphane kutuphane > backup.sql
docker compose exec -T postgres psql -U kutuphane -c 'CREATE DATABASE kutuphane_restore'
docker compose exec -T postgres psql -U kutuphane -d kutuphane_restore -v ON_ERROR_STOP=1 < backup.sql
```

Then point `KUTUPHANE_DSN` at it, or rename the databases while the app is stopped.

## 13. CLI reference

| Section | Commands |
|---|---|
| [1](#1-environment) | `migrate` |
| [2](#2-ingest-a-folder-into-a-book) | `ingest`, `show`, `reindex-map`, `kstd-init`, `kstd-check`, `skill show`, `skill rescan`, `skill clear` |
| [3](#3-indexing) | `index` |
| [4](#4-search-and-ask-from-the-cli) | `search`, `ask`, `reopen`, `read` |
| [5](#5-trust-grants-and-delegations) | `grant`, `revoke`, `delegate`, `undelegate`, `keygen`, `trust`, `untrust`, `dev-keys`, `dev-token` |
| [6](#6-journals) | `journal create`, `journal restrict`, `journal export`, `note import` |
| [7](#7-curation) | `note standing`, `note rollback`, `note expire`, `curator enroll`, `curator passkeys`, `curator revoke-passkey`, `curator end-sessions`, `curator cancel-enrollment`, `curator verify-acts`, `curator queue`, `curator report`, `curator web` ([install](install.md#curator-web)) |
| [8](#8-outcomes-and-decision-export) | `decisions export` |
| [9](#9-code-repositories) | `repo add`, `repo remove` |
| [10](#10-packages) | `export`, `receive`, `imports`, `approve-import`, `reject-import` |
| [11](#11-audit-and-logs) | `whoami`, `explain` |
