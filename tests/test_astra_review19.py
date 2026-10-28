"""Astra review #19 (docs/08): the regressions of findings 1–4.

The roles connect with the deploy grants (deploy/db-roles*.sql), as in a deployment; the owner (the test) only sets up
the data, except where a test plays the owner's own part.
"""
import hashlib
import json
import os

import psycopg
import pytest

from kutuphane import answers, authz, catalog, decisions, notes, packages, passkey, profiles, retrieval, server
from kutuphane.gate import Actor
from kutuphane.policy import make_policy
from kutuphane.source import AcceptedFinding, read_source
from test_confirm import _curator_url, act, person, propose, seq_of, shown  # noqa: F401
from test_curator_review17 import SUGGEST, model_call
from test_curatorweb import CFG
from test_decider import APP, DEC, WEB, A, J, U, note, spec
from test_decider import dec, env  # noqa: F401  (fixtures)
from test_ingest import PERSONAL_DOC
from test_packages import key, trust  # noqa: F401  (key: a fixture)
from test_quotes import books, fake  # noqa: F401  (fixtures)

PIN = ["search_path=pg_catalog, public, pg_temp"]
CLOUD = make_policy(sensitivity="normal", egress="cloud_ok", protection="standard")
LOCAL = make_policy(sensitivity="normal", egress="local_only", protection="standard")


# --- #1: no function resolves an object through the caller's temporary schema --------------------------------------

def test_every_function_of_ours_pins_its_search_path(conn):
    rows = conn.execute(
        "SELECT p.proname, p.proconfig FROM pg_proc p JOIN pg_namespace s ON s.oid = p.pronamespace "
        "WHERE s.nspname = 'public' AND NOT EXISTS (SELECT 1 FROM pg_depend d WHERE d.classid = 'pg_proc'::regclass "
        "AND d.objid = p.oid AND d.deptype = 'e') ORDER BY 1").fetchall()   # not the functions of extensions
    assert len(rows) >= 16
    assert [name for name, config in rows if config != PIN] == []


def test_no_login_role_makes_temporary_objects(env):
    for role in (APP, WEB, DEC):
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            with env.transaction():
                env.execute(f"SET LOCAL ROLE {role}")
                env.execute("CREATE TEMP TABLE shadow (a int)")


def test_a_temporary_shadow_cannot_fake_shadow_evidence(env, dec):
    """With TEMP (a deployment that did not apply the new role scripts), the decider role makes an empty temporary
    `standing_event` and a temporary `memory_seq` that gives negative numbers. A suggestion after a person's verdict
    is still refused, and a suggestion takes its seq from public.memory_seq."""
    db_name = env.execute("SELECT current_database()").fetchone()[0]
    env.execute(f'GRANT TEMPORARY ON DATABASE "{db_name}" TO {DEC}')
    s = spec()
    decided, ref = note(env, "A finding that a person rejected first")
    notes.set_standing(env, ref, "rejected", curator=U, reason="a person decided it")
    open_seq, _ = note(env, "A finding with no decision yet")
    calls = model_call(env), model_call(env)
    dec.execute("CREATE TEMP TABLE standing_event (note_seq bigint)")
    dec.execute("CREATE TEMP SEQUENCE memory_seq MINVALUE -1000000000 START -1000000000")
    with pytest.raises(psycopg.errors.RaiseException, match="has a Standing event"):
        dec.execute(SUGGEST, (decided, s.decider, s.sha256, calls[0]))
    late = dec.execute(SUGGEST, (open_seq, s.decider, s.sha256, calls[1])).fetchone()[0]
    assert late > open_seq                                  # after the note, from the real sequence
    assert env.execute("SELECT count(*) FROM note_suggestion WHERE note_seq = %s", (decided,)).fetchone()[0] == 0


# --- #2: a confirmation and an approval are of the signed parts ------------------------------------------------------

LINK = ("INSERT INTO note_link (src, src_book, type, dst_note, dst_note_book, creation, write_seq) "
        "VALUES (%s, %s, 'about', %s, %s, true, %s)")
CODE = ("INSERT INTO note_citation (note_seq, book, n, kind, path, repo, commit, line_start, line_end, excerpt_sha256) "
        "VALUES (%s, %s, 1, 'code', 'q.py', 'adc', %s, 1, 1, '\\x00')")


def _confirmed_and_approved(env):
    """A decision proposal that Ayşe confirmed (`human`) and approved, each with a passkey act; an older note."""
    other = propose(env, "An older finding", origin=None)
    r = propose(env, "Postgres 17 over 16", kind="decision_proposal",
                decision={"options": ["16", "17"], "choice": "17"})
    c, auth = person(env)
    assert act(c, auth, {"action": "confirm", "ref": r["ref"], "claim": "human"}).status_code == 200
    done = act(c, auth, {"action": "standing", "items": [{"ref": r["ref"], "to": "approved"}], "reason": "checked"})
    assert done.status_code == 200, done.text
    seq = seq_of(env, r["ref"])
    write = env.execute("SELECT seq FROM write_record WHERE note_seq = %s AND creates", (seq,)).fetchone()[0]
    return r["ref"], seq, write, seq_of(env, other["ref"])


def test_a_confirmed_note_gains_no_citation_or_creation_link_later(env):
    ref, seq, write, other = _confirmed_and_approved(env)
    for sql, params in ((LINK, (seq, J, other, J, write)), (CODE, (seq, J, "a" * 40))):
        with pytest.raises(psycopg.errors.RaiseException, match="is written"):
            with env.transaction():
                env.execute(f"SET LOCAL ROLE {APP}")     # what the app role holds: INSERT, no UPDATE or DELETE
                env.execute(sql, params)
    assert shown(env, ref) == ("human", A, U)
    assert notes.effective_standing(env, [seq], notes.NOW)[seq][0] == "approved"
    assert passkey.verify_acts(env, CFG)["problems"] == []


def test_a_part_added_before_039_voids_the_confirmation_and_the_approval(env):
    """Rows that a compromised app wrote before migration 039 (triggers off, as then): the readers compare the parts
    with the signed id, fall back to `model` and `pending`, and verify-acts names both acts."""
    ref, seq, write, other = _confirmed_and_approved(env)
    with env.transaction():
        env.execute("SET LOCAL session_replication_role = replica")
        env.execute(LINK, (seq, J, other, J, write))
    assert shown(env, ref) == ("model", None, None)
    records, _ = decisions.export(env, Actor(U), [J])
    assert (records[0]["actor"]["origin"], records[0]["actor"].get("confirmed_by")) == ("model", None)
    assert notes.effective_standing(env, [seq], notes.NOW)[seq][0] == "pending"
    acts = [a for (a,) in env.execute("SELECT seq FROM curator_act WHERE action IN ('confirm', 'standing') "
                                      "ORDER BY seq")]
    assert passkey.verify_acts(env, CFG)["problems"] == [{"act": a, "problem": "contents"} for a in acts]


def test_parts_written_with_the_note_in_a_savepoint_are_accepted(env):
    _, older = note(env, "An older finding")
    with env.transaction():
        with env.transaction():                             # a savepoint: the note row has a subtransaction xmin
            _, ref = note(env, "Derived inside a savepoint", links=[{"type": "derived_from", "ref": older}])
    seq = seq_of(env, ref)
    assert env.execute("SELECT count(*) FROM note_link WHERE src = %s AND creation", (seq,)).fetchone()[0] == 1


# --- #3: search hits and quoted records in one final decision --------------------------------------------------------

def _transfer_after_retrieval(conn, monkeypatch):
    """Retrieval finishes its own final decision; then one atomic grant change revokes briefs and grants news."""
    real = retrieval.retrieved

    def retrieved(*args, **kw):
        found = real(*args, **kw)
        with conn.transaction():
            authz.revoke(conn, "book:briefs", "read", U)
            authz.grant(conn, "book:news", "read", U)
        return found
    monkeypatch.setattr(retrieval, "retrieved", retrieved)


def test_search_never_hands_out_a_passage_with_a_record_not_readable_at_the_same_time(conn, books, monkeypatch):
    authz.grant(conn, "book:briefs", "read", U)
    _transfer_after_retrieval(conn, monkeypatch)
    out = server.op_search(os.environ["KUTUPHANE_TEST_DSN"], retrieval.Stages(), Actor(U), "falcon latency pilot", 5)
    assert [h["citation"] for h in out if h["citation"].startswith("briefs@")] == []
    assert conn.execute("SELECT count(*) FROM access_event WHERE object = 'book:briefs' AND NOT allowed "
                        "AND reason = 'changed during search'").fetchone()[0] == 1


def test_ask_never_sends_a_passage_with_a_record_not_readable_at_the_same_time(conn, books, fake, monkeypatch):
    authz.grant(conn, "book:briefs", "read", U)
    _transfer_after_retrieval(conn, monkeypatch)
    fake.reply = "The brief moves falcon to pilot [1]."
    result = answers.ask(conn, fake.bridge(), Actor(U), "What does the falcon latency pilot brief say?",
                         model="qwen", k=1)
    assert result["status"] == "not_in_library" and fake.requests == []   # nothing went to the model


def test_named_records_are_in_the_delivery_audit(conn, books):
    authz.grant(conn, "book:briefs", "read", U)
    authz.grant(conn, "book:news", "read", U)
    out = server.op_search(os.environ["KUTUPHANE_TEST_DSN"], retrieval.Stages(), Actor(U), "falcon latency pilot", 5)
    (brief,) = [h for h in out if "/brief.json#" in h["citation"]]
    assert brief["quoted_records"]
    rows = conn.execute("SELECT items FROM access_event WHERE action = 'quote' AND object = 'book:news' "
                        "AND allowed").fetchall()
    assert [items for (items,) in rows] == [brief["quoted_records"]]


# --- #4: the personal-data cloud gate at the shared publication point ------------------------------------------------

@pytest.fixture
def personal_package(conn, conn_b, okf_dir, key):
    """A package (published locally at the sender) with a file that holds an ordinary e-mail address and more."""
    (okf_dir / "nobet.md").write_text(PERSONAL_DOC, encoding="utf-8")
    catalog.publish(conn, book="kitap", title="Kitap", files=read_source(okf_dir), policy=LOCAL,
                    profile=profiles.spec("chunked"))
    private, info = key
    trust(conn_b, info)
    received = packages.receive(conn_b, packages.export(conn, "kitap", private))
    assert received["status"] == "verified"
    return received, (okf_dir / "nobet.md").read_bytes()


def test_package_review_lists_the_personal_data_findings(personal_package):
    received, data = personal_package
    found = [f for f in received["findings"] if f["kind"] == "personal_data"]
    digest = hashlib.sha256(data).hexdigest()
    assert [(f["path"], f["rule"], f["sha256"]) for f in found] == [
        ("nobet.md", rule, digest) for rule in ("email", "phone", "private-ipv4")]
    assert "ops@site-a.net" not in json.dumps(received)


def test_a_cloud_approval_needs_the_acceptance_of_each_finding(conn_b, personal_package):
    received, data = personal_package
    with pytest.raises(ValueError, match="personal-data findings in a cloud_ok book"):
        packages.approve(conn_b, received["id"], by="user:admin", policy=CLOUD)
    assert catalog.book_state(conn_b, "kitap") is None
    row = conn_b.execute("SELECT status, reasons FROM package_import WHERE id = %s", (received["id"],)).fetchone()
    assert row[0] == "verified" and "personal-data findings" in row[1][-1]          # on record, can be retried
    digest = hashlib.sha256(data).hexdigest()
    accept = [AcceptedFinding("nobet.md", digest, rule) for rule in ("email", "phone", "private-ipv4")]
    with pytest.raises(ValueError, match="matches no finding"):
        packages.approve(conn_b, received["id"], by="user:admin", policy=CLOUD,
                         accept=[*accept, AcceptedFinding("nobet.md", digest, "listed-name")])
    published = packages.approve(conn_b, received["id"], by="user:admin", policy=CLOUD, accept=accept)
    assert published.data_findings == [] and [a["rule"] for a in published.accepted_findings] == [
        "email", "phone", "private-ipv4"]


def test_a_local_approval_records_the_findings(conn_b, personal_package):
    received, _ = personal_package
    published = packages.approve(conn_b, received["id"], by="user:admin", policy=LOCAL)
    assert [d["rule"] for d in published.data_findings] == ["email", "phone", "private-ipv4"]
