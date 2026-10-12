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
import ipaddress
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
TAILNET = ipaddress.ip_network("100.64.0.0/10")

sys.path.insert(0, str(HERE))  # -I drops the script dir
from secret_scan import find_secret  # noqa: E402


class Store:
    def __init__(self, data_dir: Path):
        self.data = data_dir
        self.taxonomy = json.loads((HERE / "taxonomy.json").read_text())
        self.manifest = {m["id"]: m for m in json.loads((data_dir / "manifest.json").read_text())["docs"]}
        self.docs = {d["id"]: d for d in json.loads((data_dir / "docs.json").read_text())}
        order = sorted(self.manifest)
        random.Random(ORDER_SEED).shuffle(order)
        self.order = order
        self.excluded = self._scan()
        self.labels_path = data_dir / "labels.jsonl"
        self.lock = Lock()

    def _scan(self) -> dict:
        """Fail closed: a source that changed since selection or trips the secret scan is not served."""
        out, seen = {}, set()
        for doc_id, m in sorted(self.manifest.items()):
            if m["sha256"] in seen:
                out[doc_id] = "duplicate"  # byte-identical copy of an earlier doc
                continue
            seen.add(m["sha256"])
            try:
                raw = Path(m["path"]).read_bytes()
            except OSError:
                out[doc_id] = "unreadable"
                continue
            if hashlib.sha256(raw).hexdigest() != m["sha256"]:
                out[doc_id] = "changed"
            elif find_secret(raw.decode("utf-8", errors="replace")):
                out[doc_id] = "secret"
        reasons = sorted(set(out.values()))
        print(f"excluded {len(out)} docs: " + ", ".join(f"{r}={list(out.values()).count(r)}" for r in reasons), file=sys.stderr)
        return out

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
            if doc_id in self.excluded:
                continue
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
        if not m or doc_id in self.excluded:
            return None
        raw = Path(m["path"]).read_bytes()
        if hashlib.sha256(raw).hexdigest() != m["sha256"]:
            return None  # changed after the secret scan: never serve unscanned content
        return {"id": doc_id, "text": raw.decode("utf-8", errors="replace")}

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
            if not (isinstance(item_id, str) and DOC_ID.match(item_id) and item_id in self.manifest
                    and item_id not in self.excluded):
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
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(secrets.token_urlsafe(18))
    if path.stat().st_mode & 0o077:
        raise SystemExit(f"{path} must be private (chmod 600)")
    return path.read_text().strip()


def check_host(host: str, allow_any: bool) -> None:
    """Plain HTTP: only loopback or the WireGuard-encrypted tailnet unless explicitly allowed."""
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        raise SystemExit("--host must be an IP address")
    if not (ip.is_loopback or ip in TAILNET or allow_any):
        raise SystemExit(f"refusing {host}: plain HTTP outside loopback/tailnet; pass --allow-any-interface to override")


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
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--allow-any-interface", action="store_true")
    ap.add_argument("--port", type=int, default=8790)
    ap.add_argument("--data", default=str(HERE / "data"))
    args = ap.parse_args()
    check_host(args.host, args.allow_any_interface)
    os.umask(0o077)
    data_dir = Path(args.data)
    store = Store(data_dir)
    token = load_token(data_dir)
    page = (HERE / "page.html").read_bytes()
    httpd = ThreadingHTTPServer((args.host, args.port), make_handler(store, token, page))
    print(f"listening on {args.host}:{args.port} (token in {data_dir / 'token'})", file=sys.stderr)
    httpd.serve_forever()


if __name__ == "__main__":
    main()
