# Kütüphane

> Kütüphane is the governed catalog that people, agents and applications read from the same copy. Every item, a
> document or an agent's note, carries who wrote it (from the write path, never from a claim), who accepted it,
> where it applies and what a model may do with it. Agent memory products remember; Kütüphane keeps a record that
> can be checked, rolled back and exported.

Kütüphane is a governed knowledge catalog and a memory layer for agents. People, agents and applications read the
same copy of each book, note, rule and skill. Agents use MCP; applications use MCP or HTTP. It runs on-prem and
air-gapped. The vision is in `docs/23-vision-v1.md` (version 1.2).

## Five principles

1. **The write path is the provenance.** No label from a model, a header or a manifest outranks it.
2. **Rules are accepted; evidence is verified.** Only a person makes a rule current; evidence that nobody uses expires.
3. **Memory is data, never instruction.** Notes reach a model as tool results; instructions need `activate` and a scan.
4. **Nothing is rewritten; everything can be withdrawn.** Notes are immutable; rollback is an event with a cause.
5. **An asset leaves with its rights.** Export and import carry origin, Standing, rights and derivation.

## Who it is for

- **Coding orchestrators** (ADC, nöbetçi-mcp): shared agent memory for decisions, findings, lessons and conventions.
- **Applications** (for example InfraMedic, RAG platforms): a catalog contract (`list_books`, `list_files`) and
  signed packages (`submit_package`), with the rights of each item attached.
- **Curators:** people who accept or reject what agents propose, on the phone with a passkey (curator web) or on
  the CLI.

## What it is not

- Not a RAG platform or a chat UI: Onyx, Dify, Open WebUI and RAGFlow do that, and they connect to Kütüphane.
- Not a code graph: it only cites into code.
- Not a run-state store, and not a place for chat transcripts or scratch notes.
- Not an identity provider: tokens come from the IdP; grants live here.
- Not an extraction pipeline: it never writes a note from a conversation. An agent proposes; a person decides.

## Quick start (development)

You need Docker with Compose v2 and Python 3.11 or later. Postgres runs in Docker, the server on the host, with
development tokens and no model service.

```sh
# 1. Install, start Postgres, apply the migrations
python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'
printf 'KUTUPHANE_DB_PASSWORD=%s\n' "$(python3 -c 'import secrets;print(secrets.token_urlsafe(24))')" > .env
docker compose up -d --wait postgres
set -a; . ./.env; set +a
export KUTUPHANE_DSN="postgresql://kutuphane:${KUTUPHANE_DB_PASSWORD}@127.0.0.1:55432/kutuphane"
export PATH="$PWD/.venv/bin:$PATH"
kutuphane migrate

# 2. A book, a journal and the rights
kutuphane ingest tests/fixtures/okf-kitap --book ornek \
  --sensitivity normal --egress local_only --protection standard
kutuphane journal create team-memory --search y --ai-input y \
  --sensitivity normal --egress local_only --protection standard --by user:admin
for g in "book:ornek read" "book:team-memory read" "book:team-memory propose"; do kutuphane grant $g agent:adc; done
KUTUPHANE_CURATOR_DSN="$KUTUPHANE_DSN" kutuphane grant book:team-memory curate user:ayse
kutuphane search agent:adc "politika"

# 3. A development token and the server (KUTUPHANE_DEV=1 only on a development machine)
export KUTUPHANE_DEV=1
kutuphane dev-keys deploy/dev
export TOKEN="$(kutuphane dev-token adc --agent --client-id adc \
  --private-key deploy/dev/dev-private.pem --issuer http://127.0.0.1:8090/dev)"
KUTUPHANE_PUBLIC_URL=http://127.0.0.1:8090 KUTUPHANE_OIDC_ISSUER=http://127.0.0.1:8090/dev \
KUTUPHANE_OIDC_AUDIENCE=kutuphane KUTUPHANE_OIDC_JWKS=deploy/dev/jwks.json \
  uvicorn --factory kutuphane.server:app_from_env --host 127.0.0.1 --port 8090 &

# 4. Connect an MCP client, write a note, accept it
claude mcp add --transport http kutuphane http://127.0.0.1:8090/mcp --header "Authorization: Bearer $TOKEN"
curl -s -X POST http://127.0.0.1:8090/v1/notes -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"book":"team-memory","kind":"lesson","text":"Run migrate first.","idempotency_key":"quickstart-0001"}'
KUTUPHANE_CURATOR_DSN="$KUTUPHANE_DSN" kutuphane note standing 'team-memory@nt_<id from the receipt>' approved \
  --curator user:ayse --reason "checked"
curl -s -H "Authorization: Bearer $TOKEN" 'http://127.0.0.1:8090/v1/notes?book=team-memory'
```

Any MCP client that speaks streamable HTTP with a bearer token works. Without a model service, search is full text
only, and `tools/list` has no `ask_library` and no job tools. The light install is `compose.yaml`; the full stack
(ingress, LLMDAP, local models, two database roles) is `deploy/compose.full.yaml` (`docs/guide/install.md`).

## MCP tools

The endpoint is `/mcp` (stateless; MCP 2025-11-25 and 2026-07-28). Each tool description names the grant that it
needs. Reference: `docs/guide/mcp.md`.

| Tool | What it does |
|---|---|
| `search_library` | Search the books that you may read now; `max_chars` gives short snippets. |
| `open_citation` | Open a passage handle or a note reference at its exact version. |
| `ask_library` | Answer with `[n]` citations, or `not_in_library` (LLMDAP only). |
| `reopen_answer` | Show a stored answer and its evidence again, with no model call. |
| `read_document` | Read one text document of one version (instructions need `activate`). |
| `list_books` | List the books and journals that you may read, with their latest publication. |
| `list_files` | List the files of a book's current version, with kstd item information. |
| `job_status`, `job_result`, `job_cancel` | Follow, read or cancel a background `ask_library` job (LLMDAP only). |
| `propose_note` | Write a note into a journal; it starts `pending`. |
| `link_notes` | Link a note to a note or a passage (`same_as`, `contradicts`, `about`, …). |
| `verify_citations` | Check code citations against a branch or a commit. |
| `query_notes` | Read notes with filters: fast, deterministic, no model call. |
| `neighbours` | Show the notes linked to a note or a passage (depth 1 or 2). |
| `record_outcome` | Record `passed`, `failed`, `reverted` or `reopened` for one exact item. |
| `confirm_origin` | Show the state and the URL of the "my words" confirmation of a note. |
| `submit_package` | Submit a signed package; a person approves it on the CLI. |
| `package_status` | Show the status of your package. |

MCP Skills (`skills/list`, `skills/get`, `skill://` resources) give the skills that you may `activate`. Every tool
also has an HTTP route under `/v1/` (for example `GET /v1/search`, `POST /v1/notes`); the web UI is at `/ui/`.
Reference: `docs/guide/http-api.md`.

## Security model

- Origin comes from the write path, never from the writer's claim. An agent cannot write as a person.
- Rights, `ai_input` and egress are checked before every embedding, rerank and answer, and again at delivery.
- Only a person changes Standing: with a separate database credential on the CLI, or with a passkey act on the phone.
- Skills can get a SkillSpector scan at ingest; a bad or failed scan blocks the skill until a curator clears it.
- All model calls go through LLMDAP; a `local_only` book never reaches a cloud route.
- Every read decision and every model call is audited. Details: `docs/guide/security.md`.

## Documentation

| Read | For |
|---|---|
| `docs/guide/index.md` | The map and the reading order. |
| `docs/guide/concepts.md` | Books, versions, journals, notes, Standing, origin, rights, grants. |
| `docs/guide/install.md` | Development, light install, full stack, local models, upgrades. |
| `docs/guide/operations.md` | The CLI and the settings. |
| `docs/guide/mcp.md`, `docs/guide/http-api.md` | The interfaces. |
| `docs/guide/agent-memory.md` | A how-to for orchestrators. |
| `docs/guide/security.md`, `docs/guide/kstd.md` | The security model and the kstd manifest. |
| `docs/guide/troubleshooting.md`, `docs/guide/changelog.md` | Errors and changes. |
| `docs/23-vision-v1.md` | The vision (1.2): positioning, principles, users, roadmap. |
| `docs/11-standard-draft.md` | The kstd specification. |
| `docs/01-direction-decisions.md` | The decisions (D1 and later). |

## Status

Version 0.1.0, under active development; interfaces can change.

- **Built:** file books with kstd L0; hybrid search; answers with citations; signed packages over the CLI, HTTP and
  MCP; the catalog contract (`list_books`, `list_files`); agent memory (notes, fast reads, code citations, scope,
  rollback, outcomes, evidence expiry, journal export and import); MCP 2026-07-28 with several token issuers; MCP
  Skills with the SkillSpector scan; a light install without LLMDAP; curator web with passkey acts and the "my
  words" confirmation.
- **Open:** item-level access (#138, G10); the live reboot test (#141); the T3 A/B gate for new memory work (#121);
  the InfraMedic token issuer.
- **Removed:** delegated curate and the decider (D73, removed by D80); the `laya` decision-model service.

Changes: `docs/guide/changelog.md`.

## Licence

The code is licensed under Apache-2.0 (`LICENSE`). The kstd specification text in `docs/` and `kstd/` is licensed
under CC-BY-4.0 (`NOTICE`). Contributions: `CONTRIBUTING.md`.
