"""M1d: profiles (AT-02), pre-filtered search (AT-04 search path), citations across versions (AT-07)."""
from datetime import datetime, timedelta, timezone

import pytest

from kutuphane import authz, catalog, ids, profiles, search
from kutuphane.gate import Actor, Denied
from kutuphane.policy import make_policy
from kutuphane.source import read_file, read_source

U, A = "user:ayse", "agent:kobra-7"
POLICY = make_policy(sensitivity="normal", egress="local_only", protection="standard")
LONG = "\n\n".join([
    "---\ntype: reference\n---",
    "# Birinci bölüm",
    "Paragraf bir. " * 40,
    "Paragraf iki. " * 40,
    "## İkinci bölüm",
    "Kısa paragraf.",
]) + "\n"


def publish(conn, path, book="kitap", profile="chunked"):
    return catalog.publish(conn, book=book, title=book, files=read_source(path), policy=POLICY,
                           profile=profiles.spec(profile))


def soon():
    return datetime.now(timezone.utc) + timedelta(hours=8)


def test_chunked_profile_cuts_at_headings_and_size():  # AT-02
    f = read_file("uzun.md", LONG.encode())
    chunks = profiles.split(profiles.spec("chunked"), f)
    full = LONG
    assert all(c.text == full[c.start:c.end] for c in chunks)
    assert all(a.end <= b.start for a, b in zip(chunks, chunks[1:]))           # no overlap, in order
    assert [c.text.splitlines()[0] for c in chunks if c.text.startswith("#")] == ["# Birinci bölüm",
                                                                                   "## İkinci bölüm"]
    assert all(len(c.text) <= profiles.TARGET_CHARS or "\n\n" not in c.text for c in chunks)
    assert "type: reference" not in "".join(c.text for c in chunks)            # frontmatter is not a passage


def test_whole_profile_is_the_full_text():  # AT-02
    f = read_file("uzun.md", LONG.encode())
    (only,) = profiles.split(profiles.spec("whole"), f)
    assert only.text == LONG and (only.start, only.end) == (0, len(LONG))


def test_component_versions_change_profile_id_not_content_id(conn, okf_dir, monkeypatch):  # AT-02
    first = publish(conn, okf_dir)
    monkeypatch.setattr(profiles, "CHUNKER_VERSION", profiles.CHUNKER_VERSION + 1)
    second = publish(conn, okf_dir)
    monkeypatch.setattr(profiles, "READER_VERSION", profiles.READER_VERSION + 1)
    third = publish(conn, okf_dir)
    assert len({first.profile_id, second.profile_id, third.profile_id}) == 3
    assert first.content_id == second.content_id == third.content_id


def test_fixture_chunk_boundaries_are_exact(okf_dir):  # AT-02: the expected cut, not just "some" cut
    f = read_source(okf_dir)
    doc = next(x for x in f if x.path == "politika/veri-saklama.md")
    (chunk,) = profiles.split(profiles.spec("chunked"), doc)
    text = doc.data.decode()
    assert chunk.start == text.index("# Veri saklama")
    assert chunk.end == len(text) and chunk.text.endswith("silinir.\n")


def test_pdf_chunks_carry_pages_and_offsets(tmp_path):  # AT-02 for PDF
    from conftest import make_pdf
    from pypdf import PdfWriter, PdfReader
    import io
    writer = PdfWriter()
    for text in ("Birinci sayfa metni", "Ikinci sayfa metni"):
        writer.add_page(PdfReader(io.BytesIO(make_pdf(text))).pages[0])
    buf = io.BytesIO()
    writer.write(buf)
    f = read_file("iki.pdf", buf.getvalue())
    chunks = profiles.split(profiles.spec("chunked"), f)
    assert [c.page for c in chunks] == [1, 2]
    full = "".join(page.extract_text() for page in PdfReader(io.BytesIO(buf.getvalue())).pages)
    assert all(full[c.start:c.end] == c.text for c in chunks)


def test_huge_block_is_cut_and_whole_profile_refuses_oversize():  # Astra #2: nothing silently unindexed
    blob = ("kelime " * 3000).strip() + " sonkelime"
    f = read_file("uzun.md", blob.encode())
    chunks = profiles.split(profiles.spec("chunked"), f)
    assert all(len(c.text) <= profiles.MAX_CHUNK_CHARS for c in chunks)
    assert "sonkelime" in chunks[-1].text and "".join(c.text for c in chunks) == blob
    big = read_file("buyuk.md", ("a " * (profiles.WHOLE_MAX_CHARS // 2 + 1)).encode())
    with pytest.raises(ValueError, match="too long for the whole profile"):
        profiles.split(profiles.spec("whole"), big)


def test_search_finds_stemmed_turkish_and_cites(conn, okf_dir):
    r = publish(conn, okf_dir)
    authz.grant(conn, "book:kitap", "read", U)
    hits = search.search(conn, Actor(U), "kayıtlar ne kadar saklanır?")
    assert hits and hits[0].citation.path == "politika/veri-saklama.md"
    assert (hits[0].citation.content_id, hits[0].citation.profile_id) == (r.content_id, r.profile_id)


def test_search_never_shows_unauthorized_books(conn, okf_dir, tmp_path):  # AT-04 search path
    publish(conn, okf_dir, book="acik")
    publish(conn, okf_dir, book="gizli")
    authz.grant(conn, "book:acik", "read", U)
    hits = search.search(conn, Actor(U), "kayıtlar saklanır", k=50)
    assert hits and {h.citation.book for h in hits} == {"acik"}
    assert search.search(conn, Actor("user:mehmet"), "kayıtlar saklanır") == []


def test_agent_search_needs_delegation_and_activate_for_instructions(conn, okf_dir):  # AT-04, AT-12
    (okf_dir / "skill.md").write_text("---\ntype: skill\n---\nKayıtları özetle ve sakla.\n", encoding="utf-8")
    publish(conn, okf_dir)
    authz.grant(conn, "book:kitap", "read", U)
    agent = Actor(A, on_behalf_of=U)
    assert search.search(conn, agent, "kayıt") == []                            # no delegation yet
    did = authz.delegate(conn, delegator=U, delegate_to=A, obj="book:kitap", mode="read", expires_at=soon())
    assert "skill.md" not in {h.citation.path for h in search.search(conn, agent, "kayıt", k=50)}
    assert "skill.md" in {h.citation.path for h in search.search(conn, Actor(U), "kayıt", k=50)}
    authz.grant(conn, "book:kitap", "activate", U)
    authz.delegate(conn, delegator=U, delegate_to=A, obj="book:kitap", mode="activate", expires_at=soon())
    assert "skill.md" in {h.citation.path for h in search.search(conn, agent, "kayıt", k=50)}
    authz.revoke_delegation(conn, did)
    assert search.search(conn, agent, "kayıt") == []


def _revoke_after_first_prefilter(monkeypatch, action):
    real, calls = authz.allowed, []

    def wrapped(*args):
        out = real(*args)
        calls.append(1)
        if len(calls) == 1:
            action()  # lands between the pre-filter and the single final check
        return out
    monkeypatch.setattr(authz, "allowed", wrapped)
    return calls


def test_revocation_between_prefilter_and_delivery(conn, conn2, okf_dir, monkeypatch):  # AT-04
    publish(conn, okf_dir)
    authz.grant(conn, "book:kitap", "read", U)
    _revoke_after_first_prefilter(monkeypatch, lambda: authz.revoke(conn2, "book:kitap", "read", U))
    actor = Actor(U)
    assert search.search(conn, actor, "kayıtlar") == []
    (allowed, reason), = conn.execute("SELECT allowed, reason FROM access_event WHERE correlation_id = %s",
                                      (actor.correlation_id,)).fetchall()
    assert allowed is False and reason == "changed during search"


def test_multi_book_result_is_checked_as_a_whole(conn, conn2, okf_dir, monkeypatch):  # AT-04, Astra #2
    publish(conn, okf_dir, book="aaa")
    publish(conn, okf_dir, book="bbb")
    for book in ("aaa", "bbb"):
        authz.grant(conn, f"book:{book}", "read", U)
    _revoke_after_first_prefilter(monkeypatch, lambda: authz.revoke(conn2, "book:aaa", "read", U))
    hits = search.search(conn, Actor(U), "kayıtlar saklanır", k=50)
    assert hits and {h.citation.book for h in hits} == {"bbb"}       # aaa gone, not partially served


def test_revoked_books_do_not_consume_k(conn, conn2, okf_dir, monkeypatch):  # Astra #2: counts unaffected
    publish(conn, okf_dir, book="aaa")
    publish(conn, okf_dir, book="bbb")
    for book in ("aaa", "bbb"):
        authz.grant(conn, f"book:{book}", "read", U)
    _revoke_after_first_prefilter(monkeypatch, lambda: authz.revoke(conn2, "book:aaa", "read", U))
    (hit,) = search.search(conn, Actor(U), "kayıtlar saklanır", k=1)  # aaa ranks first by name tie-break
    assert hit.citation.book == "bbb"


def test_rights_changing_twice_refuses(conn, conn2, okf_dir, monkeypatch):
    publish(conn, okf_dir)
    authz.grant(conn, "book:kitap", "read", U)
    real = authz.allowed
    flips = iter([lambda: authz.revoke(conn2, "book:kitap", "read", U),
                  lambda: authz.grant(conn2, "book:kitap", "read", U),
                  lambda: authz.revoke(conn2, "book:kitap", "read", U),
                  lambda: None])

    def wrapped(*args):
        out = real(*args)
        next(flips)()
        return out
    monkeypatch.setattr(authz, "allowed", wrapped)
    with pytest.raises(search.SearchChanged):
        search.search(conn, Actor(U), "kayıtlar")


def test_search_log_names_delivered_chunks(conn, okf_dir):  # AT-09 Core side
    publish(conn, okf_dir)
    authz.grant(conn, "book:kitap", "read", U)
    actor = Actor(U)
    hits = search.search(conn, actor, "kayıtlar saklanır")
    profile_id, items = conn.execute("SELECT profile_id, items FROM access_event WHERE correlation_id = %s",
                                     (actor.correlation_id,)).fetchone()
    assert profile_id == hits[0].citation.profile_id and items == [h.citation.handle for h in hits]


def test_old_citation_opens_old_passage_with_current_rights(conn, okf_dir):  # AT-07
    publish(conn, okf_dir)
    authz.grant(conn, "book:kitap", "read", U)
    (hit, *_) = search.search(conn, Actor(U), "kayıtlar saklanır")
    target = okf_dir / "politika" / "veri-saklama.md"
    target.write_text(target.read_text(encoding="utf-8").replace("iki yıl", "üç yıl"), encoding="utf-8")
    publish(conn, okf_dir)
    assert "üç yıl" in search.search(conn, Actor(U), "kayıtlar saklanır")[0].text
    reopened = search.open_citation(conn, Actor(U), hit.citation)
    assert reopened.text == hit.text and "iki yıl" in reopened.text
    authz.revoke(conn, "book:kitap", "read", U)
    with pytest.raises(Denied):
        search.open_citation(conn, Actor(U), hit.citation)


def test_search_input_is_bounded(conn):
    for bad in ("", "  ", "x" * (search.MAX_QUERY_CHARS + 1)):
        with pytest.raises(ValueError):
            search.search(conn, Actor(U), bad)
    with pytest.raises(ValueError):
        search.search(conn, Actor(U), "kayıt", k=search.MAX_K + 1)


def test_chunker_changes_are_new_profiles():  # Astra #3: behavior change => new id
    current = profiles.spec("chunked")
    older = [{**current, "components": {**current["components"], "chunker": f"paragraph@{n}"}}
             for n in range(1, profiles.CHUNKER_VERSION)]
    assert older and all(ids.profile_id(o) != ids.profile_id(current) for o in older)
    one_block = read_file("blok.md", ("kelime " * 3000).encode())
    assert len(profiles.split(current, one_block)) > 1                  # v1 kept this as one chunk


JSONL = "\n".join([
    '{"id": 1, "title": "NVFP4 Blackwell destegi", "model": "claude"}',
    '{"id": 2, "title": "Pulse halkalarin yerini aldi", "model": "qwen"}',
    "",
    '{"id": 3, "title": "vLLM guvenlik duyurusu", "model": "claude"}',
]) + "\n"


def test_jsonl_book_is_searchable_per_record(conn, tmp_path):  # G1: one record, one passage, line in the citation
    (tmp_path / "haberler.jsonl").write_text(JSONL, encoding="utf-8")
    publish(conn, tmp_path)
    authz.grant(conn, "book:kitap", "read", U)
    rows = conn.execute("SELECT ordinal, line, text FROM chunk WHERE path = 'haberler.jsonl' ORDER BY ordinal").fetchall()
    assert [(o, line) for o, line, _ in rows] == [(0, 1), (1, 2), (2, 4)]
    (hit,) = search.search(conn, Actor(U), "guvenlik duyurusu")
    assert hit.citation.path == "haberler.jsonl" and hit.line == 4
    assert hit.text.strip() == JSONL.splitlines()[3]
    assert search.open_citation(conn, Actor(U), hit.citation).line == 4


FORMATS = {
    "notlar.txt": "Yedekler her gece alinir: zebrakelime.\n",
    "ayar.yaml": "servis:\n  aciklama: kaplankelime\n",
    "veri.json": '{"aciklama": "aslankelime"}\n',
    "ayar.toml": '[servis]\naciklama = "kartalkelime"\n',
    "kur.sh": "#!/bin/sh\n# kurtkelime\necho tamam\n",
    "arac.py": "def f():\n    return 'ceylankelime'\n",
    "arac.ts": "export const ad = 'tilkikelime';\n",
    "arac.js": "const ad = 'sincapkelime';\n",
    "harita.xml": "<kok><ad>baykuskelime</ad></kok>\n",
    "tablo.csv": "ad,deger\nmartikelime,1\n",
    "sayfa.html": "<html><head><script>var x = 'gizlikelime';</script><style>p{}</style></head>"
                  "<body><p>Görünen yunuskelime metni.</p><!-- yorumkelime --></body></html>\n",
}


def test_text_formats_are_searchable_and_html_only_by_visible_text(conn, tmp_path):  # G1
    for name, text in FORMATS.items():
        (tmp_path / name).write_text(text, encoding="utf-8")
    publish(conn, tmp_path)
    authz.grant(conn, "book:kitap", "read", U)
    words = {"notlar.txt": "zebrakelime", "ayar.yaml": "kaplankelime", "veri.json": "aslankelime",
             "ayar.toml": "kartalkelime", "kur.sh": "kurtkelime", "arac.py": "ceylankelime", "arac.ts": "tilkikelime",
             "arac.js": "sincapkelime", "harita.xml": "baykuskelime", "tablo.csv": "martikelime",
             "sayfa.html": "yunuskelime"}
    for name, word in words.items():
        assert [h.citation.path for h in search.search(conn, Actor(U), word)] == [name], word
    assert search.search(conn, Actor(U), "gizlikelime") == [] and search.search(conn, Actor(U), "yorumkelime") == []
