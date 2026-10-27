"""Code citations and the verifier (docs/24 §10). Slice C owns this module; this is the minimal contract-exact
part that the read path (slice B) calls. Slice C's version (confinement checks, limits) replaces it."""
import fnmatch
import hashlib
import re
import subprocess
from dataclasses import dataclass

_HEX = re.compile(r"^[0-9a-f]{40}([0-9a-f]{24})?\Z")
_CITE = re.compile(r"^([a-z0-9][a-z0-9._-]{0,62})@([0-9a-f]{40}(?:[0-9a-f]{24})?):(.+):(\d+)(?:-(\d+))?"
                   r"(?:#([A-Za-z_][A-Za-z0-9_.:$]{0,127}))?\Z", re.S)
_ENV = {"PATH": "/usr/bin:/bin", "LC_ALL": "C", "HOME": "/nonexistent", "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_NO_REPLACE_OBJECTS": "1", "GIT_NO_LAZY_FETCH": "1",
        "GIT_TERMINAL_PROMPT": "0", "GIT_OPTIONAL_LOCKS": "0", "GIT_PROTOCOL_FROM_USER": "0", "GIT_ALLOW_PROTOCOL": ""}
MAX_BLOB = 2 * 1024 * 1024
MAX_REVS = 10000


class CitationRefused(ValueError):
    pass


@dataclass(frozen=True)
class CodeCitation:
    repo: str
    commit: str
    path: str
    line_start: int
    line_end: int
    symbol: str | None = None

    def __str__(self) -> str:
        lines = f"{self.line_start}" if self.line_start == self.line_end else f"{self.line_start}-{self.line_end}"
        return f"{self.repo}@{self.commit}:{self.path}:{lines}" + (f"#{self.symbol}" if self.symbol else "")


@dataclass(frozen=True)
class Status:
    status: str                       # verified | stale | missing | unverifiable | not_checked
    reason: str | None = None
    moved_to: int | None = None
    symbol_found_at: tuple | None = None


def parse(text: str) -> CodeCitation:
    m = _CITE.match(text) if isinstance(text, str) else None
    if not m or re.search(r"[\x00-\x1f\x7f]", m.group(3)):
        raise ValueError("malformed code citation")
    start, end = int(m.group(4)), int(m.group(5) or m.group(4))
    if start < 1 or not start <= end <= start + 199:
        raise ValueError("code citation lines must be 1..200")
    return CodeCitation(m.group(1), m.group(2), m.group(3), start, end, m.group(6))


def _git(git_dir: str, *args: str, stdin: bytes | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(["git", f"--git-dir={git_dir}", "-c", f"safe.directory={git_dir}",
                           "-c", "core.fsmonitor=false", *args], input=stdin, capture_output=True, env=_ENV,
                          timeout=5, check=False)


def _repo(conn, book: str, repo: str):
    return conn.execute("SELECT git_dir, refs, removed_at IS NOT NULL FROM code_repo WHERE book = %s AND slug = %s",
                        (book, repo)).fetchone()


def _published(git_dir: str, refs: list[str], commit: str) -> bool:
    tips = _git(git_dir, "for-each-ref", "--format=%(objectname)", "--", *refs).stdout.decode().split()[:50]
    return any(_git(git_dir, "merge-base", "--is-ancestor", commit, t).returncode == 0 for t in tips)


def _commit(git_dir: str, rev: str) -> str | None:
    out = _git(git_dir, "rev-parse", "--verify", "--end-of-options", f"{rev}^{{commit}}")
    return out.stdout.decode().strip() if out.returncode == 0 else None


def parse_range(text: str) -> tuple[str, str]:
    a, sep, b = text.partition("..") if isinstance(text, str) else ("", "", "")
    if not sep or not _HEX.match(a) or not _HEX.match(b):
        raise CitationRefused("commits must be A..B with two full commit ids")
    return a, b


def resolve_targets(conn, books, repo: str | None, branch: str | None, commit: str | None) -> dict:
    """{(book, repo): commit hex | unverifiable Status} for each book where `repo` is registered."""
    if repo is None or (branch is None and commit is None):
        return {}
    if commit is not None and not _HEX.match(commit):
        raise CitationRefused("commit must be a full commit id")
    if commit is None and (not re.match(r"^[A-Za-z0-9._/-]{1,200}\Z", branch) or branch.startswith("-")):
        raise CitationRefused("invalid branch name")
    out = {}
    for book in sorted(books):
        row = _repo(conn, book, repo)
        if row is None:
            continue
        git_dir, refs, removed = row
        if removed:
            out[(book, repo)] = Status("unverifiable", reason="repo_removed")
            continue
        if commit is not None:
            if _commit(git_dir, commit) != commit:
                out[(book, repo)] = Status("unverifiable", reason="commit_unknown")
            elif not _published(git_dir, refs, commit):
                out[(book, repo)] = Status("unverifiable", reason="commit_not_published")
            else:
                out[(book, repo)] = commit
            continue
        ref = f"refs/heads/{branch}"
        c = _commit(git_dir, ref) if any(fnmatch.fnmatchcase(ref, p) for p in refs) else None
        out[(book, repo)] = c or Status("unverifiable", reason="branch_unknown")
    return out


def _lines(data: bytes) -> list[str]:
    return data.decode("utf-8", "replace").replace("\r\n", "\n").split("\n")


def _digest(lines: list[str]) -> bytes:
    return hashlib.sha256("\n".join(line.rstrip() for line in lines).encode()).digest()


def verify_many(conn, targets: dict, cites) -> list[Status]:
    """One Status per (book, citation, excerpt_sha256), in order; no target for (book, repo) -> not_checked."""
    # (slice C computes a None excerpt_sha256 from the cite's own commit; the read path always passes it)
    out = []
    for book, cite, sha in cites:
        target = targets.get((book, cite.repo))
        if target is None:
            out.append(Status("not_checked"))
            continue
        if isinstance(target, Status):
            out.append(target)
            continue
        row = _repo(conn, book, cite.repo)
        if row is None or row[2]:
            out.append(Status("unverifiable", reason="repo_removed"))
            continue
        git_dir, refs, _ = row
        try:
            if _commit(git_dir, target) != target:
                out.append(Status("unverifiable", reason="commit_unknown"))
                continue
            if not _published(git_dir, refs, target):
                out.append(Status("unverifiable", reason="commit_not_published"))
                continue
            check = _git(git_dir, "cat-file", "--batch-check", "-z",
                         stdin=f"{target}:{cite.path}".encode() + b"\0").stdout.decode().split()
            if len(check) >= 2 and check[1] == "missing":
                out.append(Status("missing"))
                continue
            if len(check) != 3 or check[1] != "blob":
                out.append(Status("unverifiable", reason="not_a_file"))
                continue
            if int(check[2]) > MAX_BLOB:
                out.append(Status("unverifiable", reason="too_large"))
                continue
            data = _git(git_dir, "cat-file", "blob", check[0]).stdout
        except subprocess.TimeoutExpired:
            out.append(Status("unverifiable", reason="timeout"))
            continue
        if b"\0" in data:
            out.append(Status("unverifiable", reason="binary"))
            continue
        lines, n = _lines(data), cite.line_end - cite.line_start + 1
        sha = bytes(sha)
        if _digest(lines[cite.line_start - 1:cite.line_end]) == sha:
            out.append(Status("verified"))
            continue
        starts = [i + 1 for i in range(len(lines) - n + 1) if _digest(lines[i:i + n]) == sha]
        found = None
        if len(starts) != 1 and cite.symbol:
            word = re.compile(rf"(?<![A-Za-z0-9_]){re.escape(cite.symbol)}(?![A-Za-z0-9_])")
            found = tuple(i + 1 for i, line in enumerate(lines) if word.search(line))[:5]
        out.append(Status("stale", moved_to=starts[0] if len(starts) == 1 else None, symbol_found_at=found))
    return out


def rev_list(conn, book: str, repo: str, a: str, b: str) -> list[str]:
    """Commits in A..B (both full ids, both published); more than 10,000 -> ValueError."""
    row = _repo(conn, book, repo)
    if row is None or row[2] or not _HEX.match(a) or not _HEX.match(b):
        raise CitationRefused("commits must be A..B with full commit ids of a registered repository")
    git_dir, refs, _ = row
    if not (_published(git_dir, refs, a) and _published(git_dir, refs, b)):
        raise CitationRefused("commits must be reachable from a registered ref")
    out = _git(git_dir, "rev-list", f"--max-count={MAX_REVS + 1}", "--end-of-options", b, f"^{a}")
    revs = out.stdout.decode().split()
    if len(revs) > MAX_REVS:
        raise CitationRefused(f"commits range has more than {MAX_REVS} commits")
    return revs
