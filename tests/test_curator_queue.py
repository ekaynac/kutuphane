"""The curator queue and its measures (docs/25 §6, §6.7; #77; slice Q): Q1–Q7 and the CLI queue (Pilot 2 G36).

Curator web runs as the curator web role with the deploy grants, as in test_curatorweb.py; the test writes as the
owner (the CLI). The delegation of Q4 is made with a real `delegate` act (a software authenticator) and the rows of
migration 025, so the database draws the sample.
"""
import json
import os
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from kutuphane import authz, catalog, cli, curatorqueue, curatorweb, notes, passkey, profiles
from kutuphane.gate import Actor
from kutuphane.source import read_source
from test_curatorweb import (CFG, H, J, LOCAL, U, client, env, events, note, options, ready, submit,  # noqa: F401
                             web_dsn)

AGENT = Actor("agent:kobra-7", U, channel="mcp")
UI = Path(curatorweb.UI_DIR)


def members(page) -> list[dict]:
    return [m for g in page["groups"] for m in g["members"]]


def seq_of(conn, ref) -> int:
    return conn.execute("SELECT seq FROM note WHERE id = %s", (ref.split("@")[1],)).fetchone()[0]


def standing(conn, ref, value, reason="ok"):
    notes.set_standing(conn, ref, value, curator=U, reason=reason)
    conn.commit()


def link(conn, src, kind, dst):
    notes.link(conn, AGENT, src, kind, dst)
    conn.commit()


# --- Q1: the risk order at a watermark ---------------------------------------------------------------------------

def test_the_risk_order_and_the_same_bytes_at_the_same_watermark(env, client):  # Q1
    old_rule = note(env, "Use ruff, not flake8", kind="convention")
    accepted = note(env, "The cache is per process")
    standing(env, old_rule, "approved")
    standing(env, accepted, "approved")
    test = note(env, "pytest -k cache: 3 passed", kind="test_result")
    dead = note(env, "Tried a shared cache: lock contention", kind="dead_end")
    finding = note(env, "Retry loop hides timeouts")
    lesson = note(env, "Measure before caching", kind="lesson")
    conv = note(env, "Name branches feat/<scope>", kind="convention")
    proposal = note(env, "Pick the queue", kind="decision_proposal",
                    decision={"options": ["redis", "postgres"], "choice": "postgres"})
    new_rule = note(env, "Use ruff format, not black", kind="convention",
                    links=[{"type": "supersedes", "ref": old_rule}])
    contra = note(env, "The cache is shared by every worker")
    link(env, contra, "contradicts", accepted)

    page = curatorqueue.queue(env, U)
    order = [(g["tier"], g["members"][0]["ref"]) for g in page["groups"]]
    assert order == [(1, new_rule), (1, contra), (2, proposal), (3, conv), (4, finding), (5, dead), (5, lesson),
                     (6, test)]
    why = {g["members"][0]["ref"]: g["why"] for g in page["groups"]}
    assert why[new_rule] == curatorqueue.WHY_SUPERSEDES and why[contra] == curatorqueue.WHY_CONTRADICTS
    assert page["pending"] == 8 and page["books"] == [J] and page["read_needed"] == []
    first = members(page)[0]
    assert first["writers"] == [{"principal": "agent:kobra-7", "on_behalf_of": U, "client_id": None}]
    assert first["origin"] == "model" and first["standing"] == "pending" and first["was"] is None
    assert first["links"][0]["type"] == "supersedes" and first["links"][0]["text"] == "Use ruff, not flake8"

    w = page["watermark"]
    again = json.dumps(curatorqueue.queue(env, U, w=w))
    note(env, "a later finding")                    # a new note after w
    standing(env, finding, "approved")              # a Standing event after w
    assert json.dumps(curatorqueue.queue(env, U, w=w)) == again == json.dumps(page)
    assert [m["ref"] for m in members(curatorqueue.queue(env, U))].count(finding) == 0

    ready(env, client)
    a, b = client.get(f"/api/queue?w={w}"), client.get(f"/api/queue?w={w}")
    assert a.status_code == 200 and a.content == b.content
    assert client.get(f"/api/queue?w={w + 10 ** 6}").status_code == 400


def test_pages_continue_at_the_same_watermark(env):  # Q1 (cursor)
    refs = [note(env, f"finding {i}") for i in range(5)]
    first = curatorqueue.queue(env, U, limit=2)
    note(env, "written after the first page")
    second = curatorqueue.queue(env, U, cursor=first["next_cursor"], limit=2)
    third = curatorqueue.queue(env, U, cursor=second["next_cursor"], limit=2)
    assert [m["ref"] for p in (first, second, third) for m in members(p)] == refs
    assert third["next_cursor"] is None and second["watermark"] == first["watermark"]
    with pytest.raises(ValueError, match="another w"):
        curatorqueue.queue(env, U, w=first["watermark"] - 1, cursor=first["next_cursor"])


# --- Q2: a same_as group in one act ------------------------------------------------------------------------------

def test_a_group_of_five_is_decided_in_one_act(env, client):  # Q2
    a, b, c, d, e = (note(env, f"The retry loop hides timeouts ({i})") for i in range(5))
    for src, dst in ((b, a), (c, a), (d, b), (e, a)):
        link(env, src, "same_as", dst)
    auth = ready(env, client)
    (group,) = client.get("/api/queue").json()["groups"]
    assert [m["ref"] for m in group["members"]] == [a, b, c, d, e] and group["pending"] == 5
    assert group["recurrence"] == 5 and group["proposed_again_after_rejection"] == 0
    items = [{"ref": a, "to": "approved"}] + [{"ref": r, "to": "rejected"} for r in (b, c, d, e)]
    o = options(client, items, reason=f"duplicate of {a}")
    r = submit(client, o, auth.get(o["publicKey"]))
    assert r.status_code == 200, r.text
    rows = env.execute("SELECT value, act, reason FROM standing_event ORDER BY seq").fetchall()
    assert len(rows) == 5 and {x[1] for x in rows} == {r.json()["act"]} and {x[2] for x in rows} == {f"duplicate of {a}"}
    assert [x[0] for x in rows].count("approved") == 1
    assert client.get("/api/queue").json()["groups"] == []


def test_a_group_shows_every_member_and_marks_contradicting_pairs(env):  # §6.3
    a, b, c = note(env, "uses port 8080"), note(env, "uses port 8090"), note(env, "uses port 8080, said again")
    link(env, b, "same_as", a)
    link(env, c, "same_as", a)
    link(env, b, "contradicts", a)
    standing(env, a, "approved")
    standing(env, c, "rejected")
    note_c_again = notes.propose(env, AGENT, {"book": J, "kind": "finding", "text": "uses port 8080, said again"})[0]
    env.commit()
    assert note_c_again["ref"] == c
    (group,) = curatorqueue.queue(env, U)["groups"]
    assert [(m["ref"], m["standing"], m["pending"]) for m in group["members"]] == [
        (a, "approved", False), (b, "pending", True), (c, "rejected", False)]
    assert group["tier"] == 1 and group["pairs"] == [[b, a]]
    assert group["proposed_again_after_rejection"] == 1


# --- Q3: the batch rules on the phone path -----------------------------------------------------------------------

def test_the_batch_rules_are_refused_before_the_passkey(env, client):  # Q3
    refs = [note(env, f"finding {i}") for i in range(51)]
    c1, c2 = note(env, "convention one", kind="convention"), note(env, "convention two", kind="convention")
    k1, k2 = note(env, "says yes"), note(env, "says no")
    link(env, k1, "contradicts", k2)
    for value in ("approved", "retired", "pending"):
        standing(env, refs[0], value)
    ready(env, client)

    def refused(items):
        r = client.post("/api/act/options", json={"action": "standing", "items": items, "reason": "batch"},
                        headers=H)
        return r.status_code, r.json()["error"]

    assert refused([{"ref": r, "to": "rejected"} for r in refs[1:]] + [{"ref": c1, "to": "rejected"}])[0] == 400
    assert "one rule" in refused([{"ref": c1, "to": "approved"}, {"ref": c2, "to": "approved"}])[1]
    assert "contradicts" in refused([{"ref": k1, "to": "approved"}, {"ref": k2, "to": "approved"}])[1]
    assert "D68" in refused([{"ref": refs[0], "to": "rejected"}])[1]
    assert env.execute("SELECT count(*) FROM curator_challenge WHERE action = 'standing'").fetchone()[0] == 0


# --- Q4: no suggestion and no sample mark before the act ---------------------------------------------------------

DECIDER = "qwen-notes@0.1"


def delegate(env, client, auth, *, sample_every=2) -> str:
    """A `delegate` act of the person (§8.2) and the curate_delegation row of its statement (migration 025)."""
    sid = passkey.session(env, client.cookies.get(curatorweb.COOKIE))[0]
    expires = env.execute("SELECT date_trunc('second', now()) + interval '14 days'").fetchone()[0]
    did = "cd_" + secrets.token_hex(16)
    spec = bytes(32)
    fields = {"delegation": {"id": did, "book": J, "kind": "finding", "decider": DECIDER, "spec_sha256": spec.hex(),
                             "min_confidence": 0.9, "sample_every": sample_every, "expires_at": expires.isoformat()}}
    with env.transaction():
        cid, _statement, opts = passkey.act_options(env, CFG, sid, U, "delegate", fields)
    with env.transaction():
        notes._lock(env)
        act = passkey.verify_act(env, CFG, sid, U, cid, auth.get(opts))
        env.execute("INSERT INTO curate_delegation (id, book, kind, decider, spec_sha256, min_confidence, "
                    "sample_every, created_by, act, expires_at) VALUES (%s, %s, 'finding', %s, %s, 0.9, %s, %s, %s, %s)",
                    (did, J, DECIDER, spec, sample_every, U, act.seq, expires))
    return did


def suggest(env, ref, value="approved", confidence=0.95) -> int:
    with env.transaction():
        notes._lock(env)
        call = env.execute("INSERT INTO model_call (correlation_id, principal, route, model, call_id) "
                           "VALUES ('c', 'agent:kutuphane-decider', 'chat', 'qwen', %s) RETURNING id",
                           (secrets.token_hex(8),)).fetchone()[0]
        return env.execute("INSERT INTO note_suggestion (note_seq, decider, spec_sha256, value, confidence, model_call) "
                           "VALUES (%s, %s, %s, %s, %s, %s) RETURNING seq",
                           (seq_of(env, ref), DECIDER, bytes(32), value, confidence, call)).fetchone()[0]


def use(env, did, ref, suggestion) -> bool:
    """A delegation use, as the decider runner inserts it; the database draws `sampled`."""
    with env.transaction():
        notes._lock(env)
        return env.execute(
            "INSERT INTO delegation_use (delegation, book, kind, decider, spec_sha256, approver, note_seq, suggestion, "
            "correlation_id) VALUES (%s, %s, 'finding', %s, %s, %s, %s, %s, 'run-1') RETURNING sampled",
            (did, J, DECIDER, bytes(32), f"model:{DECIDER}", seq_of(env, ref), suggestion)).fetchone()[0]


def test_suggestions_and_samples_only_in_the_receipt(env, client):  # Q4
    auth = ready(env, client)
    rule = note(env, "Name branches feat/<scope>", kind="convention")
    lesson = note(env, "Measure before caching", kind="lesson")
    findings = [note(env, f"finding number {i}") for i in range(12)]
    before = [m["ref"] for m in members(curatorqueue.queue(env, U))]
    did = delegate(env, client, auth)
    suggest(env, rule, "rejected", 0.81)
    sample = None
    for ref in findings:
        if use(env, did, ref, suggest(env, ref)):
            sample = ref
            break
    assert sample is not None  # N = 2: a forced sample after 4 unsampled uses at the latest
    pending = {m["ref"] for m in members(curatorqueue.queue(env, U))}
    assert sample in pending

    page = client.get("/api/queue")
    expected = [r for r in before if r in pending]
    assert [m["ref"] for g in page.json()["groups"] for m in g["members"]] == expected
    one = client.get(f"/api/note/{sample.replace('@', '/')}")
    for body in (page.text, one.text):
        for word in ("suggestion", "sample", "confidence", DECIDER, did, "delegat"):
            assert word not in body, word

    o = options(client, [{"ref": sample, "to": "approved"}, {"ref": rule, "to": "approved"}], reason="checked")
    r = submit(client, o, auth.get(o["publicKey"]))
    assert r.status_code == 200, r.text
    got = {i["ref"]: i for i in r.json()["items"]}
    assert got[sample]["sample"] == did
    assert got[sample]["suggestions"] == [{"decider": DECIDER, "value": "approved", "confidence": 0.95,
                                           "agrees": True}]
    assert got[rule]["sample"] is None
    assert got[rule]["suggestions"] == [{"decider": DECIDER, "value": "rejected", "confidence": 0.81,
                                         "agrees": False}]


# --- Q5: the measures --------------------------------------------------------------------------------------------

def test_the_report_gives_seconds_per_approved_note_and_the_seven_day_share(env, client, monkeypatch, capsys):  # Q5
    auth = ready(env, client)
    a, b, c, d, e = (note(env, f"finding {i}") for i in range(5))
    for items, ms in (([(a, "approved"), (b, "approved")], 30_000), ([(c, "approved"), (d, "rejected")], 10_000),
                      ([(e, "rejected")], 5_000)):
        o = options(client, [{"ref": r, "to": t} for r, t in items])
        assert submit(client, o, auth.get(o["publicKey"]), shown_ms=ms).status_code == 200

    # four notes written 20 days ago: decided after 2 days, after 10 days, never (a finding and a convention)
    old = [note(env, f"old finding {i}") for i in range(3)] + [note(env, "old convention", kind="convention")]
    for ref in old:
        env.execute("UPDATE note SET written_at = now() - interval '20 days' WHERE seq = %s", (seq_of(env, ref),))
    for ref, days in ((old[0], 18), (old[1], 10)):
        standing(env, ref, "approved", reason="cli")
        env.execute("UPDATE standing_event SET at = now() - %s * interval '1 day' WHERE note_seq = %s",
                    (days, seq_of(env, ref)))
    env.commit()

    now = datetime.now(timezone.utc)
    out = curatorqueue.report(env, now - timedelta(days=30), now + timedelta(minutes=1))
    t = out["curator_time"]
    assert t["acts"] == 3 and t["approved_notes"] == 3 and t["acts_by_synced_passkey"] == 3
    assert t["seconds_per_approved_note"] == pytest.approx(40 / 3, abs=1e-3)
    assert t["median_seconds_per_act"] == 10 and t["median_seconds_per_decided_note"] == 5
    p = out["pending_after_7_days"]
    assert (p["notes"], p["pending"], p["share"]) == (4, 3, 0.75)
    assert p["by_tier"] == {"3": {"notes": 1, "pending": 1, "share": 1.0},
                            "4": {"notes": 3, "pending": 2, "share": 0.6667}}
    assert p["by_book"] == {J: {"notes": 4, "pending": 3, "share": 0.75}}
    assert out["decided_by"]["people_web"] == {"approved": 3, "rejected": 2}
    assert out["decided_by"]["people_cli"] == {"approved": 2}  # 18 and 10 days old: both in the 30 days
    assert out["delegations"] == []

    monkeypatch.setenv("KUTUPHANE_CURATOR_DSN", os.environ["KUTUPHANE_TEST_DSN"])
    assert cli.main(["curator", "report", "--from", (now - timedelta(days=30)).date().isoformat(),
                     "--to", (now + timedelta(days=1)).date().isoformat()]) == 0
    assert json.loads(capsys.readouterr().out)["curator_time"]["approved_notes"] == 3
    with pytest.raises(ValueError):
        curatorqueue.report(env, now, now - timedelta(days=1))


def test_the_report_gives_the_live_agreement_of_a_delegation(env, client):  # Q5, §8.7
    auth = ready(env, client)
    findings = [note(env, f"finding number {i}") for i in range(12)]
    did = delegate(env, client, auth)
    sampled = []
    for ref in findings:
        if use(env, did, ref, suggest(env, ref)):
            sampled.append(ref)
            if len(sampled) == 2:
                break
    standing(env, sampled[0], "approved", reason="checked")
    now = datetime.now(timezone.utc)
    (d,) = curatorqueue.report(env, now - timedelta(days=1), now + timedelta(minutes=1))["delegations"]
    assert d["id"] == did and d["samples"] == {"agreed": 1, "disagreed": 0, "open": 1, "closed_no_verdict": 0}
    assert d["approved"] == d["uses"] - 2 and d["ended"] is None
    assert d["coverage"]["approved_by_delegation"] == d["approved"] and d["coverage"]["notes"] == 12
    standing(env, sampled[1], "rejected", reason="wrong")
    (d,) = curatorqueue.report(env, now - timedelta(days=1), now + timedelta(minutes=1))["delegations"]
    assert d["samples"]["disagreed"] == 1 and d["ended"]["cause"] == "disagreement"


# --- Q6: the page --------------------------------------------------------------------------------------------------

def test_the_page_shows_plain_text_marks_and_loads_nothing_external(client):  # Q6
    r = client.get("/")
    assert r.status_code == 200
    csp = r.headers["content-security-policy"]
    assert "default-src 'none'" in csp and "script-src 'self'" in csp and "frame-ancestors 'none'" in csp
    shell = r.text + "".join((UI / f).read_text(encoding="utf-8") for f in ("core.js", "queue.js", "app.css"))
    assert "http://" not in shell and "https://" not in shell and "//cdn" not in shell
    assert '<script src="/static/queue.js" defer></script>' in r.text
    for name in ("core.js", "queue.js"):
        js = (UI / name).read_text(encoding="utf-8")
        assert "innerHTML" not in js and "insertAdjacentHTML" not in js and "document.write" not in js
    core = (UI / "core.js").read_text(encoding="utf-8")
    assert "\\u200b" in core and "\\u202a-\\u202e" in core  # U+200B and U+202E are shown as marks
    assert client.get("/static/queue.js").status_code == 200


# --- Q7: rights, gated links and citations, the view record -----------------------------------------------------

@pytest.fixture
def books(env, okf_dir):
    catalog.publish(env, book="kitap", title="kitap", files=read_source(okf_dir), policy=LOCAL,
                    profile=profiles.spec("chunked"))
    notes.create_journal(env, book="ikinci", title="ikinci", search=True, ai_input=True, policy=LOCAL, by="user:admin")
    notes.create_journal(env, book="ucuncu", title="ucuncu", search=True, ai_input=True, policy=LOCAL, by="user:admin")
    for book in ("kitap", "ucuncu"):
        for mode in ("read", "propose"):
            authz.grant(env, f"book:{book}", mode, U)
            authz.delegate(env, delegator=U, delegate_to="agent:kobra-7", obj=f"book:{book}", mode=mode,
                           expires_at=datetime.now(timezone.utc) + timedelta(hours=1))
    authz.grant(env, "book:ikinci", "curate", U)  # curate but no read
    env.commit()
    return env


def passage(conn, book) -> str:
    row = conn.execute("SELECT book, content_id, profile_id, path, ordinal FROM chunk WHERE book = %s "
                       "ORDER BY path, ordinal LIMIT 1", (book,)).fetchone()
    return f"{row[0]}@{row[1]}/{row[2]}/{row[3]}#{row[4]}"


def test_only_curate_and_read_books_and_gated_links_and_citations(books, client):  # Q7
    env = books
    handle = passage(env, "kitap")
    other = notes.propose(env, AGENT, {"book": "ucuncu", "kind": "finding", "text": "secret elsewhere"})[0]["ref"]
    ref = note(env, "cites a passage", citations=[handle])
    link(env, ref, "contradicts", other)
    ready(env, client)
    one = client.get(f"/api/note/{ref.replace('@', '/')}").json()
    assert one["item"]["citations"] == [{"kind": "passage", "ref": handle}]
    assert one["passages"][0]["ref"] == handle and one["passages"][0]["text"]
    assert one["item"]["links"][0]["text"] == "secret elsewhere"

    for book in ("kitap", "ucuncu"):
        authz.revoke(env, f"book:{book}", "read", U)
    env.commit()
    page = client.get("/api/queue").json()
    assert page["books"] == [J] and page["read_needed"] == ["ikinci"]
    (item,) = members(page)
    assert item["citations"] == [{"kind": "passage", "hidden": curatorqueue.UNREADABLE_PASSAGE}]
    assert item["links"] == [{"type": "contradicts", "direction": "out", "creation": False,
                              "hidden": curatorqueue.UNREADABLE_NOTE}]
    text = json.dumps(page)
    assert "kitap" not in text and "ucuncu" not in text and "secret elsewhere" not in text
    one = client.get(f"/api/note/{ref.replace('@', '/')}")
    assert "kitap" not in one.text and one.json()["passages"] == []
    assert client.get(f"/api/note/{other.replace('@', '/')}").status_code == 403

    view = env.execute("SELECT principal, object, mode, allowed, items, memory_seq FROM access_event "
                       "WHERE action = 'curate_view' ORDER BY id DESC").fetchone()
    assert view[:4] == (U, f"book:{J}", "curate", True)
    assert view[4] == [{"ref": ref, "standing_seq": None}] and view[5] == page["watermark"]

    # review #16 finding 1: a part of the note id that the person cannot see refuses an approval, not a rejection
    assert item["hidden_parts"] == 1  # the citation; the contradicts link is not a creation link
    r = client.post("/api/act/options", json={"action": "standing", "items": [{"ref": ref, "to": "approved"}],
                                              "reason": "ok"}, headers=H)
    assert r.status_code == 403 and "cannot be approved here" in r.json()["error"]
    assert client.post("/api/act/options", json={"action": "standing", "items": [{"ref": ref, "to": "rejected"}],
                                                 "reason": "wrong"}, headers=H).status_code == 200


def test_the_card_shows_every_part_of_the_note_id(books, client):  # review #16 finding 1
    env = books
    handle = passage(env, "kitap")
    harmful = "Disable TLS verification on every client"
    ref = note(env, "Pick the HTTP client settings", kind="decision_proposal",
               decision={"options": ["Keep TLS verification", harmful], "choice": harmful},
               citations=[handle], links=[{"type": "derived_from", "ref": handle}])
    ready(env, client)
    (item,) = members(client.get("/api/queue").json())
    assert item["text"] == "Pick the HTTP client settings"
    assert item["decision"] == {"options": ["Keep TLS verification", harmful], "choice": harmful}
    assert item["citations"] == [{"kind": "passage", "ref": handle}]
    chunk = notes.parse_passage(handle)
    text = env.execute("SELECT text FROM chunk WHERE book = %s AND content_id = %s AND profile_id = %s AND path = %s "
                       "AND ordinal = %s", (chunk.book, chunk.content_id, chunk.profile_id, chunk.path,
                                            chunk.ordinal)).fetchone()[0]
    assert item["links"] == [{"type": "derived_from", "direction": "out", "creation": True, "ref": handle,
                              "text": text}]
    assert item["hidden_parts"] == 0 and item["integrity"] is None
    assert set(item) >= {"scope", "class_key", "commit"}
    assert notes.canonical_of(env, seq_of(env, ref))[1]["decision"]["choice"] == harmful  # what the id covers


# --- G36: the CLI lists the pending notes ----------------------------------------------------------------------------

def test_the_cli_lists_the_queue_of_a_curator(env, monkeypatch, capsys):  # Pilot 2 G36
    a = note(env, "finding a")
    c = note(env, "convention c", kind="convention")
    monkeypatch.setenv("KUTUPHANE_CURATOR_DSN", os.environ["KUTUPHANE_TEST_DSN"])
    assert cli.main(["curator", "queue", "--curator", U]) == 0
    out = json.loads(capsys.readouterr().out)
    assert [m["ref"] for m in members(out)] == [c, a]
    assert cli.main(["curator", "queue", "--curator", U, "--book", "baska"]) == 3
    assert "denied" in capsys.readouterr().err
    view = env.execute("SELECT principal, items FROM access_event WHERE action = 'curate_view'").fetchone()
    assert view == (U, [{"ref": c, "standing_seq": None}, {"ref": a, "standing_seq": None}])
