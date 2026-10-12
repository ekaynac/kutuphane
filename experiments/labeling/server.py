"""Local labelling server (D43/D44): content never leaves the host.

Usage: python3 -I server.py [--host 0.0.0.0] [--port 8790] [--data DIR]

Access: open http://<host>:<port>/?t=<token> once; the token (data/token, created on first
run, mode 600) is exchanged for a cookie. Labels are appended to data/labels.jsonl.
Drafts (data/drafts/*.json) are shown only for non-blind items; Laya shadow predictions
are never served.
"""
import argparse
import hashlib
import hmac
import json
import os
import random
import re
import secrets
import sys
import time
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock
from urllib.parse import parse_qs, urlparse

HERE = Path(__file__).resolve().parent
COOKIE = "kutuphane_label"
COOKIE_MAX_AGE = 30 * 24 * 3600
MAX_BODY = 16 * 1024
MAX_NOTE = 500
ORDER_SEED = 20261012
DOC_ID = re.compile(r"^d\d{3}$")


class Store:
    def __init__(self, data_dir: Path):
        self.data = data_dir
        self.taxonomy = json.loads((HERE / "taxonomy.json").read_text())
        self.manifest = {m["id"]: m for m in json.loads((data_dir / "manifest.json").read_text())["docs"]}
        self.docs = {d["id"]: d for d in json.loads((data_dir / "docs.json").read_text())}
        order = sorted(self.manifest)
        random.Random(ORDER_SEED).shuffle(order)
        self.order = order
        self.labels_path = data_dir / "labels.jsonl"
        self.lock = Lock()

    def drafts(self) -> dict:
        out = {}
        for f in sorted((self.data / "drafts").glob("batch-*.json")):
            try:
                for item in json.loads(f.read_text()):
                    out[item["id"]] = item
            except (json.JSONDecodeError, KeyError, TypeError) as exc:
                print(f"skipping unreadable drafts {f.name}: {exc}", file=sys.stderr)
        return out

    def items(self) -> dict:
        drafts = self.drafts()
        docs, qa = [], []
        for doc_id in self.order:
            d, m = self.docs[doc_id], self.manifest[doc_id]
            draft = drafts.get(doc_id)
            shown = None
            if draft and not m["blind"]:
                shown = {k: draft.get(k) for k in ("category", "category_alt", "sensitivity", "egress", "rationale")}
            docs.append({"id": doc_id, "path": d["path"], "group": d["group"], "chars": d["chars"],
                         "excerpt": d["excerpt"], "blind": m["blind"], "draft": shown})
            for i, q in enumerate((draft or {}).get("questions") or []):
                qa.append({"id": f"q-{doc_id}-{i}", "doc": doc_id, "path": d["path"],
                           "question": q.get("q", ""), "passage": q.get("passage", "")})
        return {"taxonomy": self.taxonomy, "docs": docs, "qa": qa}

    def full_text(self, doc_id: str):
        m = self.manifest.get(doc_id)
        if not m:
            return None
        raw = Path(m["path"]).read_bytes()
        changed = hashlib.sha256(raw).hexdigest() != m["sha256"]
        return {"id": doc_id, "text": raw.decode("utf-8", errors="replace"), "changed_since_manifest": changed}

    def latest(self) -> dict:
        out = {}
        if self.labels_path.exists():
            for line in self.labels_path.read_text().splitlines():
                if line.strip():
                    rec = json.loads(line)
                    out[rec["id"]] = rec
        return out

    def validate(self, body: dict) -> dict:
        task, item_id, values = body.get("task"), body.get("id"), body.get("values")
        if not isinstance(values, dict):
            raise ValueError("values must be an object")
        note = body.get("note") or ""
        if not isinstance(note, str) or len(note) > MAX_NOTE:
            raise ValueError("note too long")
        ms = body.get("ms")
        ms = int(ms) if isinstance(ms, (int, float)) and 0 <= ms < 86_400_000 else None
        if task == "doc":
            if not (isinstance(item_id, str) and DOC_ID.match(item_id) and item_id in self.manifest):
                raise ValueError("unknown doc id")
            clean = {}
            for q, spec in self.taxonomy["questions"].items():
                v = values.get(q)
                if v is not None and v not in spec["options"]:
                    raise ValueError(f"invalid {q}")
                clean[q] = v
            if body.get("skip") is not True and None in clean.values():
                raise ValueError("all three answers are required (or skip)")
            m = self.manifest[item_id]
            shown_draft = (not m["blind"]) and body.get("draft_shown") is True
            return {"task": task, "id": item_id, "values": clean, "skip": body.get("skip") is True,
                    "blind": m["blind"], "shown_draft": shown_draft, "note": note, "ms": ms}
        if task == "qa":
            valid_ids = {q["id"] for q in self.items()["qa"]}
            if item_id not in valid_ids:
                raise ValueError("unknown question id")
            rel = values.get("relevance")
            if rel not in self.taxonomy["relevance"]["options"]:
                raise ValueError("invalid relevance")
            return {"task": task, "id": item_id, "values": {"relevance": rel}, "note": note, "ms": ms}
        raise ValueError("unknown task")

    def append(self, rec: dict) -> None:
        rec = {**rec, "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
        with self.lock, self.labels_path.open("a") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def load_token(data_dir: Path) -> str:
    path = data_dir / "token"
    if not path.exists():
        path.write_text(secrets.token_urlsafe(18))
        path.chmod(0o600)
    return path.read_text().strip()


def make_handler(store: Store, token: str, page: bytes):
    class Handler(BaseHTTPRequestHandler):
        server_version = "kutuphane-label/1"

        def log_message(self, fmt, *args):  # keep tokens and paths out of logs
            sys.stderr.write(f"{self.log_date_time_string()} {self.command} {urlparse(self.path).path} -> {args[1] if len(args) > 1 else ''}\n")

        def authed(self) -> bool:
            jar = SimpleCookie(self.headers.get("Cookie", ""))
            got = jar[COOKIE].value if COOKIE in jar else ""
            return hmac.compare_digest(got, token)

        def send(self, status, body: bytes, ctype="application/json; charset=utf-8", extra=None):
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def json(self, status, obj):
            self.send(status, json.dumps(obj, ensure_ascii=False).encode())

        def do_GET(self):
            url = urlparse(self.path)
            if url.path == "/":
                t = parse_qs(url.query).get("t", [""])[0]
                if t and hmac.compare_digest(t, token):
                    cookie = f"{COOKIE}={token}; Max-Age={COOKIE_MAX_AGE}; Path=/; HttpOnly; SameSite=Strict"
                    return self.send(HTTPStatus.SEE_OTHER, b"", "text/plain", {"Set-Cookie": cookie, "Location": "/"})
                if not self.authed():
                    return self.send(HTTPStatus.UNAUTHORIZED, "Erişim bağlantısını (…/?t=…) kullanın.".encode(), "text/plain; charset=utf-8")
                return self.send(HTTPStatus.OK, page, "text/html; charset=utf-8")
            if not self.authed():
                return self.json(HTTPStatus.UNAUTHORIZED, {"error": "unauthorized"})
            if url.path == "/api/items":
                return self.json(HTTPStatus.OK, store.items())
            if url.path == "/api/state":
                return self.json(HTTPStatus.OK, store.latest())
            if url.path.startswith("/api/doc/"):
                doc = store.full_text(url.path.rsplit("/", 1)[-1])
                return self.json(HTTPStatus.OK, doc) if doc else self.json(HTTPStatus.NOT_FOUND, {"error": "not found"})
            return self.json(HTTPStatus.NOT_FOUND, {"error": "not found"})

        def do_POST(self):
            if urlparse(self.path).path != "/api/label":
                return self.json(HTTPStatus.NOT_FOUND, {"error": "not found"})
            if not self.authed():
                return self.json(HTTPStatus.UNAUTHORIZED, {"error": "unauthorized"})
            length = int(self.headers.get("Content-Length") or 0)
            if length <= 0 or length > MAX_BODY:
                return self.json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": "body size"})
            try:
                rec = store.validate(json.loads(self.rfile.read(length)))
            except (ValueError, json.JSONDecodeError) as exc:
                return self.json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            store.append(rec)
            return self.json(HTTPStatus.OK, {"ok": True})

    return Handler


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8790)
    ap.add_argument("--data", default=str(HERE / "data"))
    args = ap.parse_args()
    data_dir = Path(args.data)
    store = Store(data_dir)
    token = load_token(data_dir)
    page = (HERE / "page.html").read_bytes()
    httpd = ThreadingHTTPServer((args.host, args.port), make_handler(store, token, page))
    print(f"listening on {args.host}:{args.port} (token in {data_dir / 'token'})", file=sys.stderr)
    os.umask(0o077)
    httpd.serve_forever()


if __name__ == "__main__":
    main()
