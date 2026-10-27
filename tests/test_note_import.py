"""#75 (docs/24 §23): the bulk import of an orchestrator's local memory, and private, local-only journals."""
import json
import os
from datetime import datetime, timezone

import psycopg
import pytest
from cryptography.hazmat.primitives.asymmetric import ed25519

from kutuphane import authz, catalog, cli, db, decisions, gate, noteimport, notes, packages, profiles
from kutuphane.gate import Actor
from kutuphane.policy import make_policy
from kutuphane.source import read_source
from test_notes import (CITE, J, U, allow, code, env, fake, handle, http, journal, mcp, propose,  # noqa: F401
                        row)

NB = "agent:nobetci"
STRANGER = "user:yabanci"
PRIVATE = make_policy(sensitivity="restricted", egress="local_only", protection="standard")
TABLES = ("note", "write_record", "note_link", "note_citation", "note_import", "standing_event")


def rec(rid: str, text: str | None = None, kind: str = "finding", **fields) -> dict:
    return {"id": rid, "kind": kind, "text": text or f"record {rid}", **fields}


def run(conn, *records, by=U, book=J, embedder=None) -> dict:
    lines = [r if isinstance(r, str) else json.dumps(r, ensure_ascii=False) for r in records]
    return noteimport.run(conn, Actor(by), book, lines, embedder)


def counts(conn) -> tuple:
    return tuple(row(conn, f"SELECT count(*) FROM {t}")[0] for t in TABLES)


def links(conn) -> set:
    return {(src, type_, dst, creation) for src, type_, dst, creation in conn.execute(
        "SELECT s.book || '@' || s.id, l.type, coalesce(d.book || '@' || d.id, l.dst_book || '@' || l.dst_content_id "
        "|| '/' || l.dst_profile_id || '/' || l.dst_path || '#' || l.dst_ordinal), l.creation "
        "FROM note_link l JOIN note s ON s.seq = l.src LEFT JOIN note d ON d.seq = l.dst_note")}


# --- the record format, Standing and origin ----------------------------------------------------------------------

def test_records_import_as_pending_notes_with_their_provenance(env):
    r = run(env, rec("nb-1", "Retry loop hides timeouts", standing="approved", role="evidence", window="durable",
                     origin="human", created_at="2026-10-20T09:15:00Z", updated_at="2026-10-21T10:00:00+03:00",
                     class_key="retry/timeout"))
    [item] = r["items"]
    assert (r["created"], r["existing"], r["unchanged"]) == (1, 0, 0)
    assert item["record"] == "nb-1" and item["status"] == "created"
    assert item["standing"] == "pending" and item["standing_claimed"] == "approved"
    assert (item["origin"], item["origin_notice"]) == ("unknown", "origin-claim-refused")
    assert row(env, "SELECT count(*) FROM standing_event")[0] == 0  # an imported `approved` is never trusted
    assert row(env, "SELECT principal, on_behalf_of, channel, origin_requested, origin, notice, creates "
                    "FROM write_record") == (U, None, "cli", "human", "unknown", "origin-claim-refused", True)
    assert row(env, "SELECT record, standing_claimed, created_at, updated_at FROM note_import") == (
        "nb-1", "approved", datetime(2026, 10, 20, 9, 15, tzinfo=timezone.utc),
        datetime(2026, 10, 21, 7, 0, tzinfo=timezone.utc))
    assert row(env, "SELECT kind, body, class_key FROM note") == ("finding", "Retry loop hides timeouts",
                                                                  "retry/timeout")
    same_bytes = notes.Draft({"book": J, "kind": "finding", "text": "Retry loop hides timeouts",
                              "class_key": "retry/timeout"})
    assert item["ref"] == same_bytes.ref  # the note id of the same bytes proposed over MCP


def test_an_agent_importer_stores_model_and_the_database_keeps_d70(env):
    authz.grant(env, f"book:{J}", "propose", NB)
    [item] = run(env, rec("nb-1", origin="unknown"), by=NB)["items"]
    assert (item["origin"], item["origin_notice"]) == ("model", None)
    assert row(env, "SELECT principal, channel, origin FROM write_record") == (NB, "cli", "model")
    seq = row(env, "SELECT seq FROM note")[0]
    insert = ("INSERT INTO write_record (correlation_id, action, note_seq, creates, principal, on_behalf_of, channel, "
              "origin) VALUES ('c', 'propose', %s, false, %s, %s, 'cli', 'unknown')")
    for principal, behalf in [(NB, None), (NB, U), (U, NB)]:
        with pytest.raises(psycopg.errors.CheckViolation):
            env.execute(insert, (seq, principal, behalf))


def test_only_the_cli_imports(env):
    with pytest.raises(ValueError, match="CLI"):
        noteimport.run(env, mcp(), J, [json.dumps(rec("nb-1"))])
    assert counts(env) == (0,) * len(TABLES)


# --- links, idempotency ------------------------------------------------------------------------------------------

def test_links_between_records_resolve_by_record_id(env):
    passage = handle(env, "kitap")
    r = run(env,
            rec("nb-2", "Use a deadline per call", kind="lesson",
                links=[{"type": "derived_from", "record": "nb-1"}, {"type": "same_as", "record": "nb-3"}]),
            rec("nb-1", "Retry loop hides timeouts", links=[{"type": "about", "ref": passage}]),
            rec("nb-3", "Set a deadline on every call", kind="lesson", links=[{"type": "same_as", "record": "nb-2"}]))
    assert [i["record"] for i in r["items"]] == ["nb-2", "nb-1", "nb-3"]  # the order of the file
    ref = {i["record"]: i["ref"] for i in r["items"]}
    assert ref["nb-2"] == notes.Draft({"book": J, "kind": "lesson", "text": "Use a deadline per call",
                                       "links": [{"type": "derived_from", "ref": ref["nb-1"]}]}).ref
    assert links(env) == {(ref["nb-2"], "derived_from", ref["nb-1"], True),  # a creation link: the note identity
                          (ref["nb-1"], "about", passage, False),            # every other type: a later link
                          (ref["nb-2"], "same_as", ref["nb-3"], False),
                          (ref["nb-3"], "same_as", ref["nb-2"], False)}
    assert r["links"] == {"created": 3, "existing": 0}
    assert row(env, "SELECT source_books FROM note WHERE body = 'Use a deadline per call'") == ([J],)
    assert row(env, "SELECT count(*) FROM write_record WHERE action = 'link' AND channel = 'cli'")[0] == 3


def test_a_reimport_of_the_same_record_ids_is_a_no_op(env):
    batch = [rec("nb-1"), rec("nb-2", links=[{"type": "derived_from", "record": "nb-1"},
                                             {"type": "contradicts", "record": "nb-1"}])]
    first = run(env, *batch)
    before = counts(env)
    again = run(env, *batch)
    assert [i["status"] for i in again["items"]] == ["unchanged", "unchanged"]
    assert [i["ref"] for i in again["items"]] == [i["ref"] for i in first["items"]]
    assert counts(env) == before and again["links"] == {"created": 0, "existing": 1}
    later = run(env, rec("nb-3", links=[{"type": "derived_from", "record": "nb-2"}]))  # an earlier batch's record
    assert later["items"][0]["status"] == "created"
    before = counts(env)
    with pytest.raises(ValueError, match="nb-1.*another note"):
        run(env, rec("nb-4"), rec("nb-1", "the text changed in the source"))
    assert counts(env) == before  # nothing of the refused file


def test_a_record_with_the_bytes_of_an_existing_note_is_one_more_write(env):
    proposed = propose(env, mcp(), text="Retry loop hides timeouts")
    [item] = run(env, rec("nb-1", "Retry loop hides timeouts"))["items"]
    assert (item["ref"], item["status"]) == (proposed["ref"], "existing")
    assert row(env, "SELECT count(*) FROM write_record WHERE note_seq IS NOT NULL")[0] == 2  # recurrence 2


@pytest.mark.parametrize("records,needle", [
    ([rec("a", role="rule")], "line 1: role"),
    ([rec("a", kind="test_result", window="durable")], "line 1: window"),
    ([rec("a", window={"from": "2026-10-01T00:00:00Z", "to": "2026-10-02T00:00:00Z"})], "line 1: window"),
    ([{**rec("a"), "project": "x"}], "line 1: unknown field"),
    ([rec("a"), rec("a")], "line 2: duplicate record id"),
    ([rec("bad id!")], "line 1: id"),
    ([rec("a", standing="accepted")], "line 1: standing"),
    ([rec("a", created_at="yesterday")], "line 1: created_at"),
    ([rec("a", created_at="2026-10-20T09:15:00")], "line 1: created_at"),
    (["not json"], "line 1: not a JSON object"),
    ([rec("a", links=[{"type": "about", "record": "zz"}])], "line 1: no record zz"),
    ([rec("a", links=[{"type": "derived_from", "record": "a"}])], "line 1: .*itself"),
    ([rec("a", links=[{"type": "derived_from", "record": "b"}]),
      rec("b", links=[{"type": "supersedes", "record": "a"}])], "cycle"),
    ([rec("a", links=[{"type": "about", "record": "b", "ref": "x"}])], "line 1: a link"),
    ([rec("a", decision={"options": ["x", "y"], "choice": "x"})], "line 1: decision"),
    ([rec("a", "the deploy token is ghp_" + "a1B2c3D4e5F6g7H8i9J0k1L2")], "line 1: .*access-token"),
])
def test_an_invalid_file_is_refused_before_anything_is_written(env, records, needle):
    with pytest.raises(ValueError, match=needle) as exc:
        run(env, rec("ok"), *records) if needle == "cycle" else run(env, *records)
    assert "a1B2c3D4" not in str(exc.value)
    assert counts(env) == (0,) * len(TABLES)


def test_the_importer_needs_propose_and_read_now(env):
    with pytest.raises(gate.Denied):
        run(env, rec("a"), by=STRANGER)
    authz.grant(env, f"book:{J}", "propose", STRANGER)
    with pytest.raises(gate.Denied):  # no read on the cited book
        run(env, rec("a", citations=[handle(env, "kitap")]), by=STRANGER)
    assert counts(env) == (0,) * len(TABLES)
    refused = env.execute("SELECT principal, object, mode FROM access_event WHERE NOT allowed ORDER BY id").fetchall()
    assert refused == [(STRANGER, f"book:{J}", "propose"), (STRANGER, "book:kitap", "read")]


def test_an_import_neither_hits_nor_uses_the_daily_write_limit(env, monkeypatch):
    monkeypatch.setenv(notes.WRITES_ENV, "2")
    assert run(env, rec("a"), rec("b"), rec("c"))["created"] == 3
    assert propose(env, http(), text="after the import")["status"] == "created"  # the importer's own limit is free


def test_code_citations_and_scope_are_imported(env, code):
    run(env, rec("a", citations=[CITE], scope={"repo": "adc", "branch": "main", "paths": ["src/**"]},
                 commit="3f" * 20))
    assert code.excerpts == [(J, CITE)]
    assert row(env, "SELECT kind, repo, commit, line_start, line_end FROM note_citation") == (
        "code", "adc", "3f" * 20, 40, 52)
    assert row(env, "SELECT scope_repo, scope_branch, scope_paths FROM note") == ("adc", "main", ["src/**"])


def test_an_import_embeds_after_the_commit(env, fake):
    [item] = run(env, rec("a"), embedder=fake.embedder())["items"]
    assert item["vector"] == "stored" and row(env, "SELECT count(*) FROM note_vector")[0] == 1
    [again] = run(env, rec("a"), embedder=fake.embedder())["items"]
    assert again["status"] == "unchanged" and again["vector"] is None and len(fake.requests) == 1


def test_the_cli_imports_a_jsonl_file(env, tmp_path, monkeypatch, capsys):
    monkeypatch.setenv(db.DSN_ENV, os.environ["KUTUPHANE_TEST_DSN"])
    path = tmp_path / "nobetci.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in [rec("a"), rec("b")]), encoding="utf-8")
    assert cli.main(["note", "import", J, str(path), "--by", U]) == 0
    out = json.loads(capsys.readouterr().out)
    assert (out["book"], out["records"], out["created"]) == (J, 2, 2)
    assert cli.main(["note", "import", J, str(path), "--by", STRANGER]) == 3
    assert "denied" in capsys.readouterr().err


# --- private, local-only journals ------------------------------------------------------------------------------

@pytest.fixture
def private(env):
    notes.create_journal(env, book="musteri", title="musteri", search=True, ai_input=True, policy=PRIVATE,
                         by="user:admin")
    allow(env, "musteri", "read", "propose")
    return "musteri"


def test_a_private_journal_never_goes_to_a_cloud_route(env, private, fake):
    [item] = run(env, rec("a", "Customer X runs a custom VPN"), book=private,
                 embedder=fake.embedder(route_class="cloud"))["items"]
    assert item["vector"] == "skipped:egress" and fake.requests == []
    proposed = notes.propose(env, mcp(), {"book": private, "kind": "finding", "text": "Customer X uses SSO"},
                             fake.embedder(route_class="cloud"))[0]
    assert proposed["vector"] == "skipped:egress" and fake.requests == []
    assert {e for (e,) in env.execute("SELECT error FROM model_call")} == {"not_sent:egress_policy"}
    assert run(env, rec("b"), book=private, embedder=fake.embedder())["items"][0]["vector"] == "stored"


def test_a_private_journal_is_never_exported_published_or_used_for_training(env, private, okf_dir):
    with pytest.raises(ValueError, match="train"):
        notes.create_journal(env, book="musteri-2", title="m", search=True, ai_input=True, train=True,
                             policy=PRIVATE, by="user:admin")
    with pytest.raises(packages.PackageError):
        packages.export(env, private, ed25519.Ed25519PrivateKey.generate())
    with pytest.raises(ValueError, match="journal"):  # also the path of approve-import
        catalog.publish(env, book=private, title=private, files=read_source(okf_dir), policy=PRIVATE,
                        profile=profiles.spec("chunked"))
    state = catalog.book_state(env, private)
    assert state["content_id"] is None and state["policy"]["sensitivity"] == "restricted"
    choice = {"options": ["now", "later"], "choice": "now"}
    secret = notes.propose(env, mcp(), {"book": private, "kind": "decision_proposal", "text": "Ship the fix for X",
                                        "decision": choice})[0]
    notes.create_journal(env, book="kararlar", title="kararlar", search=True, ai_input=True, train=True,
                         policy=make_policy(sensitivity="normal", egress="local_only", protection="standard"),
                         by="user:admin")
    allow(env, "kararlar", "read", "propose")
    derived = notes.propose(env, mcp(), {"book": "kararlar", "kind": "decision_proposal", "text": "Same for Y",
                                         "decision": choice, "links": [{"type": "derived_from",
                                                                        "ref": secret["ref"]}]})[0]
    plain = notes.propose(env, mcp(), {"book": "kararlar", "kind": "decision_proposal", "text": "Unrelated",
                                       "decision": choice})[0]
    records, summary = decisions.export(env, mcp(), [private, "kararlar"])
    assert [r["ref"] for r in records] == [plain["ref"]] and summary["restricted"] == 2
    assert derived["ref"] not in json.dumps(records)


def test_a_restricted_book_is_never_in_a_package(env, okf_dir):
    catalog.publish(env, book="gizli", title="gizli", files=read_source(okf_dir), policy=PRIVATE,
                    profile=profiles.spec("chunked"))
    with pytest.raises(packages.PackageError, match="restricted"):
        packages.export(env, "gizli", ed25519.Ed25519PrivateKey.generate())


def test_027_applies_to_a_database_with_notes(conn):
    conn.execute("DELETE FROM schema_migration WHERE name = '027_note_import.sql'")
    conn.execute("DROP TABLE note_import")
    conn.execute("ALTER TABLE write_record DROP CONSTRAINT write_record_origin_path_check")
    conn.execute("ALTER TABLE write_record ADD CONSTRAINT write_record_check2 CHECK (origin = 'model' OR "
                 "(principal LIKE 'user:%' AND on_behalf_of IS NULL AND channel = 'http'))")
    conn.execute("ALTER TABLE write_record DROP CONSTRAINT write_record_channel_check")
    conn.execute("ALTER TABLE write_record ADD CONSTRAINT write_record_channel_check "
                 "CHECK (channel IN ('mcp', 'http'))")
    journal(conn)
    allow(conn, J, "read", "propose")
    propose(conn, mcp())
    assert db.migrate(conn) == ["027_note_import.sql"]
    assert run(conn, rec("a"))["created"] == 1
