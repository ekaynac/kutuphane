"""Code citations and the verifier (docs/24 §10, #70): T29–T32, the C parts of T4, T22, T30 and T38.
Every test uses real temporary git repositories: a work tree that pushes into a bare mirror inside the roots."""
import hashlib
import json
import os
import subprocess
from datetime import datetime, timedelta, timezone

import pytest
from starlette.testclient import TestClient

from kutuphane import authz, cli, coderepo, db, server
from kutuphane.coderepo import CitationRefused, CodeCitation, Status
from test_server import MCP_HEADERS, PUBLIC, bearer, keys, mcp_tool_over_http, verifier  # noqa: F401 (fixtures)

U, A = "user:ayse", "agent:kobra-7"
SETUP_ENV = {"PATH": "/usr/bin:/bin", "HOME": "/nonexistent", "LC_ALL": "C", "GIT_CONFIG_NOSYSTEM": "1",
             "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.org",
             "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.org"}
F_PY = b"".join(b"line %d\n" % i for i in range(1, 21))
RUN_PY = b"def retry_job():\n    pass\n"


def git(*args, cwd=None) -> str:
    """Test setup only (never the code under test): plain git with a fixed identity."""
    return subprocess.run(["git", *args], cwd=cwd, env=SETUP_ENV, check=True, capture_output=True).stdout.decode().strip()


class Mirror:
    """A work tree and its bare mirror `<root>/<name>.git`; commits reach the mirror only by an explicit push."""

    def __init__(self, tmp, root, name: str, object_format: str = "sha1"):
        self.work = tmp / f"work-{name}"
        self.git_dir = os.path.join(root, f"{name}.git")
        git("init", "-q", "-b", "main", f"--object-format={object_format}", str(self.work))
        git("init", "-q", "--bare", f"--object-format={object_format}", self.git_dir)

    def commit(self, files: dict) -> str:
        for path, data in files.items():
            f = self.work / path
            if data is None:
                f.unlink()
            else:
                f.parent.mkdir(parents=True, exist_ok=True)
                f.write_bytes(data)
        git("add", "-A", cwd=self.work)
        git("commit", "-q", "--allow-empty", "-m", "c", cwd=self.work)
        return git("rev-parse", "HEAD", cwd=self.work)

    def push(self, commit: str, ref: str = "refs/heads/main") -> None:
        git("push", "-q", "--force", self.git_dir, f"{commit}:{ref}", cwd=self.work)


@pytest.fixture
def root(tmp_path, monkeypatch) -> str:
    r = os.path.realpath(tmp_path / "roots")
    os.makedirs(r)
    monkeypatch.setenv(coderepo.ROOTS_ENV, r)
    return r


def journal(conn, book: str) -> None:
    conn.execute("INSERT INTO book (slug, title) VALUES (%s, %s)", (book, book))
    conn.execute("INSERT INTO journal (book, search, ai_input, created_by) VALUES (%s, true, true, 'user:admin')",
                 (book,))


@pytest.fixture
def adc(conn, tmp_path, root):
    """Journal `j` with repository `adc`: C1 on main; C2 (main now) moves, deletes and changes code; C3 only on an
    unregistered ref."""
    journal(conn, "j")
    m = Mirror(tmp_path, root, "adc")
    c1 = m.commit({"f.py": F_PY, "g.py": b"x\n", "h.py": b"same\n", "src/run.py": RUN_PY,
                   "crlf.py": b"a  \r\nb\t\r\n"})
    m.push(c1, "refs/heads/old")
    c2 = m.commit({"f.py": b"new 1\nnew 2\n" + F_PY, "g.py": None, "src/run.py": b"import os\n\n\ndef retry_job(n):\n"
                   b"    return n\n", "crlf.py": b"a\nb\n"})
    m.push(c2)
    c3 = m.commit({"secret.py": b"token\n"})
    m.push(c3, "refs/hidden/x")
    coderepo.add(conn, "j", "adc", m.git_dir, ["refs/heads/*"], by="user:admin")
    return m, c1, c2, c3


def cite(text: str) -> CodeCitation:
    return coderepo.parse(text)


def spy(monkeypatch) -> list:
    calls = []
    real = coderepo._git

    def recording(args, git_dir=None, stdin=None):
        calls.append((list(args), stdin))
        return real(args, git_dir, stdin)
    monkeypatch.setattr(coderepo, "_git", recording)
    return calls


# --- parse (T31) -------------------------------------------------------------------------------------------

def test_parse_reads_from_the_right():
    c = cite(f"adc@{'a' * 40}:src/a:b.py:40-52#Job::retry")
    assert (c.repo, c.path, c.line_start, c.line_end, c.symbol) == ("adc", "src/a:b.py", 40, 52, "Job::retry")
    assert str(c) == f"adc@{'a' * 40}:src/a:b.py:40-52#Job::retry"
    one = cite(f"adc@{'b' * 64}:x.py:7")
    assert (one.line_start, one.line_end, one.symbol) == (7, 7, None) and str(one).endswith(":x.py:7-7")


@pytest.mark.parametrize("text", [
    f"adc@{'a' * 40}:a.py\nHEAD:secret:1", f"adc@{'a' * 40}:a\r.py:1", f"adc@{'a' * 40}:a\0.py:1",
    f"adc@{'a' * 40}:a\x7f.py:1", f"adc@{'a' * 40}:../x:1", f"adc@{'a' * 40}:/etc/passwd:1",
    f"adc@{'a' * 40}:a//b.py:1", f"adc@{'a' * 40}:./a.py:1", "adc@3f2c:a.py:1", f"adc@{'A' * 40}:a.py:1",
    f"adc@{'a' * 41}:a.py:1", f"adc@main:a.py:1", f"adc@{'a' * 40}:a.py:0", f"adc@{'a' * 40}:a.py:5-4",
    f"adc@{'a' * 40}:a.py:1-201", f"adc@{'a' * 40}:a.py:01", f"Adc@{'a' * 40}:a.py:1", f"adc@{'a' * 40}:a.py",
    f"adc@{'a' * 40}:a.py:1#9x", f"--upload-pack=x@{'a' * 40}:a.py:1",
])
def test_parse_refuses(text):
    with pytest.raises(CitationRefused):
        coderepo.parse(text)


def test_a_stored_row_gets_the_same_checks():
    with pytest.raises(CitationRefused):
        CodeCitation("adc", "a" * 40, "a.py\nHEAD:secret", 1, 1)
    with pytest.raises(CitationRefused):
        CodeCitation("adc", "a" * 40, "a.py", 1, 300)


def test_ranges_need_two_full_commit_ids():
    assert coderepo.parse_range(f"{'a' * 40}..{'b' * 40}") == ("a" * 40, "b" * 40)
    for bad in (f"main..{'b' * 40}", f"{'a' * 40}..HEAD", "3f2c..4e1d", f"{'a' * 40}...{'b' * 40}", f"{'a' * 40}"):
        with pytest.raises(CitationRefused):
            coderepo.parse_range(bad)


@pytest.mark.parametrize("name", ["--upload-pack=x", "-x", "a..b", "x\n", "@{-1}", "a b", "x.lock", ""])
def test_branch_names_that_are_not_branches_are_refused(name):
    with pytest.raises(CitationRefused):
        coderepo.branch_name(name)


def test_branch_name():
    assert coderepo.branch_name("feature/x") == "refs/heads/feature/x"


# --- the verifier (T29, T30) -------------------------------------------------------------------------------

def test_statuses_at_a_branch(conn, adc):  # T29
    m, c1, c2, c3 = adc
    targets = coderepo.resolve_targets(conn, ["j"], "adc", "main", None)
    assert targets == {("j", "adc"): c2}
    cites = [cite(f"adc@{c1}:h.py:1"), cite(f"adc@{c1}:f.py:5-7"), cite(f"adc@{c1}:g.py:1"),
             cite(f"adc@{c1}:src/run.py:1-2#retry_job"), cite(f"adc@{c1}:crlf.py:1-2"), cite(f"adc@{c1}:f.py:1-2"),
             cite(f"adc@{c3}:secret.py:1"), cite(f"adc@{'e' * 40}:f.py:1")]
    stored = coderepo.excerpt(conn, "j", cites[1])
    statuses = coderepo.verify_many(conn, targets, [("j", c, None) for c in cites[:1]] + [("j", cites[1], stored)]
                                    + [("j", c, None) for c in cites[2:]])
    assert statuses == [
        Status("verified"),
        Status("stale", moved_to=7),
        Status("missing"),
        Status("stale", symbol_found_at=(4,)),
        Status("verified"),                                  # CRLF → LF and trailing white space do not count
        Status("stale", moved_to=3),
        Status("unverifiable", "commit_not_published"),     # only an unregistered ref reaches it
        Status("unverifiable", "commit_unknown"),
    ]


def test_targets_that_cannot_be_resolved(conn, adc):  # T29
    m, c1, c2, c3 = adc
    unknown_branch = coderepo.resolve_targets(conn, ["j"], "adc", "nope", None)
    assert unknown_branch == {("j", "adc"): Status("unverifiable", "branch_unknown")}
    hidden = coderepo.resolve_targets(conn, ["j"], "adc", None, c3)
    assert hidden == {("j", "adc"): Status("unverifiable", "commit_not_published")}
    assert coderepo.resolve_targets(conn, ["j"], "adc", "old", None) == {("j", "adc"): c1}
    assert coderepo.resolve_targets(conn, ["j"], "other", "main", None) == {}           # no such repo: no target
    assert coderepo.resolve_targets(conn, ["j"], "adc", None, None) == {}
    c = cite(f"adc@{c1}:h.py:1")
    assert coderepo.verify_many(conn, unknown_branch, [("j", c, None)]) == [Status("unverifiable", "branch_unknown")]
    assert coderepo.verify_many(conn, {}, [("j", c, None)]) == [Status("not_checked")]
    with pytest.raises(CitationRefused):
        coderepo.resolve_targets(conn, ["j"], "adc", "--upload-pack=x", None)           # T31
    with pytest.raises(CitationRefused):
        coderepo.resolve_targets(conn, ["j"], "adc", None, "3f2c")


def test_two_books_with_the_same_slug_get_two_targets(conn, adc, tmp_path, root):  # T30
    m, c1, c2, _ = adc
    journal(conn, "k")
    other = Mirror(tmp_path, root, "adc-k")
    k1 = other.commit({"h.py": b"other\n"})
    other.push(k1)
    coderepo.add(conn, "k", "adc", other.git_dir, ["refs/heads/main"], by="user:admin")
    targets = coderepo.resolve_targets(conn, ["j", "k"], "adc", "main", None)
    assert targets == {("j", "adc"): c2, ("k", "adc"): k1}
    statuses = coderepo.verify_many(conn, targets, [("j", cite(f"adc@{c1}:h.py:1"), None),
                                                    ("k", cite(f"adc@{k1}:h.py:1"), None)])
    assert statuses == [Status("verified"), Status("verified")]
    assert coderepo.remove(conn, "k", "adc") and not coderepo.remove(conn, "k", "adc")
    after = coderepo.resolve_targets(conn, ["j", "k"], "adc", "main", None)
    assert after == {("j", "adc"): c2, ("k", "adc"): Status("unverifiable", "repo_removed")}
    stored = hashlib.sha256(b"other").digest()
    assert coderepo.verify_many(conn, targets, [("k", cite(f"adc@{k1}:h.py:1"), stored)]) == \
        [Status("unverifiable", "repo_removed")]                                     # also with an older target
    with pytest.raises(CitationRefused):
        coderepo.excerpt(conn, "k", cite(f"adc@{k1}:h.py:1"))


def test_a_timeout_is_unverifiable(conn, adc, monkeypatch):  # T30
    m, c1, c2, _ = adc
    targets = coderepo.resolve_targets(conn, ["j"], "adc", "main", None)
    monkeypatch.setattr(coderepo, "TIMEOUT", 1e-6)
    assert coderepo.verify_many(conn, targets, [("j", cite(f"adc@{c1}:h.py:1"), None)]) == \
        [Status("unverifiable", "timeout")]
    assert coderepo.resolve_targets(conn, ["j"], "adc", None, c2) == {("j", "adc"): Status("unverifiable", "timeout")}


def test_excerpt_for_the_write_path(conn, adc):
    m, c1, c2, c3 = adc
    assert coderepo.excerpt(conn, "j", cite(f"adc@{c1}:crlf.py:1-2")) == hashlib.sha256(b"a\nb").digest()
    assert coderepo.excerpt(conn, "j", cite(f"adc@{c1}:f.py:20")) == hashlib.sha256(b"line 20").digest()
    for bad in (f"adc@{c1}:f.py:21", f"adc@{c1}:nope.py:1", f"adc@{c3}:secret.py:1", f"other@{c1}:f.py:1",
                f"adc@{c1}:src:1"):
        with pytest.raises(CitationRefused):
            coderepo.excerpt(conn, "j", cite(bad))


def test_a_sha256_repository_takes_64_hex_ids(conn, tmp_path, root):
    journal(conn, "j")
    m = Mirror(tmp_path, root, "adc", "sha256")
    c = m.commit({"h.py": b"same\n"})
    m.push(c)
    assert len(c) == 64
    assert coderepo.add(conn, "j", "adc", m.git_dir, ["refs/heads/*"], by="user:admin")["object_format"] == "sha256"
    targets = coderepo.resolve_targets(conn, ["j"], "adc", "main", None)
    assert targets == {("j", "adc"): c}
    assert coderepo.verify_many(conn, targets, [("j", cite(f"adc@{c}:h.py:1"), None),
                                                ("j", cite(f"adc@{c[:40]}:h.py:1"), None)]) == \
        [Status("verified"), Status("unverifiable", "commit_unknown")]


def test_rev_list(conn, adc, monkeypatch):  # T22, C part
    m, c1, c2, c3 = adc
    assert coderepo.rev_list(conn, "j", "adc", c1, c2) == [c2]
    assert coderepo.rev_list(conn, "j", "adc", c2, c1) == []
    with pytest.raises(CitationRefused, match="commit_not_published"):
        coderepo.rev_list(conn, "j", "adc", c1, c3)
    with pytest.raises(CitationRefused):
        coderepo.rev_list(conn, "j", "adc", c1, "main")
    c4 = m.commit({"h.py": b"changed\n"})
    m.push(c4)
    monkeypatch.setattr(coderepo, "MAX_RANGE", 1)
    with pytest.raises(CitationRefused, match="more than 1 commits"):
        coderepo.rev_list(conn, "j", "adc", c1, c4)


# --- objects and injection (T31, T32) ----------------------------------------------------------------------

def test_a_tree_a_large_blob_and_a_binary_file_are_unverifiable(conn, adc, monkeypatch):  # T32
    m, c1, c2, _ = adc
    c5 = m.commit({"big.txt": b"a\n" * (coderepo.MAX_BLOB // 2) + b"x", "bin.dat": b"a\0b\n"})
    m.push(c5)
    calls = spy(monkeypatch)
    targets = coderepo.resolve_targets(conn, ["j"], "adc", "main", None)
    statuses = coderepo.verify_many(conn, targets, [("j", cite(f"adc@{c5}:src:1"), None),
                                                    ("j", cite(f"adc@{c5}:big.txt:1"), None),
                                                    ("j", cite(f"adc@{c5}:bin.dat:1"), None)])
    assert statuses == [Status("unverifiable", "not_a_file"), Status("unverifiable", "too_large"),
                        Status("unverifiable", "binary")]
    blobs = [args for args, _ in calls if args[:2] == ["cat-file", "blob"]]
    assert len(blobs) == 1                       # type and size are checked first: only bin.dat was read


def test_one_framed_request_per_read_and_no_request_text_in_arguments(conn, adc, monkeypatch):  # T31
    m, c1, c2, _ = adc
    calls = spy(monkeypatch)
    for text in (f"adc@{c1}:h.py\nHEAD:secret.py:1", f"adc@{c1}:h.py\0HEAD:secret.py:1"):
        with pytest.raises(CitationRefused):
            coderepo.parse(text)
    assert calls == []                           # refused before any git process
    path = "dir with space/x:y#z.py"
    c6 = m.commit({path: b"ok\n"})
    m.push(c6)
    targets = coderepo.resolve_targets(conn, ["j"], "adc", "main", None)
    assert coderepo.verify_many(conn, targets, [("j", cite(f"adc@{c6}:{path}:1"), None)]) == [Status("verified")]
    requests = [stdin for args, stdin in calls if args[:2] == ["cat-file", "--batch-check"]]
    assert requests and all(r.count(b"\0") == 1 and r.endswith(b"\0") for r in requests)
    assert not any(path in a for args, _ in calls for a in args)            # the path only on stdin


def test_the_server_environment_never_reaches_git(conn, adc, tmp_path, root, monkeypatch):
    """A commit that exists only in another repository stays unknown, even if the server's own environment
    points git at that repository's objects."""
    m, c1, c2, _ = adc
    secret = Mirror(tmp_path, str(tmp_path), "secret")
    s1 = secret.commit({"key.txt": b"secret\n"})
    secret.push(s1)
    objects = os.path.join(secret.git_dir, "objects")
    for name, value in (("GIT_ALTERNATE_OBJECT_DIRECTORIES", objects), ("GIT_OBJECT_DIRECTORY", objects),
                        ("GIT_DIR", secret.git_dir), ("GIT_COMMON_DIR", secret.git_dir)):
        monkeypatch.setenv(name, value)
    targets = coderepo.resolve_targets(conn, ["j"], "adc", "main", None)
    assert targets == {("j", "adc"): c2}
    assert coderepo.verify_many(conn, targets, [("j", cite(f"adc@{s1}:key.txt:1"), None)]) == \
        [Status("unverifiable", "commit_unknown")]


def _symlink(path):
    real = path + "-real"
    os.rename(path, real)
    os.symlink(real, path)


def _gitfile(path):
    real = path + "-real"
    os.rename(path, real)
    with open(path, "w") as f:
        f.write(f"gitdir: {real}\n")


def _write(rel, text):
    def apply(path):
        with open(os.path.join(path, rel), "w") as f:
            f.write(text)
    return apply


def _config(*kv):
    def apply(path):
        git("config", "--file", os.path.join(path, "config"), *kv)
    return apply


REFUSALS = {
    "symlink": _symlink,
    "gitfile": _gitfile,
    "commondir": _write("commondir", "../other.git\n"),
    "promisor": _write("objects/pack/pack-0.promisor", ""),
    "http-alternates": _write("objects/info/http-alternates", "http://example.org/objects\n"),
    "partialclone": _config("extensions.partialclone", "origin"),
    "include": _config("include.path", "/tmp/evil.config"),
    "promisor-remote": _config("remote.origin.promisor", "true"),
    "alternate-refs": _config("core.alternateRefsCommand", "touch /tmp/pwned"),
}


@pytest.mark.parametrize("case", sorted(REFUSALS))
def test_repositories_refused_at_add_and_at_open(conn, tmp_path, root, case, monkeypatch):  # T32
    journal(conn, "j")
    m = Mirror(tmp_path, root, "adc")
    c = m.commit({"h.py": b"same\n"})
    m.push(c)
    bad = Mirror(tmp_path, root, "bad")
    bad.push(bad.commit({"h.py": b"same\n"}))
    REFUSALS[case](bad.git_dir)
    with pytest.raises(CitationRefused, match="repository refused"):
        coderepo.add(conn, "j", "bad", bad.git_dir, ["refs/heads/*"], by="user:admin")
    coderepo.add(conn, "j", "adc", m.git_dir, ["refs/heads/*"], by="user:admin")
    REFUSALS[case](m.git_dir)                                        # changed after `add`
    calls = spy(monkeypatch)
    assert coderepo.resolve_targets(conn, ["j"], "adc", "main", None) == \
        {("j", "adc"): Status("unverifiable", "repo_invalid")}
    with pytest.raises(CitationRefused, match="repository refused"):
        coderepo.excerpt(conn, "j", cite(f"adc@{c}:h.py:1"))
    assert {args[0] for args, _ in calls} <= {"check-ref-format", "config"}  # no object or ref was read


def test_an_alternates_repository_cannot_lend_objects(conn, tmp_path, root, monkeypatch):  # T32
    """`clone --shared` borrows objects through objects/info/alternates: refused at add, and at open when the file
    appears later, before any object read."""
    journal(conn, "j")
    secret = Mirror(tmp_path, str(tmp_path), "secret")
    s1 = secret.commit({"key.txt": b"secret\n"})
    secret.push(s1)
    shared = os.path.join(root, "shared.git")
    git("clone", "-q", "--bare", "--shared", secret.git_dir, shared)
    assert os.path.exists(os.path.join(shared, "objects/info/alternates"))
    with pytest.raises(CitationRefused, match="alternates"):
        coderepo.add(conn, "j", "shared", shared, ["refs/heads/*"], by="user:admin")
    m = Mirror(tmp_path, root, "adc")
    m.push(m.commit({"h.py": b"same\n"}))
    coderepo.add(conn, "j", "adc", m.git_dir, ["refs/heads/*"], by="user:admin")
    with open(os.path.join(m.git_dir, "objects/info/alternates"), "w") as f:
        f.write(os.path.join(secret.git_dir, "objects") + "\n")
    calls = spy(monkeypatch)
    assert coderepo.verify_many(conn, {("j", "adc"): s1}, [("j", cite(f"adc@{s1}:key.txt:1"), None)]) == \
        [Status("unverifiable", "repo_invalid")]
    assert not any(args[0] == "cat-file" for args, _ in calls)


def test_add_checks_the_place_and_the_ref_patterns(conn, tmp_path, root, monkeypatch):
    journal(conn, "j")
    outside = Mirror(tmp_path, str(tmp_path), "outside")
    outside.push(outside.commit({"h.py": b"x\n"}))
    with pytest.raises(CitationRefused, match="KUTUPHANE_REPO_ROOTS"):
        coderepo.add(conn, "j", "out", outside.git_dir, ["refs/heads/*"], by="user:admin")
    m = Mirror(tmp_path, root, "adc")
    m.push(m.commit({"h.py": b"x\n"}))
    with pytest.raises(CitationRefused, match="canonical"):
        coderepo.add(conn, "j", "adc", m.git_dir + "/", ["refs/heads/*"], by="user:admin")
    for refs in (["refs/heads/**"], ["refs/*/x*"], ["--upload-pack=x"], ["refs/heads/a\n"], []):
        with pytest.raises(ValueError):
            coderepo.add(conn, "j", "adc", m.git_dir, refs, by="user:admin")
    with pytest.raises(ValueError, match="no such journal"):
        coderepo.add(conn, "j2", "adc", m.git_dir, ["refs/heads/*"], by="user:admin")
    out = coderepo.add(conn, "j", "adc", m.git_dir, ["refs/heads//main", "refs/tags/v*"], by="user:admin")
    assert out["refs"] == ["refs/heads/main", "refs/tags/v*"] and out["object_format"] == "sha1"
    with pytest.raises(ValueError, match="already"):
        coderepo.add(conn, "j", "adc", m.git_dir, ["refs/heads/*"], by="user:admin")
    monkeypatch.delenv(coderepo.ROOTS_ENV)                            # no roots configured: nothing is accepted
    assert coderepo.resolve_targets(conn, ["j"], "adc", "main", None) == \
        {("j", "adc"): Status("unverifiable", "repo_invalid")}


def test_cli_repo_add_and_remove(conn, tmp_path, root, monkeypatch, capsys):
    journal(conn, "j")
    m = Mirror(tmp_path, root, "adc")
    m.push(m.commit({"h.py": b"x\n"}))
    monkeypatch.setenv(db.DSN_ENV, os.environ["KUTUPHANE_TEST_DSN"])
    assert cli.main(["repo", "add", "j", "adc", m.git_dir, "--ref", "refs/heads/*", "--by", "user:admin"]) == 0
    assert json.loads(capsys.readouterr().out)["refs"] == ["refs/heads/*"]
    assert cli.main(["repo", "add", "j", "x", m.git_dir, "--ref", "refs/heads/**", "--by", "user:admin"]) == 2
    assert cli.main(["repo", "remove", "j", "adc"]) == 0
    assert json.loads(capsys.readouterr().out) == {"removed": True}
    assert conn.execute("SELECT added_by, removed_at IS NOT NULL FROM code_repo").fetchall() == [("user:admin", True)]


# --- verify_citations (MCP) / POST /v1/citations/verify (HTTP), T4 C part -----------------------------------

def test_verify_citations_over_http_and_mcp(conn, adc, verifier, keys, monkeypatch):  # noqa: F811
    m, c1, c2, c3 = adc
    dsn = os.environ["KUTUPHANE_TEST_DSN"]
    app = server.create_app(dsn=dsn, verifier=verifier, bridge=None, model=None, public_url=PUBLIC)
    citations = [f"adc@{c1}:f.py:5-7", f"adc@{c1}:g.py:1", f"adc@{c3}:secret.py:1", f"zzz@{c1}:f.py:1"]
    body = {"book": "j", "citations": citations, "at": "main"}
    calls = spy(monkeypatch)
    with TestClient(app, base_url=PUBLIC) as client:
        r = client.post("/v1/citations/verify", json=body, headers=bearer(keys))
        assert r.status_code == 403 and calls == []                      # T4: refused before any git process
        authz.grant(conn, "book:j", "read", U)
        r = client.post("/v1/citations/verify", json=body, headers=bearer(keys))
        assert r.status_code == 200, r.text
        expected = {"targets": {"j/adc": c2}, "results": [
            {"citation": f"adc@{c1}:f.py:5-7", "status": "stale", "moved_to": 7, "symbol_found_at": None,
             "reason": None},
            {"citation": f"adc@{c1}:g.py:1-1", "status": "missing", "moved_to": None, "symbol_found_at": None,
             "reason": None},
            {"citation": f"adc@{c3}:secret.py:1-1", "status": "unverifiable", "moved_to": None,
             "symbol_found_at": None, "reason": "commit_not_published"},
            {"citation": f"zzz@{c1}:f.py:1-1", "status": "not_checked", "moved_to": None, "symbol_found_at": None,
             "reason": None}]}
        assert r.json() == expected
        assert b"line 5" not in r.content and b"token" not in r.content  # no code text
        at_commit = client.post("/v1/citations/verify", json={**body, "at": c1}, headers=bearer(keys)).json()
        assert at_commit["targets"] == {"j/adc": c1} and at_commit["results"][0]["status"] == "verified"
        for bad in ({**body, "at": "--upload-pack=x"}, {**body, "citations": [f"adc@{c1}:a.py\nHEAD:x:1"]},
                    {**body, "citations": []}, {**body, "citations": citations * 51}, {**body, "at": "a..b"}):
            assert client.post("/v1/citations/verify", json=bad, headers=bearer(keys)).status_code == 400
        authz.delegate(conn, delegator=U, delegate_to=A, obj="book:j", mode="read",
                       expires_at=datetime.now(timezone.utc) + timedelta(hours=1))
        out = mcp_tool_over_http(client, bearer(keys, act={"sub": "kobra-7"}), "verify_citations", body)
        assert not out.get("isError") and json.loads(out["content"][0]["text"]) == expected
        denied = mcp_tool_over_http(client, bearer(keys, sub="mehmet"), "verify_citations", body)
        assert denied["isError"] and "forbidden" in denied["content"][0]["text"]
    events = conn.execute("SELECT principal, on_behalf_of, action, object, allowed, items FROM access_event "
                          "WHERE action = 'verify' ORDER BY id").fetchall()
    canonical = [str(coderepo.parse(c)) for c in citations]
    assert events[0][:5] == (U, None, "verify", "book:j", False)
    assert (U, None, "verify", "book:j", True, canonical) in events
    assert (A, U, "verify", "book:j", True, canonical) in events
    assert events[-1][:5] == ("user:mehmet", None, "verify", "book:j", False)


# --- migration (T38, C part) -------------------------------------------------------------------------------

def test_017_applies_to_a_database_with_journals_and_binds_scopes(conn):
    applied = ["017_code_repo.sql"]
    conn.execute("ALTER TABLE note DROP CONSTRAINT note_book_scope_repo_fkey")
    conn.execute("ALTER TABLE note_citation DROP CONSTRAINT note_citation_book_repo_fkey")
    conn.execute("DROP TABLE code_repo")
    conn.execute("DELETE FROM schema_migration WHERE name = ANY(%s)", (applied,))
    journal(conn, "j")
    authz.grant(conn, "book:j", "read", U)
    assert db.migrate(conn) == applied
    assert conn.execute("SELECT count(*) FROM grant_tuple WHERE object = 'book:j'").fetchone()[0] == 1
    conn.execute("INSERT INTO profile_version (id, spec) VALUES ('pf_j', '{}')")
    with pytest.raises(Exception, match="code_repo"):
        conn.execute("INSERT INTO note (book, id, profile_id, kind, body, norm_sha256, scope_repo, search, ai_input, "
                     "source_books, tsv) VALUES ('j', %s, 'pf_j', 'finding', 'x', '\\x00', 'adc', true, true, "
                     "'{j}', ''::tsvector)", ("nt_" + "0" * 64,))
