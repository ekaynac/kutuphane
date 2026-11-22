"""D88 (2), #242: a model stage may call a direct OpenAI-compatible endpoint instead of LLMDAP. Our rights and egress
checks run first and every call lands in `model_call`, as on the LLMDAP path. The stub below is a local HTTP server;
no test reaches the network. Rerank has no OpenAI provider (no standard endpoint): its setting is refused here."""
import json
import logging
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from starlette.testclient import TestClient

from kutuphane import answers, audit, authz, catalog, cli, db, health, llmdap, profiles, retrieval, server, vectors
from kutuphane.gate import Actor
from kutuphane.policy import make_policy
from kutuphane.source import read_source
from test_egress_audit import KEY as LLMDAP_KEY, fake_vector
from test_kstd import write_manifest
from test_retrieval import ENGLISH, TURKISH, _bilingual, fake  # noqa: F401 (fixture: the LLMDAP stub for rerank)
from test_server import MODERN, PUBLIC, _light_env, bearer, keys, mcp_rpc, verifier  # noqa: F401 (fixtures)

# The review tool redacts IP literals, so the loopback address is built at run time, never written as a literal.
LOOPBACK = ".".join(["127", "0", "0", "1"])
KEY = "sk-test-" + "z" * 40
U = "user:ayse"
QUESTION = "Erişim kayıtları ne kadar saklanır?"
LOCAL = make_policy(sensitivity="normal", egress="local_only", protection="standard")
CLOUD = make_policy(sensitivity="normal", egress="cloud_ok", protection="standard")
MODEL_ENV = {"answer": "KUTUPHANE_ANSWER_MODEL", "embed": "KUTUPHANE_EMBED_MODEL"}
STAGE_ENV = {"answer": llmdap.ENV, "embed": llmdap.EMBED_ENV}


class StubOpenAI:
    """An OpenAI-compatible server: /v1/embeddings and /v1/chat/completions with a bearer key, nothing else."""

    def __init__(self):
        self.requests = []  # (path, lower-case headers, body) of every request that arrived
        self.reply, self.status = "İki yıl saklanır [1].", None  # `status`: answer every request with it
        stub = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                raw = self.rfile.read(int(self.headers["content-length"]))
                body = json.loads(raw)
                stub.requests.append((self.path, {k.lower(): v for k, v in self.headers.items()}, body))
                if self.path.startswith("/redirect"):
                    self.send_response(302)
                    self.send_header("Location", f"http://{LOOPBACK}:{stub.port}/stolen")
                    self.end_headers()
                    return
                failure = 401 if self.headers.get("authorization") != f"Bearer {KEY}" else stub.status
                if failure or self.path not in ("/v1/embeddings", "/v1/chat/completions"):
                    self.send_response(failure or 404)
                    self.end_headers()
                    return
                if self.path == "/v1/embeddings":
                    answer = {"data": [{"index": i, "embedding": fake_vector(t)} for i, t in enumerate(body["input"])]}
                else:
                    answer = {"choices": [{"message": {"role": "assistant", "content": stub.reply}}]}
                data = json.dumps(answer).encode()
                self.send_response(200)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        self.server = ThreadingHTTPServer((LOOPBACK, 0), Handler)
        self.port = self.server.server_address[1]
        self.url = f"http://{LOOPBACK}:{self.port}"
        self.route = llmdap.DIRECT_ROUTE_PREFIX + f"{LOOPBACK}:{self.port}"  # `model_call.route` of a direct call
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def bridge(self, route_class="local", key=KEY, prefix=""):
        return llmdap.Bridge(self.url + prefix, self.route, key, route_class, "openai")

    def embedder(self, route_class="local"):
        return llmdap.Routed(self.bridge(route_class), "text-embedding-test")

    def configure(self, mp, stage, route_class="local"):
        env = STAGE_ENV[stage]
        mp.setenv(env["provider"], "openai")
        mp.setenv(env["openai_url"], self.url)
        mp.setenv(env["openai_key"], KEY)
        mp.setenv(env["openai_class"], route_class)
        mp.setenv(MODEL_ENV[stage], "text-embedding-test" if stage == "embed" else "qwen")


@pytest.fixture
def stub():
    s = StubOpenAI()
    yield s
    s.server.shutdown()


@pytest.fixture
def bare(monkeypatch):
    for var in (*llmdap.ENV.values(), *llmdap.EMBED_ENV.values(), *llmdap.RERANK_ENV.values(),
                *MODEL_ENV.values(), server.ENV["public_url"]):
        monkeypatch.delenv(var, raising=False)
    return monkeypatch


def publish(conn, root, policy=LOCAL, book="kitap"):
    out = catalog.publish(conn, book=book, title=book, files=read_source(root), policy=policy,
                          profile=profiles.spec("chunked"))
    authz.grant(conn, f"book:{book}", "read", U)
    return out


def calls(conn):
    return conn.execute("SELECT route, model, http_status, error, source_books FROM model_call ORDER BY id").fetchall()


def test_embedding_stage_on_the_openai_path(conn, stub, bare, okf_dir):
    stub.configure(bare, "embed")
    publish(conn, okf_dir)
    embedder = retrieval.Stages.from_env().embedder
    assert embedder.bridge.provider == "openai" and embedder.model == "text-embedding-test"
    done = vectors.index(conn, embedder, "kitap")
    assert done.embedded > 0 and not done.failed
    assert {path for path, _, _ in stub.requests} == {"/v1/embeddings"}
    for _path, headers, body in stub.requests:
        assert headers["authorization"] == f"Bearer {KEY}" and body["model"] == "text-embedding-test"
        assert not [h for h in headers if h.startswith("x-llmdap")]  # the provider learns neither who nor why
    rows = calls(conn)
    assert len(rows) == len(stub.requests)  # one model_call row per call
    assert all(r == (stub.route, "text-embedding-test", 200, None, ["kitap"]) for r in rows)
    # the query is embedded through the same provider and the hybrid search says so
    hits, status = retrieval.retrieved(conn, Actor(U), "yedek geri yükleme", k=5,
                                       stages=retrieval.Stages(embedder=embedder))
    assert hits and status.embedding == "ok" and len(calls(conn)) == len(stub.requests) == len(rows) + 1


def test_answer_stage_on_the_openai_path(conn, stub, bare, okf_dir):
    stub.configure(bare, "answer")
    publish(conn, okf_dir)
    out = answers.ask(conn, llmdap.Bridge.for_stage(llmdap.ENV), Actor(U), QUESTION, model="qwen")
    assert out["status"] == "answered" and out["citations"][0]["path"] == "politika/veri-saklama.md"
    (path, headers, body), = stub.requests
    assert path == "/v1/chat/completions" and headers["authorization"] == f"Bearer {KEY}"
    assert body["model"] == "qwen" and body["stream"] is False and "[1] (kitap/politika/veri-saklama.md)" in \
        body["messages"][1]["content"]
    assert calls(conn) == [(stub.route, "qwen", 200, None, ["kitap"])]


def test_translation_stage_on_the_openai_path(conn, stub, fake, tmp_path):  # noqa: F811  the answer model translates
    _bilingual(conn, tmp_path, {**ENGLISH, **TURKISH})
    stub.reply = "Yedekler ve loglar için ne yapılır?"
    stages = retrieval.Stages(reranker=fake.reranker(), translator=llmdap.Routed(stub.bridge("cloud"), "qwen"))
    status = retrieval.retrieved(conn, Actor(U), "logs of the backup", k=4, stages=stages)[1]
    assert status.translation == "ok"  # only the query leaves, so a cloud provider may take it
    assert [p for p, _, _ in stub.requests] == ["/v1/chat/completions"]
    assert (stub.route, "qwen", 200, None, []) in calls(conn)


def test_health_probes_run_on_the_openai_path(conn, stub, bare):
    stub.configure(bare, "embed")
    stub.configure(bare, "answer")
    stages = retrieval.Stages.from_env()
    bridge = llmdap.Bridge.for_stage(llmdap.ENV)
    report = health.check(conn, Actor(U), bridge, "qwen", stages)
    assert report == {"ok": True, "db": True, "llmdap": None, "embedding": True, "rerank": None, "chat": True}
    assert sorted(p for p, _, _ in stub.requests) == ["/v1/chat/completions", "/v1/embeddings"]
    assert len(calls(conn)) == 2


@pytest.mark.parametrize("stage", ["embed", "answer"])
def test_a_local_only_book_is_refused_on_a_cloud_provider_and_nothing_is_sent(conn, stub, bare, okf_dir, stage):
    stub.configure(bare, stage, route_class="cloud")
    publish(conn, okf_dir)
    with pytest.raises(llmdap.PolicyRefused, match="kitap"):
        if stage == "embed":
            vectors.index(conn, retrieval.Stages.from_env().embedder, "kitap")
        else:
            answers.ask(conn, llmdap.Bridge.for_stage(llmdap.ENV), Actor(U), QUESTION, model="qwen")
    assert stub.requests == []  # the refusal comes before any connection
    rows = calls(conn)
    assert rows and all(r[0] == stub.route and r[2:4] == (None, llmdap.NOT_SENT_POLICY)
                        for r in rows)
    assert audit.explain(conn, conn.execute("SELECT correlation_id FROM model_call").fetchone()[0], []
                         )["model_calls"][0]["llmdap_status"] == "not_sent"


def test_a_cloud_ok_book_may_go_to_a_cloud_provider(conn, stub, bare, okf_dir):
    stub.configure(bare, "answer", route_class="cloud")
    publish(conn, okf_dir, policy=CLOUD)
    out = answers.ask(conn, llmdap.Bridge.for_stage(llmdap.ENV), Actor(U), QUESTION, model="qwen")
    assert out["status"] == "answered" and len(stub.requests) == 1


def test_item_rights_apply_before_the_openai_provider_is_called(conn, stub, bare, okf_dir):
    stub.configure(bare, "embed")
    stub.configure(bare, "answer")
    write_manifest(okf_dir, runbook_item={"rights": {"ai_use": {"search": "y", "ai_input": "n"}}})
    publish(conn, okf_dir)
    stages = retrieval.Stages.from_env()
    vectors.index(conn, stages.embedder, "kitap")
    assert {p for (p,) in conn.execute("SELECT DISTINCT path FROM chunk_vector")} == {"index.md",
                                                                                      "politika/veri-saklama.md"}
    runbook = {t for (t,) in conn.execute("SELECT text FROM chunk WHERE path = 'runbook/yedek-geri-yukleme.md'")}
    assert runbook
    stub.reply = "Kayıtlar saklanır [1]."
    out = answers.ask(conn, llmdap.Bridge.for_stage(llmdap.ENV), Actor(U), "yedek geri yükleme kayıtlar saklanır "
                      "politika runbook", model="qwen", stages=stages)
    sent = [body for _, _, body in stub.requests]
    embedded = {t for body in sent if "input" in body for t in body["input"]}
    prompt = [body for body in sent if "messages" in body][-1]["messages"][1]["content"]
    assert not runbook & embedded and "yedek-geri-yukleme" not in prompt
    assert out["withheld"] >= 1 and out["status"] == "answered"


def test_direct_calls_need_no_llmdap_record_in_the_audit(conn, stub, okf_dir):
    publish(conn, okf_dir)
    vectors.index(conn, stub.embedder(), "kitap")
    correlation = conn.execute("SELECT correlation_id FROM model_call").fetchone()[0]
    report = audit.explain(conn, correlation, [])
    assert report["complete"] and {c["llmdap_status"] for c in report["model_calls"]} == {"direct"}


def test_a_provider_failure_leaks_no_key(conn, stub, caplog):
    stub.status = 500
    caplog.set_level(logging.DEBUG)
    bridge = stub.bridge()
    with pytest.raises(llmdap.EgressError) as err:
        llmdap.chat(conn, bridge, Actor(U), model="qwen", messages=[{"role": "user", "content": "ok"}],
                    source_books=[], purpose="answer")
    assert str(err.value) == "OpenAI provider refused the call (HTTP 500)"
    assert calls(conn) == [(bridge.route, "qwen", 500, "http 500", [])]
    texts = [str(err.value), repr(bridge), caplog.text, json.dumps(calls(conn)),
             json.dumps(conn.execute("SELECT to_jsonb(m) FROM model_call m").fetchall())]
    assert not [t for t in texts if KEY in t]


def test_the_api_key_is_never_sent_to_a_redirect_target(conn, stub):
    with pytest.raises(llmdap.EgressError, match="HTTP 302"):
        llmdap.embed(conn, llmdap.Routed(stub.bridge(prefix="/redirect"), "m"), Actor(U), ["x"], source_books=[],
                     purpose="search")
    assert [p for p, _, _ in stub.requests] == ["/redirect/v1/embeddings"]


@pytest.mark.parametrize("stage", ["embed", "answer"])
@pytest.mark.parametrize("gap", ["openai_url", "openai_key", "openai_class"])
def test_start_up_refuses_a_missing_url_key_or_class(stub, bare, stage, gap):
    stub.configure(bare, stage)
    bare.delenv(STAGE_ENV[stage][gap])
    with pytest.raises(RuntimeError) as err:
        llmdap.Routed.from_env(llmdap.EMBED_ENV) if stage == "embed" else llmdap.Bridge.for_stage(llmdap.ENV)
    assert f"set {STAGE_ENV[stage][gap]}" in str(err.value) and KEY not in str(err.value)
    if gap == "openai_class":
        assert "no default" in str(err.value)


@pytest.mark.parametrize("stage", ["embed", "answer"])
def test_start_up_refuses_an_unknown_class_or_provider(stub, bare, stage):
    env = STAGE_ENV[stage]
    build = (lambda: llmdap.Routed.from_env(env)) if stage == "embed" else (lambda: llmdap.Bridge.for_stage(env))
    stub.configure(bare, stage)
    bare.setenv(env["openai_class"], "onprem")
    with pytest.raises(RuntimeError, match=f"{env['openai_class']} must be local or cloud"):
        build()
    stub.configure(bare, stage)
    bare.setenv(env["provider"], "azure")
    with pytest.raises(RuntimeError, match=f"{env['provider']} must be llmdap or openai"):
        build()
    stub.configure(bare, stage)
    bare.setenv(env["openai_url"], "ftp://models.example")
    with pytest.raises(RuntimeError, match="url must be http"):
        build()


def test_start_up_refuses_an_embedder_without_a_model(stub, bare):
    stub.configure(bare, "embed")
    bare.delenv(MODEL_ENV["embed"])
    with pytest.raises(RuntimeError, match=f"set {MODEL_ENV['embed']}"):
        llmdap.Routed.from_env(llmdap.EMBED_ENV)


def test_the_server_refuses_to_start_on_a_bad_answer_provider(stub, bare):
    bare.setenv(server.ENV["public_url"], "https://kutuphane.example")
    stub.configure(bare, "answer", route_class="onprem")
    with pytest.raises(RuntimeError, match=f"{llmdap.ENV['openai_class']} must be local or cloud"):
        server.app_from_env()
    stub.configure(bare, "answer")
    bare.delenv(MODEL_ENV["answer"])  # an answer provider needs its model, as LLMDAP does (the list has no ask_library)
    with pytest.raises(RuntimeError, match=MODEL_ENV["answer"]):
        server.app_from_env()


def test_without_a_provider_setting_the_default_is_llmdap(bare):
    for value in (None, ""):  # compose passes an empty value for an unset `${X:-}`
        for env in (llmdap.ENV, llmdap.EMBED_ENV):
            if value is not None:
                bare.setenv(env["provider"], value)
            assert llmdap.provider_of(env) == "llmdap"
    assert llmdap.provider_of(llmdap.RERANK_ENV) == "llmdap"  # rerank has no provider setting
    bare.setenv(llmdap.EMBED_ENV["openai_url"], f"http://{LOOPBACK}:9")  # unused without the provider setting
    assert llmdap.Routed.from_env(llmdap.EMBED_ENV) is None
    assert llmdap.Bridge(f"http://{LOOPBACK}:9", "chat", "k", "local").provider == "llmdap"


def test_health_llmdap_field_is_only_about_llmdap(conn, stub, fake):  # noqa: F811
    llmdap_stages = retrieval.Stages(embedder=fake.embedder(), reranker=fake.reranker())
    assert health.check(conn, Actor(U), fake.bridge(), "qwen", llmdap_stages) == {  # LLMDAP only: as before
        "ok": True, "db": True, "llmdap": True, "embedding": True, "rerank": True, "chat": True}
    down = llmdap.Bridge(f"http://{LOOPBACK}:9", "local", "k", "local")  # LLMDAP down, direct embedder up
    report = health.check(conn, Actor(U), down, "qwen", retrieval.Stages(embedder=stub.embedder()))
    assert report["llmdap"] is False and report["embedding"] is True and report["chat"] is False
    stub.status = 500  # LLMDAP up, direct embedder down
    report = health.check(conn, Actor(U), fake.bridge(), "qwen", retrieval.Stages(embedder=stub.embedder()))
    assert report["llmdap"] is True and report["embedding"] is False and report["chat"] is True
    only_direct = health.check(conn, Actor(U), None, None, retrieval.Stages(embedder=stub.embedder()))
    assert only_direct["llmdap"] is None  # no LLMDAP configured: as before


def test_the_default_llmdap_path_is_unchanged(conn, fake, bare, okf_dir):  # noqa: F811
    bare.setenv(llmdap.ENV["url"], f"http://{LOOPBACK}:{fake.port}")
    bare.setenv(llmdap.ENV["key"], LLMDAP_KEY)
    for env, model in ((llmdap.ENV, None), (llmdap.EMBED_ENV, "bge-m3")):
        bare.setenv(env["route"], "local")
        bare.setenv(env["route_class"], "local")
        if model:
            bare.setenv(env["model"], model)
    bridge, embedder = llmdap.Bridge.for_stage(llmdap.ENV), retrieval.Stages.from_env().embedder
    assert bridge.provider == embedder.bridge.provider == "llmdap" and embedder.model == "bge-m3"
    publish(conn, okf_dir)
    fake.reply = "İki yıl saklanır [1]."
    actor = Actor(U)
    answers.ask(conn, bridge, actor, QUESTION, model="qwen")
    llmdap.embed(conn, embedder, actor, ["yedek"], source_books=["kitap"], purpose="index")
    chat, embed = fake.hits[-2:]
    assert chat[0] == "/bridge/local/v1/chat/completions" and embed[0] == "/bridge/local/v1/embeddings"
    for (_, headers), purpose in ((chat, "answer"), (embed, "index")):
        assert headers["authorization"] == f"Bearer {LLMDAP_KEY}" and headers["x-llmdap-purpose"] == purpose
        assert headers["x-llmdap-correlation-id"].startswith(actor.correlation_id + ".")
        assert headers["x-llmdap-for-subject"] == U
    rows = conn.execute("SELECT route, model, http_status, error, derived_correlation_id IS NOT NULL, source_books "
                        "FROM model_call ORDER BY id").fetchall()
    assert rows == [("local", "qwen", 200, None, True, ["kitap"]), ("local", "bge-m3", 200, None, True, ["kitap"])]


def test_the_server_lists_ask_and_job_tools_only_with_an_answer_model(conn, stub, monkeypatch, verifier, keys,  # noqa: F811
                                                                      tmp_path):
    _light_env(monkeypatch, tmp_path)
    stub.configure(monkeypatch, "answer")
    tools = ["ask_library", "job_status", "job_result", "job_cancel"]
    with TestClient(server.app_from_env(), base_url=PUBLIC) as client:
        listed = [t["name"] for t in mcp_rpc(client, bearer(keys), "tools/list", version=MODERN)[1]["result"]["tools"]]
    assert all(name in listed for name in tools)
    monkeypatch.delenv(MODEL_ENV["answer"])  # an answer provider without its model: the server does not start
    with pytest.raises(RuntimeError, match=MODEL_ENV["answer"]):
        server.app_from_env()
    for var in llmdap.ENV.values():  # no answer provider (the embedder alone is direct): no answer tools
        monkeypatch.delenv(var, raising=False)
    stub.configure(monkeypatch, "embed")
    with TestClient(server.app_from_env(), base_url=PUBLIC) as client:
        listed = [t["name"] for t in mcp_rpc(client, bearer(keys), "tools/list", version=MODERN)[1]["result"]["tools"]]
        ask = client.post("/v1/ask", json={"question": QUESTION}, headers=bearer(keys))
    assert "search_library" in listed and not [name for name in tools if name in listed]
    assert ask.status_code == 503 and ask.json() == {"error": server.NO_ANSWERS}


CLI_COMMAND = {"embed": ["index", "kitap"], "answer": ["ask", U, QUESTION, "--model", "qwen"]}


@pytest.mark.parametrize("stage", ["embed", "answer"])
@pytest.mark.parametrize("fault", ["unknown_provider", "missing_class", "unknown_class"])
def test_the_cli_refuses_bad_provider_settings_and_sends_nothing(conn, stub, bare, capsys, stage, fault):
    env = STAGE_ENV[stage]
    stub.configure(bare, stage)
    bare.setenv(db.DSN_ENV, os.environ["KUTUPHANE_TEST_DSN"])
    if fault == "unknown_provider":
        bare.setenv(env["provider"], "azure")
        named = env["provider"]
    elif fault == "missing_class":
        bare.delenv(env["openai_class"])
        named = env["openai_class"]
    else:
        bare.setenv(env["openai_class"], "onprem")
        named = env["openai_class"]
    assert cli.main(CLI_COMMAND[stage]) != 0
    assert named in capsys.readouterr().err and stub.requests == []


@pytest.mark.parametrize("value", ["openai", "azure"])
def test_a_rerank_provider_other_than_llmdap_is_refused_not_ignored(conn, bare, monkeypatch, verifier, tmp_path,
                                                                    capsys, value):
    _light_env(monkeypatch, tmp_path)
    monkeypatch.setenv(db.DSN_ENV, os.environ["KUTUPHANE_TEST_DSN"])
    for empty in ("", "llmdap"):  # these are fine: rerank is LLMDAP only
        monkeypatch.setenv(llmdap.RERANK_ENV["provider"], empty)
        assert retrieval.Stages.from_env().reranker is None
    monkeypatch.setenv(llmdap.RERANK_ENV["provider"], value)
    refusal = f"{llmdap.RERANK_ENV['provider']} must be llmdap: rerank is LLMDAP-only"
    with pytest.raises(RuntimeError, match=refusal):
        retrieval.Stages.from_env()
    with pytest.raises(RuntimeError, match=refusal):
        server.app_from_env()
    assert cli.main(["search", U, "kayıtlar"]) != 0 and refusal in capsys.readouterr().err


@pytest.mark.parametrize("fault", ["missing_url", "missing_key", "missing_class", "unknown_class"])
def test_cli_search_checks_the_answer_provider_even_without_an_answer_model(conn, stub, bare, capsys, fault):
    env = llmdap.ENV
    stub.configure(bare, "answer")
    bare.delenv(MODEL_ENV["answer"])  # search needs no answer model, but the selected provider must be valid
    bare.setenv(db.DSN_ENV, os.environ["KUTUPHANE_TEST_DSN"])
    if fault == "unknown_class":
        bare.setenv(env["openai_class"], "onprem")
        named = env["openai_class"]
    else:
        named = env["openai_" + fault.split("_")[1]]
        bare.delenv(named)
    assert cli.main(["search", U, "kayıtlar"]) != 0
    assert named in capsys.readouterr().err and stub.requests == []


def test_cli_search_with_a_valid_answer_provider_and_no_model_sends_nothing(conn, stub, bare, okf_dir, capsys):
    stub.configure(bare, "answer")
    bare.delenv(MODEL_ENV["answer"])
    bare.setenv(db.DSN_ENV, os.environ["KUTUPHANE_TEST_DSN"])
    publish(conn, okf_dir)
    assert cli.main(["search", U, "kayıtlar saklanır"]) == 0 and stub.requests == []
