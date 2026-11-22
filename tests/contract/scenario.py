"""A controlled fixture and the calls over the real MCP and HTTP layers; only the shape of each result is kept.

It resets the database of KUTUPHANE_TEST_DSN (the name must end in `_test`, like the `conn` fixture of the suite),
publishes one small book, a journal, a note and a package, and calls every tool and route once or more: a found
result, a not-found or refused one, a bad request. The model gateway is the suite's own stub (FakeBridge). Values are
never recorded, only keys and types: a result changes the snapshot when a field is added, removed or changes type.
"""
import asyncio
import base64
import json
import shutil
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt
import psycopg
from cryptography.hazmat.primitives.asymmetric import rsa
from mcp.server.auth.middleware.auth_context import auth_context_var
from mcp.server.auth.middleware.bearer_auth import AuthenticatedUser
from mcp.server.auth.provider import AccessToken
from mcp.server.mcpserver.exceptions import ToolError
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

PUBLIC = "http://kutuphane.test"
USER, AGENT, STRANGER = "user:ayse", "agent:kobra-7", "mehmet"
JOURNAL, BOOK = "hafiza", "kitap"
POLICY = make_policy(sensitivity="normal", egress="local_only", protection="standard")
QUESTION = "kayıtlar saklanır"
B_SCHEMA = "install_b"
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
    """One shape that holds both. A key that is not in both gets a `?` suffix; unlike types become `any_of`."""
    if a == b:
        return a
    if isinstance(a, dict) and isinstance(b, dict):
        out = {}
        for key in sorted({k.rstrip("?") for k in a} | {k.rstrip("?") for k in b}):
            in_a, in_b = key in a or key + "?" in a, key in b or key + "?" in b
            left, right = a.get(key, a.get(key + "?")), b.get(key, b.get(key + "?"))
            both = in_a and in_b and not key.endswith("?") and key in a and key in b
            out[key if both else key + "?"] = merge(left, right) if in_a and in_b else (left if in_a else right)
        return out
    if isinstance(a, list) and isinstance(b, list):
        return [merge(a[0], b[0])] if a and b else (a or b)
    alternatives = [x for s in (a, b) for x in (s["any_of"] if isinstance(s, dict) and set(s) == {"any_of"} else [s])]
    unique = []
    for s in alternatives:
        if s not in unique:
            unique.append(s)
    unique.sort(key=lambda s: json.dumps(s, sort_keys=True))
    return unique[0] if len(unique) == 1 else {"any_of": unique}


class Cases:
    """name -> list of outcomes; outcomes with the same name merge."""

    def __init__(self):
        self.found: dict[str, object] = {}

    def add(self, name, outcome):
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
        conn.execute(f"DROP SCHEMA IF EXISTS {B_SCHEMA} CASCADE")
        conn.execute(f"CREATE SCHEMA {B_SCHEMA}")
    with db.connect(dsn + f"?options=-csearch_path%3D{B_SCHEMA},public") as conn:
        db.migrate(conn)


def collect(dsn: str) -> dict[str, dict]:
    """{"results_mcp": {...}, "results_http": {...}}: tool/route -> case -> shape."""
    reset(dsn)
    b_dsn = dsn + f"?options=-csearch_path%3D{B_SCHEMA},public"
    work = Path(tempfile.mkdtemp(prefix="kutuphane-contract-"))
    fake = FakeBridge()
    try:
        keys = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        verifier = _verifier(work, keys)
        book_dir = work / "okf-kitap"
        shutil.copytree(TESTS / "fixtures" / "okf-kitap", book_dir)
        write_manifest(book_dir)
        with db.connect(dsn) as conn:
            authz.grant(conn, f"book:{BOOK}", "curate", "user:admin")
            catalog.publish(conn, book=BOOK, title=BOOK, files=read_source(book_dir), policy=POLICY,
                            profile=profiles.spec("chunked"), approved_by="user:admin")
            notes.create_journal(conn, book=JOURNAL, title=JOURNAL, search=True, ai_input=True, policy=POLICY,
                                 by="user:admin")
            _allow(conn, JOURNAL, "read", "propose")
            _allow(conn, BOOK, "read")
            signer = signing.generate(work / "issuer.key")
            package = packages.export(conn, BOOK, signing.load_private(work / "issuer.key"))
        with db.connect(b_dsn) as conn:  # a second installation that trusts the issuer and receives the package
            packages.trust(conn, Path(signer["public_key"]).read_bytes(), expected_fingerprint=signer["fingerprint"],
                           name="Contract", by="user:admin")
            authz.grant(conn, f"book:{BOOK}", "curate", "user:admin")
            authz.grant(conn, f"book:{BOOK}", "propose", "agent:inframedic")
            authz.grant(conn, f"book:{BOOK}", "read", "agent:inframedic")
        fake.reply = "İki yıl saklanır [1]."
        ctx = Context(dsn, b_dsn, keys, verifier, fake, package)
        with TestClient(ctx.app(), base_url=PUBLIC):  # its lifespan runs the job workers the MCP jobs need
            mcp = mcp_results(ctx)
        return {"results_mcp": mcp, "results_http": http_results(ctx)}
    finally:
        fake.server.shutdown()
        shutil.rmtree(work, ignore_errors=True)


class Context:
    def __init__(self, dsn, b_dsn, keys, verifier, fake, package):
        self.dsn, self.b_dsn, self.keys, self.verifier, self.fake, self.package = dsn, b_dsn, keys, verifier, fake, package

    def token(self, **claims) -> str:
        return token((self.keys, self.keys), **claims)

    def bearer(self, **claims) -> dict:
        return {"Authorization": f"Bearer {self.token(**claims)}"}

    def claims(self, **claims) -> dict:
        return asyncio.run(server._Verifier(self.verifier).verify_token(self.token(**claims))).claims

    def app(self, dsn=None, *, bridge=True):
        return server.create_app(dsn=dsn or self.dsn, verifier=self.verifier,
                                 bridge=self.fake.bridge() if bridge else None, model="qwen" if bridge else None,
                                 public_url=PUBLIC)

    def mcp(self, dsn=None):
        return server.build_mcp(dsn=dsn or self.dsn, verifier=self.verifier, bridge=self.fake.bridge(), model="qwen",
                                public_url=PUBLIC)


# --- MCP ---------------------------------------------------------------------------------------------------------

def _call(mcp, claims, name, args):
    access = AccessToken(token="t", client_id="contract", scopes=[], claims=claims)
    reset_token = auth_context_var.set(AuthenticatedUser(access))
    try:
        result = asyncio.run(mcp.call_tool(name, args))
    except ToolError as exc:  # the SDK refuses an argument that fails the input schema before the tool runs
        return exc
    finally:
        auth_context_var.reset(reset_token)
    return result


def _outcome(result):
    """What a client sees: the structured content, else the JSON in the text block, else plain text; and `_meta`.
    An error result is its text (the error texts are a contract too)."""
    if isinstance(result, Exception):
        return {"refused": str(result)}
    text = " ".join(c.text for c in result.content if c.type == "text")
    if result.is_error:
        return {"error": text}
    out = {}
    if result.structured_content is not None:
        out["structured"] = shape(result.structured_content)
    else:
        try:
            out["text_json"] = shape(json.loads(text))
        except ValueError:
            out["text"] = "str"
    if result.meta:
        out["meta"] = shape(result.meta)
    return {"ok": out}


def mcp_results(ctx: Context) -> dict:
    cases, mcp, mcp_b = Cases(), ctx.mcp(), ctx.mcp(ctx.b_dsn)
    agent = ctx.claims(act={"sub": "kobra-7"})
    package_agent = ctx.claims(sub="inframedic", **{"kutuphane/principal_type": "agent"})

    def call(tool, case, args, *, server_=None, claims=None):
        result = _call(server_ or mcp, claims or agent, tool, args)
        cases.add(f"{tool}:{case}", _outcome(result))
        return result

    def data(result):
        if result.structured_content is not None:
            return result.structured_content.get("result", result.structured_content)
        return json.loads(result.content[0].text)

    hit = data(call("search_library", "found", {"query": QUESTION, "max_chars": 200}))[0]["citation"]
    call("search_library", "empty", {"query": "zzzzqqqq", "book": ["yok"]})
    call("search_library", "bad_request", {"query": QUESTION, "acceptance": []})
    call("open_citation", "passage", {"handle": hit})
    call("open_citation", "malformed", {"handle": hit.rsplit("#", 1)[0]})
    call("open_citation", "not_found", {"handle": hit.rsplit("#", 1)[0] + "#999"})
    asked = data(call("ask_library", "answered", {"question": "Erişim kayıtları ne kadar saklanır?"}))
    call("ask_library", "bad_request", {"question": QUESTION, "idempotency_key": "contract-key-1"})
    job = data(call("ask_library", "queued", {"question": QUESTION, "background": True,
                                              "idempotency_key": "contract-key-2"}))
    call("reopen_answer", "found", {"answer_id": asked["id"]})
    call("reopen_answer", "not_found", {"answer_id": "an_unknown"})
    books = data(call("list_books", "found", {}))
    content_id = next(b["content_id"] for b in books if b["book"] == BOOK)
    call("read_document", "found", {"book": BOOK, "content_id": content_id, "path": "index.md"})
    call("read_document", "not_found", {"book": BOOK, "content_id": content_id, "path": "yok.md"})
    call("list_files", "found", {"book": BOOK, "limit": 2})
    call("list_files", "forbidden", {"book": "gizli"})
    _wait_job(lambda: data(_call(mcp, agent, "job_status", {"job_id": job["job_id"]}))["status"])
    call("job_status", "found", {"job_id": job["job_id"]})  # recorded once it is settled
    call("job_result", "found", {"job_id": job["job_id"]})
    call("job_cancel", "found", {"job_id": job["job_id"]})
    for tool in ("job_status", "job_result", "job_cancel"):
        call(tool, "not_found", {"job_id": "jb_unknown"})
    first = data(call("propose_note", "created", {"book": JOURNAL, "kind": "finding", "text": "one",
                                                  "idempotency_key": "contract-note-1"}))
    second = data(call("propose_note", "created", {"book": JOURNAL, "kind": "lesson", "text": "two"}))
    call("propose_note", "decision", {"book": JOURNAL, "kind": "decision_proposal", "text": "three",
                                      "decision": {"options": ["a", "b"], "choice": "b"}})
    call("propose_note", "bad_request", {"book": JOURNAL, "kind": "nonsense", "text": "x"})
    call("link_notes", "created", {"src": second["ref"], "type": "about", "dst": first["ref"]})
    call("link_notes", "bad_request", {"src": second["ref"], "type": "nonsense", "dst": first["ref"]})
    call("open_citation", "note", {"handle": first["ref"]})
    call("verify_citations", "not_checked", {"book": JOURNAL, "citations": [f"adc@{NO_COMMIT}:f.py:1"], "at": "main"})
    call("verify_citations", "bad_request", {"book": JOURNAL, "citations": [], "at": "main"})
    call("query_notes", "found", {"sets": ["open"]})
    call("query_notes", "bad_request", {"order": "nonsense"})
    call("neighbours", "found", {"ref": first["ref"]})
    call("neighbours", "not_found", {"ref": f"{JOURNAL}@{NO_NOTE}"})
    call("record_outcome", "recorded", {"ref": first["ref"], "task_ref": "adc:run/1", "result": "passed",
                                        "idempotency_key": "contract-outcome-1"})
    call("record_outcome", "conflict", {"ref": first["ref"], "task_ref": "adc:run/1", "result": "failed",
                                        "idempotency_key": "contract-outcome-1"})
    call("confirm_origin", "found", {"ref": first["ref"]})
    call("confirm_origin", "not_found", {"ref": f"{JOURNAL}@{NO_NOTE}"})
    receipt = data(call("submit_package", "received", {"package_base64": base64.b64encode(ctx.package).decode()},
                        server_=mcp_b, claims=package_agent))
    call("submit_package", "bad_request", {"package_base64": "!!"}, server_=mcp_b, claims=package_agent)
    call("package_status", "found", {"import_id": receipt["id"]}, server_=mcp_b, claims=package_agent)
    call("package_status", "not_found", {"import_id": 999999}, server_=mcp_b, claims=package_agent)
    return cases.result()


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
    package_agent = ctx.bearer(sub="inframedic", **{"kutuphane/principal_type": "agent"})
    app, app_b = ctx.app(), ctx.app(ctx.b_dsn, bridge=False)

    with TestClient(app, base_url=PUBLIC) as client, TestClient(app_b, base_url=PUBLIC) as client_b:
        def call(method, route, case, path, *, c=client, headers=None, **kw):
            r = c.request(method, path, headers=user if headers is None else headers, **kw)
            cases.add(f"{method} {route} [{case}]", _http_outcome(r))
            return r

        def unauthenticated(method, route, path, **kw):
            call(method, route, "no token", path, headers={}, **kw)

        call("GET", "/healthz", "ok", "/healthz", headers={})
        call("GET", "/v1/whoami", "ok", "/v1/whoami")
        call("GET", "/v1/whoami", "delegated", "/v1/whoami", headers=agent)
        unauthenticated("GET", "/v1/whoami", "/v1/whoami")
        call("GET", "/v1/health", "ok", "/v1/health")
        unauthenticated("GET", "/v1/health", "/v1/health")
        found = call("GET", "/v1/search", "found", "/v1/search", params={"q": QUESTION}).json()["results"]
        call("GET", "/v1/search", "empty", "/v1/search", params={"q": "zzzzqqqq"})
        call("GET", "/v1/search", "bad request", "/v1/search", params={"q": QUESTION, "current_only": "maybe"})
        call("GET", "/v1/search", "stranger", "/v1/search", params={"q": QUESTION}, headers=ctx.bearer(sub=STRANGER))
        unauthenticated("GET", "/v1/search", "/v1/search", params={"q": QUESTION})
        handle = found[0]["citation"]
        call("GET", "/v1/citation", "passage", "/v1/citation", params={"handle": handle})
        call("GET", "/v1/citation", "malformed", "/v1/citation", params={"handle": handle.rsplit("#", 1)[0]})
        call("GET", "/v1/citation", "not found", "/v1/citation", params={"handle": handle.rsplit("#", 1)[0] + "#999"})
        unauthenticated("GET", "/v1/citation", "/v1/citation", params={"handle": handle})
        asked = call("POST", "/v1/ask", "answered", "/v1/ask", json={"question": "Erişim kayıtları ne kadar saklanır?"})
        call("POST", "/v1/ask", "not in library", "/v1/ask", json={"question": QUESTION, "book": ["gizli"]})
        queued = call("POST", "/v1/ask", "queued", "/v1/ask", json={"question": QUESTION, "background": True}).json()
        call("POST", "/v1/ask", "bad request", "/v1/ask", content=b"{")
        unauthenticated("POST", "/v1/ask", "/v1/ask", json={"question": QUESTION})
        call("GET", "/v1/answers/{answer_id}", "found", f"/v1/answers/{asked.json()['id']}")
        call("GET", "/v1/answers/{answer_id}", "not found", "/v1/answers/an_unknown")
        unauthenticated("GET", "/v1/answers/{answer_id}", f"/v1/answers/{asked.json()['id']}")
        job = queued["job_id"] if "job_id" in queued else queued["id"]
        _wait_job(lambda: client.get(f"/v1/jobs/{job}", headers=user).json()["status"])
        call("GET", "/v1/jobs/{job_id}", "found", f"/v1/jobs/{job}")  # recorded once it is settled
        call("GET", "/v1/jobs/{job_id}/result", "found", f"/v1/jobs/{job}/result")
        call("POST", "/v1/jobs/{job_id}/cancel", "found", f"/v1/jobs/{job}/cancel")
        for method, route, tail in (("GET", "/v1/jobs/{job_id}", ""), ("GET", "/v1/jobs/{job_id}/result", "/result"),
                                    ("POST", "/v1/jobs/{job_id}/cancel", "/cancel")):
            call(method, route, "not found", f"/v1/jobs/jb_unknown{tail}")
            unauthenticated(method, route, f"/v1/jobs/{job}{tail}")
        books = call("GET", "/v1/books", "found", "/v1/books").json()["books"]
        call("GET", "/v1/books", "stranger", "/v1/books", headers=ctx.bearer(sub=STRANGER))
        unauthenticated("GET", "/v1/books", "/v1/books")
        content_id = next(b["content_id"] for b in books if b["book"] == BOOK)
        call("GET", "/v1/books/{book}/files", "found", f"/v1/books/{BOOK}/files", params={"limit": 2})
        call("GET", "/v1/books/{book}/files", "forbidden", "/v1/books/gizli/files")
        call("GET", "/v1/books/{book}/files", "bad request", f"/v1/books/{BOOK}/files", params={"limit": 0})
        unauthenticated("GET", "/v1/books/{book}/files", f"/v1/books/{BOOK}/files")
        file_route = "/v1/files/{book}/{content_id}/{path:path}"
        call("GET", file_route, "found", f"/v1/files/{BOOK}/{content_id}/index.md")
        call("GET", file_route, "not found", f"/v1/files/{BOOK}/{content_id}/yok.md")
        unauthenticated("GET", file_route, f"/v1/files/{BOOK}/{content_id}/index.md")

        created = call("POST", "/v1/notes", "created", "/v1/notes", json={
            "book": JOURNAL, "kind": "finding", "text": "over http", "idempotency_key": "http-0001"}).json()
        call("POST", "/v1/notes", "retried", "/v1/notes", json={
            "book": JOURNAL, "kind": "finding", "text": "over http", "idempotency_key": "http-0001"})
        call("POST", "/v1/notes", "bad request", "/v1/notes", content=b"{")
        call("POST", "/v1/notes", "forbidden", "/v1/notes", headers=ctx.bearer(sub=STRANGER),
             json={"book": JOURNAL, "kind": "finding", "text": "x"})
        unauthenticated("POST", "/v1/notes", "/v1/notes", json={"book": JOURNAL, "kind": "finding", "text": "x"})
        other = call("POST", "/v1/notes", "created", "/v1/notes", json={
            "book": JOURNAL, "kind": "lesson", "text": "second"}).json()
        link = {"src": other["ref"], "type": "about", "dst": created["ref"]}
        call("POST", "/v1/notes/links", "created", "/v1/notes/links", json=link)
        call("POST", "/v1/notes/links", "retried", "/v1/notes/links", json=link)
        call("POST", "/v1/notes/links", "bad request", "/v1/notes/links", content=b"{")
        unauthenticated("POST", "/v1/notes/links", "/v1/notes/links", json=link)
        call("GET", "/v1/notes", "found", "/v1/notes", params=[("sets", "current"), ("sets", "open")])
        call("GET", "/v1/notes", "bad request", "/v1/notes", params={"order": "x"})
        unauthenticated("GET", "/v1/notes", "/v1/notes")
        book, nid = created["ref"].split("@")
        call("GET", "/v1/notes/{book}/{id}/neighbours", "found", f"/v1/notes/{book}/{nid}/neighbours")
        call("GET", "/v1/notes/{book}/{id}/neighbours", "not found", f"/v1/notes/{book}/{NO_NOTE}/neighbours")
        unauthenticated("GET", "/v1/notes/{book}/{id}/neighbours", f"/v1/notes/{book}/{nid}/neighbours")
        call("GET", "/v1/notes/{book}/{id}/confirmation", "found", f"/v1/notes/{book}/{nid}/confirmation")
        call("GET", "/v1/notes/{book}/{id}/confirmation", "forbidden", f"/v1/notes/{book}/{nid}/confirmation",
             headers=ctx.bearer(sub=STRANGER))
        unauthenticated("GET", "/v1/notes/{book}/{id}/confirmation", f"/v1/notes/{book}/{nid}/confirmation")
        outcome = {"ref": created["ref"], "task_ref": "adc:run/1", "result": "passed", "idempotency_key": "http-0001"}
        call("POST", "/v1/outcomes", "recorded", "/v1/outcomes", json=outcome)
        call("POST", "/v1/outcomes", "conflict", "/v1/outcomes", json={**outcome, "result": "failed"})
        call("POST", "/v1/outcomes", "bad request", "/v1/outcomes", json={**outcome, "idempotency_key": None})
        unauthenticated("POST", "/v1/outcomes", "/v1/outcomes", json=outcome)
        verify = {"book": JOURNAL, "citations": [f"adc@{NO_COMMIT}:f.py:1"], "at": "main"}
        call("POST", "/v1/citations/verify", "not checked", "/v1/citations/verify", json=verify)
        call("POST", "/v1/citations/verify", "bad request", "/v1/citations/verify", json={**verify, "citations": []})
        unauthenticated("POST", "/v1/citations/verify", "/v1/citations/verify", json=verify)

        sent = call("POST", "/v1/packages", "received", "/v1/packages", c=client_b, headers=package_agent,
                    content=ctx.package, ).json()
        call("POST", "/v1/packages", "bad request", "/v1/packages", c=client_b, headers=package_agent, content=b"x")
        unauthenticated("POST", "/v1/packages", "/v1/packages", c=client_b, content=ctx.package)
        call("GET", "/v1/packages/{import_id}", "found", f"/v1/packages/{sent['id']}", c=client_b,
             headers=package_agent)
        call("GET", "/v1/packages/{import_id}", "not found", "/v1/packages/999999", c=client_b, headers=package_agent)
        unauthenticated("GET", "/v1/packages/{import_id}", f"/v1/packages/{sent['id']}", c=client_b)
    return cases.result()
