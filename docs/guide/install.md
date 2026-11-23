# Install

Four ways:

- [Development](#development-install): a laptop, tests, the quick start; no models or the stub models.
- [Light install](#light-install): `compose.yaml` (Postgres, Core, ingress proxy and a local CPU embedder; no LLMDAP,
  only open source parts, #76, #242); search with vectors and rerank, no answers until you name an answer model.
  This is the public install.
- [Full stack](#full-stack): `deploy/compose.full.yaml`, one server (D15), plus LLMDAP for model calls. The LLMDAP
  bridge is a proprietary component, available only under an LLMDAP agreement.
- [Local models](#local-models): the full stack with real models on the same machine (D61); nothing leaves it.

Both compose files use project `kutuphane` and the same `postgres` service and volume (`kutuphane_pgdata`). On a
host that already runs a Kütüphane install, read [Shared host](#shared-host) before you run any `docker compose`
command of this page.

## Requirements

- Docker with Compose v2; Python 3.11+ for the host CLI (the container uses 3.12).
- git 2.45+ in the Core container, for code citations (the image build checks it).
- An encrypted disk volume for the database and the audit volume (D48). Kütüphane does not encrypt data.

## Shared host

> **Warning.** Both compose files set `name: kutuphane`. On a host that already runs a Kütüphane install, a
> `docker compose` command without its own project name joins that install, and it can recreate its running
> containers (same `postgres` service, same volumes). Every other install, development run or test run on that host
> MUST use its own project name and other host ports.

- Project name: `docker compose -p kutuphane-<name> …` on every command (`down` and `ps` too), or
  `COMPOSE_PROJECT_NAME=kutuphane-<name>` in the `.env` of that checkout. The name sets the volume names
  (`kutuphane-<name>_pgdata`, `kutuphane-<name>_models`), so the other install keeps its data.
- Host ports: `compose.yaml` publishes Postgres on `127.0.0.1:55432` and the ingress proxy on
  `${KUTUPHANE_BIND:-127.0.0.1}:8080`. A second install on the same host replaces them in an override file
  (`-f compose.yaml -f ports.yaml`):

  ```yaml
  services:
    postgres:
      ports: !override ["127.0.0.1:55433:5432"]
    ingress:
      ports: !override ["127.0.0.1:8081:8080"]
  ```

  Then use these ports in the DSN of the host CLI and in the `curl` checks of this page.
- The commands of this page, [README.md](../../README.md) and [CONTRIBUTING.md](../../CONTRIBUTING.md) show no `-p`:
  add yours on a shared host.

## Image: release or source

`core` and `curator` use the image `ghcr.io/ekaynac/kutuphane:${KUTUPHANE_VERSION}`. `KUTUPHANE_VERSION` is a release
tag that you set in `.env` (see `.env.example`); there is no `latest`, and compose stops with `set KUTUPHANE_VERSION
to a release tag` when it is empty. The tag is a compose setting only: Core does not read it, and no Core setting
changes. The named volumes keep their names, so an existing install keeps its data.

To build the image from this checkout instead (development, CI): set `KUTUPHANE_VERSION=dev` and add the override
file `compose.build.yaml` (full stack: `deploy/compose.full.build.yaml`, which also builds `curator`):

```sh
KUTUPHANE_VERSION=dev docker compose -f compose.yaml -f compose.build.yaml up -d --build --wait
KUTUPHANE_VERSION=dev docker compose -f deploy/compose.full.yaml -f deploy/compose.full.build.yaml --profile app up -d --build
```

Or put `KUTUPHANE_VERSION=dev` and `COMPOSE_FILE=compose.yaml:compose.build.yaml` (full stack:
`deploy/compose.full.yaml:deploy/compose.full.build.yaml`) in `.env`; then the plain `docker compose … up -d --build`
commands of this page build from source. Without `--build` and without the override, they pull the release image.

## Development install

```sh
python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'
printf 'KUTUPHANE_VERSION=dev\nKUTUPHANE_DB_PASSWORD=%s\n' "$(python3 -c 'import secrets;print(secrets.token_urlsafe(24))')" > .env
docker compose up -d --wait postgres
set -a; . ./.env; set +a
export KUTUPHANE_DSN="postgresql://kutuphane:${KUTUPHANE_DB_PASSWORD}@127.0.0.1:55432/kutuphane"
.venv/bin/kutuphane migrate
```

Postgres listens on `127.0.0.1:55432` for development and tests only; remove that port in production. These
commands, and the test commands below, use no `-p`: on a shared host, add your own project name and ports
([Shared host](#shared-host)). Tests:

```sh
docker compose exec -T postgres psql -U kutuphane -c 'CREATE DATABASE kutuphane_test'
export KUTUPHANE_TEST_DSN="${KUTUPHANE_DSN}_test"
.venv/bin/python -m pytest -q
(cd kstd/reference && ../../.venv/bin/python -m pytest -q -p no:cacheprovider)
```

Development tokens (`README.md` quick start) need `KUTUPHANE_DEV=1`. Never set it on a production machine.

## Full stack

The full stack needs the LLMDAP bridge image, a proprietary component that comes as a signed release tarball under an
LLMDAP agreement. Without such an agreement, use the [light install](#light-install).

With `COMPOSE_FILE=deploy/compose.full.yaml` in `.env`, every `docker compose` command here (run from the
repository root) uses the full stack (project `kutuphane`; paths relative to `deploy/`); without it, the light
`compose.yaml`. Or: `docker compose -f deploy/compose.full.yaml --env-file .env …`. Services (profile; networks):

- `postgres` (always; `db`, `dev`, `curator-db`): pgvector/pgvector 0.8.0 on PostgreSQL 17.
- `core` (`app`; `db`, `web`, `gateway`): API, MCP server, web UI (`/ui`) on port 8080.
- `ingress` (`app`; `edge`, `web`): nginx, the only way in; publishes `${KUTUPHANE_BIND:-127.0.0.1}:8080`.
- `llmdap` (`app`; `gateway`, `models`, `outbound`): the LLMDAP bridge, the only way to the model servers.
- `model-stub` (`dev-models`; `models`): deterministic stand-in models; never for measurements.
- `embedder`, `spark-chat` (`local-models`; `models`, `spark-chat` also `spark`): [local models](#local-models).
- `reranker-gpu` (`gpu-rerank`; `models`): [GPU reranker](#gpu-reranker).
- `curator`, `tailscale` (`curator`; `curator-db`, `curator` / `curator`, `tailnet`): [curator web](#curator-web).
- `publisher` (`publisher`; `db`, `gateway`): the owner-credential loop of `imports publish-admitted`, off by default.
  It replaces the host timer; never run both ([operations.md](operations.md#publisher-service-compose)).

`core`, `curator` and `publisher` run `ghcr.io/ekaynac/kutuphane:${KUTUPHANE_VERSION}`; `.env.example` lists the settings.

`db`, `web`, `gateway`, `models`, `curator-db` and `curator` are internal. `outbound` is internal too, except for a
[hosted decision model](#local-models). Core reaches only Postgres and LLMDAP.

### 1. Secrets and settings

Put these in `.env` (git-ignored), and secrets nowhere else:

- `COMPOSE_FILE`: `deploy/compose.full.yaml` (for a source build, `deploy/compose.full.yaml:deploy/compose.full.build.yaml`).
- `KUTUPHANE_VERSION`: the release tag of the Kütüphane image (`dev` for a source build).
- `KUTUPHANE_DB_PASSWORD`, `KUTUPHANE_APP_DB_PASSWORD`: owner and app role passwords.
- `KUTUPHANE_PUBLIC_URL`: the ingress URL, for example `https://kb.example.org`.
- `KUTUPHANE_OIDC_ISSUER` (exactly as tokens carry it), `KUTUPHANE_OIDC_AUDIENCE` (default `kutuphane`),
  `KUTUPHANE_OIDC_JWKS_FILE` (host path, default `deploy/jwks.json`, mounted at `/run/kutuphane/jwks.json`).
- `KUTUPHANE_LLMDAP_KEY`: Core's LLMDAP subject key (step 3).
- `KUTUPHANE_ANSWER_MODEL` (pinned on the chat route), `KUTUPHANE_LLMDAP_ROUTE`, `KUTUPHANE_LLMDAP_EMBED_ROUTE`,
  `KUTUPHANE_LLMDAP_RERANK_ROUTE`, `KUTUPHANE_EMBED_MODEL`, `KUTUPHANE_RERANK_MODEL`, `KUTUPHANE_LLMDAP_ROUTES`
  (routes file): defaults in [local models](#local-models).
- Optional: a direct OpenAI-compatible provider for the answer model or the embedder instead of LLMDAP:
  `KUTUPHANE_ANSWER_PROVIDER` or `KUTUPHANE_EMBED_PROVIDER` `openai`, with `…_OPENAI_URL`, `…_OPENAI_KEY` and
  `…_OPENAI_CLASS` of that stage ([operations.md](operations.md#direct-model-providers)). The compose files set none.
- Optional: `KUTUPHANE_REPO_DIR` (bare git mirrors, default `deploy/repos`), `KUTUPHANE_BIND` (default `127.0.0.1`).

Give `KUTUPHANE_OIDC_JWKS_FILE` and `KUTUPHANE_REPO_DIR` as absolute paths (the full stack reads a relative path
from `deploy/`, the light install from the repository root). The server refuses to start without
`KUTUPHANE_PUBLIC_URL` or an OIDC setting, with `KUTUPHANE_LLMDAP_URL` or `KUTUPHANE_ANSWER_PROVIDER=openai` but no
`KUTUPHANE_ANSWER_MODEL`, and with an
issuer that the MCP SDK would rewrite ([security.md](security.md#identity)). All settings: [operations.md](operations.md).

### 2. Database roles

- `kutuphane` (owner, `KUTUPHANE_CURATOR_DSN`): everything; for `kutuphane migrate`, `kutuphane note standing`,
  `kutuphane note rollback`, `kutuphane skill clear`, `kutuphane curator …`.
- `kutuphane_app` (`KUTUPHANE_DSN`): the server and every process an agent can reach. No Standing writes, skill
  clearances or curation tables; memory rows and skill scan records append-only.
- `kutuphane_curator_web` (`KUTUPHANE_CURATOR_WEB_DSN`, optional): only Standing events that are items of a signed
  passkey act; no enrollment, no revocation.

Once, as the owner:

```sh
docker compose up -d --wait postgres
set -a; . ./.env; set +a
docker compose exec -T postgres psql -U kutuphane -d kutuphane -v ON_ERROR_STOP=1 \
  -c "CREATE ROLE kutuphane_app LOGIN PASSWORD '${KUTUPHANE_APP_DB_PASSWORD}'"
```

After every upgrade (new tables need grants; the server refuses to start while a migration is pending):

```sh
export KUTUPHANE_CURATOR_DSN="postgresql://kutuphane:${KUTUPHANE_DB_PASSWORD}@127.0.0.1:55432/kutuphane"
.venv/bin/kutuphane migrate
docker compose exec -T postgres psql -U kutuphane -d kutuphane -v ON_ERROR_STOP=1 < deploy/db-roles.sql
# only with curator web:
docker compose exec -T postgres psql -U kutuphane -d kutuphane -v ON_ERROR_STOP=1 < deploy/db-roles-curator.sql
```

`migrate` uses `KUTUPHANE_CURATOR_DSN`, else `KUTUPHANE_DSN`. `deploy/db-roles.sql` also takes `TEMP` from
`PUBLIC`; the owner keeps it. Keep `KUTUPHANE_CURATOR_DSN` out of every environment that an agent can read
([security.md](security.md#curation-boundary)); type it or read it from a secret store that asks the person.

### 3. LLMDAP

LLMDAP is the gateway for every model call (setup: `deploy/llmdap/README.md`):

1. Load the `llmdap-bridge` image (default `llmdap-bridge:0.28.0-llmdap1.18.0`; `LLMDAP_BRIDGE_IMAGE` overrides).
2. Make Core's subject key: token into `.env` as `KUTUPHANE_LLMDAP_KEY`, hash entry into
   `deploy/llmdap/config/keys.json`.
3. Copy `deploy/llmdap/bridge.env.example` to `deploy/llmdap/bridge.env`; fill the audit and digest keys.

Routes files in `deploy/llmdap/config/`: `routes.json` (stub), `routes.local.json` (default), `routes.hosted.json`.
`policy.csv` grants Core `llm:invoke` on the routes.

### 4. Start

On a shared host, add your own `-p` and ports ([Shared host](#shared-host)) to every command here.

```sh
docker compose --profile app up -d                        # real model servers
docker compose --profile app --profile dev-models up -d   # or: stub models; a source build: add --build
```

Other model servers: set the six route and model settings and `KUTUPHANE_LLMDAP_ROUTES`. Stub models:
`KUTUPHANE_LLMDAP_ROUTES=routes.json` and the dev values in `deploy/llmdap/README.md`.

### 5. Check

```sh
curl -s http://127.0.0.1:8080/healthz
docker compose --profile app exec -T core python -I - < deploy/egress_probe.py           # AT-10
KUTUPHANE_PROBE_TOKEN=<access token> python3 deploy/mcp_probe.py http://127.0.0.1:8080
```

`egress_probe.py` exits 0 only if Core reaches nothing but Postgres and LLMDAP. `mcp_probe.py` checks both MCP
protocol versions through the proxy; `--journal <book>` also proposes a note. The web UI (Turkish) is at `/ui/`.

### Core as a host user service

Use this when Core runs on the docker host and not in the `core` container, for example for an orchestrator on
the same host (#141). `postgres`, `llmdap` and the model servers stay in compose; do not start `core` and
`ingress`. Limits:

- Core is not in the internal networks. It can reach what the host can reach, and `egress_probe.py` does not apply.
  The model gates (`ai_use`, egress, route classes) are in Core and do not change.
- LLMDAP has no host port. Core uses the address of the `llmdap` container on the `gateway` network. The address
  can change when compose makes the container again; then set it again and restart Core.
- `KUTUPHANE_PUBLIC_URL` is the address that clients use, exactly (`127.0.0.1` and `localhost` are different): MCP
  refuses another `Host`.

**Once:**

1. A deploy checkout that does not follow branch changes, with its own environment. The service runs the installed
   copy, never a development tree (a restart would run the branch that is checked out there):
   ```sh
   git worktree add --detach <deploy dir> <tag or merged commit>
   python3 -m venv <deploy dir>/.venv && <deploy dir>/.venv/bin/pip install <deploy dir>
   ```
2. The LLMDAP address:
   `docker inspect -f '{{(index .NetworkSettings.Networks "kutuphane_gateway").IPAddress}}' kutuphane-llmdap-1`.
3. `~/.config/kutuphane/core.env` (mode 600). The host has no compose defaults
   ([operations.md](operations.md#variables)), so set each value, with absolute paths:
   ```sh
   KUTUPHANE_DSN=postgresql://kutuphane_app:<password>@127.0.0.1:55432/kutuphane
   KUTUPHANE_PUBLIC_URL=http://127.0.0.1:<port>
   KUTUPHANE_OIDC_ISSUER=<issuer>
   KUTUPHANE_OIDC_JWKS=<JWKS file>
   KUTUPHANE_LLMDAP_URL=http://<LLMDAP address>:8787
   KUTUPHANE_LLMDAP_KEY=<Core's subject key>
   KUTUPHANE_LLMDAP_ROUTE=chat
   KUTUPHANE_LLMDAP_ROUTE_CLASS=local
   KUTUPHANE_ANSWER_MODEL=nvidia/Qwen3.8-Flash-Next-NVFP4
   KUTUPHANE_LLMDAP_EMBED_ROUTE=emb
   KUTUPHANE_LLMDAP_EMBED_ROUTE_CLASS=local
   KUTUPHANE_EMBED_MODEL=BAAI/bge-m3
   KUTUPHANE_LLMDAP_RERANK_ROUTE=rerank
   KUTUPHANE_LLMDAP_RERANK_ROUTE_CLASS=local
   KUTUPHANE_RERANK_MODEL=BAAI/bge-reranker-v2-m3
   ```
   `rerank-gpu` in place of `rerank` for the [GPU reranker](#gpu-reranker). Optional: `KUTUPHANE_OIDC_ISSUERS`,
   `KUTUPHANE_REPO_ROOTS`, `KUTUPHANE_JOB_WORKERS`. Never put `KUTUPHANE_CURATOR_DSN` in this file.
4. `~/.config/systemd/user/kutuphane-core.service`:
   ```ini
   [Service]
   EnvironmentFile=%h/.config/kutuphane/core.env
   ExecStart=<deploy dir>/.venv/bin/uvicorn --factory kutuphane.server:app_from_env --host 127.0.0.1 --port <port>
   Restart=always
   RestartSec=10
   UMask=0077

   [Install]
   WantedBy=default.target
   ```
   Then `systemctl --user daemon-reload && systemctl --user enable --now kutuphane-core`.
   `loginctl enable-linger <user>` keeps it running without a login and starts it at boot. If Postgres is not
   ready, Core stops at start, and systemd starts it again after 10 s.

**Check:** `curl -s http://127.0.0.1:<port>/healthz`, then `GET /v1/health` with a token
([http-api.md](http-api.md#33-get-v1health)).

**Upgrade:** `git -C <deploy dir> fetch && git -C <deploy dir> checkout --detach <new tag or commit>`;
`<deploy dir>/.venv/bin/pip install <deploy dir>`; with the owner DSN, `<deploy dir>/.venv/bin/kutuphane migrate`
and `deploy/db-roles.sql` ([step 2](#2-database-roles)); `systemctl --user restart kutuphane-core`.

## Local models

The profile `local-models` adds real models; nothing leaves the machine:

- `chat`: `spark-chat` → the host's vLLM on port 8000, `nvidia/Qwen3.8-Flash-Next-NVFP4`.
- `emb`: `embedder` (CPU, 8 threads, 8 GB), `BAAI/bge-m3` (1024 dimensions).
- `rerank`: `embedder`, `BAAI/bge-reranker-v2-m3`.
- `rerank-gpu`: `reranker-gpu` (GPU, profile `gpu-rerank`), the same weights.

These are the full stack defaults; `.env` overrides them. The host CLI reads no compose file: set its settings in
its own environment ([operations.md](operations.md)). Download the pinned weights once (`deploy/llmdap/README.md`,
"Local models"), then:

```sh
docker compose --profile app --profile local-models up -d --build
```

Vectors are stored per model name: after you change the embedding model, run `kutuphane index <book>` per book.

**Hosted decision model.** `KUTUPHANE_LLMDAP_OFFLINE=false` opens LLMDAP's network `outbound` for one hosted route
(`KUTUPHANE_LLMDAP_ROUTES=routes.hosted.json`; API key in `bridge.env`). Unset or `true`: `outbound` is internal.
Every hosted call needs an `llm:egress` grant in `policy.csv`. Core's routes stay `local` unless a `*_ROUTE_CLASS`
is `cloud`; a `local_only` book never goes to a `cloud` route. Then:

```sh
docker compose --profile app up -d llmdap
```

### GPU reranker

The CPU reranker takes most of a search's time (G26). Profile `gpu-rerank` runs the same reranker on the GPU
(image `vllm-node:latest`, never pulled; same read-only weights; no network out; non-root), with at most 0.04 of
the shared host memory (about 4.8 GB). Start it only when `free -g` shows 15 GB or more `available`. Never stop the
host's vLLM to make space.

```sh
docker compose --profile gpu-rerank up -d --no-deps reranker-gpu
KUTUPHANE_LLMDAP_RERANK_ROUTE=rerank-gpu   # in .env, restart Core; rerank or unset = CPU
```

Restart LLMDAP once after an upgrade that adds the route (`docker compose … restart llmdap`). `model_call` and the
LLMDAP audit show each call's route. Fallback: `KUTUPHANE_LLMDAP_RERANK_ROUTE=rerank`, then
`docker compose … stop reranker-gpu`. With the GPU route set and `reranker-gpu` down, a search keeps the hybrid
order, logs `reranking failed` and says `"rerank": "failed"` ([http-api.md](http-api.md#51-get-v1search)).
Measurements: `../26-pilot-2.md` §10.

## Curator web

Curator web is the curator's optional phone page for passkey-signed approvals (D72;
`../25-curator-queue-passkey-design.md`). It has its own container and database role; a Tailscale sidecar gives it
a tailnet host name with HTTPS (WebAuthn needs a secure context). Core and curator web cannot reach each other.

**Once:**

1. Tailscale admin console: MagicDNS and HTTPS certificates on; ACL tag `tag:kutuphane-curator`; only the
   operator's devices may reach `tag:kutuphane-curator:443`. Never turn on Funnel for it.
2. A tagged, non-reusable auth key for that tag in `deploy/tailscale/authkey` (mode 600; not in git).
3. The database role, as the owner:
   ```sh
   docker compose exec -T postgres psql -U kutuphane -d kutuphane -v ON_ERROR_STOP=1 \
     -c "CREATE ROLE kutuphane_curator_web LOGIN PASSWORD '${KUTUPHANE_CURATOR_WEB_DB_PASSWORD}'"
   docker compose exec -T postgres psql -U kutuphane -d kutuphane -v ON_ERROR_STOP=1 < deploy/db-roles-curator.sql
   ```
4. In `.env`: `KUTUPHANE_CURATOR_WEB_DB_PASSWORD`, `KUTUPHANE_WEBAUTHN_RP_ID=kutuphane-curator.<tailnet>.ts.net`,
   `KUTUPHANE_WEBAUTHN_ORIGIN=https://kutuphane-curator.<tailnet>.ts.net`. Passkeys belong to this host name; a
   new name means every curator enrolls again.
5. For Core: `KUTUPHANE_CURATOR_URL=https://kutuphane-curator.<tailnet>.ts.net`, the base of the "my words"
   confirmation URL (`propose_note` receipt, `confirm_origin`); without it the receipt gives `url: null` and the
   person opens `/requests`. `KUTUPHANE_CONFIRM_HOURS` (default 24, Core and curator web) keeps a request open.

**Start and check:**

```sh
docker compose --profile curator up -d        # a source build: add --build
python3 deploy/curator_probe.py https://kutuphane-curator.<tailnet>.ts.net    # from an operator device
```

`curator_probe.py` checks: (1) only HTTPS 443 answers, with strict headers; (2) Funnel is off in the sidecar;
(3) the curator container publishes no port and Core cannot reach it; (4) a cross-origin POST is refused. Run it
after each sidecar restart. Without the two WebAuthn settings, curator web stops at start and names them; without
the role password, its database login fails.

### Host install with tailscale serve

Use this when you cannot make a tagged auth key: curator web runs on the docker host as a systemd user service
behind `tailscale serve`. The RP ID is the host's tailnet name (`<host>.<tailnet>.ts.net`), shared by every HTTPS
443 service of the host. Funnel stays off.

**Once:**

1. MagicDNS and HTTPS certificates on; on the host `sudo tailscale set --operator=<user>` (no sudo for serve).
2. The database role (step 3 above), `deploy/db-roles.sql` before `deploy/db-roles-curator.sql`. If Core runs as
   the owner, these scripts do not change it (the owner keeps TEMP and skips the row policy).
3. In `.env`, for Core and `kutuphane curator enroll`: `KUTUPHANE_WEBAUTHN_RP_ID=<host>.<tailnet>.ts.net`,
   `KUTUPHANE_WEBAUTHN_ORIGIN=https://<host>.<tailnet>.ts.net` and `KUTUPHANE_CURATOR_URL` (the same origin).
4. A deploy checkout that does not follow branch changes: `git worktree add --detach <deploy dir> origin/main`.
5. `~/.config/kutuphane/curator-web.env` (mode 600):
   ```sh
   KUTUPHANE_CURATOR_WEB_DSN=postgresql://kutuphane_curator_web:<password>@127.0.0.1:55432/kutuphane
   KUTUPHANE_WEBAUTHN_RP_ID=<host>.<tailnet>.ts.net
   KUTUPHANE_WEBAUTHN_ORIGIN=https://<host>.<tailnet>.ts.net
   PYTHONPATH=<deploy dir>/src
   ```
6. `~/.config/systemd/user/kutuphane-curator-web.service`:
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
   Then `systemctl --user daemon-reload && systemctl --user enable --now kutuphane-curator-web`.
   `loginctl enable-linger <user>` keeps it running without a login.
7. `tailscale serve --bg --https=443 http://127.0.0.1:<port>`; `tailscale serve status` and
   `tailscale funnel status` must say "tailnet only".

**Check:** `python3 deploy/curator_probe.py https://<host>.<tailnet>.ts.net`; only checks 1 and 4 apply (for 2,
use `tailscale funnel status`). Its "port 80 and 8443 do not answer" part fails if a host service uses them.

**Upgrade:** `git -C <deploy dir> fetch && git -C <deploy dir> checkout --detach origin/main`;
`systemctl --user restart kutuphane-curator-web`.

**Development** (no Tailscale; WebAuthn accepts `http://localhost`):

```sh
export KUTUPHANE_WEBAUTHN_RP_ID=localhost KUTUPHANE_WEBAUTHN_ORIGIN=http://localhost:8090
KUTUPHANE_CURATOR_WEB_DSN=… .venv/bin/kutuphane curator web --port 8090
```

Enrollment and use: [operations.md](operations.md), section 7.

## Light install

No LLMDAP (#76, #242). `compose.yaml` starts `postgres` (`db`, `dev`,
`curator-db`; `127.0.0.1:55432` for the host CLI), `core` (`db`, `web`, `models`), `ingress` (`edge`, `web`; publishes
`${KUTUPHANE_BIND:-127.0.0.1}:8080`), `embedder` (`models`) and the one-shot `models-fetch` (`fetch`). Core reaches
Postgres and the embedder, nothing else. The first `up` downloads the model weights once
([below](#model-weights-and-offline-install)).

### What works and what is lost

- `search_library`, `GET /v1/search`: full text, vectors (bge-m3) and rerank (bge-reranker-v2-m3) from the local
  `embedder`. Without it ([operations.md](operations.md#standalone-embedder)): full text only, so other words or
  another language find less. Question translation needs an answer model.
- `open_citation`, `read_document`, notes, links, outcomes, decisions, code citations: as in the full stack.
- `ask_library`, `POST /v1/ask`, the job tools: not available until you set an answer model
  ([operations.md](operations.md#standalone-embedder)). `tools/list` omits `ask_library`, `job_status`,
  `job_result` and `job_cancel`. `POST /v1/ask` gives HTTP `503` `answers are not available: this install has no
  model gateway (LLMDAP); search is full text only`, also with `background: true` (no job is made).
- A direct call has a `model_call` row (route `openai:embedder:8000`) but no LLMDAP audit chain (AT-09).

Core calls a model through LLMDAP or, if you set a direct provider, an OpenAI-compatible endpoint (D3, D88). The light
install uses the direct provider for the embedder (`KUTUPHANE_EMBED_PROVIDER=openai` and the rerank twin; the
variables are in `compose.yaml`, [operations.md](operations.md#direct-model-providers)). An embedding or rerank route
without `KUTUPHANE_LLMDAP_URL` stops the server (`LLMDAP not configured: set KUTUPHANE_LLMDAP_URL, …`), so to run
with no model server set both providers to `llmdap` ([operations.md](operations.md#standalone-embedder)).

### Steps

For a first install of the latest release. A release needs a checkout of its tag (`git clone`, then
`git checkout <tag>`): the compose files, `deploy/` scripts and SQL come from it, and its tag is `KUTUPHANE_VERSION`.
**No release exists yet.** Until the first release exists, build from source: check out `main`, set
`KUTUPHANE_VERSION=dev` and `COMPOSE_FILE=compose.yaml:compose.build.yaml` in `.env` ([above](#image-release-or-source)).
On a shared host, read [Shared host](#shared-host) first.

1. `cp .env.example .env` (git-ignored). Set `KUTUPHANE_VERSION` (the release tag; `dev` for a source build),
   `KUTUPHANE_DB_PASSWORD`, `KUTUPHANE_APP_DB_PASSWORD` (use letters and digits, `-` and `_` only: both go into a
   database address), `KUTUPHANE_PUBLIC_URL`, `KUTUPHANE_OIDC_ISSUER`, `KUTUPHANE_OIDC_JWKS_FILE`; optional
   `KUTUPHANE_OIDC_AUDIENCE`, `KUTUPHANE_BIND`, `KUTUPHANE_REPO_DIR` (paths absolute). No `COMPOSE_FILE` (except
   `compose.yaml:compose.build.yaml` for a source build) and no `KUTUPHANE_LLMDAP_*`. Shell
   variables override `.env`. Without `KUTUPHANE_PUBLIC_URL` or `KUTUPHANE_OIDC_ISSUER`, Core does not start and
   its log names the setting.
2. Make the database ready. Nothing runs a migration at start: Core refuses to start while one is pending
   (`database needs migrations … run kutuphane migrate`). `kutuphane migrate` is in the Core image, so no host
   Python is needed. **Source build:** run `docker compose build core` first. The migration runs from the image
   that exists, and an older `dev` image would run the old migrations.

   ```sh
   docker compose up -d --wait postgres
   set -a; . ./.env; set +a
   docker compose exec -T postgres psql -U kutuphane -d kutuphane -v ON_ERROR_STOP=1 \
     -c "CREATE ROLE kutuphane_app LOGIN PASSWORD '${KUTUPHANE_APP_DB_PASSWORD}'"
   PGPASSWORD="$KUTUPHANE_DB_PASSWORD" docker compose run --rm --no-deps -e PGPASSWORD \
     -e KUTUPHANE_CURATOR_DSN=postgresql://kutuphane@postgres:5432/kutuphane core kutuphane migrate
   docker compose exec -T postgres psql -U kutuphane -d kutuphane -v ON_ERROR_STOP=1 < deploy/db-roles.sql
   ```

   `migrate` prints the applied migrations as JSON (`"applied": [...]`). Shell variables override `.env`: if the
   migration fails with `password authentication failed`, check that your shell has no old `KUTUPHANE_DB_PASSWORD`.
   The roles are explained in [full stack step 2](#2-database-roles) (the curator web script is not needed).
3. Start the stack: `docker compose up -d` (from source: [see above](#image-release-or-source), with `--build`).
   The first `up` downloads the model weights once, about 4.5 GB ([below](#model-weights-and-offline-install));
   follow it with `docker compose logs -f models-fetch`. `docker compose ps` shows `core` and `embedder` `healthy`
   when the start is complete.
4. Check the start (with `--light`, `egress_probe.py` exits 0 only if Core reaches Postgres and nothing else):

   ```sh
   curl -s http://127.0.0.1:8080/healthz
   docker compose exec -T core python -I - --light < deploy/egress_probe.py   # the embedder is a known peer
   ```

   `GET /v1/health` with a token ([http-api.md](http-api.md#33-get-v1health)) shows `embedding` and `rerank` `true`.
5. First owner steps: a journal and the grants for an agent. Install the host CLI from the same checkout, and use
   the app role in a shell with no `KUTUPHANE_LLMDAP_*` (libpq reads the password from `PGPASSWORD`, so it is not in
   the address):

   ```sh
   python3 -m venv .venv && .venv/bin/pip install .
   export PGPASSWORD="$KUTUPHANE_APP_DB_PASSWORD"
   export KUTUPHANE_DSN=postgresql://kutuphane_app@127.0.0.1:55432/kutuphane
   .venv/bin/kutuphane journal create team-memory --search y --ai-input y \
     --sensitivity normal --egress local_only --protection standard --by user:admin
   for g in "book:team-memory read" "book:team-memory propose"; do .venv/bin/kutuphane grant $g agent:adc; done
   ```

   More books, rights and curation: `README.md` quick start, step 2, and [operations.md](operations.md). Publishing
   needs the owner credential (`KUTUPHANE_CURATOR_DSN`) and a `curate` grant for `--by`.
6. Check the MCP route through the proxy with an access token of the agent from step 5 (from your IdP; a
   development token: see below). The probe proposes one note into the journal:

   ```sh
   KUTUPHANE_PROBE_TOKEN=<access token> python3 deploy/mcp_probe.py http://127.0.0.1:8080 --journal team-memory
   ```

Development tokens (README quick start, step 3): `KUTUPHANE_OIDC_ISSUER` is `<KUTUPHANE_PUBLIC_URL>/dev`,
`KUTUPHANE_OIDC_JWKS_FILE` the `jwks.json` of `kutuphane dev-keys`.

### Variants

- **No models** (full text search only): add `compose.nomodels.yaml` to every command, here and in the
  [upgrade](#upgrade): `docker compose -f compose.yaml -f compose.nomodels.yaml up -d --wait` (or
  `COMPOSE_FILE=compose.yaml:compose.nomodels.yaml` in `.env`). Nothing is downloaded
  ([operations.md](operations.md#standalone-embedder)).
- **Another embedder or rerank server:** the same file, and the provider, URL, key, class and model of the stage in
  `.env` ([operations.md](operations.md#standalone-embedder)).
- **An answer model:** an OpenAI-compatible server in `.env`
  ([operations.md](operations.md#standalone-embedder), "Answers"). After the change, restart Core.
- **An LLMDAP outside this project:** the [full stack](#full-stack) with `deploy/compose.external-llmdap.yaml`
  ([operations.md](operations.md#llmdap-as-its-own-compose-project-242)). The network of that LLMDAP must be
  `internal: true`; do not use profile `app` with it.

### Model weights and offline install

The embedder needs `BAAI/bge-m3` (2.3 GB) and `BAAI/bge-reranker-v2-m3` (2.2 GB) at the commits pinned in
`deploy/models/server.py`. The first `docker compose up` runs `models-fetch`, which downloads them once into the named
volume `models` (about 4.5 GB of disk; some minutes on a fast link, at most about an hour on a slow one); `embedder`
starts after it, and is `healthy` about 20 s to 3 min later. A second `up` makes no download: `models-fetch` finds the
files and ends. (`models-fetch` always has its network `fetch`; it just does not use it.) The `embedder` has no
network out. The volume `models` needs no backup: download it again or pre-seed it.

To start with no network at all, fill the volume first from a Hugging Face cache that has the two commits, then run
`up`. `models-fetch` checks every file against the manifest and, with a complete volume, ends with success without
any call to the Hub. With an empty volume and no route to the Hub, or with a missing or wrong file, it ends with an
error that names the file (`missing` or the wrong size), and `embedder` and Core do not start.

Copy the two pinned `snapshots/<commit>` folders **with their blobs**: follow the links (`cp -rL` or `rsync -rL`).
Some caches keep the blobs in a shared store, and a plain copy (`cp -a`, `rsync -a`) leaves links that point to
nothing, which `models-fetch` reports as `missing`. The commits are `PINNED` in `deploy/models/server.py`:

```sh
mkdir -p seed/hub
for pair in bge-m3:5617a9f61b028005a4858fdac845db406aefb181 bge-reranker-v2-m3:953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e; do
  d="models--BAAI--${pair%%:*}"; mkdir -p "seed/hub/$d/snapshots"
  cp -rL "$HOME/.cache/huggingface/hub/$d/snapshots/${pair#*:}" "seed/hub/$d/snapshots/"
done
```

Then put `seed` in the volume. The volume is `<project>_models` (`kutuphane_models` for project `kutuphane`), and the
image is the one of your release:

```sh
docker volume create kutuphane_models
docker run --rm --user 0 --entrypoint sh -v kutuphane_models:/hf -v "$PWD/seed:/seed:ro" \
  ghcr.io/ekaynac/kutuphane-models:<release tag> -c 'cp -a /seed/. /hf/ && chown -R 65532 /hf'
```

`seed` holds `hub/models--BAAI--bge-m3/…` and `hub/models--BAAI--bge-reranker-v2-m3/…`.

To publish packages without a person at the command line, the `publisher` profile of `compose.yaml` runs the owner
credential loop (`imports publish-admitted`); it replaces a host timer, never run both ([operations.md](operations.md#publisher-service-compose)).

To add models later, set `COMPOSE_FILE=deploy/compose.full.yaml`, start the [full stack](#full-stack) (same
volume) and run `kutuphane index <book>` per book. An install from the old `deploy/compose.light.yaml` uses project
`kutuphane-light` (volume `kutuphane-light_pgdata`): keep it with `COMPOSE_PROJECT_NAME=kutuphane-light` in `.env`.

## Optional: SkillSpector

SkillSpector (NVIDIA, D71) scans skill folders at ingest; it is not in the Kütüphane package or image. Install it
where you run `kutuphane ingest`, `receive` and `skill rescan`. Needs `uv`, `curl`, Python 3.12 or 3.13 (yara-python
has no 3.14 wheel).

```sh
deploy/skillspector/install.sh /opt/skillspector        # or SKILLSPECTOR_PREFIX=…
export KUTUPHANE_SKILLSPECTOR_BIN=/opt/skillspector/bin/skillspector
export KUTUPHANE_SKILLSPECTOR_PROXY=http://127.0.0.1:9  # optional: block OSV.dev requests
.venv/bin/python -m pytest -q tests/test_skillspector_contract.py   # contract test
```

The script installs only the version in `deploy/skillspector/skillspector.pin`, checks the tarball sha256 (offline:
`SKILLSPECTOR_TARBALL=<file>`), refuses a folder that is not empty, and copies `LICENSE` and
`THIRD_PARTY_NOTICES.md` to `PREFIX/share/skillspector/`. The contract test checks the version, report format and
verdicts on known samples. What a scan blocks: [security.md](security.md#skill-scan-skillspector).

## Reboot and restart

- `postgres`, `core`, `ingress`, `llmdap`, `embedder`, `spark-chat` have `restart: unless-stopped` (light install
  too, with its own `embedder`; `models-fetch` runs once): Docker restarts them after a crash or reboot if the daemon starts at boot (`systemctl is-enabled docker`);
  `docker compose … stop` and `docker kill` keep one stopped (Docker counts both as a stop by a person; start it
  with `docker start`). `model-stub` and the curator services have no policy: run their `docker compose … up -d`
  again. `publisher` has `restart: unless-stopped`.
- `reranker-gpu` has `restart: unless-stopped` too (#141). Docker starts it again after a failed start (for example
  `CUDA error: out of memory` while the host's GPU memory is busy) and after an engine death (vLLM exits with code
  0). A failed start takes 20 to 60 s, and Docker starts the next one after 0.1 s, until a start works. It is
  `healthy` about one minute after a start that works (`docker compose … ps reranker-gpu`).
- [Core as a host user service](#core-as-a-host-user-service) has `Restart=always`; with `loginctl enable-linger`,
  systemd starts it at boot. `systemctl --user stop kutuphane-core` keeps it stopped.
- `GET /v1/health` (token needed; [http-api.md](http-api.md#33-get-v1health)) shows each dependency `true` when it
  answers now; `/healthz` only that the process answers.
- The named volumes `pgdata` and `llmdap-audit` (the LLMDAP audit chain) stay.
- Start the host's vLLM before you use local models; without it `ask_library` fails, search and notes work.
- A job that was running when the server stopped becomes `failed: interrupted` when its lease ends (60 s). It never
  runs again; submit it again.
- Query vectors are in memory only; a restart loses them and changes no result.

## Upgrade

Read `changelog.md` for the new release first: it names each action (a re-ingest, a re-index, a new setting).
**An older release ignores the provider settings of a newer one** (`KUTUPHANE_*_PROVIDER`): it starts without
models and gives full text search only, with no error. Read the release notes before an upgrade and before a
[rollback](#rollback).

Run every command in the checkout, in a shell that has the settings. Do this again in each new terminal, and
again after each change of `.env`:

```sh
cd <checkout>
set -a; . ./.env; set +a
: "${KUTUPHANE_DB_PASSWORD:?set KUTUPHANE_DB_PASSWORD in .env}"
```

1. Back up: [operations.md](operations.md#12-backups) (`pg_dump -Fc`). Keep the file until the new version works.
2. Get the new version. The compose files, `deploy/` SQL and scripts must match the image.
   - **Release:** `git fetch --tags && git checkout <new tag>`; set `KUTUPHANE_VERSION` in `.env` to the new tag and
     load `.env` again; then `docker compose pull` (full stack: add your `--profile` options).
   - **Source build** ([see above](#image-release-or-source)): `git checkout <new commit>`, then build the new image
     now, before the migration: `docker compose build core`. Step 3 runs `kutuphane migrate` from the image that
     exists; an old `dev` image would run the old migrations.
3. Migrate. Nothing runs a migration at start; the new Core refuses to start while one is pending. Stop `core`, run
   `kutuphane migrate` with the owner credential, then apply `deploy/db-roles.sql`
   (light: the commands of [Steps](#steps), step 2, without `CREATE ROLE`; full stack:
   [step 2](#2-database-roles)):

   ```sh
   docker compose stop core
   PGPASSWORD="$KUTUPHANE_DB_PASSWORD" docker compose run --rm --no-deps -e PGPASSWORD \
     -e KUTUPHANE_CURATOR_DSN=postgresql://kutuphane@postgres:5432/kutuphane core kutuphane migrate
   docker compose exec -T postgres psql -U kutuphane -d kutuphane -v ON_ERROR_STOP=1 < deploy/db-roles.sql
   ```

   A migrate that has nothing to do prints `"applied": []`.
4. Start the new version: `docker compose up -d` (source build: `docker compose up -d --build`). If the new
   release pins other model commits, `models-fetch` downloads them once. Full stack:
   - with the built-in LLMDAP: `docker compose --profile app up -d`;
   - with an [outside LLMDAP](#variants), and never `--profile app` (add the model profiles that you use):

     ```sh
     docker compose -f deploy/compose.full.yaml -f deploy/compose.external-llmdap.yaml --profile local-models up -d
     ```
5. Check: `curl -s http://127.0.0.1:8080/healthz`, `docker compose ps` (every service `healthy`), and `GET /v1/health`
   with a token: every stage that you use is `true`.
6. If you use SkillSpector and the pin changed, install the new pin into a new folder, point
   `KUTUPHANE_SKILLSPECTOR_BIN` at it, and run `kutuphane skill rescan`.
7. Do the actions that `changelog.md` names, for example a re-ingest or a re-index.

Use the same `-f` options and project name as at the install ([Shared host](#shared-host), the
[no-models variant](#variants)).

## Rollback

Migrations go forward only: there is no down script. An older Core starts on a newer schema (it refuses only
when a migration of its own is missing), but it can fail on tables or columns that it does not know. Go back only
in one of these two ways. In both, load the settings first (the three lines at the start of [Upgrade](#upgrade)).
Never run `kutuphane migrate`, and never start the newer release again, during a rollback.

- **The release notes of the newer release say that the older one works with the new schema.** `docker compose stop
  core`, check out the previous tag, set `KUTUPHANE_VERSION` to it, load `.env` again, `docker compose pull`
  (source build: `docker compose build core`), then `docker compose up -d` (full stack: with your `--profile`
  options). No database step.
- **Otherwise, or when the notes give no rollback SQL:** go back to the backup from before the upgrade, in this order:
  1. `docker compose down` (stops the newer release; keeps every volume).
  2. Check out the previous tag, set `KUTUPHANE_VERSION` to it in `.env`, load `.env` again, and get its image:
     `docker compose pull` (source build: `docker compose build core`). Do not start anything yet.
  3. Restore the backup into a new volume, as in [operations.md](operations.md#12-backups) ("Restore into a new
     volume"), and start the previous release (its step 4). The old, newer-schema volume stays on the disk, and
     nothing is migrated.
  4. Check as in [Upgrade](#upgrade), step 5. Everything written after that backup is lost. When you have checked
     the restored database, remove the old volume by hand.

An older release ignores `KUTUPHANE_*_PROVIDER` and starts without models: after a rollback, check that `embedding`
and `rerank` in `GET /v1/health` are `true`.
