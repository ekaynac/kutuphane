"""M1e: HTTP API and Kütüphane MCP. The caller is only what a verified token says (AT-11, Core side);
human (HTTP) and agent (MCP) reach the same evidence (AT-03)."""
import asyncio
import json
import os
import re
import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from mcp.server.auth.middleware.auth_context import auth_context_var
from mcp.server.auth.middleware.bearer_auth import AuthenticatedUser
from starlette.testclient import TestClient

from kutuphane import authz, catalog, llmdap, profiles, retrieval, server, snippets
from kutuphane.identity import Verifier
from kutuphane.policy import make_policy
from kutuphane.source import read_source
from test_egress_audit import FakeBridge
from test_identity import AUD, ISS, token

U, A = "user:ayse", "agent:kobra-7"
PUBLIC = "http://kutuphane.test"


@pytest.fixture(scope="module")
def keys():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048), \
        rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture
def verifier(keys, tmp_path):
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(keys[0].public_key()))
    path = tmp_path / "jwks.json"
    path.write_text(json.dumps({"keys": [{**jwk, "kid": "k1", "use": "sig", "alg": "RS256"}]}))
    return Verifier.from_files(ISS, AUD, path)


@pytest.fixture
def fake():
    f = FakeBridge()
    yield f
    f.server.shutdown()


@pytest.fixture
def app_env(conn, okf_dir, verifier, fake):
    r = catalog.publish(conn, book="kitap", title="kitap", files=read_source(okf_dir),
                        policy=make_policy(sensitivity="normal", egress="local_only", protection="standard"),
                        profile=profiles.spec("chunked"))
    authz.grant(conn, "book:kitap", "read", U)
    dsn = os.environ["KUTUPHANE_TEST_DSN"]
    app = server.create_app(dsn=dsn, verifier=verifier, bridge=fake.bridge(), model="qwen", public_url=PUBLIC)
    return app, r, dsn


def bearer(keys, **claims):
    return {"Authorization": f"Bearer {token(keys, **claims)}"}


def test_no_token_or_bad_token_is_401(app_env, keys):
    app, _, _ = app_env
    with TestClient(app) as client:
        assert client.get("/healthz").status_code == 200
        r = client.get("/v1/search", params={"q": "kayıt"})
        assert r.status_code == 401 and r.headers["www-authenticate"] == "Bearer"
        assert client.get("/v1/search", params={"q": "kayıt"}, headers={"Authorization": "Bearer x.y.z"}).status_code == 401
        assert client.get("/v1/search", params={"q": "kayıt"}, headers=bearer(keys, key=1)).status_code == 401


def test_headers_cannot_change_who_is_calling(app_env, keys):  # AT-11
    app, _, _ = app_env
    with TestClient(app) as client:
        spoof = {**bearer(keys, sub="mehmet"), "x-llmdap-user": U, "x-kutuphane-principal": U,
                 "x-on-behalf-of": U}
        r = client.get("/v1/search", params={"q": "kayıtlar saklanır"}, headers=spoof)
        assert r.status_code == 200 and r.json()["results"] == []          # mehmet has no rights


def test_search_citation_file_and_errors(app_env, keys):
    app, published, _ = app_env
    with TestClient(app) as client:
        h = bearer(keys)
        results = client.get("/v1/search", params={"q": "kayıtlar saklanır"}, headers=h).json()["results"]
        handle = results[0]["citation"]
        cited = client.get("/v1/citation", params={"handle": handle}, headers=h).json()
        assert cited["text"] == results[0]["text"]
        f = client.get(f"/v1/files/kitap/{published.content_id}/politika/veri-saklama.md", headers=h)
        assert f.status_code == 200 and f.headers["content-type"].startswith("text/markdown")
        assert client.get("/v1/citation", params={"handle": "bozuk"}, headers=h).status_code == 400
        assert client.get(f"/v1/files/kitap/{published.content_id}/../etc/passwd", headers=h).status_code in (400, 404)
        assert client.get("/v1/search", params={"q": "kayıt"}, headers=bearer(keys, sub="mehmet")).json()["results"] == []
        assert client.get("/v1/citation", params={"handle": handle}, headers=bearer(keys, sub="mehmet")).status_code == 403


def test_ask_and_reopen_over_http(app_env, keys, fake):
    app, _, _ = app_env
    fake.reply = "İki yıl saklanır [1]."
    with TestClient(app) as client:
        h = bearer(keys)
        asked = client.post("/v1/ask", json={"question": "Erişim kayıtları ne kadar saklanır?"}, headers=h).json()
        assert asked["status"] == "answered" and asked["correlation_id"]
        again = client.get(f"/v1/answers/{asked['id']}", headers=h).json()
        assert again["body"] == "İki yıl saklanır [1]."
        assert client.post("/v1/ask", content=b"{", headers=h).status_code == 400


class ToolFailed(Exception):
    pass


def call_tool(mcp, actor_claims: dict, name: str, args: dict):
    """SDK v2 (docs/24 §12.1): `call_tool` gives a `CallToolResult`. The adapter returns (content blocks, structured
    content) and raises with the message text when the result is an error."""
    from mcp.server.auth.provider import AccessToken
    access = AccessToken(token="t", client_id="test", scopes=[], claims=actor_claims)
    reset = auth_context_var.set(AuthenticatedUser(access))
    try:
        result = asyncio.run(mcp.call_tool(name, args))
    finally:
        auth_context_var.reset(reset)
    if result.is_error:
        raise ToolFailed(" ".join(c.text for c in result.content if c.type == "text"))
    return result.content, result.structured_content


def test_mcp_agent_and_http_user_see_the_same_evidence(app_env, keys, verifier, conn):  # AT-03
    from datetime import datetime, timedelta, timezone
    app, _, dsn = app_env
    authz.delegate(conn, delegator=U, delegate_to=A, obj="book:kitap", mode="read",
                   expires_at=datetime.now(timezone.utc) + timedelta(hours=1))
    with TestClient(app) as client:
        human = client.get("/v1/search", params={"q": "kayıtlar saklanır"}, headers=bearer(keys)).json()["results"]
    mcp = server.build_mcp(dsn=dsn, verifier=verifier, bridge=None, model=None, public_url=PUBLIC)
    tokens = asyncio.run(server._Verifier(verifier).verify_token(token(keys, act={"sub": "kobra-7"})))
    out = call_tool(mcp, tokens.claims, "search_library", {"query": "kayıtlar saklanır"})
    _content, structured = out
    agent_results = structured["result"]
    assert [r["citation"] for r in agent_results] == [r["citation"] for r in human]


def test_scope_filters_over_http_and_mcp(app_env, keys, verifier, conn, okf_dir, fake):  # G14
    app, _, dsn = app_env
    catalog.publish(conn, book="gizli", title="gizli", files=read_source(okf_dir),
                    policy=make_policy(sensitivity="normal", egress="local_only", protection="standard"),
                    profile=profiles.spec("chunked"))                    # U may not read it
    q = "kayıtlar saklanır yedek geri yükleme"
    with TestClient(app) as client:
        h = bearer(keys)
        runbook = client.get("/v1/search", params={"q": q, "path": "runbook/", "book": ["kitap", "gizli"]},
                             headers=h).json()["results"]
        assert runbook and all(r["citation"].startswith("kitap@") and "/runbook/" in r["citation"] for r in runbook)
        assert client.get("/v1/search", params={"q": q, "book": "gizli"}, headers=h).json()["results"] == []
        assert client.get("/v1/search", params={"q": q, "origin": "llm"}, headers=h).status_code == 400
        assert client.get("/v1/search", params={"q": q, "current_only": "maybe"}, headers=h).status_code == 400
        assert client.get("/v1/search", params={"q": q, "current_only": "true"}, headers=h).json()["results"]
        fake.reply = "Kayıtlar saklanır [1]."
        asked = client.post("/v1/ask", json={"question": q, "book": ["gizli"]}, headers=h).json()
        assert asked["status"] == "not_in_library" and asked["citations"] == []
        assert client.post("/v1/ask", json={"question": q, "path": "../x"}, headers=h).status_code == 400
    mcp = server.build_mcp(dsn=dsn, verifier=verifier, bridge=None, model=None, public_url=PUBLIC)
    tokens = asyncio.run(server._Verifier(verifier).verify_token(token(keys)))
    _content, structured = call_tool(mcp, tokens.claims, "search_library", {"query": q, "path": "runbook/"})
    assert [r["citation"] for r in structured["result"]] == [r["citation"] for r in runbook]
    _content, structured = call_tool(mcp, tokens.claims, "search_library", {"query": q, "book": ["gizli"]})
    assert structured["result"] == []


def test_mcp_endpoint_requires_a_token(app_env, keys):
    app, _, _ = app_env
    init = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                       "clientInfo": {"name": "test", "version": "0"}}}
    headers = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
    with TestClient(app, base_url=PUBLIC) as client:
        assert client.post("/mcp", json=init, headers=headers).status_code == 401
        ok = client.post("/mcp", json=init, headers={**headers, **bearer(keys)})
        assert ok.status_code == 200, ok.text


def test_security_headers_and_whoami(app_env, keys):
    app, _, _ = app_env
    with TestClient(app) as client:
        r = client.get("/v1/whoami", headers=bearer(keys, act={"sub": "kobra-7"}))
        assert r.json() == {"principal": "agent:kobra-7", "on_behalf_of": "user:ayse"}
        csp = r.headers["content-security-policy"]
        assert "default-src 'none'" in csp and "img-src 'self'" in csp and "frame-ancestors 'none'" in csp
        assert r.headers["x-frame-options"] == "DENY" and r.headers["referrer-policy"] == "no-referrer"


def test_server_refuses_a_schema_it_does_not_match(conn, monkeypatch, verifier, tmp_path):
    conn.execute("DELETE FROM schema_migration WHERE name = '007_answer.sql'")
    monkeypatch.setenv("KUTUPHANE_DSN", os.environ["KUTUPHANE_TEST_DSN"])
    monkeypatch.setenv("KUTUPHANE_PUBLIC_URL", PUBLIC)
    monkeypatch.setenv("KUTUPHANE_ANSWER_MODEL", "qwen")
    monkeypatch.setenv("KUTUPHANE_OIDC_ISSUER", ISS)
    monkeypatch.setenv("KUTUPHANE_OIDC_AUDIENCE", AUD)
    monkeypatch.setenv("KUTUPHANE_OIDC_JWKS", str(tmp_path / "unused.json"))
    with pytest.raises(RuntimeError, match="kutuphane migrate"):
        server.app_from_env()


def _light_env(monkeypatch, tmp_path):
    """The light install (#76): no LLMDAP, no model route, no answer model."""
    for name in (*llmdap.ENV.values(), *llmdap.EMBED_ENV.values(), *llmdap.RERANK_ENV.values(),
                 "KUTUPHANE_ANSWER_MODEL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("KUTUPHANE_DSN", os.environ["KUTUPHANE_TEST_DSN"])
    monkeypatch.setenv("KUTUPHANE_PUBLIC_URL", PUBLIC)
    monkeypatch.setenv("KUTUPHANE_OIDC_ISSUER", ISS)
    monkeypatch.setenv("KUTUPHANE_OIDC_AUDIENCE", AUD)
    monkeypatch.setenv("KUTUPHANE_OIDC_JWKS", str(tmp_path / "jwks.json"))  # written by the verifier fixture


def test_light_install_searches_full_text_and_refuses_answers(conn, monkeypatch, verifier, tmp_path, keys, okf_dir):
    catalog.publish(conn, book="kitap", title="kitap", files=read_source(okf_dir),
                    policy=make_policy(sensitivity="normal", egress="local_only", protection="standard"),
                    profile=profiles.spec("chunked"))
    authz.grant(conn, "book:kitap", "read", U)
    _light_env(monkeypatch, tmp_path)
    app = server.app_from_env()                  # starts without LLMDAP and without KUTUPHANE_ANSWER_MODEL
    with TestClient(app) as client:
        h = bearer(keys)
        hits = client.get("/v1/search", params={"q": "kayıtlar saklanır"}, headers=h).json()["results"]
        assert hits and all(r["citation"].startswith("kitap@") for r in hits)
        for body in ({"question": "Kayıtlar ne kadar saklanır?"},
                     {"question": "Kayıtlar ne kadar saklanır?", "background": True}):
            r = client.post("/v1/ask", json=body, headers=h)
            assert r.status_code == 503 and r.json() == {"error": server.NO_ANSWERS}
    assert conn.execute("SELECT count(*) FROM model_call").fetchone()[0] == 0
    assert conn.execute("SELECT count(*) FROM ask_job").fetchone()[0] == 0
    mcp = server.build_mcp(dsn=os.environ["KUTUPHANE_TEST_DSN"], verifier=verifier, bridge=None, model=None,
                           public_url=PUBLIC)
    claims = asyncio.run(server._Verifier(verifier).verify_token(token(keys))).claims
    assert "ask_library" not in [t.name for t in asyncio.run(mcp.list_tools())]    # #121: not listed at all
    with pytest.raises(Exception, match="ask_library"):
        call_tool(mcp, claims, "ask_library", {"question": "Kayıtlar ne kadar saklanır?"})
    _content, structured = call_tool(mcp, claims, "search_library", {"query": "kayıtlar saklanır"})
    assert [r["citation"] for r in structured["result"]] == [r["citation"] for r in hits]


def test_light_install_has_no_direct_model_path(conn, monkeypatch, verifier, tmp_path):
    """A model route without LLMDAP is refused at start: Core never calls an embedder or a reranker directly (D3)."""
    _light_env(monkeypatch, tmp_path)
    for env, route, model in ((llmdap.EMBED_ENV, "emb", "BAAI/bge-m3"),
                              (llmdap.RERANK_ENV, "rerank", "BAAI/bge-reranker-v2-m3")):
        with monkeypatch.context() as m:
            m.setenv(env["route"], route)
            m.setenv(env["model"], model)
            with pytest.raises(RuntimeError, match="LLMDAP not configured: set KUTUPHANE_LLMDAP_URL"):
                server.app_from_env()


def test_server_needs_the_answer_model_with_a_model_gateway(conn, monkeypatch, verifier, tmp_path):
    _light_env(monkeypatch, tmp_path)
    monkeypatch.setenv("KUTUPHANE_LLMDAP_URL", "http://llmdap:8787")
    with pytest.raises(RuntimeError, match="server not configured: set KUTUPHANE_ANSWER_MODEL"):
        server.app_from_env()


def test_feedback_over_http(app_env, keys):  # AT-15 through the API
    app, published, _ = app_env
    with TestClient(app) as client:
        h = bearer(keys)
        body = {"book": "kitap", "content_id": published.content_id, "path": "runbook/yedek-geri-yukleme.md",
                "outcome": "worked", "tested_on": "postgres-17"}
        assert client.post("/v1/feedback", json=body, headers=h).status_code == 201
        listed = client.get("/v1/feedback", params={k: body[k] for k in ("book", "content_id", "path")}, headers=h)
        assert [f["outcome"] for f in listed.json()] == ["worked"]
        assert client.post("/v1/feedback", json={**body, "outcome": 3}, headers=h).status_code == 400
        assert client.post("/v1/feedback", json=body, headers=bearer(keys, sub="mehmet")).status_code == 403


MCP_HEADERS = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}


def mcp_tool_over_http(client, auth: dict, name: str, args: dict) -> dict:
    """A real tools/call through /mcp (stateless transport; the reply is one SSE message)."""
    body = {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": name, "arguments": args}}
    r = client.post("/mcp", json=body, headers={**MCP_HEADERS, **auth})
    assert r.status_code == 200, r.text
    return json.loads([line[5:] for line in r.text.splitlines() if line.startswith("data:")][-1])["result"]


def test_agent_over_mcp_and_human_over_http_open_the_same_passages(app_env, keys, conn):  # AT-03, Astra #4
    from datetime import datetime, timedelta, timezone
    app, _, _ = app_env
    authz.delegate(conn, delegator=U, delegate_to=A, obj="book:kitap", mode="read",
                   expires_at=datetime.now(timezone.utc) + timedelta(hours=1))
    with TestClient(app, base_url=PUBLIC) as client:
        human = client.get("/v1/search", params={"q": "kayıtlar saklanır"}, headers=bearer(keys)).json()["results"]
        agent = bearer(keys, act={"sub": "kobra-7"})
        found = mcp_tool_over_http(client, agent, "search_library", {"query": "kayıtlar saklanır"})
        assert [r["citation"] for r in found["structuredContent"]["result"]] == [r["citation"] for r in human]
        handle = human[0]["citation"]
        opened = mcp_tool_over_http(client, agent, "open_citation", {"handle": handle})
        by_agent = json.loads(opened["content"][0]["text"])
        by_human = client.get("/v1/citation", params={"handle": handle}, headers=bearer(keys)).json()
        assert by_agent["text"] == by_human["text"] and by_agent["citation"] == by_human["citation"]


BAD_TOKENS = {
    "none": lambda keys: {},
    "not a jwt": lambda keys: {"Authorization": "Bearer x.y.z"},
    "not bearer": lambda keys: {"Authorization": f"Basic {token(keys)}"},
    "unknown key": lambda keys: bearer(keys, key=1),
    "unknown kid": lambda keys: bearer(keys, kid="k9"),
    "expired": lambda keys: bearer(keys, iat=int(time.time()) - 600, exp=int(time.time()) - 300),
    "other audience": lambda keys: bearer(keys, aud="baska"),
    "other issuer": lambda keys: bearer(keys, iss="https://idp.test/realms/baska"),
    "no subject": lambda keys: bearer(keys, sub=None),
}


@pytest.mark.parametrize("case", BAD_TOKENS)
def test_every_bad_token_is_refused_on_both_surfaces(app_env, keys, case):  # AT-11 (Core), Astra #4
    app, _, _ = app_env
    auth = BAD_TOKENS[case](keys)
    init = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                       "clientInfo": {"name": "t", "version": "0"}}}
    call = {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
            "params": {"name": "search_library", "arguments": {"query": "kayıt"}}}
    with TestClient(app, base_url=PUBLIC) as client:
        assert client.get("/v1/whoami", headers=auth).status_code == 401
        assert client.post("/mcp", json=init, headers={**MCP_HEADERS, **auth}).status_code == 401
        assert client.post("/mcp", json=call, headers={**MCP_HEADERS, **auth}).status_code == 401


def test_mcp_errors_are_uniform_and_hide_internals(app_env, keys, verifier, monkeypatch):  # Astra #4
    app, _, dsn = app_env
    mcp = server.build_mcp(dsn=dsn, verifier=verifier, bridge=None, model=None, public_url=PUBLIC)
    claims = asyncio.run(server._Verifier(verifier).verify_token(token(keys, sub="mehmet"))).claims
    with pytest.raises(Exception, match="forbidden") as denied:
        call_tool(mcp, claims, "open_citation", {"handle": "kitap@ct_x/pf_x/a.md#0"})
    assert "Denied" not in str(denied.value)

    def broken(*_a, **_k):
        raise RuntimeError("INTERNAL_MARKER database host /internal/path")
    monkeypatch.setattr(server, "op_search", broken)
    with pytest.raises(Exception) as failed:
        call_tool(mcp, claims, "search_library", {"query": "kayıt"})
    assert "internal error" in str(failed.value) and "INTERNAL_MARKER" not in str(failed.value)


def test_http_search_embeds_the_query_through_llmdap(conn, okf_dir, verifier, fake, keys):  # D31 hybrid
    from kutuphane import vectors
    catalog.publish(conn, book="kitap", title="kitap", files=read_source(okf_dir),
                    policy=make_policy(sensitivity="normal", egress="local_only", protection="standard"),
                    profile=profiles.spec("chunked"))
    authz.grant(conn, "book:kitap", "read", U)
    vectors.index(conn, fake.embedder(), "kitap")
    app = server.create_app(dsn=os.environ["KUTUPHANE_TEST_DSN"], verifier=verifier, bridge=fake.bridge(),
                            model="qwen", public_url=PUBLIC, stages=retrieval.Stages(fake.embedder()))
    with TestClient(app) as client:
        r = client.get("/v1/search", params={"q": "kayıtlar saklanır"}, headers=bearer(keys))
    assert r.status_code == 200 and r.json()["results"]
    path, headers = fake.hits[-1]
    assert path.endswith("/v1/embeddings") and headers["x-llmdap-purpose"] == "search"
    assert headers["x-llmdap-for-subject"] == U


def _probe_feature(seen: list):
    """A feature module as slices add them (docs/24 §16 P0): one MCP tool and one HTTP route."""
    import types

    from starlette.routing import Route

    def register_mcp(mcp, deps):
        @mcp.tool()
        @deps.mcp_errors
        async def probe_channel(fail: bool = False) -> dict:
            """Who is calling, and through which entry point."""
            actor = deps.mcp_actor()
            if fail:
                raise server.gate.Denied("INTERNAL_DETAIL")
            seen.append(("mcp", deps.dsn))
            return {"principal": actor.principal, "channel": actor.channel}

    def http_routes(deps, endpoint):
        async def h_probe(_request, actor):
            seen.append(("http", deps.dsn))
            return server.JSONResponse({"principal": actor.principal, "channel": actor.channel})
        return [Route("/v1/probe", endpoint(h_probe))]

    return types.SimpleNamespace(register_mcp=register_mcp, http_routes=http_routes)


def test_feature_hooks_add_tools_and_routes_with_the_server_gate(app_env, keys, verifier):  # docs/24 §16 P0
    _app, _, dsn = app_env
    seen = []
    feature = _probe_feature(seen)
    app = server.create_app(dsn=dsn, verifier=verifier, bridge=None, model=None, public_url=PUBLIC,
                            features=(feature,))
    with TestClient(app, base_url=PUBLIC) as client:
        assert client.get("/v1/probe").status_code == 401                         # the server's own auth
        r = client.get("/v1/probe", headers={**bearer(keys), "x-kutuphane-channel": "mcp"})
        assert r.json() == {"principal": U, "channel": "http"}                    # the entry point sets it
        tools = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                            headers={**MCP_HEADERS, **bearer(keys)})
        names = [t["name"] for t in json.loads([ln[5:] for ln in tools.text.splitlines()
                                                 if ln.startswith("data:")][-1])["result"]["tools"]]
        assert names[-1] == "probe_channel" and names[0] == "search_library"    # built-ins first, fixed order
        out = mcp_tool_over_http(client, bearer(keys, act={"sub": "kobra-7"}), "probe_channel", {})
        assert json.loads(out["content"][0]["text"]) == {"principal": A, "channel": "mcp"}
        failed = mcp_tool_over_http(client, bearer(keys), "probe_channel", {"fail": True})
        assert failed["isError"] and "forbidden" in failed["content"][0]["text"]
        assert "INTERNAL_DETAIL" not in json.dumps(failed)                        # the uniform MCP errors
    assert seen == [("http", dsn), ("mcp", dsn)]


# --- docs/24 §12.1, T33/T37: both protocol eras on one app ------------------------------------------------------

MODERN, LEGACY = "2026-07-28", "2025-11-25"
TOOLS = ["search_library", "open_citation", "ask_library", "reopen_answer", "read_document",
         "record_runbook_feedback", "job_status", "job_result", "job_cancel",
         "propose_note", "link_notes", "verify_citations", "query_notes", "neighbours",
         "record_outcome", "confirm_origin"]  # then FEATURES, in order
ANSWER_TOOLS = {"ask_library", "job_status", "job_result", "job_cancel"}  # only with LLMDAP (#121)
# #121: each description names the grant the tool needs, so an agent does not spend a turn to find it out.
GRANT = re.compile(r"\b(needs? (read|use|activate|propose|curate)\b|no grant)", re.IGNORECASE)


def _message(r) -> dict:
    if r.headers.get("content-type", "").startswith("text/event-stream"):
        return json.loads([ln[5:] for ln in r.text.splitlines() if ln.startswith("data:")][-1])
    return r.json()


def mcp_rpc(client, auth: dict, method: str, params: dict | None = None, *, version: str, meta: dict | None = None,
            headers: dict | None = None):
    """One request through /mcp as a client of that protocol version: a 2025-11-25 client first does `initialize`
    (stateless: every request stands alone); a 2026-07-28 client sends the per-request `_meta` envelope and the
    `Mcp-Method`/`Mcp-Name` headers. Returns (HTTP status, JSON-RPC message)."""
    params = dict(params or {})
    if version == MODERN:
        params["_meta"] = {"io.modelcontextprotocol/protocolVersion": MODERN,
                           "io.modelcontextprotocol/clientCapabilities": {}, **(meta or {})}
        era = {"MCP-Protocol-Version": MODERN, "Mcp-Method": method,
               **({"Mcp-Name": params["name"]} if "name" in params else {})}
    else:
        init = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                "params": {"protocolVersion": LEGACY, "capabilities": {},
                           "clientInfo": (meta or {}).get("io.modelcontextprotocol/clientInfo",
                                                          {"name": "t", "version": "0"})}}
        r = client.post("/mcp", json=init, headers={**MCP_HEADERS, **auth})
        if r.status_code != 200:
            return r.status_code, None
        assert _message(r)["result"]["protocolVersion"] == LEGACY
        era = {"MCP-Protocol-Version": LEGACY}
    r = client.post("/mcp", json={"jsonrpc": "2.0", "id": 2, "method": method, "params": params},
                    headers={**MCP_HEADERS, **era, **auth, **(headers or {})})
    return r.status_code, (_message(r) if r.content else None)


@pytest.mark.parametrize("version", [LEGACY, MODERN])
def test_both_protocol_versions_list_and_call_tools(app_env, keys, conn, monkeypatch, version):  # T33, bare-dict note
    from datetime import datetime, timedelta, timezone
    app, _, _ = app_env
    authz.delegate(conn, delegator=U, delegate_to=A, obj="book:kitap", mode="read",
                   expires_at=datetime.now(timezone.utc) + timedelta(hours=1))
    agent = bearer(keys, act={"sub": "kobra-7"})
    with TestClient(app, base_url=PUBLIC) as client:
        listed = [mcp_rpc(client, agent, "tools/list", version=version)[1]["result"]["tools"] for _ in range(2)]
        assert [t["name"] for t in listed[0]] == TOOLS and listed[0] == listed[1]       # stable order
        status, found = mcp_rpc(client, agent, "tools/call", {"name": "search_library",
                                                              "arguments": {"query": "kayıtlar saklanır"}},
                                version=version)
        found = found["result"]
        hits = found["structuredContent"]["result"]                                     # a list: {"result": [...]}
        assert status == 200 and hits and set(found["structuredContent"]) == {"result"}
        assert [c["text"] for c in found["content"]] == [json.dumps(h, indent=2, ensure_ascii=False) for h in hits]
        status, opened = mcp_rpc(client, agent, "tools/call", {"name": "open_citation",
                                                               "arguments": {"handle": hits[0]["citation"]}},
                                 version=version)
        opened = opened["result"]                                                       # a dict: JSON text only
        assert "structuredContent" not in opened and len(opened["content"]) == 1
        cited = json.loads(opened["content"][0]["text"])
        assert opened["content"][0]["text"] == json.dumps(cited, indent=2, ensure_ascii=False)
        assert cited["citation"] == hits[0]["citation"]

        def broken(*_a, **_k):
            raise RuntimeError("INTERNAL_MARKER /internal/path")
        monkeypatch.setattr(server, "op_search", broken)
        _, failed = mcp_rpc(client, agent, "tools/call", {"name": "search_library", "arguments": {"query": "x"}},
                            version=version)
        assert failed["result"]["isError"] and "internal error" in failed["result"]["content"][0]["text"]
        assert "INTERNAL_MARKER" not in json.dumps(failed)


@pytest.mark.parametrize("version", [LEGACY, MODERN])
@pytest.mark.parametrize("answering", [True, False])
def test_the_tool_list_depends_on_the_deployment_only(app_env, keys, verifier, version, answering):  # #121
    """Without LLMDAP there is no ask_library and no job tool. The list never depends on the caller: a reader, an
    agent and a principal with no grant get the same bytes (grants change in a session; public cache hints)."""
    app, _, dsn = app_env
    if not answering:
        app = server.create_app(dsn=dsn, verifier=verifier, bridge=None, model=None, public_url=PUBLIC)
    expected = [t for t in TOOLS if answering or t not in ANSWER_TOOLS]
    with TestClient(app, base_url=PUBLIC) as client:
        listed = [mcp_rpc(client, auth, "tools/list", version=version)[1]["result"]["tools"]
                  for auth in (bearer(keys), bearer(keys, act={"sub": "kobra-7"}), bearer(keys, sub="mehmet"))]
    assert [t["name"] for t in listed[0]] == expected
    assert listed[1] == listed[0] and listed[2] == listed[0]


def test_every_tool_description_names_its_grant(verifier, fake):  # #121
    mcp = server.build_mcp(dsn="postgresql://unused", verifier=verifier, bridge=fake.bridge(), model="qwen",
                           public_url=PUBLIC)
    tools = asyncio.run(mcp.list_tools())
    assert [t.name for t in tools] == TOOLS
    assert [t.name for t in tools if not GRANT.search(" ".join(t.description.split()))] == []
    search_tool = next(t for t in tools if t.name == "search_library")
    assert f"{snippets.MIN_CHARS}-{snippets.MAX_CHARS}" in search_tool.description
    assert "max_chars" in search_tool.input_schema["properties"]


@pytest.mark.parametrize("version", [LEGACY, MODERN])
def test_no_token_gives_401_with_resource_metadata(app_env, version):  # T33
    app, _, _ = app_env
    with TestClient(app, base_url=PUBLIC) as client:
        status, _ = mcp_rpc(client, {}, "tools/list", version=version)
        assert status == 401
        r = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, headers=MCP_HEADERS)
        assert 'resource_metadata="http://kutuphane.test/.well-known/oauth-protected-resource' \
            in r.headers["www-authenticate"]


def test_mcp_name_header_must_match_the_body(app_env, keys):  # T33: -32020
    app, _, _ = app_env
    with TestClient(app, base_url=PUBLIC) as client:
        status, msg = mcp_rpc(client, bearer(keys), "tools/call", {"name": "job_status",
                                                                   "arguments": {"job_id": "jb_" + "0" * 32}},
                              version=MODERN, headers={"Mcp-Name": "search_library"})
        assert status == 400 and msg["error"]["code"] == -32020
        status, msg = mcp_rpc(client, bearer(keys), "tools/call", {"name": "job_status",
                                                                   "arguments": {"job_id": "jb_" + "0" * 32}},
                              version=MODERN)
        assert status == 200 and "not found" in msg["result"]["content"][0]["text"]


def test_discover_advertises_client_credentials_and_cache_hints(app_env, keys):  # docs/24 §12.1, §12.4
    app, _, _ = app_env
    with TestClient(app, base_url=PUBLIC) as client:
        _, found = mcp_rpc(client, bearer(keys), "server/discover", version=MODERN)
        assert "io.modelcontextprotocol/oauth-client-credentials" in found["result"]["capabilities"]["extensions"]
        _, listed = mcp_rpc(client, bearer(keys), "tools/list", version=MODERN)
        assert listed["result"]["cacheScope"] == "public" and listed["result"]["ttlMs"] > 0


def _client_probe():
    """A feature tool and route that show what the server took from the token."""
    import types

    from starlette.routing import Route

    def who(actor):
        return {"principal": actor.principal, "on_behalf_of": actor.on_behalf_of, "client_id": actor.client_id}

    def register_mcp(mcp, deps):
        @mcp.tool()
        @deps.mcp_errors
        async def probe_client() -> dict:
            """Who is calling."""
            return who(deps.mcp_actor())

    def http_routes(deps, endpoint):
        async def h_probe(_request, actor):
            return server.JSONResponse(who(actor))
        return [Route("/v1/probe-client", endpoint(h_probe))]

    return types.SimpleNamespace(register_mcp=register_mcp, http_routes=http_routes)


@pytest.mark.parametrize("version", [LEGACY, MODERN])
def test_client_id_comes_from_the_token_and_client_info_changes_nothing(app_env, keys, verifier, version):  # T37
    _app, _, dsn = app_env
    app = server.create_app(dsn=dsn, verifier=verifier, bridge=None, model=None, public_url=PUBLIC,
                            features=(_client_probe(),))
    exchanged = bearer(keys, act={"sub": "adc"}, client_id="adc-orchestrator")
    machine = bearer(keys, sub="adc", azp="adc-orchestrator", **{"kutuphane/principal_type": "agent"})
    claimed = {"io.modelcontextprotocol/clientInfo": {"name": "kutuphane-ui", "version": "1"}}
    with TestClient(app, base_url=PUBLIC) as client:
        for auth, expected in [(exchanged, {"principal": "agent:adc", "on_behalf_of": U}),
                               (machine, {"principal": "agent:adc", "on_behalf_of": None})]:
            expected = {**expected, "client_id": "adc-orchestrator"}
            assert client.get("/v1/probe-client", headers=auth).json() == expected
            _, out = mcp_rpc(client, auth, "tools/call", {"name": "probe_client", "arguments": {}},
                             version=version, meta=claimed)
            assert json.loads(out["result"]["content"][0]["text"]) == expected


# --- docs/24 §12.5, §12.7: the issuer, and a scoped test client --------------------------------------------------

def _resource_metadata(client) -> dict:
    r = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, headers=MCP_HEADERS)
    url = r.headers["www-authenticate"].split('resource_metadata="')[1].split('"')[0]
    return client.get(url.removeprefix(PUBLIC)).json()


@pytest.mark.parametrize("issuer", [ISS, "https://idp.test"])
def test_resource_metadata_advertises_exactly_the_pinned_issuer(conn, keys, verifier, issuer):  # §12.5
    import dataclasses
    pinned = dataclasses.replace(verifier, issuer=issuer)
    app = server.create_app(dsn=os.environ["KUTUPHANE_TEST_DSN"], verifier=pinned, bridge=None, model=None,
                            public_url=PUBLIC)
    with TestClient(app, base_url=PUBLIC) as client:
        assert _resource_metadata(client)["authorization_servers"] == [issuer]    # what a client records (RFC 9207)
        assert client.get("/v1/whoami", headers=bearer(keys, iss=issuer)).status_code == 200  # what tokens carry


@pytest.mark.parametrize("issuer", ["https://IDP.test/realms/kurum", "https://idp.test:443/realms/kurum"])
def test_an_issuer_the_sdk_would_rewrite_is_refused_at_start(conn, verifier, issuer):  # §12.5
    import dataclasses
    with pytest.raises(RuntimeError, match="issuer"):
        server.create_app(dsn=os.environ["KUTUPHANE_TEST_DSN"], verifier=dataclasses.replace(verifier, issuer=issuer),
                          bridge=None, model=None, public_url=PUBLIC)


@pytest.mark.parametrize("version", [LEGACY, MODERN])
def test_scoped_test_client_reads_one_book_and_nothing_else(app_env, keys, conn, okf_dir, tmp_path, monkeypatch,
                                                            capsys, version):  # §12.7, ADC stage-2 T3
    from kutuphane import cli, notes
    from kutuphane.gate import Actor
    user_app, _, dsn = app_env
    catalog.publish(conn, book="baska", title="baska", files=read_source(okf_dir),
                    policy=make_policy(sensitivity="normal", egress="local_only", protection="standard"),
                    profile=profiles.spec("chunked"))
    authz.grant(conn, "book:baska", "read", U)
    notes.create_journal(conn, book="gunluk", title="gunluk", search=True, ai_input=True, by="user:admin",
                         policy=make_policy(sensitivity="normal", egress="local_only", protection="standard"))
    for mode in ("read", "propose"):
        authz.grant(conn, "book:gunluk", mode, U)
    notes.propose(conn, Actor(U, channel="http"), {"book": "gunluk", "kind": "finding", "text": "Kayıtlar saklanır."})

    # The documented procedure (§12.7), local form.
    monkeypatch.setenv("KUTUPHANE_DEV", "1")
    monkeypatch.setenv("KUTUPHANE_DSN", dsn)
    auth_dir = tmp_path / "dev-auth"
    assert cli.main(["dev-keys", str(auth_dir)]) == 0
    assert cli.main(["grant", "book:kitap", "read", "agent:adc-t3"]) == 0
    capsys.readouterr()
    assert cli.main(["dev-token", "adc-t3", "--agent", "--client-id", "adc-t3", "--issuer", ISS, "--audience", AUD,
                     "--private-key", str(auth_dir / "dev-private.pem")]) == 0
    t3 = {"Authorization": f"Bearer {capsys.readouterr().out.strip()}"}
    app = server.create_app(dsn=dsn, verifier=Verifier.from_files(ISS, AUD, auth_dir / "jwks.json"), bridge=None,
                            model=None, public_url=PUBLIC)

    with TestClient(user_app, base_url=PUBLIC) as client:   # the user sees both books and the note
        other = client.get("/v1/search", params={"q": "kayıtlar saklanır", "book": "baska"},
                           headers=bearer(keys)).json()["results"]
        assert other and client.get("/v1/notes", params={"sets": "open"}, headers=bearer(keys)).json()["items"]
    with TestClient(app, base_url=PUBLIC) as client:
        def call(name: str, args: dict) -> dict:
            status, msg = mcp_rpc(client, t3, "tools/call", {"name": name, "arguments": args}, version=version)
            assert status == 200
            return msg["result"]

        def refused(result: dict) -> bool:
            return result.get("isError") and "forbidden" in result["content"][0]["text"]

        assert client.get("/v1/whoami", headers=t3).json()["principal"] == "agent:adc-t3"
        found = call("search_library", {"query": "kayıtlar saklanır"})["structuredContent"]["result"]
        assert found and {h["citation"].split("@")[0] for h in found} == {"kitap"}
        opened = json.loads(call("open_citation", {"handle": found[0]["citation"]})["content"][0]["text"])
        assert opened["citation"] == found[0]["citation"] and opened["text"]

        assert call("search_library", {"query": "kayıtlar saklanır", "book": ["baska"]})["structuredContent"] \
            == {"result": []}
        assert refused(call("open_citation", {"handle": other[0]["citation"]}))
        cited = server.parse_citation(other[0]["citation"])
        assert refused(call("read_document", {"book": "baska", "content_id": cited.content_id, "path": cited.path}))
        assert refused(call("propose_note", {"book": "gunluk", "kind": "finding", "text": "T3 cannot write."}))
        assert json.loads(call("query_notes", {"sets": ["open", "current"]})["content"][0]["text"])["items"] == []
