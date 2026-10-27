"""docs/24 §9, §11 (#71): the notes read path. The rows are written with SQL in the shape of the 016 DDL, so these
tests depend only on the contract, not on the write path."""
import asyncio
import hashlib
import json
import os
import re
import subprocess
from datetime import datetime, timedelta, timezone

import pytest
from starlette.testclient import TestClient

from kutuphane import authz, coderepo, notesquery, server
from kutuphane.gate import Actor, Denied
from kutuphane.notesquery import query_notes, neighbours, open_note

U, A, V = "user:ayse", "agent:kobra-7", "user:veli"
PERSON, MODEL = Actor(U), Actor(A, U)


def _glob_re(glob: str) -> str:
    out = re.sub(r"\\\*\\\*|\\\*|\\\?", lambda m: {"\\*\\*": ".*", "\\*": "[^/]*", "\\?": "[^/]"}[m.group(0)],
                 re.escape(glob))
    return f"^{out}$"


def journal(conn, book, search=True, ai_input=True, readers=(U,)):
    conn.execute("INSERT INTO profile_version (id, spec) VALUES ('pf_journal', '{}') ON CONFLICT DO NOTHING")
    conn.execute("INSERT INTO book (slug, title) VALUES (%s, %s)", (book, book))
    conn.execute("INSERT INTO journal (book, search, ai_input, created_by) VALUES (%s, %s, %s, 'user:admin')",
                 (book, search, ai_input))
    for r in readers:
        authz.grant(conn, f"book:{book}", "read", r)


def note(conn, book, body, kind="finding", *, repo=None, branch=None, paths=(), commit=None, class_key=None,
         origin="model", creation_links=()):
    """A note and its creating propose write (and its creation links: [(type, dst seq)]). Returns the seq."""
    nid = "nt_" + hashlib.sha256(f"{book}\n{body}\n{creation_links}".encode()).hexdigest()
    s = conn.execute("SELECT search FROM journal WHERE book = %s", (book,)).fetchone()[0]
    with conn.transaction():
        seq = conn.execute(
            "INSERT INTO note (book, id, profile_id, kind, body, norm_sha256, class_key, scope_repo, scope_branch, "
            "scope_paths, scope_path_re, observed_commit, search, ai_input, source_books, tsv) VALUES "
            "(%s, %s, 'pf_journal', %s, %s, '\\x00', %s, %s, %s, %s, %s, %s, %s, true, %s, "
            " CASE WHEN %s THEN to_tsvector('turkish', %s) END) RETURNING seq",
            (book, nid, kind, body, class_key, repo, branch, list(paths), [_glob_re(p) for p in paths], commit,
             s, [book], s, body)).fetchone()[0]
        principal, behalf, channel = ("agent:kobra-7", U, "mcp") if origin == "model" else (U, None, "http")
        wseq = conn.execute(
            "INSERT INTO write_record (correlation_id, action, note_seq, creates, principal, on_behalf_of, channel, "
            "origin) VALUES ('t', 'propose', %s, true, %s, %s, %s, %s) RETURNING seq",
            (seq, principal, behalf, channel, origin)).fetchone()[0]
        for type_, dst in creation_links:
            conn.execute("INSERT INTO note_link (src, src_book, type, dst_note, dst_note_book, creation, write_seq) "
                         "VALUES (%s, %s, %s, %s, (SELECT book FROM note WHERE seq = %s), true, %s)",
                         (seq, book, type_, dst, dst, wseq))
    return seq


def again(conn, seq):
    """The same bytes proposed again: one more write record."""
    conn.execute("INSERT INTO write_record (correlation_id, action, note_seq, creates, principal, on_behalf_of, "
                 "channel, origin) VALUES ('t', 'propose', %s, false, 'agent:kobra-7', %s, 'mcp', 'model')",
                 (seq, U))


def link(conn, src, type_, dst):
    with conn.transaction():
        wseq = conn.execute("INSERT INTO write_record (correlation_id, action, creates, principal, on_behalf_of, "
                            "channel, origin) VALUES ('t', 'link', false, 'agent:kobra-7', %s, 'mcp', 'model') "
                            "RETURNING seq", (U,)).fetchone()[0]
        conn.execute("INSERT INTO note_link (src, src_book, type, dst_note, dst_note_book, creation, write_seq) VALUES "
                     "(%s, (SELECT book FROM note WHERE seq = %s), %s, %s, (SELECT book FROM note WHERE seq = %s), "
                     "false, %s)", (src, src, type_, dst, dst, wseq))


def standing(conn, seq, value):
    return conn.execute("INSERT INTO standing_event (note_seq, value, set_by, reason, correlation_id) "
                        "VALUES (%s, %s, 'user:curator', 'test', 't') RETURNING seq", (seq, value)).fetchone()[0]


def approved(conn, *args, **kw):
    seq = note(conn, *args, **kw)
    standing(conn, seq, "approved")
    return seq


def ref(conn, seq):
    return "{}@{}".format(*conn.execute("SELECT book, id FROM note WHERE seq = %s", (seq,)).fetchone())


def refs(result, key="items"):
    return [i["ref"] for i in result[key]]


def q(conn, actor=PERSON, **kw):
    return query_notes(conn, actor, for_model=actor.principal.startswith("agent:"), **kw)


@pytest.fixture
def mem(conn):
    journal(conn, "mem")
    authz.delegate(conn, delegator=U, delegate_to=A, obj="book:mem", mode="read",
                   expires_at=datetime.now(timezone.utc) + timedelta(hours=1))
    return conn


def model_calls(conn):
    return conn.execute("SELECT count(*) FROM model_call").fetchone()[0]


# --- sets and the shared predicate ----------------------------------------------------------------------------

def test_pending_is_open_not_current(mem):  # T1
    seq = note(mem, "mem", "Retry loop never ends")
    assert refs(q(mem, MODEL, sets=["open"])) == [ref(mem, seq)]
    assert q(mem, MODEL, sets=["open"])["items"][0]["standing"] == "pending"
    assert q(mem, MODEL)["items"] == []


def test_standing_moves_notes_between_sets(mem):  # T19
    a, r, t = (approved(mem, "mem", "kept"), note(mem, "mem", "refused"), approved(mem, "mem", "ran", "test_result"))
    standing(mem, r, "rejected")
    p = approved(mem, "mem", "old rule", "convention")
    s = approved(mem, "mem", "new rule", "convention", creation_links=[("supersedes", p)])
    standing(mem, p, "retired")
    assert refs(q(mem)) == [ref(mem, s), ref(mem, a)]
    hist = q(mem, sets=["history"])
    assert refs(hist) == [ref(mem, p), ref(mem, t), ref(mem, r)]
    by = {i["ref"]: i for i in hist["items"]}
    assert by[ref(mem, r)]["standing"] == "rejected" and by[ref(mem, p)]["successor"] == ref(mem, s)
    assert all(not i["current"] for i in hist["items"])


def test_bounded_rule_needs_context_in_query_and_neighbours(mem):  # T23
    rule = approved(mem, "mem", "use ? params", "convention", repo=None, class_key="cwe-89")
    mem.execute("INSERT INTO code_repo (book, slug, git_dir, object_format, refs, added_by) "
                "VALUES ('mem', 'adc', '/nonexistent', 'sha1', '{refs/heads/*}', 'user:admin')")
    bounded = approved(mem, "mem", "no f-strings in SQL", "convention", repo="adc", paths=["src/db/**"])
    ev = approved(mem, "mem", "q.py builds SQL by hand", "finding", repo="adc", paths=["src/db/**"])
    link(mem, ev, "violates", bounded)
    link(mem, ev, "violates", rule)
    out = q(mem)
    assert refs(out) == [ref(mem, ev), ref(mem, rule)] and out["excluded"]["needs_context"] == 1
    assert next(i for i in out["items"] if i["ref"] == ref(mem, ev))["scope"] == \
        {"repo": "adc", "branch": None, "paths": ["src/db/**"]}
    n = neighbours(mem, PERSON, for_model=False, ref=ref(mem, ev))
    assert [x["ref"] for x in n["nodes"]] == [ref(mem, rule)]
    assert n["edges"] == [{"src": ref(mem, ev), "type": "violates", "dst": ref(mem, rule)}]
    ctx = q(mem, repo="adc", path="src/db/q.py")
    assert refs(ctx) == [ref(mem, ev), ref(mem, bounded), ref(mem, rule)]
    n = neighbours(mem, PERSON, for_model=False, ref=ref(mem, ev), repo="adc", path="src/db/q.py")
    assert [x["ref"] for x in n["nodes"]] == [ref(mem, bounded), ref(mem, rule)]
    assert refs(q(mem, repo="adc", path="src/api/x.py")) == [ref(mem, rule)]  # the globs do not match
    assert refs(q(mem, repo="adc", path="src/")) == [ref(mem, ev), ref(mem, bounded), ref(mem, rule)]


# --- filters ------------------------------------------------------------------------------------------------

def test_each_filter(mem):  # T22 (commits: test_code_targets_and_commits_range)
    f = approved(mem, "mem", "Kayıtlar iki yıl saklanır", "finding", class_key="retention")
    d = approved(mem, "mem", "Use a queue", "decision_proposal")
    h = approved(mem, "mem", "Lesson by hand", "lesson", origin="unknown")
    m = approved(mem, "mem", "main only", "lesson", repo=None)
    fix = approved(mem, "mem", "Fixed the retention bug", "finding")
    link(mem, f, "fixed_by", fix)
    r = lambda *s: [ref(mem, x) for x in s]  # noqa: E731
    assert refs(q(mem, kind=["lesson"])) == r(m, h)
    assert refs(q(mem, role=["rule"])) == r(d)
    assert refs(q(mem, origin=["unknown"])) == r(h)
    assert refs(q(mem, class_key="retention")) == r(f)
    assert refs(q(mem, text="saklanır")) == r(f)
    assert refs(q(mem, unfixed=True)) == r(fix)
    standing(mem, fix, "rejected")  # a rejected fix does not fix
    assert refs(q(mem, unfixed=True)) == r(f)
    t = mem.execute("SELECT written_at FROM note WHERE seq = %s", (h,)).fetchone()[0]
    assert refs(q(mem, written_after=t.isoformat(), order="oldest")) == r(m)
    assert refs(q(mem, written_before=t.isoformat(), order="oldest")) == r(f, d)
    assert refs(q(mem, sets=["current"], order="oldest")) == r(f, d, h, m)
    with pytest.raises(ValueError):
        q(mem, order="relevance")
    with pytest.raises(ValueError):
        q(mem, kind=["poem"])


def test_scope_branch_and_path_globs(mem):  # T22
    mem.execute("INSERT INTO code_repo (book, slug, git_dir, object_format, refs, added_by) "
                "VALUES ('mem', 'adc', '/nonexistent', 'sha1', '{refs/heads/*}', 'user:admin')")
    one = approved(mem, "mem", "only on main", "finding", repo="adc", branch="main", paths=["src/*.py"])
    deep = approved(mem, "mem", "anywhere below", "finding", repo="adc", paths=["src/**"])
    assert refs(q(mem, repo="adc", branch="main", path="src/a.py")) == [ref(mem, deep), ref(mem, one)]
    assert refs(q(mem, repo="adc", branch="dev", path="src/a.py")) == [ref(mem, deep)]
    assert refs(q(mem, repo="adc", branch="main", path="src/x/a.py")) == [ref(mem, deep)]
    assert refs(q(mem, repo="other")) == []


def test_search_false_journal(conn):  # T14
    journal(conn, "quiet", search=False)
    seq = approved(conn, "quiet", "Kayıtlar saklanır")
    assert q(conn, text="saklanır")["items"] == []
    assert refs(q(conn, kind=["finding"])) == [ref(conn, seq)]
    with pytest.raises(ValueError):
        q(conn, order="relevance")


def test_ai_input_false_withholds_text_from_model_readers(mem):  # T15
    mem.execute("UPDATE journal SET ai_input = false WHERE book = 'mem'")
    approved(mem, "mem", "secret-free but not for models")
    agent = q(mem, MODEL)["items"][0]
    assert agent["text"] is None and agent["withheld"] == notesquery.WITHHELD
    assert q(mem)["items"][0]["text"] == "secret-free but not for models"


# --- determinism, as_of, size --------------------------------------------------------------------------------

def test_same_request_same_bytes_and_as_of(mem):  # T20
    a = approved(mem, "mem", "first")
    b = approved(mem, "mem", "second", origin="unknown")
    one, two = q(mem), q(mem)
    assert notesquery._dumps(one) == notesquery._dumps(two)
    w = one["watermark"]
    link(mem, a, "same_as", b)
    again(mem, b)
    mem.execute("INSERT INTO write_record (correlation_id, action, note_seq, creates, principal, channel, origin) "
                "VALUES ('t', 'propose', %s, false, 'agent:x', 'mcp', 'model')", (b,))
    now = {i["ref"]: i for i in q(mem)["items"]}
    assert now[ref(mem, b)]["recurrence"] == 4 and now[ref(mem, b)]["origin"] == "model"
    assert now[ref(mem, a)]["links"] == {"same_as": 1}
    old = q(mem, as_of=w)
    assert notesquery._dumps(old) == notesquery._dumps(one)
    assert {i["ref"]: i["recurrence"] for i in old["items"]} == {ref(mem, a): 1, ref(mem, b): 1}
    assert refs(q(mem, collapse=True)) == [ref(mem, b)]
    assert refs(q(mem, collapse=True, as_of=w)) == [ref(mem, b), ref(mem, a)]


def test_collapse_keeps_contradicting_members(mem):
    a, b, c = (approved(mem, "mem", t) for t in ("x is slow", "x is SLOW", "x is fast"))
    link(mem, a, "same_as", b)
    link(mem, b, "same_as", c)
    assert refs(q(mem, collapse=True)) == [ref(mem, c)]
    link(mem, c, "contradicts", a)
    assert refs(q(mem, collapse=True)) == [ref(mem, c), ref(mem, a)]


def test_collapse_never_drops_a_contradicting_member(mem):  # Astra review #13 (8)
    a, b, c = (approved(mem, "mem", t) for t in ("x is slow", "x is SLOW", "x is fast"))
    link(mem, a, "same_as", b)
    link(mem, b, "same_as", c)
    link(mem, a, "contradicts", b)  # neither older member contradicts the newest one
    assert refs(q(mem, collapse=True)) == [ref(mem, c), ref(mem, b), ref(mem, a)]
    d = approved(mem, "mem", "x is quick")
    link(mem, d, "same_as", c)  # a member without a contradiction still collapses into the newest
    assert refs(q(mem, collapse=True)) == [ref(mem, d), ref(mem, b), ref(mem, a)]


def test_size_limits_and_cursor(mem):  # T21
    made = [approved(mem, "mem", f"note {i} " + "word " * 300) for i in range(30)]
    seen, cursor, pages = [], None, 0
    while True:
        out = q(mem, budget_tokens=2000, max_bytes=8192, cursor=cursor)
        size = len(notesquery._dumps(out).encode())
        assert size <= 8192 and -(-size // 4) <= 2000
        seen += refs(out)
        pages += 1
        cursor = out["next_cursor"]
        if cursor is None:
            break
    assert pages > 1 and seen == [ref(mem, s) for s in reversed(made)]          # no gaps, no duplicates
    approved(mem, "mem", "written while paging")
    page2 = q(mem, budget_tokens=2000, max_bytes=8192, cursor=q(mem, budget_tokens=2000, max_bytes=8192,
                                                               as_of=out["watermark"])["next_cursor"])
    assert "written while paging" not in json.dumps(page2)                     # the cursor implies as_of
    big = approved(mem, "mem", "huge " * 1500)
    cut = q(mem, budget_tokens=200, max_bytes=8192)
    first = cut["items"][0]
    assert first["ref"] == ref(mem, big) and first["text_cut"] is True and len(cut["items"]) == 1
    assert len(notesquery._dumps(cut).encode()) <= 8192 and cut["next_cursor"]
    with pytest.raises(ValueError):
        q(mem, max_bytes=100)


def test_tombstones_are_paged_under_the_byte_limit(mem):  # Astra review #13 (9)
    gone = [approved(mem, "mem", f"retired note {i}") for i in range(80)]
    w0 = q(mem)["watermark"]
    for s in gone:
        standing(mem, s, "retired")
    fresh = [approved(mem, "mem", f"new note {i} " + "word " * 200) for i in range(6)]
    left, items, cursor, pages = [], [], None, 0
    while True:
        out = q(mem, since=w0, max_bytes=8192, cursor=cursor)
        size = len(notesquery._dumps(out).encode())
        assert size <= 8192 and -(-size // 4) <= 2000
        left += refs(out, "left")
        items += refs(out)
        pages += 1
        cursor = out["next_cursor"]
        if cursor is None:
            break
    assert pages > 2
    assert left == [ref(mem, s) for s in gone]                                     # every removal, once, in order
    assert items == [ref(mem, s) for s in reversed(fresh)]


# --- graph visibility, rights, audit ---------------------------------------------------------------------------

def test_counts_and_neighbours_use_the_visible_graph(mem):  # T24
    journal(mem, "hidden", readers=(V,))
    f = approved(mem, "mem", "a finding")
    other = approved(mem, "hidden", "a fix nobody here may read")
    c = approved(mem, "hidden", "a contradiction")
    link(mem, f, "fixed_by", other)
    link(mem, f, "contradicts", c)
    item = q(mem)["items"][0]
    assert item["links"] == {} and refs(q(mem, unfixed=True)) == [ref(mem, f)]
    n = neighbours(mem, PERSON, for_model=False, ref=ref(mem, f), depth=2)
    assert n["nodes"] == [] and n["edges"] == [] and n["root"]["ref"] == ref(mem, f)
    with pytest.raises(Denied):
        neighbours(mem, PERSON, for_model=False, ref=ref(mem, other))


def test_neighbours_depth_direction_and_passage_root(mem):
    a = approved(mem, "mem", "root")
    b = approved(mem, "mem", "one hop", creation_links=[("derived_from", a)])
    c = approved(mem, "mem", "two hops", creation_links=[("derived_from", b)])
    one = neighbours(mem, PERSON, for_model=False, ref=ref(mem, a))
    assert [x["ref"] for x in one["nodes"]] == [ref(mem, b)]
    two = neighbours(mem, PERSON, for_model=False, ref=ref(mem, a), depth=2)
    assert [x["ref"] for x in two["nodes"]] == [ref(mem, b), ref(mem, c)]
    assert neighbours(mem, PERSON, for_model=False, ref=ref(mem, a), direction="out")["nodes"] == []
    assert neighbours(mem, PERSON, for_model=False, ref=ref(mem, b), max_nodes=1)["truncated"] is True
    with pytest.raises(ValueError):
        neighbours(mem, PERSON, for_model=False, ref=ref(mem, a), depth=3)


def test_right_revoked_during_query_reruns_and_logs(mem, monkeypatch):  # T25
    journal(mem, "two")
    approved(mem, "mem", "stays")
    gone = approved(mem, "two", "goes")
    link(mem, mem.execute("SELECT min(seq) FROM note WHERE book = 'mem'").fetchone()[0], "contradicts", gone)
    real, calls = notesquery._read, []

    def racing(conn, actor):
        calls.append(1)
        if len(calls) == 1:
            out = real(conn, actor)
            authz.revoke(conn, "book:two", "read", U)
            return out
        return real(conn, actor)
    monkeypatch.setattr(notesquery, "_read", racing)
    out = q(mem)
    assert out["books"] == ["mem"] and out["items"][0]["links"] == {} and len(calls) == 4
    lost = mem.execute("SELECT reason FROM access_event WHERE object = 'book:two' AND NOT allowed").fetchall()
    assert lost == [("changed during query",)]


def test_since_ignores_links_from_unreadable_books(mem):  # Astra review #13 (7)
    journal(mem, "hidden", readers=(V,))
    f = approved(mem, "mem", "a readable finding")
    w0 = q(mem)["watermark"]
    h = approved(mem, "hidden", "a note nobody here may read")
    link(mem, h, "contradicts", f)
    assert q(mem, since=w0)["items"] == []
    mine = approved(mem, "mem", "a readable note")
    link(mem, mine, "contradicts", f)
    assert refs(q(mem, since=w0)) == [ref(mem, mine), ref(mem, f)]


def test_open_citation_reruns_when_a_linked_book_is_lost(mem, monkeypatch):  # Astra review #13 (4)
    journal(mem, "two")
    p = approved(mem, "mem", "old rule", "convention")
    s = approved(mem, "two", "new rule elsewhere", "convention", creation_links=[("supersedes", p)])
    standing(mem, p, "retired")
    link(mem, p, "contradicts", s)
    assert open_note(mem, PERSON, for_model=False, ref=ref(mem, p))["note"]["successor"] == ref(mem, s)
    real, calls = notesquery._read, []

    def racing(conn, actor):
        calls.append(1)
        out = real(conn, actor)
        if len(calls) == 1:
            authz.revoke(conn, "book:two", "read", U)
        return out
    monkeypatch.setattr(notesquery, "_read", racing)
    item = open_note(mem, PERSON, for_model=False, ref=ref(mem, p))["note"]
    assert item["links"] == {} and item["successor"] is None
    lost = mem.execute("SELECT reason FROM access_event WHERE object = 'book:two' AND NOT allowed").fetchall()
    assert lost == [("changed during query",)]


def test_no_model_call(mem):  # T26
    a = approved(mem, "mem", "Kayıtlar saklanır")
    before = model_calls(mem)
    q(mem, MODEL, text="saklanır", order="relevance")
    neighbours(mem, MODEL, for_model=True, ref=ref(mem, a), depth=2)
    open_note(mem, MODEL, for_model=True, ref=ref(mem, a))
    assert model_calls(mem) == before


def test_since_left_and_books(mem, conn2):  # T27
    a = approved(mem, "mem", "will be retired")
    b = note(mem, "mem", "pending one")
    w0 = q(mem)["watermark"]
    standing(mem, a, "retired")
    standing(mem, b, "approved")
    # a concurrent writer that took its seq but has not committed: the watermark stops below it
    conn2.execute("BEGIN")
    conn2.execute("SELECT pg_advisory_xact_lock(1)")
    late = conn2.execute(
        "INSERT INTO note (book, id, profile_id, kind, body, norm_sha256, search, ai_input, source_books, tsv) "
        "VALUES ('mem', 'nt_' || repeat('a', 64), 'pf_journal', 'finding', 'late', '\\x00', true, true, '{mem}', "
        "to_tsvector('late')) RETURNING seq").fetchone()[0]
    conn2.execute("INSERT INTO write_record (correlation_id, action, note_seq, creates, principal, on_behalf_of, "
                  "channel, origin) VALUES ('t', 'propose', %s, true, 'agent:kobra-7', %s, 'mcp', 'model')", (late, U))
    conn2.execute("INSERT INTO standing_event (note_seq, value, set_by, reason, correlation_id) "
                  "VALUES (%s, 'approved', 'user:c', 'r', 't')", (late,))
    first = q(mem, since=w0)
    assert refs(first) == [ref(mem, b)]
    assert first["left"] == [{"ref": ref(mem, a), "standing": "retired", "seq": first["left"][0]["seq"],
                              "successor": None}]
    assert first["watermark"] < late
    conn2.execute("COMMIT")
    second = q(mem, since=first["watermark"])
    assert refs(second) == [f"mem@nt_{'a' * 64}"] and second["left"] == []
    assert q(mem, since=second["watermark"])["items"] == []
    authz.revoke(mem, "book:mem", "read", U)
    assert q(mem, since=w0)["books"] == []


def test_audit_names_standing_and_watermark(mem):  # T28
    a = approved(mem, "mem", "approved one")
    b = note(mem, "mem", "pending one")
    out = q(mem, sets=["current", "open"])
    ev = mem.execute("SELECT seq FROM standing_event WHERE note_seq = %s", (a,)).fetchone()[0]
    row = mem.execute("SELECT items, memory_seq, action FROM access_event WHERE object = 'book:mem' AND allowed "
                      "ORDER BY id DESC LIMIT 1").fetchone()
    assert row[1] == out["watermark"] and row[2] == "query_notes"
    assert row[0] == [{"ref": ref(mem, b), "standing_seq": None}, {"ref": ref(mem, a), "standing_seq": ev}]


# --- code targets --------------------------------------------------------------------------------------------

def _git(*args, cwd):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True,
                          env={"PATH": "/usr/bin:/bin", "HOME": str(cwd), "GIT_AUTHOR_NAME": "t",
                               "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
                          ).stdout.strip()


def _excerpt(text: str, start: int, end: int) -> bytes:
    lines = text.split("\n")[start - 1:end]
    return hashlib.sha256("\n".join(x.rstrip() for x in lines).encode()).digest()


@pytest.fixture
def repo(mem, tmp_path, monkeypatch):
    work = tmp_path / "work"
    work.mkdir()
    _git("init", "-q", "-b", "main", cwd=work)
    v1 = "a = 1\nb = 2\nc = 3\n"
    (work / "q.py").write_text(v1)
    _git("add", "q.py", cwd=work)
    _git("commit", "-q", "-m", "one", cwd=work)
    c1 = _git("rev-parse", "HEAD", cwd=work)
    (work / "q.py").write_text("x = 0\na = 1\nb = 2\nc = 3\n")
    _git("commit", "-q", "-am", "two", cwd=work)
    c2 = _git("rev-parse", "HEAD", cwd=work)
    bare = tmp_path / "adc.git"
    monkeypatch.setenv(coderepo.ROOTS_ENV, os.path.realpath(tmp_path))  # the real verifier reads only inside roots
    _git("clone", "-q", "--bare", str(work), str(bare), cwd=tmp_path)
    mem.execute("INSERT INTO code_repo (book, slug, git_dir, object_format, refs, added_by) "
                "VALUES ('mem', 'adc', %s, 'sha1', '{refs/heads/*}', 'user:admin')", (os.path.realpath(bare),))
    return c1, c2, v1


def cite(conn, seq, c, start, end, sha, n=1):
    conn.execute("INSERT INTO note_citation (note_seq, book, n, kind, path, repo, commit, line_start, line_end, "
                 "excerpt_sha256) VALUES (%s, 'mem', %s, 'code', 'q.py', 'adc', %s, %s, %s, %s)",
                 (seq, n, c, start, end, sha))


def test_code_targets_and_commits_range(mem, repo):  # T30, T22 commits
    c1, c2, v1 = repo
    moved = approved(mem, "mem", "b is two", repo="adc", commit=c1)
    cite(mem, moved, c1, 2, 2, _excerpt(v1, 2, 2))
    still = approved(mem, "mem", "c is three at the end", repo="adc", commit=c2)
    cite(mem, still, c1, 1, 3, _excerpt(v1, 1, 3))
    assert refs(q(mem)) == [ref(mem, still), ref(mem, moved)]                 # no target: not_checked
    assert q(mem)["items"][0]["citations"][0]["status"] == "not_checked"
    old = q(mem, repo="adc", commit=c1)
    assert refs(old) == [ref(mem, still), ref(mem, moved)] and old["targets"] == {"mem/adc": c1}
    new = q(mem, repo="adc", branch="main")
    assert new["targets"] == {"mem/adc": c2} and new["items"] == [] and new["excluded"]["code"] == 2
    shown = q(mem, repo="adc", branch="main", include_unverified=True)
    by = {i["ref"]: i for i in shown["items"]}
    assert by[ref(mem, moved)]["current"] is False
    assert by[ref(mem, moved)]["citations"][0] == {"ref": f"adc@{c1}:q.py:2-2", "status": "stale", "moved_to": 3}
    assert refs(q(mem, repo="adc", branch="nope")) == []                      # an unknown branch never verifies
    assert refs(q(mem, repo="adc", commits=f"{c1}..{c2}")) == [ref(mem, still)]
    with pytest.raises(ValueError):
        q(mem, repo="adc", commits="main..HEAD")
    item = open_note(mem, PERSON, for_model=False, ref=ref(mem, moved), repo="adc", branch="main")["note"]
    assert item["current"] is False and item["text"] == "b is two"


def test_many_cited_notes_never_fail_a_query(mem, repo, monkeypatch):  # Astra review #13 (3)
    c1, _c2, v1 = repo
    retired = []
    for i in range(11):
        s = approved(mem, "mem", f"retired with citations {i}")
        for n in range(1, 21):
            cite(mem, s, c1, 1, 1, _excerpt(v1, 1, 1), n=n)
        standing(mem, s, "retired")
        retired.append(s)
    calls = []
    real = coderepo._git
    monkeypatch.setattr(coderepo, "_git", lambda *a, **kw: (calls.append(a[0]), real(*a, **kw))[1])
    assert q(mem)["items"] == []                                              # history is not requested
    assert len(q(mem, sets=["history"], max_bytes=131072, budget_tokens=16000)["items"]) == 11
    assert calls == []                                                        # no target: nothing to verify
    current = []
    for i in range(11):
        s = approved(mem, "mem", f"current with citations {i} " + "word " * 100)
        for n in range(1, 21):
            cite(mem, s, c1, n % 3 + 1, n % 3 + 1, _excerpt(v1, n % 3 + 1, n % 3 + 1), n=n)
        current.append(s)
    verified = []
    real_verify = coderepo._verify
    monkeypatch.setattr(coderepo, "_verify", lambda r, book, c, *rest: (verified.append(str(c)),
                                                                        real_verify(r, book, c, *rest))[1])
    page = q(mem, repo="adc", commit=c1, max_bytes=8192)
    assert 0 < len(page["items"]) < 11 and page["next_cursor"]
    assert all(c["status"] == "verified" for i in page["items"] for c in i["citations"])
    assert len(verified) <= 20 * (len(page["items"]) + 1)                    # the page and one note after it
    seen, cursor = [], None
    while True:
        out = q(mem, repo="adc", commit=c1, max_bytes=8192, cursor=cursor)
        seen += refs(out)
        cursor = out["next_cursor"]
        if cursor is None:
            break
    assert seen == [ref(mem, s) for s in reversed(current)]


# --- MCP, HTTP, open_citation ---------------------------------------------------------------------------------

def test_tools_routes_and_open_citation(mem, keys, verifier):  # §9.4, §13
    from test_server import PUBLIC, bearer
    from test_identity import token
    seq = approved(mem, "mem", "over the wire")
    pending = note(mem, "mem", "not yet")
    dsn = os.environ["KUTUPHANE_TEST_DSN"]
    app = server.create_app(dsn=dsn, verifier=verifier, bridge=None, model=None, public_url=PUBLIC)
    with TestClient(app) as client:
        r = client.get("/v1/notes", params=[("sets", "current"), ("sets", "open")], headers=bearer(keys))
        assert r.status_code == 200 and r.headers["x-correlation-id"]
        assert refs(r.json()) == [ref(mem, pending), ref(mem, seq)]
        assert r.content == notesquery._dumps(r.json()).encode()
        book, nid = ref(mem, seq).split("@")
        n = client.get(f"/v1/notes/{book}/{nid}/neighbours", headers=bearer(keys))
        assert n.status_code == 200 and n.json()["root"]["ref"] == ref(mem, seq)
        c = client.get("/v1/citation", params={"handle": ref(mem, seq)}, headers=bearer(keys)).json()
        assert c["note"]["text"] == "over the wire" and c["note"]["current"] is True
        assert client.get("/v1/notes", params={"order": "x"}, headers=bearer(keys)).status_code == 400
        assert client.get("/v1/notes", headers=bearer(keys, sub="mehmet")).json()["items"] == []
    mcp = server.build_mcp(dsn=dsn, verifier=verifier, bridge=None, model=None, public_url=PUBLIC)
    names = [t.name for t in asyncio.run(mcp.list_tools())]
    assert names.index("query_notes") < names.index("neighbours")
    claims = asyncio.run(server._Verifier(verifier).verify_token(token(keys, act={"sub": "kobra-7"}))).claims
    assert refs(_tool(mcp, claims, "query_notes", {"sets": ["open"]})) == [ref(mem, pending)]
    assert _tool(mcp, claims, "open_citation", {"handle": ref(mem, seq)})["note"]["ref"] == ref(mem, seq)


def _tool(mcp, claims, name, args) -> dict:
    """The tool's JSON result, from the text block (the same on SDK v1 and v2)."""
    from test_server import call_tool
    out = call_tool(mcp, claims, name, args)
    content = out[0] if isinstance(out, tuple) else out
    return json.loads(content[0].text)


@pytest.fixture
def keys():
    from cryptography.hazmat.primitives.asymmetric import rsa
    return rsa.generate_private_key(public_exponent=65537, key_size=2048), \
        rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture
def verifier(keys, tmp_path):
    import jwt
    from kutuphane.identity import Verifier
    from test_identity import AUD, ISS
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(keys[0].public_key()))
    path = tmp_path / "jwks.json"
    path.write_text(json.dumps({"keys": [{**jwk, "kid": "k1", "use": "sig", "alg": "RS256"}]}))
    return Verifier.from_files(ISS, AUD, path)
