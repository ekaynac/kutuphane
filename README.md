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
Reranking (optional): `KUTUPHANE_LLMDAP_RERANK_ROUTE` (an LLMDAP `surface: "rerank"` route), `_RERANK_ROUTE_CLASS`,
`KUTUPHANE_RERANK_MODEL` (e.g. `bge-reranker-v2-m3`); the top 30 hybrid hits are reordered.
`echo "$TOKEN" | kutuphane whoami` verifies a token; `kutuphane explain <correlation-id> --llmdap-export audit.jsonl`
prints the unified audit.
