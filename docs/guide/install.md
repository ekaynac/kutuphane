# Install

This page tells you how to install Kütüphane. There are three ways:

| Way | For | Model calls |
|---|---|---|
| [Development](#development-install) | a developer laptop, tests, the quick start | none, or the stub models |
| [Full stack](#full-stack) | one server (D15): Postgres, Core, the ingress proxy, LLMDAP | through LLMDAP |
| [Local models](#local-models-overlay) | the full stack with real models on the same machine (D61) | nothing leaves the machine |

The [light install](#light-install-status) (no LLMDAP, one container) is not ready yet (#76).

## Requirements

- Docker with Compose v2.
- Python 3.11 or later (for the CLI on the host). The container uses Python 3.12.
- git 2.45 or later in the Core container, for code citations. The image checks this when you build it.
- An encrypted disk volume for the database and the audit volume (D48). Kütüphane does not encrypt data.

## Development install

```sh
python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'
printf 'KUTUPHANE_DB_PASSWORD=%s\n' "$(python3 -c 'import secrets;print(secrets.token_urlsafe(24))')" > .env
docker compose up -d --wait postgres
set -a; . ./.env; set +a
export KUTUPHANE_DSN="postgresql://kutuphane:${KUTUPHANE_DB_PASSWORD}@127.0.0.1:55432/kutuphane"
.venv/bin/kutuphane migrate
```

Postgres listens on `127.0.0.1:55432` for development and tests only. Remove that port in production.

To run the tests, make a separate test database:

```sh
docker compose exec -T postgres psql -U kutuphane -c 'CREATE DATABASE kutuphane_test'
export KUTUPHANE_TEST_DSN="${KUTUPHANE_DSN}_test"
.venv/bin/python -m pytest -q
(cd kstd/reference && ../../.venv/bin/python -m pytest -q -p no:cacheprovider)
```

To run the server on the host with development tokens, follow the quick start in the `README.md`. Development
tokens need `KUTUPHANE_DEV=1`. Never set it on a production machine.

## Full stack

The compose file `compose.yaml` starts these services:

| Service | Profile | Networks | Purpose |
|---|---|---|---|
| `postgres` | (always) | `db`, `dev` | pgvector/pgvector 0.8.0 on PostgreSQL 17 |
| `core` | `app` | `db`, `web`, `gateway` | the API, MCP server and web UI (`/ui`) on port 8080 |
| `ingress` | `app` | `edge`, `web` | nginx; the only way in from users; publishes `${KUTUPHANE_BIND:-127.0.0.1}:8080` |
| `llmdap` | `app` | `gateway`, `models` | the LLMDAP bridge; the only way to the model servers |
| `model-stub` | `dev-models` | `models` | deterministic stand-in models; never for measurements |
| `laya` | `decision-models` | `models` | the typed-decision model (labelling work) |

`db`, `web`, `gateway` and `models` are internal networks. Core reaches only Postgres and LLMDAP. Only LLMDAP
reaches the model servers.

### 1. Secrets and settings

Put these in `.env` (git-ignored). Do not put secrets anywhere else.

| Variable | Value |
|---|---|
| `KUTUPHANE_DB_PASSWORD` | the owner role password |
| `KUTUPHANE_APP_DB_PASSWORD` | the app role password (`kutuphane_app`) |
| `KUTUPHANE_PUBLIC_URL` | the public URL of the ingress, for example `https://kb.example.org` |
| `KUTUPHANE_OIDC_ISSUER` | the IdP issuer, exactly as its tokens carry it |
| `KUTUPHANE_OIDC_AUDIENCE` | the token audience (compose default `kutuphane`) |
| `KUTUPHANE_OIDC_JWKS_FILE` | the host path of the IdP's JWKS file (compose mounts it at `/run/kutuphane/jwks.json`) |
| `KUTUPHANE_ANSWER_MODEL` | the answer model name, pinned on the chat route |
| `KUTUPHANE_LLMDAP_KEY` | Core's LLMDAP subject key (see step 3) |
| `KUTUPHANE_LLMDAP_ROUTE`, `KUTUPHANE_LLMDAP_EMBED_ROUTE`, `KUTUPHANE_LLMDAP_RERANK_ROUTE` | the route names |
| `KUTUPHANE_EMBED_MODEL`, `KUTUPHANE_RERANK_MODEL` | the pinned model names of those routes |
| `KUTUPHANE_REPO_DIR` | optional: the host folder of bare git mirrors (default `./deploy/repos`) |
| `KUTUPHANE_BIND` | optional: the address that the ingress publishes on (default `127.0.0.1`) |

The server refuses to start when `KUTUPHANE_ANSWER_MODEL`, `KUTUPHANE_PUBLIC_URL` or an OIDC setting is missing.
It also refuses an issuer that the MCP SDK would rewrite (an uppercase host, a default port). See `security.md`.
The full list of settings is in `operations.md`.

### 2. Database roles

Kütüphane uses two database roles:

| Role | Used by | Can |
|---|---|---|
| `kutuphane` (owner) | `kutuphane migrate`, `kutuphane note standing`, `kutuphane note rollback` (`KUTUPHANE_CURATOR_DSN`) | everything |
| `kutuphane_app` | the server and every process that an agent can reach (`KUTUPHANE_DSN`) | no Standing writes; memory rows are append-only |

Do these steps once, as the owner:

```sh
docker compose up -d --wait postgres
set -a; . ./.env; set +a
docker compose exec -T postgres psql -U kutuphane -d kutuphane -v ON_ERROR_STOP=1 \
  -c "CREATE ROLE kutuphane_app LOGIN PASSWORD '${KUTUPHANE_APP_DB_PASSWORD}'"
```

Do these steps after every upgrade:

```sh
export KUTUPHANE_CURATOR_DSN="postgresql://kutuphane:${KUTUPHANE_DB_PASSWORD}@127.0.0.1:55432/kutuphane"
.venv/bin/kutuphane migrate
docker compose exec -T postgres psql -U kutuphane -d kutuphane -v ON_ERROR_STOP=1 < deploy/db-roles.sql
```

`migrate` uses `KUTUPHANE_CURATOR_DSN`; without it, it uses `KUTUPHANE_DSN`. New tables need their grants, so
apply `deploy/db-roles.sql` after every `migrate`. The server refuses to start while a migration is pending.

Keep `KUTUPHANE_CURATOR_DSN` out of every environment that an agent can read: not in the Core container, not in an
orchestrator container, not in a shell profile that an agent session gets. Type it at the prompt or read it from a
secret store that asks the person.

### 3. LLMDAP

LLMDAP is the gateway for every model call. Its setup is in `deploy/llmdap/README.md`. In short:

1. Load the `llmdap-bridge` image (default tag `llmdap-bridge:0.28.0-llmdap1.18.0`; `LLMDAP_BRIDGE_IMAGE`
   overrides it).
2. Make Core's subject key. The token goes into `.env` as `KUTUPHANE_LLMDAP_KEY`. The hash entry goes into
   `deploy/llmdap/config/keys.json`.
3. Copy `deploy/llmdap/bridge.env.example` to `deploy/llmdap/bridge.env` and fill the audit key and the digest key.

The routes are in `deploy/llmdap/config/routes.json` (stub models), `routes.local.json` (local models) and
`routes.hosted.json` (a hosted decision model). `policy.csv` grants Core `llm:invoke` on the routes.

### 4. Start

```sh
docker compose --profile app up -d --build                        # real model servers on the models network
docker compose --profile app --profile dev-models up -d --build   # or: with the stub models
```

### 5. Check

```sh
curl -s http://127.0.0.1:8080/healthz
docker compose --profile app exec -T core python -I - < deploy/egress_probe.py           # AT-10 network check
KUTUPHANE_PROBE_TOKEN=<access token> python3 deploy/mcp_probe.py http://127.0.0.1:8080   # MCP through the proxy
```

`egress_probe.py` exits 0 only if Core reaches nothing but Postgres and LLMDAP. `mcp_probe.py` checks both MCP
protocol versions through the proxy. Add `--journal <book>` to also propose a note.

The web UI is at `/ui/` (in Turkish). It searches, asks and opens citations with your token.

## Local models overlay

The overlay `deploy/compose.local-models.yaml` adds real models. Nothing leaves the machine:

| Route | Service | Model |
|---|---|---|
| `chat` | `spark-chat` → the host's vLLM on port 8000 | `RadixArk/Qwen3.8-27B-NVFP4` |
| `emb` | `embedder` (CPU, 8 threads, 8 GB) | `BAAI/bge-m3` (1024 dimensions) |
| `rerank` | `embedder` | `BAAI/bge-reranker-v2-m3` |

The overlay sets Core's route and model settings itself. Download the pinned weights into the Hugging Face cache
once (`deploy/llmdap/README.md`, section "Local models"). Then:

```sh
docker compose -f compose.yaml -f deploy/compose.local-models.yaml \
  --profile app --profile decision-models --profile local-models up -d --build
```

Vectors are stored per model name. After you change the embedding model, run `kutuphane index <book>` for each
book.

**Hosted decision model.** `deploy/compose.hosted.yaml` gives LLMDAP an outbound network for one hosted route. Every
hosted call needs an `llm:egress` grant in `policy.csv`. Core's own routes stay `local` unless you set a
`*_ROUTE_CLASS` to `cloud`. A `local_only` book never goes to a `cloud` route.

## Light install status

Issue #76 (open) asks for one container with Postgres, Kütüphane and a local embedder, with no LLMDAP. It is not
built. What works today:

- The server starts without `KUTUPHANE_LLMDAP_URL`. Then it makes no model call: `search_library` and the note tools
  work (full-text search only). `ask_library` fails, and `POST /v1/ask` returns 502 "model service unavailable or
  refused".
  `KUTUPHANE_ANSWER_MODEL` must still have a value.
- The `core` service in `compose.yaml` always sets `KUTUPHANE_LLMDAP_URL` (default `http://llmdap:8787`). So in
  compose, use the full stack. Without compose, run the server on the host as in the quick start.

## Reboot and restart

- No service in the compose files has a `restart:` policy. After a host reboot, start the stack again with the
  same `docker compose … up -d` command.
- The database (`pgdata`) and the LLMDAP audit chain (`llmdap-audit`) are named volumes. They stay.
- Start the host's vLLM before you use the local-models overlay. Without it, `ask_library` fails; search and notes
  still work.
- A background job that was running when the server stopped becomes `failed: interrupted` when its lease ends
  (60 s). It never runs again. Submit it again.
- The server keeps query vectors in memory only. They are lost on a restart; this changes no result.

## Upgrade

1. Pull or check out the new version.
2. Run `kutuphane migrate` with the owner DSN, then apply `deploy/db-roles.sql` (step 2).
3. Rebuild and start: `docker compose --profile app up -d --build`.
4. Read `changelog.md` for changes that need an action, for example a re-ingest or a re-index.
