"""Development stand-in for the model servers behind LLMDAP (compose profile `dev-models`). Standard library only.

It serves the three openai-compatible APIs that the LLMDAP routes use, with deterministic answers:
- `/v1/chat/completions`: a fixed reply that cites passage [1];
- `/v1/embeddings`: hashed word counts (64 dimensions);
- `/v1/rerank`: the share of query words found in each document.

It echoes the requested `model`, so the LLMDAP pin check passes. It never stands in for a real model in measurements.
"""
import hashlib
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

DIMS = 64
REPLY = os.environ.get("STUB_REPLY", "Kayıtlar iki yıl saklanır [1].")


def words(text: str) -> list[str]:
    return [w.strip(".,:;?!()") for w in text.casefold().split()]


def vector(text: str) -> list[float]:
    v = [0.0] * DIMS
    for w in words(text):
        v[int(hashlib.sha256(w.encode()).hexdigest(), 16) % DIMS] += 1.0
    v[0] += 1e-3  # never a zero vector
    return v


def answer(path: str, body: dict) -> dict | None:
    model = body.get("model")
    if path == "/v1/chat/completions":
        return {"id": "stub", "object": "chat.completion", "model": model,
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
                "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": REPLY}}]}
    if path == "/v1/embeddings":
        texts = body["input"] if isinstance(body["input"], list) else [body["input"]]
        return {"object": "list", "model": model, "usage": {"prompt_tokens": 1, "total_tokens": 1},
                "data": [{"object": "embedding", "index": i, "embedding": vector(t)} for i, t in enumerate(texts)]}
    if path == "/v1/rerank":
        q = set(words(body["query"]))
        return {"model": model, "usage": {"total_tokens": 1},
                "results": [{"index": i, "relevance_score": len(q & set(words(d))) / max(len(q), 1)}
                            for i, d in enumerate(body["documents"])]}
    return None


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        try:
            out = answer(self.path, json.loads(self.rfile.read(int(self.headers.get("content-length") or 0))))
        except (ValueError, KeyError, TypeError):
            out = None
        data = json.dumps(out or {"error": "not found or bad request"}).encode()
        self.send_response(200 if out else 400)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8000), Handler).serve_forever()
