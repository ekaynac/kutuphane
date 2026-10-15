"""Reranking through the LLMDAP rerank route (#236): it only reorders passages the search already authorized;
a failed or malformed rerank keeps the hybrid order."""
import pytest

from kutuphane import authz, catalog, profiles, retrieval, search
from kutuphane.gate import Actor
from kutuphane.policy import make_policy
from kutuphane.source import read_source
from test_egress_audit import FakeBridge

U = "user:ayse"


@pytest.fixture
def fake():
    f = FakeBridge()
    yield f
    f.server.shutdown()


@pytest.fixture
def book(conn, okf_dir):
    catalog.publish(conn, book="kitap", title="kitap", files=read_source(okf_dir),
                    policy=make_policy(sensitivity="normal", egress="local_only", protection="standard"),
                    profile=profiles.spec("chunked"))
    authz.grant(conn, "book:kitap", "read", U)


QUERY = "yedek geri yükleme kayıtlar"


def test_reranker_reorders_authorized_hits(conn, fake, book):
    plain = search.search(conn, Actor(U), QUERY, k=8)
    ranked = retrieval.retrieve(conn, Actor(U), QUERY, k=8, stages=retrieval.Stages(reranker=fake.reranker()))
    assert {h.citation for h in ranked} <= {h.citation for h in search.search(conn, Actor(U), QUERY, k=30)}
    assert [h.score for h in ranked] == sorted((h.score for h in ranked), reverse=True)   # relevance order
    assert len(ranked) == len(plain)
    path, headers = fake.hits[-1]
    assert path == "/bridge/local/v1/rerank" and headers["x-llmdap-purpose"] == "rerank"
    assert fake.last_body["model"] == "bge-reranker-v2-m3" and fake.last_body["top_n"] == len(fake.last_body["documents"])


@pytest.mark.parametrize("reply", [
    lambda b: [{"index": 0, "relevance_score": 1.0} for _ in b["documents"]],            # one passage scored twice
    lambda b: [{"index": i, "relevance_score": 0.5} for i in range(len(b["documents"]) - 1)],  # one missing
    lambda b: [{"index": float(i), "relevance_score": 0.5} for i in range(len(b["documents"]))],
    lambda b: [{"index": i, "relevance_score": float("nan")} for i in range(len(b["documents"]))],
])
def test_bad_rerank_answers_keep_the_hybrid_order(conn, fake, book, reply):
    fake.rerank_reply = reply
    plain = search.search(conn, Actor(U), QUERY, k=8)
    ranked = retrieval.retrieve(conn, Actor(U), QUERY, k=8, stages=retrieval.Stages(reranker=fake.reranker()))
    assert [h.citation for h in ranked] == [h.citation for h in plain]


def test_local_only_passages_never_reach_a_cloud_reranker(conn, fake, book):
    ranked = retrieval.retrieve(conn, Actor(U), QUERY, k=8,
                                stages=retrieval.Stages(reranker=fake.reranker(route_class="cloud")))
    assert ranked and fake.hits == []                                                   # refused before egress
    assert conn.execute("SELECT error FROM model_call").fetchone() == ("not_sent:egress_policy",)


def test_no_reranker_is_plain_hybrid_search(conn, fake, book):
    assert retrieval.retrieve(conn, Actor(U), QUERY, k=5) == search.search(conn, Actor(U), QUERY, k=5)
    assert fake.hits == []


def test_negative_rerank_scores_still_reach_the_answer(conn, fake, book):  # Astra review #7
    from kutuphane import answers
    fake.rerank_reply = lambda b: [{"index": i, "relevance_score": -0.1 - i} for i in range(len(b["documents"]))]
    fake.reply = "İki yıl saklanır [1]."
    out = answers.ask(conn, fake.bridge(), Actor(U), QUERY, model="qwen",
                      stages=retrieval.Stages(reranker=fake.reranker()))
    assert out["status"] == "answered"
