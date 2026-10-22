"""Local CPU model server behind the LLMDAP routes `emb` and `rerank` (compose profile `local-models`, D61).

It serves the same openai-compatible shapes as `deploy/model_stub.py`, with real open-weights models:
- `/v1/embeddings`: BAAI/bge-m3 dense vectors (CLS pooling, L2-normalised, 1024 dimensions);
- `/v1/rerank`: BAAI/bge-reranker-v2-m3 cross-encoder scores (sigmoid of the logit, 0..1), best first;
- `/health`: the Hub commit SHA of every loaded model.

Both models load only from the pinned commit in the read-only Hugging Face cache; the container has no network out.
One forward pass runs at a time (the CPU threads are the limit, not the request count).
"""
import json
import logging
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import torch
from huggingface_hub import snapshot_download
from transformers import AutoModel, AutoModelForSequenceClassification, AutoTokenizer

EMBED, RERANK = "BAAI/bge-m3", "BAAI/bge-reranker-v2-m3"
PINNED = {  # reviewed Hub commits; another revision needs a code change, never an environment variable
    EMBED: "5617a9f61b028005a4858fdac845db406aefb181",
    RERANK: "953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e",
}
# The files the server needs (the rest of each repo, e.g. bge-m3's ONNX export, is never downloaded).
FILES = ["config.json", "pytorch_model.bin", "model.safetensors", "tokenizer.json", "tokenizer_config.json",
         "sentencepiece.bpe.model", "special_tokens_map.json"]
THREADS = int(os.environ.get("MODELS_THREADS", "8"))
EMBED_MAX_TOKENS = int(os.environ.get("EMBED_MAX_TOKENS", "8192"))
RERANK_MAX_TOKENS = int(os.environ.get("RERANK_MAX_TOKENS", "1024"))
MAX_BODY = 8 * 1024 * 1024  # LLMDAP's default maxRequestBytes
MAX_ITEMS = 1000            # texts per embeddings request, documents per rerank request
MICRO_BATCH = 16            # texts per forward pass, sorted by length so padding stays small

log = logging.getLogger("models")


class BadRequest(ValueError):
    pass


def load(repo: str, cls):
    # Fails unless every needed file of the pinned commit is in the cache.
    path = snapshot_download(repo, revision=PINNED[repo], allow_patterns=FILES, local_files_only=True)
    return AutoTokenizer.from_pretrained(path), cls.from_pretrained(path, dtype=torch.float32).eval()


def batches(texts: list[str]):
    """(original indexes, texts) in micro-batches of similar length."""
    order = sorted(range(len(texts)), key=lambda i: len(texts[i]))
    for start in range(0, len(order), MICRO_BATCH):
        idx = order[start:start + MICRO_BATCH]
        yield idx, [texts[i] for i in idx]


class Models:
    def __init__(self):
        torch.set_num_threads(THREADS)
        self.lock = threading.Lock()
        self.embed_tok, self.embed_model = load(EMBED, AutoModel)
        self.rerank_tok, self.rerank_model = load(RERANK, AutoModelForSequenceClassification)

    @torch.inference_mode()
    def embed(self, texts: list[str]) -> tuple[list[list[float]], int]:
        out: list[list[float] | None] = [None] * len(texts)
        tokens = 0
        with self.lock:
            for idx, chunk in batches(texts):
                enc = self.embed_tok(chunk, padding=True, truncation=True, max_length=EMBED_MAX_TOKENS,
                                     return_tensors="pt")
                cls = self.embed_model(**enc).last_hidden_state[:, 0]
                vecs = torch.nn.functional.normalize(cls, dim=-1)
                tokens += int(enc["attention_mask"].sum())
                for i, v in zip(idx, vecs.tolist()):
                    out[i] = v
        return out, tokens

    @torch.inference_mode()
    def rerank(self, query: str, documents: list[str]) -> tuple[list[float], int]:
        out: list[float] = [0.0] * len(documents)
        tokens = 0
        with self.lock:
            for idx, chunk in batches(documents):
                enc = self.rerank_tok([query] * len(chunk), chunk, padding=True, truncation=True,
                                      max_length=RERANK_MAX_TOKENS, return_tensors="pt")
                scores = torch.sigmoid(self.rerank_model(**enc).logits.view(-1).float())
                tokens += int(enc["attention_mask"].sum())
                for i, s in zip(idx, scores.tolist()):
                    out[i] = s
        return out, tokens


def _model(body: dict, served: str) -> None:
    if body.get("model") != served:
        raise BadRequest(f"this endpoint serves only {served}")


def _texts(value, field: str) -> list[str]:
    items = [value] if isinstance(value, str) else value
    if not isinstance(items, list) or not items or len(items) > MAX_ITEMS or \
            not all(isinstance(t, str) for t in items):
        raise BadRequest(f"{field} must be a string or 1..{MAX_ITEMS} strings")
    return items


def answer(models: Models, path: str, body) -> dict:
    if not isinstance(body, dict):
        raise BadRequest("body must be a JSON object")
    if path == "/v1/embeddings":
        _model(body, EMBED)
        vectors, tokens = models.embed(_texts(body.get("input"), "input"))
        return {"object": "list", "model": EMBED, "usage": {"prompt_tokens": tokens, "total_tokens": tokens},
                "data": [{"object": "embedding", "index": i, "embedding": v} for i, v in enumerate(vectors)]}
    if path == "/v1/rerank":
        _model(body, RERANK)
        query, documents, top_n = body.get("query"), _texts(body.get("documents"), "documents"), body.get("top_n")
        if not isinstance(query, str):
            raise BadRequest("query must be a string")
        if top_n is not None and (type(top_n) is not int or top_n < 1):
            raise BadRequest("top_n must be a positive integer")
        scores, tokens = models.rerank(query, documents)
        ranked = sorted(range(len(scores)), key=lambda i: -scores[i])[:top_n or len(scores)]
        return {"model": RERANK, "usage": {"total_tokens": tokens},
                "results": [{"index": i, "relevance_score": scores[i]} for i in ranked]}
    raise BadRequest(f"unknown path {path}")


def handler(models: Models):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def send(self, status: int, out: dict) -> None:
            data = json.dumps(out).encode()
            self.send_response(status)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if self.path != "/health":
                return self.send(404, {"error": "not found"})
            self.send(200, {"status": "ok", "revisions": PINNED, "threads": torch.get_num_threads()})

        def do_POST(self):
            if self.path not in ("/v1/embeddings", "/v1/rerank"):
                return self.send(404, {"error": "not found"})
            try:
                length = int(self.headers.get("content-length") or 0)
                if length > MAX_BODY:
                    return self.send(413, {"error": "request too large"})
                body = json.loads(self.rfile.read(length))
            except ValueError:
                return self.send(400, {"error": "invalid JSON or content-length"})
            try:
                self.send(200, answer(models, self.path, body))
            except BadRequest as exc:
                self.send(400, {"error": str(exc)})
            except Exception:  # noqa: BLE001 — never a traceback to the caller; the log has it
                log.exception("inference failed")
                self.send(500, {"error": "inference failed"})

    return Handler


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    models = Models()
    log.info("loaded %s", ", ".join(f"{m}@{r}" for m, r in PINNED.items()))
    ThreadingHTTPServer(("0.0.0.0", 8000), handler(models)).serve_forever()
