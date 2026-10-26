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


def test_the_reranker_reads_a_capped_passage(conn, fake, tmp_path, okf_dir):  # G26
    folder = tmp_path / "uzun"
    folder.mkdir()
    (folder / "uzun.md").write_text("# Yedek\n\n" + "yedek kayıtlar saklanır. " * 400 + "\n", encoding="utf-8")
    catalog.publish(conn, book="uzun", title="uzun", files=read_source(folder), policy=make_policy(
        sensitivity="normal", egress="local_only", protection="standard"), profile=profiles.spec("whole"))
    authz.grant(conn, "book:uzun", "read", U)
    (long_hit,) = retrieval.retrieve(conn, Actor(U), "yedek kayıtlar", k=8)          # no reranker: one passage
    assert len(long_hit.text) > retrieval.RERANK_CHARS
    catalog.publish(conn, book="kisa", title="kisa", files=read_source(okf_dir), policy=make_policy(
        sensitivity="normal", egress="local_only", protection="standard"), profile=profiles.spec("chunked"))
    authz.grant(conn, "book:kisa", "read", U)
    ranked = retrieval.retrieve(conn, Actor(U), "yedek kayıtlar", k=8,
                                stages=retrieval.Stages(reranker=fake.reranker()))
    assert max(len(d) for d in fake.last_body["documents"]) == retrieval.RERANK_CHARS
    assert long_hit.text in {h.text for h in ranked}                                  # the hit itself stays whole


def test_a_repeated_query_is_embedded_once(conn, fake, book):  # G26
    from kutuphane import vectors
    vectors.index(conn, fake.embedder(), "kitap")
    stages = retrieval.Stages(embedder=fake.embedder())
    query = "yedek geri yükleme ne zaman yapılır"
    first = retrieval.retrieve(conn, Actor(U), query, k=5, stages=stages)
    calls = len(fake.hits)
    again = retrieval.retrieve(conn, Actor("user:mehmet"), query, k=5, stages=stages)  # no rights: no hits
    assert retrieval.retrieve(conn, Actor(U), query, k=5, stages=stages) == first and again == []
    assert len(fake.hits) == calls                                                     # no second embedding call
    fake.embed_reply = lambda texts: []                                                # a broken embedder
    other = "kayıtlar kaç yıl saklanır"
    retrieval.retrieve(conn, Actor(U), other, k=5, stages=stages)                     # full text only, not cached
    fake.embed_reply = None
    retrieval.retrieve(conn, Actor(U), other, k=5, stages=stages)
    assert sum(path.endswith("/v1/embeddings") for path, _ in fake.hits[calls:]) == 2


ENGLISH = {f"en{i}.md": f"# Note {i}\n\nThe archive is kept for {i} years. Restore it with care.\n" for i in range(8)}
TURKISH = {"tr.md": "# Yedek\n\nBackup logs, the backup logs için: yedekler ve loglar; geri yükleme adımları, "
                    "bu belge Türkçe.\n"}


def _bilingual(conn, tmp_path, files):
    for name, text in files.items():
        (tmp_path / name).write_text(text, encoding="utf-8")
    catalog.publish(conn, book="iki", title="iki", files=read_source(tmp_path), policy=make_policy(
        sensitivity="normal", egress="local_only", protection="standard"), profile=profiles.spec("chunked"))
    authz.grant(conn, "book:iki", "read", U)


def test_a_passage_in_the_other_language_keeps_a_place(conn, fake, tmp_path):  # G19
    _bilingual(conn, tmp_path, {**ENGLISH, **TURKISH})
    query = "logs of the backup"
    hybrid = search.search(conn, Actor(U), query, k=4)
    assert "tr.md" in {h.citation.path for h in hybrid}                                # the hybrid top 4 has it
    fake.rerank_reply = lambda b: [{"index": i, "relevance_score": 0.0 if "Türkçe" in d else 0.9}
                                   for i, d in enumerate(b["documents"])]               # cross-lingual blind spot
    ranked = retrieval.retrieve(conn, Actor(U), query, k=4, stages=retrieval.Stages(reranker=fake.reranker()))
    assert len(ranked) == 4 and ranked[-1].citation.path == "tr.md"
    assert [h.citation.path for h in ranked[:3]] == [h.citation.path for h in ranked if h.citation.path != "tr.md"]


def test_the_language_reserve_changes_nothing_in_one_language(conn, fake, tmp_path):  # G19
    _bilingual(conn, tmp_path, ENGLISH)
    fake.rerank_reply = lambda b: [{"index": i, "relevance_score": 1.0 / (1 + i)} for i in range(len(b["documents"]))]
    query = "logs of the backup"
    ranked = retrieval.retrieve(conn, Actor(U), query, k=4, stages=retrieval.Stages(reranker=fake.reranker()))
    assert [h.citation for h in ranked] == [h.citation for h in search.search(conn, Actor(U), query, k=30)][:4]
