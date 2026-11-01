"""#159, #160: the catalog read for consumers. `GET /v1/books` / `list_books` names only the books and journals that the
caller may read now; `GET /v1/books/{book}/files` / `list_files` lists the files of the current version with the kstd
item information, behind the same book gate as `read_document`, a page at a time. Each publication records who stood
behind it (`approved_by`, `channel`; for a package also the issuer key and the sequence), shown on the book list, the
file list and `open_citation`."""
import asyncio
import getpass
import json
import os

import psycopg
import pytest
from starlette.testclient import TestClient

from kutuphane import authz, catalog, cli, db, llmdap, notes, packages, profiles, server, signing
from kutuphane.policy import make_policy
from kutuphane.source import read_source
from test_identity import token
from test_kstd import write_manifest
from test_server import PUBLIC, U, bearer, call_tool, keys, verifier  # noqa: F401 (fixtures)

POLICY = make_policy(sensitivity="normal", egress="local_only", protection="standard")


def publish(conn, root, book, **facts):
    return catalog.publish(conn, book=book, title=book.title(), files=read_source(root), policy=POLICY,
                           profile=profiles.spec("chunked"), **facts)


@pytest.fixture
def library(conn, okf_dir):
    """kitap (readable, with a kstd manifest), gizli (not readable), gunluk (a readable journal)."""
    write_manifest(okf_dir)
    kitap = publish(conn, okf_dir, "kitap", approved_by="user:admin")
    publish(conn, okf_dir, "gizli", approved_by="user:admin")
    notes.create_journal(conn, book="gunluk", title="Günlük", search=True, ai_input=True, policy=POLICY,
                         by="user:admin")
    authz.grant(conn, "book:kitap", "read", U)
    authz.grant(conn, "book:gunluk", "read", U)
    return kitap


@pytest.fixture
def client(library, verifier):
    app = server.create_app(dsn=os.environ["KUTUPHANE_TEST_DSN"], verifier=verifier, bridge=None, model=None,
                            public_url=PUBLIC)
    with TestClient(app) as c:
        yield c


def test_the_book_list_names_only_readable_books_and_journals(client, keys, library, conn):
    r = client.get("/v1/books", headers=bearer(keys))
    assert r.status_code == 200 and "gizli" not in r.text
    books = {b["book"]: b for b in r.json()["books"]}
    assert set(books) == {"kitap", "gunluk"}
    assert books["kitap"]["kind"] == "book" and books["gunluk"]["kind"] == "journal"
    assert books["kitap"]["content_id"] == library.content_id and books["kitap"]["profile_id"] == library.profile_id
    pub = books["kitap"]["publication"]
    assert pub["approved_by"] == "user:admin" and pub["channel"] == "ingest" and pub["published_at"]
    assert pub["issuer_key"] is None and pub["sequence"] is None
    assert books["gunluk"]["content_id"] is None and books["gunluk"]["publication"] is None
    events = conn.execute("SELECT object, allowed FROM access_event WHERE action = 'list_books' ORDER BY object")
    assert events.fetchall() == [("book:gunluk", True), ("book:kitap", True)]  # nothing about gizli
    assert client.get("/v1/books", headers=bearer(keys, sub="mehmet")).json() == {"books": []}


def test_an_unreadable_book_is_refused_as_a_missing_one(client, keys):
    hidden = client.get("/v1/books/gizli/files", headers=bearer(keys))
    missing = client.get("/v1/books/yok/files", headers=bearer(keys))
    assert hidden.status_code == missing.status_code == 403 and hidden.json() == missing.json()


def test_the_file_list_has_the_item_information_and_pages(client, keys, library):
    h = bearer(keys)
    first = client.get("/v1/books/kitap/files", params={"limit": 2}, headers=h).json()
    assert first["content_id"] == library.content_id and first["publication"]["approved_by"] == "user:admin"
    rest = client.get("/v1/books/kitap/files", params={"limit": 2, "cursor": first["next_cursor"]}, headers=h).json()
    paths = [f["path"] for f in first["files"] + rest["files"]]
    assert paths == sorted(paths) == ["index.md", "kstd.yaml", "politika/veri-saklama.md",
                                      "runbook/yedek-geri-yukleme.md"]
    assert rest["next_cursor"] is None
    runbook = next(f for f in rest["files"] if f["path"] == "runbook/yedek-geri-yukleme.md")
    assert runbook["passages"] > 0 and runbook["sha256"] and runbook["size"] > 0
    item = runbook["item"]
    assert item["license"] == "CC-BY-4.0" and item["origin"] == "human" and item["personal_data"] == "no"
    assert item["ai_use"]["search"] == "y" and item["applies_to"] == {"platform": ["Postgres 17"]}
    assert item["valid_from"] == "2026-01-01"
    for bad in ({"limit": 0}, {"limit": 501}, {"limit": "x"}):
        assert client.get("/v1/books/kitap/files", params=bad, headers=h).status_code == 400
    journal = client.get("/v1/books/gunluk/files", headers=h)
    assert journal.status_code == 404


def test_the_mcp_tools_have_the_same_gates(library, verifier, keys):
    mcp = server.build_mcp(dsn=os.environ["KUTUPHANE_TEST_DSN"], verifier=verifier, bridge=None, model=None,
                           public_url=PUBLIC)
    claims = asyncio.run(server._Verifier(verifier).verify_token(token(keys))).claims
    _, listed = call_tool(mcp, claims, "list_books", {})
    assert {b["book"] for b in listed["result"]} == {"kitap", "gunluk"}
    content, _ = call_tool(mcp, claims, "list_files", {"book": "kitap", "limit": 1})
    files = json.loads(content[0].text)
    assert [f["path"] for f in files["files"]] == ["index.md"] and files["next_cursor"] == "index.md"
    with pytest.raises(Exception, match="forbidden"):
        call_tool(mcp, claims, "list_files", {"book": "gizli"})


def test_open_citation_shows_who_approved_the_version(client, keys):
    h = bearer(keys)
    handle = client.get("/v1/search", params={"q": "kayıtlar saklanır"}, headers=h).json()["results"][0]["citation"]
    cited = client.get("/v1/citation", params={"handle": handle}, headers=h).json()
    assert cited["publication"]["approved_by"] == "user:admin" and cited["publication"]["channel"] == "ingest"


def test_ingest_records_the_cli_user(conn, okf_dir, monkeypatch, capsys):
    monkeypatch.setenv(db.DSN_ENV, os.environ["KUTUPHANE_TEST_DSN"])
    monkeypatch.delenv(llmdap.EMBED_ENV["route"], raising=False)
    base = ["ingest", str(okf_dir), "--book", "kitap", "--sensitivity", "normal", "--egress", "local_only",
            "--protection", "standard"]
    assert cli.main(base) == 0
    okf_dir.joinpath("yeni.md").write_text("# Yeni\n\nYeni bir sayfa.\n")
    assert cli.main([*base, "--by", "user:ayse"]) == 0
    capsys.readouterr()
    pubs = catalog.book_state(conn, "kitap")["publications"]
    assert [(p["approved_by"], p["channel"]) for p in pubs] == [(f"user:{getpass.getuser()}", "ingest"),
                                                                ("user:ayse", "ingest")]
    with pytest.raises(ValueError, match="approved_by"):
        publish(conn, okf_dir, "kitap", approved_by="Ayşe")


def test_package_approval_records_the_decider_the_key_and_the_sequence(conn, conn_b, okf_dir, tmp_path):
    publish(conn, okf_dir, "kitap", approved_by="user:admin")
    info = signing.generate(tmp_path / "a.key")
    packages.trust(conn_b, open(info["public_key"], "rb").read(), expected_fingerprint=info["fingerprint"],
                   name="A", by="user:admin")
    received = packages.receive(conn_b, packages.export(conn, "kitap", signing.load_private(tmp_path / "a.key")))
    packages.approve(conn_b, received["id"], by="user:x", policy=POLICY)
    state = catalog.book_state(conn_b, "kitap")
    pub = catalog.publications(conn_b, [("kitap", state["content_id"], state["profile_id"])])[
        ("kitap", state["content_id"], state["profile_id"])]
    assert pub == {"content_id": state["content_id"], "published_at": pub["published_at"], "channel": "import",
                   "approved_by": "user:x", "issuer_key": info["fingerprint"], "sequence": received["sequence"]}


def test_a_publication_without_facts_shows_nulls_and_the_columns_go_together(conn, okf_dir):
    old = publish(conn, okf_dir, "kitap")  # as every publication before migration 045
    key = ("kitap", old.content_id, old.profile_id)
    pub = catalog.publications(conn, [key])[key]
    assert pub["approved_by"] is None and pub["channel"] is None and pub["issuer_key"] is None
    with pytest.raises(psycopg.errors.CheckViolation):
        with conn.transaction():
            conn.execute("UPDATE publication SET channel = 'ingest' WHERE book = 'kitap'")
    with pytest.raises(psycopg.errors.CheckViolation):
        with conn.transaction():
            conn.execute("UPDATE publication SET channel = 'import', approved_by = 'user:x' WHERE book = 'kitap'")
