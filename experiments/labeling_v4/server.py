"""Labelling v4 page server (docs/16 §4). It shows the dataset items in batches of 20, with the raw bytes (hidden
characters made visible) and the rule proposals, and appends each label to <data>/labels.jsonl.

    python -I server.py --data <research/labelling-v4> --host <tailnet-ip> --port 8791
    open http://<ip>:8791/?t=<data/token>     (the token is made on the first run, mode 600)

Plain HTTP only on loopback or the tailnet; the access token is exchanged for an HttpOnly cookie.
"""
import argparse
import hmac
import ipaddress
import json
import os
import re
import secrets
import sys
import time
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

HERE = Path(__file__).resolve().parent
TAILNET = ipaddress.ip_network("100.64.0.0/10")
COOKIE, COOKIE_MAX_AGE = "kl4", 30 * 86400
MAX_BODY, MAX_TEXT, BATCH = 64 * 1024, 200_000, 20
STRATA = ("R", "S", "W", "A")  # labelling order (docs/16 §4)
HIDDEN = re.compile("[\u200b\u200c\u200d\u2060\ufeff\u202a-\u202e\u2066-\u2069\u00ad]")

ORIGIN = ("human", "assisted", "model", "tool", "unknown")  # `tool`: docs/17, not decided yet
CHOICES = {
    "origin": ORIGIN,
    "personal_data": ("yes", "no", "synthetic", "unknown"),
    "acceptance": ("pending", "accepted", "withdrawn", "suspended"),
    "mandate": ("no", "yes"),
    "export": ("", "normal", "restricted"),
    "route": ("", "cloud_ok", "local_only"),
    "instruction": ("no", "yes"),
    "activate": ("n/a", "allow", "deny", "escalate"),
    "needs_split": ("no", "yes"),
    "issuer_trusted": ("unknown", "yes", "no"),
}
AI_USE = ("search", "ai_input", "train")
TEXT_FIELDS = {"reviewed_by": 200, "license_item": 300, "applies_to": 300, "issued": 10, "valid_from": 10,
               "valid_to": 10, "inputs": 2000, "software_agent": 200, "note": 2000}
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class Store:
    def __init__(self, root: Path):
        self.root = root
        self.items = {}
        for s in STRATA:
            f = root / "items" / f"{s}.jsonl"
            for line in f.read_text().splitlines() if f.exists() else []:
                if line.strip():
                    it = json.loads(line)
                    self.items[it["id"]] = it
        prop = root / "proposals.jsonl"
        self.proposals = {json.loads(l)["id"]: json.loads(l)["proposals"]
                          for l in (prop.read_text().splitlines() if prop.exists() else []) if l.strip()}
        self.labels_path = root / "labels.jsonl"
        self.groups = {}
        for it in self.items.values():
            if it.get("group"):
                self.groups.setdefault(it["group"], []).append(it["id"])

    def labelled(self) -> dict:
        out = {}
        if self.labels_path.exists():
            for line in self.labels_path.read_text().splitlines():
                if line.strip():
                    rec = json.loads(line)
                    out[rec["id"]] = rec
        return out

    def state(self) -> dict:
        done = self.labelled()
        return {s: {"total": sum(1 for i in self.items.values() if i["stratum"] == s),
                    "done": sum(1 for i in self.items.values() if i["stratum"] == s and i["id"] in done)}
                for s in STRATA}

    def batch(self, stratum: str) -> list:
        done = self.labelled()
        todo = [i for i in self.items.values() if i["stratum"] == stratum and i["id"] not in done]
        return [i["id"] for i in sorted(todo, key=lambda i: (i.get("group") or "", i["id"]))[:BATCH]]

    def item(self, iid: str) -> dict | None:
        it = self.items.get(iid)
        if it is None:
            return None
        text, hidden = None, 0
        if it.get("local_path"):
            data = (self.root / it["local_path"]).read_bytes()
            if b"\0" not in data[:8192]:
                raw = data[:MAX_TEXT].decode("utf-8", "replace")
                hidden = len(HIDDEN.findall(raw))
                text = HIDDEN.sub(lambda m: f"⟦U+{ord(m.group(0)):04X}⟧", raw)
        siblings = [s for s in self.groups.get(it.get("group"), []) if s != iid]
        blind = it["stratum"] == "S"  # the synthetic notes, facts and hostile flag are the answers
        shown = {k: v for k, v in it.items() if not (blind and k in ("known", "notes", "hostile", "known_source"))}
        return {"item": shown,
                "text": text, "hidden_chars": hidden, "truncated": bool(it.get("bytes", 0) > MAX_TEXT),
                "proposals": self.proposals.get(iid, {}), "siblings": siblings,
                "label": self.labelled().get(iid)}

    def validate(self, body: dict) -> dict:
        iid = body.get("id")
        if iid not in self.items:
            raise ValueError("unknown item")
        labels = body.get("labels")
        if not isinstance(labels, dict):
            raise ValueError("labels must be an object")
        rec = {}
        for field, options in CHOICES.items():
            value = labels.get(field, options[0])
            if value not in options:
                raise ValueError(f"{field}: not one of {options}")
            rec[field] = value
        ai_use = labels.get("ai_use") or {}
        if not isinstance(ai_use, dict) or any(k not in AI_USE or v not in ("y", "n") for k, v in ai_use.items()):
            raise ValueError("ai_use: only search/ai_input/train with y or n; leave a term out for 'not stated'")
        rec["ai_use"] = ai_use
        for field, limit in TEXT_FIELDS.items():
            value = labels.get(field, "")
            if not isinstance(value, str) or len(value) > limit:
                raise ValueError(f"{field}: text up to {limit} characters")
            if field in ("issued", "valid_from", "valid_to") and value and not DATE.match(value):
                raise ValueError(f"{field}: YYYY-MM-DD")
            rec[field] = value.strip()
        if rec["origin"] == "assisted" and not rec["reviewed_by"]:
            raise ValueError("assisted needs reviewed_by (a named person who reviewed it in substance)")
        if rec["origin"] == "tool" and not rec["software_agent"]:
            raise ValueError("tool needs software_agent (name and version)")
        accepted = body.get("accepted_proposals", [])
        if not isinstance(accepted, list) or not all(isinstance(a, str) for a in accepted):
            raise ValueError("accepted_proposals must be a list of field names")
        ms = body.get("ms")
        return {"id": iid, "stratum": self.items[iid]["stratum"], "labels": rec, "claim_source": "person",
                "accepted_proposals": sorted(set(accepted))[:40],
                "ms": int(ms) if isinstance(ms, (int, float)) and 0 <= ms < 86_400_000 else None,
                "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z")}

    def append(self, rec: dict) -> None:
        with self.labels_path.open("a") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def load_token(root: Path) -> str:
    path = root / "token"
    if not path.exists():
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(secrets.token_urlsafe(18))
    if path.stat().st_mode & 0o077:
        raise SystemExit(f"{path} must be private (chmod 600)")
    return path.read_text().strip()


def check_host(host: str, allow_any: bool) -> None:
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        raise SystemExit("--host must be an IP address")
    if not (ip.is_loopback or ip in TAILNET or allow_any):
        raise SystemExit(f"refusing {host}: plain HTTP outside loopback/tailnet")


def make_handler(store: Store, token: str, page: bytes):
    class Handler(BaseHTTPRequestHandler):
        server_version = "kutuphane-label/4"

        def log_message(self, fmt, *args):  # no tokens or query strings in logs
            sys.stderr.write(f"{self.log_date_time_string()} {self.command} {urlparse(self.path).path} -> {args[1] if len(args) > 1 else ''}\n")

        def authed(self) -> bool:
            jar = SimpleCookie(self.headers.get("Cookie", ""))
            return hmac.compare_digest(jar[COOKIE].value if COOKIE in jar else "", token)

        def send(self, status, body: bytes, ctype="application/json; charset=utf-8", extra=None):
            self.send_response(status)
            for k, v in {"Content-Type": ctype, "Content-Length": str(len(body)), "Cache-Control": "no-store",
                         "X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer",
                         "Content-Security-Policy": "default-src 'none'; script-src 'unsafe-inline'; "
                                                    "style-src 'unsafe-inline'; connect-src 'self'",
                         **(extra or {})}.items():
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
                    return self.send(HTTPStatus.UNAUTHORIZED, b"Use the access link (.../?t=...).", "text/plain")
                return self.send(HTTPStatus.OK, page, "text/html; charset=utf-8")
            if not self.authed():
                return self.json(HTTPStatus.UNAUTHORIZED, {"error": "unauthorized"})
            if url.path == "/api/state":
                return self.json(HTTPStatus.OK, {"strata": store.state(), "choices": CHOICES})
            if url.path == "/api/batch":
                s = parse_qs(url.query).get("stratum", ["R"])[0]
                return self.json(HTTPStatus.OK, {"ids": store.batch(s)}) if s in STRATA else \
                    self.json(HTTPStatus.BAD_REQUEST, {"error": "stratum"})
            if url.path.startswith("/api/item/"):
                got = store.item(url.path[len("/api/item/"):])
                return self.json(HTTPStatus.OK, got) if got else self.json(HTTPStatus.NOT_FOUND, {"error": "not found"})
            return self.json(HTTPStatus.NOT_FOUND, {"error": "not found"})

        def do_POST(self):
            if urlparse(self.path).path != "/api/label":
                return self.json(HTTPStatus.NOT_FOUND, {"error": "not found"})
            if not self.authed():
                return self.json(HTTPStatus.UNAUTHORIZED, {"error": "unauthorized"})
            raw = self.headers.get("Content-Length", "")
            if not raw.isdigit() or not 0 < int(raw) <= MAX_BODY:
                return self.json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": "body size"})
            try:
                rec = store.validate(json.loads(self.rfile.read(int(raw))))
            except (ValueError, json.JSONDecodeError, AttributeError) as exc:
                return self.json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            store.append(rec)
            return self.json(HTTPStatus.OK, {"ok": True})

    return Handler


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8791)
    ap.add_argument("--allow-any-interface", action="store_true")
    args = ap.parse_args()
    check_host(args.host, args.allow_any_interface)
    os.umask(0o077)
    root = Path(args.data)
    store, token = Store(root), load_token(root)
    httpd = ThreadingHTTPServer((args.host, args.port), make_handler(store, token, (HERE / "page.html").read_bytes()))
    print(f"listening on {args.host}:{args.port}; {len(store.items)} items (token in {root / 'token'})", file=sys.stderr)
    httpd.serve_forever()


if __name__ == "__main__":
    main()
