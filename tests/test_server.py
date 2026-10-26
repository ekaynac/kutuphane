"""M1e: HTTP API and Kütüphane MCP. The caller is only what a verified token says (AT-11, Core side);
human (HTTP) and agent (MCP) reach the same evidence (AT-03)."""
import asyncio
import json
import os
import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from mcp.server.auth.middleware.auth_context import auth_context_var
from mcp.server.auth.middleware.bearer_auth import AuthenticatedUser
from starlette.testclient import TestClient

from kutuphane import authz, catalog, profiles, retrieval, server
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


def call_tool(mcp, actor_claims: dict, name: str, args: dict):
    from mcp.server.auth.provider import AccessToken
    access = AccessToken(token="t", client_id="test", scopes=[], claims=actor_claims)
    reset = auth_context_var.set(AuthenticatedUser(access))
    try:
        return asyncio.run(mcp.call_tool(name, args))
    finally:
        auth_context_var.reset(reset)


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
    _content, structured = out                                    # FastMCP returns (content blocks, structured)
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
