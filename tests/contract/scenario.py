"""A controlled fixture and the calls over the real MCP and HTTP layers; only the shape of each result is kept.

It resets the database of KUTUPHANE_TEST_DSN (the name must end in `_test`, like the `conn` fixture of the suite),
publishes one small book, a journal, a note and a package, and calls every tool and route once or more: a found
result, a not-found or refused one, a bad request. The model gateway is the suite's own stub (FakeBridge). Values are
never recorded, only keys and types: a result changes the snapshot when a field is added, removed or changes type.
"""
import base64
import json
import shutil
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from starlette.testclient import TestClient

TESTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TESTS))  # the suite's helpers (test_*.py, conftest.py) import each other by bare name

from kutuphane import authz, catalog, db, notes, packages, profiles, server, signing  # noqa: E402
from kutuphane.identity import Verifier  # noqa: E402
from kutuphane.policy import make_policy  # noqa: E402
from kutuphane.source import read_source  # noqa: E402
from test_egress_audit import FakeBridge  # noqa: E402
from test_identity import AUD, ISS, token  # noqa: E402
from test_kstd import write_manifest  # noqa: E402
from test_server import LEGACY, MCP_HEADERS, MODERN, _message, mcp_rpc  # noqa: E402

from .matrix import kind_of, label  # noqa: E402

PUBLIC = "http://kutuphane.test"
USER, AGENT, STRANGER = "user:ayse", "agent:kobra-7", "mehmet"
JOURNAL, BOOK = "hafiza", "kitap"
POLICY = make_policy(sensitivity="normal", egress="local_only", protection="standard")
QUESTION = "kayıtlar saklanır"
B_SCHEMA, S_SCHEMA = "install_b", "install_s"  # B receives packages; S, the source, signs them
PACKAGE_AGENT = "agent:inframedic"
NO_NOTE = "nt_" + "0" * 64
NO_COMMIT = "0" * 40


# --- shapes ------------------------------------------------------------------------------------------------------

def shape(value):
    """Keys and types, recursively. A list has one element shape (the merge of its elements)."""
    if isinstance(value, dict):
        return {k: shape(v) for k, v in sorted(value.items())}
    if isinstance(value, list):
        return [merge_all([shape(v) for v in value])] if value else []
    return {bool: "bool", int: "int", float: "float", str: "str", type(None): "null"}[type(value)]


def merge_all(shapes):
    out = shapes[0]
    for other in shapes[1:]:
        out = merge(out, other)
    return out


def merge(a, b):
    """One shape that holds both. A key that is not in both gets a `?` suffix. Unlike shapes become `any_of`: one
    merged object, one merged list and each distinct scalar type, sorted."""
    if a == b:
        return a
    parts = [x for s in (a, b) for x in (s["any_of"] if _is_any_of(s) else [s])]
    objects = [x for x in parts if isinstance(x, dict) and not _is_any_of(x)]
    lists = [x for x in parts if isinstance(x, list)]
    scalars = sorted({x for x in parts if isinstance(x, (str, int))}, key=str)  # a status code is an int
    alternatives = scalars + ([_merge_objects(objects)] if objects else []) + ([_merge_lists(lists)] if lists else [])
    alternatives.sort(key=lambda s: json.dumps(s, sort_keys=True))
    return alternatives[0] if len(alternatives) == 1 else {"any_of": alternatives}


def _is_any_of(shape_):
    return isinstance(shape_, dict) and set(shape_) == {"any_of"}


def _merge_lists(lists):
    elements = [x[0] for x in lists if x]
    return [merge_all(elements)] if elements else []


def _merge_objects(objects):
    keys = sorted({k.rstrip("?") for o in objects for k in o})
    out = {}
    for key in keys:
        seen = [o[key] if key in o else o[key + "?"] for o in objects if key in o or key + "?" in o]
        always = len(seen) == len(objects) and all(key in o for o in objects)
        out[key if always else key + "?"] = merge_all(seen)
    return out


class Cases:
    """case name -> shape. A case is `tool:kind` or `tool:kind (variant)`, `METHOD route [kind]` or
    `METHOD route [kind (variant)]`; outcomes recorded under one name merge. The kind must fit the outcome: `ok` is a
    success, every other kind a refusal; a case that does not fit stops the run (the matrix would be wrong)."""

    def __init__(self):
        self.found: dict[str, object] = {}

    def add(self, name, outcome, *, success: bool):
        kind = kind_of(name)
        if success != (kind in ("ok", "head_ok")):
            raise SystemExit(f"case {name!r}: the outcome does not fit the kind (success={success})")
        self.found[name] = merge(self.found[name], outcome) if name in self.found else outcome

    def result(self):
        return dict(sorted(self.found.items()))


# --- the fixture -------------------------------------------------------------------------------------------------

def _verifier(tmp: Path, key) -> Verifier:
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
    path = tmp / "jwks.json"
    path.write_text(json.dumps({"keys": [{**jwk, "kid": "k1", "use": "sig", "alg": "RS256"}]}))
    return Verifier.from_files(ISS, AUD, path)


def _allow(conn, book, *modes):
    for mode in modes:
        authz.grant(conn, f"book:{book}", mode, USER)
        authz.delegate(conn, delegator=USER, delegate_to=AGENT, obj=f"book:{book}", mode=mode,
                       expires_at=datetime.now(timezone.utc) + timedelta(hours=1))


def reset(dsn: str) -> None:
    with db.connect(dsn) as conn:
        name = conn.execute("SELECT current_database()").fetchone()[0]
        if not name.endswith("_test"):
            raise SystemExit(f"refusing to reset non-test database {name!r}")
        conn.execute("DROP SCHEMA IF EXISTS public CASCADE")
        conn.execute("CREATE SCHEMA public")
        db.migrate(conn)
        for schema in (B_SCHEMA, S_SCHEMA):
            conn.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
            conn.execute(f"CREATE SCHEMA {schema}")
    for schema in (B_SCHEMA, S_SCHEMA):
        with db.connect(dsn + f"?options=-csearch_path%3D{schema},public") as conn:
            db.migrate(conn)


class Context:
    """The installation under test: A (the library the calls read), B (receives packages) and S (a source installation
    that publishes the book and signs its packages, so that A stays as it is)."""

    def __init__(self, dsn, work, keys, verifier, fake):
        self.dsn, self.work = dsn, work
        self.b_dsn, self.s_dsn = (dsn + f"?options=-csearch_path%3D{schema},public" for schema in (B_SCHEMA, S_SCHEMA))
        self.keys, self.verifier, self.fake = keys, verifier, fake
        self.book_dir = work / "okf-kitap"
        self.signer = signing.generate(work / "issuer.key")
        self.private = signing.load_private(work / "issuer.key")
        signing.generate(work / "unknown.key")  # a key that B does not trust
        self.package = self._next = None

    def token(self, **claims) -> str:
        return token((self.keys, self.keys), **claims)

    def bearer(self, **claims) -> dict:
        return {"Authorization": f"Bearer {self.token(**claims)}"}

    def app(self, dsn=None, *, bridge=True):
        return server.create_app(dsn=dsn or self.dsn, verifier=self.verifier,
                                 bridge=self.fake.bridge() if bridge else None, model="qwen" if bridge else None,
                                 public_url=PUBLIC)

    # -- the library (A) and its packages
    def build(self):
        shutil.copytree(TESTS / "fixtures" / "okf-kitap", self.book_dir)
        self._manifest()
        with db.connect(self.dsn) as conn:
            authz.grant(conn, f"book:{BOOK}", "curate", "user:admin")
            catalog.publish(conn, book=BOOK, title=BOOK, files=read_source(self.book_dir), policy=POLICY,
                            profile=profiles.spec("chunked"), approved_by="user:admin")
            notes.create_journal(conn, book=JOURNAL, title=JOURNAL, search=True, ai_input=True, policy=POLICY,
                                 by="user:admin")
            _allow(conn, JOURNAL, "read", "propose")
            _allow(conn, BOOK, "read")
        with db.connect(self.s_dsn) as conn:
            authz.grant(conn, f"book:{BOOK}", "curate", "user:admin")
            self._publish_source(conn)
            self.package = packages.export(conn, BOOK, self.private)
        with db.connect(self.b_dsn) as conn:
            packages.trust(conn, Path(self.signer["public_key"]).read_bytes(),
                           expected_fingerprint=self.signer["fingerprint"], name="Contract", by="user:admin")
            authz.grant(conn, f"book:{BOOK}", "curate", "user:admin")
            authz.grant(conn, f"book:{BOOK}", "propose", PACKAGE_AGENT)
            authz.grant(conn, f"book:{BOOK}", "read", PACKAGE_AGENT)

    def _publish_source(self, conn):
        catalog.publish(conn, book=BOOK, title=BOOK, files=read_source(self.book_dir), policy=POLICY,
                        profile=profiles.spec("chunked"), approved_by="user:admin")

    def _manifest(self):
        # an unknown key in an item is a notice of the kstd reader: it fills `notices` of the items
        write_manifest(self.book_dir, runbook_item={"contract_extra": "x"}, policy_item={"contract_extra": "x"})

    def approve(self, import_id: int) -> None:
        """A person approves the import in B (a human act: no tool or route does it)."""
        with db.connect(self.b_dsn) as conn:
            packages.approve(conn, import_id, by="user:admin", policy=POLICY)

    def next_package(self) -> bytes:
        """Version 2 of the book, signed by the issuer: a changed file, a removed file, a file with an e-mail
        address (a data finding). Built once."""
        if self._next is not None:
            return self._next
        (self.book_dir / "runbook" / "yedek-geri-yukleme.md").write_text("# Yedek\n\nDegisti.\n", encoding="utf-8")
        (self.book_dir / "index.md").unlink()
        (self.book_dir / "ek").mkdir(exist_ok=True)
        # built at run time: a review tool redacts e-mail addresses and IPs it finds written in a file
        address = "@".join(["yonetici", "ornek.org"])
        (self.book_dir / "ek" / "iletisim.md").write_text(f"# Iletisim\n\n{address}\n", encoding="utf-8")
        self._manifest()
        with db.connect(self.s_dsn) as conn:
            self._publish_source(conn)
            self._next = packages.export(conn, BOOK, self.private)
        return self._next

    @staticmethod
    def check_findings(receipt: dict) -> None:
        """The e-mail address of version 2 must be a data finding of the receipt (the fixture would be wrong)."""
        if not any(f.get("rule") == "email" for f in receipt["findings"]):
            raise SystemExit(f"the package receipt has no e-mail finding: {receipt['findings']!r}")

    def untrusted_package(self) -> bytes:
        with db.connect(self.s_dsn) as conn:
            return packages.export(conn, BOOK, signing.load_private(self.work / "unknown.key"))


def collect(dsn: str) -> dict[str, dict]:
    """{"results_mcp": {...}, "results_http": {...}}: case -> shape."""
    reset(dsn)
    work = Path(tempfile.mkdtemp(prefix="kutuphane-contract-"))
    fake = FakeBridge()
    try:
        keys = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        ctx = Context(dsn, work, keys, _verifier(work, keys), fake)
        fake.reply = "İki yıl saklanır [1]."
        ctx.build()
        tools, mount = mcp_results(ctx)
        return {"results_mcp": tools, "results_http": {**http_results(ctx), **mount}}
    finally:
        fake.server.shutdown()
        shutil.rmtree(work, ignore_errors=True)


# --- MCP ---------------------------------------------------------------------------------------------------------
# Every tool is called through the streamable HTTP transport the server exposes at /mcp, as a client of each protocol
# era sends it (test_server.mcp_rpc), and the JSON-RPC message that comes back is recorded as it is serialized.

ERAS = (LEGACY, MODERN)


def _is_error(message) -> bool:
    return message is None or "error" in message or bool(message["result"].get("isError"))


def _rpc_outcome(status, message):
    """The envelope a client receives: the HTTP status, the JSON-RPC message (its shape: `content` blocks,
    `structuredContent`, `isError`, `resultType`, `_meta`, or the `error` object), the block types, the shape of the
    JSON a text block carries, and the text of an error (an error text is a contract)."""
    if message is not None and "tools" in message.get("result", {}):  # the schemas are in tools.json
        message = {**message, "result": {**message["result"], "tools": [
            {k: type(v).__name__ for k, v in t.items()} for t in message["result"]["tools"]]}}
    out = {"http_status": status, "message": shape(message)}
    if message is None:
        return out
    if "error" in message:
        out["rpc_error"] = {"code": message["error"]["code"], "message": message["error"]["message"]}
        return out
    result = message["result"]
    if "content" not in result:
        return out
    out["block_types"] = sorted({block["type"] for block in result["content"]})
    text = " ".join(c["text"] for c in result["content"] if c["type"] == "text")
    if result.get("isError"):
        out["error_text"] = text
    else:
        try:
            out["decoded_text"] = shape(json.loads(text))
        except ValueError:
            out["decoded_text"] = "not json"
    return out


def _both_eras(client, auth, method, params, eras=ERAS):
    """({era: outcome}, the first era's message); the eras must agree on success."""
    outcomes, messages = {}, {}
    for era in eras:
        status, message = mcp_rpc(client, auth, method, params, version=era)
        outcomes[era], messages[era] = _rpc_outcome(status, message), message
    if len({_is_error(m) for m in messages.values()}) != 1:
        raise SystemExit(f"{method} {params}: the two protocol eras do not agree on the outcome")
    return outcomes, messages[eras[0]]


def mcp_results(ctx: Context) -> tuple[dict, dict]:
    """(the tool cases, the cases of the mount `/`)."""
    cases, mount = Cases(), Cases()
    agent = ctx.bearer(act={"sub": "kobra-7"})
    package_agent = ctx.bearer(sub="inframedic", **{"kutuphane/principal_type": "agent"})
    package_stranger = ctx.bearer(sub="outsider", **{"kutuphane/principal_type": "agent"})

    # the client sessions run the lifespan of the apps: the job workers the background jobs need
    with TestClient(ctx.app(), base_url=PUBLIC) as client, TestClient(ctx.app(ctx.b_dsn), base_url=PUBLIC) as client_b:
        def call(tool, kind, args, variant=None, *, c=client, auth=None):
            outcomes, message = _both_eras(c, auth or agent, "tools/call", {"name": tool, "arguments": args})
            cases.add(tool + label(tool, kind, variant), outcomes, success=not _is_error(message))
            return message

        def data(message):
            result = message["result"]
            if "structuredContent" in result:
                return result["structuredContent"].get("result", result["structuredContent"])
            return json.loads(result["content"][0]["text"])

        def job_state(job_id):
            _, message = mcp_rpc(client, agent, "tools/call", {"name": "job_status", "arguments": {"job_id": job_id}},
                                 version=MODERN)
            return data(message)["status"]

        hit = data(call("search_library", "ok", {"query": QUESTION, "max_chars": 200}))[0]["citation"]
        first = data(call("propose_note", "ok", {"book": JOURNAL, "kind": "finding", "text": "one"}))
        second = data(call("propose_note", "ok", {"book": JOURNAL, "kind": "lesson", "text": "two",
                                                  "citations": [hit], "idempotency_key": "contract-note-1"}))
        cited = data(call("propose_note", "ok", {"book": JOURNAL, "kind": "convention", "text": "with a citation",
                                                 "citations": [hit]}))
        call("propose_note", "ok", {"book": JOURNAL, "kind": "decision_proposal", "text": "three",
                                    "decision": {"options": ["a", "b"], "choice": "b"}}, "decision")
        call("propose_note", "not_found", {"book": BOOK, "kind": "finding", "text": "x"}, "no propose grant")
        call("propose_note", "bad_request", {"book": JOURNAL, "kind": "nonsense", "text": "x"})
        call("propose_note", "bad_request", {"kind": "finding"}, "schema")
        call("link_notes", "ok", {"src": second["ref"], "type": "about", "dst": first["ref"]})
        call("link_notes", "ok", {"src": cited["ref"], "type": "about", "dst": second["ref"]})
        call("link_notes", "not_found", {"src": second["ref"], "type": "about", "dst": f"{JOURNAL}@{NO_NOTE}"})
        call("link_notes", "bad_request", {"src": second["ref"], "type": "nonsense", "dst": first["ref"]})
        call("search_library", "ok", {"query": "zzzzqqqq", "book": ["yok"]}, "empty")
        call("search_library", "bad_request", {"query": QUESTION, "acceptance": []})
        call("open_citation", "ok", {"handle": hit}, "passage")
        call("open_citation", "ok", {"handle": cited["ref"]}, "note")
        call("open_citation", "bad_request", {"handle": hit.rsplit("#", 1)[0]})
        call("open_citation", "not_found", {"handle": hit.rsplit("#", 1)[0] + "#999"})
        asked = data(call("ask_library", "ok", {"question": "Erişim kayıtları ne kadar saklanır?"}))
        call("ask_library", "bad_request", {"question": QUESTION, "idempotency_key": "contract-key-1"})
        job = data(call("ask_library", "ok", {"question": QUESTION, "background": True,
                                              "idempotency_key": "contract-key-2"}, "queued"))
        call("reopen_answer", "ok", {"answer_id": asked["id"]})
        call("reopen_answer", "not_found", {"answer_id": "an_unknown"})
        call("reopen_answer", "bad_request", {}, "schema")
        books = data(call("list_books", "ok", {}))
        content_id = next(b["content_id"] for b in books if b["book"] == BOOK)
        call("read_document", "ok", {"book": BOOK, "content_id": content_id, "path": "index.md"})
        call("read_document", "not_found", {"book": BOOK, "content_id": content_id, "path": "yok.md"})
        call("read_document", "bad_request", {"book": BOOK}, "schema")
        call("list_files", "ok", {"book": BOOK})
        call("list_files", "ok", {"book": BOOK, "limit": 3}, "page")
        call("list_files", "not_found", {"book": "gizli"}, "forbidden")
        call("list_files", "bad_request", {"book": BOOK, "limit": 0})
        _wait_job(lambda: job_state(job["job_id"]))
        for tool in ("job_status", "job_result", "job_cancel"):  # recorded once the job is settled
            call(tool, "ok", {"job_id": job["job_id"]})
            call(tool, "not_found", {"job_id": "jb_unknown"})
            call(tool, "bad_request", {}, "schema")
        call("verify_citations", "ok", {"book": JOURNAL, "citations": [f"adc@{NO_COMMIT}:f.py:1"], "at": "main"})
        call("verify_citations", "not_found", {"book": "gizli", "citations": [f"adc@{NO_COMMIT}:f.py:1"],
                                               "at": "main"}, "forbidden")
        call("verify_citations", "bad_request", {"book": JOURNAL, "citations": [], "at": "main"})
        both = {"sets": ["current", "open"]}
        call("query_notes", "ok", both)
        call("query_notes", "bad_request", {"order": "nonsense"})
        call("neighbours", "ok", {"ref": cited["ref"], **both})
        call("neighbours", "not_found", {"ref": f"{JOURNAL}@{NO_NOTE}"})
        call("neighbours", "bad_request", {"ref": "x"}, "malformed ref")
        call("record_outcome", "ok", {"ref": first["ref"], "task_ref": "adc:run/1", "result": "passed",
                                      "idempotency_key": "contract-outcome-1"})
        call("record_outcome", "not_found", {"ref": f"{JOURNAL}@{NO_NOTE}", "task_ref": "adc:run/1",
                                            "result": "passed", "idempotency_key": "contract-outcome-2"})
        call("record_outcome", "bad_request", {"ref": first["ref"], "task_ref": "adc:run/1", "result": "failed",
                                               "idempotency_key": "contract-outcome-1"}, "conflict")
        call("confirm_origin", "ok", {"ref": first["ref"]})
        call("confirm_origin", "not_found", {"ref": f"{JOURNAL}@{NO_NOTE}"})
        call("confirm_origin", "bad_request", {"ref": "x"}, "malformed ref")

        def submit(blob, kind="ok", variant=None, auth=package_agent):
            return call("submit_package", kind, {"package_base64": base64.b64encode(blob).decode()}, variant,
                        c=client_b, auth=auth)

        def status(import_id, kind="ok", variant=None):
            return call("package_status", kind, {"import_id": import_id}, variant, c=client_b, auth=package_agent)
        received = data(submit(ctx.package))
        status(received["id"])
        ctx.approve(received["id"])
        received = data(submit(ctx.next_package()))
        ctx.check_findings(received)
        status(received["id"])
        rejected = data(submit(ctx.untrusted_package()))  # status rejected, with reasons
        status(rejected["id"])
        submit(ctx.package, "not_found", "no propose grant", package_stranger)
        call("submit_package", "bad_request", {"package_base64": "!!"}, c=client_b, auth=package_agent)
        status(999999, "not_found")
        call("package_status", "bad_request", {"import_id": "x"}, "schema", c=client_b, auth=package_agent)
        _transport(client, mount, agent)
    return cases.result(), mount.result()


def _transport(client, cases, agent):
    """The mount at `/`: the MCP endpoint and the protected-resource metadata, without a tool."""
    def raw(kind, variant, r, *, success):
        out = {"status": r.status_code, "content_type": r.headers.get("content-type", "").split(";")[0]}
        try:
            out["body"] = shape(_message(r))
        except ValueError:
            out["body"] = "non-json" if r.content else "empty"
        cases.add(f"MOUNT / {label('MOUNT /', kind, variant)}", out, success=success)

    def rpc_cases(kind, variant, method, params, eras=ERAS):
        outcomes, message = _both_eras(client, agent, method, params, eras)
        cases.add(f"MOUNT / {label('MOUNT /', kind, variant)}", outcomes, success=not _is_error(message))

    rpc_cases("ok", "tools/list", "tools/list", {})
    rpc_cases("ok", "server/discover", "server/discover", {}, (MODERN,))  # only the 2026-07-28 era has it
    rpc_cases("not_found", "unknown tool", "tools/call", {"name": "no_such_tool", "arguments": {}})
    rpc_cases("not_found", "unknown method", "no/such/method", {})
    rpc_cases("bad_request", "no tool name", "tools/call", {"arguments": {}})
    raw("ok", "protected resource metadata", client.get("/.well-known/oauth-protected-resource"), success=True)
    raw("bad_request", "not json", client.post("/mcp", content=b"{", headers={**MCP_HEADERS, **agent}), success=False)
    raw("unauthorized", None, client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                                          headers=MCP_HEADERS), success=False)


def _wait_job(status, timeout=30.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if status() in ("succeeded", "failed", "cancelled"):
            return
        time.sleep(0.2)
    raise SystemExit("the background job did not finish")


# --- HTTP --------------------------------------------------------------------------------------------------------

def _http_outcome(r):
    type_ = r.headers.get("content-type", "").split(";")[0]
    try:
        body = shape(r.json()) if type_ == "application/json" else "non-json"
    except ValueError:
        body = "invalid-json"
    return {"status": r.status_code, "content_type": type_, "body": body}


def http_results(ctx: Context) -> dict:
    cases = Cases()
    user, agent = ctx.bearer(), ctx.bearer(act={"sub": "kobra-7"})
    outsider = ctx.bearer(sub=STRANGER)
    package_agent = ctx.bearer(sub="inframedic", **{"kutuphane/principal_type": "agent"})
    package_stranger = ctx.bearer(sub="outsider", **{"kutuphane/principal_type": "agent"})
    app, app_b = ctx.app(), ctx.app(ctx.b_dsn, bridge=False)

    with TestClient(app, base_url=PUBLIC) as client, TestClient(app_b, base_url=PUBLIC) as client_b:
        def call(method, route, kind, path, variant=None, *, c=client, headers=None, head=False, **kw):
            """One request; with `head`, the same request with HEAD too (GET routes: the ok and the main error)."""
            headers = user if headers is None else headers
            r = c.request(method, path, headers=headers, **kw)
            cases.add(f"{method} {route} {label(f'{method} {route}', kind, variant)}", _http_outcome(r),
                      success=r.status_code < 400)
            if head:
                h = c.head(path, headers=headers, **{k: v for k, v in kw.items() if k == "params"})
                outcome = {**_http_outcome(h), "body": "empty" if not h.content else "NOT EMPTY", "body_empty": not h.content}
                cases.add(f"HEAD {route} [head_{'ok' if kind == 'ok' else 'error'}]", outcome,
                          success=h.status_code < 400)
            return r

        def unauthorized(method, route, path, head=False, **kw):
            return call(method, route, "unauthorized", path, headers={}, head=head, **kw)

        call("GET", "/healthz", "ok", "/healthz", headers={}, head=True)
        call("GET", "/v1/whoami", "ok", "/v1/whoami", head=True)
        call("GET", "/v1/whoami", "ok", "/v1/whoami", "delegated", headers=agent)
        unauthorized("GET", "/v1/whoami", "/v1/whoami", head=True)
        call("GET", "/v1/health", "ok", "/v1/health", head=True)
        unauthorized("GET", "/v1/health", "/v1/health", head=True)

        found = call("GET", "/v1/search", "ok", "/v1/search", params={"q": QUESTION}, head=True).json()["results"]
        call("GET", "/v1/search", "ok", "/v1/search", "empty", params={"q": "zzzzqqqq"})
        call("GET", "/v1/search", "ok", "/v1/search", "empty", params={"q": QUESTION}, headers=outsider)
        call("GET", "/v1/search", "bad_request", "/v1/search", params={"q": QUESTION, "current_only": "maybe"},
             head=True)
        unauthorized("GET", "/v1/search", "/v1/search", params={"q": QUESTION})
        handle = found[0]["citation"]
        call("GET", "/v1/citation", "ok", "/v1/citation", params={"handle": handle}, head=True)
        call("GET", "/v1/citation", "bad_request", "/v1/citation", "malformed",
             params={"handle": handle.rsplit("#", 1)[0]})
        call("GET", "/v1/citation", "not_found", "/v1/citation", params={"handle": handle.rsplit("#", 1)[0] + "#999"},
             head=True)
        unauthorized("GET", "/v1/citation", "/v1/citation", params={"handle": handle})

        asked = call("POST", "/v1/ask", "ok", "/v1/ask", json={"question": "Erişim kayıtları ne kadar saklanır?"})
        call("POST", "/v1/ask", "ok", "/v1/ask", "empty", json={"question": QUESTION, "book": ["gizli"]})
        queued = call("POST", "/v1/ask", "ok", "/v1/ask", "queued", json={"question": QUESTION,
                                                                          "background": True}).json()
        call("POST", "/v1/ask", "bad_request", "/v1/ask", content=b"{")
        unauthorized("POST", "/v1/ask", "/v1/ask", json={"question": QUESTION})
        answer = f"/v1/answers/{asked.json()['id']}"
        call("GET", "/v1/answers/{answer_id}", "ok", answer, head=True)
        call("GET", "/v1/answers/{answer_id}", "not_found", "/v1/answers/an_unknown", head=True)
        unauthorized("GET", "/v1/answers/{answer_id}", answer)
        job = queued["job_id"]
        _wait_job(lambda: client.get(f"/v1/jobs/{job}", headers=user).json()["status"])
        for method, route, tail in (("GET", "/v1/jobs/{job_id}", ""), ("GET", "/v1/jobs/{job_id}/result", "/result"),
                                    ("POST", "/v1/jobs/{job_id}/cancel", "/cancel")):  # once the job is settled
            head = method == "GET"
            call(method, route, "ok", f"/v1/jobs/{job}{tail}", head=head)
            call(method, route, "not_found", f"/v1/jobs/jb_unknown{tail}", head=head)
            unauthorized(method, route, f"/v1/jobs/{job}{tail}", head=head)

        books = call("GET", "/v1/books", "ok", "/v1/books", head=True).json()["books"]
        call("GET", "/v1/books", "ok", "/v1/books", "empty", headers=outsider)
        unauthorized("GET", "/v1/books", "/v1/books", head=True)
        content_id = next(b["content_id"] for b in books if b["book"] == BOOK)
        files = f"/v1/books/{BOOK}/files"
        call("GET", "/v1/books/{book}/files", "ok", files, head=True)
        call("GET", "/v1/books/{book}/files", "ok", files, "page", params={"limit": 3})
        call("GET", "/v1/books/{book}/files", "not_found", "/v1/books/gizli/files", "forbidden", head=True)
        call("GET", "/v1/books/{book}/files", "bad_request", files, params={"limit": 0}, head=True)
        unauthorized("GET", "/v1/books/{book}/files", files)
        file_route = "/v1/files/{book}/{content_id}/{path:path}"
        call("GET", file_route, "ok", f"/v1/files/{BOOK}/{content_id}/index.md", head=True)
        call("GET", file_route, "not_found", f"/v1/files/{BOOK}/{content_id}/yok.md", head=True)
        unauthorized("GET", file_route, f"/v1/files/{BOOK}/{content_id}/index.md")

        note = {"book": JOURNAL, "kind": "finding", "text": "over http", "idempotency_key": "http-0001",
                "citations": [handle]}
        created = call("POST", "/v1/notes", "ok", "/v1/notes", "created", json=note).json()
        call("POST", "/v1/notes", "ok", "/v1/notes", "retried", json=note)
        call("POST", "/v1/notes", "bad_request", "/v1/notes", content=b"{")
        call("POST", "/v1/notes", "not_found", "/v1/notes", "forbidden", headers=outsider,
             json={"book": JOURNAL, "kind": "finding", "text": "x"})
        unauthorized("POST", "/v1/notes", "/v1/notes", json=note)
        other = call("POST", "/v1/notes", "ok", "/v1/notes", "with a citation", json={
            "book": JOURNAL, "kind": "lesson", "text": "second", "citations": [handle]}).json()
        link = {"src": other["ref"], "type": "about", "dst": created["ref"]}  # both cite a passage
        call("POST", "/v1/notes/links", "ok", "/v1/notes/links", "created", json=link)
        call("POST", "/v1/notes/links", "ok", "/v1/notes/links", "retried", json=link)
        call("POST", "/v1/notes/links", "not_found", "/v1/notes/links", json={**link, "dst": f"{JOURNAL}@{NO_NOTE}"})
        call("POST", "/v1/notes/links", "bad_request", "/v1/notes/links", content=b"{")
        unauthorized("POST", "/v1/notes/links", "/v1/notes/links", json=link)
        call("GET", "/v1/notes", "ok", "/v1/notes", params=[("sets", "current"), ("sets", "open")], head=True)
        call("GET", "/v1/notes", "bad_request", "/v1/notes", params={"order": "x"}, head=True)
        unauthorized("GET", "/v1/notes", "/v1/notes")
        book, nid = other["ref"].split("@")
        near = f"/v1/notes/{book}/{nid}/neighbours"
        call("GET", "/v1/notes/{book}/{id}/neighbours", "ok", near, params=[("sets", "current"), ("sets", "open")],
             head=True)
        call("GET", "/v1/notes/{book}/{id}/neighbours", "not_found", f"/v1/notes/{book}/{NO_NOTE}/neighbours",
             head=True)
        call("GET", "/v1/notes/{book}/{id}/neighbours", "bad_request", f"/v1/notes/{book}/x/neighbours", "malformed id")
        unauthorized("GET", "/v1/notes/{book}/{id}/neighbours", near)
        sure = f"/v1/notes/{book}/{nid}/confirmation"
        call("GET", "/v1/notes/{book}/{id}/confirmation", "ok", sure, head=True)
        call("GET", "/v1/notes/{book}/{id}/confirmation", "not_found", sure, "forbidden", headers=outsider, head=True)
        call("GET", "/v1/notes/{book}/{id}/confirmation", "bad_request", f"/v1/notes/{book}/x/confirmation",
             "malformed id")
        unauthorized("GET", "/v1/notes/{book}/{id}/confirmation", sure)
        outcome = {"ref": created["ref"], "task_ref": "adc:run/1", "result": "passed", "idempotency_key": "http-0001"}
        call("POST", "/v1/outcomes", "ok", "/v1/outcomes", json=outcome)
        call("POST", "/v1/outcomes", "not_found", "/v1/outcomes", json={**outcome, "ref": f"{JOURNAL}@{NO_NOTE}",
                                                                          "idempotency_key": "http-0002"})
        call("POST", "/v1/outcomes", "bad_request", "/v1/outcomes", "conflict", json={**outcome, "result": "failed"})
        call("POST", "/v1/outcomes", "bad_request", "/v1/outcomes", json={**outcome, "idempotency_key": None})
        unauthorized("POST", "/v1/outcomes", "/v1/outcomes", json=outcome)
        verify = {"book": JOURNAL, "citations": [f"adc@{NO_COMMIT}:f.py:1"], "at": "main"}
        call("POST", "/v1/citations/verify", "ok", "/v1/citations/verify", json=verify)
        call("POST", "/v1/citations/verify", "not_found", "/v1/citations/verify", "forbidden",
             json={**verify, "book": "gizli"})
        call("POST", "/v1/citations/verify", "bad_request", "/v1/citations/verify", json={**verify, "citations": []})
        unauthorized("POST", "/v1/citations/verify", "/v1/citations/verify", json=verify)

        def send(blob, kind="ok", variant=None, headers=package_agent):
            return call("POST", "/v1/packages", kind, "/v1/packages", variant, c=client_b, headers=headers,
                        content=blob)
        send(ctx.package)  # a retry of what the MCP calls submitted: the stored receipt
        sent = send(ctx.next_package()).json()
        ctx.check_findings(sent)
        rejected = send(ctx.untrusted_package()).json()  # status rejected, with reasons
        send(ctx.package, "not_found", "forbidden", package_stranger)
        send(b"x", "bad_request")
        unauthorized("POST", "/v1/packages", "/v1/packages", c=client_b, content=ctx.package)
        status = f"/v1/packages/{sent['id']}"
        call("GET", "/v1/packages/{import_id}", "ok", status, c=client_b, headers=package_agent, head=True)
        call("GET", "/v1/packages/{import_id}", "ok", f"/v1/packages/{rejected['id']}", c=client_b,
             headers=package_agent)
        call("GET", "/v1/packages/{import_id}", "not_found", "/v1/packages/999999", c=client_b,
             headers=package_agent, head=True)
        call("GET", "/v1/packages/{import_id}", "bad_request", "/v1/packages/x", "not a number", c=client_b,
             headers=package_agent)
        unauthorized("GET", "/v1/packages/{import_id}", status, c=client_b)
    return cases.result()
