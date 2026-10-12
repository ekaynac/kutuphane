"""M1e: HTTP API and Kütüphane MCP. The caller is only what a verified token says (AT-11, Core side);
human (HTTP) and agent (MCP) reach the same evidence (AT-03)."""
import asyncio
import json
import os

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from mcp.server.auth.middleware.auth_context import auth_context_var
from mcp.server.auth.middleware.bearer_auth import AuthenticatedUser
from starlette.testclient import TestClient

from kutuphane import authz, catalog, profiles, server
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
