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
# 1. The image: docker load the signed LLMDAP release tarball, delivered under an LLMDAP agreement
#    (LLMDAP is proprietary; without an agreement use the light install, docs/guide/install.md)
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
| `KUTUPHANE_ANSWER_MODEL` | `stub-chat` | `nvidia/Qwen3.8-Flash-Next-NVFP4` |
| `KUTUPHANE_LLMDAP_EMBED_ROUTE` | `emb` | `emb` |
| `KUTUPHANE_EMBED_MODEL` | `stub-embed` | `BAAI/bge-m3` |
| `KUTUPHANE_LLMDAP_RERANK_ROUTE` | `rerank` | `rerank` |
| `KUTUPHANE_RERANK_MODEL` | `stub-rerank` | `BAAI/bge-reranker-v2-m3` |

## Local models (D61)

Nothing leaves the machine. LLMDAP reads `config/routes.local.json` (the default of `KUTUPHANE_LLMDAP_ROUTES`):

- `chat` → `spark-chat` (nginx, `deploy/spark-chat/`) → the host's vLLM on port 8000 (`nvidia/Qwen3.8-Flash-Next-NVFP4`).
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
docker compose --profile app --profile local-models up -d --build
```

Vectors are stored per model name, so an index built with `stub-embed` stays apart; run `kutuphane index <book>` to
fill in the bge-m3 vectors.

## Verify

```sh
docker compose --profile app run --rm -T --no-deps core python -I - model-stub:8000 < deploy/egress_probe.py  # AT-10
python -I deploy/llmdap_contract.py <okf dir> --chat chat stub-chat --embed emb stub-embed --rerank rerank stub-rerank \
  --audit-export "docker compose --profile app exec -T llmdap llmdap-audit-export --path /var/lib/llmdap/audit/audit.log"
# local models: --chat chat nvidia/Qwen3.8-Flash-Next-NVFP4 --embed emb BAAI/bge-m3 --rerank rerank BAAI/bge-reranker-v2-m3
#   (GPU reranker: --rerank rerank-gpu BAAI/bge-reranker-v2-m3)
```

## Contract runner for LLMDAP's CI (#243)

`deploy/llmdap_contract_ci.sh` runs the contract above in one command. It needs only Docker (with compose) and bash on the host; it brings its
own Postgres, model stub and book. LLMDAP's release CI runs it from this repository at a pinned commit.

```sh
KUTUPHANE_LLMDAP_URL=http://llmdap:8787 KUTUPHANE_LLMDAP_KEY=<token of subject svc-kutuphane> \
KUTUPHANE_VERSION=<release tag> \
  deploy/llmdap_contract_ci.sh --audit-export "docker exec <bridge> llmdap-audit-export --path /var/lib/llmdap/audit/audit.log" \
  [--image <kutuphane image>] [--export-timeout <seconds>] [--keep]
```

| Input | Meaning |
|---|---|
| `KUTUPHANE_LLMDAP_URL` | the bridge, as seen from the runner's containers (`http://llmdap:8787`) |
| `KUTUPHANE_LLMDAP_KEY` | the token of subject `svc-kutuphane` |
| `--audit-export "<cmd>"` | a command of the host that prints the verified LLMDAP chain as JSONL; the runner runs it after the calls. Exit non-zero fails the check. For a long chain see `LLMDAP_AUDIT_MAX_SCAN_BYTES` in the LLMDAP docs. |
| `--image` | the Kütüphane image that runs the contract. Default `ghcr.io/ekaynac/kutuphane:${KUTUPHANE_VERSION}`. A local build is allowed. |
| `--export-timeout <s>` | time limit of the export command, default 120. The host kills it (and its process group) at the limit; the check then fails. |
| `--keep` | do not tear down (debugging) |
| `LLMDAP_GATEWAY_TRUST_SECRET` | optional: the gateway's real shared secret, for the shared-secret check |

What it does:

1. Takes the lock: it creates (never starts) the container `kutuphane-contract-lock` from the Kütüphane image. Docker
   keeps container names unique, so a second run fails here, exits 2, and changes nothing. A lock left by a crashed run
   or by `--keep` blocks every run until you remove it: `docker rm -f kutuphane-contract-lock`.
2. Under the lock, refuses (exit 2, nothing created) if a container, volume or network of the compose project
   `kutuphane-contract` exists (a leftover, or a `--keep` run). Each of the three queries must succeed.
   Then creates the internal Docker network `kutuphane-contract` (the name the caller attaches to; the script keeps
   its id and uses the id from then on) and the compose project `kutuphane-contract` (`deploy/contract/compose.yaml`;
   never the project `kutuphane`): scratch `pgvector/pgvector:0.8.0-pg17` (no host port, no volume) and `model-stub`
   (`deploy/model_stub.py`, port 8000). Every container carries the label `kutuphane.contract.run=<run id>` of this run.
3. Waits up to 60 s for the bridge. The caller attaches its bridge container to the network with the alias `llmdap`,
   before or after the start: `docker network connect --alias llmdap kutuphane-contract <bridge>`.
4. Phase 1: runs `deploy/llmdap_contract.py --phase calls` in the Kütüphane image against the book
   `deploy/contract/book`, with `--chat chat stub-chat --embed emb stub-embed --rerank rerank stub-rerank`: every model
   call and the authentication checks.
5. Runs the `--audit-export` command on the host, with stdout in a file of a private directory (`mktemp -d`, mode 0700)
   that no container can write to. The command runs in its own process group with the time limit `--export-timeout`
   (TERM, then KILL, to the group); at the limit the check fails.
6. Phase 2: `--phase verify --audit-export-file /export/export.jsonl --audit-export-status <exit status of the export>`,
   with that directory mounted **read-only**: the audit checks (chain, AT-09, one authenticated subject) against the
   database rows of phase 1.
7. Prints one line per check on stdout (`PASS`/`FAIL`, both phases), then a JSON summary line. Exit codes:

   | Exit | Meaning |
   |---|---|
   | 0 | every check passed and the teardown succeeded |
   | 1 | a check failed (this includes an export command that failed or ran past `--export-timeout`) |
   | 2 | wrong call, the lock is held, a leftover or running `kutuphane-contract` project or network (nothing is created), or the bridge did not answer within 60 s |
   | 3 | every check passed, but a teardown step failed; each failed step is named on stderr (an earlier failure code is kept) |
   | 125 | a process of the export command could not be ended (TERM, then KILL, to its group): the verify phase did not run. (An export command that itself exits 125 is an ordinary failure: verify runs with that status, exit 1.) |

8. Removes what this run created, always (unless `--keep`): the containers and volumes with its run id (only ids of a
   successful listing), the bridge it finds on its network by the alias `llmdap` (detached by container and network
   id), the network by id, the private directory, and last the lock, by id. Then it checks that nothing of the run is
   left. Every failed query or step is a failed teardown (exit 3). A process of the export command that survived is
   killed again here.

The host needs Docker with the compose plugin, and bash. The contract container has no writable host mount.
`llmdap_contract.py` without `--phase` works as before (one process, `--audit-export "<cmd>"`).

The bridge routes are fixed (the same as `config/routes.json`):

| Route | `baseUrl` | `pinnedModel` | Surface |
|---|---|---|---|
| `chat` | `http://model-stub:8000` | `stub-chat` | chat |
| `emb` | `http://model-stub:8000` | `stub-embed` | `embeddings` |
| `rerank` | `http://model-stub:8000` | `stub-rerank` | `rerank` |

`GATEWAY_ALLOWED_HOSTS` must include `llmdap`, and the subject `svc-kutuphane` needs `llm:invoke` on the three routes.
A change to the inputs, the network name, the route table or the exit codes is announced on issue #243 before it merges.
