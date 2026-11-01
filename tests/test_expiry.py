"""R1 and R2 (docs/research/2026-11-01-agent-memory-research.md §8): evidence that nobody uses expires, and
outcomes filter `query_notes`. Time comes from explicit timestamps (`now`, and stored times moved), never from
sleeping."""
import asyncio
import json
import os
import uuid
from datetime import datetime, timedelta, timezone

import psycopg
import pytest
from starlette.testclient import TestClient

from kutuphane import authz, cli, db, notes, notesquery, outcomes, server
from test_identity import token
from test_notes import PUBLIC, J, env, keys, mcp, row, verifier  # noqa: F401 (fixtures)
from test_rollback import CURATOR, act, events, put, seq_of, standing

DAY = timedelta(days=1)


def later(days: int) -> datetime:
    return datetime.now(timezone.utc) + days * DAY


def expire(conn, after: int, days: int = 90, **kw) -> dict:
    return notes.expire(conn, days=days, now=later(after), **kw)


def rule(conn, text, kind="convention"):
    args = {"decision": {"options": ["a", "b"], "choice": "a"}} if kind == "decision_proposal" else {}
    return notes.propose(conn, mcp(), {"book": J, "kind": kind, "text": text, **args})[0]["ref"]


def outcome(conn, ref, result, shift_days=0) -> None:
    outcomes.record(conn, mcp(), {"ref": ref, "task_ref": "adc:run/1", "result": result,
                                  "idempotency_key": f"key-{uuid.uuid4().hex}"})
    conn.execute("UPDATE outcome SET at = at + %s * interval '1 day' WHERE seq = (SELECT max(seq) FROM outcome)",
                 (shift_days,))


def moved(out: dict) -> dict:
    return {n["ref"]: (n["was"], n["standing"]) for n in out["notes"]}


# --- R1: expiry ------------------------------------------------------------------------------------------------

def test_unused_evidence_expires_and_rules_never_do(env):
    authz.grant(env, f"book:{J}", "curate", CURATOR)
    pending = put(env, "a pending finding nobody used")
    approved = put(env, "an approved finding nobody used")
    act(env, approved, "approved")
    reopened = put(env, "approved once, reopened since")
    for value in ("approved", "retired", "pending"):
        act(env, reopened, value)
    out_already = put(env, "rejected by a person")
    act(env, out_already, "rejected")
    convention = rule(env, "a convention nobody used")
    decision = rule(env, "a decision nobody used", "decision_proposal")
    act(env, decision, "approved")

    assert expire(env, 89)["notes"] == []
    out = expire(env, 91)
    assert moved(out) == {pending: ("pending", "rejected"), approved: ("approved", "retired"),
                          reopened: ("pending", "retired")}  # D68: a note approved once is never rejected
    assert out["days"] == 90 and out["dry_run"] is False
    assert events(env, pending) == [("rejected", "system", None, "expired")]
    assert events(env, approved)[-1] == ("retired", "system", None, "expired")
    assert len({row(env, "SELECT correlation_id FROM standing_event WHERE seq = %s", n["event_seq"])[0]
                for n in out["notes"]}) == 1  # one run, one correlation id
    assert [standing(env, r) for r in (out_already, convention, decision)] == ["rejected", "pending", "approved"]


def test_a_passed_outcome_or_a_curator_event_resets_the_clock(env):
    authz.grant(env, f"book:{J}", "curate", CURATOR)
    used, failed, touched = (put(env, t) for t in ("passed later", "failed later", "approved later"))
    act(env, used, "approved")
    act(env, failed, "approved")
    outcome(env, used, "passed", shift_days=60)
    outcome(env, failed, "failed", shift_days=60)       # a failed use is not a use that keeps it
    outcome(env, failed, "reopened", shift_days=60)
    act(env, touched, "approved")
    env.execute("UPDATE standing_event SET at = at + interval '60 days' WHERE note_seq = %s", (seq_of(env, touched),))
    assert moved(expire(env, 120)) == {failed: ("approved", "retired")}
    assert moved(expire(env, 151)) == {used: ("approved", "retired"), touched: ("approved", "retired")}


def test_expiry_is_idempotent_and_a_dry_run_writes_nothing(env):
    ref = put(env, "a pending finding")
    before = row(env, "SELECT count(*) FROM standing_event")[0]
    dry = expire(env, 91, dry_run=True)
    assert moved(dry) == {ref: ("pending", "rejected")} and dry["notes"][0]["event_seq"] is None
    assert row(env, "SELECT count(*) FROM standing_event")[0] == before
    assert moved(expire(env, 91)) == {ref: ("pending", "rejected")}
    assert expire(env, 91)["notes"] == [] and expire(env, 400)["notes"] == []
    assert row(env, "SELECT count(*) FROM standing_event")[0] == before + 1
    for bad in (0, -1, True, "90", 36501):
        with pytest.raises(ValueError, match="days"):
            notes.expire(env, days=bad)


def test_the_cli_needs_the_owner_credential_and_reads_the_days(env, monkeypatch, capsys):
    ref = put(env, "written 100 days ago")
    env.execute("UPDATE note SET written_at = written_at - interval '100 days' WHERE seq = %s", (seq_of(env, ref),))
    monkeypatch.delenv(db.CURATOR_DSN_ENV, raising=False)
    assert cli.main(["note", "expire"]) == 2 and db.CURATOR_DSN_ENV in capsys.readouterr().err
    monkeypatch.setenv(db.CURATOR_DSN_ENV, os.environ["KUTUPHANE_TEST_DSN"])
    monkeypatch.setenv(notes.EXPIRY_ENV, "120")
    assert cli.main(["note", "expire"]) == 0 and json.loads(capsys.readouterr().out)["notes"] == []
    assert cli.main(["note", "expire", "--days", "99", "--dry-run"]) == 0
    assert [n["ref"] for n in json.loads(capsys.readouterr().out)["notes"]] == [ref]
    assert standing(env, ref) == "pending"
    monkeypatch.setenv(notes.EXPIRY_ENV, "ninety")
    assert cli.main(["note", "expire"]) == 2 and notes.EXPIRY_ENV in capsys.readouterr().err
    monkeypatch.delenv(notes.EXPIRY_ENV)
    assert cli.main(["note", "expire"]) == 0
    assert json.loads(capsys.readouterr().out)["days"] == 90 and standing(env, ref) == "rejected"


def test_the_database_allows_only_the_two_expiry_moves(env):  # migration 049
    authz.grant(env, f"book:{J}", "curate", CURATOR)
    pending, convention = put(env, "pending evidence"), rule(env, "a pending rule")
    approved, reopened = put(env, "approved evidence"), put(env, "approved once")
    act(env, approved, "approved")
    for value in ("approved", "retired", "pending"):
        act(env, reopened, value)

    def system(ref, value, reason="expired", cause=None):
        with env.transaction():
            env.execute("INSERT INTO standing_event (note_seq, value, set_by, cause_seq, reason, correlation_id) "
                        "VALUES (%s, %s, 'system', %s, %s, 'test')", (seq_of(env, ref), value, cause, reason))

    for ref, value, reason, cause in (
            (convention, "rejected", "expired", None),     # a rule never expires
            (pending, "retired", "expired", None),         # pending, never approved: rejected
            (approved, "rejected", "expired", None),       # approved: retired
            (reopened, "rejected", "expired", None),       # D68
            (pending, "approved", "expired", None),        # the system only tightens
            (pending, "pending", "expired", None),
            (pending, "rejected", "stale", None),          # only an expiry has no cause
            (pending, "rejected", "expired", row(env, "SELECT max(seq) FROM standing_event")[0])):
        with pytest.raises((psycopg.errors.IntegrityError, psycopg.errors.RaiseException)):
            system(ref, value, reason, cause)
    system(pending, "rejected")
    with pytest.raises(psycopg.errors.RaiseException):
        system(pending, "rejected")                        # already out
    system(approved, "retired")
    system(reopened, "retired")
    assert [standing(env, r) for r in (pending, approved, reopened, convention)] == [
        "rejected", "retired", "retired", "pending"]


# --- R2: outcomes filter query_notes --------------------------------------------------------------------------

def refs(conn, **kw) -> set:
    return {i["ref"] for i in notesquery.query_notes(conn, mcp(), for_model=True, sets=["open"], **kw)["items"]}


@pytest.fixture
def used(env):
    two = put(env, "passed twice")
    for _ in range(2):
        outcome(env, two, "passed")
    then_failed, then_reverted, then_passed = (put(env, t) for t in ("then failed", "then reverted", "then passed"))
    for ref, results in ((then_failed, ("passed", "failed")), (then_reverted, ("passed", "reverted")),
                         (then_passed, ("failed", "passed"))):
        for result in results:
            outcome(env, ref, result)
    reopened = put(env, "then reopened")
    for result in ("failed", "reopened"):
        outcome(env, reopened, result)
    never = put(env, "no outcome")
    return {"two": two, "failed": then_failed, "reverted": then_reverted, "passed": then_passed,
            "reopened": reopened, "never": never}


def test_min_passed_and_exclude_failed_filter_query_notes(env, used):
    every = set(used.values())
    assert refs(env) == every and refs(env, min_passed=0) == every
    assert refs(env, min_passed=1) == {used[k] for k in ("two", "failed", "reverted", "passed")}
    assert refs(env, min_passed=2) == {used["two"]}
    assert refs(env, exclude_failed=True) == every - {used["failed"], used["reverted"]}
    assert refs(env, min_passed=1, exclude_failed=True) == {used["two"], used["passed"]}
    w = notesquery.watermark(env)
    outcome(env, used["passed"], "failed")                       # after the watermark: as_of reads the past
    assert refs(env, exclude_failed=True, as_of=w) == every - {used["failed"], used["reverted"]}
    assert used["passed"] not in refs(env, exclude_failed=True)
    for bad in ({"min_passed": -1}, {"min_passed": 101}, {"min_passed": True}, {"exclude_failed": "yes"}):
        with pytest.raises(ValueError):
            refs(env, **bad)


def test_the_filters_over_http_and_mcp(env, used, keys, verifier):
    from test_server import call_tool
    dsn = os.environ["KUTUPHANE_TEST_DSN"]
    mcp_server = server.build_mcp(dsn=dsn, verifier=verifier, bridge=None, model=None, public_url=PUBLIC)
    claims = asyncio.run(server._Verifier(verifier).verify_token(token(keys, act={"sub": "kobra-7"}))).claims
    content, _ = call_tool(mcp_server, claims, "query_notes", {"sets": ["open"], "min_passed": 2})
    assert [i["ref"] for i in json.loads(content[0].text)["items"]] == [used["two"]]
    app = server.create_app(dsn=dsn, verifier=verifier, bridge=None, model=None, public_url=PUBLIC)
    h = {"Authorization": f"Bearer {token(keys)}"}
    with TestClient(app) as client:
        r = client.get("/v1/notes?sets=open&min_passed=1&exclude_failed=true", headers=h)
        assert r.status_code == 200 and {i["ref"] for i in r.json()["items"]} == {used["two"], used["passed"]}
        assert client.get("/v1/notes?sets=open&min_passed=x", headers=h).status_code == 400
        assert client.get("/v1/notes?sets=open&exclude_failed=maybe", headers=h).status_code == 400
