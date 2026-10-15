# LLMDAP in the Kütüphane compose (D52, AT-09/10/11)

LLMDAP's bridge-only image (`llmdap-bridge`, LLMDAP #237) is the only way to the model servers. It runs on the
`gateway` network (to Core) and the `models` network (to the model servers). Neither network has a route out.

## Files

| File | In git | Content |
|---|---|---|
| `config/routes.json` | yes | bridge routes: `chat`, `emb` (embeddings), `rerank`. The dev routes point to `model-stub`. |
| `config/policy.csv` | yes | `p, svc-kutuphane, llm:invoke, llm/<route>` |
| `config/keys.json` | **no** | Core's subject key, as a **hash** only (`GATEWAY_SUBJECT_KEYS_FILE`) |
| `bridge.env` | **no** | audit signing key, digest key, auth mode (copy `bridge.env.example`) |
| `core.key` | **no** | Core's subject key token. It goes into `.env` as `KUTUPHANE_LLMDAP_KEY`, and nowhere else. |

## Set up

```sh
# 1. The image: docker load the LLMDAP release tarball, or build it from the LLMDAP repo
#    (docker build -f deploy/bridge/Dockerfile -t llmdap-bridge:<gw>-llmdap<root> .)
# 2. Core's subject key (the token is printed once; the hash entry goes to keys.json)
umask 077
docker run --rm llmdap-bridge:0.28.0-llmdap1.18.0 \
  llmdap-gateway-subject-key --subject svc-kutuphane --key-id k1 > core.key 2> entry.txt
#    put the JSON entry from entry.txt into config/keys.json:
#    {"version":1,"subjects":[{"subject":"svc-kutuphane","groups":[],"keys":[<entry>]}]}
# 3. bridge.env from bridge.env.example (audit key: openssl genpkey -algorithm ed25519 | base64 -w0)
# 4. .env: KUTUPHANE_LLMDAP_KEY=<contents of core.key>, plus the route names and models below
docker compose --profile app --profile dev-models up -d
```

Core settings (`.env`):

| Setting | Dev value |
|---|---|
| `KUTUPHANE_LLMDAP_ROUTE` | `chat` |
| `KUTUPHANE_ANSWER_MODEL` | `stub-chat` |
| `KUTUPHANE_LLMDAP_EMBED_ROUTE` | `emb` |
| `KUTUPHANE_EMBED_MODEL` | `stub-embed` |
| `KUTUPHANE_LLMDAP_RERANK_ROUTE` | `rerank` |
| `KUTUPHANE_RERANK_MODEL` | `stub-rerank` |

For real models, replace `model-stub` in `config/routes.json` with the model servers on the `models` network, and set the pinned models (for example bge-m3 and bge-reranker-v2-m3, M0).

## Verify

```sh
docker compose --profile app run --rm -T --no-deps core python -I - model-stub:8000 < deploy/egress_probe.py  # AT-10
python -I deploy/llmdap_contract.py <okf dir> --chat chat stub-chat --embed emb stub-embed --rerank rerank stub-rerank \
  --audit-export "docker compose --profile app exec -T llmdap llmdap-audit-export --path /var/lib/llmdap/audit/audit.log"
```
