# Install

This page tells you how to install Kütüphane. There are four ways:

| Way | For | Model calls |
|---|---|---|
| [Development](#development-install) | a developer laptop, tests, the quick start | none, or the stub models |
| [Light install](#light-install) | `compose.yaml`: Postgres, Core and the ingress proxy; no LLMDAP, only open source parts (#76) | none: full-text search, no answers |
| [Full stack](#full-stack) | `deploy/compose.full.yaml`, one server (D15): Postgres, Core, the ingress proxy, LLMDAP | through LLMDAP |
| [Local models](#local-models) | the full stack with real models on the same machine (D61) | nothing leaves the machine |

There are two compose files. Both have the project name `kutuphane` and the same `postgres` service, so they use the
same database container and the same volume (`kutuphane_pgdata`).

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

The compose file `deploy/compose.full.yaml` (project `kutuphane`) starts these services. Put
`COMPOSE_FILE=deploy/compose.full.yaml` in `.env`: then every `docker compose` command on this page, run from the
repository root, uses the full stack. Without it, `docker compose` uses the light `compose.yaml`. The other way is to
name the file and the `.env` in each command: `docker compose -f deploy/compose.full.yaml --env-file .env …`.

| Service | Profile | Networks | Purpose |
|---|---|---|---|
| `postgres` | (always) | `db`, `dev`, `curator-db` | pgvector/pgvector 0.8.0 on PostgreSQL 17 |
| `core` | `app` | `db`, `web`, `gateway` | the API, MCP server and web UI (`/ui`) on port 8080 |
| `ingress` | `app` | `edge`, `web` | nginx; the only way in from users; publishes `${KUTUPHANE_BIND:-127.0.0.1}:8080` |
| `llmdap` | `app` | `gateway`, `models`, `outbound` | the LLMDAP bridge; the only way to the model servers |
| `model-stub` | `dev-models` | `models` | deterministic stand-in models; never for measurements |
| `laya` | `decision-models` | `models` | the typed-decision model (labelling work) |
| `embedder`, `spark-chat` | `local-models` | `models` (`spark-chat` also `spark`) | [local models](#local-models) |
| `reranker-gpu` | `gpu-rerank` | `models` | [GPU reranker](#gpu-reranker) |
| `curator`, `tailscale` | `curator` | `curator-db`, `curator`; `curator`, `tailnet` | [curator web](#curator-web) |

`db`, `web`, `gateway`, `models`, `curator-db` and `curator` are internal networks. `outbound` is internal too,
except for a [hosted decision model](#local-models). Core reaches only Postgres and LLMDAP. Only LLMDAP reaches the
model servers. The paths in the file are relative to `deploy/`.

### 1. Secrets and settings

Put these in `.env` (git-ignored). Do not put secrets anywhere else.

| Variable | Value |
|---|---|
| `COMPOSE_FILE` | `deploy/compose.full.yaml` (see above) |
| `KUTUPHANE_DB_PASSWORD` | the owner role password |
| `KUTUPHANE_APP_DB_PASSWORD` | the app role password (`kutuphane_app`) |
| `KUTUPHANE_PUBLIC_URL` | the public URL of the ingress, for example `https://kb.example.org` |
| `KUTUPHANE_OIDC_ISSUER` | the IdP issuer, exactly as its tokens carry it |
| `KUTUPHANE_OIDC_AUDIENCE` | the token audience (compose default `kutuphane`) |
| `KUTUPHANE_OIDC_JWKS_FILE` | the host path of the IdP's JWKS file (compose mounts it at `/run/kutuphane/jwks.json`; default `deploy/jwks.json`) |
| `KUTUPHANE_ANSWER_MODEL` | the answer model name, pinned on the chat route (full stack default: [local models](#local-models)) |
| `KUTUPHANE_LLMDAP_KEY` | Core's LLMDAP subject key (see step 3) |
| `KUTUPHANE_LLMDAP_ROUTE`, `KUTUPHANE_LLMDAP_EMBED_ROUTE`, `KUTUPHANE_LLMDAP_RERANK_ROUTE` | the route names (full stack default: [local models](#local-models)) |
| `KUTUPHANE_EMBED_MODEL`, `KUTUPHANE_RERANK_MODEL` | the pinned model names of those routes (full stack default: [local models](#local-models)) |
| `KUTUPHANE_LLMDAP_ROUTES` | the routes file of LLMDAP (full stack default `routes.local.json`; see step 3) |
| `KUTUPHANE_REPO_DIR` | optional: the host folder of bare git mirrors (default `deploy/repos`) |
| `KUTUPHANE_BIND` | optional: the address that the ingress publishes on (default `127.0.0.1`) |

Give `KUTUPHANE_OIDC_JWKS_FILE` and `KUTUPHANE_REPO_DIR` as absolute paths: the full stack reads a relative path
from `deploy/`, the light install from the repository root.

The server refuses to start when `KUTUPHANE_PUBLIC_URL` or an OIDC setting is missing, and when
`KUTUPHANE_LLMDAP_URL` is set without `KUTUPHANE_ANSWER_MODEL`.
It also refuses an issuer that the MCP SDK would rewrite (an uppercase host, a default port). See `security.md`.
The full list of settings is in `operations.md`.

### 2. Database roles

Kütüphane uses these database roles:

| Role | Used by | Can |
|---|---|---|
| `kutuphane` (owner) | `kutuphane migrate`, `kutuphane note standing`, `kutuphane note rollback`, `kutuphane skill clear`, `kutuphane curator …` (`KUTUPHANE_CURATOR_DSN`) | everything |
| `kutuphane_app` | the server and every process that an agent can reach (`KUTUPHANE_DSN`) | no Standing writes, no skill clearances, no curation tables; memory rows and skill scan records are append-only |
| `kutuphane_curator_web` | curator web only (`KUTUPHANE_CURATOR_WEB_DSN`; optional, see [Curator web](#curator-web)) | Standing events that are items of a signed passkey act; no enrollment, no revocation |

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
# only with curator web:
docker compose exec -T postgres psql -U kutuphane -d kutuphane -v ON_ERROR_STOP=1 < deploy/db-roles-curator.sql
```

`migrate` uses `KUTUPHANE_CURATOR_DSN`; without it, it uses `KUTUPHANE_DSN`. New tables need their grants, so
apply `deploy/db-roles.sql` (and `deploy/db-roles-curator.sql` when you run curator web) after every `migrate`. The server refuses to start while a migration is pending.
`deploy/db-roles.sql` also takes the right to make temporary tables (`TEMP`) on the database from `PUBLIC`; the owner
of the database keeps it. No Kütüphane process needs temporary tables.

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

The routes are in `deploy/llmdap/config/routes.json` (stub models), `routes.local.json` (local models, the default)
and `routes.hosted.json` (a hosted decision model). `KUTUPHANE_LLMDAP_ROUTES` in `.env` names the file that LLMDAP
reads. `policy.csv` grants Core `llm:invoke` on the routes.

### 4. Start

```sh
docker compose --profile app up -d --build                        # real model servers on the models network
docker compose --profile app --profile dev-models up -d --build   # or: with the stub models
```

For model servers other than the [local models](#local-models), set the six route and model settings and
`KUTUPHANE_LLMDAP_ROUTES` in `.env`. The stub models: `KUTUPHANE_LLMDAP_ROUTES=routes.json` and the dev values in
`deploy/llmdap/README.md`.

### 5. Check

```sh
curl -s http://127.0.0.1:8080/healthz
docker compose --profile app exec -T core python -I - < deploy/egress_probe.py           # AT-10 network check
KUTUPHANE_PROBE_TOKEN=<access token> python3 deploy/mcp_probe.py http://127.0.0.1:8080   # MCP through the proxy
```

`egress_probe.py` exits 0 only if Core reaches nothing but Postgres and LLMDAP. `mcp_probe.py` checks both MCP
protocol versions through the proxy. Add `--journal <book>` to also propose a note.

The web UI is at `/ui/` (in Turkish). It searches, asks and opens citations with your token.

## Local models

The profile `local-models` of the full stack adds real models. Nothing leaves the machine:

| Route | Service | Model |
|---|---|---|
| `chat` | `spark-chat` → the host's vLLM on port 8000 | `RadixArk/Qwen3.8-27B-NVFP4` |
| `emb` | `embedder` (CPU, 8 threads, 8 GB) | `BAAI/bge-m3` (1024 dimensions) |
| `rerank` | `embedder` | `BAAI/bge-reranker-v2-m3` |
| `rerank-gpu` | `reranker-gpu` (GPU, profile `gpu-rerank`) | `BAAI/bge-reranker-v2-m3` (the same weights) |

The full stack's defaults are these routes and models: Core's route and model settings and LLMDAP's routes file
(`routes.local.json`) need no line in `.env`. A value in `.env` overrides its default. The CLI on the host reads no
compose file: give it the settings that it needs in its own environment ([operations.md](operations.md)).

Download the pinned weights into the Hugging Face cache once (`deploy/llmdap/README.md`, section "Local models").
Then:

```sh
docker compose --profile app --profile decision-models --profile local-models up -d --build
```

Vectors are stored per model name. After you change the embedding model, run `kutuphane index <book>` for each
book.

**Hosted decision model.** `KUTUPHANE_LLMDAP_OFFLINE=false` in `.env` makes the network `outbound` of LLMDAP a
network with a way out, for one hosted route (`KUTUPHANE_LLMDAP_ROUTES=routes.hosted.json` in `.env`; the API key
goes into `bridge.env`). Without `KUTUPHANE_LLMDAP_OFFLINE`, or with `true`, `outbound` is internal. Every hosted call
needs an `llm:egress` grant in `policy.csv`. Core's own routes stay `local` unless you set a `*_ROUTE_CLASS` to
`cloud`. A `local_only` book never goes to a `cloud` route. Start LLMDAP again:

```sh
docker compose --profile app --profile decision-models up -d llmdap
```

### GPU reranker

The CPU reranker takes most of the time of a search or an answer (G26). The profile `gpu-rerank` runs the same
reranker on the GPU with the host vLLM's own image (`vllm-node:latest`, the image of the `vllm_node` container; it is
never pulled). It reads the pinned weights from the same read-only Hugging Face cache as `embedder`, so it needs no
download. It has no network out and runs as a non-root user.

The GPU memory is the host memory, shared with the chat model. The service may take at most 0.04 of it (about
4.8 GB). Measured on the GB10: 1.9 GB (`nvidia-smi`), stable under load. Before you start it, check that `free -g`
shows 15 GB or more `available`. Never stop the host's vLLM to make space.

```sh
docker compose --profile gpu-rerank up -d --no-deps reranker-gpu
```

Then set the one switch in `.env` and start Core again (or export it for the host CLI):

```sh
KUTUPHANE_LLMDAP_RERANK_ROUTE=rerank-gpu   # rerank (or unset) = the CPU reranker in embedder
```

Both routes are in LLMDAP (`routes.local.json`, `policy.csv`). LLMDAP reads them at its start, so restart it once
after an upgrade that adds the route (`docker compose … restart llmdap`). After that, the switch needs no LLMDAP
restart, and `model_call` and the LLMDAP audit show which route served each call. The CPU route is the fallback: set
`KUTUPHANE_LLMDAP_RERANK_ROUTE=rerank` and stop `reranker-gpu` (`docker compose … stop reranker-gpu`). If the GPU
route is set but `reranker-gpu` is not running, a search keeps the hybrid order, logs `reranking failed` and says
`"rerank": "failed"` in its `retrieval` status ([http-api.md](http-api.md#51-get-v1search)).

On the pilot questions the rerank stage went from 11–25 s (CPU) to 0.2–0.3 s (GPU), with the same top 8 in the same
order (`docs/26` §10).

## Curator web

Curator web is the phone page of the curator (docs/25, D72): the curator approves or rejects pending notes and
signs each decision with a passkey. It is optional; the CLI path stays. It runs as its own container with its own
database role, and a Tailscale sidecar gives it its own tailnet host name with HTTPS (WebAuthn needs a secure
context). Core cannot reach it, and it cannot reach Core.

**Once:**

1. In the Tailscale admin console: MagicDNS and HTTPS certificates on. In the ACL, a tag `tag:kutuphane-curator`,
   and a rule that lets only the operator's devices reach `tag:kutuphane-curator:443`. Never turn on Funnel for it.
2. A tagged, non-reusable auth key for `tag:kutuphane-curator`, in `deploy/tailscale/authkey` (mode 600; it is not
   in git).
3. The database role, as the owner:
   ```sh
   docker compose exec -T postgres psql -U kutuphane -d kutuphane -v ON_ERROR_STOP=1 \
     -c "CREATE ROLE kutuphane_curator_web LOGIN PASSWORD '${KUTUPHANE_CURATOR_WEB_DB_PASSWORD}'"
   docker compose exec -T postgres psql -U kutuphane -d kutuphane -v ON_ERROR_STOP=1 < deploy/db-roles-curator.sql
   ```
4. In `.env`: `KUTUPHANE_CURATOR_WEB_DB_PASSWORD`, `KUTUPHANE_WEBAUTHN_RP_ID=kutuphane-curator.<tailnet>.ts.net`
   and `KUTUPHANE_WEBAUTHN_ORIGIN=https://kutuphane-curator.<tailnet>.ts.net`. Passkeys belong to this host name:
   if it changes, every curator enrolls again.
5. In `.env`, for Core: `KUTUPHANE_CURATOR_URL=https://kutuphane-curator.<tailnet>.ts.net`. Core puts it in the
   "my words" confirmation URL (`propose_note` receipt, `confirm_origin`). `KUTUPHANE_CONFIRM_HOURS` (default 24) is
   how long a confirmation request is open; Core and curator web read the same value. Without
   `KUTUPHANE_CURATOR_URL`, the receipt gives `url: null` and the person opens `/requests` in curator web.

**Start and check:**

```sh
docker compose --profile curator up -d --build
python3 deploy/curator_probe.py https://kutuphane-curator.<tailnet>.ts.net    # from a device of the operator
```

`curator_probe.py` checks that only HTTPS 443 answers with the strict headers, that Funnel is off in the sidecar,
that the curator container publishes no port, that Core cannot reach it, and that a POST from another origin is
refused. Run it again after a restart of the sidecar. Both compose files attach Postgres to the internal network
`curator-db`, so curator web needs no change to the Postgres container. Without the two WebAuthn settings of step 4,
curator web stops at its start and names them; without the role password, its database login fails.

### Host install with tailscale serve

Use this variant when you cannot make a tagged auth key for a sidecar. Curator web runs on the docker host as a
systemd user service, and `tailscale serve` on the host gives it HTTPS. The RP ID is then the host name of the host
on the tailnet (`<host>.<tailnet>.ts.net`). Every service of the host that serves on HTTPS 443 shares this name; the
tailnet ACL controls who can reach it. Funnel stays off.

**Once:**

1. In the Tailscale admin console: MagicDNS and HTTPS certificates on. On the host:
   `sudo tailscale set --operator=<user>` (then `tailscale serve` runs without sudo).
2. The database role (step 3 above), and `deploy/db-roles.sql` before `deploy/db-roles-curator.sql`. If Core runs
   as the owner, these scripts do not change it: the owner keeps TEMP and is not under the row policy.
3. In `.env`, for Core and for `kutuphane curator enroll`: `KUTUPHANE_WEBAUTHN_RP_ID=<host>.<tailnet>.ts.net`,
   `KUTUPHANE_WEBAUTHN_ORIGIN=https://<host>.<tailnet>.ts.net` and `KUTUPHANE_CURATOR_URL` (the same origin).
4. A deploy checkout that does not move when you change branches in the work checkout:
   `git worktree add --detach <deploy dir> origin/main`.
5. A service env file, `~/.config/kutuphane/curator-web.env` (mode 600):
   ```sh
   KUTUPHANE_CURATOR_WEB_DSN=postgresql://kutuphane_curator_web:<password>@127.0.0.1:55432/kutuphane
   KUTUPHANE_WEBAUTHN_RP_ID=<host>.<tailnet>.ts.net
   KUTUPHANE_WEBAUTHN_ORIGIN=https://<host>.<tailnet>.ts.net
   PYTHONPATH=<deploy dir>/src
   ```
6. The unit `~/.config/systemd/user/kutuphane-curator-web.service`:
   ```ini
   [Service]
   WorkingDirectory=<deploy dir>
   EnvironmentFile=%h/.config/kutuphane/curator-web.env
   ExecStart=<venv>/bin/python -m kutuphane.cli curator web --host 127.0.0.1 --port <port>
   Restart=always
   UMask=0077

   [Install]
   WantedBy=default.target
   ```
   Then `systemctl --user daemon-reload && systemctl --user enable --now kutuphane-curator-web`. Lingering
   (`loginctl enable-linger <user>`) keeps it running without a login.
7. `tailscale serve --bg --https=443 http://127.0.0.1:<port>`. Check `tailscale serve status` and
   `tailscale funnel status` (it must say "tailnet only").

**Check:** `python3 deploy/curator_probe.py https://<host>.<tailnet>.ts.net`. Checks 1 (HTTPS 443 and headers) and
4 (POST from another origin) apply. Checks 2 and 3 look for the sidecar, curator and Core containers, so they fail
for a host service; check Funnel with `tailscale funnel status` instead. The service binds only to 127.0.0.1, so
no container and no other device reaches it except through `tailscale serve`. The "port 80 and 8443 do not answer"
part fails when another service of the host listens on those ports.

**Upgrade:** `git -C <deploy dir> fetch && git -C <deploy dir> checkout --detach origin/main`, then
`systemctl --user restart kutuphane-curator-web`.

**Development on one machine** (no Tailscale): WebAuthn treats `http://localhost` as a secure context.

```sh
export KUTUPHANE_WEBAUTHN_RP_ID=localhost KUTUPHANE_WEBAUTHN_ORIGIN=http://localhost:8090
KUTUPHANE_CURATOR_WEB_DSN=… .venv/bin/kutuphane curator web --port 8090
```

Enrollment and use: [operations.md](operations.md), section 7.

## Light install

The light install has no LLMDAP and no model server (#76). An orchestrator can use Kütüphane over MCP with no
proprietary part. The compose file `compose.yaml` starts three containers:

| Service | Networks | Purpose |
|---|---|---|
| `postgres` | `db`, `dev`, `curator-db` | pgvector/pgvector 0.8.0 on PostgreSQL 17; `127.0.0.1:55432` for the CLI on the host |
| `core` | `db`, `web` | the API, MCP server and web UI, built from this repository; no model settings |
| `ingress` | `edge`, `web` | nginx; publishes `${KUTUPHANE_BIND:-127.0.0.1}:8080` |

Core reaches only Postgres. It makes no model call.

### What works and what is lost

| Function | Light install |
|---|---|
| `search_library`, `GET /v1/search` | Full text only. No vector search, no rerank, no question translation. |
| `open_citation`, `read_document`, notes, links, outcomes, decisions, code citations | The same as in the full stack. |
| `ask_library`, `POST /v1/ask`, the job tools | Not available. `tools/list` does not list `ask_library`, `job_status`, `job_result` and `job_cancel`. `POST /v1/ask` gives HTTP `503` `answers are not available: this install has no model gateway (LLMDAP); search is full text only`, also with `background: true`: no job is made. |
| Model audit | No model call, so no `model_call` row and no LLMDAP audit chain. |

What you lose:

- **Answers.** No `ask_library` answers with `[n]` citations, and no background ask jobs. The agent reads the passages
  itself with `search_library` and `open_citation`.
- **Vectors and rerank.** Search ranks by full text only. A question that uses other words than the text, or another
  language (a Turkish question for an English passage), finds less.
- **The model audit.** LLMDAP grants each model call (`policy.csv`) and signs its audit chain (AT-09). The light
  install has no model call to grant or audit.

**No local embedder.** Core calls a model only through LLMDAP (D3, `src/kutuphane/llmdap.py`). A direct call from
Core to the `embedder` container would skip the LLMDAP grant and the signed audit chain. So the light install has no
embedder. The server refuses to start when an embedding or rerank route is set without `KUTUPHANE_LLMDAP_URL`
(`LLMDAP not configured: set KUTUPHANE_LLMDAP_URL, …`). For vectors and rerank on local models, use the
[full stack](#full-stack) with [local models](#local-models).

### Steps

1. Put these in `.env`: `KUTUPHANE_DB_PASSWORD`, `KUTUPHANE_APP_DB_PASSWORD`, `KUTUPHANE_PUBLIC_URL`,
   `KUTUPHANE_OIDC_ISSUER` and `KUTUPHANE_OIDC_JWKS_FILE` (as in the full stack, step 1). Optional:
   `KUTUPHANE_OIDC_AUDIENCE`, `KUTUPHANE_BIND`, `KUTUPHANE_REPO_DIR`. Do not set `COMPOSE_FILE`.
   - Give `KUTUPHANE_OIDC_JWKS_FILE` and `KUTUPHANE_REPO_DIR` as absolute paths. Compose reads a relative path from
     the repository root.
   - A variable in your shell overrides the same variable in `.env`. Start compose from a shell that does not export
     the variables of another installation.
   - The compose file gives Core no `KUTUPHANE_LLMDAP_*` and no `KUTUPHANE_ANSWER_MODEL` setting. Without
     `KUTUPHANE_PUBLIC_URL` or `KUTUPHANE_OIDC_ISSUER`, Core does not start, and its log names the setting.
2. Start Postgres, make the app role (once), and migrate:

   ```sh
   docker compose up -d --wait postgres
   set -a; . ./.env; set +a
   docker compose exec -T postgres psql -U kutuphane -d kutuphane \
     -v ON_ERROR_STOP=1 -c "CREATE ROLE kutuphane_app LOGIN PASSWORD '${KUTUPHANE_APP_DB_PASSWORD}'"
   export KUTUPHANE_CURATOR_DSN="postgresql://kutuphane:${KUTUPHANE_DB_PASSWORD}@127.0.0.1:55432/kutuphane"
   .venv/bin/kutuphane migrate
   docker compose exec -T postgres psql -U kutuphane -d kutuphane -v ON_ERROR_STOP=1 < deploy/db-roles.sql
   ```

   After every upgrade, run `migrate` and `db-roles.sql` again (full stack, step 2).
3. Add books, journals and rights with the CLI on the host, as in the `README.md` quick start (step 2). Do not set
   `KUTUPHANE_LLMDAP_*` in that shell.
4. Start Core and the ingress proxy:

   ```sh
   docker compose up -d --build --wait
   ```

5. Check:

   ```sh
   curl -s http://127.0.0.1:8080/healthz
   docker compose exec -T core python -I - --light < deploy/egress_probe.py
   KUTUPHANE_PROBE_TOKEN=<access token> python3 deploy/mcp_probe.py http://127.0.0.1:8080 --journal <journal>
   ```

   With `--light`, `egress_probe.py` exits 0 only if Core reaches Postgres and nothing else (not LLMDAP either).

Tokens come from your IdP. For a test, use development tokens (README quick start, step 3): set
`KUTUPHANE_OIDC_ISSUER` to `<KUTUPHANE_PUBLIC_URL>/dev` and `KUTUPHANE_OIDC_JWKS_FILE` to the `jwks.json` of
`kutuphane dev-keys`.

The light install and the full stack use the same database volume (`kutuphane_pgdata`). To add models later, set
`COMPOSE_FILE=deploy/compose.full.yaml` in `.env`, start the [full stack](#full-stack), and run
`kutuphane index <book>` for each book. A light install made from the earlier `deploy/compose.light.yaml` has the
project `kutuphane-light` and the volume `kutuphane-light_pgdata`: put `COMPOSE_PROJECT_NAME=kutuphane-light` in
`.env` to keep using them.

## Optional: SkillSpector

SkillSpector (NVIDIA) scans skill folders at ingest (D71). It is optional and not part of the Kütüphane package or
image. Install it on the machine where you run `kutuphane ingest`, `receive` and `skill rescan`. You need `uv`,
`curl` and Python 3.12–3.14.

```sh
deploy/skillspector/install.sh /opt/skillspector        # or SKILLSPECTOR_PREFIX=…; default /opt/skillspector
export KUTUPHANE_SKILLSPECTOR_BIN=/opt/skillspector/bin/skillspector
export KUTUPHANE_SKILLSPECTOR_PROXY=http://127.0.0.1:9  # optional: block its OSV.dev requests
.venv/bin/python -m pytest -q tests/test_skillspector_contract.py   # the contract test of the installed version
```

- The script installs only the version in `deploy/skillspector/skillspector.pin`. It refuses a tarball whose sha256
  is not the pinned one. On a host without network, download the tarball elsewhere and give it with
  `SKILLSPECTOR_TARBALL=<file>`; the sha256 check still applies.
- It refuses a folder that is not empty. It copies SkillSpector's `LICENSE` and `THIRD_PARTY_NOTICES.md` to
  `PREFIX/share/skillspector/`.
- The contract test checks the version, the report format and the verdicts on known samples.
- What a scan does and blocks: [operations.md](operations.md) ("Skill scan") and [security.md](security.md).

## Reboot and restart

- `postgres`, `core`, `ingress` and `llmdap` (and, with the profile `local-models`, `embedder` and `spark-chat`) have
  `restart: unless-stopped`. Docker starts them again after a crash and after a host reboot, if the Docker daemon
  starts at boot (`systemctl is-enabled docker`). A service that you stopped with `docker compose … stop` stays
  stopped. The light install has the same policy for its three services. `laya`, `model-stub` and the curator
  services have no policy: start them again with the same `docker compose … up -d` command.
- `reranker-gpu` has `restart: on-failure:5`. A start that fails (for example `CUDA error: out of memory` while the
  GPU memory is busy) is tried again at most 5 times, with a longer wait each time. After a reboot it starts with
  the others. If it stops after 5 failures, check `free -g` (15 GB or more `available`) and start it again (below).
- Check the result with `GET /v1/health` (a token is necessary; [http-api.md](http-api.md#33-get-v1health)): each
  dependency is `true` when it answers now. `/healthz` shows only that the process answers.
- The database (`pgdata`) and the LLMDAP audit chain
  (`llmdap-audit`) are named volumes. They stay.
- Start the host's vLLM before you use local models. Without it, `ask_library` fails; search and notes
  still work.
- If the GPU reranker stopped after its retries, wait until the host's vLLM is up, check `free -g` (15 GB or more
  `available`), then start it again:
  `docker compose --profile gpu-rerank up -d --no-deps reranker-gpu`.
  It is ready in about one minute (`docker compose … ps reranker-gpu` shows `healthy`). Until then, with
  `KUTUPHANE_LLMDAP_RERANK_ROUTE=rerank-gpu`, searches keep the hybrid order and say `"rerank": "failed"` in their
  `retrieval` status.
- A background job that was running when the server stopped becomes `failed: interrupted` when its lease ends
  (60 s). It never runs again. Submit it again.
- The server keeps query vectors in memory only. They are lost on a restart; this changes no result.

## Upgrade

1. Pull or check out the new version.
2. Run `kutuphane migrate` with the owner DSN, then apply `deploy/db-roles.sql` (step 2).
3. Rebuild and start: `docker compose --profile app up -d --build` (light install:
   `docker compose up -d --build --wait`).
4. If you use SkillSpector and the pin changed, install the new pin into a new folder, point
   `KUTUPHANE_SKILLSPECTOR_BIN` at it, and run `kutuphane skill rescan`.
5. Read `changelog.md` for changes that need an action, for example a re-ingest or a re-index.
