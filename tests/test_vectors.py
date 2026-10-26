"""Hybrid search (D31): chunk vectors through LLMDAP embeddings (#222), fused with full text under the same
pre-filter. A vector can rank a chunk; it can never reveal one the caller may not read."""
import pytest

from kutuphane import authz, catalog, llmdap, profiles, search, vectors
from kutuphane.gate import Actor
from kutuphane.policy import make_policy
from kutuphane.source import read_source
from test_egress_audit import FakeBridge, fake_vector

U, A = "user:ayse", "agent:kobra-7"
LOCAL = make_policy(sensitivity="normal", egress="local_only", protection="standard")


@pytest.fixture
def fake():
    f = FakeBridge()
    yield f
    f.server.shutdown()


def publish(conn, path, book="kitap", policy=LOCAL):
    return catalog.publish(conn, book=book, title=book, files=read_source(path), policy=policy,
                           profile=profiles.spec("chunked"))


def chunk_text(conn, book, path):
    return conn.execute("SELECT text FROM chunk WHERE book = %s AND path = %s ORDER BY ordinal LIMIT 1",
                        (book, path)).fetchone()[0]


def test_index_embeds_through_llmdap_once(conn, fake, okf_dir):
    publish(conn, okf_dir)
    total = conn.execute("SELECT count(*) FROM chunk WHERE book = 'kitap'").fetchone()[0]
    assert vectors.index(conn, fake.embedder(), "kitap") == total
    assert vectors.index(conn, fake.embedder(), "kitap") == 0                    # nothing twice
    path, headers = fake.hits[-1]
    assert path == "/bridge/local/v1/embeddings" and headers["x-llmdap-purpose"] == "index"
    calls = conn.execute("SELECT principal, source_books, error FROM model_call").fetchall()
    assert calls and all(c == (vectors.INDEXER, ["kitap"], None) for c in calls)


def test_long_passages_are_embedded_in_smaller_batches(conn, fake, tmp_path):  # pilot radar: 504 on JSON briefs
    (tmp_path / "records.jsonl").write_text("".join(f'{{"n": {i}, "text": "{"x " * 1500}"}}\n' for i in range(20)))
    publish(conn, tmp_path)
    assert vectors.index(conn, fake.embedder(), "kitap") == 20
    sizes = [sum(map(len, body["input"])) for path, body in fake.requests if path.endswith("/embeddings")]
    assert len(sizes) > 1 and all(s <= vectors.BATCH_CHARS for s in sizes)


def test_a_batch_holds_one_passage_even_beyond_the_char_budget():
    rows = [(None,) * 5 + ("y" * (vectors.BATCH_CHARS + 1),), (None,) * 5 + ("z",)]
    assert [len(b) for b in vectors._batches(rows)] == [1, 1]
    assert [len(b) for b in vectors._batches([(None,) * 5 + ("a",)] * 40)] == [vectors.BATCH, 8]


def test_local_only_book_is_never_embedded_on_a_cloud_route(conn, fake, okf_dir):  # E5 egress
    publish(conn, okf_dir)
    with pytest.raises(llmdap.EgressError, match="kitap"):
        vectors.index(conn, fake.embedder(route_class="cloud"), "kitap")
    assert fake.hits == [] and conn.execute("SELECT count(*) FROM chunk_vector").fetchone()[0] == 0


def test_vector_finds_what_words_do_not_but_only_in_readable_books(conn, fake, okf_dir):  # AT-04 on the vector path
    publish(conn, okf_dir)
    publish(conn, okf_dir, book="gizli")
    for book in ("kitap", "gizli"):
        vectors.index(conn, fake.embedder(), book)
    authz.grant(conn, "book:kitap", "read", U)
    target = chunk_text(conn, "kitap", "politika/veri-saklama.md")
    exact = search.QueryVector("bge-m3", fake_vector(target))
    hits = search.search(conn, Actor(U), "zzqx", k=3, vector=exact)               # no word matches at all
    assert hits[0].citation.path == "politika/veri-saklama.md"
    assert {h.citation.book for h in hits} == {"kitap"}                            # "gizli" matches as well, unseen
    other_model = search.QueryVector("baska-model", fake_vector(target))
    assert search.search(conn, Actor(U), "zzqx", k=3, vector=other_model) == []    # vectors of another model ignored


def test_instruction_chunks_need_activate_on_the_vector_path(conn, fake, okf_dir):  # K3 (D37)
    (okf_dir / "skill.md").write_text("---\ntype: skill\n---\nYedekten geri yükleme adımlarını uygula.\n",
                                      encoding="utf-8")
    publish(conn, okf_dir)
    vectors.index(conn, fake.embedder(), "kitap")
    authz.grant(conn, "book:kitap", "read", A)
    exact = search.QueryVector("bge-m3", fake_vector(chunk_text(conn, "kitap", "skill.md")))
    assert "skill.md" not in {h.citation.path for h in search.search(conn, Actor(A), "zzqx", k=8, vector=exact)}
    authz.grant(conn, "book:kitap", "activate", A)
    assert "skill.md" in {h.citation.path for h in search.search(conn, Actor(A), "zzqx", k=8, vector=exact)}


def test_failed_query_embedding_falls_back_to_full_text(conn, fake, okf_dir):
    publish(conn, okf_dir)
    authz.grant(conn, "book:kitap", "read", U)
    actor = Actor(U)
    broken = llmdap.Routed(fake.bridge(key="llmdap_sk_" + "x" * 43), "bge-m3")
    assert vectors.query_vector(conn, broken, actor, "kayıtlar") is None
    assert conn.execute("SELECT http_status FROM model_call WHERE correlation_id = %s",
                        (actor.correlation_id,)).fetchone() == (401,)              # the failure is on record
    assert search.search(conn, actor, "kayıtlar saklanır", vector=None)          # full text still answers


@pytest.mark.parametrize("reply", [
    lambda texts: [{"index": 0, "embedding": fake_vector(t)} for t in texts],          # every vector claims index 0
    lambda texts: [{"index": i, "embedding": [float("nan")] * 16} for i, _ in enumerate(texts)],
    lambda texts: [{"index": i, "embedding": [0.0] * 16} for i, _ in enumerate(texts)],
    lambda texts: [{"index": i, "embedding": []} for i, _ in enumerate(texts)],
])
def test_bad_embeddings_answers_are_refused_not_stored(conn, fake, okf_dir, reply):  # Astra review #5
    publish(conn, okf_dir)
    fake.embed_reply = reply
    with pytest.raises(llmdap.EgressError):
        vectors.index(conn, fake.embedder(), "kitap")
    assert conn.execute("SELECT count(*) FROM chunk_vector").fetchone()[0] == 0


def test_one_model_one_width(conn, fake, okf_dir):  # Astra review #5
    publish(conn, okf_dir)
    publish(conn, okf_dir, book="ikinci")
    vectors.index(conn, fake.embedder(), "kitap")
    authz.grant(conn, "book:kitap", "read", U)
    fake.embed_reply = lambda texts: [{"index": i, "embedding": fake_vector(t, dims=8)} for i, t in enumerate(texts)]
    with pytest.raises(llmdap.EgressError, match="dimensions"):
        vectors.index(conn, fake.embedder(), "ikinci")                              # same name, new width
    assert vectors.query_vector(conn, fake.embedder(), Actor(U), "kayıtlar") is None  # search falls back to text
    assert search.search(conn, Actor(U), "kayıtlar saklanır")


def test_every_principal_is_a_valid_llmdap_label():  # LLMDAP isChainLabel: at most 128 characters
    longest = "agent:" + "a" * 122
    assert authz.PRINCIPAL.match(longest) and len(longest) == 128
    assert not authz.PRINCIPAL.match("agent:" + "a" * 123)
