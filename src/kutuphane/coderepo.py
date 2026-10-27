"""Code citations and the verifier (docs/24 §10, #70).

A code citation `<repo>@<commit>:<path>:<start>[-<end>][#<symbol>]` points into a repository that an administrator
registered for the note's own book (`kutuphane repo add`). Kütüphane never fetches: the operator keeps a bare mirror
current. The verifier reads that mirror through a confined git process:

- the repository passes the confinement checks at `add` and at each open (bare, no alternates, no commondir, no
  promisor pack, an allowlisted config, inside `KUTUPHANE_REPO_ROOTS`, no symlink in its path);
- git runs with an environment built from nothing, never through a shell, and gets no request text as an argument
  except a branch name for `check-ref-format`, after it passed the checks of `branch_name`. Paths reach git only as
  one NUL-framed `cat-file` request on stdin, after control characters are refused;
- a commit counts only if a registered ref reaches it, never because it exists in the object store;
- the object type and size are checked before its content is read. No output contains code text.
"""
import dataclasses
import glob
import hashlib
import os
import re
import subprocess

from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse
from starlette.routing import Route

from . import db, gate, ids

ROOTS_ENV = "KUTUPHANE_REPO_ROOTS"
TIMEOUT = 5.0                 # seconds per git command (§10.3)
MAX_LINES = 200               # lines per citation
MAX_BLOB = 2 * 1024 * 1024    # bytes of one cited file
MAX_CITATIONS = 200           # per request
MAX_TIPS = 50                 # registered ref tips tried for reachability
MAX_RANGE = 10_000            # commits of `A..B`
HEX_LEN = {"sha1": 40, "sha256": 64}
# docs/24 §10.4: why a check could not be made. A failed check never restores authority.
REASONS = ("repo_removed", "repo_invalid", "commit_unknown", "commit_not_published", "branch_unknown", "not_a_file",
           "too_large", "binary", "timeout")

CONTROL = re.compile(r"[\x00-\x1f\x7f]")
SLUG = re.compile(r"[a-z0-9][a-z0-9._-]{0,62}")
HEX = re.compile(r"[0-9a-f]{40}(?:[0-9a-f]{24})?")
SYMBOL = re.compile(r"[A-Za-z_][A-Za-z0-9_.:$]{0,127}")
# The path is matched greedily and the line part from the right, so a path can contain ':' and '#'.
CITATION = re.compile(rf"(?P<repo>{SLUG.pattern})@(?P<commit>{HEX.pattern}):(?P<path>.+)"
                      rf":(?P<start>[1-9][0-9]{{0,8}})(?:-(?P<end>[1-9][0-9]{{0,8}}))?(?:#(?P<symbol>{SYMBOL.pattern}))?")
CONFIG_KEYS = frozenset({"core.repositoryformatversion", "core.bare", "core.filemode", "core.ignorecase",
                         "core.precomposeunicode", "core.logallrefupdates", "extensions.objectformat"})
REMOTE_KEYS = frozenset({"url", "fetch", "mirror"})
# Built from nothing, never inherited: so GIT_DIR, GIT_OBJECT_DIRECTORY, GIT_ALTERNATE_OBJECT_DIRECTORIES and
# GIT_COMMON_DIR never reach git, and no lazy fetch, prompt, lock or protocol can happen.
GIT_ENV = {"PATH": "/usr/bin:/bin", "LC_ALL": "C", "HOME": "/nonexistent", "GIT_CONFIG_NOSYSTEM": "1",
           "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_NO_REPLACE_OBJECTS": "1", "GIT_NO_LAZY_FETCH": "1",
           "GIT_TERMINAL_PROMPT": "0", "GIT_OPTIONAL_LOCKS": "0", "GIT_PROTOCOL_FROM_USER": "0", "GIT_ALLOW_PROTOCOL": ""}
BATCH_CHECK = re.compile(rb"(?P<oid>[0-9a-f]{40}(?:[0-9a-f]{24})?) (?P<type>[a-z]+) (?P<size>[0-9]{1,12})\n")


class CitationRefused(ValueError):
    """A citation, a branch, a range or a repository that cannot be used. `reason` is one of REASONS when the check
    could not be made, else a refusal of the request itself. The message never contains code text."""

    def __init__(self, reason: str, message: str | None = None):
        super().__init__(message or f"code citation refused: {reason}")
        self.reason = reason


@dataclasses.dataclass(frozen=True)
class CodeCitation:
    repo: str
    commit: str
    path: str
    line_start: int
    line_end: int
    symbol: str | None = None

    def __post_init__(self):
        # The same checks for a parsed citation and one rebuilt from a stored row: nothing else reaches git.
        if not (isinstance(self.repo, str) and SLUG.fullmatch(self.repo)):
            raise CitationRefused("invalid", "code citation: bad repository slug")
        if not (isinstance(self.commit, str) and HEX.fullmatch(self.commit)):
            raise CitationRefused("invalid", "code citation: the commit must be a full hex commit id")
        if not isinstance(self.path, str) or CONTROL.search(self.path):
            raise CitationRefused("invalid", "code citation: control character in the path")
        try:
            canonical = ids.normalize_path(self.path)
        except ValueError:
            raise CitationRefused("invalid", "code citation: unsafe or non-canonical path") from None
        if canonical != self.path:
            raise CitationRefused("invalid", "code citation: unsafe or non-canonical path")
        lines_ok = all(isinstance(n, int) and not isinstance(n, bool) for n in (self.line_start, self.line_end))
        if not lines_ok or not 1 <= self.line_start <= self.line_end < self.line_start + MAX_LINES:
            raise CitationRefused("invalid", f"code citation: lines must be start[-end], at most {MAX_LINES}")
        if self.symbol is not None and not (isinstance(self.symbol, str) and SYMBOL.fullmatch(self.symbol)):
            raise CitationRefused("invalid", "code citation: bad symbol")

    def __str__(self) -> str:
        symbol = f"#{self.symbol}" if self.symbol else ""
        return f"{self.repo}@{self.commit}:{self.path}:{self.line_start}-{self.line_end}{symbol}"


@dataclasses.dataclass(frozen=True)
class Status:
    status: str                                     # verified | stale | missing | unverifiable | not_checked
    reason: str | None = None                       # unverifiable only: one of REASONS
    moved_to: int | None = None                     # stale: where the same excerpt now starts (exactly once)
    symbol_found_at: tuple[int, ...] | None = None  # stale, not moved, with a symbol: whole-word matches (≤ 5)


def parse(text: str) -> CodeCitation:
    """`<repo>@<commit>:<path>:<start>[-<end>][#<symbol>]` (docs/24 §10.1). Raises CitationRefused."""
    if not isinstance(text, str) or CONTROL.search(text):
        raise CitationRefused("invalid", "code citation: control character")
    m = CITATION.fullmatch(text)
    if m is None:
        raise CitationRefused("invalid", "malformed code citation")
    start = int(m["start"])
    return CodeCitation(m["repo"], m["commit"], m["path"], start, int(m["end"]) if m["end"] else start, m["symbol"])


def parse_range(text: str) -> tuple[str, str]:
    """`A..B` with two full commit ids (no branch names, no short ids)."""
    parts = text.split("..") if isinstance(text, str) else []
    if len(parts) != 2 or not all(HEX.fullmatch(p) for p in parts):
        raise CitationRefused("invalid", "commits must be A..B with two full commit ids")
    return parts[0], parts[1]


def excerpt_hash(lines: list[bytes]) -> bytes:
    """docs/24 §10.3: the cited lines (already normalized by `_lines`) joined with LF, SHA-256."""
    return hashlib.sha256(b"\n".join(lines)).digest()


def _lines(content: bytes) -> list[bytes]:
    """CRLF → LF, trailing white space removed per line. A final LF ends the last line; it does not start one."""
    lines = content.replace(b"\r\n", b"\n").split(b"\n")
    if lines[-1] == b"":
        lines.pop()
    return [line.rstrip() for line in lines]


# --- git ---------------------------------------------------------------------------------------------------

def _git(args: list[str], git_dir: str | None = None, stdin: bytes | None = None) -> subprocess.CompletedProcess:
    """One git command: an argument vector, no shell, the built environment, a time limit."""
    prefix = ["git", f"--git-dir={git_dir}", "-c", f"safe.directory={git_dir}", "-c", "core.fsmonitor=false"] \
        if git_dir else ["git"]
    try:
        return subprocess.run([*prefix, *args], input=stdin, capture_output=True, env=dict(GIT_ENV), cwd="/",
                              timeout=TIMEOUT, check=False)
    except subprocess.TimeoutExpired:
        raise CitationRefused("timeout") from None


def _roots() -> list[str]:
    return [os.path.realpath(r) for r in os.environ.get(ROOTS_ENV, "").split(os.pathsep) if os.path.isabs(r)]


def check_git_dir(git_dir: str) -> None:
    """The confinement checks (docs/24 §10.2), with Python file APIs and one `git config --file`. Raises
    CitationRefused("repo_invalid") naming the failed check (never the path)."""
    def refuse(why: str):
        raise CitationRefused("repo_invalid", f"repository refused: {why}")

    if not isinstance(git_dir, str) or not os.path.isabs(git_dir) or CONTROL.search(git_dir):
        refuse("git_dir must be an absolute path without control characters")
    if os.path.realpath(git_dir) != git_dir:
        refuse("git_dir must be canonical, with no symlink in the path")
    if not any(git_dir != root and os.path.commonpath([root, git_dir]) == root for root in _roots()):
        refuse(f"git_dir is not inside {ROOTS_ENV}")
    if not os.path.isdir(git_dir):
        refuse("git_dir is not a directory (a gitfile is not accepted)")
    if not (os.path.isfile(os.path.join(git_dir, "HEAD")) and os.path.isfile(os.path.join(git_dir, "config"))
            and os.path.isdir(os.path.join(git_dir, "objects"))):
        refuse("not a bare repository (HEAD, config and objects/ are needed)")
    for name in ("commondir", "objects/info/alternates", "objects/info/http-alternates"):
        if os.path.lexists(os.path.join(git_dir, name)):
            refuse(f"{name} is not accepted")
    if glob.glob(os.path.join(glob.escape(git_dir), "objects", "pack", "*.promisor")):
        refuse("a promisor pack is not accepted")
    objects = os.path.realpath(os.path.join(git_dir, "objects"))
    if os.path.commonpath([git_dir, objects]) != git_dir:
        refuse("objects/ is outside the repository")
    out = _git(["config", "--file", os.path.join(git_dir, "config"), "--null", "--no-includes", "--list"], git_dir)
    if out.returncode != 0:
        refuse("config cannot be read")
    for entry in out.stdout.split(b"\0"):
        if entry and not _allowed_key(entry.split(b"\n", 1)[0].decode("utf-8", "replace")):
            refuse("config has a key outside the allowlist")


def _allowed_key(key: str) -> bool:
    if key in CONFIG_KEYS:
        return True
    section, _, rest = key.partition(".")
    name, _, var = rest.rpartition(".")
    return section == "remote" and bool(name) and var in REMOTE_KEYS


def _object_format(git_dir: str) -> str:
    out = _git(["rev-parse", "--show-object-format"], git_dir)
    fmt = out.stdout.decode("ascii", "replace").strip()
    if out.returncode != 0 or fmt not in HEX_LEN:
        raise CitationRefused("repo_invalid", "repository refused: unknown object format")
    return fmt


def ref_pattern(pattern: str) -> str:
    """A registered ref pattern: `git check-ref-format --normalize --allow-onelevel`, `*` allowed once."""
    if not isinstance(pattern, str) or CONTROL.search(pattern) or pattern.startswith("-") or pattern.count("*") > 1:
        raise CitationRefused("invalid", "bad ref pattern")
    out = _git(["check-ref-format", "--normalize", "--allow-onelevel", "--refspec-pattern", pattern])
    if out.returncode != 0:
        raise CitationRefused("invalid", "bad ref pattern")
    return out.stdout.decode("utf-8").strip()


def _branch_text(name) -> None:
    """The checks of a requested branch name that need no process: no control character, no option or `@{…}` form."""
    if not isinstance(name, str) or not 0 < len(name) <= 255 or CONTROL.search(name) or name.startswith("-") \
            or "@{" in name:
        raise CitationRefused("invalid", "bad branch name")


def branch_name(name: str) -> str:
    """A branch name from a request: `_branch_text`, then `git check-ref-format --branch` (which reads no
    repository). Returns `refs/heads/<name>`."""
    _branch_text(name)
    out = _git(["check-ref-format", "--branch", name])
    if out.returncode != 0 or out.stdout.decode("utf-8", "replace").strip() != name:
        raise CitationRefused("invalid", "bad branch name")
    return f"refs/heads/{name}"


# --- the registry ------------------------------------------------------------------------------------------

@dataclasses.dataclass(frozen=True)
class Repo:
    book: str
    slug: str
    git_dir: str
    object_format: str
    refs: tuple[str, ...]


def add(conn, book: str, slug: str, git_dir: str, refs: list[str], *, by: str) -> dict:
    """`kutuphane repo add` (administrator): register a bare mirror for a journal."""
    if not isinstance(slug, str) or not SLUG.fullmatch(slug):
        raise ValueError("slug must match [a-z0-9][a-z0-9._-]{0,62}")
    if conn.execute("SELECT 1 FROM journal WHERE book = %s", (book,)).fetchone() is None:
        raise ValueError(f"no such journal: {book}")
    if not 1 <= len(refs) <= 10:
        raise ValueError("give 1 to 10 --ref patterns")
    check_git_dir(git_dir)
    fmt = _object_format(git_dir)
    patterns = [ref_pattern(r) for r in refs]
    row = conn.execute("INSERT INTO code_repo (book, slug, git_dir, object_format, refs, added_by) "
                       "VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (book, slug) DO NOTHING RETURNING 1",
                       (book, slug, git_dir, fmt, patterns, by)).fetchone()
    if row is None:
        raise ValueError(f"{slug} is already a repository of {book} (a removed slug is not reused)")
    return {"book": book, "slug": slug, "git_dir": git_dir, "object_format": fmt, "refs": patterns}


def remove(conn, book: str, slug: str) -> bool:
    """`kutuphane repo remove`: new scopes and citations are refused; verification is `repo_removed`."""
    row = conn.execute("UPDATE code_repo SET removed_at = now() WHERE book = %s AND slug = %s AND removed_at IS NULL "
                       "RETURNING 1", (book, slug)).fetchone()
    return row is not None


class _Reader:
    """The git reads of one request. Every result, a refusal included, is cached for the request only, by
    (book, repo) for a repository and by (book, repo, commit[, path]) below it."""

    def __init__(self, conn):
        self.conn = conn
        self.cache: dict = {}

    def _memo(self, key, fn):
        if key not in self.cache:
            try:
                self.cache[key] = (True, fn())
            except CitationRefused as exc:
                self.cache[key] = (False, exc)
        ok, value = self.cache[key]
        if not ok:
            raise value
        return value

    def repo(self, book: str, slug: str) -> Repo:
        def open_():
            row = self.conn.execute("SELECT git_dir, object_format, refs, removed_at IS NOT NULL FROM code_repo "
                                    "WHERE book = %s AND slug = %s", (book, slug)).fetchone()
            if row is None:
                raise CitationRefused("repo_unknown", f"code citation: {slug} is not a repository of {book}")
            if row[3]:
                raise CitationRefused("repo_removed")
            check_git_dir(row[0])  # again at each open: the directory may have changed since `add`
            return Repo(book, slug, row[0], row[1], tuple(row[2]))
        return self._memo(("repo", book, slug), open_)

    def refs(self, repo: Repo) -> list[tuple[str, str]]:
        """(object id, ref name) of every ref that the registered patterns match, in ref name order."""
        def list_():
            out = _git(["for-each-ref", "--format=%(objectname) %(refname)", "--", *repo.refs], repo.git_dir)
            if out.returncode != 0:
                raise CitationRefused("repo_invalid")
            pairs = [tuple(line.split(" ", 1)) for line in out.stdout.decode("utf-8", "replace").splitlines()]
            if not all(len(p) == 2 and HEX.fullmatch(p[0]) for p in pairs):
                raise CitationRefused("repo_invalid")
            return pairs
        return self._memo(("refs", repo.book, repo.slug), list_)

    def _commit(self, repo: Repo, oid: str) -> str:
        """The commit that `oid` names, or commit_unknown. `oid` is validated hex: never request text."""
        if not HEX.fullmatch(oid):
            raise CitationRefused("commit_unknown")
        out = _git(["rev-parse", "--verify", "--quiet", "--end-of-options", f"{oid}^{{commit}}"], repo.git_dir)
        commit = out.stdout.decode("ascii", "replace").strip()
        if out.returncode != 0 or len(commit) != HEX_LEN[repo.object_format] or not HEX.fullmatch(commit):
            raise CitationRefused("commit_unknown")
        return commit

    def published(self, repo: Repo, commit: str) -> str:
        """`commit` if one of the registered refs reaches it (docs/24 §10.2): existence alone is not enough."""
        def check():
            if len(commit) != HEX_LEN[repo.object_format] or not HEX.fullmatch(commit):
                raise CitationRefused("commit_unknown")
            found = self._commit(repo, commit)
            tips = list(dict.fromkeys(oid for oid, _ in self.refs(repo)))[:MAX_TIPS]
            for tip in tips:
                out = _git(["merge-base", "--is-ancestor", "--end-of-options", found, tip], repo.git_dir)
                if out.returncode == 0:
                    return found
            raise CitationRefused("commit_not_published")
        return self._memo(("published", repo.book, repo.slug, commit), check)

    def branch(self, repo: Repo, ref: str) -> str:
        """The head commit of `ref` (= `branch_name(…)`), which a registered pattern must match."""
        def resolve():
            oid = next((o for o, name in self.refs(repo) if name == ref), None)
            if oid is None:
                raise CitationRefused("branch_unknown")
            return self._commit(repo, oid)
        return self._memo(("branch", repo.book, repo.slug, ref), resolve)

    def lines(self, repo: Repo, commit: str, path: str) -> list[bytes] | None:
        """The normalized lines of `path` at a published commit; None when the path does not exist there."""
        def read():
            self.published(repo, commit)
            if CONTROL.search(path):  # parse refused it already; one framed request must stay one request
                raise CitationRefused("invalid", "code citation: control character in the path")
            out = _git(["cat-file", "--batch-check", "-z"], repo.git_dir, stdin=f"{commit}:{path}\0".encode("utf-8"))
            if out.returncode != 0:
                raise CitationRefused("repo_invalid")
            if out.stdout.endswith(b" missing\n") and out.stdout.count(b"\n") == 1:
                return None
            m = BATCH_CHECK.fullmatch(out.stdout)
            if m is None or m["type"] != b"blob":
                raise CitationRefused("not_a_file")
            if int(m["size"]) > MAX_BLOB:
                raise CitationRefused("too_large")
            blob = _git(["cat-file", "blob", "--end-of-options", m["oid"].decode("ascii")], repo.git_dir)
            if blob.returncode != 0 or len(blob.stdout) != int(m["size"]):
                raise CitationRefused("repo_invalid")
            if b"\0" in blob.stdout:
                raise CitationRefused("binary")
            return _lines(blob.stdout)
        return self._memo(("lines", repo.book, repo.slug, commit, path), read)


def _cited(reader: _Reader, repo: Repo, cite: CodeCitation) -> list[bytes] | None:
    """The cited lines at the citation's own commit; None when the path or the lines do not exist there."""
    lines = reader.lines(repo, cite.commit, cite.path)
    if lines is None or cite.line_end > len(lines):
        return None
    return lines[cite.line_start - 1:cite.line_end]


# --- the contract (docs/24 §16) ----------------------------------------------------------------------------

def excerpt(conn, book: str, cite: CodeCitation) -> bytes:
    """The excerpt hash (32 bytes) of a citation at its own commit, for the write path (docs/24 §6.1 step 7).
    Raises CitationRefused for an unknown or removed repository, an unpublished commit, a missing path or line, and
    every other failed check."""
    reader = _Reader(conn)
    lines = _cited(reader, reader.repo(book, cite.repo), cite)
    if lines is None:
        raise CitationRefused("missing", "code citation: the path or the lines do not exist at that commit")
    return excerpt_hash(lines)


def resolve_targets(conn, books: list[str], repo: str | None, branch: str | None,
                    commit: str | None) -> dict[tuple[str, str], str | Status]:
    """The code target of each requested book where `repo` is registered (docs/24 §9.2): `commit` if given, else the
    head of `branch` in that book's own repository. A target that cannot be resolved is an `unverifiable` Status,
    so the citations into that repository are not current. Books without the slug have no target."""
    if repo is None or (branch is None and commit is None):
        return {}
    if commit is not None:
        if not isinstance(commit, str) or not HEX.fullmatch(commit):
            raise CitationRefused("invalid", "commit must be a full commit id")
        ref = None
    else:
        ref = branch_name(branch)
    reader = _Reader(conn)
    out: dict[tuple[str, str], str | Status] = {}
    for (book,) in conn.execute("SELECT book FROM code_repo WHERE book = ANY(%s) AND slug = %s ORDER BY book",
                                (list(books), repo)).fetchall():
        try:
            r = reader.repo(book, repo)
            out[(book, repo)] = reader.published(r, commit) if ref is None else reader.branch(r, ref)
        except CitationRefused as exc:
            out[(book, repo)] = _unverifiable(exc)
    return out


def verify_many(conn, targets: dict, cites: list[tuple[str, CodeCitation, bytes | None]]) -> list[Status]:
    """One Status per `(book, citation, stored excerpt hash)` (docs/24 §10.4), in order. A stored hash of None is
    computed from the citation's own commit (verify_citations). No target for (book, repo): `not_checked`."""
    if len(cites) > MAX_CITATIONS:
        raise CitationRefused("invalid", f"at most {MAX_CITATIONS} citations per request")
    reader = _Reader(conn)
    out = []
    for book, cite, stored in cites:
        target = targets.get((book, cite.repo))
        if target is None:
            out.append(Status("not_checked"))
        elif isinstance(target, Status):
            out.append(target)
        else:
            try:
                out.append(_verify(reader, book, cite, stored, target))
            except CitationRefused as exc:
                out.append(_unverifiable(exc))
    return out


def _unverifiable(exc: CitationRefused) -> Status:
    if exc.reason not in REASONS:
        raise exc
    return Status("unverifiable", exc.reason)


def _verify(reader: _Reader, book: str, cite: CodeCitation, stored: bytes | None, target: str) -> Status:
    repo = reader.repo(book, cite.repo)
    old = None
    if stored is None:
        old = _cited(reader, repo, cite)
        if old is None:
            return Status("missing")
        stored = excerpt_hash(old)
    now = reader.lines(repo, target, cite.path)
    if now is None:
        return Status("missing")
    window = now[cite.line_start - 1:cite.line_end]
    if len(window) == cite.line_end - cite.line_start + 1 and excerpt_hash(window) == stored:
        return Status("verified")
    if old is None:
        try:
            old = _cited(reader, repo, cite)
        except CitationRefused:
            old = None  # the stored hash still decides `stale`; only `moved_to` needs the old lines
    moved_to = _moved_to(now, old) if old else None
    found = None
    if moved_to is None and cite.symbol:
        word = re.compile(rb"(?<![A-Za-z0-9_$])" + re.escape(cite.symbol.encode("ascii")) + rb"(?![A-Za-z0-9_$])")
        found = tuple(i for i, line in enumerate(now, start=1) if word.search(line))[:5]
    return Status("stale", moved_to=moved_to, symbol_found_at=found)


def _moved_to(now: list[bytes], old: list[bytes]) -> int | None:
    """The first line where `old` starts in `now`, if it occurs exactly once."""
    hits = [i + 1 for i in range(len(now) - len(old) + 1) if now[i] == old[0] and now[i:i + len(old)] == old]
    return hits[0] if len(hits) == 1 else None


def rev_list(conn, book: str, repo: str, a: str, b: str) -> list[str]:
    """The commits of `A..B` (reachable from B, not from A); both must be published (docs/24 §10.3)."""
    for x in (a, b):
        if not isinstance(x, str) or not HEX.fullmatch(x):
            raise CitationRefused("invalid", "commits must be A..B with two full commit ids")
    reader = _Reader(conn)
    r = reader.repo(book, repo)
    a, b = reader.published(r, a), reader.published(r, b)
    out = _git(["rev-list", f"--max-count={MAX_RANGE + 1}", "--end-of-options", b, f"^{a}"], r.git_dir)
    if out.returncode != 0:
        raise CitationRefused("repo_invalid")
    commits = out.stdout.decode("ascii", "replace").split()
    if len(commits) > MAX_RANGE:
        raise CitationRefused("invalid", f"the range has more than {MAX_RANGE} commits")
    return commits


# --- verify_citations (MCP) / POST /v1/citations/verify (HTTP), docs/24 §10.5 -------------------------------

def op_verify(dsn: str, actor: gate.Actor, book, citations, at) -> dict:
    if not isinstance(book, str) or not isinstance(at, str) or not isinstance(citations, list) \
            or not all(isinstance(c, str) for c in citations):
        raise ValueError("book and at must be strings, citations a list of strings")
    if not 1 <= len(citations) <= MAX_CITATIONS:
        raise ValueError(f"give 1 to {MAX_CITATIONS} citations")
    cites = [parse(c) for c in citations]  # no I/O before the decision
    commit = at if HEX.fullmatch(at) else None
    if commit is None:
        _branch_text(at)  # the git check of the name runs after the decision

    def work():
        targets = {}
        for slug in sorted({c.repo for c in cites}):
            targets.update(resolve_targets(conn, [book], slug, None if commit else at, commit))
        statuses = verify_many(conn, targets, [(book, c, None) for c in cites])
        return {"targets": {f"{b}/{r}": (t if isinstance(t, str) else None) for (b, r), t in sorted(targets.items())},
                "results": [{"citation": str(c), "status": s.status, "moved_to": s.moved_to,
                             "symbol_found_at": list(s.symbol_found_at) if s.symbol_found_at is not None else None,
                             "reason": s.reason} for c, s in zip(cites, statuses)]}

    obj = f"book:{book}"
    with db.connect(dsn) as conn:
        return gate.guard_many(conn, actor, {obj: {"read"}}, work, action="verify",
                               items={obj: [str(c) for c in cites]})


def register_mcp(mcp, deps) -> None:
    @mcp.tool()
    @deps.mcp_errors
    async def verify_citations(book: str, citations: list[str], at: str) -> dict:
        """Check code citations (`repo@commit:path:start-end[#symbol]`) of a journal's repositories against `at`
        (a branch name or a full commit id): verified, stale (with moved_to), missing, or unverifiable with a
        reason. No code text is returned. Needs read on the book."""
        return await run_in_threadpool(op_verify, deps.dsn, deps.mcp_actor(), book, citations, at)


def http_routes(deps, endpoint) -> list:
    async def h_verify(request, actor):
        try:
            body = await request.json()
        except ValueError:
            raise ValueError("JSON body required") from None
        if not isinstance(body, dict):
            raise ValueError("JSON object required")
        return JSONResponse(await run_in_threadpool(op_verify, deps.dsn, actor, body.get("book"),
                                                    body.get("citations"), body.get("at")))
    return [Route("/v1/citations/verify", endpoint(h_verify), methods=["POST"])]
