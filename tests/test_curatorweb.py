"""Curator web and the passkey act (docs/25 §3, §5, §6.5; slice P): C1–C14 and the static part of T-DEP.

A software authenticator (tests/softauthn.py) makes real registrations and assertions; the server runs the real
`py_webauthn` checks. Curator web connects as the curator web role with the deploy grants (deploy/db-roles*.sql), as
in a deployment; the test itself writes as the owner (the CLI). The hostile inserts are in test_curation_db.py.
"""
import json
import os
import re
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from kutuphane import authz, canonical, cli, curation, curatorweb, notes, passkey
from kutuphane.gate import Actor
from kutuphane.policy import make_policy
from softauthn import SoftAuthenticator

RP = "kutuphane-curator.example.ts.net"
ORIGIN = f"https://{RP}"
H = {"Origin": ORIGIN}
U, M, A, J = "user:ayse", "user:mehmet", "agent:kobra-7", "hafiza"
LOCAL = make_policy(sensitivity="normal", egress="local_only", protection="standard")
CFG = passkey.Config(rp_id=RP, origin=ORIGIN)
DEPLOY = Path(__file__).parent.parent / "deploy"
WEB_ROLE, APP_ROLE = "kutuphane_curator_web_test", "kutuphane_app_test"


@pytest.fixture
def env(conn):
    for role in (APP_ROLE, WEB_ROLE):
        conn.execute(f"DO $$ BEGIN CREATE ROLE {role} NOLOGIN; EXCEPTION WHEN duplicate_object THEN NULL; END $$")
    conn.execute((DEPLOY / "db-roles.sql").read_text(encoding="utf-8").replace("kutuphane_app", APP_ROLE))
    conn.execute((DEPLOY / "db-roles-curator.sql").read_text(encoding="utf-8")
                 .replace("kutuphane_curator_web", WEB_ROLE).replace("kutuphane_app", APP_ROLE))
    notes.create_journal(conn, book=J, title=J, search=True, ai_input=True, policy=LOCAL, by="user:admin")
    for mode in ("read", "propose"):
        authz.grant(conn, f"book:{J}", mode, U)
        authz.delegate(conn, delegator=U, delegate_to=A, obj=f"book:{J}", mode=mode,
                       expires_at=datetime.now(timezone.utc) + timedelta(hours=1))
    authz.grant(conn, f"book:{J}", "curate", U)
    yield conn
    for role in (APP_ROLE, WEB_ROLE):
        conn.execute(f"DROP OWNED BY {role}")


def web_dsn() -> str:
    """The test database as the curator web role (`SET ROLE` at connection start, as a deployment's login role)."""
    dsn = os.environ["KUTUPHANE_TEST_DSN"]
    return dsn + ("&" if "?" in dsn else "?") + f"options=-crole%3D{WEB_ROLE}"


@pytest.fixture
def client(env):
    with TestClient(curatorweb.create_app(dsn=web_dsn(), cfg=CFG), base_url=ORIGIN) as c:
        yield c


def note(conn, text, kind="finding", **kw) -> str:
    r = notes.propose(conn, Actor(A, U, channel="mcp"), {"book": J, "kind": kind, "text": text, **kw})[0]
    conn.commit()
    return r["ref"]


def enroll(conn, client, auth, principal=U, **create_kw):
    _, code = passkey.enroll(conn, principal, created_by="user:admin")
    conn.commit()
    assert client.post("/api/enroll/session", json={"code": code}, headers=H).status_code == 200
    o = client.post("/api/enroll/options", json={}, headers=H).json()
    return client.post("/api/enroll", json={"challenge_id": o["challenge_id"],
                                            "credential": auth.create(o["publicKey"], **create_kw)}, headers=H)


def login(client, auth, **get_kw):
    o = client.post("/auth/passkey/options", json={}, headers=H).json()
    return client.post("/auth/passkey", json={"challenge_id": o["challenge_id"],
                                              "credential": auth.get(o["publicKey"], **get_kw)}, headers=H)


def options(client, items, reason="checked"):
    r = client.post("/api/act/options", json={"action": "standing", "items": items, "reason": reason}, headers=H)
    assert r.status_code == 200, r.text
    return r.json()


def submit(client, o, cred, shown_ms=1200):
    return client.post("/api/act", json={"challenge_id": o["challenge_id"], "credential": cred,
                                         "shown_ms": shown_ms}, headers=H)


def act(client, auth, items, reason="checked", **get_kw):
    o = options(client, items, reason)
    return submit(client, o, auth.get(o["publicKey"], **get_kw))


def ready(env, client, **auth_kw):
    auth = SoftAuthenticator(ORIGIN, **auth_kw)
    assert enroll(env, client, auth).status_code == 200
    assert login(client, auth).status_code == 200
    return auth


def events(conn):
    return conn.execute("SELECT note_seq, value, set_by, act FROM standing_event ORDER BY seq").fetchall()


def queued(client):
    """Every member of every group of the first queue page (docs/25 §6)."""
    return [m for g in client.get("/api/queue").json()["groups"] for m in g["members"]]


# --- C1, C2: enrollment, login, one approval ---------------------------------------------------------------------

def test_enroll_login_and_approve_one_note_with_user_verification(env, client):  # C1, C2
    ref = note(env, "Retry loop in run.py hides timeouts")
    auth = ready(env, client)
    assert client.get("/api/me").json() == {"principal": U}
    pending = queued(client)
    assert [i["ref"] for i in pending] == [ref] and pending[0]["text"] == "Retry loop in run.py hides timeouts"
    o = options(client, [{"ref": ref, "to": "approved"}])
    assert o["statement"]["items"] == [{"ref": ref, "id": ref.split("@")[1], "was": None, "to": "approved"}]
    assert o["publicKey"]["userVerification"] == "required" and o["publicKey"]["rpId"] == RP
    r = submit(client, o, auth.get(o["publicKey"]))
    assert r.status_code == 200, r.text
    (seq, value, set_by, act_seq), = events(env)
    assert (value, set_by) == ("approved", U) and act_seq == r.json()["act"]
    row = env.execute("SELECT backup_state, shown_ms FROM curator_act WHERE seq = %s", (act_seq,)).fetchone()
    assert row == (True, 1200)  # a synced passkey (D72 default Q3) is recorded with each act
    assert queued(client) == []
    assert notes.effective_standing(env, [seq], notes.NOW)[seq][0] == "approved"


def test_enrollment_refusals(env, client):  # C1
    auth = SoftAuthenticator(ORIGIN)
    _, code = passkey.enroll(env, U, created_by="user:admin")
    env.commit()
    assert client.post("/api/enroll/session", json={"code": "x" + code}, headers=H).status_code == 403
    assert client.post("/api/enroll/session", json={"code": code}, headers=H).status_code == 200
    for bad in ({"uv": False}, {"origin": "https://spark.example.ts.net"}, {"cross_origin": True},
                {"top_origin": "https://evil.example"}, {"kind": "webauthn.get"}, {"rp_id": "example.ts.net"}):
        o = client.post("/api/enroll/options", json={}, headers=H).json()
        r = client.post("/api/enroll", json={"challenge_id": o["challenge_id"],
                                             "credential": auth.create(o["publicKey"], **bad)}, headers=H)
        assert r.status_code == 403, bad
    assert env.execute("SELECT count(*) FROM passkey").fetchone()[0] == 0
    o = client.post("/api/enroll/options", json={}, headers=H).json()
    assert client.post("/api/enroll", json={"challenge_id": o["challenge_id"],
                                            "credential": auth.create(o["publicKey"])}, headers=H).status_code == 200
    # the code is used: no second session, no second passkey
    assert client.post("/api/enroll/session", json={"code": code}, headers=H).status_code == 403
    _, late = passkey.enroll(env, U, created_by="user:admin")
    env.execute("UPDATE curator_enrollment SET created_at = created_at - interval '1 hour', "
                "expires_at = expires_at - interval '1 hour' WHERE code_sha256 = %s", (passkey.digest(late),))
    env.commit()
    assert client.post("/api/enroll/session", json={"code": late}, headers=H).status_code == 403
    # an enrollment session may only register
    assert client.get("/api/queue").status_code == 401


def test_login_needs_user_verification_and_the_person_handle(env, client):  # C6, C11
    auth = SoftAuthenticator(ORIGIN)
    assert enroll(env, client, auth).status_code == 200
    for kw, reason in (({"uv": False}, "user-verification-missing"),
                       ({"user_handle": False}, "does not name this person"),
                       ({"user_handle": secrets.token_bytes(32)}, "does not name this person"),
                       ({"top_origin": "https://evil.example"}, "cross-origin or framed")):
        r = login(client, auth, **kw)
        assert r.status_code == 403 and reason in r.json()["error"], (kw, r.text)
    assert env.execute("SELECT count(*) FROM curator_session WHERE login = 'passkey'").fetchone()[0] == 0
    r = login(client, auth)
    assert r.status_code == 200
    cookie = r.headers["set-cookie"]
    assert cookie.startswith("__Host-kc=") and "domain" not in cookie.lower()
    for attr in ("Secure", "HttpOnly", "SameSite=strict", "Path=/"):
        assert attr.lower() in cookie.lower(), attr


def test_a_post_needs_this_origin_and_json(env, client):  # C11
    ready(env, client)
    assert client.post("/api/act/options", json={"action": "standing"}).status_code == 403
    assert client.post("/api/act/options", json={"action": "standing"},
                       headers={"Origin": "https://spark.example.ts.net"}).status_code == 403
    assert client.post("/api/act/options", content=b"action=standing",
                       headers={**H, "content-type": "application/x-www-form-urlencoded"}).status_code == 415


# --- C3–C8: replay, binding, origin, UV, counter, rights ----------------------------------------------------------

def test_replay_expiry_and_session_binding(env, client):  # C3
    ref = note(env, "a finding")
    auth = ready(env, client)
    o = options(client, [{"ref": ref, "to": "approved"}])
    cred = auth.get(o["publicKey"])
    assert submit(client, o, cred).status_code == 200
    r = submit(client, o, cred)
    assert r.status_code == 403 and "used" in r.json()["error"]  # the challenge is used
    ref2 = note(env, "another finding")
    o2 = options(client, [{"ref": ref2, "to": "approved"}])
    env.execute("UPDATE curator_challenge SET created_at = created_at - interval '10 minutes', "
                "expires_at = expires_at - interval '10 minutes' WHERE id = %s", (o2["challenge_id"],))
    env.commit()
    r = submit(client, o2, auth.get(o2["publicKey"]))
    assert r.status_code == 403 and "expired" in r.json()["error"]
    o3 = options(client, [{"ref": ref2, "to": "approved"}])
    with TestClient(curatorweb.create_app(dsn=web_dsn(), cfg=CFG), base_url=ORIGIN) as other:
        assert login(other, auth).status_code == 200  # the same person, another session
        r = submit(other, o3, auth.get(o3["publicKey"]))
        assert r.status_code == 403 and "another session" in r.json()["error"]
    assert len(events(env)) == 1


def test_the_assertion_is_bound_to_the_exact_statement(env, client):  # C4
    a, b = note(env, "finding a"), note(env, "finding b")
    auth = ready(env, client)
    oa, ob = options(client, [{"ref": a, "to": "approved"}]), options(client, [{"ref": b, "to": "rejected"}])
    assert submit(client, ob, auth.get(oa["publicKey"])).status_code == 403  # signed A, sent as B
    env.execute("UPDATE curator_challenge SET payload = jsonb_set(payload, '{reason}', '\"checked!\"') WHERE id = %s",
                (oa["challenge_id"],))
    env.commit()
    assert submit(client, oa, auth.get(oa["publicKey"])).status_code == 403  # one changed byte of the statement
    assert events(env) == []


@pytest.mark.parametrize("bad, reason", [({"origin": "https://spark.example.ts.net"}, "wrong origin"),
                                         ({"origin": f"http://{RP}"}, "wrong origin"),
                                         ({"origin": f"{ORIGIN}:8443"}, "wrong origin"),
                                         ({"cross_origin": True}, "cross-origin or framed"),
                                         ({"top_origin": "https://evil.example"}, "cross-origin or framed"),
                                         ({"rp_id": "example.ts.net"}, "wrong RP ID"),
                                         ({"kind": "webauthn.create"}, "wrong ceremony type")])
def test_origin_and_ceremony_checks_on_an_act(env, client, bad, reason):  # C5
    ref = note(env, "a finding")
    auth = ready(env, client)
    r = act(client, auth, [{"ref": ref, "to": "approved"}], **bad)
    assert r.status_code == 403 and reason in r.json()["error"], r.text
    assert events(env) == []


def test_an_act_without_user_verification_is_refused(env, client):  # C6
    ref = note(env, "a finding")
    auth = ready(env, client)
    r = act(client, auth, [{"ref": ref, "to": "approved"}], uv=False)
    assert r.status_code == 403 and "user-verification-missing" in r.text
    assert events(env) == []


def test_the_counter_must_increase_over_logins_and_acts(env, client):  # C7
    a, b = note(env, "finding a"), note(env, "finding b")
    auth = ready(env, client, synced=False, counter_step=1)  # login: counter 1
    assert act(client, auth, [{"ref": a, "to": "approved"}]).status_code == 200  # 2
    r = act(client, auth, [{"ref": b, "to": "approved"}], counter=2)
    assert r.status_code == 403 and "counter" in r.text
    assert env.execute("SELECT sign_count FROM passkey").fetchone()[0] == 2


def test_rights_and_standing_are_decided_again_at_the_act(env, client):  # C8
    a, b = note(env, "finding a"), note(env, "finding b")
    auth = ready(env, client)
    o = options(client, [{"ref": a, "to": "approved"}])
    notes.set_standing(env, a, "rejected", curator=U, reason="another curator, on the CLI")
    env.commit()
    r = submit(client, o, auth.get(o["publicKey"]))
    assert r.status_code == 409  # the Standing in force is not `was`
    o = options(client, [{"ref": b, "to": "approved"}])
    authz.revoke(env, f"book:{J}", "curate", U)
    env.commit()
    r = submit(client, o, auth.get(o["publicKey"]))
    assert r.status_code == 403
    assert [e[1] for e in events(env)] == ["rejected"]
    refusal = env.execute("SELECT allowed, reason FROM access_event WHERE action = 'curate' ORDER BY id DESC").fetchone()
    assert refusal[0] is False and "curate" in refusal[1]


def test_a_note_whose_parts_changed_is_refused(env, client):  # C14
    a, b = note(env, "finding a"), note(env, "finding b")
    auth = ready(env, client)
    seq_a, seq_b = (env.execute("SELECT seq FROM note WHERE id = %s", (r.split("@")[1],)).fetchone()[0] for r in (a, b))
    write = env.execute("SELECT seq FROM write_record WHERE note_seq = %s AND creates", (seq_b,)).fetchone()[0]
    # what an app-role writer could do before migration 039 (its trigger off, as then): add a creation link to a
    # stored note under its own creating write
    with env.transaction():
        env.execute("SET LOCAL session_replication_role = replica")
        env.execute("INSERT INTO note_link (src, src_book, type, dst_note, dst_note_book, creation, write_seq) "
                    "VALUES (%s, %s, 'about', %s, %s, true, %s)", (seq_b, J, seq_a, J, write))
    item = next(i for i in queued(client) if i["ref"] == b)
    assert item["integrity"] == "note-integrity"
    r = client.post("/api/act/options", json={"action": "standing", "items": [{"ref": b, "to": "approved"}],
                                              "reason": "x"}, headers=H)
    assert r.status_code == 403 and "note-integrity" in r.text
    assert canonical.canonical_of(env, seq_a)[0] == a.split("@")[1]


# --- curation.apply: the batch rules of §6.5 -----------------------------------------------------------------------

def test_batch_rules(env):  # §6.5 (also Q3 for the phone path)
    refs = [note(env, f"finding {i}") for i in range(51)]
    c1 = note(env, "convention one", kind="convention")
    c2 = note(env, "convention two", kind="convention")
    k1, k2 = note(env, "says yes"), note(env, "says no")
    notes.link(env, Actor(A, U, channel="mcp"), k1, "contradicts", k2)
    env.commit()

    def apply(items):
        with env.transaction():
            notes._lock(env)
            return curation.apply(env, principal=U, items=items, reason="batch")

    with pytest.raises(ValueError, match="1..50"):
        apply([{"ref": r, "to": "approved"} for r in refs])
    with pytest.raises(ValueError, match="one rule"):
        apply([{"ref": c1, "to": "approved"}, {"ref": c2, "to": "approved"}])
    with pytest.raises(ValueError, match="contradicts"):
        apply([{"ref": k1, "to": "approved"}, {"ref": k2, "to": "approved"}])
    out = apply([{"ref": c1, "to": "approved"}, {"ref": c2, "to": "rejected"}, {"ref": k1, "to": "approved"},
                 {"ref": k2, "to": "rejected"}])
    assert [o["standing"] for o in out] == ["approved", "rejected", "approved", "rejected"]
    assert len({e[0] for e in events(env)}) == 4
    for value in ("approved", "retired", "pending"):
        apply([{"ref": refs[0], "to": value}])
    with pytest.raises(ValueError, match="D68"):
        apply([{"ref": refs[0], "to": "rejected"}])


# --- C10, C12, C13, T-DEP ---------------------------------------------------------------------------------------

def test_the_curator_web_route_snapshot(client):  # C10
    paths = sorted({r.path for r in client.app.routes if hasattr(r, "path")})
    assert paths == ["/", "/api/act", "/api/act/options", "/api/delegations", "/api/delegations/{id}", "/api/enroll",
                     "/api/enroll/options", "/api/enroll/session", "/api/me", "/api/note/{book}/{id}", "/api/queue",
                     "/api/requests", "/api/requests/{book}/{id}", "/auth/logout", "/auth/passkey",
                     "/auth/passkey/options", "/c/{book}/{id}", "/enroll", "/requests", "/static"]


def test_verify_acts_finds_a_bad_signature_and_a_missing_effect(env, client):  # C12
    a, b = note(env, "finding a"), note(env, "finding b")
    auth = ready(env, client)
    first = act(client, auth, [{"ref": a, "to": "approved"}]).json()["act"]
    second = act(client, auth, [{"ref": b, "to": "approved"}]).json()["act"]
    assert passkey.verify_acts(env, CFG) == {"acts": 2, "problems": []}
    env.execute("UPDATE curator_act SET signature = %s WHERE seq = %s", (b"\x30\x00", first))
    env.execute("DELETE FROM standing_event WHERE act = %s", (second,))
    problems = passkey.verify_acts(env, CFG)["problems"]
    assert {(p["act"], p["problem"]) for p in problems} == {(first, "signature"), (second, "effects")}


def test_cli_enroll_prints_a_one_time_url_and_note_standing_writes_no_act(env, monkeypatch, capsys):  # C13
    monkeypatch.setenv("KUTUPHANE_CURATOR_DSN", os.environ["KUTUPHANE_TEST_DSN"])
    monkeypatch.setenv("KUTUPHANE_WEBAUTHN_RP_ID", RP)
    monkeypatch.setenv("KUTUPHANE_WEBAUTHN_ORIGIN", ORIGIN)
    assert cli.main(["curator", "enroll", U]) == 0
    out = json.loads(capsys.readouterr().out)
    assert re.fullmatch(re.escape(ORIGIN) + r"/enroll#[A-Za-z0-9_-]{22,}", out["url"]) and out["principal"] == U
    ref = note(env, "a finding")
    assert cli.main(["note", "standing", ref, "approved", "--curator", U, "--reason", "cli"]) == 0
    capsys.readouterr()
    assert [e[3] for e in events(env)] == [None]
    assert cli.main(["curator", "passkeys"]) == 0
    assert json.loads(capsys.readouterr().out) == []


def test_the_sidecar_serves_443_only_and_never_funnel():  # T-DEP (static part; the live check is deploy/curator_probe.py)
    serve = json.loads((Path(__file__).parent.parent / "deploy" / "tailscale" / "serve.json").read_text())
    assert set(serve["TCP"]) == {"443"} and serve["TCP"]["443"] == {"HTTPS": True}
    assert "AllowFunnel" not in serve
    (handlers,) = [v["Handlers"] for v in serve["Web"].values()]
    assert handlers == {"/": {"Proxy": "http://curator:8090"}}
