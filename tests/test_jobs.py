"""docs/24 §12.2, T35, T36, T38 (018): `ask_library` as a durable background job."""
import json
import time
from datetime import datetime, timedelta, timezone

import pytest
from starlette.testclient import TestClient

from kutuphane import answers, authz, db, jobs, server
from kutuphane.gate import Actor
from test_server import A, MODERN, PUBLIC, U, app_env, bearer, fake, keys, mcp_rpc, verifier  # noqa: F401

Q = "Erişim kayıtları ne kadar saklanır?"
REPLY = "İki yıl saklanır [1]."


def model_calls(fake) -> int:
    return sum(1 for path, _h in fake.hits if path.endswith("/chat/completions"))


def app_with(app_env, verifier, fake, workers: int):
    _app, _, dsn = app_env
    return server.create_app(dsn=dsn, verifier=verifier, bridge=fake.bridge(), model="qwen", public_url=PUBLIC,
                             job_workers=workers)


def wait_for(client, auth, job_id, states=("succeeded", "failed", "cancelled"), seconds=30) -> dict:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        state = client.get(f"/v1/jobs/{job_id}", headers=auth).json()
        if state["status"] in states:
            return state
        time.sleep(0.05)
    raise AssertionError(f"job {job_id} still {state['status']}")


def run_ask(fake):
    def ask(conn, actor, question, scope, check, commit):
        return answers.ask(conn, fake.bridge(), actor, question, model="qwen", scope=scope, check=check,
                           commit=commit)["id"]
    return ask


def submit(client, auth, **extra):
    return client.post("/v1/ask", json={"question": Q, "background": True, **extra}, headers=auth)


def test_background_ask_returns_a_job_at_once_and_survives_a_restart(app_env, verifier, keys, fake):  # T35
    fake.reply = REPLY
    h = bearer(keys)
    with TestClient(app_with(app_env, verifier, fake, 0), base_url=PUBLIC) as client:
        r = submit(client, h)
        assert r.status_code == 202 and r.json()["status"] == "queued" and r.json()["job_id"].startswith("jb_")
        job_id = r.json()["job_id"]
        state = client.get(f"/v1/jobs/{job_id}", headers=h).json()
        assert state["status"] == "queued" and state["created_at"] and state["started_at"] is None
        assert set(state) == {"status", "created_at", "started_at", "finished_at", "error"}
        assert client.get(f"/v1/jobs/{job_id}/result", headers=h).status_code == 400   # no result yet
        assert model_calls(fake) == 0
    with TestClient(app_with(app_env, verifier, fake, 1), base_url=PUBLIC) as client:   # a new server process
        state = wait_for(client, h, job_id)
        assert state["status"] == "succeeded" and state["finished_at"] and state["error"] is None
        result = client.get(f"/v1/jobs/{job_id}/result", headers=h).json()
        assert result["body"] == REPLY and result["evidence"]
        assert client.get(f"/v1/answers/{result['id']}", headers=h).json() == result   # = reopen_answer
    assert model_calls(fake) == 1


def test_expired_lease_fails_the_job_and_it_never_runs_again(app_env, conn, fake):  # T35
    _app, _, dsn = app_env
    actor = Actor(U)
    job, _ = jobs.submit(conn, actor, Q, server.search.Scope())
    assert jobs.claim(conn) is not None                                  # a worker took it, then its process died
    conn.execute("UPDATE ask_job SET lease_until = now() - interval '1 second' WHERE id = %s", (job["job_id"],))
    state = jobs.status(conn, actor, job["job_id"])
    assert (state["status"], state["error"]) == ("failed", "interrupted") and state["finished_at"]
    assert jobs.work_one(conn, dsn, run_ask(fake), server._safe_error) is False
    assert model_calls(fake) == 0


def test_cancel_before_run_and_while_running(app_env, conn, fake):  # T35
    _app, _, dsn = app_env
    actor = Actor(U)
    queued, _ = jobs.submit(conn, actor, Q, server.search.Scope())
    assert jobs.cancel(conn, actor, queued["job_id"])["status"] == "cancelled"
    assert jobs.work_one(conn, dsn, run_ask(fake), server._safe_error) is False   # never claimed
    running, _ = jobs.submit(conn, actor, Q, server.search.Scope())
    claimed = jobs.claim(conn)
    assert jobs.cancel(conn, actor, running["job_id"])["status"] == "running"     # the worker sees it at its check
    jobs.run(conn, dsn, claimed, run_ask(fake), server._safe_error)
    state = jobs.status(conn, actor, running["job_id"])
    assert state["status"] == "cancelled" and state["finished_at"]
    assert model_calls(fake) == 0                                                  # stopped before the model call
    assert conn.execute("SELECT count(*) FROM answer").fetchone()[0] == 0


def test_cancel_after_the_model_call_stores_no_answer(app_env, conn, fake):  # §12.2: checked before the store
    _app, _, dsn = app_env
    fake.reply = REPLY
    actor = Actor(U)
    job, _ = jobs.submit(conn, actor, Q, server.search.Scope())
    claimed = jobs.claim(conn)
    fake.on_request = lambda: db.connect(dsn).execute(
        "UPDATE ask_job SET cancel_requested_at = now() WHERE id = %s", (job["job_id"],))
    jobs.run(conn, dsn, claimed, run_ask(fake), server._safe_error)
    assert jobs.status(conn, actor, job["job_id"])["status"] == "cancelled"
    assert model_calls(fake) == 1 and conn.execute("SELECT count(*) FROM answer").fetchone()[0] == 0


def test_a_cancel_that_lands_before_the_store_wins(app_env, conn, fake, monkeypatch):  # Astra review #13 (5)
    _app, _, dsn = app_env
    fake.reply = REPLY
    actor = Actor(U)
    job, _ = jobs.submit(conn, actor, Q, server.search.Scope())
    claimed = jobs.claim(conn)
    real = answers._store

    def racing(*args, **kw):  # the worker's last check passed; a cancel commits before the insert
        with db.connect(dsn) as other:
            assert jobs.cancel(other, actor, job["job_id"])["status"] == "running"
        return real(*args, **kw)
    monkeypatch.setattr(answers, "_store", racing)
    jobs.run(conn, dsn, claimed, run_ask(fake), server._safe_error)
    state = jobs.status(conn, actor, job["job_id"])
    assert state["status"] == "cancelled" and state["finished_at"]
    assert model_calls(fake) == 1 and conn.execute("SELECT count(*) FROM answer").fetchone()[0] == 0


def test_an_expired_and_failed_job_stores_no_answer(app_env, conn, fake):  # Astra review #13 (6)
    _app, _, dsn = app_env
    fake.reply = REPLY
    actor = Actor(U)
    job, _ = jobs.submit(conn, actor, Q, server.search.Scope())
    claimed = jobs.claim(conn)

    def expired():  # while the model "thinks", the lease ends and another process fails the job
        with db.connect(dsn) as other:
            other.execute("UPDATE ask_job SET lease_until = now() - interval '1 second' WHERE id = %s",
                          (job["job_id"],))
            jobs.expire(other)
    fake.on_request = expired
    jobs.run(conn, dsn, claimed, run_ask(fake), server._safe_error)
    state = jobs.status(conn, actor, job["job_id"])
    assert (state["status"], state["error"]) == ("failed", "interrupted")
    assert conn.execute("SELECT count(*) FROM answer").fetchone()[0] == 0


def test_renewal_never_revives_an_expired_lease(app_env, conn, fake):  # Astra review #13 (6)
    _app, _, dsn = app_env
    fake.reply = REPLY
    actor = Actor(U)
    job, _ = jobs.submit(conn, actor, Q, server.search.Scope())
    claimed = jobs.claim(conn, lease_seconds=0.3)

    def lapse():  # the lease ends (no process has failed the job yet); the heartbeat runs meanwhile
        with db.connect(dsn) as other:
            other.execute("UPDATE ask_job SET lease_until = now() - interval '1 second' WHERE id = %s",
                          (job["job_id"],))
        time.sleep(0.5)
    fake.on_request = lapse
    jobs.run(conn, dsn, claimed, run_ask(fake), server._safe_error, lease_seconds=0.3)
    state = jobs.status(conn, actor, job["job_id"])
    assert (state["status"], state["error"]) == ("failed", "interrupted")
    assert conn.execute("SELECT count(*) FROM answer").fetchone()[0] == 0
    lease = conn.execute("SELECT lease_until FROM ask_job WHERE id = %s", (job["job_id"],)).fetchone()[0]
    assert lease is None


def test_retry_with_the_same_key_gives_the_same_job_and_one_model_call(app_env, verifier, keys, fake):  # T35, §6.4
    fake.reply = REPLY
    h = bearer(keys)
    with TestClient(app_with(app_env, verifier, fake, 0), base_url=PUBLIC) as client:
        first = submit(client, h, idempotency_key="retry-key-1")
        again = submit(client, h, idempotency_key="retry-key-1")
        assert (first.status_code, again.status_code) == (202, 200)
        assert again.json()["job_id"] == first.json()["job_id"]
        _, over_mcp = mcp_rpc(client, h, "tools/call", {"name": "ask_library", "arguments": {
            "question": Q, "background": True, "idempotency_key": "retry-key-1"}}, version=MODERN)
        assert json.loads(over_mcp["result"]["content"][0]["text"]) == {"job_id": first.json()["job_id"],
                                                                         "status": "queued"}   # same principal
        other = submit(client, h, idempotency_key="retry-key-1", book=["kitap"])
        assert other.status_code == 409 and "reused" in other.json()["error"]
        agent = bearer(keys, act={"sub": "kobra-7"})                                 # another context: independent
        assert submit(client, agent, idempotency_key="retry-key-1").json()["job_id"] != first.json()["job_id"]
        assert submit(client, h, idempotency_key="short").status_code == 400
        assert client.post("/v1/ask", json={"question": Q, "idempotency_key": "retry-key-2"},
                           headers=h).status_code == 400                             # a key needs background
    with TestClient(app_with(app_env, verifier, fake, 1), base_url=PUBLIC) as client:
        assert wait_for(client, h, first.json()["job_id"])["status"] == "succeeded"
    assert model_calls(fake) == 1


def test_at_most_three_open_jobs_per_principal(app_env, verifier, keys, fake):  # §12.2, §13: 429
    h = bearer(keys)
    with TestClient(app_with(app_env, verifier, fake, 0), base_url=PUBLIC) as client:
        ids = [submit(client, h).json()["job_id"] for _ in range(jobs.MAX_OPEN)]
        assert submit(client, h).status_code == 429
        assert client.post(f"/v1/jobs/{ids[0]}/cancel", headers=h).json()["status"] == "cancelled"
        assert submit(client, h).status_code == 202


def test_job_visibility_follows_reopen(app_env, verifier, keys, fake, conn):  # T36
    fake.reply = REPLY
    did = authz.delegate(conn, delegator=U, delegate_to=A, obj="book:kitap", mode="read",
                         expires_at=datetime.now(timezone.utc) + timedelta(hours=1))
    x_for_a = bearer(keys, act={"sub": "kobra-7"})
    a = bearer(keys)
    x_for_b = bearer(keys, sub="mehmet", act={"sub": "kobra-7"})
    x = bearer(keys, sub="kobra-7", **{"kutuphane/principal_type": "agent"})
    with TestClient(app_with(app_env, verifier, fake, 1), base_url=PUBLIC) as client:
        _, sent = mcp_rpc(client, x_for_a, "tools/call", {"name": "ask_library", "arguments": {
            "question": Q, "background": True}}, version=MODERN)
        job_id = json.loads(sent["result"]["content"][0]["text"])["job_id"]
        assert wait_for(client, x_for_a, job_id)["status"] == "succeeded"
        shown = {}
        for name, auth in [("x_for_a", x_for_a), ("a", a)]:
            assert client.get(f"/v1/jobs/{job_id}", headers=auth).status_code == 200
            result = client.get(f"/v1/jobs/{job_id}/result", headers=auth)
            assert result.status_code == 200 and result.json()["body"] == REPLY
            shown[name] = result.json()
        _, over_mcp = mcp_rpc(client, x_for_a, "tools/call", {"name": "job_result", "arguments": {"job_id": job_id}},
                              version=MODERN)
        assert json.loads(over_mcp["result"]["content"][0]["text"])["body"] == REPLY
        answer_id = shown["a"]["id"]
        for auth in (x_for_b, x):
            for path in (f"/v1/jobs/{job_id}", f"/v1/jobs/{job_id}/result"):
                r = client.get(path, headers=auth)
                assert (r.status_code, r.json()) == (404, {"error": "not found"})
            assert client.post(f"/v1/jobs/{job_id}/cancel", headers=auth).status_code == 404
        before = {name: client.get(f"/v1/answers/{answer_id}", headers=auth).status_code
                  for name, auth in [("x_for_a", x_for_a), ("a", a), ("x_for_b", x_for_b), ("x", x)]}
        authz.revoke_delegation(conn, did)
        assert client.get(f"/v1/jobs/{job_id}", headers=x_for_a).json()["status"] == "succeeded"   # status: yes
        assert client.get(f"/v1/jobs/{job_id}/result", headers=x_for_a).status_code == 403       # result: no
        revoked = {name: client.get(f"/v1/answers/{answer_id}", headers=auth).status_code
                   for name, auth in [("x_for_a", x_for_a), ("a", a), ("x_for_b", x_for_b), ("x", x)]}
        conn.execute("UPDATE ask_job SET finished_at = now() - interval '8 days'")
        jobs.cleanup(conn)
        assert conn.execute("SELECT count(*) FROM ask_job").fetchone()[0] == 0
        assert client.get(f"/v1/jobs/{job_id}", headers=a).status_code == 404
        after = {name: client.get(f"/v1/answers/{answer_id}", headers=auth).status_code
                 for name, auth in [("x_for_a", x_for_a), ("a", a), ("x_for_b", x_for_b), ("x", x)]}
    assert before == {"x_for_a": 200, "a": 200, "x_for_b": 403, "x": 403}
    assert after == revoked == {"x_for_a": 403, "a": 200, "x_for_b": 403, "x": 403}


def test_018_applies_to_a_database_at_015_with_data(conn):  # T38 (D's part)
    applied = ["018_ask_job.sql"]
    conn.execute("DROP TABLE ask_job")
    conn.execute("DELETE FROM schema_migration WHERE name = ANY(%s)", (applied,))
    authz.grant(conn, "book:kitap", "read", U)
    did = authz.delegate(conn, delegator=U, delegate_to=A, obj="book:kitap", mode="read",
                         expires_at=datetime.now(timezone.utc) + timedelta(hours=1))
    assert db.migrate(conn) == applied
    assert authz.authorize(conn, A, U, "book:kitap", "read").allowed
    assert conn.execute("SELECT count(*) FROM delegation WHERE id = %s", (did,)).fetchone()[0] == 1
    with pytest.raises(Exception, match="ask_job_id_check"):
        conn.execute("INSERT INTO ask_job (id, principal, correlation_id, question, scope, status) "
                     "VALUES ('jb_x', 'user:ayse', 'c', 'q', '{}', 'queued')")
