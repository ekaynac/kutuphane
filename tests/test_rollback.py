"""#79: rollback along `derived_from`, its report, and restriction that follows derivation (docs/24 §20)."""
import json
import os

import pytest

from kutuphane import authz, cli, db, decisions, gate, notes
from kutuphane.gate import Actor
from kutuphane.notesquery import open_note, query_notes
from test_notes import A, J, U, allow, env, http, journal, mcp, row  # noqa: F401 (env is a fixture)

J2 = "hafiza-iki"
CURATOR = "user:kurator"


def put(conn, text, book=J, actor=None, **args):
    return notes.propose(conn, actor or mcp(), {"book": book, "kind": "finding", "text": text, **args})[0]["ref"]


def derived(conn, text, src, book=J):
    return put(conn, text, book, links=[{"type": "derived_from", "ref": src}])


def act(conn, ref, value):
    return notes.set_standing(conn, ref, value, curator=CURATOR, reason="r")


def seq_of(conn, ref):
    return row(conn, "SELECT seq FROM note WHERE id = %s", ref.split("@")[1])[0]


def events(conn, ref):
    return conn.execute("SELECT value, set_by, cause_seq, reason FROM standing_event WHERE note_seq = %s ORDER BY seq",
                        (seq_of(conn, ref),)).fetchall()


def standing(conn, ref):
    s = seq_of(conn, ref)
    return notes.effective_standing(conn, [s], notes.NOW)[s][0]


@pytest.fixture
def chain(env):
    """root (approved) <- b (approved) <- c (pending) <- d (another journal, pending); e: a creation `about` link
    to root; f: a later `same_as` link to root. Only b, c, d are on a `derived_from` chain to root."""
    journal(env, J2)
    allow(env, J2, "read", "propose")
    authz.grant(env, f"book:{J}", "curate", CURATOR)
    root = put(env, "poison: disable the TLS check in deploy")
    act(env, root, "approved")
    b = derived(env, "summary: the TLS check is optional", root)
    act(env, b, "approved")
    c = derived(env, "lesson: skip TLS checks to save time", b)
    d = derived(env, "convention draft from the lesson", c, book=J2)
    e = put(env, "about the TLS note", links=[{"type": "about", "ref": root}])
    f = put(env, "poison: disable the TLS check in deploy (again)")
    notes.link(env, mcp(), f, "same_as", root)
    return {"root": root, "b": b, "c": c, "d": d, "e": e, "f": f}


def test_rollback_retires_the_root_and_every_note_derived_from_it(env, chain):  # T39
    root, b, c, d = chain["root"], chain["b"], chain["c"], chain["d"]
    out = notes.rollback(env, root, curator=CURATOR, reason="poisoned: MINJA-style injection")
    assert events(env, root)[-1] == ("retired", CURATOR, None, "poisoned: MINJA-style injection")
    cause = out["event_seq"]
    for ref in (b, c, d):
        assert events(env, ref)[-1] == ("retired", "system", cause, f"derived from {root}")
        assert standing(env, ref) == "retired"
    assert standing(env, chain["e"]) == "pending" and standing(env, chain["f"]) == "pending"
    assert events(env, chain["e"]) == [] and events(env, chain["f"]) == []
    assert out["root"] == root
    assert [(n["ref"], n["was"], n["standing"]) for n in out["notes"]] == [
        (root, "approved", "retired"), (b, "approved", "retired"), (c, "pending", "retired"),
        (d, "pending", "retired")]
    assert all(n["event_seq"] for n in out["notes"])
    assert out["notes"][0]["writers"] == [{"principal": A, "on_behalf_of": U, "client_id": None}]
    # a reader sees the retirement and its reason: no longer current, not open
    items = query_notes(env, mcp(), for_model=True, sets=["current", "open"])["items"]
    assert {i["ref"] for i in items} == {chain["e"], chain["f"]}


def test_a_pending_root_is_rejected_and_out_notes_keep_their_standing(env):  # T40
    authz.grant(env, f"book:{J}", "curate", CURATOR)
    root = put(env, "a pending poisoned note")
    x = derived(env, "x from the pending note", root)
    y = derived(env, "y from x", x)
    act(env, x, "rejected")
    out = notes.rollback(env, root, curator=CURATOR, reason="poisoned")
    assert events(env, root) == [("rejected", CURATOR, None, "poisoned")]  # D68: never accepted
    assert events(env, x) == [("rejected", CURATOR, None, "r")]  # already out: no event
    assert events(env, y) == [("retired", "system", out["event_seq"], f"derived from {root}")]
    assert [(n["ref"], n["was"], n["standing"], n["event_seq"] is None) for n in out["notes"]] == [
        (root, "pending", "rejected", False), (x, "rejected", "rejected", True), (y, "pending", "retired", False)]
    # rolled back again (a new note derived after the act): one more root event, the new note is reached
    z = derived(env, "z from the rejected root, written later", root)
    again = notes.rollback(env, root, curator=CURATOR, reason="again")
    assert [v for v, *_ in events(env, root)] == ["rejected", "rejected"]
    assert events(env, z) == [("retired", "system", again["event_seq"], f"derived from {root}")]
    assert [n["event_seq"] is None for n in again["notes"]] == [False, True, True, False]


def test_the_report_lists_the_reads_answers_and_exports_of_the_closure(env, chain):  # T41
    root, b, c, d = chain["root"], chain["b"], chain["c"], chain["d"]
    reader = mcp()
    query_notes(env, reader, for_model=True, sets=["current", "open"])          # delivers root, b, c, e, f, d
    open_note(env, http(), for_model=False, ref=d)                                 # one note, by a person
    open_note(env, http(), for_model=False, ref=chain["e"])                        # another note only: not listed
    candidate = notes.propose(env, mcp(), {"book": J, "kind": "finding",           # a candidate delivery of root
                                           "text": "Poison: disable the TLS check in deploy"})[0]
    assert root in [x["ref"] for x in candidate["candidates"]]
    asker, exporter = Actor(A, U), Actor("agent:ihracat")
    seq_b = seq_of(env, b)
    b_event = notes.effective_standing(env, [seq_b], notes.NOW)[seq_b][1]
    env.execute("INSERT INTO answer (id, correlation_id, principal, on_behalf_of, question, status, body) "
                "VALUES ('an_1', %s, %s, %s, 'is the TLS check optional?', 'answered', 'yes [1]')",
                (asker.correlation_id, A, U))
    ok = authz.Decision(True, "test")
    gate.log_event(env, asker, "answer", f"book:{J}", "read", ok, None, None, None,
                   items=[{"ref": b, "standing_seq": b_event}])
    # a real decision export (#74) of one decision note in the closure and one outside it
    g = notes.propose(env, mcp(), {"book": J, "kind": "decision_proposal", "text": "decide: drop TLS checks in CI",
                                   "decision": {"options": ["drop", "keep"], "choice": "drop"},
                                   "links": [{"type": "derived_from", "ref": b}]})[0]["ref"]
    h = notes.propose(env, mcp(), {"book": J, "kind": "decision_proposal", "text": "decide: cache the index",
                                   "decision": {"options": ["cache", "rebuild"], "choice": "cache"}})[0]["ref"]
    authz.grant(env, f"book:{J}", "read", exporter.principal)
    records, _ = decisions.export(env, exporter, [J])
    assert {r["ref"] for r in records} == {g, h}
    gate.log_event(env, exporter, "export_decisions", f"book:{J}", "read", authz.Decision(False, "no right"),
                   None, None, None, items=[{"ref": root, "standing_seq": None}])  # refused: not a delivery

    out = notes.rollback(env, root, curator=CURATOR, reason="poisoned")
    deliveries = [(x["action"], x["principal"], [i["ref"] for i in x["items"]]) for x in out["deliveries"]]
    assert deliveries == [("query_notes", A, [root, b, c]), ("query_notes", A, [d]), ("cite", U, [d]),
                          ("propose", A, [root])]
    first = out["deliveries"][0]
    assert first["on_behalf_of"] == U and first["correlation_id"] == reader.correlation_id
    assert first["memory_seq"] is not None
    assert [i["standing"] for i in first["items"]] == ["approved", "approved", "pending"]
    assert out["answers"] == [{"id": "an_1", "at": out["answers"][0]["at"], "principal": A, "on_behalf_of": U,
                               "refs": [b]}]
    assert [(x["action"], x["principal"], [i["ref"] for i in x["items"]]) for x in out["exports"]] == [
        ("export_decisions", "agent:ihracat", [g])]


def test_rollback_needs_curate_on_the_root_book_and_the_curator_credential(env, monkeypatch, capsys):  # T42
    root = put(env, "poison")
    derived(env, "derived", root)
    with pytest.raises(gate.Denied, match="curate"):
        notes.rollback(env, root, curator=CURATOR, reason="x")
    for bad in ({"curator": "agent:kobra-7", "reason": "x"}, {"curator": CURATOR, "reason": ""}):
        with pytest.raises(ValueError):
            notes.rollback(env, root, **bad)
    assert row(env, "SELECT count(*) FROM standing_event")[0] == 0
    cmd = ["note", "rollback", root, "--curator", CURATOR, "--reason", "poisoned"]
    monkeypatch.delenv(db.CURATOR_DSN_ENV, raising=False)
    assert cli.main(cmd) == 2 and db.CURATOR_DSN_ENV in capsys.readouterr().err
    monkeypatch.setenv(db.CURATOR_DSN_ENV, os.environ["KUTUPHANE_TEST_DSN"])
    assert cli.main(cmd) == 3 and "curate" in capsys.readouterr().err
    authz.grant(env, f"book:{J}", "curate", CURATOR)
    assert cli.main(cmd) == 0
    out = json.loads(capsys.readouterr().out)
    assert [n["standing"] for n in out["notes"]] == ["rejected", "retired"]


def test_a_restricted_source_journal_restricts_notes_derived_from_it(env):  # T43
    journal(env, J2)
    allow(env, J2, "read", "propose")
    src = put(env, "a source note", book=J2)
    note = derived(env, "derived into the main journal", src)
    notes.restrict_journal(env, J2, ai_input=True)
    item = {i["ref"]: i for i in query_notes(env, mcp(), for_model=True, sets=["open"])["items"]}[note]
    assert item["text"] is None and item["withheld"]
    assert notes.item_info(env, seq_of(env, note))["ai_use"] == {"search": "y", "ai_input": "n"}
    later = derived(env, "derived from the derived note", note)
    assert row(env, "SELECT ai_input FROM note WHERE id = %s", later.split("@")[1]) == (False,)
    # a person over HTTP still reads the text; search is unchanged
    item = {i["ref"]: i for i in query_notes(env, http(), for_model=False, sets=["open"])["items"]}[note]
    assert item["text"] == "derived into the main journal"
    assert row(env, "SELECT search FROM note_journal WHERE seq = %s", seq_of(env, note)) == (True,)


def test_train_follows_derivation_through_the_note_journal_view(env):  # §20.3, §21.3
    from test_notes import LOCAL
    for book in ("kaynak", "kararlar"):
        notes.create_journal(env, book=book, title=book, search=True, ai_input=True, train=True, policy=LOCAL,
                             by="user:admin")
        allow(env, book, "read", "propose")
    src = put(env, "a trainable source note", book="kaynak")
    ref = notes.propose(env, mcp(), {"book": "kararlar", "kind": "decision_proposal", "text": "decide: keep the cache",
                                     "decision": {"options": ["keep", "drop"], "choice": "keep"},
                                     "links": [{"type": "derived_from", "ref": src}]})[0]["ref"]
    assert row(env, "SELECT train FROM note WHERE id = %s", ref.split("@")[1]) == (True,)
    [shown], _ = decisions.export(env, mcp(), ["kararlar"])
    assert shown["withheld"] is None and shown["ai_use"]["train"] == "y"
    notes.restrict_journal(env, "kaynak", train=True)       # the source journal only
    assert row(env, "SELECT train FROM note_journal WHERE seq = %s", seq_of(env, ref)) == (False,)
    [hidden], _ = decisions.export(env, mcp(), ["kararlar"])
    assert hidden["withheld"] and hidden["ai_use"]["train"] == "n"
    later = put(env, "derived from the decision", book="kararlar", links=[{"type": "derived_from", "ref": ref}])
    assert row(env, "SELECT train FROM note WHERE id = %s", later.split("@")[1]) == (False,)


def test_rollback_retires_a_reopened_root_that_was_approved_before(env):  # Astra #14 P3, D68
    authz.grant(env, f"book:{J}", "curate", CURATOR)
    root = put(env, "approved once, then retired and reopened")
    child = derived(env, "derived from the reopened root", root)
    for value in ("approved", "retired", "pending"):
        act(env, root, value)
    out = notes.rollback(env, root, curator=CURATOR, reason="poisoned")
    assert events(env, root)[-1] == ("retired", CURATOR, None, "poisoned")
    assert [(n["ref"], n["was"], n["standing"]) for n in out["notes"]] == [
        (root, "pending", "retired"), (child, "pending", "retired")]


def test_standing_refuses_rejected_for_a_note_that_was_ever_approved(env, monkeypatch, capsys):  # Astra #14, D68
    authz.grant(env, f"book:{J}", "curate", CURATOR)
    ref = put(env, "approved once")
    for value in ("approved", "retired", "pending"):
        act(env, ref, value)
    with pytest.raises(ValueError, match="use retired"):
        act(env, ref, "rejected")
    monkeypatch.setenv(db.CURATOR_DSN_ENV, os.environ["KUTUPHANE_TEST_DSN"])
    assert cli.main(["note", "standing", ref, "rejected", "--curator", CURATOR, "--reason", "x"]) != 0
    assert "use retired" in capsys.readouterr().err
    assert [v for v, *_ in events(env, ref)] == ["approved", "retired", "pending"]
    never = put(env, "never approved")
    assert act(env, never, "rejected")["standing"] == "rejected"
