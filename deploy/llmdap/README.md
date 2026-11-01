# LLMDAP in the Kütüphane compose (D52, AT-09/10/11)

LLMDAP's bridge-only image (`llmdap-bridge`, LLMDAP #237) is the only way to the model servers. It runs on the
`gateway` network (to Core) and the `models` network (to the model servers). Neither network has a route out.

## Files

| File | In git | Content |
|---|---|---|
| `config/routes.json` | yes | bridge routes: `chat`, `emb` (embeddings), `rerank`. The dev routes point to `model-stub`. |
| `config/routes.local.json` | yes | the same routes on real local models (profile `local-models` of `deploy/compose.full.yaml`, D61), plus `rerank-gpu` |
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
# 4. .env: COMPOSE_FILE=deploy/compose.full.yaml, KUTUPHANE_LLMDAP_KEY=<contents of core.key>, plus the dev values
#    below (the defaults of deploy/compose.full.yaml are the local models)
docker compose --profile app --profile dev-models up -d
```

Settings (`.env`):

| Setting | Dev value | Local models (the compose default) |
|---|---|---|
| `KUTUPHANE_LLMDAP_ROUTES` (LLMDAP's routes file) | `routes.json` | `routes.local.json` |
| `KUTUPHANE_LLMDAP_ROUTE` | `chat` | `chat` |
| `KUTUPHANE_ANSWER_MODEL` | `stub-chat` | `RadixArk/Qwen3.8-27B-NVFP4` |
| `KUTUPHANE_LLMDAP_EMBED_ROUTE` | `emb` | `emb` |
| `KUTUPHANE_EMBED_MODEL` | `stub-embed` | `BAAI/bge-m3` |
| `KUTUPHANE_LLMDAP_RERANK_ROUTE` | `rerank` | `rerank` |
| `KUTUPHANE_RERANK_MODEL` | `stub-rerank` | `BAAI/bge-reranker-v2-m3` |

## Local models (D61)

Nothing leaves the machine. LLMDAP reads `config/routes.local.json` (the default of `KUTUPHANE_LLMDAP_ROUTES`):

- `chat` → `spark-chat` (nginx, `deploy/spark-chat/`) → the host's vLLM on port 8000 (`RadixArk/Qwen3.8-27B-NVFP4`).
  The proxy forwards only `POST /v1/chat/completions` and forces `chat_template_kwargs.enable_thinking=false`
  (Qwen3.8 otherwise spends tokens on a `reasoning` field). It is the only model service with a non-internal network.
- `emb` (1024 dimensions) and `rerank` → `embedder` (`deploy/models/`): bge-m3 and bge-reranker-v2-m3 on CPU,
  8 threads, offline, read-only, at the Hub commits pinned in `deploy/models/server.py` (`GET /health` reports them).
- `rerank-gpu` → `reranker-gpu` (profile `gpu-rerank`): the same bge-reranker-v2-m3 commit on the GPU, served by the
  host vLLM's own image (`vllm-node:latest`) with 0.04 of the GPU memory. vLLM's `/v1/rerank` answer has the same
  `results[].index` and `relevance_score` (0..1) as the embedder, plus `document` and `id`, which LLMDAP's rerank check
  allows; no adapter is needed. Core uses it when `KUTUPHANE_LLMDAP_RERANK_ROUTE=rerank-gpu`; `rerank` stays the CPU
  fallback (`docs/guide/install.md`, "GPU reranker").

LLMDAP's digest gate (`digestSource` + `approvedDigests`) exists only for the systemone and ollama schemas, so these
openai routes pin the model *name*; the embedder and `reranker-gpu` pin the weights themselves (each loads only the
pinned commit: the embedder by revision, `reranker-gpu` by the snapshot path of that commit).

```sh
# once: the pinned weights into the Hugging Face cache (a throwaway venv with huggingface_hub); the files are the
# FILES list in deploy/models/server.py, and the container user (uid 65532) must be able to read them
python -c 'from huggingface_hub import snapshot_download as d
p = ["config.json", "pytorch_model.bin", "model.safetensors", "tokenizer.json", "tokenizer_config.json",
     "sentencepiece.bpe.model", "special_tokens_map.json"]
d("BAAI/bge-m3", revision="5617a9f61b028005a4858fdac845db406aefb181", allow_patterns=p)
d("BAAI/bge-reranker-v2-m3", revision="953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e", allow_patterns=p)'
chmod -R a+rX ~/.cache/huggingface/hub/models--BAAI--bge-m3 ~/.cache/huggingface/hub/models--BAAI--bge-reranker-v2-m3
docker compose --profile app --profile decision-models --profile local-models up -d --build
```

Vectors are stored per model name, so an index built with `stub-embed` stays apart; run `kutuphane index <book>` to
fill in the bge-m3 vectors.

## Verify

```sh
docker compose --profile app run --rm -T --no-deps core python -I - model-stub:8000 < deploy/egress_probe.py  # AT-10
python -I deploy/llmdap_contract.py <okf dir> --chat chat stub-chat --embed emb stub-embed --rerank rerank stub-rerank \
  --audit-export "docker compose --profile app exec -T llmdap llmdap-audit-export --path /var/lib/llmdap/audit/audit.log"
# local models: --chat chat RadixArk/Qwen3.8-27B-NVFP4 --embed emb BAAI/bge-m3 --rerank rerank BAAI/bge-reranker-v2-m3
#   (GPU reranker: --rerank rerank-gpu BAAI/bge-reranker-v2-m3)
```
