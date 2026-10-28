"""#136: every search and answer says which model stages ran; #141: the authenticated dependency check."""
import asyncio
import os

from mcp.server.auth.middleware.auth_context import auth_context_var
from mcp.server.auth.middleware.bearer_auth import AuthenticatedUser
from starlette.testclient import TestClient

from kutuphane import answers, llmdap, retrieval, server, vectors
from kutuphane.gate import Actor
from test_retrieval import ENGLISH, TURKISH, _bilingual, book, fake  # noqa: F401 (fixtures)
from test_server import PUBLIC, app_env, bearer, keys, verifier  # noqa: F401 (fixtures)

U = "user:ayse"
QUERY = "yedek geri yükleme kayıtlar"
ALL_OK = {"embedding": "ok", "translation": "skipped", "rerank": "ok"}


def _stages(fake, **more):
    return retrieval.Stages(embedder=fake.embedder(), reranker=fake.reranker(), **more)


def _broken_rerank(body):
    return [{"index": 0, "relevance_score": 1.0} for _ in body["documents"]]


def test_a_normal_search_says_ok_and_a_failed_rerank_says_failed(conn, fake, book, monkeypatch):
    monkeypatch.setattr(retrieval, "_vectors", retrieval._QueryCache())
    vectors.index(conn, fake.embedder(), "kitap")
    assert retrieval.retrieved(conn, Actor(U), QUERY, k=8, stages=_stages(fake))[1].as_dict() == ALL_OK
    fake.rerank_reply = _broken_rerank
    hits, status = retrieval.retrieved(conn, Actor(U), QUERY, k=8, stages=_stages(fake))
    assert hits and status.as_dict() == {**ALL_OK, "rerank": "failed"}


def test_no_models_is_skipped(conn, book):
    assert retrieval.retrieved(conn, Actor(U), QUERY, k=8)[1].as_dict() == \
        {"embedding": "skipped", "translation": "skipped", "rerank": "skipped"}


def test_a_failed_or_misfit_query_embedding_says_failed(conn, fake, book, monkeypatch):
    monkeypatch.setattr(retrieval, "_vectors", retrieval._QueryCache())
    vectors.index(conn, fake.embedder(), "kitap")
    fake.embed_status = lambda body: 504                                            # the embedder is down
    hits, status = retrieval.retrieved(conn, Actor(U), QUERY, k=8, stages=retrieval.Stages(fake.embedder()))
    assert hits and status.embedding == "failed"                                    # full text still answers
    fake.embed_status = None
    fake.embed_reply = lambda texts: [{"index": i, "embedding": [1.0] * 8} for i, _ in enumerate(texts)]
    assert retrieval.retrieved(conn, Actor(U), "kayıtlar saklanır", k=8,
                               stages=retrieval.Stages(fake.embedder()))[1].embedding == "failed"  # another width


def test_a_failed_translation_says_failed(conn, fake, tmp_path):
    _bilingual(conn, tmp_path, {**ENGLISH, **TURKISH})
    translator = llmdap.Routed(fake.bridge(prefix="/drop"), "qwen")  # no answer comes back
    stages = retrieval.Stages(reranker=fake.reranker(), translator=translator)
    status = retrieval.retrieved(conn, Actor(U), "logs of the backup", k=4, stages=stages)[1]
    assert status.as_dict() == {"embedding": "skipped", "translation": "failed", "rerank": "ok"}
    fake.reply = "Yedekler ve loglar için ne yapılır?"
    stages = retrieval.Stages(reranker=fake.reranker(), translator=llmdap.Routed(fake.bridge(), "qwen"))
    assert retrieval.retrieved(conn, Actor(U), "logs of the backup", k=4, stages=stages)[1].translation == "ok"


def test_the_answer_stores_the_status_and_reopen_shows_it(conn, fake, book):
    fake.reply, fake.rerank_reply = "İki yıl saklanır [1].", _broken_rerank
    asked = answers.ask(conn, fake.bridge(), Actor(U), "Yedek geri yükleme kayıtları ne kadar saklanır?", model="qwen",
                        stages=retrieval.Stages(reranker=fake.reranker()))
    expected = {"embedding": "skipped", "translation": "skipped", "rerank": "failed"}
    assert asked["retrieval"] == expected
    assert answers.reopen(conn, Actor(U), asked["id"])["retrieval"] == expected
    failed = conn.execute("SELECT count(*) FROM model_call WHERE model = 'bge-reranker-v2-m3' AND (error IS NOT NULL "
                          "OR http_status IS DISTINCT FROM 200)").fetchone()[0]
    assert failed == 0  # the reranker answered (HTTP 200) but badly: model_call counts transport failures only


def test_http_search_ask_and_mcp_meta_carry_the_status(app_env, keys, fake, verifier):
    app, _, dsn = app_env
    fake.reply, fake.rerank_reply = "İki yıl saklanır [1].", _broken_rerank
    stages = retrieval.Stages(reranker=fake.reranker())
    app = server.create_app(dsn=dsn, verifier=verifier, bridge=fake.bridge(), model="qwen", public_url=PUBLIC,
                            stages=stages)
    expected = {"embedding": "skipped", "translation": "skipped", "rerank": "failed"}
    with TestClient(app) as client:
        h = bearer(keys)
        found = client.get("/v1/search", params={"q": QUERY}, headers=h).json()
        assert found["results"] and found["retrieval"] == expected
        asked = client.post("/v1/ask", json={"question": "Yedek geri yükleme kayıtları ne kadar saklanır?"}, headers=h).json()
        assert asked["retrieval"] == expected
        assert client.get(f"/v1/answers/{asked['id']}", headers=h).json()["retrieval"] == expected
    mcp = server.build_mcp(dsn=dsn, verifier=verifier, bridge=fake.bridge(), model="qwen", public_url=PUBLIC,
                           stages=stages)
    from mcp.server.auth.provider import AccessToken
    claims = {"kutuphane_principal": U, "kutuphane_on_behalf_of": None}
    reset = auth_context_var.set(AuthenticatedUser(AccessToken(token="t", client_id="test", scopes=[],
                                                               claims=claims)))
    try:
        result = asyncio.run(mcp.call_tool("search_library", {"query": QUERY}))
    finally:
        auth_context_var.reset(reset)
    assert not result.is_error and result.meta[server.RETRIEVAL_KEY] == expected


def test_v1_health_needs_a_token_and_reports_booleans_only(app_env, keys, fake, verifier):
    _, _, dsn = app_env
    app = server.create_app(dsn=dsn, verifier=verifier, bridge=fake.bridge(), model="qwen", public_url=PUBLIC,
                            stages=_stages(fake))
    with TestClient(app) as client:
        assert client.get("/v1/health").status_code == 401
        assert client.get("/healthz").json() == {"ok": True}                       # unchanged, public
        up = client.get("/v1/health", headers=bearer(keys))
        assert up.status_code == 200
        assert up.json() == {"ok": True, "db": True, "llmdap": True, "embedding": True, "rerank": True, "chat": True}
        fake.rerank_reply = _broken_rerank
        down = client.get("/v1/health", headers=bearer(keys))
        assert down.status_code == 503 and down.json()["rerank"] is False and down.json()["llmdap"] is True
        assert all(v is None or isinstance(v, bool) for v in down.json().values())  # no routes, no addresses
    purposes = {h["x-llmdap-purpose"] for _, h in fake.hits}
    assert purposes == {"health"}


def test_v1_health_without_models_or_without_llmdap(app_env, keys, verifier):
    _, _, dsn = app_env
    light = server.create_app(dsn=dsn, verifier=verifier, bridge=None, model=None, public_url=PUBLIC)
    with TestClient(light) as client:
        assert client.get("/v1/health", headers=bearer(keys)).json() == \
            {"ok": True, "db": True, "llmdap": None, "embedding": None, "rerank": None, "chat": None}
    gone = llmdap.Bridge("http://127.0.0.1:9", "local", "k", "local")              # nothing listens
    app = server.create_app(dsn=dsn, verifier=verifier, bridge=gone, model="qwen", public_url=PUBLIC)
    with TestClient(app) as client:
        r = client.get("/v1/health", headers=bearer(keys))
    assert r.status_code == 503 and r.json()["chat"] is False and r.json()["llmdap"] is False
