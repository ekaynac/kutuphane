"""Security review #17 (docs/08): the regressions of findings 1–7 on curator slices R, D and Q.

The decider runner connects as the decider role and curator web as its role, with the deploy grants (deploy/db-roles*.sql),
as in a deployment; the owner (the test) only sets up the data.
"""
import json
import secrets

import psycopg
import pytest

from kutuphane import authz, curatorweb, decider, delegation, notes, passkey
from kutuphane.gate import Actor
from test_confirm import CONFIRM, _curator_url, _refused, _signed, act, person, propose, seq_of, shown  # noqa: F401
from test_curatorweb import H, ORIGIN, RP, web_dsn
from test_decider import (APP, DEC, J, M, MODEL, U, WEB, A, act_row, note, signed_delegation, spec, uses)
from test_decider import dec, env, route  # noqa: F401  (fixtures)

USE = ("INSERT INTO delegation_use (delegation, book, kind, decider, spec_sha256, approver, note_seq, suggestion, "
       "correlation_id) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'c') RETURNING sampled")
SUGGEST = ("INSERT INTO note_suggestion (note_seq, decider, spec_sha256, value, confidence, model_call) "
           "VALUES (%s, %s, %s, 'approved', 0.95, %s) RETURNING seq")


def model_call(conn) -> int:
    return conn.execute("INSERT INTO model_call (correlation_id, call_id, principal, route, model) "
                        "VALUES ('c', %s, %s, 'chat', %s) RETURNING id",
                        (f"c.{secrets.token_hex(6)}", decider.PRINCIPAL, MODEL)).fetchone()[0]


def suggested(conn, s, text) -> tuple[int, int]:
    """A note with a committed `approved` suggestion of `s` (as phase 1 writes it)."""
    seq, _ = note(conn, text)
    return seq, conn.execute(SUGGEST, (seq, s.decider, s.sha256, model_call(conn))).fetchone()[0]


def use_row(s, d, seq, suggestion) -> tuple:
    return (d, J, "finding", s.decider, s.sha256, s.approver, seq, suggestion)


def draw(conn, d, seq, every) -> bool:
    """The owner's view of the draw (the decider role cannot read the key)."""
    return conn.execute("SELECT ('x' || encode(substr(hmac(convert_to(%s || ':' || %s, 'UTF8'), key, 'sha256'), 1, 4), "
                        "'hex'))::bit(32)::bigint %% %s = 0 FROM delegation_sample_key", (d, seq, every)).fetchone()[0]


# --- #1: the database enforces the sample against the runner role ------------------------------------------------

def test_a_rollback_and_retry_gives_the_same_draw(env, dec):
    s = spec()
    d = signed_delegation(env, s, sample_every=2)
    seq, sug = suggested(env, s, "A finding the runner would like unsampled")
    draws = set()
    for _ in range(16):   # insert, read `sampled`, roll back, try again
        with dec.transaction(force_rollback=True):
            draws.add(dec.execute(USE, use_row(s, d, seq, sug)).fetchone()[0])
    assert len(draws) == 1                   # one draw per (delegation, note), whatever the retries
    assert draws == {draw(env, d, seq, 2)}   # the HMAC under the owner's key
    assert uses(env, d) == []


def test_a_cherry_picked_note_for_the_forced_sample_is_refused(env, dec):
    s = spec()
    d = signed_delegation(env, s, sample_every=2)
    first = suggested(env, s, "The oldest eligible finding")
    newer = suggested(env, s, "A newer finding")
    with pytest.raises(psycopg.errors.RaiseException, match="not the next note"):   # no skipping
        with dec.transaction():
            dec.execute(USE, use_row(s, d, *newer))
    unsampled, waiting = [], [first, newer]
    while len(unsampled) < 4:   # 2N = 4 unsampled uses, then the next use is a forced sample
        seq, sug = waiting.pop(0) if waiting else suggested(env, s, f"Finding {secrets.token_hex(4)}")
        if draw(env, d, seq, 2):
            ref = env.execute("SELECT book || '@' || id FROM note WHERE seq = %s", (seq,)).fetchone()[0]
            notes.set_standing(env, ref, "rejected", curator=U, reason="a person decides it: no longer eligible")
            continue
        unsampled.append((seq, sug))
    for seq, sug in unsampled:
        with dec.transaction():
            assert dec.execute(USE, use_row(s, d, seq, sug)).fetchone()[0] is False
    oldest = suggested(env, s, "The next note: it gets the forced sample")
    harmless = suggested(env, s, "A harmless note the runner wants to show the person")
    with pytest.raises(psycopg.errors.RaiseException, match="not the next note"):
        with dec.transaction():
            dec.execute(USE, use_row(s, d, *harmless))
    with dec.transaction():
        assert dec.execute(USE, use_row(s, d, *oldest)).fetchone()[0] is True   # forced, on the oldest note


def test_the_runner_role_cannot_set_seq_at_or_sampled(env, dec):
    s = spec()
    d = signed_delegation(env, s, sample_every=100)
    seq, sug = suggested(env, s, "A finding")
    other, _ = note(env, "Another finding")
    call = model_call(env)
    hostile = [
        ("INSERT INTO delegation_use (seq, delegation, book, kind, decider, spec_sha256, approver, note_seq, suggestion, "
         "correlation_id) VALUES (-1, %s, %s, %s, %s, %s, %s, %s, %s, 'c')", use_row(s, d, seq, sug)),
        ("INSERT INTO delegation_use (sampled, delegation, book, kind, decider, spec_sha256, approver, note_seq, "
         "suggestion, correlation_id) VALUES (false, %s, %s, %s, %s, %s, %s, %s, %s, 'c')", use_row(s, d, seq, sug)),
        ("INSERT INTO delegation_use (at, delegation, book, kind, decider, spec_sha256, approver, note_seq, suggestion, "
         "correlation_id) VALUES (now() - interval '1 day', %s, %s, %s, %s, %s, %s, %s, %s, 'c')",
         use_row(s, d, seq, sug)),
        ("INSERT INTO note_suggestion (seq, note_seq, decider, spec_sha256, value, confidence, model_call) "
         "VALUES (-2, %s, %s, %s, 'approved', 0.95, %s)", (other, s.decider, s.sha256, call)),
        ("INSERT INTO note_suggestion (at, note_seq, decider, spec_sha256, value, confidence, model_call) "
         "VALUES (now() - interval '1 day', %s, %s, %s, 'approved', 0.95, %s)", (other, s.decider, s.sha256, call)),
    ]
    for sql, params in hostile:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            with dec.transaction():
                dec.execute(sql, params)
    with dec.transaction():   # the columns it may set
        dec.execute(USE, use_row(s, d, seq, sug))
    assert uses(env, d)[0][0] > sug > 0


def test_a_fake_late_suggestion_is_no_shadow_evidence(env, dec):
    s = spec()
    seq, ref = note(env, "A finding a person approved first")
    notes.set_standing(env, ref, "approved", curator=U, reason="checked")
    call = model_call(env)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):   # a low seq to look earlier than the verdict
        with dec.transaction():
            dec.execute("INSERT INTO note_suggestion (seq, note_seq, decider, spec_sha256, value, confidence, "
                        "model_call) VALUES (1, %s, %s, %s, 'approved', 0.95, %s)", (seq, s.decider, s.sha256, call))
    with pytest.raises(psycopg.errors.RaiseException, match="has a Standing event"):   # any suggestion after it
        with dec.transaction():
            dec.execute(SUGGEST, (seq, s.decider, s.sha256, call))
    assert delegation.shadow_n(env, s.decider, s.sha256, J, "finding", 0.9) == 0


def test_a_use_needs_a_suggestion_committed_before_it(env, dec):
    s = spec()
    d = signed_delegation(env, s, sample_every=100)
    seq, _ = note(env, "A finding with no suggestion yet")
    call = model_call(env)
    for savepoint in (False, True):
        with pytest.raises(psycopg.errors.RaiseException, match="not committed before its use"):
            with dec.transaction():
                if savepoint:
                    with dec.transaction():   # a savepoint has its own xmin
                        sug = dec.execute(SUGGEST, (seq, s.decider, s.sha256, call)).fetchone()[0]
                else:
                    sug = dec.execute(SUGGEST, (seq, s.decider, s.sha256, call)).fetchone()[0]
                dec.execute(USE, use_row(s, d, seq, sug))
    with dec.transaction():
        sug = dec.execute(SUGGEST, (seq, s.decider, s.sha256, call)).fetchone()[0]
    with dec.transaction():
        dec.execute(USE, use_row(s, d, seq, sug))


def test_the_trigger_checks_the_creator_right_and_the_runner_authorship(env, dec):
    s = spec()
    d = signed_delegation(env, s, sample_every=100)
    authz.grant(env, f"book:{J}", "propose", decider.PRINCIPAL)
    own, _ = note(env, "A finding by the runner's own principal", actor=Actor(decider.PRINCIPAL, channel="mcp"))
    own_sug = env.execute(SUGGEST, (own, s.decider, s.sha256, model_call(env))).fetchone()[0]
    with pytest.raises(psycopg.errors.RaiseException, match="propose write by the runner's principal"):
        with dec.transaction():
            dec.execute(USE, use_row(s, d, own, own_sug))
    seq, sug = suggested(env, s, "A fresh finding")
    authz.revoke(env, f"book:{J}", "curate", U)
    with pytest.raises(psycopg.errors.RaiseException, match=f"{U} no longer holds curate on book:{J}"):
        with dec.transaction():
            dec.execute(USE, use_row(s, d, seq, sug))
    assert uses(env, d) == []


# --- #2: only the confirmer replaces a live confirmation -----------------------------------------------------------

def test_another_person_cannot_replace_a_live_confirmation(env):
    r = propose(env, "Ayşe's own words.")
    c, auth = person(env)
    assert act(c, auth, {"action": "confirm", "ref": r["ref"], "claim": "human"}).status_code == 200
    authz.grant(env, f"book:{J}", "read", M)
    authz.grant(env, f"book:{J}", "curate", M)
    env.commit()
    cm, am = person(env, M)
    page = cm.get(f"/api/requests/{r['ref'].replace('@', '/')}").json()
    assert page["claims"] == [] and page["withdraw"] is None   # nothing offered over Ayşe's confirmation
    refused = act(cm, am, {"action": "confirm", "ref": r["ref"], "claim": "assisted"})
    assert refused.status_code == 403 and "only that person withdraws it" in refused.json()["error"]
    assert shown(env, r["ref"]) == ("human", A, U)
    # the database refuses it too, for the curator web role
    seq, nid = seq_of(env, r["ref"]), r["ref"].split("@")[1]
    write = env.execute("SELECT seq FROM write_record WHERE note_seq = %s", (seq,)).fetchone()[0]
    by_m = _signed(env, M, "confirm", {"item": {"ref": r["ref"], "id": nid, "write": write}, "claim": "assisted",
                                       "entered_by": A})
    env.commit()
    _refused(env, CONFIRM, (seq, J, nid, write, "assisted", A, M, by_m), psycopg.errors.RaiseException, WEB)
    # after Ayşe withdraws, Mehmet may confirm
    assert act(c, auth, {"action": "withdraw", "ref": r["ref"]}).status_code == 200
    assert act(cm, am, {"action": "confirm", "ref": r["ref"], "claim": "assisted"}).status_code == 200
    assert shown(env, r["ref"]) == ("assisted", A, M)


def test_a_new_request_is_no_path_to_take_over_a_live_confirmation(env):
    text = "Words that Ayşe confirmed."
    r = propose(env, text)
    c, auth = person(env)
    assert act(c, auth, {"action": "confirm", "ref": r["ref"], "claim": "human"}).status_code == 200
    reader_agent = "agent:kobra-8"
    for mode in ("read", "propose"):
        authz.grant(env, f"book:{J}", mode, M)
        authz.delegate(env, delegator=M, delegate_to=reader_agent, obj=f"book:{J}", mode=mode,
                       expires_at=env.execute("SELECT now() + interval '1 hour'").fetchone()[0])
    env.commit()
    again = propose(env, text, actor=Actor(reader_agent, M, channel="mcp"))   # the same bytes, "human" for Mehmet
    assert again["ref"] == r["ref"] and again["origin_notice"] == "origin-claim-refused"
    cm, am = person(env, M)
    page = cm.get(f"/api/requests/{r['ref'].replace('@', '/')}").json()
    assert page["claims"] == []
    refused = act(cm, am, {"action": "confirm", "ref": r["ref"], "claim": "human"})
    assert refused.status_code == 403, refused.text
    assert shown(env, r["ref"]) == ("human", A, U)


# --- #3: the page and the act options check `read` before any lookup ---------------------------------------------

def test_a_person_without_read_gets_one_refusal_for_every_note_state(env):
    absent = f"{J}@nt_{'0' * 64}"
    plain = note(env, "A note with no request")[1]
    requested = propose(env, "A note with an open request")["ref"]
    confirmed = propose(env, "A note with a live confirmation")["ref"]
    c, auth = person(env)
    assert act(c, auth, {"action": "confirm", "ref": confirmed, "claim": "human"}).status_code == 200
    env.commit()
    cm, _ = person(env, M)   # enrolled, no right on the book
    seen = set()
    for ref in (absent, plain, requested, confirmed):
        for r in (cm.get(f"/api/requests/{ref.replace('@', '/')}"),
                  cm.post("/api/act/options", json={"action": "confirm", "ref": ref, "claim": "assisted"}, headers=H),
                  cm.post("/api/act/options", json={"action": "withdraw", "ref": ref}, headers=H)):
            seen.add((r.status_code, r.json()["error"]))
    assert seen == {(403, f"{M} does not hold read on book:{J}")}


# --- #4: the text gate again just before each model call ---------------------------------------------------------

def test_the_text_gate_is_checked_again_before_each_model_call(env, dec, route):
    s = spec()
    note(env, "The first finding")
    second, second_ref = note(env, "The second finding")
    original = route.server.RequestHandlerClass.do_POST

    def do_post(handler):   # while the model answers the first note, the second loses its ai_input
        env.execute("UPDATE note SET ai_input = false WHERE seq = %s", (second,))
        original(handler)
    route.server.RequestHandlerClass.do_POST = do_post
    out = decider.run(dec, s, route.bridge(), books=[J], shadow=True)
    sent = [json.loads(b["messages"][1]["content"])["text"] for _, b, _ in route.requests]
    assert sent == ["The first finding"] and out["closed_meanwhile"] == [second_ref]


# --- #5: the decider role reads note text only through the gate ---------------------------------------------------

def test_the_decider_role_reads_note_text_only_through_the_gate(env, dec):
    s = spec()
    open_seq, _ = note(env, "A note in a configured book")
    closed_seq, _ = note(env, "A note whose text may not go to a model")
    env.execute("UPDATE note SET ai_input = false WHERE seq = %s", (closed_seq,))
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        with dec.transaction():
            dec.execute("SELECT body FROM note LIMIT 1")
    for role in (DEC, WEB, APP):
        with pytest.raises(psycopg.errors.InsufficientPrivilege):   # the draw key: the owner's only
            with env.transaction():
                env.execute(f"SET LOCAL ROLE {role}")
                env.execute("SELECT key FROM delegation_sample_key")
    gated = "SELECT seq, body FROM decider_notes(%s, %s, %s, 8000, 100, NULL)"
    assert dec.execute(gated, ([J], s.decider, s.sha256)).fetchall() == [(open_seq, "A note in a configured book")]
    authz.revoke(env, f"book:{J}", "read", decider.PRINCIPAL)   # not configured and no live delegation: nothing
    assert dec.execute(gated, ([J], s.decider, s.sha256)).fetchall() == []
    signed_delegation(env, s)   # a live delegation in the book opens it again
    assert [r[0] for r in dec.execute(gated, ([J], s.decider, s.sha256)).fetchall()] == [open_seq]


# --- #6: an end by an act names that act --------------------------------------------------------------------------

def test_a_delegation_end_is_bound_to_its_end_delegation_act(env):
    s = spec()
    d = signed_delegation(env, s)
    standing_act = act_row(env, U, "standing", {"v": 1})
    end_act = act_row(env, U, "end_delegation", {"v": 1, "delegation": d})
    end = "INSERT INTO delegation_end (delegation, cause, ended_by, act) VALUES (%s, 'revoked', %s, %s)"
    _refused(env, end, (d, U, standing_act), psycopg.errors.ForeignKeyViolation, WEB)   # an act of another action
    _refused(env, end, (d, M, end_act), psycopg.errors.ForeignKeyViolation, WEB)        # another person's end
    with env.transaction():
        env.execute(f"SET LOCAL ROLE {WEB}")
        env.execute(end, (d, U, end_act))
    assert env.execute("SELECT act_action FROM delegation_end").fetchone()[0] == "end_delegation"


# --- #7: smaller gaps ---------------------------------------------------------------------------------------------

@pytest.mark.parametrize("value", ["0", "-5", "abc", "2.5"])
def test_a_bad_shadow_minimum_stops_curator_web_at_start(env, monkeypatch, value):
    monkeypatch.setenv(delegation.MIN_SHADOW_ENV, value)
    monkeypatch.setenv(curatorweb.DSN_ENV, web_dsn())
    monkeypatch.setenv("KUTUPHANE_WEBAUTHN_RP_ID", RP)
    monkeypatch.setenv("KUTUPHANE_WEBAUTHN_ORIGIN", ORIGIN)
    with pytest.raises(RuntimeError, match=delegation.MIN_SHADOW_ENV):
        delegation.min_shadow()
    with pytest.raises(RuntimeError, match=delegation.MIN_SHADOW_ENV):
        curatorweb.app_from_env()
    monkeypatch.setenv(delegation.MIN_SHADOW_ENV, "")
    assert delegation.min_shadow() == delegation.MIN_SHADOW_DEFAULT
    assert curatorweb.app_from_env() is not None


def test_a_change_to_the_prompt_code_changes_the_spec(monkeypatch):
    before = spec()
    original = decider._messages

    def _messages(s, row):   # one more sentence in the system prompt
        out = original(s, row)
        out[0]["content"] += " Be brief."
        return out
    monkeypatch.setattr(decider, "_messages", _messages)
    after = spec()
    assert after.doc == before.doc and after.sha256 != before.sha256
    monkeypatch.setattr(decider, "_messages", original)
    assert spec().sha256 == before.sha256
