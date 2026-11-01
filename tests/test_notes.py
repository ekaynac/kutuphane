"""R1 agent memory, the write core (docs/24 §3–§8, slice A): T1–T19 (A parts) and T38."""
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import jwt
import psycopg
import pytest
from cryptography.hazmat.primitives.asymmetric import ed25519, rsa
from starlette.testclient import TestClient

import kutuphane
from kutuphane import (authz, canonical, catalog, cli, db, gate, ids, kstd, notes, notesquery, packages, profiles,
                       retrieval, search, server)
from kutuphane import origin as origins
from kutuphane.gate import Actor
from kutuphane.identity import Verifier
from kutuphane.policy import make_policy
from kutuphane.source import read_source
from test_egress_audit import FakeBridge
from test_identity import AUD, ISS, token

U, A, B = "user:ayse", "agent:kobra-7", "user:mehmet"
J = "hafiza"
LOCAL = make_policy(sensitivity="normal", egress="local_only", protection="standard")
CLOUD = make_policy(sensitivity="normal", egress="cloud_ok", protection="standard")
PUBLIC = "http://kutuphane.test"
CODE_REPO = """
CREATE TABLE IF NOT EXISTS code_repo (
    book text NOT NULL REFERENCES journal(book), slug text NOT NULL, git_dir text NOT NULL,
    object_format text NOT NULL, refs text[] NOT NULL, added_by text NOT NULL,
    added_at timestamptz NOT NULL DEFAULT now(), removed_at timestamptz, PRIMARY KEY (book, slug))
"""  # migration 017 (slice C) when present; the subset the write path reads


def mcp(principal=A, behalf=U, **kw) -> Actor:
    return Actor(principal, behalf, channel="mcp", **kw)


def http(principal=U, **kw) -> Actor:
    return Actor(principal, channel="http", **kw)


def journal(conn, book=J, *, search=True, ai_input=True, policy=LOCAL):
    return notes.create_journal(conn, book=book, title=book, search=search, ai_input=ai_input, policy=policy,
                                by="user:admin")


def allow(conn, book, *modes, user=U, agent=A):
    for mode in modes:
        authz.grant(conn, f"book:{book}", mode, user)
        if agent:
            authz.delegate(conn, delegator=user, delegate_to=agent, obj=f"book:{book}", mode=mode,
                           expires_at=datetime.now(timezone.utc) + timedelta(hours=1))


def handle(conn, book) -> str:
    row = conn.execute("SELECT book, content_id, profile_id, path, ordinal FROM chunk WHERE book = %s "
                       "ORDER BY path, ordinal LIMIT 1", (book,)).fetchone()
    return f"{row[0]}@{row[1]}/{row[2]}/{row[3]}#{row[4]}"


@pytest.fixture
def env(conn, okf_dir):
    catalog.publish(conn, book="kitap", title="kitap", files=read_source(okf_dir), policy=LOCAL,
                    profile=profiles.spec("chunked"))
    journal(conn)
    allow(conn, J, "read", "propose")
    allow(conn, "kitap", "read")
    return conn


@pytest.fixture
def fake():
    f = FakeBridge()
    yield f
    f.server.shutdown()


def propose(conn, actor, text="Retry loop in run.py hides timeouts", embedder=None, **args):
    return notes.propose(conn, actor, {"book": J, "kind": "finding", "text": text, **args}, embedder)[0]


def row(conn, sql, *params):
    return conn.execute(sql, params).fetchone()


def rights(conn, seq) -> tuple:
    """A note's (search, ai_input) ANDed with the current rights of the journals of its closure."""
    return row(conn, "SELECT n.search AND j.search, n.ai_input AND j.ai_input "
                     "FROM note n JOIN note_journal j ON j.seq = n.seq WHERE n.seq = %s", seq)


def note_count(conn) -> int:
    return row(conn, "SELECT count(*) FROM note")[0]


# --- T1, T2, T3: origin from the write path --------------------------------------------------------------------

def test_an_agent_proposes_over_mcp_a_pending_model_note(env):  # T1
    r = propose(env, mcp(client_id="adc-orchestrator"))
    assert r["status"] == "created" and r["standing"] == "pending" and r["origin"] == "model"
    assert r["origin_notice"] is None and r["recurrence"] == 1 and r["vector"] == "skipped:no_route"
    assert re.fullmatch(rf"{J}@nt_[0-9a-f]{{64}}", r["ref"])
    w = row(env, "SELECT principal, on_behalf_of, channel, client_id, origin, creates FROM write_record")
    assert w == (A, U, "mcp", "adc-orchestrator", "model", True)  # client_id is recorded only
    assert row(env, "SELECT count(*) FROM standing_event")[0] == 0  # no event = pending
    assert notes.effective_standing(env, [row(env, "SELECT seq FROM note")[0]], notes.NOW) \
        == {row(env, "SELECT seq FROM note")[0]: ("pending", None)}


def test_an_origin_claim_is_refused_and_the_database_refuses_forbidden_origins(env):  # T2
    r = propose(env, mcp(), origin="human")
    assert (r["origin"], r["origin_notice"]) == ("model", "origin-claim-refused")
    assert row(env, "SELECT origin_requested, origin, notice FROM write_record") == ("human", "model",
                                                                                    "origin-claim-refused")
    seq = row(env, "SELECT seq FROM note")[0]
    insert = ("INSERT INTO write_record (correlation_id, action, note_seq, creates, principal, on_behalf_of, channel, "
              "origin) VALUES ('c', 'propose', %s, false, %s, %s, %s, %s)")
    for principal, behalf, channel, value in [(U, None, "http", "human"), (A, None, "http", "unknown"),
                                              (A, U, "http", "unknown"), (U, None, "mcp", "unknown")]:
        with pytest.raises(psycopg.errors.CheckViolation):
            env.execute(insert, (seq, principal, behalf, channel, value))


def test_a_user_token_is_model_over_mcp_and_unknown_over_http(env):  # T3
    assert propose(env, mcp(U, None), text="over mcp")["origin"] == "model"
    assert propose(env, http(client_id="kutuphane-ui"), text="over http")["origin"] == "unknown"
    assert propose(env, http(), text="asks for model", origin="model")["origin"] == "model"
    seq = row(env, "SELECT seq FROM note WHERE body = 'over http'")[0]
    assert origins.shown(env, [seq], None)[seq][0] == "unknown"


def test_the_shown_origin_is_the_lowest_over_the_writes(env):
    propose(env, http(), text="same")
    seq = row(env, "SELECT seq FROM note")[0]
    assert origins.shown(env, [seq], None)[seq][0] == "unknown"
    propose(env, mcp(), text="same")
    assert origins.shown(env, [seq], None)[seq] == ("model", None, None) and rights(env, seq) == (True, True)


# --- T4, T5, T6: authorization before work, rollback, secrets --------------------------------------------------

@dataclass(frozen=True)
class FakeCite:
    repo: str
    commit: str
    path: str
    line_start: int
    line_end: int
    symbol: str | None = None

    def __str__(self):
        return f"{self.repo}@{self.commit}:{self.path}:{self.line_start}-{self.line_end}"


class FakeCodeRepo:
    """Stands in for slice C's coderepo: parse is pure; excerpt is where git would run."""

    def __init__(self):
        self.excerpts = []

    def parse(self, text):
        m = re.fullmatch(r"([a-z0-9._-]+)@([0-9a-f]{40}):(.+):(\d+)-(\d+)", text)
        if not m:
            raise ValueError("malformed code citation")
        return FakeCite(m[1], m[2], m[3], int(m[4]), int(m[5]))

    def excerpt(self, conn, book, cite):
        self.excerpts.append((book, str(cite)))
        return b"\x01" * 32


@pytest.fixture
def code(env, monkeypatch):
    fake = FakeCodeRepo()
    monkeypatch.setitem(sys.modules, "kutuphane.coderepo", fake)
    monkeypatch.setattr(kutuphane, "coderepo", fake, raising=False)
    env.execute(CODE_REPO)
    env.execute("INSERT INTO code_repo (book, slug, git_dir, object_format, refs, added_by) "
                "VALUES (%s, 'adc', '/srv/git/adc.git', 'sha1', '{refs/heads/*}', 'user:admin')", (J,))
    return fake


CITE = "adc@" + "3f" * 20 + ":src/run.py:40-52"


def test_a_code_citation_is_stored_with_its_excerpt_hash(env, code):
    r = propose(env, mcp(), citations=[CITE], scope={"repo": "adc", "branch": "main", "paths": ["src/**"]},
                commit="3f" * 20)
    assert r["status"] == "created" and code.excerpts == [(J, CITE)]
    assert row(env, "SELECT kind, repo, commit, line_start, line_end, excerpt_sha256 FROM note_citation") == \
        ("code", "adc", "3f" * 20, 40, 52, b"\x01" * 32)
    assert row(env, "SELECT scope_paths, scope_path_re FROM note") == (["src/**"], ["^src/.*$"])


def test_no_right_refuses_before_any_git_process_or_model_call(env, code, fake):  # T4
    other = "kitap2"
    catalog.publish(env, book=other, title=other, files=read_source(os.path.join(os.path.dirname(__file__),
                                                                                 "fixtures", "okf-kitap")),
                    policy=LOCAL, profile=profiles.spec("chunked"))
    no_propose = mcp("agent:yabanci", None)
    with pytest.raises(gate.Denied):
        propose(env, no_propose, citations=[CITE], embedder=fake.embedder())
    with pytest.raises(gate.Denied):  # propose on the journal, but no read on the cited book
        propose(env, mcp(), citations=[CITE, handle(env, other)], embedder=fake.embedder())
    assert code.excerpts == [] and fake.requests == [] and note_count(env) == 0
    assert row(env, "SELECT count(*) FROM model_call")[0] == 0
    refused = env.execute("SELECT principal, object, mode FROM access_event WHERE NOT allowed ORDER BY id").fetchall()
    assert refused == [("agent:yabanci", f"book:{J}", "propose"), (A, f"book:{other}", "read")]


@pytest.mark.parametrize("book", [J, "kitap"])
@pytest.mark.parametrize("when", ["embedding", "transaction"])
def test_a_right_revoked_before_the_commit_rolls_back(env, conn2, fake, monkeypatch, book, when):  # T5
    delegation = row(env, "SELECT id FROM delegation WHERE object = %s AND mode = %s",
                     f"book:{book}", "propose" if book == J else "read")[0]
    revoke = lambda: authz.revoke_delegation(conn2, delegation)  # noqa: E731 - another session commits it
    if when == "embedding":
        fake.on_request = revoke
    else:  # inside the write transaction, after the inserts' lock and before the final decision
        lock = notes._lock
        monkeypatch.setattr(notes, "_lock", lambda c: (lock(c), revoke()))
    with pytest.raises(gate.Denied):
        propose(env, mcp(), citations=[handle(env, "kitap")], embedder=fake.embedder())
    assert note_count(env) == 0 and row(env, "SELECT count(*) FROM write_record")[0] == 0
    assert row(env, "SELECT count(*) FROM note_vector")[0] == 0
    reason = row(env, "SELECT reason FROM access_event WHERE NOT allowed")[0]
    assert reason.startswith("revoked before delivery" if when == "transaction" else "no current right")


def test_credential_like_text_is_refused_without_its_value(env):  # T6
    secret = "ghp_" + "a1B2c3D4e5F6g7H8i9J0k1L2"
    with pytest.raises(ValueError) as exc:
        propose(env, mcp(), text=f"the deploy token is {secret}")
    assert "access-token" in str(exc.value) and secret not in str(exc.value)
    assert note_count(env) == 0
    logged = env.execute("SELECT * FROM access_event").fetchall()
    assert secret not in json.dumps([list(map(str, r)) for r in logged])


# --- T7, T8, T9: identity, candidates, links -------------------------------------------------------------------

def test_the_same_bytes_are_one_note_and_keep_their_standing(env, monkeypatch):  # T7
    first = propose(env, mcp())
    again = propose(env, mcp())
    assert again["ref"] == first["ref"] and again["status"] == "existing" and again["recurrence"] == 2
    assert again["standing"] == "pending" and note_count(env) == 1
    authz.grant(env, f"book:{J}", "curate", "user:kurator")
    notes.set_standing(env, first["ref"], "rejected", curator="user:kurator", reason="not reproducible")
    third = propose(env, mcp())
    assert third["standing"] == "rejected" and third["recurrence"] == 3  # a re-proposal never reopens
    seq = row(env, "SELECT seq FROM note")[0]
    assert notes.effective_standing(env, [seq], notes.NOW)[seq][0] == "rejected"


def test_variants_are_candidates_never_merged_or_linked(env, fake):  # T8
    original = propose(env, mcp(), embedder=fake.embedder())
    variant = propose(env, mcp(), text="retry  loop in RUN.PY hides timeouts", embedder=fake.embedder())
    assert variant["status"] == "created" and note_count(env) == 2
    assert variant["candidates"][0] | {"text": None} == {
        "ref": original["ref"], "match": "normalized", "similarity": None, "kind": "finding", "standing": "pending",
        "text": None, "withheld": None}
    similar = propose(env, mcp(), text="Retry loop in run.py hides timeouts often", embedder=fake.embedder())
    vector = [c for c in similar["candidates"] if c["match"] == "vector"]
    assert vector and vector[0]["similarity"] >= 0.9 and similar["vector"] == "stored"
    assert row(env, "SELECT count(*) FROM note_link")[0] == 0 and note_count(env) == 3


def test_creation_links_are_part_of_the_identity(env):  # T9
    base = propose(env, mcp(), text="the base finding")
    plain = propose(env, mcp())
    linked = propose(env, mcp(), links=[{"type": "about", "ref": base["ref"]}])
    assert linked["ref"] != plain["ref"] and linked["status"] == "created"
    plain_seq = row(env, "SELECT seq FROM note WHERE id = %s", plain["ref"].split("@")[1])[0]
    assert row(env, "SELECT count(*) FROM note_link WHERE src = %s", plain_seq)[0] == 0  # unchanged
    for kind in notes.CREATION_ONLY:
        with pytest.raises(ValueError, match="creation link"):
            notes.link(env, mcp(), plain["ref"], kind, base["ref"])
    result, created = notes.link(env, mcp(), plain["ref"], "contradicts", base["ref"])
    assert created and result == {"src": plain["ref"], "type": "contradicts", "dst": base["ref"],
                                  "status": "created"}
    assert notes.link(env, mcp(), plain["ref"], "contradicts", base["ref"]) == ({**result, "status": "existing"},
                                                                                False)
    assert row(env, "SELECT count(*) FROM write_record WHERE action = 'link'")[0] == 1


def test_link_rules(env):
    a, b = propose(env, mcp(), text="a"), propose(env, mcp(), text="b")
    journal(env, "baska")
    allow(env, "baska", "read", "propose")
    c = notes.propose(env, mcp(), {"book": "baska", "kind": "lesson", "text": "c"})[0]
    with pytest.raises(ValueError, match="one book"):
        notes.link(env, mcp(), a["ref"], "same_as", c["ref"])
    assert notes.link(env, mcp(), a["ref"], "contradicts", c["ref"])[1]  # across books, both readable
    with pytest.raises(ValueError, match="passage"):
        notes.link(env, mcp(), a["ref"], "fixed_by", handle(env, "kitap"))
    assert notes.link(env, mcp(), a["ref"], "about", handle(env, "kitap"))[1]
    with pytest.raises(ValueError, match="itself"):
        notes.link(env, mcp(), a["ref"], "same_as", a["ref"])
    assert notes.link(env, mcp(), b["ref"], "same_as", a["ref"])[1]
    assert propose(env, mcp(), text="a")["recurrence"] == 3  # recurrence over the cluster {a, b}
    seqs = sorted(s for (s,) in env.execute("SELECT seq FROM note WHERE book = %s", (J,)))
    assert notes.clusters(env, J, notes.NOW) == {seqs[0]: seqs[0], seqs[1]: seqs[0]}
    with pytest.raises(gate.Denied):  # propose on the source book is needed
        notes.link(env, mcp("agent:yabanci", None), a["ref"], "about", b["ref"])


def test_creation_links_point_to_existing_older_notes(env):
    with pytest.raises(gate.NotFound):
        propose(env, mcp(), links=[{"type": "derived_from", "ref": f"{J}@nt_" + "0" * 64}])
    with pytest.raises(ValueError, match="twice"):
        base = propose(env, mcp(), text="base")
        propose(env, mcp(), links=[{"type": "about", "ref": base["ref"]}, {"type": "about", "ref": base["ref"]}])


def test_the_database_binds_creation_links_to_their_write(env, okf_dir):  # T10
    for text in ("a", "b", "b"):  # the second b is a non-creating propose
        propose(env, mcp(), text=text)
    (sa, wa), (sb, wb) = env.execute("SELECT note_seq, seq FROM write_record WHERE creates ORDER BY seq").fetchall()
    wb2 = row(env, "SELECT seq FROM write_record WHERE NOT creates")[0]
    insert = ("INSERT INTO note_link (src, src_book, type, dst_note, dst_note_book, creation, write_seq) "
              "VALUES (%s, %s, %s, %s, %s, %s, %s)")
    with pytest.raises(psycopg.errors.RaiseException, match="is written"):  # 039: only in the note's transaction
        env.execute(insert, (sb, J, "about", sa, J, True, wb))
    cid = row(env, "SELECT content_id, profile_id FROM chunk LIMIT 1")
    with env.transaction(force_rollback=True):
        # the keys hold inside the transaction that writes note b too (the owner plays that transaction here)
        env.execute("UPDATE note SET written_xact = pg_current_xact_id() WHERE seq = %s", (sb,))
        with pytest.raises(psycopg.errors.ForeignKeyViolation), env.transaction():  # the write of another note
            env.execute(insert, (sb, J, "about", sa, J, True, wa))
        with pytest.raises(psycopg.errors.ForeignKeyViolation), env.transaction():  # a non-creating propose
            env.execute(insert, (sb, J, "about", sa, J, True, wb2))
        with pytest.raises(psycopg.errors.ForeignKeyViolation), env.transaction():  # a passage that does not exist
            env.execute("INSERT INTO note_link (src, src_book, type, dst_book, dst_content_id, dst_profile_id, "
                        "dst_path, dst_ordinal, creation, write_seq) "
                        "VALUES (%s, %s, 'about', 'kitap', %s, %s, 'yok.md', 0, true, %s)",
                        (sb, J, cid[0], cid[1], wb))
    journal(env, "baska")
    allow(env, "baska", "read", "propose")
    notes.propose(env, mcp(), {"book": "baska", "kind": "lesson", "text": "c"})
    sc, wl = row(env, "SELECT seq FROM note WHERE book = 'baska'")[0], wb
    with pytest.raises(psycopg.errors.CheckViolation):  # same_as across books
        env.execute(insert, (sc, "baska", "same_as", sa, J, False, wl))


# --- T11, T12, T13: idempotency, receipt level, candidate rights -----------------------------------------------

def test_idempotent_retries(env):  # T11
    request = {"book": J, "kind": "finding", "text": "x", "idempotency_key": "key-0001"}
    first, retry = notes.propose(env, mcp(), request)
    again, retried = notes.propose(env, mcp(), {**request, "citations": [], "links": []})
    assert (retry, retried) == (False, True) and again == first
    assert row(env, "SELECT count(*) FROM write_record")[0] == 1
    with pytest.raises(ids.IdempotencyConflict):
        propose(env, mcp(), text="y", idempotency_key="key-0001")
    authz.grant(env, f"book:{J}", "read", "user:mehmet")
    authz.grant(env, f"book:{J}", "propose", "user:mehmet")
    allow(env, J, "read", "propose", user="user:mehmet")
    assert propose(env, mcp(A, "user:mehmet"), text="y", idempotency_key="key-0001")["status"] == "created"
    assert propose(env, mcp(U, None), text="z", idempotency_key="key-0001")["status"] == "created"
    assert row(env, "SELECT count(*) FROM write_record")[0] == 3


def test_a_retry_runs_the_pre_decision_again(env):
    propose(env, mcp(), text="x", idempotency_key="key-0002")
    authz.revoke_delegation(env, row(env, "SELECT id FROM delegation WHERE object = %s AND mode = 'propose'",
                                     f"book:{J}")[0])
    with pytest.raises(gate.Denied):
        propose(env, mcp(), text="x", idempotency_key="key-0002")


def test_a_propose_only_caller_gets_a_minimal_receipt(env):  # T12
    authz.grant(env, f"book:{J}", "propose", "agent:yazar")
    new = propose(env, mcp("agent:yazar", None), text="known")
    existing = propose(env, mcp("agent:yazar", None), text="known")
    assert new == {"ref": new["ref"], "status": "recorded", "origin": "model", "origin_notice": None}
    assert existing == new
    assert propose(env, mcp())["recurrence"] == 1


def test_candidates_come_only_from_readable_searchable_books(env):  # T13
    journal(env, "baska")
    journal(env, "kapali", search=False)
    authz.grant(env, "book:baska", "propose", U)
    authz.grant(env, "book:kapali", "propose", U)
    for book in ("baska", "kapali"):
        notes.propose(env, http(), {"book": book, "kind": "finding", "text": "Shared Text"})
    receipt = propose(env, http(), text="shared text")
    assert receipt["candidates"] == []  # baska is not readable, kapali does not allow search
    authz.grant(env, "book:baska", "read", U)
    authz.grant(env, "book:kapali", "read", U)
    receipt = propose(env, http(), text="shared  text")
    assert [c["ref"].split("@")[0] for c in receipt["candidates"]] == [J, "baska"]
    logged = env.execute("SELECT object, items FROM access_event WHERE action = 'propose' AND mode = 'read' "
                         "AND items IS NOT NULL ORDER BY id").fetchall()
    assert [o for o, _ in logged][-2:] == ["book:baska", f"book:{J}"]
    assert logged[-1][1] == [{"ref": receipt["candidates"][0]["ref"], "standing_seq": None}]


def test_a_candidate_book_revoked_after_selection_is_not_in_the_receipt(env, conn2, monkeypatch):  # Astra #13 (2)
    journal(env, "baska")
    authz.grant(env, "book:baska", "propose", U)
    authz.grant(env, "book:baska", "read", U)
    notes.propose(env, http(), {"book": "baska", "kind": "finding", "text": "Shared Text"})
    real = notes._candidates

    def racing(*args):  # another session revokes the candidate book after the candidates were chosen
        out = real(*args)
        authz.revoke(conn2, "book:baska", "read", U)
        return out
    monkeypatch.setattr(notes, "_candidates", racing)
    receipt = propose(env, http(), text="shared text")
    assert receipt["status"] == "created" and receipt["candidates"] == []
    assert "Shared Text" not in json.dumps(receipt)
    logged = env.execute("SELECT count(*) FROM access_event WHERE action = 'propose' AND mode = 'read' "
                         "AND object = 'book:baska' AND items IS NOT NULL").fetchone()[0]
    assert logged == 0


def test_journal_read_revoked_after_the_receipt_level_gives_the_minimal_receipt(env, conn2, monkeypatch):  # #13 (2)
    propose(env, http(), text="known before")
    real = notes._candidates

    def racing(*args):  # the journal's read is lost after the full receipt level was chosen
        out = real(*args)
        authz.revoke(conn2, f"book:{J}", "read", U)
        return out
    monkeypatch.setattr(notes, "_candidates", racing)
    receipt = propose(env, http(), text="Known before")
    assert receipt == {"ref": receipt["ref"], "status": "recorded", "origin": "unknown", "origin_notice": None}
    logged = env.execute("SELECT count(*) FROM access_event WHERE action = 'propose' AND mode = 'read' "
                         "AND items IS NOT NULL AND object = %s", (f"book:{J}",)).fetchone()[0]
    assert logged == 0  # the candidate from the journal was never delivered


def test_class_count_and_guard_due(env):
    first = propose(env, mcp(), text="sql built by string concatenation", class_key="cwe-89")
    assert (first["class_count"], first["guard_due"]) == (1, False)
    second = propose(env, mcp(), text="another query concatenates input", class_key="cwe-89")
    assert (second["class_count"], second["guard_due"]) == (2, True)
    assert second["candidates"][0]["match"] == "class"
    notes.link(env, mcp(), second["ref"], "same_as", first["ref"])
    third = propose(env, mcp(), text="third", class_key="cwe-89")
    assert third["class_count"] == 2  # two of the three are one cluster
    authz.grant(env, f"book:{J}", "curate", "user:kurator")
    guard = propose(env, mcp(), kind="convention", text="use bound parameters", class_key="cwe-89")
    notes.set_standing(env, guard["ref"], "approved", curator="user:kurator", reason="the guard")
    assert propose(env, mcp(), text="fourth", class_key="cwe-89")["guard_due"] is False


def test_class_count_counts_evidence_clusters_only(env):  # G31 (pilot 2): the rules of a class are not repeats
    first = propose(env, mcp(), text="unknown is not down", class_key="monitor-unknown")
    rule = propose(env, mcp(), kind="convention", text="treat unknown as not confirmed", class_key="monitor-unknown")
    assert (rule["class_count"], rule["guard_due"]) == (1, False)
    plan = propose(env, mcp(), kind="decision_proposal", text="page only on down", class_key="monitor-unknown")
    assert (plan["class_count"], plan["guard_due"]) == (1, False)
    again = propose(env, mcp(), kind="dead_end", text="restarting the agent did not help", class_key="monitor-unknown")
    assert (again["class_count"], again["guard_due"]) == (2, True)
    assert first["class_count"] == 1


def test_neighbours_of_a_passage_follow_its_citations(env):  # G32 (pilot 2): a citation is an edge too
    passage = handle(env, "kitap")
    authz.grant(env, f"book:{J}", "curate", "user:kurator")
    kept, open_, refused = (propose(env, mcp(), text=t, citations=[passage])["ref"] for t in ("kept", "open", "no"))
    notes.set_standing(env, kept, "approved", curator="user:kurator", reason="r")
    notes.set_standing(env, refused, "rejected", curator="user:kurator", reason="r")

    def near(**kw):
        out = notesquery.neighbours(env, Actor(U), for_model=False, ref=passage, **kw)
        return [n["ref"] for n in out["nodes"]], out["edges"]
    assert near() == ([kept], [{"src": kept, "type": "cites", "dst": passage}])
    assert near(sets=["open"])[0] == [open_]                                        # the same gates as links
    assert near(sets=["history"])[0] == [refused]
    assert near(types=["cites"])[0] == [kept] and near(types=["about"]) == ([], [])
    assert near(direction="out") == ([], [])
    deeper = propose(env, mcp(), text="builds on kept", links=[{"type": "about", "ref": kept}])["ref"]
    notes.set_standing(env, deeper, "approved", curator="user:kurator", reason="r")
    assert near(depth=2)[0] == [kept, deeper]


def test_a_journal_in_the_search_filter_gives_a_notice(env):  # G33 (pilot 2): not a silent empty list
    propose(env, mcp(), text="Yedekler her gece alınır")
    with pytest.raises(ValueError, match="journal: use query_notes"):
        search.search(env, Actor(U), "yedek", scope=search.Scope.of([J]))
    with pytest.raises(ValueError, match="journal: use query_notes"):                # ask uses the same retrieval
        retrieval.retrieve(env, Actor(U), "yedek", scope=search.Scope.of([J, "kitap"]))
    journal(env, "kapali")                                                           # no read: as a missing book
    assert search.search(env, Actor(U), "yedek", scope=search.Scope.of(["kapali"])) == []
    assert search.search(env, Actor(U), "yedek")                                     # no filter: books only


# --- T14, T15, T16: journal permissions and rights by derivation -----------------------------------------------

def test_a_journal_without_search_has_no_tsv_vector_or_candidates(env, fake):  # T14
    journal(env, "kapali", search=False)
    allow(env, "kapali", "read", "propose")
    for text in ("same text", "Same Text"):
        r = notes.propose(env, mcp(), {"book": "kapali", "kind": "finding", "text": text}, fake.embedder())[0]
    assert r["candidates"] == [] and r["vector"] == "skipped:search"
    assert env.execute("SELECT search, tsv FROM note").fetchall() == [(False, None), (False, None)]
    assert row(env, "SELECT count(*) FROM model_call")[0] == 0 and fake.requests == []


def test_a_journal_without_ai_input_never_calls_a_model_and_withholds_text(env, fake):  # T15
    journal(env, "ozel", ai_input=False)
    allow(env, "ozel", "read", "propose")
    notes.propose(env, mcp(), {"book": "ozel", "kind": "finding", "text": "private finding"}, fake.embedder())
    to_model = notes.propose(env, mcp(), {"book": "ozel", "kind": "finding", "text": "Private finding"},
                             fake.embedder())[0]
    assert to_model["vector"] == "skipped:ai_input" and row(env, "SELECT count(*) FROM model_call")[0] == 0
    assert to_model["candidates"][0]["text"] is None and to_model["candidates"][0]["withheld"] == notes.WITHHELD
    to_person = notes.propose(env, http(), {"book": "ozel", "kind": "finding", "text": "PRIVATE finding"})[0]
    assert {c["text"] for c in to_person["candidates"]} == {"private finding", "Private finding"}
    seq = row(env, "SELECT seq FROM note WHERE book = 'ozel' ORDER BY seq LIMIT 1")[0]
    assert rights(env, seq) == (True, False)


def test_rights_follow_derivation(env, okf_dir, tmp_path, fake):  # T16
    restricted = tmp_path / "gizli"
    restricted.mkdir()
    (restricted / "not.md").write_text("# Gizli\n\nYedekler her gece alınır.\n", encoding="utf-8")
    stated = kstd.init(read_source(restricted), "ACME <kb@acme.example>").replace(  # init states no term (D74)
        "# ai_use: {search: y|n, ai_input: y|n, train: y|n}", "ai_use: {search: y, ai_input: n, train: n}")
    (restricted / kstd.MANIFEST).write_text(stated)
    catalog.publish(env, book="gizli", title="gizli", files=read_source(restricted), policy=CLOUD,
                    profile=profiles.spec("chunked"))
    allow(env, "gizli", "read")
    cited = propose(env, mcp(), text="cites a restricted passage", citations=[handle(env, "gizli")],
                    embedder=fake.embedder())
    assert cited["vector"] == "skipped:ai_input"
    derived = propose(env, mcp(), text="derived from that note", links=[{"type": "derived_from", "ref": cited["ref"]}],
                      embedder=fake.embedder())
    assert derived["vector"] == "skipped:ai_input"
    assert env.execute("SELECT ai_input, search, source_books FROM note ORDER BY seq").fetchall() == [
        (False, True, ["gizli", J]), (False, True, ["gizli", J])]
    assert fake.requests == []
    local = propose(env, mcp(), text="derived from a local_only book",
                    links=[{"type": "derived_from", "ref": handle(env, "kitap")}],
                    embedder=fake.embedder(route_class="cloud"))
    assert local["vector"] == "skipped:egress" and fake.requests == []
    assert row(env, "SELECT error, source_books FROM model_call") == ("not_sent:egress_policy", [J, "kitap"])


def test_journals_from_the_cli_and_restriction_only_tightens(conn, monkeypatch, capsys):
    monkeypatch.setenv(db.DSN_ENV, os.environ["KUTUPHANE_TEST_DSN"])
    create = ["journal", "create", J, "--search", "y", "--ai-input", "y", "--sensitivity", "normal",
              "--egress", "local_only", "--protection", "standard", "--by", "user:admin"]
    assert cli.main(create) == 0 and json.loads(capsys.readouterr().out)["search"] is True
    with pytest.raises(SystemExit):  # search and AI input must both be stated (missing = deny)
        cli.main(["journal", "create", "eksik", "--search", "y", "--sensitivity", "normal", "--egress",
                  "local_only", "--protection", "standard", "--by", "user:admin"])
    assert cli.main(["journal", "restrict", J, "--no-ai-input"]) == 0
    assert json.loads(capsys.readouterr().out) == {"book": J, "search": True, "ai_input": False, "train": False}
    allow(conn, J, "read", "propose")
    propose(conn, http(), text="after restriction")
    assert rights(conn, row(conn, "SELECT seq FROM note")[0]) == (True, False)
    with pytest.raises(ValueError):
        notes.restrict_journal(conn, J)


def test_a_journal_is_a_new_book_with_the_journal_profile(env):
    with pytest.raises(ValueError, match="new book"):
        journal(env, "kitap")
    state = catalog.book_state(env, J)
    assert state["content_id"] is None and state["profile_id"] == ids.profile_id(profiles.spec("journal"))
    assert row(env, "SELECT profile_id FROM note LIMIT 1") is None
    with pytest.raises(packages.PackageError, match="no content version"):  # §14: a journal is not exported
        packages.export(env, J, ed25519.Ed25519PrivateKey.generate())


# --- T17, T18, T19: Standing, curation, supersession -----------------------------------------------------------

def test_the_app_role_cannot_write_standing(env):  # T17
    role = "kutuphane_app_test"
    env.execute(f"DO $$ BEGIN CREATE ROLE {role} NOLOGIN; EXCEPTION WHEN duplicate_object THEN NULL; END $$")
    script = open(os.path.join(os.path.dirname(__file__), "..", "deploy", "db-roles.sql"), encoding="utf-8").read()
    env.execute(script.replace("kutuphane_app", role))
    r = propose(env, mcp())
    seq = row(env, "SELECT seq FROM note")[0]
    try:
        env.execute(f"SET ROLE {role}")
        assert row(env, "SELECT count(*) FROM standing_event")[0] == 0  # it reads
        for sql in ("INSERT INTO standing_event (note_seq, value, set_by, reason, correlation_id) "
                    f"VALUES ({seq}, 'approved', 'user:x', 'r', 'c')",
                    "UPDATE standing_event SET reason = 'x'", "DELETE FROM standing_event",
                    "UPDATE note SET body = 'x'", "DELETE FROM write_record", "UPDATE note_link SET type = 'about'",
                    "DELETE FROM note_citation"):
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                env.execute(sql)
        assert notes.propose(env, mcp(), {"book": J, "kind": "lesson", "text": "the app role writes notes"})[0][
            "status"] == "created"
    finally:
        env.execute("RESET ROLE")
        env.execute(f"DROP OWNED BY {role}")
    assert r["standing"] == "pending"


def test_no_mcp_tool_or_http_route_changes_standing(verifier):  # T17
    class Recorder:
        def __init__(self):
            self.names = []

        def tool(self):
            return lambda fn: self.names.append(fn.__name__) or fn

    deps = server.Deps("postgresql://unused", None, None, None)
    recorder = Recorder()
    notes.register_mcp(recorder, deps)
    assert recorder.names == ["propose_note", "link_notes"]
    routes = [(r.path, sorted(r.methods - {"HEAD"})) for r in notes.http_routes(deps, lambda work: work)]
    assert routes == [("/v1/notes", ["POST"]), ("/v1/notes/links", ["POST"])]
    app = server.create_app(dsn="postgresql://unused", verifier=verifier, bridge=None, model=None, public_url=PUBLIC)
    assert not [r.path for r in app.routes if "standing" in getattr(r, "path", "")]


def test_grant_curate_needs_the_curator_credential(env, monkeypatch, capsys):  # #67 comment, D78
    grant = ["grant", f"book:{J}", "curate", "user:kurator"]
    monkeypatch.setenv("KUTUPHANE_DSN", os.environ["KUTUPHANE_TEST_DSN"])
    monkeypatch.delenv(db.CURATOR_DSN_ENV, raising=False)
    assert cli.main(grant) == 2 and db.CURATOR_DSN_ENV in capsys.readouterr().err
    assert row(env, "SELECT count(*) FROM grant_tuple WHERE relation = 'curate'") == (0,)
    assert cli.main(["grant", f"book:{J}", "read", "user:kurator"]) == 0  # other modes keep the app credential
    monkeypatch.setenv(db.CURATOR_DSN_ENV, os.environ["KUTUPHANE_TEST_DSN"])
    assert cli.main(grant) == 0
    assert row(env, "SELECT count(*) FROM grant_tuple WHERE relation = 'curate'") == (1,)


def test_curation_needs_curate_and_the_curator_credential(env, monkeypatch, capsys):  # T18
    ref = propose(env, mcp())["ref"]
    monkeypatch.delenv(db.CURATOR_DSN_ENV, raising=False)
    standing = ["note", "standing", ref, "approved", "--curator", "user:kurator", "--reason", "ok"]
    assert cli.main(standing) == 2 and db.CURATOR_DSN_ENV in capsys.readouterr().err
    monkeypatch.setenv(db.CURATOR_DSN_ENV, os.environ["KUTUPHANE_TEST_DSN"])
    assert cli.main(standing) == 3 and "curate" in capsys.readouterr().err
    authz.grant(env, f"book:{J}", "curate", "user:kurator")
    assert cli.main(standing) == 0 and json.loads(capsys.readouterr().out)["standing"] == "approved"
    assert row(env, "SELECT value, set_by, reason FROM standing_event") == ("approved", "user:kurator", "ok")
    for subject in ("agent:kobra-7", "role:ekip#member", "role:ekip"):
        with pytest.raises(psycopg.errors.CheckViolation):
            env.execute("INSERT INTO grant_tuple (object, relation, subject) VALUES (%s, 'curate', %s)",
                        (f"book:{J}", subject))
        with pytest.raises(authz.AuthzError):
            authz.grant(env, f"book:{J}", "curate", subject)
    with pytest.raises(psycopg.errors.CheckViolation):
        env.execute("INSERT INTO delegation (delegator, delegate, object, mode, expires_at) "
                    "VALUES ('user:kurator', 'agent:kobra-7', %s, 'curate', now() + interval '1 hour')", (f"book:{J}",))
    with pytest.raises(authz.AuthzError):
        authz.delegate(env, delegator="user:kurator", delegate_to=A, obj=f"book:{J}", mode="curate",
                       expires_at=datetime.now(timezone.utc) + timedelta(hours=1))


def test_standing_transitions(env):  # T19 (A part)
    authz.grant(env, f"book:{J}", "curate", "user:kurator")

    def act(ref, value):
        return notes.set_standing(env, ref, value, curator="user:kurator", reason="r")

    a, b = propose(env, mcp(), text="a")["ref"], propose(env, mcp(), text="b")["ref"]
    assert act(a, "approved")["standing"] == "approved"
    assert act(b, "rejected")["standing"] == "rejected"
    for ref, value in ((b, "approved"), (b, "retired"), (a, "rejected"), (a, "pending"), (a, "approved")):
        with pytest.raises(ValueError, match="transition"):
            act(ref, value)
    assert act(a, "retired")["standing"] == "retired"
    assert act(a, "pending")["standing"] == "pending" and act(b, "pending")["standing"] == "pending"
    seqs = [s for (s,) in env.execute("SELECT seq FROM note ORDER BY seq")]
    events = notes.effective_standing(env, seqs, notes.NOW)
    assert [v for v, _ in events.values()] == ["pending", "pending"] and all(e for _, e in events.values())
    first_event = row(env, "SELECT min(seq) FROM standing_event")[0]
    assert notes.effective_standing(env, seqs[:1], first_event)[seqs[0]] == ("approved", first_event)  # as of w


def test_supersession_retires_only_a_predecessor_with_the_same_scope(env, code):  # T19, §8.3
    authz.grant(env, f"book:{J}", "curate", "user:kurator")

    def act(ref, value):
        return notes.set_standing(env, ref, value, curator="user:kurator", reason="r")

    scope = {"repo": "adc", "branch": "main", "paths": ["src/db/**"]}
    old = propose(env, mcp(), kind="convention", text="use the pool", scope=scope)["ref"]
    other = propose(env, mcp(), kind="convention", text="use the pool v0", scope={**scope, "paths": ["src/**"]})["ref"]
    act(old, "approved")
    act(other, "approved")
    new = propose(env, mcp(), kind="convention", text="use the pool with a timeout", scope=scope,
                  links=[{"type": "supersedes", "ref": old}, {"type": "supersedes", "ref": other}])["ref"]
    out = act(new, "approved")
    assert out["retired"] == [old] and out["rules_same_repo"] == [other]
    seqs = dict(env.execute("SELECT id, seq FROM note").fetchall())
    standing = notes.effective_standing(env, [seqs[r.split("@")[1]] for r in (old, other)], notes.NOW)
    assert [v for v, _ in standing.values()] == ["retired", "approved"]
    system = row(env, "SELECT set_by, cause_seq, reason FROM standing_event WHERE set_by = 'system'")
    assert system == ("system", out["event_seq"], f"superseded by {new}")
    act(new, "retired")  # a successor that loses approval does not reopen the predecessor
    assert notes.effective_standing(env, [seqs[old.split("@")[1]]], notes.NOW)[seqs[old.split("@")[1]]][0] == \
        "retired"


def test_applies_to_is_part_of_the_id_and_of_the_same_scope(env, code):  # #164
    authz.grant(env, f"book:{J}", "curate", "user:kurator")
    plain = notes.Draft({"book": J, "kind": "convention", "text": "pin the pool"})
    assert "applies_to" not in plain.body  # a note without it keeps the id it had before #164
    bound = {"platform": ["vcenter", "esxi"], "version": ">=7,<8"}
    r = propose(env, mcp(), kind="convention", text="pin the pool", applies_to=bound)
    assert r["ref"] != f"{J}@{plain.id}"
    stored = row(env, "SELECT seq, applies_to FROM note")
    assert stored[1] == {"platform": ["esxi", "vcenter"], "version": ">=7,<8"}
    assert canonical.canonical_of(env, stored[0])[0] == r["ref"].split("@")[1]  # the stored parts give the id
    assert propose(env, mcp(), kind="convention", text="pin the pool", applies_to="vcenter")["ref"] != r["ref"]
    notes.set_standing(env, r["ref"], "approved", curator="user:kurator", reason="r")
    new = propose(env, mcp(), kind="convention", text="pin the pool to 8", applies_to={"version": ">=8"},
                  links=[{"type": "supersedes", "ref": r["ref"]}])["ref"]
    assert notes.set_standing(env, new, "approved", curator="user:kurator", reason="r").get("retired", []) == []


def test_a_supersedes_link_from_evidence_retires_nothing(env):
    authz.grant(env, f"book:{J}", "curate", "user:kurator")
    old = propose(env, mcp(), text="old")["ref"]
    notes.set_standing(env, old, "approved", curator="user:kurator", reason="r")
    new = propose(env, mcp(), text="new", links=[{"type": "supersedes", "ref": old}])["ref"]
    assert "retired" not in notes.set_standing(env, new, "approved", curator="user:kurator", reason="r")


# --- validation, limits ----------------------------------------------------------------------------------------

@pytest.mark.parametrize("args, needle", [
    ({"kind": "rumor"}, "kind"),
    ({"text": ""}, "text"),
    ({"text": "x" * 8001}, "text"),
    ({"class_key": "Bad Key"}, "class_key"),
    ({"commit": "3f" * 20}, "commit"),
    ({"scope": {"repo": "adc", "branch": "main\nx"}}, "branch"),
    ({"scope": {"repo": "adc", "paths": ["a\rb"]}}, "paths"),
    ({"scope": {"repo": "adc", "paths": ["../etc"]}}, "path"),
    ({"citations": ["kitap@ct_x/pf_y/a\x00b#0"]}, "citation"),
    ({"citations": ["kitap@ct_x/pf_y/../a#0"]}, "passage"),
    ({"links": [{"type": "cites", "ref": "x"}]}, "link"),
    ({"origin": "person"}, "origin"),
    ({"idempotency_key": "short"}, "idempotency_key"),
    ({"extra": 1}, "fields"),
    ({"applies_to": {"platform": []}}, "applies_to"),
    ({"applies_to": {"version": "7.x"}}, "applies_to"),
    ({"applies_to": {"os": "linux"}}, "applies_to"),
    ({"applies_to": {}}, "applies_to"),
    ({"applies_to": {"platform": ["a\nb"]}}, "applies_to"),
    ({"citations": ["x"] * 21}, "citations"),
])
def test_invalid_requests_are_refused_before_any_io(env, args, needle):
    with pytest.raises(ValueError, match=needle):
        propose(env, mcp(), **args)
    assert row(env, "SELECT count(*) FROM access_event")[0] == 0


def test_the_cli_channel_does_not_write_notes(env):
    with pytest.raises(ValueError, match="MCP or HTTP"):
        propose(env, Actor(U))


def test_the_daily_write_limit(env, monkeypatch):
    monkeypatch.setenv(notes.WRITES_ENV, "2")
    propose(env, mcp(), text="1")
    propose(env, mcp(), text="2", idempotency_key="key-0003")
    assert propose(env, mcp(), text="2", idempotency_key="key-0003")["status"] == "created"  # a retry is no write
    with pytest.raises(ids.LimitExceeded):
        propose(env, mcp(), text="3")


def test_the_note_reference():
    nid = "nt_" + "a" * 64
    assert notes.parse_ref(f"adc-memory@{nid}") == ("adc-memory", nid)
    for bad in ("adc-memory@nt_abc", f"ADC@{nid}", f"adc@{nid}x", nid, None):
        with pytest.raises(ValueError):
            notes.parse_ref(bad)
    assert notes.glob_re("src/**/*.py") == r"^src/.*/[^/]*\.py$" and notes.glob_re("a?b") == "^a[^/]b$"


# --- HTTP ------------------------------------------------------------------------------------------------------

@pytest.fixture(scope="module")
def keys():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048), None


@pytest.fixture
def verifier(keys, tmp_path):
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(keys[0].public_key()))
    path = tmp_path / "jwks.json"
    path.write_text(json.dumps({"keys": [{**jwk, "kid": "k1", "use": "sig", "alg": "RS256"}]}))
    return Verifier.from_files(ISS, AUD, path)


def test_http_propose_and_link(env, keys, verifier, monkeypatch):  # §13
    app = server.create_app(dsn=os.environ["KUTUPHANE_TEST_DSN"], verifier=verifier, bridge=None, model=None,
                            public_url=PUBLIC)
    h = {"Authorization": f"Bearer {token(keys)}"}
    body = {"book": J, "kind": "finding", "text": "over http", "idempotency_key": "http-0001"}
    with TestClient(app) as client:
        created = client.post("/v1/notes", json=body, headers=h)
        assert created.status_code == 201 and created.json()["origin"] == "unknown"
        retried = client.post("/v1/notes", json=body, headers=h)
        assert retried.status_code == 200 and retried.json()["ref"] == created.json()["ref"]
        conflict = client.post("/v1/notes", json={**body, "text": "other"}, headers=h)
        assert conflict.status_code == 409 and conflict.json() == {"error": "idempotency_key reused with another "
                                                                            "request"}
        assert client.post("/v1/notes", content=b"{", headers=h).status_code == 400
        assert client.post("/v1/notes", json=body).status_code == 401
        other = client.post("/v1/notes", json={"book": J, "kind": "lesson", "text": "second"}, headers=h).json()
        link = {"src": other["ref"], "type": "about", "dst": created.json()["ref"]}
        assert client.post("/v1/notes/links", json=link, headers=h).status_code == 201
        assert client.post("/v1/notes/links", json=link, headers=h).status_code == 200
        stranger = {"Authorization": f"Bearer {token(keys, sub='mehmet')}"}
        assert client.post("/v1/notes", json={**body, "idempotency_key": None}, headers=stranger).status_code == 403
        monkeypatch.setenv(notes.WRITES_ENV, "1")
        assert client.post("/v1/notes", json={"book": J, "kind": "lesson", "text": "third"},
                           headers=h).status_code == 429


# --- T38 ---------------------------------------------------------------------------------------------------------

def test_016_applies_on_015_with_data(conn):  # T38
    conn.execute("DROP SCHEMA IF EXISTS mig_a CASCADE")
    conn.execute("CREATE SCHEMA mig_a")
    try:
        with db.connect(os.environ["KUTUPHANE_TEST_DSN"] + "?options=-csearch_path%3Dmig_a,public") as c:
            c.execute("CREATE TABLE schema_migration (name text PRIMARY KEY, applied_at timestamptz NOT NULL "
                      "DEFAULT now())")
            for script in db._scripts():
                if script.name < "016":
                    c.execute(script.read_text())
                    c.execute("INSERT INTO schema_migration (name) VALUES (%s)", (script.name,))
            c.execute("INSERT INTO book (slug, title) VALUES ('kitap', 'kitap')")
            authz.grant(c, "book:kitap", "read", U)
            authz.delegate(c, delegator=U, delegate_to=A, obj="book:kitap", mode="read",
                           expires_at=datetime.now(timezone.utc) + timedelta(hours=1))
            assert "016_notes.sql" in db.migrate(c)
            assert authz.authorize(c, A, U, "book:kitap", "read").allowed
            authz.grant(c, "book:kitap", "propose", U)
    finally:
        conn.execute("DROP SCHEMA IF EXISTS mig_a CASCADE")


def test_047_keeps_runbook_feedback_that_an_old_server_commits_during_the_upgrade(conn, conn2):
    """Astra review #21: the emptiness check must not miss a row that is committed while 047 waits for its lock."""
    import threading
    from importlib.resources import files
    conn.execute("DROP SCHEMA public CASCADE")
    conn.execute("CREATE SCHEMA public")
    scripts = sorted((f for f in files("kutuphane.migrations").iterdir() if f.name.endswith(".sql")),
                     key=lambda f: f.name)
    for script in scripts:
        if script.name < "047":
            conn.execute(script.read_text())
    with conn2.transaction():  # the old server: its feedback row is not committed when 047 starts
        conn2.execute("INSERT INTO book (slug, title) VALUES ('k', 'k')")
        conn2.execute("INSERT INTO content_version (book, id, manifest) VALUES ('k', 'c', '{}')")
        conn2.execute("INSERT INTO runbook_feedback (correlation_id, book, content_id, path, outcome, principal) "
                      "VALUES ('x', 'k', 'c', 'a.md', 'worked', 'user:a')")
        step = next(s for s in scripts if s.name.startswith("047"))
        errors = []

        def run():
            try:
                with conn.transaction():
                    conn.execute(step.read_text())
            except Exception as e:  # noqa: BLE001 (reported below)
                errors.append(e)
        t = threading.Thread(target=run)
        t.start()
        t.join(1.0)  # 047 now waits for the old server's lock
    t.join(10)
    assert not errors and not t.is_alive()
    assert conn.execute("SELECT count(*) FROM runbook_feedback").fetchone()[0] == 1
