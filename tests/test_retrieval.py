"""Reranking through the LLMDAP rerank route (#236): it only reorders passages the search already authorized;
a failed or malformed rerank keeps the hybrid order."""
import pytest

from kutuphane import answers, authz, catalog, kstd, llmdap, profiles, retrieval, search, server
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


# Relevance order (path order for full text, first letter for the fake reranker): W30, W40, W33, W36.
WEEKS = {f"{p}-brief-2026-W{w}.md": f"{p}: model x{w} entered the pilot ring.\n"
         for p, w in (("a", 30), ("b", 40), ("c", 33), ("d", 36))}


@pytest.mark.parametrize("query,recent", [
    ("Which models entered the pilot ring recently?", True), ("the latest pilot ring moves", True),
    ("Hangi modeller son haftalarda pilot halkasına girdi?", True), ("En yeni modeller hangileri?", True),
    ("Which models entered the pilot ring?", False), ("Sonra ne oldu?", False),
])
def test_recency_questions_are_recognized(query, recent):  # G22
    assert retrieval.asks_recent(query) is recent


def test_passage_dates_come_from_path_and_record_metadata_only(conn):  # G22, Astra review #12
    from datetime import datetime, timezone
    rights = kstd.Rights(conn)                                                          # no such book: no manifest

    def when(path, text, line=None):
        hit = search.Hit(search.Citation("yok", "ct", "pf", path, 0), None, 0, len(text), text, 1.0, line)
        found = retrieval.passage_date(rights, hit)
        return found and found.date().isoformat()
    assert when("data/briefs/brief-2026-W40.json", "x") == "2026-09-28"
    assert when("digests/digest_2026-W28.html", "x") == "2026-07-06"
    assert when("v2026-13-45 and 12026-01-01, then 2026-02-03.md", "x") == "2026-02-03"
    record = '{"x": 1, "classified_at": "2026-08-05T09:21:18Z"}\n'
    assert retrieval.passage_date(rights, search.Hit(search.Citation("yok", "ct", "pf", "news.jsonl", 0), None, 0, 1,
                                                     record, 1.0, 3)) == datetime(2026, 8, 5, 9, 21, 18,
                                                                                  tzinfo=timezone.utc)
    assert when("notes/z.md", "2099-12-31 z: model x99 entered the pilot ring.") is None   # body text: never
    assert when("notes/z.md", record) is None                                  # a record field outside a record file
    assert when("news.jsonl", '{"x": 1, "note": "2026-08-05"}', 3) is None      # not a known record date field
    assert when("news.jsonl", '{"classified_at": "2099-12-31"}', 3) is None   # the future is ignored
    assert when("brief-2099-W01.json", "x") is None
    assert when("no date here.md", "no date here") is None


def test_a_body_date_does_not_promote_a_passage(conn):  # Astra review #12
    def hit(path, text):
        return search.Hit(search.Citation("yok", "ct", "pf", path, 0), None, 0, len(text), text, 1.0)
    ranked = [hit("a-brief-2026-W30.md", "a: model x30 entered the pilot ring."),
              hit("z-notes.md", "2099-12-31 z: model x99 entered the pilot ring."),
              hit("b-brief-2026-W40.md", "b: model x40 entered the pilot ring."),
              hit("c-brief-2026-W33.md", "c: model x33 entered the pilot ring.")]
    order = [h.citation.path[0] for h in retrieval._prefer_recent(conn, ranked, 2)]
    assert order == ["a", "b", "z", "c"]                                   # z is undated: after every dated one


@pytest.mark.parametrize("stages", ["reranker", "none"])
def test_a_recency_question_prefers_newer_passages(conn, fake, tmp_path, stages):  # G22
    _bilingual(conn, tmp_path, WEEKS)
    fake.rerank_reply = lambda b: [{"index": i, "relevance_score": 1.0 - ord(d[0]) / 1000}
                                   for i, d in enumerate(b["documents"])]
    st = retrieval.Stages(reranker=fake.reranker()) if stages == "reranker" else retrieval.Stages()

    def weeks(query):
        return [h.citation.path[-5:-3] for h in retrieval.retrieve(conn, Actor(U), query, k=2, stages=st)]
    assert weeks("Which models entered the pilot ring?") == ["30", "40"]
    assert weeks("Which models entered the pilot ring recently?") == ["40", "30"]  # rank sums: 1+0 < 0+3


def _blind(body):
    """A reranker with the G19 blind spot: a passage in the other language than the query scores 0."""
    from test_egress_audit import fake_relevance
    lang = retrieval.language(body["query"])
    return [{"index": i, "relevance_score": fake_relevance(body["query"], d) if retrieval.language(d) == lang else 0.0}
            for i, d in enumerate(body["documents"])]


def test_other_language_passages_are_reranked_with_a_translated_query(conn, fake, tmp_path):  # G19
    _bilingual(conn, tmp_path, {**ENGLISH, **TURKISH})
    fake.rerank_reply, fake.reply = _blind, "Yedekler ve loglar için ne yapılır?"
    stages = retrieval.Stages(reranker=fake.reranker(), translator=llmdap.Routed(fake.bridge(), "qwen"))
    ranked = retrieval.retrieve(conn, Actor(U), "logs of the backup", k=4, stages=stages)
    assert ranked[0].citation.path == "tr.md" and ranked[0].score > ranked[1].score   # scored in its own language
    chats = [(p, h) for p, h in fake.hits if p.endswith("/chat/completions")]
    assert len(chats) == 1 and chats[0][1]["x-llmdap-purpose"] == "translate"
    asked = next(b for p, b in fake.requests if p.endswith("/chat/completions"))
    assert [m["content"] for m in asked["messages"]][1:] == ["logs of the backup"]   # only the question goes out
    reranks = [b for p, b in fake.requests if p.endswith("/v1/rerank")]
    assert sorted(b["query"] for b in reranks) == ["Yedekler ve loglar için ne yapılır?", "logs of the backup"]
    assert conn.execute("SELECT source_books FROM model_call WHERE model = 'qwen'").fetchone() == ([],)


def test_no_translation_for_a_one_language_pool_or_a_bad_translation(conn, fake, tmp_path):  # G19
    _bilingual(conn, tmp_path, ENGLISH)
    stages = retrieval.Stages(reranker=fake.reranker(), translator=llmdap.Routed(fake.bridge(), "qwen"))
    retrieval.retrieve(conn, Actor(U), "logs of the backup", k=4, stages=stages)
    assert not any(p.endswith("/chat/completions") for p, _ in fake.hits)
    (tmp_path / "tr.md").write_text(TURKISH["tr.md"], encoding="utf-8")
    _bilingual(conn, tmp_path, {})
    fake.rerank_reply, fake.reply = _blind, "logs of the backup"                  # not a translation: ignored
    ranked = retrieval.retrieve(conn, Actor(U), "logs of the backup", k=4, stages=stages)
    assert ranked[-1].citation.path == "tr.md"                                   # the language reserve still holds


def test_a_grant_change_between_the_two_searches_lets_no_passage_of_the_removed_book_through(conn, fake, tmp_path,
                                                                                             monkeypatch):
    # Astra review #12: rights move from book A to book B while the query is translated; the first search saw A, the
    # second sees B. The merged pool is decided again in one statement, so A never reaches a model or the caller.
    for book, files in (("ing", ENGLISH), ("trk", TURKISH)):
        folder = tmp_path / book
        folder.mkdir()
        for name, text in files.items():
            (folder / name).write_text(text, encoding="utf-8")
        catalog.publish(conn, book=book, title=book, files=read_source(folder), policy=make_policy(
            sensitivity="normal", egress="local_only", protection="standard"), profile=profiles.spec("chunked"))
    authz.grant(conn, "book:ing", "read", U)
    query = "logs of the backup"
    assert {h.citation.book for h in search.search(conn, Actor(U), query, k=30)} == {"ing"}

    def switch(conn, translator, actor, query, pool):
        authz.revoke(conn, "book:ing", "read", U)
        authz.grant(conn, "book:trk", "read", U)
        return "Yedekler ve loglar için ne yapılır?"
    monkeypatch.setattr(retrieval, "translate", switch)
    fake.rerank_reply = lambda b: [{"index": i, "relevance_score": 0.5} for i in range(len(b["documents"]))]
    ranked = retrieval.retrieve(conn, Actor(U), query, k=8, stages=retrieval.Stages(reranker=fake.reranker()))
    assert ranked and {h.citation.book for h in ranked} == {"trk"}
    sent = [d for p, b in fake.requests if p.endswith("/v1/rerank") for d in b["documents"]]
    assert not any("archive is kept" in d for d in sent)                     # no passage of A went to the reranker
    assert conn.execute("SELECT count(*) FROM access_event WHERE object = 'book:ing' AND NOT allowed "
                        "AND reason = 'changed during search'").fetchone()[0] == 1


def test_an_oversized_question_is_refused_before_embedding_or_the_cache(conn, fake, book, monkeypatch):
    # Astra review #12: the 1,000-character limit holds on every path (search and ask) before the query is embedded
    # or becomes a cache key.
    monkeypatch.setattr(retrieval, "_vectors", retrieval._QueryCache())
    stages = retrieval.Stages(embedder=fake.embedder())
    long = "yedek " * 200
    with pytest.raises(ValueError, match="1..1000"):
        retrieval.retrieve(conn, Actor(U), long, stages=stages)
    with pytest.raises(ValueError, match="1..1000"):
        answers.ask(conn, fake.bridge(), Actor(U), long, model="qwen", stages=stages)
    with pytest.raises(ValueError, match="1..1000"):
        retrieval.query_vector(conn, fake.embedder(), Actor(U), long)
    for op in (lambda: server.op_ask("unused", fake.bridge(), "qwen", stages, Actor(U), long),
               lambda: server.op_search("unused", stages, Actor(U), long, 8)):
        with pytest.raises(server.BadRequest, match="1..1000"):                   # before any database connection
            op()
    assert fake.hits == [] and not retrieval._vectors.entries


def test_the_query_cache_is_bounded_in_bytes(monkeypatch):  # Astra review #12
    cache = retrieval._QueryCache()
    vector = search.QueryVector("bge-m3", [0.0] * 100)

    def key(q):
        return ("http://bridge", "local", "bge-m3", q)
    size = cache.size(key("a"), vector)
    monkeypatch.setattr(retrieval, "QUERY_CACHE_BYTES", 3 * size)
    for q in "abcd":
        cache.put(key(q), vector)
    assert list(cache.entries) == [key("b"), key("c"), key("d")] and cache.bytes == 3 * size
    assert cache.get(key("b")) == vector                                          # b is now the most recent
    cache.put(key("e"), vector)
    assert list(cache.entries) == [key("d"), key("b"), key("e")] and cache.bytes == 3 * size
    cache.put(key("f"), search.QueryVector("bge-m3", [0.0] * 1000))              # larger than the budget: not kept
    assert list(cache.entries) == [key("d"), key("b"), key("e")] and cache.bytes == 3 * size
