# Install

Four ways:

- [Development](#development-install): a laptop, tests, the quick start; no models or the stub models.
- [Light install](#light-install): `compose.yaml` (Postgres, Core, ingress proxy; no LLMDAP, only open source parts,
  #76); full-text search, no answers.
- [Full stack](#full-stack): `deploy/compose.full.yaml`, one server (D15), plus LLMDAP for model calls.
- [Local models](#local-models): the full stack with real models on the same machine (D61); nothing leaves it.

Both compose files use project `kutuphane` and the same `postgres` service and volume (`kutuphane_pgdata`).

## Requirements

- Docker with Compose v2; Python 3.11+ for the host CLI (the container uses 3.12).
- git 2.45+ in the Core container, for code citations (the image build checks it).
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

Postgres listens on `127.0.0.1:55432` for development and tests only; remove that port in production. Tests:

```sh
docker compose exec -T postgres psql -U kutuphane -c 'CREATE DATABASE kutuphane_test'
export KUTUPHANE_TEST_DSN="${KUTUPHANE_DSN}_test"
.venv/bin/python -m pytest -q
(cd kstd/reference && ../../.venv/bin/python -m pytest -q -p no:cacheprovider)
```

Development tokens (`README.md` quick start) need `KUTUPHANE_DEV=1`. Never set it on a production machine.

## Full stack

With `COMPOSE_FILE=deploy/compose.full.yaml` in `.env`, every `docker compose` command here (run from the
repository root) uses the full stack (project `kutuphane`; paths relative to `deploy/`); without it, the light
`compose.yaml`. Or: `docker compose -f deploy/compose.full.yaml --env-file .env …`. Services (profile; networks):

- `postgres` (always; `db`, `dev`, `curator-db`): pgvector/pgvector 0.8.0 on PostgreSQL 17.
- `core` (`app`; `db`, `web`, `gateway`): API, MCP server, web UI (`/ui`) on port 8080.
- `ingress` (`app`; `edge`, `web`): nginx, the only way in; publishes `${KUTUPHANE_BIND:-127.0.0.1}:8080`.
- `llmdap` (`app`; `gateway`, `models`, `outbound`): the LLMDAP bridge, the only way to the model servers.
- `model-stub` (`dev-models`; `models`): deterministic stand-in models; never for measurements.
- `laya` (`decision-models`; `models`): the typed-decision model (labelling work).
- `embedder`, `spark-chat` (`local-models`; `models`, `spark-chat` also `spark`): [local models](#local-models).
- `reranker-gpu` (`gpu-rerank`; `models`): [GPU reranker](#gpu-reranker).
- `curator`, `tailscale` (`curator`; `curator-db`, `curator` / `curator`, `tailnet`): [curator web](#curator-web).

`db`, `web`, `gateway`, `models`, `curator-db` and `curator` are internal. `outbound` is internal too, except for a
[hosted decision model](#local-models). Core reaches only Postgres and LLMDAP.

### 1. Secrets and settings

Put these in `.env` (git-ignored), and secrets nowhere else:

- `COMPOSE_FILE`: `deploy/compose.full.yaml`.
- `KUTUPHANE_DB_PASSWORD`, `KUTUPHANE_APP_DB_PASSWORD`: owner and app role passwords.
- `KUTUPHANE_PUBLIC_URL`: the ingress URL, for example `https://kb.example.org`.
- `KUTUPHANE_OIDC_ISSUER` (exactly as tokens carry it), `KUTUPHANE_OIDC_AUDIENCE` (default `kutuphane`),
  `KUTUPHANE_OIDC_JWKS_FILE` (host path, default `deploy/jwks.json`, mounted at `/run/kutuphane/jwks.json`).
- `KUTUPHANE_LLMDAP_KEY`: Core's LLMDAP subject key (step 3).
- `KUTUPHANE_ANSWER_MODEL` (pinned on the chat route), `KUTUPHANE_LLMDAP_ROUTE`, `KUTUPHANE_LLMDAP_EMBED_ROUTE`,
  `KUTUPHANE_LLMDAP_RERANK_ROUTE`, `KUTUPHANE_EMBED_MODEL`, `KUTUPHANE_RERANK_MODEL`, `KUTUPHANE_LLMDAP_ROUTES`
  (routes file): defaults in [local models](#local-models).
- Optional: `KUTUPHANE_REPO_DIR` (bare git mirrors, default `deploy/repos`), `KUTUPHANE_BIND` (default `127.0.0.1`).

Give `KUTUPHANE_OIDC_JWKS_FILE` and `KUTUPHANE_REPO_DIR` as absolute paths (the full stack reads a relative path
from `deploy/`, the light install from the repository root). The server refuses to start without
`KUTUPHANE_PUBLIC_URL` or an OIDC setting, with `KUTUPHANE_LLMDAP_URL` but no `KUTUPHANE_ANSWER_MODEL`, and with an
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

```sh
docker compose --profile app up -d --build                        # real model servers
docker compose --profile app --profile dev-models up -d --build   # or: stub models
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

## Local models

The profile `local-models` adds real models; nothing leaves the machine:

- `chat`: `spark-chat` → the host's vLLM on port 8000, `RadixArk/Qwen3.8-27B-NVFP4`.
- `emb`: `embedder` (CPU, 8 threads, 8 GB), `BAAI/bge-m3` (1024 dimensions).
- `rerank`: `embedder`, `BAAI/bge-reranker-v2-m3`.
- `rerank-gpu`: `reranker-gpu` (GPU, profile `gpu-rerank`), the same weights.

These are the full stack defaults; `.env` overrides them. The host CLI reads no compose file: set its settings in
its own environment ([operations.md](operations.md)). Download the pinned weights once (`deploy/llmdap/README.md`,
"Local models"), then:

```sh
docker compose --profile app --profile decision-models --profile local-models up -d --build
```

Vectors are stored per model name: after you change the embedding model, run `kutuphane index <book>` per book.

**Hosted decision model.** `KUTUPHANE_LLMDAP_OFFLINE=false` opens LLMDAP's network `outbound` for one hosted route
(`KUTUPHANE_LLMDAP_ROUTES=routes.hosted.json`; API key in `bridge.env`). Unset or `true`: `outbound` is internal.
Every hosted call needs an `llm:egress` grant in `policy.csv`. Core's routes stay `local` unless a `*_ROUTE_CLASS`
is `cloud`; a `local_only` book never goes to a `cloud` route. Then:

```sh
docker compose --profile app --profile decision-models up -d llmdap
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
docker compose --profile curator up -d --build
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

No LLMDAP, no model server (#76). `compose.yaml` starts `postgres` (`db`, `dev`,
`curator-db`; `127.0.0.1:55432` for the host CLI), `core` (`db`, `web`; no model settings) and `ingress` (`edge`,
`web`; publishes `${KUTUPHANE_BIND:-127.0.0.1}:8080`). Core reaches only Postgres.

### What works and what is lost

- `search_library`, `GET /v1/search`: full text only; no vectors, rerank or question translation, so other words or
  another language find less.
- `open_citation`, `read_document`, notes, links, outcomes, decisions, code citations: as in the full stack.
- `ask_library`, `POST /v1/ask`, the job tools: not available. `tools/list` omits `ask_library`, `job_status`,
  `job_result` and `job_cancel`. `POST /v1/ask` gives HTTP `503` `answers are not available: this install has no
  model gateway (LLMDAP); search is full text only`, also with `background: true` (no job is made).
- No `model_call` row and no LLMDAP audit chain (AT-09).

Core calls a model only through LLMDAP (D3), so there is no local embedder. An embedding or rerank route without
`KUTUPHANE_LLMDAP_URL` stops the server (`LLMDAP not configured: set KUTUPHANE_LLMDAP_URL, …`).

### Steps

1. In `.env`: `KUTUPHANE_DB_PASSWORD`, `KUTUPHANE_APP_DB_PASSWORD`, `KUTUPHANE_PUBLIC_URL`,
   `KUTUPHANE_OIDC_ISSUER`, `KUTUPHANE_OIDC_JWKS_FILE`; optional `KUTUPHANE_OIDC_AUDIENCE`, `KUTUPHANE_BIND`,
   `KUTUPHANE_REPO_DIR` (paths absolute). No `COMPOSE_FILE`, `KUTUPHANE_LLMDAP_*` or `KUTUPHANE_ANSWER_MODEL`. Shell
   variables override `.env`. Without `KUTUPHANE_PUBLIC_URL` or `KUTUPHANE_OIDC_ISSUER`, Core does not start and
   its log names the setting.
2. Do [full stack step 2](#2-database-roles) (without the curator web script).
3. Add books, journals and rights with the host CLI (`README.md` quick start, step 2), with no
   `KUTUPHANE_LLMDAP_*` in that shell.
4. Start Core and the ingress proxy: `docker compose up -d --build --wait`.
5. Check (with `--light`, `egress_probe.py` exits 0 only if Core reaches Postgres and nothing else):

   ```sh
   curl -s http://127.0.0.1:8080/healthz
   docker compose exec -T core python -I - --light < deploy/egress_probe.py
   KUTUPHANE_PROBE_TOKEN=<access token> python3 deploy/mcp_probe.py http://127.0.0.1:8080 --journal <journal>
   ```

Development tokens (README quick start, step 3): `KUTUPHANE_OIDC_ISSUER` is `<KUTUPHANE_PUBLIC_URL>/dev`,
`KUTUPHANE_OIDC_JWKS_FILE` the `jwks.json` of `kutuphane dev-keys`.

To add models later, set `COMPOSE_FILE=deploy/compose.full.yaml`, start the [full stack](#full-stack) (same
volume) and run `kutuphane index <book>` per book. An install from the old `deploy/compose.light.yaml` uses project
`kutuphane-light` (volume `kutuphane-light_pgdata`): keep it with `COMPOSE_PROJECT_NAME=kutuphane-light` in `.env`.

## Optional: SkillSpector

SkillSpector (NVIDIA, D71) scans skill folders at ingest; it is not in the Kütüphane package or image. Install it
where you run `kutuphane ingest`, `receive` and `skill rescan`. Needs `uv`, `curl`, Python 3.12–3.14.

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
  too): Docker restarts them after a crash or reboot if the daemon starts at boot (`systemctl is-enabled docker`);
  `docker compose … stop` keeps one stopped. `laya`, `model-stub` and the curator services have no policy: run
  their `docker compose … up -d` again.
- `reranker-gpu` has `restart: on-failure:5`: a failed start (for example `CUDA error: out of memory`) is retried
  at most 5 times, with longer waits. After that, wait for the host's vLLM, check `free -g`, and start it as in
  [GPU reranker](#gpu-reranker). It is `healthy` after about one minute (`docker compose … ps reranker-gpu`).
- `GET /v1/health` (token needed; [http-api.md](http-api.md#33-get-v1health)) shows each dependency `true` when it
  answers now; `/healthz` only that the process answers.
- The named volumes `pgdata` and `llmdap-audit` (the LLMDAP audit chain) stay.
- Start the host's vLLM before you use local models; without it `ask_library` fails, search and notes work.
- A job that was running when the server stopped becomes `failed: interrupted` when its lease ends (60 s). It never
  runs again; submit it again.
- Query vectors are in memory only; a restart loses them and changes no result.

## Upgrade

1. Pull or check out the new version.
2. Run `kutuphane migrate` with the owner DSN, then apply `deploy/db-roles.sql` (step 2).
3. Rebuild and start: `docker compose --profile app up -d --build` (light: `docker compose up -d --build --wait`).
4. If you use SkillSpector and the pin changed, install the new pin into a new folder, point
   `KUTUPHANE_SKILLSPECTOR_BIN` at it, and run `kutuphane skill rescan`.
5. Read `changelog.md` for changes that need an action, for example a re-ingest or a re-index.
