"""Security review #16 (docs/08): the regressions of findings 2–6 on curator slice P."""
import importlib.util
import json
import os
import subprocess

import psycopg
import pytest
from softauthn import SoftAuthenticator

from kutuphane import cli, notes, passkey
from test_curatorweb import (CFG, DEPLOY, H, ORIGIN, RP, U, client, enroll, env, login, note, options,  # noqa: F401
                             ready, submit, web_dsn)


def rule(conn, text, supersedes=None) -> str:
    links = [{"type": "supersedes", "ref": supersedes}] if supersedes else []
    return note(conn, text, kind="convention", links=links)


def approve(client, auth, ref) -> dict:
    o = options(client, [{"ref": ref, "to": "approved"}])
    r = submit(client, o, auth.get(o["publicKey"]))
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture
def owner_cli(monkeypatch):
    monkeypatch.setenv("KUTUPHANE_CURATOR_DSN", os.environ["KUTUPHANE_TEST_DSN"])
    monkeypatch.setenv("KUTUPHANE_WEBAUTHN_RP_ID", RP)
    monkeypatch.setenv("KUTUPHANE_WEBAUTHN_ORIGIN", ORIGIN)


# --- #2: the retirements of a rule approval are signed ---------------------------------------------------------

def test_a_rule_approval_signs_the_retirements_it_causes(env, client):
    auth = ready(env, client)
    a = rule(env, "rule a")
    a_event = approve(client, auth, a)["items"][0]["event_seq"]
    b = rule(env, "rule b", supersedes=a)
    o = options(client, [{"ref": b, "to": "approved"}])
    assert o["statement"]["retires"] == [{"ref": a, "id": a.split("@")[1], "was": a_event}]
    notes.set_standing(env, a, "retired", curator=U, reason="by the CLI in between")
    env.commit()
    r = submit(client, o, auth.get(o["publicKey"]))
    assert r.status_code == 409, r.text           # the signed retirement is no longer the one in force
    o = options(client, [{"ref": b, "to": "approved"}])
    assert o["statement"]["retires"] == []
    assert submit(client, o, auth.get(o["publicKey"])).status_code == 200


def test_verify_acts_checks_the_system_events_of_an_act(env, client):
    auth = ready(env, client)
    a = rule(env, "rule a")
    approve(client, auth, a)
    b = rule(env, "rule b", supersedes=a)
    out = approve(client, auth, b)
    assert out["items"][0]["retired"] == [a]
    assert passkey.verify_acts(env, CFG)["problems"] == []
    env.execute("DELETE FROM standing_event WHERE set_by = 'system'")
    assert passkey.verify_acts(env, CFG)["problems"] == [{"act": out["act"], "problem": "effects"}]


# --- #3: the system branch of the web role's policy -------------------------------------------------------------

def test_the_web_role_writes_no_unsigned_system_standing(env, client):
    auth = ready(env, client)
    a = rule(env, "rule a")                          # pending: approving b retires nothing
    b = rule(env, "rule b", supersedes=a)
    cause = approve(client, auth, b)["items"][0]["event_seq"]
    a_seq = env.execute("SELECT seq FROM note WHERE id = %s", (a.split("@")[1],)).fetchone()[0]
    for value in ("approved", "retired"):
        with psycopg.connect(web_dsn()) as web, pytest.raises(psycopg.Error):
            web.execute("INSERT INTO standing_event (note_seq, value, set_by, cause_seq, reason, correlation_id) "
                        "VALUES (%s, %s, 'system', %s, 'forged', 'x')", (a_seq, value, cause))
    assert env.execute("SELECT count(*) FROM standing_event WHERE note_seq = %s", (a_seq,)).fetchone()[0] == 0
    c = rule(env, "rule c", supersedes=b)            # b is approved: a signed retirement, then a forged copy
    out = approve(client, auth, c)
    assert out["items"][0]["retired"] == [b]
    b_seq = env.execute("SELECT seq FROM note WHERE id = %s", (b.split("@")[1],)).fetchone()[0]
    with psycopg.connect(web_dsn()) as web, pytest.raises(psycopg.Error):  # the cause is of another transaction
        web.execute("INSERT INTO standing_event (note_seq, value, set_by, cause_seq, reason, correlation_id) "
                    "VALUES (%s, 'retired', 'system', %s, 'forged', 'x')", (b_seq, out["items"][0]["event_seq"]))


# --- #4: revocation ends sessions --------------------------------------------------------------------------------

def test_revoking_a_passkey_ends_its_sessions(env, client, owner_cli, capsys):
    ready(env, client)
    assert client.get("/api/me").status_code == 200
    assert cli.main(["curator", "passkeys", U]) == 0
    (pk,) = json.loads(capsys.readouterr().out)
    assert cli.main(["curator", "revoke-passkey", pk["id"]]) == 0
    capsys.readouterr()
    assert client.get("/api/me").status_code == 401
    assert env.execute("SELECT count(*) FROM curator_session WHERE login = 'passkey' AND ended_at IS NULL"
                       ).fetchone()[0] == 0


def test_a_session_of_a_revoked_passkey_is_refused(env, client):
    ready(env, client)
    env.execute("UPDATE passkey SET revoked_at = clock_timestamp()")   # revoked without ending the session
    env.commit()
    assert client.get("/api/me").status_code == 401


def test_end_sessions_of_a_person(env, client, owner_cli, capsys):
    ready(env, client)
    assert cli.main(["curator", "end-sessions", U]) == 0
    assert json.loads(capsys.readouterr().out) == {"principal": U, "ended": 1}
    assert client.get("/api/me").status_code == 401


# --- #5: an enrollment session is bound to its code ---------------------------------------------------------------

def test_an_enrollment_session_registers_for_its_own_code(env, client, owner_cli, capsys):
    first, code_a = passkey.enroll(env, U, created_by="user:admin")
    second, code_b = passkey.enroll(env, U, created_by="user:admin")
    env.commit()
    assert client.post("/api/enroll/session", json={"code": code_a}, headers=H).status_code == 200
    o = client.post("/api/enroll/options", json={}, headers=H).json()
    r = client.post("/api/enroll", json={"challenge_id": o["challenge_id"],
                                         "credential": SoftAuthenticator(ORIGIN).create(o["publicKey"])}, headers=H)
    assert r.status_code == 200, r.text
    assert env.execute("SELECT enrollment FROM passkey").fetchall() == [(first,)]
    assert cli.main(["curator", "cancel-enrollment", second]) == 0
    assert json.loads(capsys.readouterr().out)["cancelled"] == second
    assert client.post("/api/enroll/session", json={"code": code_b}, headers=H).status_code == 403


def test_cancelling_an_enrollment_ends_its_session(env, client, owner_cli, capsys):
    eid, code = passkey.enroll(env, U, created_by="user:admin")
    env.commit()
    assert client.post("/api/enroll/session", json={"code": code}, headers=H).status_code == 200
    assert cli.main(["curator", "cancel-enrollment", eid]) == 0
    capsys.readouterr()
    assert client.post("/api/enroll/options", json={}, headers=H).status_code == 401


# --- #6: the deployment probe ------------------------------------------------------------------------------------

def _probe():
    spec = importlib.util.spec_from_file_location("curator_probe", DEPLOY / "curator_probe.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.https = lambda host, method, path, body=None, headers=None: (
        (200, {"content-security-policy": "frame-ancestors 'none'", "x-content-type-options": "nosniff",
               "referrer-policy": "no-referrer"}, "Kütüphane curator".encode()) if method == "GET" else (403, {}, b""))
    module.closed = lambda host, port: True
    return module


@pytest.mark.parametrize("docker", [
    lambda args: subprocess.CompletedProcess(args, 1, "", "Error: No such container: kutuphane-tailscale-1"),
    lambda args: subprocess.CompletedProcess(args, 127, "", "docker: command not found"),
    lambda args: subprocess.CompletedProcess(args, 0, "", ""),
])
def test_the_probe_fails_when_docker_cannot_see_the_containers(monkeypatch, capsys, docker):
    probe = _probe()
    monkeypatch.setattr(probe.subprocess, "run", lambda args, **kw: docker(args))
    monkeypatch.setattr("sys.argv", ["curator_probe.py", ORIGIN])
    assert probe.main() == 1
    assert "FAIL" in capsys.readouterr().out


def test_the_probe_passes_a_good_deployment(monkeypatch, capsys):
    probe = _probe()

    def run(args, **kw):
        if args[1] == "inspect":
            return subprocess.CompletedProcess(args, 0, "[]", "")
        if "funnel" in args:
            return subprocess.CompletedProcess(args, 0, '{"TCP": {"443": {"HTTPS": true}}}', "")
        if args[1] == "port":
            return subprocess.CompletedProcess(args, 0, "", "")
        return subprocess.CompletedProcess(args, 3, "UNREACHABLE gaierror\n", "")
    monkeypatch.setattr(probe.subprocess, "run", run)
    monkeypatch.setattr("sys.argv", ["curator_probe.py", ORIGIN])
    assert probe.main() == 0, capsys.readouterr().out
