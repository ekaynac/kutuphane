"""#138 option 2 (guide: operations.md, "One book per scope"): each scope is a book, the shared content is one more
book that every scope reads. A role with grants on scope A and the shared book never receives a scope-B passage or
note from search, ask evidence, open_citation, neighbours or query_notes. Item-level access (G10) is not built."""
import pytest

from kutuphane import answers, authz, catalog, profiles, search
from kutuphane.gate import Actor, Denied, NotFound
from kutuphane.notesquery import neighbours, query_notes
from kutuphane.source import read_source
from test_kstd import fake  # noqa: F401 (a fixture)
from test_notes_query import approved, journal, link, ref
from test_search import POLICY

KAYSERI, ANKARA = "user:kayseri-op", "user:ankara-op"
A_BOOKS, B_BOOKS = {"scope-kayseri", "shared"}, {"scope-ankara", "shared"}
Q = "kayıtlar saklanır yedek geri yükleme politika kitabı"


@pytest.fixture
def lib(conn, okf_dir):
    for book in ("scope-kayseri", "scope-ankara", "shared"):
        catalog.publish(conn, book=book, title=book, files=read_source(okf_dir), policy=POLICY,
                        profile=profiles.spec("chunked"))
    for who, books in ((KAYSERI, A_BOOKS), (ANKARA, B_BOOKS)):
        for book in books:
            authz.grant(conn, f"book:{book}", "read", who)
    journal(conn, "mem-kayseri", readers=(KAYSERI,))
    journal(conn, "mem-ankara", readers=(ANKARA,))
    journal(conn, "mem-shared", readers=(KAYSERI, ANKARA))
    a = approved(conn, "mem-kayseri", "kayseri disk dolu bulgusu")
    b = approved(conn, "mem-ankara", "ankara disk dolu bulgusu")
    s = approved(conn, "mem-shared", "disk dolu genel kural")
    for src, dst in ((a, b), (a, s), (b, s)):
        link(conn, src, "contradicts", dst)
    return conn, {"a": a, "b": b, "s": s}


def books(hits) -> set:
    return {h.citation.book for h in hits}


def test_search_and_open_citation_stay_in_scope(lib):
    conn, _ = lib
    mine = search.search(conn, Actor(KAYSERI), Q, k=50)
    theirs = search.search(conn, Actor(ANKARA), Q, k=50)
    assert books(mine) == A_BOOKS and books(theirs) == B_BOOKS        # one call joins the scope and the shared book
    assert search.search(conn, Actor(KAYSERI), Q, k=50, scope=search.Scope.of(["scope-ankara"])) == []
    other = next(h for h in theirs if h.citation.book == "scope-ankara")
    with pytest.raises((Denied, NotFound)):
        search.open_citation(conn, Actor(KAYSERI), other.citation)
    assert search.open_citation(conn, Actor(ANKARA), other.citation).text == other.text


def test_ask_evidence_stays_in_scope(lib, fake):  # noqa: F811
    conn, _ = lib
    answers.ask(conn, fake.bridge(), Actor(KAYSERI), Q, model="qwen")
    sent = [b for path, b in fake.requests if path.endswith("/chat/completions")][-1]["messages"][1]["content"]
    assert "scope-kayseri/" in sent and "scope-ankara/" not in sent
    sources = conn.execute("SELECT sources FROM answer WHERE principal = %s", (KAYSERI,)).fetchone()[0]
    assert {s["book"] for s in sources} <= A_BOOKS


def test_notes_stay_in_scope(lib):
    conn, seqs = lib
    found = query_notes(conn, Actor(KAYSERI), for_model=False, text="disk dolu")
    assert {i["ref"].split("@")[0] for i in found["items"]} == {"mem-kayseri", "mem-shared"}
    assert query_notes(conn, Actor(KAYSERI), for_model=False, book=["mem-ankara"])["items"] == []
    near = neighbours(conn, Actor(KAYSERI), for_model=False, ref=ref(conn, seqs["a"]))
    assert [n["ref"] for n in near["nodes"]] == [ref(conn, seqs["s"])]
    assert all("mem-ankara" not in (e["src"] + e["dst"]) for e in near["edges"])
    shared = neighbours(conn, Actor(KAYSERI), for_model=False, ref=ref(conn, seqs["s"]))
    assert [n["ref"] for n in shared["nodes"]] == [ref(conn, seqs["a"])]
    with pytest.raises((Denied, NotFound)):
        neighbours(conn, Actor(KAYSERI), for_model=False, ref=ref(conn, seqs["b"]))
