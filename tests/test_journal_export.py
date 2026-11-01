"""R3 (2026-11-01): `kutuphane journal export` writes a journal as JSONL in the `note import` record shape, plus the
Standing history, the writers and the outcomes; `note import` reads it back as `pending` notes."""
import json
import os

import pytest

from kutuphane import authz, catalog, cli, db, gate, journalexport, noteimport, notes, profiles
from kutuphane.gate import Actor
from kutuphane.source import read_source
from test_note_import import PRIVATE
from test_notes import A, LOCAL, U, allow, env, handle, mcp  # noqa: F401
from test_outcomes import record
from test_unknown_licence import PATH, UNKNOWN_POLICY_FILE, passage, publish

M = "bellek"  # a journal that allows ai_input and train
CURATOR = "user:ayse"


def make(conn, book=M, *, train=True, ai_input=True, policy=LOCAL):
    notes.create_journal(conn, book=book, title=book, search=True, ai_input=ai_input, train=train, policy=policy,
                         by="user:admin")


def fresh(conn, okf_dir) -> None:
    """A fresh installation: the same book `kitap`, a fresh journal M that allows everything, the importer U."""
    conn.execute("DROP SCHEMA public CASCADE")
    conn.execute("CREATE SCHEMA public")
    db.migrate(conn)
    catalog.publish(conn, book="kitap", title="kitap", files=read_source(okf_dir), policy=LOCAL,
                    profile=profiles.spec("chunked"))
    make(conn)
    allow(conn, M, "read", "propose", agent=None)  # read: the later links name notes of the journal
    allow(conn, "kitap", "read", agent=None)


def note(conn, text, kind="finding", book=M, **args) -> str:
    return notes.propose(conn, mcp(), {"book": book, "kind": kind, "text": text, **args})[0]["ref"]


def nid(ref: str) -> str:
    return ref.partition("@")[2]


def note_links(conn) -> set:
    return {(s, t, d, c) for s, t, d, c in conn.execute(
        "SELECT s.id, l.type, d.book || '@' || d.id, l.creation FROM note_link l JOIN note s ON s.seq = l.src "
        "JOIN note d ON d.seq = l.dst_note")}


def export_cli(monkeypatch, capsys, tmp_path, book=M, by=U) -> tuple[int, dict | str, list[dict]]:
    monkeypatch.setenv(db.DSN_ENV, os.environ["KUTUPHANE_TEST_DSN"])
    out = tmp_path / f"{book}.jsonl"
    code = cli.main(["journal", "export", book, "--out", str(out), "--by", by])
    captured = capsys.readouterr()
    if code:
        return code, captured.err, []
    assert oct(out.stat().st_mode & 0o777) == "0o600"
    return code, json.loads(captured.out), [json.loads(line) for line in out.read_text().splitlines()]


@pytest.fixture
def memory(env):
    make(env)
    allow(env, M, "read", "propose")
    authz.grant(env, f"book:{M}", "curate", CURATOR)
    a = note(env, "Retry loop hides timeouts", class_key="retry/timeout", applies_to={"platform": ["linux"]})
    b = note(env, "Fail fast after a 4xx", kind="lesson", links=[{"type": "derived_from", "ref": a}])
    old = note(env, "Retry three times", kind="convention")
    new = note(env, "Retry once", kind="convention", links=[{"type": "supersedes", "ref": old}])
    pick = note(env, "Retry or fail fast", kind="decision_proposal",
                decision={"options": ["retry", "fail fast"], "choice": "fail fast"})
    notes.link(env, mcp(), a, "same_as", b)
    notes.link(env, mcp(), b, "same_as", a)
    notes.link(env, mcp(), pick, "about", handle(env, "kitap"))
    notes.set_standing(env, a, "approved", curator=CURATOR, reason="checked in run 41")
    notes.set_standing(env, a, "retired", curator=CURATOR, reason="fixed upstream")
    record(env, mcp(), a, task_ref="adc:run/41")
    return {"a": a, "b": b, "old": old, "new": new, "pick": pick}


def test_the_export_writes_the_import_shape_with_history_writers_and_outcomes(env, memory, monkeypatch, capsys,
                                                                             tmp_path):
    code, summary, records = export_cli(monkeypatch, capsys, tmp_path)
    assert code == 0 and summary["records"] == 5 and summary["withheld"] == 0
    by_id = {r["id"]: r for r in records}
    assert list(by_id) == [nid(memory[k]) for k in ("a", "b", "old", "new", "pick")]  # creation links point back
    a, b = by_id[nid(memory["a"])], by_id[nid(memory["b"])]
    assert set(a) <= set(noteimport.FIELDS)
    assert (a["kind"], a["text"], a["role"], a["window"], a["class_key"]) == (
        "finding", "Retry loop hides timeouts", "evidence", "durable", "retry/timeout")
    assert a["applies_to"] == {"platform": ["linux"]} and a["standing"] == "retired" and a["origin"] == "model"
    assert [(e["value"], e["set_by"], e["reason"]) for e in a["standing_history"]] == [
        ("approved", CURATOR, "checked in run 41"), ("retired", CURATOR, "fixed upstream")]
    assert [(w["principal"], w["on_behalf_of"], w["channel"], w["origin"]) for w in a["writers"]] == [
        (A, U, "mcp", "model")]
    assert [(o["task_ref"], o["result"], o["principal"]) for o in a["outcomes"]] == [("adc:run/41", "passed", A)]
    assert a["links"] == [{"type": "same_as", "record": nid(memory["b"])}]
    assert b["links"] == [{"type": "derived_from", "record": nid(memory["a"])},
                          {"type": "same_as", "record": nid(memory["a"])}]
    pick = by_id[nid(memory["pick"])]
    assert pick["decision"] == {"options": ["retry", "fail fast"], "choice": "fail fast"}
    assert pick["links"] == [{"type": "about", "ref": handle(env, "kitap")}]
    assert a["ai_use"] == {"search": "y", "ai_input": "y", "train": "y"} and a["withheld"] is None
    [(items,)] = env.execute(
        "SELECT items FROM access_event WHERE action = 'export_journal' AND object = %s AND allowed", (f"book:{M}",))
    assert [i["ref"] for i in items] == [memory[k] for k in ("a", "b", "old", "new", "pick")]


def test_round_trip_into_a_fresh_installation_keeps_the_note_ids_and_links(env, memory, okf_dir):
    lines = [json.dumps(r) for r in journalexport.export(env, Actor(U), M)[0]]
    ids, links = {i for (i,) in env.execute("SELECT id FROM note WHERE book = %s", (M,))}, note_links(env)
    passage_links = env.execute("SELECT type, dst_book, dst_content_id, dst_path FROM note_link "
                                "WHERE dst_book IS NOT NULL").fetchall()
    fresh(env, okf_dir)
    report = noteimport.run(env, Actor(U), M, lines)
    assert report["created"] == 5 and {i["standing"] for i in report["items"]} == {"pending"}
    assert {i["record"]: i["standing_claimed"] for i in report["items"]}[nid(memory["a"])] == "retired"
    assert env.execute("SELECT count(*) FROM standing_event").fetchone()[0] == 0  # never trusted
    assert {i for (i,) in env.execute("SELECT id FROM note")} == ids
    assert note_links(env) == links
    assert env.execute("SELECT type, dst_book, dst_content_id, dst_path FROM note_link "
                       "WHERE dst_book IS NOT NULL").fetchall() == passage_links


def test_the_import_validates_the_export_fields_and_refuses_withheld_text(env):
    make(env)
    allow(env, M, "read", "propose")
    good = {"id": "r1", "kind": "finding", "text": "x", "standing_history": [
        {"value": "approved", "set_by": CURATOR, "reason": "ok", "at": "2026-11-01T10:00:00Z"}],
        "writers": [], "outcomes": [], "ai_use": {"search": "y", "ai_input": "y", "train": "y"}, "withheld": None}
    assert noteimport.run(env, Actor(U), M, [json.dumps(good)])["created"] == 1
    for bad, needle in [({"standing_history": [{"value": "maybe"}]}, "standing_history"),
                        ({"writers": "agent:x"}, "writers"),
                        ({"outcomes": [{"task_ref": "t", "result": "passed", "at": "now", "principal": U,
                                        "on_behalf_of": None, "origin": "model"}]}, "at"),
                        ({"ai_use": {"search": "y"}}, "ai_use"),
                        ({"text": None, "withheld": gate.SKILL_WITHHELD}, "withheld")]:
        with pytest.raises(ValueError, match=needle):
            noteimport.run(env, Actor(U), M, [json.dumps({**good, "id": "r2", **bad})])


def test_a_train_n_journal_round_trips_with_its_text_and_its_rights(env, okf_dir, monkeypatch, capsys, tmp_path):
    make(env, ai_input=False, train=False)
    allow(env, M, "read", "propose")
    ref = note(env, "Secret plan", kind="decision_proposal", decision={"options": ["a", "b"], "choice": "b"})
    code, summary, [r] = export_cli(monkeypatch, capsys, tmp_path)
    assert code == 0 and summary["withheld"] == 0 and r["id"] == nid(ref)
    assert (r["text"], r["decision"], r["withheld"]) == ("Secret plan", {"options": ["a", "b"], "choice": "b"}, None)
    assert r["ai_use"] == {"search": "y", "ai_input": "n", "train": "n"}
    fresh(env, okf_dir)  # M allows ai_input and train here: the import must not widen the note's rights
    [item] = noteimport.run(env, Actor(U), M, [json.dumps(r)])["items"]
    assert item["ref"] == ref and item["status"] == "created"
    assert env.execute("SELECT search, ai_input, train FROM note").fetchone() == (True, False, False)


def test_a_note_with_a_blocked_skill_is_exported_without_its_text(env, monkeypatch, capsys, tmp_path):
    make(env)
    allow(env, M, "read", "propose")
    ref = note(env, "Cites a skill", citations=[handle(env, "kitap")])
    content = env.execute("SELECT current_content FROM book WHERE slug = 'kitap'").fetchone()[0]
    env.execute("INSERT INTO skill_scan (book, content_id, skill_path, status, input_digest, tool_version, mode, "
                "reason) VALUES ('kitap', %s, '.', 'failed', %s, '2.13.1', 'no-llm', 'test')", (content, "0" * 64))
    code, summary, [r] = export_cli(monkeypatch, capsys, tmp_path)
    assert summary["withheld"] == 1 and r["id"] == nid(ref)
    assert (r["text"], r["withheld"]) == (None, gate.SKILL_WITHHELD)
    assert "Cites a skill" not in (tmp_path / f"{M}.jsonl").read_text()
    with pytest.raises(ValueError, match="withheld"):
        noteimport.run(env, Actor(U), M, [json.dumps(r)])


def test_a_restricted_journal_is_refused(env):
    make(env, "musteri", train=False, policy=PRIVATE)
    allow(env, "musteri", "read", "propose")
    note(env, "Customer X runs a VPN", book="musteri")
    with pytest.raises(ValueError, match="restricted"):
        journalexport.export(env, Actor(U), "musteri")
    make(env)  # a note derived from the private journal is left out, as in the decision export
    allow(env, M, "read", "propose")
    derived = note(env, "Same for Y", links=[{"type": "derived_from", "ref": note(env, "VPN", book="musteri")}])
    plain = note(env, "Unrelated")
    records, summary = journalexport.export(env, Actor(U), M)
    assert [r["id"] for r in records] == [nid(plain)] and summary["restricted"] == 1
    assert nid(derived) not in json.dumps(records)


def test_notes_derived_from_license_unknown_are_left_out(conn, okf_dir):
    publish(conn, okf_dir, policy_item=UNKNOWN_POLICY_FILE)
    make(conn)
    allow(conn, M, "read", "propose")
    cited = note(conn, "Retention is in the policy", citations=[passage(conn, PATH)])
    derived = note(conn, "Derived from it", links=[{"type": "derived_from", "ref": cited}])
    later = note(conn, "Same topic")
    notes.link(conn, mcp(), later, "about", cited)
    records, summary = journalexport.export(conn, Actor(U), M)
    assert [r["id"] for r in records] == [nid(later)] and summary["licence_unknown"] == 2
    assert records[0]["links"] == [{"type": "about", "ref": cited}]  # not in the file: a ref, never a record
    assert nid(derived) not in json.dumps(records)


def test_the_export_needs_read_on_the_journal_and_every_named_book(env, monkeypatch, capsys, tmp_path):
    make(env)
    allow(env, M, "read", "propose")
    note(env, "Cites kitap", citations=[handle(env, "kitap")])
    code, err, _ = export_cli(monkeypatch, capsys, tmp_path, by="user:yabanci")
    assert code == 3 and "denied" in err and not (tmp_path / f"{M}.jsonl").exists()
    authz.grant(env, f"book:{M}", "read", "user:okur")
    code, err, _ = export_cli(monkeypatch, capsys, tmp_path, by="user:okur")
    assert code == 3 and "book:kitap" in err
    with pytest.raises(gate.NotFound):
        journalexport.export(env, Actor(U), "kitap")  # a content book is not a journal
