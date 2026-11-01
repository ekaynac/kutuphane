"""docs/25 §4.4, §8, §12.2 C9, D1, D3, D5, D7, D9, M1 (slice D): the signed delegation, the sample verdict on every
Standing path, expiry, the end, the report, and the database rules of migration 025 as hostile inserts.

Curator web runs as its role with the deploy grants and a software authenticator (tests/softauthn.py); the runner
runs as the decider role against the fake model route of test_decider.py.
"""
import json
import os
import secrets
from datetime import timedelta
from importlib.resources import files

import psycopg
import pytest
from starlette.testclient import TestClient

from kutuphane import authz, cli, curatorweb, db, decider, delegation, notes, notesquery, passkey
from kutuphane.gate import Actor

from conftest import WRITE_PATH_COLUMNS
from softauthn import SoftAuthenticator
from test_curatorweb import CFG, H, ORIGIN, enroll, login, web_dsn
from test_decider import (APP, DEC, J, LOCAL, M, MODEL, U, WEB, A, act_row, apply_roles, drop_roles, note,
                          open_samples, signed_delegation, spec, statement, uses)
from test_decider import dec, env, route  # noqa: F401  (fixtures)


@pytest.fixture
def client(env):
    with TestClient(curatorweb.create_app(dsn=web_dsn(), cfg=CFG), base_url=ORIGIN) as c:
        yield c


def ready(conn, client, principal=U):
    auth = SoftAuthenticator(ORIGIN)
    assert enroll(conn, client, auth, principal=principal).status_code == 200
    assert login(client, auth).status_code == 200
    return auth


def sign(client, auth, body):
    """One act through curator web: options, then the software authenticator's assertion."""
    o = client.post("/api/act/options", json=body, headers=H)
    if o.status_code != 200:
        return o
    o = o.json()
    return client.post("/api/act", json={"challenge_id": o["challenge_id"], "credential": auth.get(o["publicKey"])},
                       headers=H)


def delegate_body(s, **over):
    return {"action": "delegate", "book": J, "kind": "finding", "decider": s.decider,
            "spec_sha256": s.sha256.hex(), "min_confidence": 0.9, "sample_every": 10, "days": 14, **over}


def shadow_decisions(conn, s, n, *, value="approved", confidence=0.95, kind="finding"):
    """n notes with a suggestion of `s` written before a person's verdict `value` (§8.7)."""
    for _ in range(n):
        seq, ref = note(conn, f"Shadow {kind} {secrets.token_hex(4)}", kind=kind)
        call = conn.execute("INSERT INTO model_call (correlation_id, call_id, principal, route, model) "
                            "VALUES ('shadow', %s, %s, 'chat', %s) RETURNING id",
                            (f"shadow.{secrets.token_hex(6)}", decider.PRINCIPAL, MODEL)).fetchone()[0]
        conn.execute("INSERT INTO note_suggestion (note_seq, decider, spec_sha256, value, confidence, model_call) "
                     "VALUES (%s, %s, %s, 'approved', %s, %s)", (seq, s.decider, s.sha256, confidence, call))
        notes.set_standing(conn, ref, value, curator=U, reason="checked")


def ref_of(conn, seq):
    return conn.execute("SELECT book || '@' || id FROM note WHERE seq = %s", (seq,)).fetchone()[0]


def sampled_note(env, dec, route, s, d):
    """Run the decider over fresh notes until the database draws a sample (N = 2: forced after 4)."""
    for i in range(6):
        note(env, f"Candidate finding {i} {secrets.token_hex(3)}")
        decider.run(dec, s, route.bridge())
        waiting = open_samples(env, d)
        if waiting:
            return waiting[0]
    raise AssertionError("no sample drawn within 2N + 1 uses")


def run(conn, sql, params=(), *, role=None):
    with conn.transaction():
        if role:
            conn.execute(f"SET LOCAL ROLE {role}")
        cur = conn.execute(sql, params)
        return cur.fetchone() if cur.description else None


USE = ("INSERT INTO delegation_use (delegation, book, kind, decider, spec_sha256, approver, note_seq, suggestion, "
       "correlation_id) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'c')")


# --- D1: create ---------------------------------------------------------------------------------------------------

def test_a_delegation_is_created_only_by_a_signed_delegate_act_with_shadow_evidence(env, client):  # D1
    s = spec()
    auth = ready(env, client)
    shadow_decisions(env, s, 29)
    shadow_decisions(env, s, 3, value="rejected", confidence=0.95)  # disagreements count in n too
    shadow_decisions(env, s, 5, confidence=0.6)  # under the chosen threshold: not counted at 0.9
    table = {r["threshold"]: r for r in delegation.agreement(env, s.decider, s.sha256, J, "finding")}
    assert (table[0.9]["n"], table[0.9]["agreed"], table[0.5]["n"]) == (32, 29, 37)
    assert 0 < table[0.9]["wilson_lower"] < table[0.9]["share"] == round(29 / 32, 4)
    r = sign(client, auth, delegate_body(s, min_confidence=0.95))
    assert r.status_code == 200, r.text  # 32 shadow decisions at 0.95
    d = r.json()["delegation"]
    row = env.execute("SELECT book, kind, decider, approver, min_confidence, sample_every, created_by, "
                      "expires_at - created_at < interval '14 days 1 minute' FROM curate_delegation WHERE id = %s",
                      (d,)).fetchone()
    assert row == (J, "finding", s.decider, s.approver, pytest.approx(0.95), 10, U, True)
    assert passkey.verify_acts(env, CFG) == {"acts": 1, "problems": []}
    refusals = {"kind": delegate_body(s, kind="convention"), "days": delegate_body(s, days=31),
                "sample": delegate_body(s, sample_every=1), "threshold": delegate_body(s, min_confidence=0.4),
                "shadow": delegate_body(s, kind="lesson")}  # no shadow decisions in this class
    for why, body in refusals.items():
        r = sign(client, auth, body)
        assert r.status_code == 400, (why, r.text)
    assert "shadow decisions" in sign(client, auth, delegate_body(s, kind="lesson")).json()["error"]
    other = spec(instructions="Another prompt.")
    assert sign(client, auth, delegate_body(other)).status_code == 400  # another spec: no shadow evidence
    authz.revoke(env, f"book:{J}", "curate", U)
    assert sign(client, auth, delegate_body(s)).status_code == 403
    assert env.execute("SELECT count(*) FROM curate_delegation").fetchone()[0] == 1


def test_the_database_accepts_only_the_signed_statement(env):  # D1, C9
    s = spec()
    now = env.execute("SELECT date_trunc('second', now())").fetchone()[0]
    d = statement(s, expires_at=now + timedelta(days=14))
    act = act_row(env, U, "delegate", {"delegation": d})
    insert = ("INSERT INTO curate_delegation (id, book, kind, decider, spec_sha256, min_confidence, sample_every, "
              "created_by, act, expires_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)")
    row = [d["id"], J, "finding", s.decider, s.sha256, 0.9, 10, U, act, now + timedelta(days=14)]
    for i, changed in ((5, 0.5), (6, 2), (3, "other@0.1"), (4, b"\0" * 32), (9, now + timedelta(days=13))):
        bad = list(row)
        bad[i] = changed
        with pytest.raises(psycopg.errors.RaiseException, match="not the statement"):
            run(env, insert, bad, role=WEB)
    with pytest.raises(psycopg.errors.ForeignKeyViolation):  # the signer is the creator
        run(env, insert, row[:7] + [M] + row[8:], role=WEB)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):  # Core cannot create one
        run(env, insert, row, role=APP)
    run(env, insert, row, role=WEB)
    standing_act = act_row(env, U, "standing", {"delegation": {**d, "id": "cd_" + "1" * 32}})
    with pytest.raises(psycopg.errors.ForeignKeyViolation):  # only a `delegate` act
        run(env, insert, ["cd_" + "1" * 32] + row[1:8] + [standing_act, row[9]])
    rule = statement(s, kind="convention", expires_at=now + timedelta(days=14))
    with pytest.raises(psycopg.errors.CheckViolation):  # a rule kind: never
        run(env, insert, [rule["id"], J, "convention", s.decider, s.sha256, 0.9, 10, U,
                          act_row(env, U, "delegate", {"delegation": rule}), now + timedelta(days=14)])
    long = statement(s, expires_at=now + timedelta(days=31))
    with pytest.raises(psycopg.errors.CheckViolation):  # more than 30 days
        run(env, insert, [long["id"], J, "finding", s.decider, s.sha256, 0.9, 10, U,
                          act_row(env, U, "delegate", {"delegation": long}), now + timedelta(days=31)])


# --- C9: the use rules ----------------------------------------------------------------------------------------------

def test_the_decider_role_inserts_only_uses_the_database_decides(env, dec, route):  # C9
    s = spec()
    d = signed_delegation(env, s, sample_every=100)
    good, _ = note(env, "A good finding")
    rule, _ = note(env, "Use tabs", kind="convention")
    low, _ = note(env, "A weak finding")
    route.answers["A weak finding"] = ("approve", 0.6)
    decider.run(dec, s, route.bridge(), books=[J], shadow=True)
    sug = dict(env.execute("SELECT note_seq, seq FROM note_suggestion").fetchall())
    with pytest.raises(psycopg.errors.ForeignKeyViolation):  # another approver
        run(env, USE, (d, J, "finding", s.decider, s.sha256, "model:other@1", good, sug[good]), role=DEC)
    with pytest.raises(psycopg.errors.RaiseException, match="not the next note"):  # a rule note: not of the class
        run(env, USE, (d, J, "finding", s.decider, s.sha256, s.approver, rule, sug[rule]), role=DEC)
    with pytest.raises(psycopg.errors.ForeignKeyViolation):  # the suggestion of another note
        run(env, USE, (d, J, "finding", s.decider, s.sha256, s.approver, good, sug[rule]), role=DEC)
    with pytest.raises(psycopg.errors.RaiseException, match="under the delegation threshold"):
        run(env, USE, (d, J, "finding", s.decider, s.sha256, s.approver, low, sug[low]), role=DEC)
    for role in (APP, WEB):
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            run(env, USE, (d, J, "finding", s.decider, s.sha256, s.approver, good, sug[good]), role=role)
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            run(env, "INSERT INTO note_suggestion (note_seq, decider, spec_sha256, value, confidence, model_call) "
                     "SELECT note_seq, decider, spec_sha256, value, confidence, model_call FROM note_suggestion "
                     "LIMIT 1", role=role)
    run(env, USE, (d, J, "finding", s.decider, s.sha256, s.approver, good, sug[good]), role=DEC)
    with pytest.raises((psycopg.errors.UniqueViolation, psycopg.errors.RaiseException)):  # one use per note
        run(env, USE, (d, J, "finding", s.decider, s.sha256, s.approver, good, sug[good]), role=DEC)
    use_seq, _, sampled, event, *_ = uses(env, d)[0]
    if not sampled:  # a delegated event names the use of the same note, approved only
        other, _ = note(env, "Another note")
        with pytest.raises(psycopg.errors.ForeignKeyViolation):
            run(env, "INSERT INTO standing_event (note_seq, value, set_by, reason, correlation_id, delegation_use) "
                     "VALUES (%s, 'approved', %s, 'x', 'c', %s)", (other, s.approver, use_seq + 1000))
        with pytest.raises(psycopg.errors.CheckViolation):
            run(env, "INSERT INTO standing_event (note_seq, value, set_by, reason, correlation_id) "
                     "VALUES (%s, 'approved', %s, 'x', 'c')", (other, s.approver))
    assert run(env, "SELECT count(*) FROM delegation_use", role=APP)[0] == 1  # reads stay open


# --- D3: the sample and its verdict on every path -------------------------------------------------------------------

@pytest.mark.parametrize("path", ["phone", "standing", "rollback", "approve"])
def test_a_sample_waits_for_a_person_and_a_rejection_ends_the_delegation(env, dec, route, client, path):  # D3
    s = spec()
    auth = ready(env, client) if path == "phone" else None
    d = signed_delegation(env, s, sample_every=2)
    sample = sampled_note(env, dec, route, s, d)
    ref = ref_of(env, sample)
    reader = Actor(U, channel="http")
    item = next(i for i in notesquery.query_notes(env, reader, for_model=False, book=[J], sets=["open"])["items"]
                if i["ref"] == ref)
    assert item["standing"] == "pending" and item["approved_by"] is None
    assert not {"suggestion", "sample", "sampled", "delegation"} & set(item)  # no mark, no suggestion
    if path == "phone":
        o = client.post("/api/act/options", json={"action": "standing", "items": [{"ref": ref, "to": "rejected"}],
                                                  "reason": "wrong"}, headers=H).json()
        r = client.post("/api/act", json={"challenge_id": o["challenge_id"], "credential": auth.get(o["publicKey"])},
                        headers=H)
        assert r.status_code == 200, r.text
    elif path == "standing":
        notes.set_standing(env, ref, "rejected", curator=U, reason="wrong")
    elif path == "rollback":
        notes.rollback(env, ref, curator=U, reason="wrong source")
    else:
        notes.set_standing(env, ref, "approved", curator=U, reason="checked: correct")
    verdict = env.execute("SELECT seq FROM standing_event WHERE note_seq = %s ORDER BY seq LIMIT 1",
                          (sample,)).fetchone()[0]
    ended = env.execute("SELECT cause, ended_by, event FROM delegation_end WHERE delegation = %s", (d,)).fetchone()
    report = delegation.report(env, d)
    if path == "approve":
        assert ended is None and report["live_agreement"]["agreed"] == 1
        return
    assert ended == ("disagreement", "system", verdict)  # in the same transaction as the verdict
    assert report["live_agreement"]["disagreed"] == 1 and report["delegation"]["state"] == "ended:disagreement"
    note(env, "A finding after the end")
    assert decider.run(dec, s, route.bridge(), books=[J])["uses"] == []
    fresh = env.execute("SELECT note_seq, seq FROM note_suggestion s WHERE NOT EXISTS (SELECT 1 FROM delegation_use u "
                        "WHERE u.note_seq = s.note_seq) AND NOT EXISTS (SELECT 1 FROM standing_event e "
                        "WHERE e.note_seq = s.note_seq) ORDER BY seq DESC LIMIT 1").fetchone()
    with pytest.raises(psycopg.errors.RaiseException, match="is not live"):  # also by a direct insert
        run(env, USE, (d, J, "finding", s.decider, s.sha256, s.approver, fresh[0], fresh[1]), role=DEC)


def test_a_system_first_event_closes_a_sample_with_no_verdict(env, dec, route):  # §8.4
    s = spec()
    d = signed_delegation(env, s, sample_every=2)
    _, root = note(env, "A root finding")
    notes.set_standing(env, root, "approved", curator=U, reason="checked")
    for i in range(6):  # derived notes: a rollback of the root retires them with system events
        note(env, f"Derived finding {i}", links=[{"type": "derived_from", "ref": root}])
    decider.run(dec, s, route.bridge())
    assert open_samples(env, d)
    notes.rollback(env, root, curator=U, reason="bad root")
    report = delegation.report(env, d)
    assert report["end"] is None and report["live_agreement"]["closed"] >= 1 and report["live_agreement"]["open"] == 0


# --- D5: expiry -----------------------------------------------------------------------------------------------------

def test_no_use_after_expiry(env, dec, route):  # D5
    s = spec()
    d = signed_delegation(env, s, expired=True, sample_every=100)
    seq, _ = note(env, "A finding after the expiry")
    out = decider.run(dec, s, route.bridge(), books=[J])
    assert out["uses"] == [] and len(out["suggestions"]) == 1
    sug = env.execute("SELECT seq FROM note_suggestion WHERE note_seq = %s", (seq,)).fetchone()[0]
    with pytest.raises(psycopg.errors.RaiseException, match="is not live"):
        run(env, USE, (d, J, "finding", s.decider, s.sha256, s.approver, seq, sug), role=DEC)
    assert delegation.list_(env)[0]["state"] == "expired"


# --- D7: readers and the report ---------------------------------------------------------------------------------------

def test_readers_see_the_approver_and_the_report_lists_every_use(env, dec, route):  # D7
    s = spec()
    d = signed_delegation(env, s, sample_every=100)
    for i in range(3):
        note(env, f"Reported finding {i}")
    _, human = note(env, "A finding a person approved")
    notes.set_standing(env, human, "approved", curator=U, reason="checked")
    out = decider.run(dec, s, route.bridge())
    reader = Actor(A, U, channel="mcp")
    items = {i["ref"]: i for i in notesquery.query_notes(env, reader, for_model=True, book=[J])["items"]}
    assert items[human]["approved_by"] == U
    delegated = [u["ref"] for u in out["uses"] if not u["sampled"]]
    assert delegated and all(items[r]["approved_by"] == s.approver for r in delegated)
    near = notesquery.neighbours(env, reader, for_model=True, ref=delegated[0])
    assert near["root"]["approved_by"] == s.approver
    opened = notesquery.open_note(env, reader, for_model=True, ref=delegated[0])
    assert opened["note"]["approved_by"] == s.approver
    reason = env.execute("SELECT reason FROM standing_event WHERE set_by = %s LIMIT 1", (s.approver,)).fetchone()[0]
    assert reason == f"delegated: {d}"  # the approval reason names the delegation
    report = delegation.report(env, d)
    assert [u["ref"] for u in report["uses"]] == [u["ref"] for u in out["uses"]]
    for u in report["uses"]:
        assert u["correlation_id"] == out["correlation_id"] and u["model_call"]["route"] == "chat"
        assert u["model_call"]["call_id"].startswith(out["correlation_id"] + ".")
        assert u["model_call"]["derived_correlation_id"] == "d:" + u["model_call"]["call_id"]
    assert report["signed"]["principal"] == U and report["coverage"]["approved"] == len(delegated)


def test_a_delegated_approval_passes_the_026_retirement_trigger(env, dec, route):  # 025 × 026 (review #16)
    """A delegated approval has no cause: trigger standing_event_retires_signed lets it through. It retires nothing,
    also when the note supersedes an approved note, and curator web cannot hang a retirement on it (no act)."""
    assert env.execute("SELECT 1 FROM pg_trigger WHERE tgname = 'standing_event_retires_signed'").fetchone()
    s = spec()
    signed_delegation(env, s, sample_every=100)
    _, old = note(env, "The cache holds 10 entries")
    notes.set_standing(env, old, "approved", curator=U, reason="checked")
    new_seq, _ = note(env, "The cache holds 12 entries", links=[{"type": "supersedes", "ref": old}])
    decider.run(dec, s, route.bridge())
    event = env.execute("SELECT seq, value, set_by FROM standing_event WHERE note_seq = %s", (new_seq,)).fetchone()
    if event is None:  # the 1-in-100 sample: no event to check
        pytest.skip("the database drew a sample")
    assert event[1:] == ("approved", s.approver)
    old_seq = env.execute("SELECT seq FROM note WHERE book || '@' || id = %s", (old,)).fetchone()[0]
    assert env.execute("SELECT value FROM standing_event WHERE note_seq = %s ORDER BY seq DESC LIMIT 1",
                       (old_seq,)).fetchone()[0] == "approved"  # nothing retired
    with pytest.raises(psycopg.errors.InsufficientPrivilege):  # RLS: a retirement needs a signed act's cause
        run(env, "INSERT INTO standing_event (note_seq, value, set_by, reason, correlation_id, cause_seq) "
                 "VALUES (%s, 'retired', 'system', 'x', 'c', %s)", (old_seq, event[0]), role=WEB)


# --- D9: the end by a curator, and the creator's right --------------------------------------------------------------

def test_a_curator_ends_a_delegation_by_act_or_cli_and_retires_its_approvals(env, dec, route, client, monkeypatch,
                                                                              capsys):  # D9
    s = spec()
    auth = ready(env, client)
    monkeypatch.setenv(delegation.MIN_SHADOW_ENV, "1")  # the shadow rule is under test in D1
    shadow_decisions(env, s, 1)
    r = sign(client, auth, {**delegate_body(s, sample_every=100)})
    assert r.status_code == 200, r.text
    by_act = r.json()["delegation"]
    for i in range(3):
        note(env, f"Approved by the delegation {i}")
    decider.run(dec, s, route.bridge())
    approved = [r for r in delegation.review_list(env, by_act) if r["retirable"]]
    assert approved
    r = sign(client, auth, {"action": "end_delegation", "delegation": by_act, "reason": "enough"})
    assert r.status_code == 200, r.text
    assert env.execute("SELECT cause, ended_by, act IS NOT NULL FROM delegation_end WHERE delegation = %s",
                       (by_act,)).fetchone() == ("revoked", U, True)
    assert sign(client, auth, {"action": "end_delegation", "delegation": by_act, "reason": "again"}).status_code == 400
    assert passkey.verify_acts(env, CFG)["problems"] == []
    view = client.get(f"/api/delegations/{by_act}").json()
    assert [i["ref"] for i in view["review"]] == [i["ref"] for i in approved]
    retire = sign(client, auth, {"action": "standing", "reason": "the delegation ended",
                                 "items": [{"ref": i["ref"], "to": "retired"} for i in view["review"]]})
    assert retire.status_code == 200, retire.text
    assert all(not i["retirable"] for i in delegation.review_list(env, by_act))
    listed = client.get("/api/delegations").json()
    assert [x["id"] for x in listed["delegations"]] == [by_act] and listed["books"] == [J]

    by_cli = signed_delegation(env, s, sample_every=100)
    monkeypatch.setenv("KUTUPHANE_CURATOR_DSN", os.environ["KUTUPHANE_TEST_DSN"])
    assert cli.main(["delegation", "end", by_cli, "--curator", M, "--reason", "no"]) == 3  # no curate
    assert cli.main(["delegation", "end", by_cli, "--curator", U, "--reason", "enough"]) == 0
    capsys.readouterr()
    assert env.execute("SELECT cause, ended_by, act FROM delegation_end WHERE delegation = %s",
                       (by_cli,)).fetchone() == ("revoked", U, None)
    note(env, "After both ends")
    assert decider.run(dec, s, route.bridge())["uses"] == []

    lost = signed_delegation(env, s, sample_every=100)
    authz.revoke(env, f"book:{J}", "curate", U)
    out = decider.run(dec, s, route.bridge())
    assert out["uses"] == [] and out["stopped"] == [{"delegation": lost,
                                                     "reason": f"{U} no longer holds curate on book:{J}"}]
    assert cli.main(["delegation", "list"]) == 0
    states = {x["id"]: x["state"] for x in json.loads(capsys.readouterr().out)}
    assert states == {by_act: "ended:revoked", by_cli: "ended:revoked", lost: "live"}
    assert cli.main(["delegation", "report", lost]) == 0
    assert json.loads(capsys.readouterr().out)["delegation"]["id"] == lost


# --- M1: the upgrade --------------------------------------------------------------------------------------------------

def test_025_applies_over_notes_and_cli_events(conn):  # M1
    conn.execute("DROP SCHEMA public CASCADE")
    conn.execute("CREATE SCHEMA public")
    conn.execute("CREATE TABLE schema_migration (name text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())")
    for script in sorted((f for f in files("kutuphane.migrations").iterdir() if f.name.endswith(".sql")),
                         key=lambda f: f.name):
        if script.name >= "025" and script.name not in WRITE_PATH_COLUMNS:
            continue
        conn.execute(script.read_text())
        conn.execute("INSERT INTO schema_migration (name) VALUES (%s)", (script.name,))
    notes.create_journal(conn, book=J, title=J, search=True, ai_input=True, policy=LOCAL, by="user:admin")
    for mode in ("read", "propose", "curate"):
        authz.grant(conn, f"book:{J}", mode, U)
    r = notes.propose(conn, Actor(U, channel="http"), {"book": J, "kind": "finding", "text": "An old finding"})[0]
    notes.set_standing(conn, r["ref"], "approved", curator=U, reason="checked")
    applied = db.migrate(conn)
    assert applied[0] == "025_curate_delegation.sql"
    assert conn.execute("SELECT set_by, act, delegation_use, delegated FROM standing_event").fetchall() == [
        (U, None, None, None)]
    apply_roles(conn)
    try:
        assert run(conn, "SELECT count(*) FROM standing_event", role=APP)[0] == 1
        assert run(conn, "SELECT count(*) FROM note", role=APP)[0] == 1
    finally:
        drop_roles(conn)
