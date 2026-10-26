"""Labelling v4 page server (docs/16 §4). It shows the dataset items in batches of 20, with the raw bytes (hidden
characters made visible) and the rule proposals, and appends each label to <data>/labels.jsonl.

    python -I server.py --data <research/labelling-v4> --host <tailnet-ip> --port 8791
    open http://<ip>:8791/?t=<data/token>     (the token is made on the first run, mode 600)

Plain HTTP only on loopback or the tailnet. "/" is a static page shell served to anyone; it keeps the ?t= token for
the tab and sends it as the X-Label-Token header, the only credential: no cookie, since a cookie is sent to every
port of the host (Astra review #12). Every /api/ route needs the header, and a label POST must be JSON from this
server's own origin (Astra review #11).
"""
import argparse
import hashlib
import hmac
import ipaddress
import json
import os
import posixpath
import re
import secrets
import sys
import time
from collections import Counter, defaultdict
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

HERE = Path(__file__).resolve().parent
TAILNET = ipaddress.ip_network("100.64.0.0/10")
MAX_BODY, MAX_TEXT, BATCH = 64 * 1024, 200_000, 20
STRATA = ("R", "S", "W", "A")  # labelling order (docs/16 §4)
HIDDEN = re.compile("[\u200b\u200c\u200d\u2060\ufeff\u202a-\u202e\u2066-\u2069\u00ad]")

ORIGIN = ("human", "assisted", "model", "tool", "unknown")  # D63/D64
CHOICES = {
    "rule": ("no", "yes"),  # optional: the document states a rule, decision or procedure; it opens the rule fields
    "origin": ORIGIN,
    "personal_data": ("yes", "no", "synthetic", "unknown"),
    "acceptance": ("pending", "accepted", "withdrawn", "suspended"),
    "mandate": ("no", "yes"),
    "export": ("normal", "restricted"),
    "route": ("cloud_ok", "local_only"),
    "instruction": ("no", "yes"),
    "activate": ("allow", "deny", "escalate"),
    "needs_split": ("no", "yes"),
}
REQUIRED = ("origin", "instruction", "personal_data")  # every other field only when its condition shows it
AI_USE = ("search", "ai_input", "train")
TEXT_FIELDS = {"reviewed_by": 200, "license_item": 300, "applies_to": 300, "valid_from": 10,
               "valid_to": 10, "inputs": 2000, "software_agent": 200, "note": 2000}
FIELDS = frozenset(CHOICES) | frozenset(TEXT_FIELDS) | {"ai_use"}
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
BLIND_SHARE = 0.3  # of the items per stratum: suggestions withheld, to measure the proposers without anchoring
MODES = ("basic", "exception", "all")  # the page's form mode: few fields, + licence/AI use, every field
ALWAYS = frozenset({"origin", "instruction", "personal_data", "rule", "needs_split", "note"})
RULE_FIELDS = frozenset({"acceptance", "mandate", "valid_from", "valid_to", "applies_to"})


def allowed_fields(labels: dict, mode: str) -> frozenset:
    """The fields that the page shows for these choices in this mode (page.html buildForm, docs/19)."""
    if mode == "all":
        return FIELDS
    out = set(ALWAYS)
    origin = labels.get("origin")
    if origin == "assisted":
        out.add("reviewed_by")
    if origin == "tool":
        out.add("software_agent")
    if origin in ("model", "tool", "assisted"):
        out.add("inputs")
    if labels.get("instruction") == "yes":
        out |= {"activate", "applies_to"}
    if labels.get("rule") == "yes":
        out |= RULE_FIELDS
    if mode == "exception":
        out |= {"license_item", "ai_use"}
    return frozenset(out)


def family(it: dict) -> str:
    """Items that share provenance: the group (a skill folder), else the source and the file's directory."""
    return it.get("group") or f"{it['source']}:{posixpath.dirname(it['ref'].get('path') or '')}"


def blind_families(items: list) -> set:
    """A fixed sample of whole families, ~BLIND_SHARE of the items of each stratum (docs/09 blind slice; Astra
    reviews of docs/19 and #11): a person never sees suggestions for a sibling of a blind item. Families are taken in
    sha256 order while they fit the stratum's share. Decided here, never by the page."""
    sizes, totals = defaultdict(Counter), Counter()
    for it in items:
        sizes[family(it)][it["stratum"]] += 1
        totals[it["stratum"]] += 1
    target = {s: round(n * BLIND_SHARE) for s, n in totals.items()}
    taken, out = Counter(), set()
    for fam in sorted(sizes, key=lambda f: hashlib.sha256(f.encode()).hexdigest()):
        if all(taken[s] + n <= target[s] for s, n in sizes[fam].items()):
            out.add(fam)
            taken.update(sizes[fam])
    return out


def _sha256(data: bytes | None) -> str | None:
    return hashlib.sha256(data).hexdigest() if data is not None else None


def _same(field: str, value, proposal) -> bool:
    """Is the stored value the proposal as the page prefilled or showed it?"""
    if field == "ai_use":
        return isinstance(proposal, dict) and value == proposal
    if isinstance(proposal, list):
        proposal = ",".join(map(str, proposal))
    if not isinstance(proposal, str):
        return False
    if field in ("valid_from", "valid_to"):
        proposal = proposal[:10]
    return value == proposal.strip()


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
        data = prop.read_bytes() if prop.exists() else None
        self.proposals = {json.loads(l)["id"]: json.loads(l)["proposals"]
                          for l in (data.decode().splitlines() if data else []) if l.strip()}
        self.proposals_sha256 = _sha256(data)  # of the bytes that were loaded (the file is read once)
        self.blind = blind_families(list(self.items.values()))
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
        hide = it["stratum"] == "S"  # the synthetic notes, facts and hostile flag are the answers
        shown = {k: v for k, v in it.items() if not (hide and k in ("known", "notes", "hostile", "known_source"))}
        blind = self.is_blind(iid)
        return {"item": shown, "blind": blind,
                "text": text, "hidden_chars": hidden, "truncated": bool(it.get("bytes", 0) > MAX_TEXT),
                "proposals": {} if blind else self.proposals.get(iid, {}),
                "llm": None if blind else self.llm().get(iid), "siblings": siblings,
                "label": self.labelled().get(iid)}

    def is_blind(self, iid: str) -> bool:
        return family(self.items[iid]) in self.blind

    def llm(self) -> dict:
        """Qwen suggestions (llm_propose.py); the file grows while a run is going, so it is read when it changes."""
        return self._llm_state()[0]

    def _llm_state(self) -> tuple:
        """(suggestions, sha256 of the bytes they were read from)."""
        path = self.root / "proposals_llm.jsonl"
        mtime = path.stat().st_mtime if path.exists() else None
        if mtime != getattr(self, "_llm_mtime", "unset"):
            data = path.read_bytes() if mtime is not None else None
            rows = [json.loads(l) for l in data.decode().splitlines() if l.strip()] if data else []
            self._llm, self._llm_mtime = ({r["id"]: r["p"] for r in rows if "p" in r}, _sha256(data)), mtime
        return self._llm

    def accepted(self, iid: str, rec: dict, llm: dict) -> list:
        """The label fields whose value is the rule proposal or the Qwen suggestion shown for this item."""
        if self.is_blind(iid):
            return []
        rule, qwen = self.proposals.get(iid, {}), llm.get(iid) or {}
        out = []
        for field, value in rec.items():
            seen = []
            key = "license" if field == "license_item" else field
            if isinstance(rule.get(key), dict) and "value" in rule[key]:
                seen.append(rule[key]["value"])
            if field == "activate":
                seen += ["deny"] if qwen.get("hostile") == "yes" else []
            elif field in qwen:
                seen.append(qwen[field])
            if any(_same(field, value, p) for p in seen):
                out.append(field)
        return sorted(out)

    def validate(self, body: dict) -> dict:
        iid = body.get("id")
        if iid not in self.items:
            raise ValueError("unknown item")
        labels = body.get("labels")
        if not isinstance(labels, dict):
            raise ValueError("labels must be an object")
        if set(labels) - FIELDS:
            raise ValueError(f"unknown fields: {', '.join(sorted(set(labels) - FIELDS))}")
        mode = body.get("mode")
        if mode not in MODES:
            raise ValueError(f"mode: one of {MODES}")
        lists = {k: body.get(k, []) for k in ("shown", "kept")}
        if any(not isinstance(v, list) or not all(isinstance(a, str) and a in FIELDS for a in v) for v in lists.values()):
            raise ValueError("shown and kept must be lists of field names")
        shown, kept = set(lists["shown"]), set(lists["kept"])
        if set(labels) - shown:
            raise ValueError(f"not shown: {', '.join(sorted(set(labels) - shown))}")
        if kept - set(labels) or kept - shown:
            raise ValueError("kept: only shown fields that hold a value")
        if set(REQUIRED) - shown:
            raise ValueError(f"required fields not shown: {', '.join(sorted(set(REQUIRED) - shown))}")
        hidden = shown - allowed_fields(labels, mode) - kept
        if hidden:
            raise ValueError(f"not visible in mode {mode} for these choices: {', '.join(sorted(hidden))}")
        rec = {}
        for field, options in CHOICES.items():  # only the fields that the page showed and the person set
            if field in labels:
                if labels[field] not in options:
                    raise ValueError(f"{field}: not one of {options}")
                rec[field] = labels[field]
        missing = [f for f in REQUIRED if f not in rec]
        if missing:
            raise ValueError(f"required: {', '.join(missing)}")
        if "ai_use" in labels:
            ai_use = labels["ai_use"]
            if not isinstance(ai_use, dict) or any(k not in AI_USE or v not in ("y", "n") for k, v in ai_use.items()):
                raise ValueError("ai_use: only search/ai_input/train with y or n; leave a term out for 'not stated'")
            rec["ai_use"] = ai_use
        for field, limit in TEXT_FIELDS.items():
            if field not in labels:
                continue
            value = labels[field]
            if not isinstance(value, str) or len(value) > limit:
                raise ValueError(f"{field}: text up to {limit} characters")
            if field in ("valid_from", "valid_to") and value and not DATE.match(value):
                raise ValueError(f"{field}: YYYY-MM-DD")
            if value.strip():
                rec[field] = value.strip()
        if rec["origin"] == "assisted" and not rec.get("reviewed_by"):
            raise ValueError("assisted needs reviewed_by (a named person who reviewed it in substance)")
        if rec["origin"] == "tool" and not rec.get("software_agent"):
            raise ValueError("tool needs software_agent (name and version)")
        if rec["instruction"] == "yes" and "activate" not in rec:
            raise ValueError("an instruction needs an activate decision (allow / deny / escalate)")
        ms = body.get("ms")
        llm, llm_sha256 = self._llm_state()
        return {"id": iid, "stratum": self.items[iid]["stratum"], "labels": rec, "claim_source": "person",
                "blind": self.is_blind(iid), "family": family(self.items[iid]), "mode": mode,
                "shown": sorted(shown), "kept": sorted(kept),
                "accepted_proposals": self.accepted(iid, rec, llm),  # derived here; a client list is ignored
                "proposal_version": {"proposals": self.proposals_sha256, "proposals_llm": llm_sha256},
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
    token = path.read_text().strip()
    if len(token) < 16:  # an empty or cut file would make every request look authenticated
        raise SystemExit(f"{path} holds no valid token (16+ characters); delete it to make a new one")
    return token


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
            """Only the X-Label-Token header: no cookie, which every other port of this host would also receive
            (Astra review #12)."""
            got = self.headers.get("X-Label-Token", "")
            return bool(got) and hmac.compare_digest(got, token)

        def send(self, status, body: bytes, ctype="application/json; charset=utf-8"):
            self.send_response(status)
            for k, v in {"Content-Type": ctype, "Content-Length": str(len(body)), "Cache-Control": "no-store",
                         "X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer",
                         "Content-Security-Policy": "default-src 'none'; script-src 'unsafe-inline'; "
                                                    "style-src 'unsafe-inline'; connect-src 'self'"}.items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def json(self, status, obj):
            self.send(status, json.dumps(obj, ensure_ascii=False).encode())

        def do_GET(self):
            url = urlparse(self.path)
            if url.path == "/":
                # The page shell is static and holds no data, so it is served to anyone and the same with or
                # without ?t=: the page keeps the token in sessionStorage, sends it on every /api/ call and removes
                # ?t= from the address bar (Astra reviews #11/#12).
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
            # CSRF (Astra review #11): a page on another port of this host can send a text/plain "simple" POST;
            # only a JSON body from this server's own origin is accepted, on top of the token header.
            host = self.headers.get("Host", "")
            if self.headers.get_content_type() != "application/json" or not host or \
                    self.headers.get("Origin") != f"http://{host}":
                return self.json(HTTPStatus.FORBIDDEN, {"error": "cross-origin or non-JSON request"})
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
