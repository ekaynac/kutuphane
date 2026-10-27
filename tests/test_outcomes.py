"""R2 #74 (docs/24 §21): outcome feedback on an exact item version, decision fields, the `train` right and the
decision export. O1–O9."""
import asyncio
import hashlib
import json
import os
from importlib.resources import files

import psycopg
import pytest
from starlette.testclient import TestClient

from kutuphane import authz, catalog, cli, db, gate, ids, kstd, notes, notesquery, outcomes, profiles, server
from kutuphane.source import read_source
from test_identity import token
from test_notes import (A, B, CLOUD, J, PUBLIC, U, allow, env, handle, http, journal, keys, mcp,  # noqa: F401
                        propose, row, verifier)

DSN_ENV = "KUTUPHANE_TEST_DSN"


def record(conn, actor, ref, result="passed", task_ref="adc:run/41", key="key-00000001"):
    return outcomes.record(conn, actor, {"ref": ref, "task_ref": task_ref, "result": result,
                                         "idempotency_key": key})


def q(conn, actor, **kw):
    return notesquery.query_notes(conn, actor, for_model=actor.channel == "mcp", **kw)


def item(result, ref):
    return next(i for i in result["items"] if i["ref"] == ref)


def outcome_rows(conn) -> int:
    return row(conn, "SELECT count(*) FROM outcome")[0]


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# --- O1: record, counts in reads, Standing unchanged ----------------------------------------------------------

def test_an_agent_records_outcomes_that_never_change_standing(env):  # O1
    ref = propose(env, mcp())["ref"]
    receipt, retry = record(env, mcp(client_id="adc"), ref)
    assert receipt == {"ref": ref, "task_ref": "adc:run/41", "result": "passed", "origin": "model"} and not retry
    assert row(env, "SELECT principal, on_behalf_of, channel, client_id, origin, result FROM outcome") == (
        A, U, "mcp", "adc", "model", "passed")
    assert item(q(env, mcp(), sets=["open"]), ref)["outcomes"] == {"passed": 1}
    authz.grant(env, f"book:{J}", "curate", U)
    notes.set_standing(env, ref, "approved", curator=U, reason="ok")
    record(env, mcp(), ref, "failed", key="key-00000002")
    record(env, mcp(), ref, "reverted", key="key-00000003")
    record(env, mcp(), ref, "reverted", task_ref="adc:run/42", key="key-00000004")
    current = q(env, mcp())
    assert item(current, ref)["current"] is True and item(current, ref)["standing"] == "approved"
    assert item(current, ref)["outcomes"] == {"passed": 1, "failed": 1, "reverted": 2}
    assert row(env, "SELECT count(*) FROM standing_event")[0] == 1  # the curator's approval only
    assert notesquery.open_note(env, mcp(), for_model=True, ref=ref)["note"]["outcomes"] == {
        "passed": 1, "failed": 1, "reverted": 2}
    other = propose(env, mcp(), text="no outcome yet")["ref"]
    assert item(q(env, mcp(), sets=["open"]), other)["outcomes"] == {}


# --- O2: idempotency -------------------------------------------------------------------------------------------

def test_a_retry_returns_the_first_receipt_and_a_reused_key_is_refused(env):  # O2
    ref = propose(env, mcp())["ref"]
    first, _ = record(env, mcp(), ref)
    again, retry = record(env, mcp(), ref)
    assert again == first and retry and outcome_rows(env) == 1
    with pytest.raises(ids.IdempotencyConflict):
        record(env, mcp(), ref, "failed")
    record(env, http(), ref)  # another principal: the key is independent
    assert outcome_rows(env) == 2
    with pytest.raises(ValueError, match="idempotency_key"):
        outcomes.record(env, mcp(), {"ref": ref, "task_ref": "adc:run/41", "result": "passed"})
    for bad in ({"result": "worked"}, {"task_ref": "a b"}, {"task_ref": "x" * 201}, {"ref": "nope"}):
        with pytest.raises(ValueError):
            outcomes.record(env, mcp(), {"ref": ref, "task_ref": "adc:run/41", "result": "passed",
                                         "idempotency_key": "key-00000009", **bad})


# --- O3: rights --------------------------------------------------------------------------------------------------

def test_propose_and_read_on_the_book_are_needed(env):  # O3
    ref = propose(env, mcp())["ref"]
    authz.grant(env, f"book:{J}", "read", B)
    with pytest.raises(gate.Denied):
        record(env, http(B), ref)
    reader_only = row(env, "SELECT allowed, mode FROM access_event WHERE principal = %s ORDER BY id DESC LIMIT 1", B)
    assert reader_only == (False, "propose")
    writer = "user:veli"
    authz.grant(env, f"book:{J}", "propose", writer)
    with pytest.raises(gate.Denied):  # without read, found or not found would tell that the bytes exist
        record(env, http(writer), ref)
    with pytest.raises(gate.Denied):
        record(env, http(writer), f"{J}@nt_{'0' * 64}")
    assert outcome_rows(env) == 0
    with pytest.raises(gate.NotFound):
        record(env, mcp(), f"{J}@nt_{'0' * 64}")


# --- O4: passages ------------------------------------------------------------------------------------------------

def test_an_outcome_on_a_passage_version_is_shown_by_open_citation(env):  # O4
    h = handle(env, "kitap")
    with pytest.raises(gate.Denied):  # read on kitap, no propose
        record(env, http(), h)
    allow(env, "kitap", "propose")
    assert record(env, mcp(), h, "failed")[0] == {"ref": h, "task_ref": "adc:run/41", "result": "failed",
                                                  "origin": "model"}
    assert row(env, "SELECT book, note_seq IS NULL, path FROM outcome")[:2] == ("kitap", True)
    assert server.op_citation(os.environ[DSN_ENV], http(), h)["outcomes"] == {"failed": 1}
    other = h.rsplit("#", 1)[0] + "#9999"
    with pytest.raises(gate.NotFound):
        record(env, mcp(), other, key="key-00000002")


# --- O5: origin and append-only ----------------------------------------------------------------------------------

def test_origin_from_the_write_path_and_the_app_role_cannot_change_outcomes(env):  # O5
    ref = propose(env, mcp())["ref"]
    assert record(env, http(), ref)[0]["origin"] == "unknown"
    assert record(env, mcp(U, None), ref, key="key-00000002")[0]["origin"] == "model"
    seq = row(env, "SELECT seq FROM note")[0]
    with pytest.raises(psycopg.errors.CheckViolation):
        env.execute("INSERT INTO outcome (correlation_id, book, note_seq, task_ref, result, principal, channel, origin, "
                    "idempotency_key, request_sha256) VALUES ('c', %s, %s, 't', 'passed', %s, 'mcp', 'unknown', "
                    "'key-00000003', '\\x00')", (J, seq, A))
    role = "kutuphane_app_test"
    env.execute(f"DO $$ BEGIN CREATE ROLE {role} NOLOGIN; EXCEPTION WHEN duplicate_object THEN NULL; END $$")
    script = open(os.path.join(os.path.dirname(__file__), "..", "deploy", "db-roles.sql"), encoding="utf-8").read()
    env.execute(script.replace("kutuphane_app", role))
    try:
        env.execute(f"SET ROLE {role}")
        assert record(env, mcp(), ref, key="key-00000004")[0]["result"] == "passed"  # it appends
        for sql in ("UPDATE outcome SET result = 'failed'", "DELETE FROM outcome"):
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                env.execute(sql)
    finally:
        env.execute("RESET ROLE")
        env.execute(f"DROP OWNED BY {role}")


# --- O6: as_of and since -----------------------------------------------------------------------------------------

def test_counts_follow_the_watermark(env):  # O6
    ref = propose(env, mcp())["ref"]
    propose(env, mcp(), text="another note")
    record(env, mcp(), ref)
    w = q(env, mcp(), sets=["open"])["watermark"]
    record(env, mcp(), ref, "reopened", key="key-00000002")
    assert item(q(env, mcp(), sets=["open"], as_of=w), ref)["outcomes"] == {"passed": 1}
    changed = q(env, mcp(), sets=["open"], since=w)
    assert [i["ref"] for i in changed["items"]] == [ref] and changed["items"][0]["outcomes"] == {
        "passed": 1, "reopened": 1}


# --- O7: decision fields -----------------------------------------------------------------------------------------

def decide(conn, actor, text, options, choice, book=J, **args):
    return notes.propose(conn, actor, {"book": book, "kind": "decision_proposal", "text": text,
                                       "decision": {"options": options, "choice": choice}, **args})[0]


def test_decision_fields_are_validated_and_part_of_the_identity(env):  # O7
    plain = {"book": J, "kind": "decision_proposal", "text": "Use the cache"}
    body = {"v": 1, "kind": "decision_proposal", "text": "Use the cache", "class_key": None, "scope": None,
            "commit": None, "citations": [], "links": []}
    assert notes.Draft(plain).id == "nt_" + ids.sha256_hex(ids.canonical(body))  # older notes keep their id
    with_decision = notes.Draft({**plain, "decision": {"options": ["yes", "no"], "choice": "yes"}})
    other_choice = notes.Draft({**plain, "decision": {"options": ["yes", "no"], "choice": "no"}})
    assert len({notes.Draft(plain).id, with_decision.id, other_choice.id}) == 3
    for bad in ({"options": ["yes", "no"], "choice": "maybe"}, {"options": ["only"], "choice": "only"},
                {"options": ["a", "a"], "choice": "a"}, {"options": ["a", "b\n"], "choice": "a"},
                {"options": ["a", "b"]}, ["a", "b"]):
        with pytest.raises(ValueError):
            notes.Draft({**plain, "decision": bad})
    with pytest.raises(ValueError, match="decision_proposal"):
        notes.Draft({**plain, "kind": "finding", "decision": {"options": ["a", "b"], "choice": "a"}})
    secret = "AKIA" + "Z" * 16
    with pytest.raises(ValueError, match="credential"):
        decide(env, mcp(), "Which key", [secret, "none"], "none")
    r = decide(env, mcp(), "Retry or fail fast", ["retry", "fail fast"], "fail fast")
    assert r["status"] == "created"
    assert row(env, "SELECT options, choice FROM note") == (["retry", "fail fast"], "fail fast")
    with pytest.raises(psycopg.errors.CheckViolation):
        env.execute("UPDATE note SET choice = 'maybe'")


# --- O8: the decision export -------------------------------------------------------------------------------------

def export(monkeypatch, capsys, tmp_path, *args):
    monkeypatch.setenv(db.DSN_ENV, os.environ[DSN_ENV])
    out = tmp_path / "decisions.jsonl"
    assert cli.main(["decisions", "export", *args, "--out", str(out)]) == 0
    summary = json.loads(capsys.readouterr().out)
    data = out.read_bytes()
    return summary, [json.loads(line) for line in data.decode().splitlines()], data


def test_the_export_gives_text_only_with_ai_input_and_train(env, monkeypatch, capsys, tmp_path):  # O8
    notes.create_journal(env, book="kararlar", title="kararlar", search=True, ai_input=True, train=True,
                         policy=CLOUD, by="user:admin")
    allow(env, "kararlar", "read", "propose")
    open_ = decide(env, mcp(client_id="adc"), "Retry or fail fast", ["retry", "fail fast"], "fail fast",
                   book="kararlar")["ref"]
    record(env, mcp(), open_, task_ref="adc:run/7")
    closed = decide(env, mcp(), "Secret plan for the release", ["ship", "wait"], "wait")["ref"]  # J: train n
    restricted = tmp_path / "egitim"
    restricted.mkdir()
    (restricted / "not.md").write_text("# Not\n\nEğitim yok.\n", encoding="utf-8")
    manifest = kstd.init(read_source(restricted), "ACME <kb@acme.example>").replace("ai_input: n", "ai_input: y")
    (restricted / kstd.MANIFEST).write_text(manifest)
    catalog.publish(env, book="egitim", title="egitim", files=read_source(restricted), policy=CLOUD,
                    profile=profiles.spec("chunked"))
    allow(env, "egitim", "read")
    cites = decide(env, mcp(), "Cited plan without train", ["a", "b"], "b", book="kararlar",
                   citations=[handle(env, "egitim")])["ref"]
    assert row(env, "SELECT ai_input, train FROM note WHERE body = 'Cited plan without train'") == (True, False)
    propose(env, mcp(), text="not a decision")

    summary, records, data = export(monkeypatch, capsys, tmp_path, U)
    assert summary["records"] == 3 and summary["withheld"] == 2 and summary["books"] == sorted([J, "kararlar"])
    by_ref = {r["ref"]: r for r in records}
    assert [r["ref"] for r in records] == [closed, open_, cites]  # (book, seq)
    shown = by_ref[open_]
    assert shown["context"]["text"] == "Retry or fail fast" and shown["context"]["text_sha256"] == sha(
        "Retry or fail fast")
    assert (shown["options"], shown["choice"]) == (["retry", "fail fast"], "fail fast")
    assert shown["options_sha256"] == [sha("retry"), sha("fail fast")] and shown["choice_sha256"] == sha("fail fast")
    assert shown["actor"] == {"principal": A, "on_behalf_of": U, "client_id": "adc", "origin": "model"}
    assert [(o["task_ref"], o["result"], o["principal"], o["origin"]) for o in shown["outcomes"]] == [
        ("adc:run/7", "passed", A, "model")]
    assert shown["ai_use"] == {"search": "y", "ai_input": "y", "train": "y"} and shown["withheld"] is None
    assert shown["standing"] == "pending"
    for ref in (closed, cites):
        hidden = by_ref[ref]
        assert hidden["context"]["text"] is None and hidden["options"] is None and hidden["choice"] is None
        assert hidden["withheld"] and hidden["ai_use"]["train"] == "n"
        assert len(hidden["options_sha256"]) == 2 and hidden["choice_sha256"]
    assert by_ref[closed]["context"]["text_sha256"] == sha("Secret plan for the release")
    assert by_ref[cites]["context"]["citations"] == [handle(env, "egitim")]
    assert b"Secret plan" not in data and b"Cited plan" not in data and b'"wait"' not in data
    events = env.execute("SELECT object, items FROM access_event WHERE action = 'export_decisions' AND allowed "
                         "ORDER BY object").fetchall()
    assert events == [(f"book:{J}", [{"ref": closed, "standing_seq": None}]),
                      ("book:kararlar", [{"ref": open_, "standing_seq": None}, {"ref": cites, "standing_seq": None}])]


def test_the_export_needs_read_and_hides_unreadable_citations(env, monkeypatch, capsys, tmp_path):  # O8
    notes.create_journal(env, book="kararlar", title="kararlar", search=True, ai_input=True, train=True,
                         policy=CLOUD, by="user:admin")
    allow(env, "kararlar", "read", "propose")
    ref = decide(env, mcp(), "Cites kitap", ["a", "b"], "a", book="kararlar", citations=[handle(env, "kitap")])["ref"]
    authz.grant(env, "book:kararlar", "read", B)
    summary, records, _ = export(monkeypatch, capsys, tmp_path, B)
    assert summary["books"] == ["kararlar"] and [r["ref"] for r in records] == [ref]
    assert records[0]["context"]["citations"] == []  # B cannot read kitap
    monkeypatch.setenv(db.DSN_ENV, os.environ[DSN_ENV])
    assert cli.main(["decisions", "export", B, "--book", J, "--out", str(tmp_path / "x.jsonl")]) == 3
    assert not (tmp_path / "x.jsonl").exists()
    assert row(env, "SELECT allowed FROM access_event WHERE action = 'export_decisions' AND principal = %s "
                    "ORDER BY id DESC LIMIT 1", B) == (False,)


def test_journal_train_from_the_cli(conn, monkeypatch, capsys):
    monkeypatch.setenv(db.DSN_ENV, os.environ[DSN_ENV])
    base = ["journal", "create", "--search", "y", "--ai-input", "y", "--sensitivity", "normal", "--egress",
            "local_only", "--protection", "standard", "--by", "user:admin"]
    assert cli.main([*base[:2], "egitimli", *base[2:], "--train", "y"]) == 0
    assert json.loads(capsys.readouterr().out)["train"] is True
    assert cli.main([*base[:2], "varsayilan", *base[2:]]) == 0  # not stated: n
    assert json.loads(capsys.readouterr().out)["train"] is False
    assert cli.main(["journal", "restrict", "egitimli", "--no-train"]) == 0
    assert json.loads(capsys.readouterr().out) == {"book": "egitimli", "search": True, "ai_input": True,
                                                   "train": False}


# --- §21.1 over HTTP and MCP -------------------------------------------------------------------------------------

def test_record_outcome_over_http_and_mcp(env, keys, verifier, monkeypatch):  # §21.1, §13
    from test_server import call_tool
    ref = propose(env, mcp())["ref"]
    dsn = os.environ[DSN_ENV]
    h = {"Authorization": f"Bearer {token(keys)}"}
    body = {"ref": ref, "task_ref": "adc:run/1", "result": "passed", "idempotency_key": "http-0001"}
    mcp_server = server.build_mcp(dsn=dsn, verifier=verifier, bridge=None, model=None, public_url=PUBLIC)
    claims = asyncio.run(server._Verifier(verifier).verify_token(token(keys, act={"sub": "kobra-7"}))).claims
    content, _ = call_tool(mcp_server, claims, "record_outcome", {**body, "result": "reverted"})
    assert json.loads(content[0].text)["origin"] == "model"
    content, _ = call_tool(mcp_server, claims, "propose_note", {
        "book": J, "kind": "decision_proposal", "text": "via mcp",
        "decision": {"options": ["a", "b"], "choice": "b"}})
    assert json.loads(content[0].text)["status"] == "created"
    assert row(env, "SELECT options, choice FROM note WHERE body = 'via mcp'") == (["a", "b"], "b")
    app = server.create_app(dsn=dsn, verifier=verifier, bridge=None, model=None, public_url=PUBLIC)
    with TestClient(app) as client:
        created = client.post("/v1/outcomes", json=body, headers=h)
        assert created.status_code == 201 and created.json() == {"ref": ref, "task_ref": "adc:run/1",
                                                                  "result": "passed", "origin": "unknown"}
        retried = client.post("/v1/outcomes", json=body, headers=h)
        assert retried.status_code == 200 and retried.json() == created.json()
        assert client.post("/v1/outcomes", json={**body, "result": "failed"}, headers=h).status_code == 409
        assert client.post("/v1/outcomes", json={k: v for k, v in body.items() if k != "idempotency_key"},
                           headers=h).status_code == 400
        assert client.post("/v1/outcomes", json=body).status_code == 401
        stranger = {"Authorization": f"Bearer {token(keys, sub='mehmet')}"}
        assert client.post("/v1/outcomes", json=body, headers=stranger).status_code == 403
        monkeypatch.setenv(notes.WRITES_ENV, "1")  # one daily budget for every memory write
        assert client.post("/v1/outcomes", json={**body, "idempotency_key": "http-0002"},
                           headers=h).status_code == 429
    assert env.execute("SELECT principal, channel, result FROM outcome ORDER BY seq").fetchall() == [
        (A, "mcp", "reverted"), (U, "http", "passed")]


# --- O9: migration -----------------------------------------------------------------------------------------------

def test_020_applies_to_a_database_with_notes(conn):  # O9
    conn.execute("DROP SCHEMA public CASCADE")
    conn.execute("CREATE SCHEMA public")
    conn.execute("CREATE TABLE schema_migration (name text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())")
    for script in sorted((f for f in files("kutuphane.migrations").iterdir() if f.name.endswith(".sql")),
                         key=lambda f: f.name):
        if script.name >= "020":
            break
        conn.execute(script.read_text())
        conn.execute("INSERT INTO schema_migration (name) VALUES (%s)", (script.name,))
    conn.execute("INSERT INTO profile_version (id, spec) VALUES ('pf_journal', '{}')")
    conn.execute("INSERT INTO book (slug, title) VALUES ('eski', 'eski')")
    conn.execute("INSERT INTO journal (book, search, ai_input, created_by) VALUES ('eski', true, true, 'user:admin')")
    nid = "nt_" + "1" * 64
    conn.execute("INSERT INTO note (book, id, profile_id, kind, body, norm_sha256, search, ai_input, source_books, tsv) "
                 "VALUES ('eski', %s, 'pf_journal', 'decision_proposal', 'old', '\\x00', true, true, '{eski}', "
                 "''::tsvector)", (nid,))
    assert "020_outcome.sql" in db.migrate(conn)
    assert row(conn, "SELECT train FROM journal") == (False,)
    assert row(conn, "SELECT id, train, options, choice FROM note") == (nid, False, None, None)


# --- Astra review #14: the final decision of the export -------------------------------------------------------------

def _after_records(monkeypatch, change):
    """Run `change` (on another, committed session) right after the export built its records, before delivery."""
    from kutuphane import decisions
    built = decisions._records

    def records_then_change(conn, actor, books):
        out = built(conn, actor, books)
        change()
        return out
    monkeypatch.setattr(decisions, "_records", records_then_change)


def test_the_export_drops_references_whose_read_was_revoked_before_delivery(env, conn2, monkeypatch):  # Astra #14 P1
    from kutuphane import decisions
    notes.create_journal(env, book="kararlar", title="kararlar", search=True, ai_input=True, train=True,
                         policy=CLOUD, by="user:admin")
    allow(env, "kararlar", "read", "propose")
    src = propose(env, mcp(), text="a source finding in the main journal")["ref"]
    ref = decide(env, mcp(), "Cites kitap and derives from J", ["a", "b"], "a", book="kararlar",
                 citations=[handle(env, "kitap")], links=[{"type": "derived_from", "ref": src}])["ref"]

    def revoke():
        authz.revoke(conn2, "book:kitap", "read", U)
        authz.revoke(conn2, f"book:{J}", "read", U)
    _after_records(monkeypatch, revoke)
    [r], _ = decisions.export(env, mcp(), ["kararlar"])
    assert r["ref"] == ref
    assert r["context"]["citations"] == [] and r["context"]["links"] == []


def test_the_export_withholds_text_when_a_source_loses_train_before_delivery(env, conn2, monkeypatch):  # #14 P2
    from kutuphane import decisions
    for book in ("kaynak", "kararlar"):
        notes.create_journal(env, book=book, title=book, search=True, ai_input=True, train=True, policy=CLOUD,
                             by="user:admin")
        allow(env, book, "read", "propose")
    a = propose(env, mcp(), book="kaynak", text="source A, trainable")["ref"]
    b = propose(env, mcp(), book="kararlar", text="B from A", links=[{"type": "derived_from", "ref": a}])["ref"]
    decide(env, mcp(), "Decision C from B", ["x", "y"], "x", book="kararlar",
           links=[{"type": "derived_from", "ref": b}])
    _after_records(monkeypatch, lambda: notes.restrict_journal(conn2, "kaynak", train=True))
    records, summary = decisions.export(env, mcp(), ["kararlar"])
    c = [r for r in records if r["options_sha256"]][0]
    assert c["context"]["text"] is None and c["options"] is None and c["choice"] is None
    assert c["withheld"] and c["ai_use"]["train"] == "n" and summary["withheld"] == len(records)
