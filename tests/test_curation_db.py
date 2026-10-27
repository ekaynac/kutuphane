"""docs/25 §4.1, §4.5, §12.1 (slice P): the database rules of migration 023 and the role grants, as hostile inserts.

Each probe runs as the role that would try it in a deployment: the app role (Core, every process an agent can reach),
the curator web role, or the owner (the CLI). A refused probe must be refused by the rule named in its test.
"""
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path

import psycopg
import pytest
from psycopg.types.json import Jsonb

from kutuphane import authz, notes
from kutuphane.gate import Actor
from kutuphane.policy import make_policy

DEPLOY = Path(__file__).parent.parent / "deploy"
APP, WEB = "kutuphane_app_test", "kutuphane_curator_web_test"
U, M, A, J = "user:ayse", "user:mehmet", "agent:kobra-7", "hafiza"
LOCAL = make_policy(sensitivity="normal", egress="local_only", protection="standard")


@pytest.fixture
def db(conn):
    for role in (APP, WEB):
        conn.execute(f"DO $$ BEGIN CREATE ROLE {role} NOLOGIN; EXCEPTION WHEN duplicate_object THEN NULL; END $$")
    conn.execute((DEPLOY / "db-roles.sql").read_text(encoding="utf-8").replace("kutuphane_app", APP))
    conn.execute((DEPLOY / "db-roles-curator.sql").read_text(encoding="utf-8")
                 .replace("kutuphane_curator_web", WEB).replace("kutuphane_app", APP))
    notes.create_journal(conn, book=J, title=J, search=True, ai_input=True, policy=LOCAL, by="user:admin")
    for mode in ("read", "propose"):
        authz.grant(conn, f"book:{J}", mode, U)
        authz.delegate(conn, delegator=U, delegate_to=A, obj=f"book:{J}", mode=mode,
                       expires_at=datetime.now(timezone.utc) + timedelta(hours=1))
    conn.commit()
    conn.autocommit = True
    yield conn
    conn.execute("RESET ROLE")
    for role in (APP, WEB):
        conn.execute(f"DROP OWNED BY {role}")


def note(conn, text, kind="finding", **kw):
    r = notes.propose(conn, Actor(A, U, channel="mcp"), {"book": J, "kind": kind, "text": text, **kw})[0]
    return conn.execute("SELECT seq FROM note WHERE id = %s", (r["ref"].split("@")[1],)).fetchone()[0], r["ref"]


def run(conn, sql, params=(), *, role=None):
    """Execute in its own transaction as `role`; return the row or raise the database error."""
    with conn.transaction():
        if role:
            conn.execute(f"SET LOCAL ROLE {role}")
        cur = conn.execute(sql, params)
        return cur.fetchone() if cur.description else None


def refused(conn, sql, params=(), *, role=None, error=psycopg.Error, match=None):
    with pytest.raises(error, match=match):
        run(conn, sql, params, role=role)


PERSON = "INSERT INTO curator_person VALUES (%s, %s)"
ENROLL = ("INSERT INTO curator_enrollment (id, principal, code_sha256, created_by, created_at, expires_at) "
          "VALUES (%s, %s, %s, 'user:admin', clock_timestamp() + %s::interval, clock_timestamp() + %s::interval)")
PASSKEY = ("INSERT INTO passkey (credential_id, principal, user_handle, enrollment, public_key, sign_count, "
           "backup_eligible) VALUES (%s, %s, %s, %s, 'k', 0, true)")
SESSION = ("INSERT INTO curator_session (id_sha256, principal, login, login_challenge, expires_at, enrollment, "
           "credential_id) SELECT v.i, v.p, v.l, v.c, now() + v.t, "   # 026: the session's enrollment or passkey
           "CASE WHEN v.l = 'enrollment' THEN (SELECT id FROM curator_enrollment WHERE principal = v.p LIMIT 1) END, "
           "CASE WHEN v.l = 'passkey' THEN (SELECT credential_id FROM passkey WHERE principal = v.p LIMIT 1) END "
           "FROM (VALUES (%s::bytea, %s::text, %s::text, %s::text, %s::interval)) v (i, p, l, c, t)")
CHALLENGE = ("INSERT INTO curator_challenge (id, session, principal, action, payload, challenge, expires_at) "
             "VALUES (%s, %s, %s, %s, %s, %s, now() + %s::interval)")
ACT = ("INSERT INTO curator_act (challenge, principal, action, credential_id, authenticator_data, client_data_json, "
       "signature, backup_state) VALUES (%s, %s, %s, %s, 'ad', 'cd', 'sig', true) RETURNING seq")
EVENT = ("INSERT INTO standing_event (note_seq, value, set_by, reason, correlation_id, act, cause_seq) "
         "VALUES (%s, %s, %s, %s, 'c', %s, %s) RETURNING seq")


def enrollment(conn, principal, start="0 minutes", end="15 minutes"):
    eid = "en_" + secrets.token_hex(16)
    run(conn, ENROLL, (eid, principal, secrets.token_bytes(32), start, end))
    return eid


def challenge(conn, session, principal, action, payload, ttl="5 minutes", role=None):
    cid = "ch_" + secrets.token_hex(16)
    run(conn, CHALLENGE, (cid, session, principal, action, Jsonb(payload), secrets.token_bytes(32), ttl), role=role)
    return cid


@pytest.fixture
def people(db):
    hu, hm = secrets.token_bytes(32), secrets.token_bytes(32)
    run(db, PERSON, (U, hu))
    run(db, PERSON, (M, hm))
    eu, em = enrollment(db, U), enrollment(db, M)
    run(db, PASSKEY, (b"u" * 16, U, hu, eu), role=WEB)
    run(db, PASSKEY, (b"m" * 16, M, hm, em), role=WEB)
    su, sm = secrets.token_bytes(32), secrets.token_bytes(32)
    run(db, SESSION, (su, U, "enrollment", None, "1 hour"), role=WEB)
    run(db, SESSION, (sm, M, "enrollment", None, "1 hour"), role=WEB)
    return {"handles": (hu, hm), "sessions": (su, sm)}


def test_only_the_owner_makes_people_and_enrollments(db):
    refused(db, PERSON, (U, secrets.token_bytes(32)), role=WEB, error=psycopg.errors.InsufficientPrivilege)
    run(db, PERSON, (U, secrets.token_bytes(32)))
    refused(db, ENROLL, ("en_" + secrets.token_hex(16), U, secrets.token_bytes(32), "0 minutes", "1 minute"),
            role=WEB, error=psycopg.errors.InsufficientPrivilege)
    refused(db, ENROLL, ("en_" + secrets.token_hex(16), U, secrets.token_bytes(32), "0 minutes", "2 hours"),
            error=psycopg.errors.CheckViolation)


def test_a_passkey_needs_a_live_unused_enrollment_of_its_own_person(db):
    hu, hm = secrets.token_bytes(32), secrets.token_bytes(32)
    run(db, PERSON, (U, hu))
    run(db, PERSON, (M, hm))
    eu, old = enrollment(db, U), enrollment(db, U, start="-2 hours", end="-105 minutes")
    refused(db, PASSKEY, (b"a" * 16, M, hm, eu), role=WEB, error=psycopg.errors.ForeignKeyViolation)
    refused(db, PASSKEY, (b"a" * 16, U, hm, eu), role=WEB, error=psycopg.errors.ForeignKeyViolation)
    refused(db, PASSKEY, (b"a" * 16, U, hu, old), role=WEB, match="is not live")
    run(db, PASSKEY, (b"a" * 16, U, hu, eu), role=WEB)
    refused(db, PASSKEY, (b"b" * 16, U, hu, eu), role=WEB, error=psycopg.errors.UniqueViolation)
    refused(db, PASSKEY, (b"c" * 16, U, hu, enrollment(db, U)), role=APP, error=psycopg.errors.InsufficientPrivilege)
    run(db, "UPDATE passkey SET sign_count = 7 WHERE credential_id = %s", (b"a" * 16,), role=WEB)
    refused(db, "UPDATE passkey SET revoked_at = NULL", role=WEB, error=psycopg.errors.InsufficientPrivilege)


def test_the_app_role_cannot_touch_curation_tables(db, people):
    for table in ("curator_person", "curator_enrollment", "curator_session", "curator_challenge"):
        refused(db, f"SELECT * FROM {table}", role=APP, error=psycopg.errors.InsufficientPrivilege)
    refused(db, SESSION, (secrets.token_bytes(32), U, "enrollment", None, "1 hour"), role=APP,
            error=psycopg.errors.InsufficientPrivilege)
    assert run(db, "SELECT count(*) FROM passkey", role=APP)[0] == 2  # it may see which credentials exist
    assert run(db, "SELECT count(*) FROM standing_event", role=APP)[0] == 0  # RLS keeps reads open


def test_sessions_and_challenges_are_bounded_and_bound(db, people):
    su, sm = people["sessions"]
    refused(db, SESSION, (secrets.token_bytes(32), U, "enrollment", None, "9 hours"), role=WEB,
            error=psycopg.errors.CheckViolation)
    refused(db, CHALLENGE, ("ch_" + secrets.token_hex(16), su, M, "standing", Jsonb({}), secrets.token_bytes(32),
                            "1 minute"), role=WEB, error=psycopg.errors.ForeignKeyViolation)
    refused(db, CHALLENGE, ("ch_" + secrets.token_hex(16), su, U, "standing", Jsonb({}), secrets.token_bytes(32),
                            "6 minutes"), role=WEB, error=psycopg.errors.CheckViolation)
    login = challenge(db, None, None, "login", {}, ttl="2 minutes", role=WEB)
    other = challenge(db, sm, M, "standing", {"items": []})
    refused(db, SESSION, (secrets.token_bytes(32), U, "passkey", other, "8 hours"), role=WEB,
            error=psycopg.errors.ForeignKeyViolation)
    run(db, SESSION, (secrets.token_bytes(32), U, "passkey", login, "8 hours"), role=WEB)
    refused(db, SESSION, (secrets.token_bytes(32), U, "passkey", login, "8 hours"), role=WEB,
            error=psycopg.errors.UniqueViolation)
    run(db, "UPDATE curator_session SET ended_at = now() WHERE id_sha256 = %s", (sm,), role=WEB)
    for login_, column in (("passkey", "login_challenge, credential_id"), ("enrollment", "login_challenge, enrollment")):
        refused(db, f"INSERT INTO curator_session (id_sha256, principal, login, {column}, expires_at) "  # 026
                    "VALUES (%s, %s, %s, NULL, NULL, now() + interval '1 hour')", (secrets.token_bytes(32), U, login_),
                role=WEB, error=psycopg.errors.CheckViolation)


def test_an_act_is_one_use_of_its_own_challenge_by_its_own_passkey(db, people):
    su, _ = people["sessions"]
    c1 = challenge(db, su, U, "standing", {"items": [], "reason": "r"})
    refused(db, ACT, (c1, U, "standing", b"m" * 16), role=WEB, error=psycopg.errors.ForeignKeyViolation)
    refused(db, ACT, (c1, U, "confirm", b"u" * 16), role=WEB, error=psycopg.errors.ForeignKeyViolation)
    run(db, ACT, (c1, U, "standing", b"u" * 16), role=WEB)
    refused(db, ACT, (c1, U, "standing", b"u" * 16), role=WEB, error=psycopg.errors.UniqueViolation)
    refused(db, ACT, (challenge(db, su, U, "standing", {}), U, "standing", b"u" * 16), role=APP,
            error=psycopg.errors.InsufficientPrivilege)
    refused(db, "UPDATE curator_act SET shown_ms = 9", role=WEB, error=psycopg.errors.InsufficientPrivilege)


def test_a_web_event_is_an_item_of_its_act_statement(db, people):
    su, _ = people["sessions"]
    n2, _ref2 = note(db, "plain finding")
    n3, ref3 = note(db, "a convention", kind="convention")
    c1 = challenge(db, su, U, "standing", {"items": [{"ref": ref3, "to": "approved"}], "reason": "checked"})
    act = run(db, ACT, (c1, U, "standing", b"u" * 16), role=WEB)[0]
    c2 = challenge(db, su, U, "confirm", {"items": [{"ref": ref3, "to": "approved"}], "reason": "checked"})
    confirm = run(db, ACT, (c2, U, "confirm", b"u" * 16), role=WEB)[0]
    refused(db, EVENT, (n2, "approved", U, "r", None, None), role=WEB, match="row-level security")
    refused(db, EVENT, (n3, "approved", M, "checked", act, None), role=WEB, error=psycopg.errors.ForeignKeyViolation)
    refused(db, EVENT, (n3, "approved", U, "checked", confirm, None), role=WEB)  # not a standing act
    refused(db, EVENT, (n2, "approved", U, "checked", act, None), role=WEB, match="not in the statement")
    refused(db, EVENT, (n3, "rejected", U, "checked", act, None), role=WEB, match="not in the statement")
    refused(db, EVENT, (n3, "approved", U, "other", act, None), role=WEB, match="not in the statement")
    run(db, EVENT, (n3, "approved", U, "checked", act, None), role=WEB)
    refused(db, EVENT, (n3, "approved", U, "checked", act, None), role=WEB, error=psycopg.errors.UniqueViolation)


def test_web_system_events_are_only_the_supersession_of_its_approved_rule(db, people):
    su, _ = people["sessions"]
    n2, _ = note(db, "plain finding")
    n3, ref3 = note(db, "a convention", kind="convention")
    run(db, "INSERT INTO standing_event (note_seq, value, set_by, reason, correlation_id) "
            "VALUES (%s, 'approved', %s, 'cli', 'c')", (n3, U))
    cli = run(db, "INSERT INTO standing_event (note_seq, value, set_by, reason, correlation_id) "
                  "VALUES (%s, 'approved', %s, 'cli', 'c') RETURNING seq", (n2, U))[0]
    n9, ref9 = note(db, "a better convention", kind="convention", links=[{"type": "supersedes", "ref": ref3}])
    retires = [{"ref": ref3, "id": ref3.split("@")[1], "was": None}]
    c9 = challenge(db, su, U, "standing", {"items": [{"ref": ref9, "to": "approved"}], "reason": "better",
                                           "retires": retires})
    act9 = run(db, ACT, (c9, U, "standing", b"u" * 16), role=WEB)[0]
    with db.transaction():  # the act's own transaction (026: a signed retirement is written with its cause)
        db.execute(f"SET LOCAL ROLE {WEB}")
        ev9 = db.execute(EVENT, (n9, "approved", U, "better", act9, None)).fetchone()[0]
        for bad in ((n3, "approved", "system", "x", None, ev9), (n2, "retired", "system", "x", None, ev9),
                    (n3, "retired", "system", "x", None, cli)):
            with pytest.raises(psycopg.Error), db.transaction():
                db.execute(EVENT, bad)
        db.execute(EVENT, (n3, "retired", "system", "superseded", None, ev9))
    refused(db, EVENT, (n3, "retired", "system", "again", None, ev9), role=WEB, match="not a retirement signed")


def test_the_owner_path_is_unchanged(db):
    """The CLI (owner) writes events with no act; RLS does not apply to it (docs/24 §8.2 unchanged)."""
    n2, _ = note(db, "plain finding")
    run(db, "INSERT INTO standing_event (note_seq, value, set_by, reason, correlation_id) "
            "VALUES (%s, 'approved', %s, 'cli', 'c')", (n2, U))
    assert run(db, "SELECT act FROM standing_event")[0] is None
