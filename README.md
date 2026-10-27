# Kütüphane

**Kütüphane is the place where people and AI agents keep what they know, with a record of who wrote it, who
accepted it, and who may use it for what.** It is a governed knowledge catalog and an agent memory layer. Agents
reach it through MCP; RAG platforms and orchestrators use it as their governed source. It runs on-prem and
air-gapped. It is not a RAG platform, a chat UI, a code graph or a run-state store (`docs/23-vision-v1.md`).

Five promises (each one is a behavior that you can check):

| # | Promise |
|---|---|
| P1 | **Knowledge with an owner.** Each item shows who issued it, who accepted it, and whether it is current. |
| P2 | **An agent can never pass as a person.** Origin comes from the write path, not from the writer's claim. |
| P3 | **A model never sees what it may not see.** Rights and personal data are checked before every embedding, rerank and answer. |
| P4 | **Memory that does not rot.** Duplicates are found, contradictions kept, stale code citations flagged, poisoned notes rolled back with everything derived from them. |
| P5 | **Cheap and fast for agent loops.** Deterministic, filtered reads with no model call; a model answer only on request. |

## Who it is for

- **Coding orchestrators** (ADC, nöbetçi-mcp): shared memory for decisions, findings, lessons and conventions.
- **Organizations with a RAG platform:** a governed source that gives only the passages that the caller and the
  model may use, with their rights attached.
- **Curators:** people who accept or reject what agents propose.

## Quick start (development)

You need Docker with Compose v2 and Python 3.11 or later. These commands run Postgres in Docker and the server on
the host, with development tokens and no model service.

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
kutuphane grant book:ornek read agent:adc
kutuphane grant book:team-memory read agent:adc
kutuphane grant book:team-memory propose agent:adc
kutuphane grant book:team-memory curate user:ayse
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
KUTUPHANE_PROBE_TOKEN="$TOKEN" python3 deploy/mcp_probe.py http://127.0.0.1:8090 --journal team-memory
claude mcp add --transport http kutuphane http://127.0.0.1:8090/mcp --header "Authorization: Bearer $TOKEN"
curl -s -X POST http://127.0.0.1:8090/v1/notes -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"book":"team-memory","kind":"lesson","text":"Run migrate first.","idempotency_key":"quickstart-0001"}'
KUTUPHANE_CURATOR_DSN="$KUTUPHANE_DSN" kutuphane note standing 'team-memory@nt_<id from the receipt>' approved \
  --curator user:ayse --reason "checked"
curl -s -H "Authorization: Bearer $TOKEN" 'http://127.0.0.1:8090/v1/notes?book=team-memory'
```

Any MCP client that speaks streamable HTTP with a bearer token works; `claude mcp add` is one example. Without a
model service, search is full text only and `ask_library` is not available. To run the same in containers with no
LLMDAP and only open source parts, use the light install (`deploy/compose.light.yaml`). For the full stack (ingress,
LLMDAP, local models, two database roles) read `docs/guide/install.md`.

## MCP tools

The endpoint is `/mcp`. It is stateless and serves MCP 2025-11-25 and 2026-07-28 clients. Reference:
`docs/guide/mcp.md`.

| Tool | What it does |
|---|---|
| `search_library` | search the books that you may read now (full text, plus vectors and rerank when configured) |
| `open_citation` | open a passage handle or a note reference at its exact version |
| `ask_library` | answer with `[n]` citations, or `not_in_library`; can run as a background job |
| `reopen_answer` | show a stored answer and its evidence again, with no model call |
| `read_document` | read one text document of one version (agent instructions need `activate`) |
| `record_runbook_feedback` | record `worked`, `failed` or `changed` for one runbook version |
| `job_status`, `job_result`, `job_cancel` | follow, read or cancel a background `ask_library` job |
| `propose_note` | write a note into a journal; it starts `pending` |
| `link_notes` | link a note to a note or passage (`same_as`, `contradicts`, `about`, `fixed_by`, …) |
| `verify_citations` | check code citations against a branch or commit |
| `query_notes` | fast, deterministic, filtered note reads with no model call |
| `neighbours` | the notes linked to a note or passage (depth 1 or 2) |
| `record_outcome` | record `passed`, `failed`, `reverted` or `reopened` for a task on one exact item |
| `skills/list`, `skills/get`, `resources/read` of `skill://` | MCP Skills (SEP-2640): the skill folders that you may `activate`, with a SHA-256 for each file; the files only on demand |

`search_library`, `open_citation`, `read_document` and `query_notes` give the Sensitivity and Egress of their
content in `_meta["kutuphane/handling"]`.

## HTTP API

Every MCP tool has an HTTP route under `/v1/` (for example `GET /v1/search`, `POST /v1/notes`, `GET /v1/notes`).
The web UI is at `/ui/`. Reference: `docs/guide/http-api.md`.

## Security model

- The IdP issues every token; the issuer is compared exactly; there are no static API keys.
- One gate decides every read before the work and again at delivery; every decision is audited.
- `ai_input: n` text never reaches a model; a `local_only` book never reaches a cloud route; all model calls go through LLMDAP.
- Origin comes from the write path; only a curator changes Standing: with a separate database credential on the CLI, or on the phone with a passkey act that signs the exact notes and reason (curator web, D72).
- Secrets are refused at ingest and in notes; code citations read confined bare mirrors only.
- Optional SkillSpector scan of skills at ingest: a `DO_NOT_INSTALL`, partial or failed scan blocks the skill for agents (and in MCP Skills for everyone) until a curator clears it; `SAFE` grants nothing.

Details: `docs/guide/security.md`.

## Documentation

| Read | For |
|---|---|
| `docs/guide/index.md` | the map and the reading order |
| `docs/guide/concepts.md` | books, versions, journals, notes, Standing, origin, rights, grants, delegation |
| `docs/guide/install.md` | development, full stack, local models, database roles, upgrades |
| `docs/guide/operations.md` | the CLI: ingest, index, grants, journals, curation, exports, repositories, backups |
| `docs/guide/mcp.md`, `docs/guide/http-api.md` | the interfaces |
| `docs/guide/agent-memory.md` | a how-to for orchestrators |
| `docs/guide/security.md`, `docs/guide/kstd.md` | the security model and the kstd manifest |
| `docs/guide/troubleshooting.md`, `docs/guide/changelog.md` | errors and changes |

Design and decisions: `docs/01-direction-decisions.md`, `docs/23-vision-v1.md`, `docs/24-r1-agent-memory-design.md`.

## Status

Version 0.1.0, under active development; interfaces can change. Built: file books with kstd L0, hybrid search,
answers with citations, signed packages, agent memory R1 (notes, fast reads, code citations, MCP 2026-07-28,
headless auth), R2 rollback, outcomes, decision export, bulk import and private journals, a light install
without LLMDAP (#76), and curator web with passkey acts (D72, `docs/25` slice P). Open: the risk-ordered curator
queue (#77, slice Q), the "my words" confirmation (D70 R3), delegated curate (#78) and MCP Skills (#80). See
`docs/guide/changelog.md`.

## Licence

The code is licensed under Apache-2.0 (`LICENSE`). The kstd specification text in `docs/` and `kstd/` is
licensed under CC-BY-4.0 (`NOTICE`). Contributions: `CONTRIBUTING.md`.
