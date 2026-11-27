"""#139 (option 2): a consumer application submits a signed package over HTTP or MCP; the same verification as CLI
`receive` runs; a person approves with the CLI (`approve-import`); only changed passages embed again. The submitter
needs `propose` on the target book (no new grant mode); the issuer is the verified signature (D74); the submitter is
recorded from the verified token (D70)."""
import asyncio
import base64
import json
import os

import pytest
from starlette.testclient import TestClient

from kutuphane import authz, catalog, packages, profiles, server, signing, vectors
from kutuphane.policy import make_policy
from kutuphane.source import read_source
from test_identity import token
from test_kstd import write_manifest
from test_server import PUBLIC, call_tool, keys, verifier  # noqa: F401
from test_egress_audit import FakeBridge
from test_vectors import current_texts, embedded_inputs

AGENT = "agent:inframedic"
POLICY = make_policy(sensitivity="normal", egress="local_only", protection="standard")


@pytest.fixture
def fake():
    f = FakeBridge()
    yield f
    f.server.shutdown()


@pytest.fixture
def signer(tmp_path):
    info = signing.generate(tmp_path / "a.key")
    return signing.load_private(tmp_path / "a.key"), info


@pytest.fixture
def b_dsn(conn_b):
    return os.environ["KUTUPHANE_TEST_DSN"] + "?options=-csearch_path%3Dinstall_b,public"


@pytest.fixture
def setup(conn, conn_b, okf_dir, signer, verifier, b_dsn):
    """Installation A (the consumer, e.g. InfraMedic) signs its book; installation B trusts A's key."""
    private, info = signer
    write_manifest(okf_dir)
    catalog.publish(conn, book="runbooks", title="Runbooks", files=read_source(okf_dir), policy=POLICY,
                    profile=profiles.spec("chunked"))
    pem = open(info["public_key"], "rb").read()
    packages.trust(conn_b, pem, expected_fingerprint=info["fingerprint"], name="InfraMedic", by="user:admin")
    authz.grant(conn_b, "book:runbooks", "curate", "user:admin")  # D85: approving a package needs curate
    app = server.create_app(dsn=b_dsn, verifier=verifier, bridge=None, model=None, public_url=PUBLIC)
    return app, packages.export(conn, "runbooks", private), info["fingerprint"]


def agent_auth(keys):  # noqa: F811
    return {"Authorization": "Bearer " + token(keys, sub="inframedic", azp="inframedic",
                                               **{"kutuphane/principal_type": "agent"})}


def test_submit_needs_propose_on_the_book_and_stores_nothing_without_it(setup, keys, conn_b):  # noqa: F811
    app, pkg, _ = setup
    with TestClient(app) as client:
        r = client.post("/v1/packages", content=pkg, headers=agent_auth(keys))
    assert r.status_code == 403
    assert conn_b.execute("SELECT count(*) FROM package_import").fetchone()[0] == 0
    assert conn_b.execute("SELECT allowed, mode, object FROM access_event WHERE action = 'submit_package'"
                          ).fetchall() == [(False, "propose", "book:runbooks")]


def test_submit_over_http_then_a_person_approves_and_only_changed_passages_embed(setup, keys, conn, conn_b,  # noqa: F811
                                                                                okf_dir, signer, fake):
    app, pkg, issuer = setup
    authz.grant(conn_b, "book:runbooks", "propose", AGENT)
    authz.grant(conn_b, "book:runbooks", "read", AGENT)  # the diff names catalog files: it needs read
    with TestClient(app) as client:
        auth = agent_auth(keys)
        r = client.post("/v1/packages", content=pkg, headers={**auth, "content-type": "application/x-tar"})
        assert r.status_code == 201, r.text
        receipt = r.json()
        assert receipt["status"] in ("received", "findings") and receipt["book"] == "runbooks"
        assert receipt["issuer"] == issuer and receipt["diff"]["added"]
        assert catalog.book_state(conn_b, "runbooks") is None                    # nothing published yet
        assert client.get(f"/v1/packages/{receipt['id']}", headers=auth).json() == receipt
        other = {"Authorization": "Bearer " + token(keys, sub="mehmet")}
        assert client.get(f"/v1/packages/{receipt['id']}", headers=other).status_code == 404
        assert conn_b.execute("SELECT issuer, submitted_by, submitted_for, submitted_channel, submitted_client_id "
                              "FROM package_import WHERE id = %s", (receipt["id"],)).fetchone() == (
            issuer, AGENT, None, "http", "inframedic")

        # approve-import stays a human CLI act: no route approves
        assert client.post(f"/v1/packages/{receipt['id']}", headers=auth).status_code in (404, 405)
        first = packages.approve(conn_b, receipt["id"], by="user:admin", policy=POLICY)
        vectors.index(conn_b, fake.embedder(), "runbooks")
        assert client.get(f"/v1/packages/{receipt['id']}", headers=auth).json()["status"] == "approved"

        # a new version with one changed file: only its passages embed again (G17)
        changed = "runbook/yedek-geri-yukleme.md"
        with open(okf_dir / changed, "a", encoding="utf-8") as f:
            f.write("\n5. Geri yükleme süresini olay kaydına yaz.\n")
        write_manifest(okf_dir)
        catalog.publish(conn, book="runbooks", title="Runbooks", files=read_source(okf_dir), policy=POLICY,
                        profile=profiles.spec("chunked"))
        second = client.post("/v1/packages", content=packages.export(conn, "runbooks", signer[0]), headers=auth).json()
        assert second["status"] in ("received", "findings")
        assert second["diff"]["changed"] == ["kstd.yaml", changed]
        authz.grant(conn_b, "book:runbooks", "read", "user:ayse")
        reader = {"Authorization": "Bearer " + token(keys)}

        def found():
            hits = client.get("/v1/search", params={"q": "geri yükleme süresini olay kaydına"}, headers=reader)
            return any("olay kaydına" in h["text"] for h in hits.json()["results"])
        assert not found()                                                       # pending: search does not see it
        since = len(fake.requests)
        published = packages.approve(conn_b, second["id"], by="user:admin", policy=POLICY)
        assert published.content_id != first.content_id
        result = vectors.index(conn_b, fake.embedder(), "runbooks")
        rows, sent = current_texts(conn_b, "runbooks"), embedded_inputs(fake, since)
        assert sent and set(sent) <= {t for p, _, t in rows if p == changed}
        assert result.embedded == len(sent) and result.reused == len(rows) - len(sent) > 0
        assert found()                                                           # approved: search sees it


def test_propose_without_read_gets_no_catalog_diff(setup, keys, conn_b):  # noqa: F811
    """Astra review #20: the diff lists the receiving catalog's files (removed) and is an equality oracle (changed):
    `propose` alone gets the status without it; a current `read` shows it."""
    app, pkg, _ = setup
    authz.grant(conn_b, "book:runbooks", "propose", AGENT)
    with TestClient(app) as client:
        auth = agent_auth(keys)
        receipt = client.post("/v1/packages", content=pkg, headers=auth).json()
        assert receipt["status"] in ("received", "findings") and receipt["diff"] is None
        assert client.get(f"/v1/packages/{receipt['id']}", headers=auth).json()["diff"] is None
        authz.grant(conn_b, "book:runbooks", "read", AGENT)
        assert client.get(f"/v1/packages/{receipt['id']}", headers=auth).json()["diff"]["added"]


def test_a_failed_verification_is_kept_and_reported_refused(setup, keys, conn_b):  # noqa: F811
    app, pkg, _ = setup
    authz.grant(conn_b, "book:runbooks", "propose", AGENT)
    with TestClient(app) as client:
        auth = agent_auth(keys)
        first = client.post("/v1/packages", content=pkg, headers=auth)
        assert first.status_code == 201
        packages.approve(conn_b, first.json()["id"], by="user:admin", policy=POLICY)
        again = client.post("/v1/packages", content=pkg, headers=auth)
        assert again.status_code == 201 and client.get(f"/v1/packages/{again.json()['id']}",
                                                       headers=auth).json() == again.json()
    assert again.json()["status"] == "refused" and "replay" in again.json()["reasons"][0]
    assert again.json()["issuer"] is None                                  # a refused package proves no issuer


def test_size_limit_and_unreadable_input(setup, keys, conn_b, monkeypatch):  # noqa: F811
    app, pkg, _ = setup
    monkeypatch.setattr(packages, "MAX_PACKAGE_BYTES", len(pkg) - 1)
    with TestClient(app) as client:
        assert client.post("/v1/packages", content=pkg, headers=agent_auth(keys)).status_code == 413
        monkeypatch.undo()
        assert client.post("/v1/packages", content=b"not a tar", headers=agent_auth(keys)).status_code == 400
    assert conn_b.execute("SELECT count(*) FROM package_import").fetchone()[0] == 0


def test_a_journal_is_never_a_package_target(setup, keys, conn_b, okf_dir, signer, conn):  # noqa: F811
    from kutuphane import notes
    app, _, _ = setup
    notes.create_journal(conn_b, book="runbooks", title="j", search=True, ai_input=True, policy=POLICY,
                         by="user:admin")
    authz.grant(conn_b, "book:runbooks", "propose", AGENT)
    with TestClient(app) as client:
        r = client.post("/v1/packages", content=packages.export(conn, "runbooks", signer[0]), headers=agent_auth(keys))
    assert r.status_code == 400 and "journal" in r.json()["error"]


def test_submit_package_and_package_status_over_mcp(setup, keys, verifier, conn_b, b_dsn):  # noqa: F811
    _app, pkg, issuer = setup
    authz.grant(conn_b, "book:runbooks", "propose", AGENT)
    mcp = server.build_mcp(dsn=b_dsn, verifier=verifier, bridge=None, model=None, public_url=PUBLIC)
    claims = asyncio.run(server._Verifier(verifier).verify_token(
        token(keys, sub="inframedic", azp="inframedic", **{"kutuphane/principal_type": "agent"}))).claims
    content, _ = call_tool(mcp, claims, "submit_package", {"package_base64": base64.b64encode(pkg).decode()})
    out = json.loads(content[0].text)
    assert out["status"] in ("received", "findings") and out["issuer"] == issuer
    content, _ = call_tool(mcp, claims, "package_status", {"import_id": out["id"]})
    assert json.loads(content[0].text) == out
    assert conn_b.execute("SELECT submitted_channel FROM package_import").fetchone()[0] == "mcp"
    with pytest.raises(Exception, match="not base64"):
        call_tool(mcp, claims, "submit_package", {"package_base64": "***"})


def test_package_status_names_who_decided_it_and_null_before(setup, keys, conn_b):  # noqa: F811  # #208
    app, pkg, _ = setup
    authz.grant(conn_b, "book:runbooks", "propose", AGENT)
    with TestClient(app) as client:
        auth = agent_auth(keys)
        receipt = client.post("/v1/packages", content=pkg, headers=auth).json()
        assert receipt["decided_by"] is None and receipt["decided_at"] is None
        packages.approve(conn_b, receipt["id"], by="user:admin", policy=POLICY)
        assert client.get(f"/v1/packages/{receipt['id']}", headers=auth).json()["decided_by"] == "user:admin"


# --- #268: an early refusal must not reset the connection while the body is still sent ---------------------------
# The release ingress streams the upload (`proxy_request_buffering off`). When Core answered 401 or 413 and closed with
# the body unread, the kernel reset the connection; nginx saw the reset and showed 502 instead of Core's answer.

@pytest.fixture
def live(setup):
    """The app of `setup` behind a real uvicorn on a free local port (HTTP over a socket, not the test client)."""
    import threading
    import time

    import uvicorn
    server_ = uvicorn.Server(uvicorn.Config(setup[0], host="127.0.0.1", port=0, log_level="warning"))
    thread = threading.Thread(target=server_.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server_.started and time.monotonic() < deadline:
        time.sleep(0.01)
    assert server_.started, "uvicorn did not start"
    yield server_.servers[0].sockets[0].getsockname()[1]
    server_.should_exit = True
    thread.join(10)


def post_raw(port: int, size: int, headers: dict | None = None) -> tuple[bool, int, dict]:
    """POST `size` bytes to /v1/packages like a streaming client: headers first, then the whole body.
    Returns (the whole body was sent without a reset, the status, the JSON of the answer)."""
    import socket
    head = {"Host": f"127.0.0.1:{port}", "Content-Type": "application/x-tar", "Content-Length": str(size),
            "Connection": "close", **(headers or {})}
    with socket.create_connection(("127.0.0.1", port), timeout=30) as s:
        s.sendall(("POST /v1/packages HTTP/1.1\r\n" + "".join(f"{k}: {v}\r\n" for k, v in head.items()) + "\r\n").encode())
        chunk, sent_whole = b"x" * 65536, True
        try:
            for _ in range(size // len(chunk)):
                s.sendall(chunk)
        except OSError:
            sent_whole = False
        raw = b""
        try:
            while part := s.recv(65536):
                raw += part
        except OSError:
            pass
    assert raw.startswith(b"HTTP/1.1 "), "no answer from Core"
    status = int(raw.split(b" ", 2)[1])
    return sent_whole, status, json.loads(raw.partition(b"\r\n\r\n")[2])


@pytest.mark.parametrize("headers", [None, {"Authorization": "Bearer x.y.z"}], ids=["no-token", "bad-token"])
def test_refusal_without_a_valid_token_reaches_a_client_that_still_sends(live, headers, conn_b):
    """The drain is response-agnostic (it runs before any response that is sent with the body unread), so the same path
    covers every early status: 401 here, 413 below. The package route has no early 403 of its own: `gate.Denied` comes
    from `submit`, after the whole body is read, so there is nothing unread to drain for it."""
    for _ in range(3):
        sent_whole, status, body = post_raw(live, 16 * 1024 * 1024, headers)
        assert sent_whole, "Core closed the connection with the body unread (a proxy would answer 502)"
        assert status == 401 and body == {"error": "unauthenticated"}
    assert conn_b.execute("SELECT count(*) FROM package_import").fetchone()[0] == 0


def test_size_refusal_reaches_a_client_that_still_sends(live, keys, conn_b, monkeypatch):  # noqa: F811
    monkeypatch.setattr(packages, "MAX_PACKAGE_BYTES", 1024 * 1024)
    for _ in range(3):  # a declared length above the limit, and nothing is stored
        sent_whole, status, body = post_raw(live, 4 * 1024 * 1024, agent_auth(keys))
        assert sent_whole and status == 413 and "too large" in body["error"]
    assert conn_b.execute("SELECT count(*) FROM package_import").fetchone()[0] == 0


def test_a_request_that_waits_for_100_continue_gets_the_refusal_and_sends_no_body(live):
    """The client holds its body back until the server says `100 Continue`: the refusal is the answer, and Core must
    not ask for the body (a drain would)."""
    import socket
    request = (f"POST /v1/packages HTTP/1.1\r\nHost: 127.0.0.1:{live}\r\nContent-Length: 4194304\r\n"
               "Expect: 100-continue\r\nConnection: keep-alive\r\n\r\n")
    with socket.create_connection(("127.0.0.1", live), timeout=10) as s:
        s.sendall(request.encode())
        raw = s.recv(65536)
        assert raw.startswith(b"HTTP/1.1 401 ") and b"connection: close" in raw.lower()   # its body is unread


def test_a_declared_length_above_the_drain_bound_gets_the_refusal_and_a_closed_connection(live):
    """The declared body (400 MiB) is above the bound of the drain (300 MiB): it is not drained, so the answer must
    close the connection, which is not fit for a next request with that body unread."""
    import socket
    request = (f"POST /v1/packages HTTP/1.1\r\nHost: 127.0.0.1:{live}\r\nContent-Length: {400 * 1024 * 1024}\r\n"
               "Connection: keep-alive\r\n\r\n")
    with socket.create_connection(("127.0.0.1", live), timeout=10) as s:
        s.sendall(request.encode() + b"x" * 1024)
        raw = b""
        while b"\r\n\r\n" not in raw or b'"error"' not in raw:
            part = s.recv(65536)
            assert part, "the connection closed before the whole answer"
            raw += part
        assert raw.startswith(b"HTTP/1.1 401 ") and b"connection: close" in raw.lower()
        s.settimeout(5)
        try:
            assert s.recv(65536) == b""  # Core closed it (a reset is allowed too)
        except ConnectionResetError:
            pass


def asgi_request(chunks, headers=(), ends=True):
    """(scope, receive, send, log): a fake ASGI request that delivers `chunks` one by one. `ends`: the last chunk
    closes the body; otherwise the body goes on until the client leaves (`http.disconnect`)."""
    log = {"received": 0, "sent": []}
    index = 0

    async def receive():
        nonlocal index
        log["received"] += 1
        if index == len(chunks):
            return {"type": "http.disconnect"}
        index += 1
        return {"type": "http.request", "body": chunks[index - 1], "more_body": not (ends and index == len(chunks))}

    async def send(message):
        log["sent"].append((message["type"], log["received"]))
        if message["type"] == "http.response.start":
            log["headers"] = message.get("headers", [])

    scope = {"type": "http", "headers": [(k.encode(), v.encode()) for k, v in headers]}
    return scope, receive, send, log


async def refuse(scope, receive, send):  # an app that answers without reading
    await send({"type": "http.response.start", "status": 401, "headers": []})
    await send({"type": "http.response.body", "body": b"{}"})


def test_drain_reads_the_rest_of_the_body_before_the_response_starts():
    scope, receive, send, log = asgi_request([b"a" * 10] * 5)
    asyncio.run(packages.DrainUnreadBody(refuse, 1000)(scope, receive, send))
    assert log["received"] == 5 and log["sent"][0] == ("http.response.start", 5)


def test_drain_does_not_read_again_a_body_the_app_has_read():
    scope, receive, send, log = asgi_request([b"a" * 10] * 3)

    async def reads_all(scope, receive, send):
        while (await receive())["more_body"]:
            pass
        await refuse(scope, receive, send)

    asyncio.run(packages.DrainUnreadBody(reads_all, 1000)(scope, receive, send))
    assert log["received"] == 3                                    # a second read would wait for ever


def test_drain_is_bounded_and_skips_a_declared_length_above_the_bound():
    scope, receive, send, log = asgi_request([b"a" * 4] * 100, ends=False)
    asyncio.run(packages.DrainUnreadBody(refuse, 10)(scope, receive, send))
    assert log["received"] == 3 and log["sent"][0][0] == "http.response.start"   # stops after 12 bytes: above the bound

    scope, receive, send, log = asgi_request([b"a"], headers=[("content-length", "11")])
    asyncio.run(packages.DrainUnreadBody(refuse, 10)(scope, receive, send))
    assert log["received"] == 0                                    # the proxy refuses such a body itself
    assert (b"connection", b"close") in log["headers"]             # the unread body is not left on a reusable connection

    scope, receive, send, log = asgi_request([b"a"], headers=[("content-length", "10")])
    asyncio.run(packages.DrainUnreadBody(refuse, 10)(scope, receive, send))
    assert log["received"] == 1 and (b"connection", b"close") not in log["headers"]   # drained whole: keep-alive stays


def test_drain_stops_when_the_client_leaves():
    scope, receive, send, log = asgi_request([b"a" * 4] * 2, ends=False)
    asyncio.run(packages.DrainUnreadBody(refuse, 10 ** 6)(scope, receive, send))
    assert log["received"] == 3 and log["sent"][0][0] == "http.response.start"


def test_drain_reads_the_rest_after_the_app_read_the_body_partly():
    scope, receive, send, log = asgi_request([b"a" * 10] * 5)

    async def reads_one_chunk_then_refuses(scope, receive, send):
        assert (await receive())["more_body"]
        await refuse(scope, receive, send)

    asyncio.run(packages.DrainUnreadBody(reads_one_chunk_then_refuses, 1000)(scope, receive, send))
    assert log["received"] == 5 and log["sent"][0] == ("http.response.start", 5)   # the response waits for the rest


def test_drain_gives_up_when_its_time_budget_ends_and_the_answer_closes_the_connection(monkeypatch):
    monkeypatch.setattr(packages, "DRAIN_SECONDS", 0.2)
    sent = []

    async def receive():  # a client that sends nothing more and does not leave
        await asyncio.sleep(3600)

    async def send(message):
        sent.append(message)

    async def run():
        await asyncio.wait_for(packages.DrainUnreadBody(refuse, 1000)({"type": "http", "headers": []}, receive, send), 5)

    asyncio.run(run())
    assert sent[0]["type"] == "http.response.start" and (b"connection", b"close") in sent[0]["headers"]


def test_a_client_that_trickles_its_body_gets_the_refusal_when_the_drain_budget_ends(live, monkeypatch):
    """nginx `client_body_timeout` is an idle timeout between two reads: a client that sends one byte after the other
    would hold Core for ever. The refusal comes when the budget ends, with `Connection: close`, and Core closes."""
    import select
    import socket
    import time
    monkeypatch.setattr(packages, "DRAIN_SECONDS", 1.0)
    request = (f"POST /v1/packages HTTP/1.1\r\nHost: 127.0.0.1:{live}\r\nContent-Length: 1048576\r\n"
               "Connection: keep-alive\r\n\r\n")
    with socket.create_connection(("127.0.0.1", live), timeout=10) as s:
        s.sendall(request.encode())
        started, trickled, raw = time.monotonic(), 0, b""
        while time.monotonic() - started < 8:      # one byte every 0.1 s: 1 MiB would need more than a day
            s.sendall(b"x")
            trickled += 1
            if select.select([s], [], [], 0.1)[0]:
                raw = s.recv(65536)
                break
        answered_in = time.monotonic() - started
        assert raw.startswith(b"HTTP/1.1 401 "), "no refusal while the client trickles"
        assert 0.9 <= answered_in < 4, answered_in   # the budget (1 s) plus a margin
        assert trickled < 1048576 and b"connection: close" in raw.lower()
        s.settimeout(5)
        try:
            while s.recv(65536):  # the server task has ended: Core closes the connection (a reset is allowed)
                pass
        except ConnectionResetError:
            pass
