"""Hybrid search (D31): chunk vectors through LLMDAP embeddings (#222), fused with full text under the same
pre-filter. A vector can rank a chunk; it can never reveal one the caller may not read."""
import collections
import json
import os

import pytest

from kutuphane import authz, catalog, cli, db, llmdap, profiles, search, vectors
from kutuphane.gate import Actor
from kutuphane.policy import make_policy
from kutuphane.source import read_source
from test_egress_audit import FakeBridge, fake_vector

U, A = "user:ayse", "agent:kobra-7"
LOCAL = make_policy(sensitivity="normal", egress="local_only", protection="standard")
FAST = vectors.Settings(batch=1, backoff=0)  # one call per passage, retries without waiting


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
    assert vectors.index(conn, fake.embedder(), "kitap").embedded == total
    assert vectors.index(conn, fake.embedder(), "kitap").report()["vectors_added"] == 0  # nothing twice
    path, headers = fake.hits[-1]
    assert path == "/bridge/local/v1/embeddings" and headers["x-llmdap-purpose"] == "index"
    calls = conn.execute("SELECT principal, source_books, error FROM model_call").fetchall()
    assert calls and all(c == (vectors.INDEXER, ["kitap"], None) for c in calls)


def test_long_passages_are_embedded_in_smaller_batches(conn, fake, tmp_path):  # pilot radar: 504 on JSON briefs
    (tmp_path / "records.jsonl").write_text("".join(f'{{"n": {i}, "text": "{"x " * 1500}"}}\n' for i in range(20)))
    publish(conn, tmp_path)
    assert vectors.index(conn, fake.embedder(), "kitap").embedded == 20
    sizes = [sum(map(len, body["input"])) for path, body in fake.requests if path.endswith("/embeddings")]
    assert len(sizes) > 1 and all(s <= vectors.Settings().batch_chars for s in sizes)


def test_a_batch_holds_one_passage_even_beyond_the_char_budget():
    settings = vectors.Settings(batch=32)
    rows = [(None,) * 5 + ("y" * (settings.batch_chars + 1),), (None,) * 5 + ("z",)]
    assert [len(b) for b in vectors._batches(rows, settings)] == [1, 1]
    assert [len(b) for b in vectors._batches([(None,) * 5 + ("a",)] * 40, settings)] == [32, 8]


def test_an_oversized_passage_is_embedded_by_a_bounded_prefix(conn, fake, tmp_path):  # Astra review #11
    text = "kelime " * (vectors.EMBED_CHARS // 7 + 10) + "sonuncusözcük\n"
    (tmp_path / "uzun.md").write_text(text)
    catalog.publish(conn, book="kitap", title="kitap", files=read_source(tmp_path), policy=LOCAL,
                    profile=profiles.spec("whole"))
    assert vectors.index(conn, fake.embedder(), "kitap").embedded == 1
    sent = [s for path, body in fake.requests if path.endswith("/embeddings") for s in body["input"]]
    assert sent == [text[:vectors.EMBED_CHARS]]
    assert conn.execute("SELECT truncated FROM chunk_vector").fetchall() == [(True,)]
    stored, found = conn.execute("SELECT text, tsv @@ to_tsquery('turkish', 'sonuncusözcük') FROM chunk").fetchone()
    assert stored == text and found  # the passage is stored and found by full text whole


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
    total = conn.execute("SELECT count(*) FROM chunk WHERE book = 'kitap'").fetchone()[0]
    result = vectors.index(conn, fake.embedder(), "kitap", vectors.Settings(backoff=0))  # all passages in one call
    assert len(result.failed) + result.not_attempted == total and result.embedded == 0
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


def current_texts(conn, book="kitap"):
    return conn.execute("SELECT c.path, c.ordinal, c.text FROM chunk c JOIN book b ON b.slug = c.book "
                        "AND b.current_content = c.content_id AND b.current_profile = c.profile_id "
                        "WHERE c.book = %s ORDER BY c.path, c.ordinal", (book,)).fetchall()


def embedded_inputs(fake, since=0):
    return [t for path, body in fake.requests[since:] if path.endswith("/embeddings") for t in body["input"]]


def test_a_failed_batch_is_retried_and_the_run_goes_on(conn, fake, okf_dir):  # G12: one 504 stopped the whole run
    publish(conn, okf_dir)
    rows = current_texts(conn)
    assert len(rows) >= 3
    flaky, broken = rows[0][2], rows[1][2]
    attempts = collections.Counter()

    def status(body):
        (text,) = body["input"]
        attempts[text] += 1
        return 504 if text == broken or (text == flaky and attempts[text] == 1) else None

    fake.embed_status = status
    result = vectors.index(conn, fake.embedder(), "kitap", FAST)
    assert attempts[flaky] == 2 and attempts[broken] == 1 + FAST.retries
    assert [(f["path"], f["ordinal"]) for f in result.failed] == [rows[1][:2]] and "504" in result.failed[0]["error"]
    assert result.embedded == len(rows) - 1 and result.not_attempted == 0 and not result.complete
    fake.embed_status = None
    assert vectors.index(conn, fake.embedder(), "kitap", FAST).embedded == 1  # the next run adds the missing one


def test_index_stops_trying_when_the_embedder_is_down(conn, fake, okf_dir):  # G12: bounded, not hours of retries
    publish(conn, okf_dir)
    total = len(current_texts(conn))
    fake.embed_status = lambda body: 503
    settings = vectors.Settings(batch=1, backoff=0, give_up_after=2)
    result = vectors.index(conn, fake.embedder(), "kitap", settings)
    assert len(result.failed) == 2 and result.not_attempted == total - 2
    assert len(embedded_inputs(fake)) == 2 * (1 + settings.retries)
    assert result.report()["vectors_added"] == 0


def test_ingest_prints_the_publication_when_indexing_fails(conn, fake, okf_dir, monkeypatch, capsys):  # G12
    bridge = fake.bridge()
    for var, value in {db.DSN_ENV: os.environ["KUTUPHANE_TEST_DSN"], llmdap.ENV["url"]: bridge.url,
                       llmdap.ENV["key"]: bridge.key, llmdap.EMBED_ENV["route"]: bridge.route,
                       llmdap.EMBED_ENV["route_class"]: "local", llmdap.EMBED_ENV["model"]: "bge-m3"}.items():
        monkeypatch.setenv(var, value)
    monkeypatch.setattr(vectors.time, "sleep", lambda seconds: None)
    fake.embed_status = lambda body: 504
    ingest = ["ingest", str(okf_dir), "--book", "kitap", "--sensitivity", "normal", "--egress", "local_only",
              "--protection", "standard"]
    assert cli.main(ingest) == cli.INDEX_INCOMPLETE
    out = capsys.readouterr()
    report = json.loads(out.out)
    assert report["content_id"] == catalog.book_state(conn, "kitap")["content_id"]  # published and printed
    assert report["failed"] and report["vectors_added"] == 0
    assert "is published and live" in out.err and "kutuphane index kitap" in out.err
    assert cli.main(["index", "kitap"]) == cli.INDEX_INCOMPLETE                    # still down: reported, not raised
    capsys.readouterr()
    fake.embed_status = None
    assert cli.main(["index", "kitap", "--batch", "2"]) == 0
    assert json.loads(capsys.readouterr().out)["vectors_added"] == len(current_texts(conn))
    monkeypatch.delenv(llmdap.EMBED_ENV["route_class"])                           # pilot: published, then this error
    (okf_dir / "yeni.md").write_text("Yeni sayfa.\n", encoding="utf-8")
    assert cli.main(ingest) == 2
    assert "ROUTE_CLASS" in capsys.readouterr().err
    assert catalog.book_state(conn, "kitap")["content_id"] == report["content_id"]  # nothing was published


def test_a_new_version_embeds_only_the_changed_passages(conn, fake, okf_dir):  # G17
    publish(conn, okf_dir)
    vectors.index(conn, fake.embedder(), "kitap")
    since = len(fake.requests)
    changed = "runbook/yedek-geri-yukleme.md"
    with open(okf_dir / changed, "a", encoding="utf-8") as f:
        f.write("\n5. Geri yükleme süresini olay kaydına yaz.\n")
    version = publish(conn, okf_dir)
    result = vectors.index(conn, fake.embedder(), "kitap")
    rows = current_texts(conn)
    sent = embedded_inputs(fake, since)
    assert sent and set(sent) <= {t for p, _, t in rows if p == changed}
    assert result.embedded == len(sent) and result.reused == len(rows) - len(sent) > 0
    assert conn.execute("SELECT count(*) FROM chunk_vector WHERE content_id = %s",
                        (version.content_id,)).fetchone()[0] == len(rows)
    assert conn.execute("SELECT bool_and(n.embedding = o.embedding) FROM chunk_vector n JOIN chunk_vector o "
                        "ON o.input_sha256 = n.input_sha256 AND o.content_id <> n.content_id "
                        "WHERE n.content_id = %s", (version.content_id,)).fetchone()[0]
    since = len(fake.requests)
    publish(conn, okf_dir, book="ikinci")                                           # same text, another book
    assert vectors.index(conn, fake.embedder(), "ikinci").reused == 0               # vectors never cross a book
    assert len(embedded_inputs(fake, since)) == len(rows)


def test_a_new_chunker_reuses_the_vectors_of_unchanged_passages(conn, fake, okf_dir, monkeypatch):  # G27
    body = ("Yetki gövdesi uzun bir cümledir. " * 40).strip()
    (okf_dir / "kural.md").write_text(f"# Kural\n\n{body}\n\n## Son\n\nKısa.\n", encoding="utf-8")
    with monkeypatch.context() as m:                                    # the cut of chunker 4: "# Kural" alone
        m.setattr(profiles, "CHUNKER_VERSION", profiles.CHUNKER_VERSION - 1)
        m.setattr(profiles, "_attach_bare", lambda merged: [(s, e) for s, e, _bare in merged])
        old = publish(conn, okf_dir)
        vectors.index(conn, fake.embedder(), "kitap")
    since = len(fake.requests)
    new = publish(conn, okf_dir)                                        # same bytes, new profile
    assert new.profile_id != old.profile_id and new.content_id == old.content_id
    result = vectors.index(conn, fake.embedder(), "kitap")
    assert embedded_inputs(fake, since) == [f"# Kural\n\n{body}\n"]   # only the passage that got its heading
    assert result.embedded == 1 and result.reused == len(current_texts(conn)) - 1 > 0
    publish(conn, okf_dir, book="ikinci")
    assert vectors.index(conn, fake.embedder(), "ikinci").reused == 0  # still never across books


def test_migration_014_gives_old_vectors_the_reuse_key(conn, fake, okf_dir):  # G17: the radar books keep theirs
    (okf_dir / "uzun.md").write_text("ğüş İı " * (vectors.EMBED_CHARS // 7 + 10), encoding="utf-8")
    catalog.publish(conn, book="kitap", title="kitap", files=read_source(okf_dir), policy=LOCAL,
                    profile=profiles.spec("whole"))
    vectors.index(conn, fake.embedder(), "kitap")
    keys = "SELECT path, ordinal, input_sha256, truncated FROM chunk_vector ORDER BY path, ordinal"
    expected = conn.execute(keys).fetchall()
    assert any(row[3] for row in expected)                                          # a truncated passage is in
    conn.execute("DROP INDEX chunk_vector_reuse")
    conn.execute("ALTER TABLE chunk_vector DROP COLUMN input_sha256")
    conn.execute("DELETE FROM schema_migration WHERE name = '014_vector_input_hash.sql'")
    assert db.migrate(conn) == ["014_vector_input_hash.sql"]
    assert conn.execute(keys).fetchall() == expected


def test_migration_015_keys_a_vector_by_the_text_it_was_made_from(conn, fake, okf_dir):  # Astra review #12
    import hashlib
    long = "ğüş İı " * (vectors.EMBED_CHARS // 7 + 10)

    def version(suffix):
        (okf_dir / "uzun.md").write_text(long + suffix, encoding="utf-8")
        return catalog.publish(conn, book="kitap", title="kitap", files=read_source(okf_dir), policy=LOCAL,
                               profile=profiles.spec("whole")).content_id
    first = version("")
    vectors.index(conn, fake.embedder(), "kitap")
    # Before 013 the long passage was embedded whole (not truncated); 014 still gave it the key of its prefix.
    conn.execute("UPDATE chunk_vector SET truncated = false WHERE path = 'uzun.md'")
    second = version("başka bir son")                                       # same prefix, another suffix
    assert vectors.index(conn, fake.embedder(), "kitap").embedded == 0       # 014's key: the old vector was copied
    conn.execute("DELETE FROM schema_migration WHERE name = '015_vector_input_hash_backfill.sql'")
    assert db.migrate(conn) == ["015_vector_input_hash_backfill.sql"]
    keys = {(c, p): (bytes(k) if k is not None else None, t, text) for c, p, k, t, text in conn.execute(
        "SELECT v.content_id, v.path, v.input_sha256, v.truncated, c.text FROM chunk_vector v JOIN chunk c "
        "USING (book, content_id, profile_id, path, ordinal)").fetchall()}
    whole, truncated = keys[(first, "uzun.md")], keys[(second, "uzun.md")]
    assert not whole[1] and whole[0] == hashlib.sha256(whole[2].encode()).digest()  # the whole text it was made from
    assert truncated[1] and truncated[0] is None                             # perhaps a copy of it: never reused
    assert all(k == vectors.input_sha256(text) for (c, p), (k, t, text) in keys.items() if p != "uzun.md")
    since = len(fake.requests)
    third = version("üçüncü son")                                             # the same prefix once more
    assert vectors.index(conn, fake.embedder(), "kitap").embedded == 1       # embedded again, not copied
    assert embedded_inputs(fake, since) == [vectors.embedded_text(conn.execute(
        "SELECT text FROM chunk WHERE content_id = %s AND path = 'uzun.md'", (third,)).fetchone()[0])]


def test_concurrent_index_calls_store_every_vector(conn, fake, okf_dir):  # G18: configurable concurrency
    publish(conn, okf_dir)
    total = len(current_texts(conn))
    assert vectors.index(conn, fake.embedder(), "kitap", vectors.Settings(batch=1, concurrency=4)).embedded == total
    assert conn.execute("SELECT count(*) FROM chunk_vector").fetchone()[0] == total


def test_index_settings_come_from_the_environment_and_options(monkeypatch):  # G18
    assert vectors.Settings().concurrency == 1
    monkeypatch.setenv(vectors.SETTINGS_ENV["batch"], "4")
    monkeypatch.setenv(vectors.SETTINGS_ENV["concurrency"], "2")
    settings = vectors.Settings.from_env(concurrency=None, batch_chars=3000)  # an option wins over the environment
    assert (settings.batch, settings.batch_chars, settings.concurrency) == (4, 3000, 2)
    monkeypatch.setenv(vectors.SETTINGS_ENV["batch"], "0")
    with pytest.raises(ValueError, match="batch"):
        vectors.Settings.from_env()
    monkeypatch.setenv(vectors.SETTINGS_ENV["batch"], "acht")
    with pytest.raises(ValueError, match="KUTUPHANE_INDEX_BATCH"):
        vectors.Settings.from_env()
    with pytest.raises(ValueError, match="concurrency"):
        vectors.Settings(concurrency=vectors.MAX_CONCURRENCY + 1)
