"""Labelling v5 page server (docs/20 §4, D67). It shows whole cases (a document, a package or a chain, with its
evidence) in fixed, mixed batches of 10 and appends each answer to <data>/labels.jsonl.

    python -I server.py --data <research/labelling-v5> --host <tailnet-ip> --port 8792
    open http://<ip>:8792/?t=<data/token>     (the token is made on the first run, mode 600)

Data: <data>/{human,scenario}/<slice>.cases.jsonl, the case folders <data>/<set>/<slice>/<case_id>/ (file copies), and
the proposer files <data>/proposals.<set>.jsonl and <data>/proposals_llm.<set>.jsonl. The server never reads a
*.gold.jsonl file.

Human cases (D67): the person judges first. The server stores that first choice, and only then returns the rule and
Qwen suggestions; the person confirms or changes, and the server stores the second choice as a revision. The first
choice is the measurement; the revision gives the correction time. Scenario cases get one answer
(permit / deny / escalate + a reason) and never show suggestions.

Plain HTTP only on loopback or the tailnet. "/" is a static page shell served to anyone; it keeps the ?t= token for
the tab and sends it as the X-Label-Token header, the only credential: no cookie, since a cookie is sent to every
port of the host (Astra review #12). Every /api/ route needs the header, and a label POST must be JSON from this
server's own origin (Astra reviews #10/#11).
"""
import argparse
import hashlib
import hmac
import ipaddress
import json
import os
import re
import secrets
import sys
import threading
import time
from collections import Counter
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))  # `python -I` does not put the script folder on the path
from propose import case_file  # noqa: E402  (the one containment check for case files, Astra review #12)

TAILNET = ipaddress.ip_network("100.64.0.0/10")
MAX_BODY, MAX_TEXT = 64 * 1024, 200_000
BATCH, PER_FAMILY = 10, 2  # docs/20 §4.1
SETS = ("human", "scenario")
SEED = "labelling-v5/batches/1"  # the batch order is a function of this seed and the case ids; then it is frozen
HIDDEN = re.compile("[\u200b\u200c\u200d\u2060\ufeff\u202a-\u202e\u2066-\u2069\u00ad]")
CASE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,199}$")

# The one open question of each human group (docs/20 §3.3). "unknown" is "insufficient evidence" in every group; the
# values follow the proposers (experiments/labeling_v5/propose.py) and kstd (personal_data), so they compare directly.
GROUPS = {
    "review-evidence": {"field": "review", "options": ("substantive", "approval-only", "unknown"),
                        "text": {"reviewed_by": 200}, "related": ("review", "reviewed_by", "origin")},
    "instruction-safety": {"field": "activation_risk", "options": ("safe", "risky", "harmful", "unknown"),
                           "text": {}, "related": ("activation_risk", "instruction", "hostile")},
    "normative-meaning": {"field": "normative", "options": ("binding", "advice", "history", "unknown"),
                          "text": {"scope": 300}, "related": ("normative", "scope", "acceptance")},
    "personal-data": {"field": "personal_data", "options": ("yes", "synthetic", "no", "unknown"),
                      "text": {}, "related": ("personal_data",)},
}
COMMON_TEXT = {"evidence_pointer": 500, "note": 2000}
DECISIONS = ("permit", "deny", "escalate")
SCENARIO_TEXT = {"reason": 500, "notices": 1000, "note": 2000}
STAGES = {"human": ("first", "revision"), "scenario": ("answer",)}
# The case keys that the page may see. Anything else (an expected result, a held-out mark, the selection stratum)
# stays on the server, so held-out bases look like the others.
CASE_KEYS = ("id", "set", "group", "source", "family", "operation", "questions", "title", "why_selected", "evidence",
             "statements", "policy", "trust", "request", "evaluation_time", "eval_time", "now", "actor")
FILE_KEYS = ("path", "url", "ref", "sha256", "bytes", "copy", "license_item", "role", "redistribute")
# Before the first choice of a human case, a file shows its own path but not its source path or URL: a fixture
# folder name (".../malicious_skill/SKILL.md") would give the answer away. Repo and commit stay visible.
BLIND_REF = ("repo", "commit")


def _sha256(data: bytes | None) -> str | None:
    return hashlib.sha256(data).hexdigest() if data is not None else None


def _now() -> tuple:
    t = time.time()
    return int(t * 1000), time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(t))


def family(case: dict) -> str:
    """The source family of a case: its declared family, else its source."""
    return case.get("family") or case.get("source") or case["id"]


def plan_batches(cases: list, frozen: list | None = None) -> list:
    """Fixed, mixed batches of BATCH: at most PER_FAMILY cases of one family in a batch, the groups taken in turn
    (the group with the most cases left first). Inside a group the next case is from the family with the most cases
    left (so that no single family is left over at the end), else in sha256(SEED + id) order; the result does not
    depend on the file order. Batches that are already frozen stay as they are; new cases go into new batches at the
    end."""
    frozen = [list(b) for b in frozen or []]
    placed = {i for b in frozen for i in b}
    queues, left = {}, Counter()
    for c in sorted((c for c in cases if c["id"] not in placed),
                    key=lambda c: hashlib.sha256(f"{SEED}/{c['id']}".encode()).hexdigest()):
        queues.setdefault(c.get("group") or "", []).append(c)
        left[family(c)] += 1
    out = frozen
    while any(queues.values()):
        batch, fams = [], Counter()
        progress = True
        while len(batch) < BATCH and progress:
            progress = False
            for g in sorted(queues, key=lambda g: (-len(queues[g]), g)):
                allowed = [c for c in queues[g] if fams[family(c)] < PER_FAMILY]
                if not allowed:
                    continue
                pick = max(allowed, key=lambda c: left[family(c)])  # max() keeps the first of equals
                queues[g].remove(pick)
                batch.append(pick["id"])
                fams[family(pick)] += 1
                left[family(pick)] -= 1
                progress = True
                if len(batch) == BATCH:
                    break
        out.append(batch)
    return out


def _text(data: bytes) -> tuple:
    """(text with hidden characters made visible, count of hidden characters), or (None, 0) for binary bytes."""
    if b"\0" in data[:8192]:
        return None, 0
    raw = data[:MAX_TEXT].decode("utf-8", "replace")
    return HIDDEN.sub(lambda m: f"⟦U+{ord(m.group(0)):04X}⟧", raw), len(HIDDEN.findall(raw))


class Proposals:
    """One proposer file, re-read when it changes (a Qwen run may still write to it). The latest line per id
    counts; a line with an error is no suggestion."""

    def __init__(self, path: Path, key: str):
        self.path, self.key, self._mtime, self._rows, self._sha = path, key, "unset", {}, None

    def state(self) -> tuple:
        mtime = self.path.stat().st_mtime if self.path.exists() else None
        if mtime != self._mtime:
            data = self.path.read_bytes() if mtime is not None else None
            rows = {}
            for line in data.decode("utf-8", "replace").splitlines() if data else []:
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(r, dict) and "id" in r and isinstance(r.get(self.key), dict) and not r.get("error"):
                    rows[r["id"]] = r
            self._rows, self._sha, self._mtime = rows, _sha256(data), mtime
        return self._rows, self._sha


def slice_indexes(root: Path) -> list:
    """(set, slice, index path) of every case index to label. A candidate pool (`<slice>-candidates*.cases.jsonl`)
    is the input of a selection, not a case list, so it is never shown."""
    return [(s, index.name[:-len(".cases.jsonl")], index) for s in SETS
            for index in sorted((root / s).glob("*.cases.jsonl")) if "-candidates" not in index.name]


class Store:
    def __init__(self, root: Path):
        self.root = root
        self.cases, self.dirs = {}, {}
        self.skipped = []
        for s, slice_, index in slice_indexes(root):
            for line in index.read_text().splitlines():
                if not line.strip():
                    continue
                c = json.loads(line)
                cid = c.get("id")
                if not isinstance(cid, str) or not CASE_ID.match(cid) or cid in self.cases:
                    self.skipped.append(f"{index.name}: bad or repeated id {cid!r}")
                    continue
                if s == "human" and c.get("group") not in GROUPS:
                    self.skipped.append(f"{index.name}: {cid}: no question for group {c.get('group')!r}")
                    continue
                c["set"] = s
                self.cases[cid] = c
                self.dirs[cid] = root / s / slice_ / cid
        self.rules = {s: Proposals(root / f"proposals.{s}.jsonl", "proposals") for s in SETS}
        self.llm = {s: Proposals(root / f"proposals_llm.{s}.jsonl", "p") for s in SETS}
        self.batches = {s: self._freeze(s) for s in SETS}
        self.labels_path = root / "labels.jsonl"
        self.lock = threading.Lock()
        self.first, self.last = {}, {}  # id -> the first choice / the latest record
        if self.labels_path.exists():
            for line in self.labels_path.read_text().splitlines():
                if line.strip():
                    self._index(json.loads(line))

    def _freeze(self, s: str) -> list:
        path = self.root / f"batches.{s}.json"
        frozen = json.loads(path.read_text())["batches"] if path.exists() else []
        cases = [c for c in self.cases.values() if c["set"] == s]
        batches = plan_batches(cases, frozen)
        if batches != frozen:
            path.write_text(json.dumps({"seed": SEED, "batch": BATCH, "per_family": PER_FAMILY,
                                        "batches": batches}, indent=1) + "\n")
        return [[i for i in b if i in self.cases] for b in batches]  # a removed case drops out; the rest stay

    def _index(self, rec: dict) -> None:
        if rec.get("stage") in ("first", "answer") and rec["id"] not in self.first:
            self.first[rec["id"]] = rec
        self.last[rec["id"]] = rec

    def status(self, cid: str) -> str:
        last = self.last.get(cid)
        return {None: "todo", "first": "first", "revision": "done", "answer": "done"}[last and last["stage"]]

    def state(self) -> dict:
        out = {}
        for s in SETS:
            ids = [i for b in self.batches[s] for i in b]
            out[s] = {"total": len(ids), "done": sum(self.status(i) == "done" for i in ids),
                      "batches": len(self.batches[s])}
        return out

    def batch_list(self, s: str) -> list:
        return [[{"id": i, "status": self.status(i), "group": self.cases[i].get("group")} for i in b]
                for b in self.batches[s]]

    def files(self, cid: str, blind: bool = False) -> tuple:
        out, hidden = [], 0
        folder = self.dirs[cid]
        for f in self.cases[cid].get("files") or []:
            meta = {k: f[k] for k in FILE_KEYS if k in f}
            if blind:
                meta.pop("url", None)
                if isinstance(meta.get("ref"), dict):
                    meta["ref"] = {k: v for k, v in meta["ref"].items() if k in BLIND_REF}
            text, n, note = None, 0, None
            if f.get("copy") is True and isinstance(f.get("local_path"), str) and f["local_path"]:
                path = case_file(folder, f)
                if path is None:
                    note = "The copy is missing."
                else:
                    data = path.read_bytes()
                    text, n = _text(data)
                    if text is None:
                        note = "Binary file: not shown."
                    elif len(data) > MAX_TEXT:
                        note = "Only the first 200 KB are shown."
            else:
                note = "No copy (the licence does not allow it, or rights are unclear): reference and hash only."
            hidden += n
            out.append({**meta, "text": text, "hidden_chars": n, "note": note})
        return out, hidden

    def suggestions(self, cid: str) -> dict:
        """The rule and Qwen suggestions for the fields of this case's group question."""
        case = self.cases[cid]
        related = GROUPS[case["group"]]["related"]
        rules, rules_sha = self.rules["human"].state()
        llm, llm_sha = self.llm["human"].state()
        out = []
        rule = rules.get(cid)
        for field in related:
            p = (rule or {}).get("proposals", {}).get(field)
            if isinstance(p, dict) and "value" in p:
                out.append({"from": "rule", "field": field, "value": p["value"],
                            "confidence": p.get("confidence"), "evidence": p.get("evidence")})
        q = (llm.get(cid) or {}).get("p", {})
        for field in related:
            if field in q:
                out.append({"from": "Qwen", "field": field, "value": q[field],
                            "confidence": q.get(f"{field}_confidence"), "evidence": q.get(f"{field}_evidence")})
        return {"items": out,
                "version": {"proposals": rules_sha, "proposals_llm": llm_sha,
                            "rule": (rule or {}).get("proposer_version"),
                            "llm": (llm.get(cid) or {}).get("proposer_version")}}

    def case(self, cid: str) -> dict | None:
        c = self.cases.get(cid)
        if c is None:
            return None
        with self.lock:
            first, last = self.first.get(cid), self.last.get(cid)
        files, hidden = self.files(cid, blind=c["set"] == "human" and not first)
        out = {"case": {k: c[k] for k in CASE_KEYS if k in c}, "files": files, "hidden_chars": hidden,
               "first": None, "latest": None, "suggestions": None}
        if first:
            out["first"], out["latest"] = first["labels"], last["labels"]
        if c["set"] == "human":
            out["question"] = {"group": c["group"], "field": GROUPS[c["group"]]["field"],
                               "options": GROUPS[c["group"]]["options"]}
            if first:  # judge first (D67): no suggestions before the first choice is stored
                out["suggestions"] = self.suggestions(cid)
        return out

    def validate(self, body: dict) -> dict:
        """The answer as stored. Raises ValueError for a bad body."""
        if not isinstance(body, dict):
            raise ValueError("body must be an object")
        cid = body.get("id")
        if cid not in self.cases:
            raise ValueError("unknown case")
        case = self.cases[cid]
        stage = body.get("stage")
        if stage not in STAGES[case["set"]]:
            raise ValueError(f"stage: one of {STAGES[case['set']]}")
        answer = body.get("answer")
        if not isinstance(answer, dict):
            raise ValueError("answer must be an object")
        if case["set"] == "human":
            g = GROUPS[case["group"]]
            choices, texts, required = {g["field"]: g["options"]}, {**g["text"], **COMMON_TEXT}, [g["field"]]
        else:
            choices, texts, required = {"decision": DECISIONS}, SCENARIO_TEXT, ["decision", "reason"]
        extra = set(answer) - set(choices) - set(texts)
        if extra:
            raise ValueError(f"not asked for this case: {', '.join(sorted(extra))}")
        rec = {}
        for field, options in choices.items():
            if field in answer:
                if answer[field] not in options:
                    raise ValueError(f"{field}: one of {options}")
                rec[field] = answer[field]
        for field, limit in texts.items():
            if field in answer:
                v = answer[field]
                if not isinstance(v, str) or len(v) > limit:
                    raise ValueError(f"{field}: text up to {limit} characters")
                if v.strip():
                    rec[field] = v.strip()
        missing = [f for f in required if f not in rec]
        if missing:
            raise ValueError(f"required: {', '.join(missing)}")
        if rec.get("review") == "substantive" and not rec.get("reviewed_by"):
            raise ValueError("a substantive review needs the name of the person (reviewed_by)")
        ms = body.get("ms")
        return {"id": cid, "set": case["set"], "group": case.get("group"), "family": family(case),
                "operation": case.get("operation"), "stage": stage, "labels": rec,
                "ms": int(ms) if isinstance(ms, (int, float)) and 0 <= ms < 86_400_000 else None}

    def save(self, body: dict) -> dict:
        """Validate, store, and return what the page may see next. Raises ValueError (400) or LookupError (409)."""
        rec = self.validate(body)
        cid, stage = rec["id"], rec["stage"]
        with self.lock:
            first = self.first.get(cid)
            if stage == "first" and first:
                raise LookupError("the first choice is already stored; send a revision")
            if stage == "revision" and not first:
                raise LookupError("no first choice yet: a revision comes after the first choice")
            t, rec["ts"] = _now()
            rec["t_ms"] = t
            if rec["set"] == "human":
                sugg = self.suggestions(cid)
                field = GROUPS[rec["group"]]["field"]
                rec["suggestions_seen"] = stage == "revision"
                rec["proposal_version"] = sugg["version"]
                rec["matches"] = {s["from"]: s["value"] == rec["labels"].get(field)
                                  for s in sugg["items"] if s["field"] == field}
                if stage == "revision":
                    rec["first_ts"] = first["ts"]
                    rec["correction_ms"] = t - first["t_ms"]  # from the reveal (the first save) to this choice
                    rec["changed"] = sorted(k for k in set(rec["labels"]) | set(first["labels"])
                                            if rec["labels"].get(k) != first["labels"].get(k))
            with self.labels_path.open("a") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            self._index(rec)
        out = {"ok": True}
        if stage == "first":
            out["suggestions"] = sugg
        return out


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
        server_version = "kutuphane-label/5"

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
                return self.json(HTTPStatus.OK, {"sets": store.state(), "groups": GROUPS, "decisions": DECISIONS})
            if url.path == "/api/batches":
                s = parse_qs(url.query).get("set", [""])[0]
                return self.json(HTTPStatus.OK, {"batches": store.batch_list(s)}) if s in SETS else \
                    self.json(HTTPStatus.BAD_REQUEST, {"error": "set"})
            if url.path.startswith("/api/case/"):
                got = store.case(unquote(url.path[len("/api/case/"):]))
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
                out = store.save(json.loads(self.rfile.read(int(raw))))
            except LookupError as exc:
                return self.json(HTTPStatus.CONFLICT, {"error": str(exc)})
            except (ValueError, json.JSONDecodeError) as exc:
                return self.json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return self.json(HTTPStatus.OK, out)

    return Handler


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8792)
    ap.add_argument("--allow-any-interface", action="store_true")
    args = ap.parse_args()
    check_host(args.host, args.allow_any_interface)
    os.umask(0o077)
    root = Path(args.data)
    store, token = Store(root), load_token(root)
    for msg in store.skipped:
        print(f"skipped: {msg}", file=sys.stderr)
    httpd = ThreadingHTTPServer((args.host, args.port), make_handler(store, token, (HERE / "page.html").read_bytes()))
    counts = ", ".join(f"{s} {v['total']} in {v['batches']} batches" for s, v in store.state().items())
    print(f"listening on {args.host}:{args.port}; {counts} (token in {root / 'token'})", file=sys.stderr)
    httpd.serve_forever()


if __name__ == "__main__":
    main()
