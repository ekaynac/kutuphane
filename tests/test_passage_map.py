"""#140: after a re-index (a new profile id or a new content version), note citations and passage links (`about`,
`derived_from`) follow to the new passage through the passage map (migration 040, passagemap.py)."""
import json

import pytest

from kutuphane import catalog, cli, curatorqueue, decisions, gate, notes, notesquery, passagemap, profiles, server
from kutuphane.gate import Actor
from kutuphane.passagemap import choose
from kutuphane.source import read_source
from test_notes import LOCAL, allow, journal, mcp
from test_skillscan import REF, agent_with, fake, folder  # noqa: F401  (fake, folder: fixtures)

J, BOOK = "hafiza", "kitap"
RUNBOOK = "runbook/yedek-geri-yukleme.md"
PERSON = Actor("user:ayse", channel="http")


def publish(conn, path, profile="chunked", policy=LOCAL):
    return catalog.publish(conn, book=BOOK, title=BOOK, files=read_source(path), policy=policy,
                           profile=profiles.spec(profile))


def handle(conn, path=RUNBOOK, ordinal=None) -> str:
    """A passage of the book's current version: `ordinal`, or the last one of the path."""
    row = conn.execute(
        "SELECT c.book, c.content_id, c.profile_id, c.path, c.ordinal FROM chunk c JOIN book b ON b.slug = c.book "
        "AND b.current_content = c.content_id AND b.current_profile = c.profile_id WHERE c.book = %s AND c.path = %s "
        "AND (%s::int IS NULL OR c.ordinal = %s) ORDER BY c.ordinal DESC LIMIT 1",
        (BOOK, path, ordinal, ordinal)).fetchone()
    return passagemap.handle(row)


def propose(conn, text, **args):
    return notes.propose(conn, mcp(), {"book": J, "kind": "finding", "text": text, **args})[0]["ref"]


def cites(conn, ref):
    return notesquery.open_note(conn, PERSON, for_model=False, ref=ref)["note"]["citations"]


def neighbours(conn, ref, **kw):
    return notesquery.neighbours(conn, PERSON, for_model=False, ref=ref, sets=["open"], **kw)


@pytest.fixture
def mem(conn, okf_dir):
    publish(conn, okf_dir)
    journal(conn)
    allow(conn, J, "read", "propose")
    allow(conn, BOOK, "read")
    return conn


# --- choosing a successor --------------------------------------------------------------------------------------

def test_choose_prefers_the_same_text_then_the_largest_overlap_then_none():
    old = "Servisi bakım kipine al ve yedeği seç."
    assert choose(old, 3, [(0, "başka"), (2, old), (5, old)]) == (2, "exact")  # the nearest ordinal wins a tie
    assert choose(old, 0, [(0, "# Başlık\n\n" + old + " Sonra geri yükle."), (1, "yedeği seç.")]) == (0, "overlap")
    assert choose(old, 0, [(0, "Servisi durdur."), (1, "Tamamen başka bir metin.")]) == (None, "none")
    assert choose(old, 0, []) == (None, "none")
    half = "Servisi bakım kipine al"  # 3 of the 6 word pairs: exactly OVERLAP_MIN
    assert choose(old, 0, [(4, half)]) == (4, "overlap")
    assert choose(old, 0, [(4, "Servisi bakım kipine")]) == (None, "none")  # 2 of 6


# --- a re-index under a new profile ------------------------------------------------------------------------------

def test_a_reindex_moves_citations_and_links_and_neighbours_follow(mem, okf_dir, monkeypatch):
    """The acceptance of #140: neighbours from the new handle returns the note; the note still opens its original
    passage; `about` and `derived_from` links to the passage follow too."""
    old = handle(mem)
    cited = propose(mem, "Bakım kipi geri yüklemeden önce gelir", citations=[old])
    derived = propose(mem, "Geri yükleme adımları", links=[{"type": "derived_from", "ref": old}])
    about = propose(mem, "Geri yükleme hakkında bir bulgu")
    notes.link(mem, mcp(), about, "about", old)
    assert cites(mem, cited) == [{"ref": old, "status": "current"}]

    monkeypatch.setattr(profiles, "CHUNKER_VERSION", profiles.CHUNKER_VERSION + 1)  # a new chunker: a new profile id
    result = publish(mem, okf_dir)
    new = handle(mem)
    assert new != old and new.split("/", 2)[2] == old.split("/", 2)[2]  # same content, path and ordinal
    assert result.passage_map == {"book": BOOK, "content_id": result.content_id, "profile_id": result.profile_id,
                                  "passages": 1, "added": 1, "exact": 1, "overlap": 0, "none": 0}
    assert cites(mem, cited) == [{"ref": old, "status": "moved", "moved_to": new, "match": "exact"}]

    near = neighbours(mem, new)
    assert sorted(n["ref"] for n in near["nodes"]) == sorted([cited, derived, about])
    assert sorted((e["src"], e["type"], e["dst"], e["original"]) for e in near["edges"]) == sorted(
        [(cited, "cites", new, old), (derived, "derived_from", new, old), (about, "about", new, old)])
    assert sorted(n["ref"] for n in neighbours(mem, old)["nodes"]) == sorted([cited, derived, about])
    assert [n["ref"] for n in neighbours(mem, new, types=["about"])["nodes"]] == [about]

    # the original passage still opens, and says where it is now; the new one is current
    monkeypatch.setattr(server, "_run", lambda _dsn, fn: fn(mem))
    opened = server.op_citation(None, PERSON, old)
    assert (opened["citation"], opened["status"], opened["moved_to"], opened["match"]) == (old, "moved", new, "exact")
    assert opened["text"] is not None
    assert server.op_citation(None, PERSON, new)["status"] == "current"
    listed = notesquery.query_notes(mem, PERSON, for_model=False, book=[J], sets=["open"])
    assert {i["ref"]: i["citations"] for i in listed["items"]}[cited] == [
        {"ref": old, "status": "moved", "moved_to": new, "match": "exact"}]


def test_a_new_profile_that_cuts_differently_maps_by_overlap(mem, okf_dir):
    old = handle(mem)
    cited = propose(mem, "Bütünlük denetimi şart", citations=[old])
    publish(mem, okf_dir, profile="whole")  # one passage per file: the old one is inside it
    new = handle(mem)
    assert new.endswith("#0") and new != old
    assert cites(mem, cited) == [{"ref": old, "status": "moved", "moved_to": new, "match": "overlap"}]
    assert [n["ref"] for n in neighbours(mem, new)["nodes"]] == [cited]


def test_a_passage_with_no_successor_is_stale_and_never_dropped(mem, okf_dir, monkeypatch, capsys):
    old = handle(mem)
    cited = propose(mem, "Geri yükleme sonrası geri bildirim", citations=[old])
    (okf_dir / RUNBOOK).write_text("# Yeni süreç\n\nTamamen farklı bir içerik burada.\n", encoding="utf-8")
    result = publish(mem, okf_dir)  # a new content version: the cited text is gone
    assert (result.passage_map["none"], result.passage_map["added"]) == (1, 1)
    assert cites(mem, cited) == [{"ref": old, "status": "stale"}]
    assert [n["ref"] for n in neighbours(mem, old)["nodes"]] == [cited]  # the old handle still finds it
    assert neighbours(mem, handle(mem))["nodes"] == []  # the new passage is another passage
    monkeypatch.setattr(server, "_run", lambda _dsn, fn: fn(mem))
    assert server.op_citation(None, PERSON, old)["status"] == "stale"
    cli._warn_stale(result.passage_map)
    assert "1 cited or linked passages" in capsys.readouterr().err


def test_a_note_written_later_on_an_old_passage_is_mapped_in_its_write(mem, okf_dir, monkeypatch):
    old = handle(mem)
    monkeypatch.setattr(profiles, "CHUNKER_VERSION", profiles.CHUNKER_VERSION + 1)
    publish(mem, okf_dir)
    assert mem.execute("SELECT count(*) FROM passage_map").fetchone()[0] == 0  # nothing referenced yet
    cited = propose(mem, "Eski bir pasaja atıf", citations=[old])
    assert mem.execute("SELECT match FROM passage_map").fetchall() == [("exact",)]
    assert [n["ref"] for n in neighbours(mem, handle(mem))["nodes"]] == [cited]


def test_two_reindexes_map_straight_to_the_current_version(mem, okf_dir, monkeypatch):
    old = handle(mem)
    cited = propose(mem, "İki kez yeniden dizinlenen pasaj", citations=[old])
    for step in (1, 2):
        monkeypatch.setattr(profiles, "CHUNKER_VERSION", profiles.CHUNKER_VERSION + step)
        publish(mem, okf_dir)
    assert cites(mem, cited) == [{"ref": old, "status": "moved", "moved_to": handle(mem), "match": "exact"}]


# --- existing books: `kutuphane reindex-map` ---------------------------------------------------------------------

def test_reindex_map_backfills_and_is_idempotent(mem, okf_dir, monkeypatch, capsys):
    old = handle(mem)
    propose(mem, "Göç öncesi atıf", citations=[old])
    monkeypatch.setattr(profiles, "CHUNKER_VERSION", profiles.CHUNKER_VERSION + 1)
    publish(mem, okf_dir)
    mem.execute("DELETE FROM passage_map")  # a book published before migration 040 (the owner may delete)
    monkeypatch.setattr(cli.db, "connect", lambda *_a, **_k: _Same(mem))

    def run(*args):
        assert cli.main(["reindex-map", BOOK, *args]) == 0
        return json.loads(capsys.readouterr().out)
    dry = run("--dry-run")
    assert (dry["passages"], dry["added"], dry["exact"], dry["dry_run"]) == (1, 1, 1, True)
    assert mem.execute("SELECT count(*) FROM passage_map").fetchone()[0] == 0
    assert run()["added"] == 1
    again = run()
    assert (again["passages"], again["added"], again["exact"]) == (1, 0, 1)
    assert mem.execute("SELECT count(*) FROM passage_map").fetchone()[0] == 1
    assert cli.main(["reindex-map", "yok"]) == 1


class _Same:
    """db.connect for cli.main: the test's connection, left open."""
    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        return self.conn

    def __exit__(self, *exc):
        return False


# --- the curator queue and the decision export ------------------------------------------------------------------

def test_curator_queue_and_decision_export_show_the_state(mem, okf_dir, monkeypatch):
    old = handle(mem)
    decided = notes.propose(mem, mcp(), {"book": J, "kind": "decision_proposal", "text": "Bakım kipini kullan",
                                         "citations": [old], "links": [{"type": "about", "ref": old}],
                                         "decision": {"options": ["evet", "hayır"], "choice": "evet"}})[0]["ref"]
    monkeypatch.setattr(profiles, "CHUNKER_VERSION", profiles.CHUNKER_VERSION + 1)
    publish(mem, okf_dir)
    new = handle(mem)
    moved = {"status": "moved", "moved_to": new, "match": "exact"}
    readable = {BOOK, J}
    seq = mem.execute("SELECT seq FROM note WHERE id = %s", (decided.split("@")[1],)).fetchone()[0]
    [cited] = curatorqueue._citations(mem, [seq], readable)[seq]
    assert {k: cited[k] for k in ("ref", "status", "moved_to", "match")} == {"ref": old, **moved}
    [linked] = curatorqueue._links(mem, [seq], readable, notesquery.watermark(mem))[seq]
    assert {k: linked[k] for k in ("ref", "status", "moved_to", "match")} == {"ref": old, **moved}
    [record], _ = decisions.export(mem, PERSON, [J])
    assert record["context"]["citations"] == [old] and record["context"]["passages"] == {old: moved}


# --- the gates apply to the new passage --------------------------------------------------------------------------

def test_a_skill_blocked_in_the_new_version_withholds_a_note_on_the_old_passage(conn, folder, fake):  # noqa: F811
    """D71: a note cites a skill passage while the skill is allowed; the next version blocks the skill. The note's
    citation follows to the new passage, so a model reader gets the text withheld."""
    publish(conn, folder("Özetle ve kaydet.\n", "Kaynak listesi: üç belge.\n"))
    agent_with(conn, "read", "activate")
    journal(conn)
    allow(conn, J, "read", "propose")
    cited = propose(conn, "Kaynak listesi: üç belge.", citations=[handle(conn, REF, 0)])
    reader = Actor("agent:kobra-7", "user:ayse", channel="mcp")
    assert notesquery.open_note(conn, reader, for_model=True, ref=cited)["note"]["text"] is not None
    fake.verdict("DO_NOT_INSTALL")
    result = publish(conn, folder("Özetle ve kaydet.\n", "Kaynak listesi: üç belge ve bir ek.\n"))
    assert any(s["blocking"] for s in result.skill_scans) and result.passage_map["overlap"] == 1
    item = notesquery.open_note(conn, reader, for_model=True, ref=cited)["note"]
    assert (item["text"], item["withheld"]) == (None, gate.SKILL_WITHHELD)
    assert item["citations"][0]["status"] == "moved"
