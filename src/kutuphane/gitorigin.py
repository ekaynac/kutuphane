"""Origin proposals from a source repository (G34, docs/26 §6; part of G6, docs/15 §3) for `kstd-init`.

`kstd-init` runs on a copy of a folder (docs/15 §4), and a copy has no git history. `kstd-init --source-repo <repo>
[--commit <rev>]` reads the history of a LOCAL repository and proposes an origin for each file of the copy:

- **match**: the file is in the tree of the commit (default `HEAD`) at the same path (or the same end of a path:
  a copy of a subfolder) with the same content, or its content (the git blob id) is at another path of that tree.
  A file whose path is in the tree with other content has no evidence for the change: it stays `unknown`. A file
  with no match stays `unknown`;
- **history**: every non-merge commit up to that commit that changed the matched path, back to the commit that added
  it (renames are followed, `-M`);
- **proposal**: `model` when every one of these commits has a `Co-Authored-By` trailer (git's own trailer parsing)
  with a known model agent (names_model); else `unknown`.

A proposal is never authority (D63/D64, R1). `human` is never proposed: a person's commit does not prove that a
person wrote the words. `assisted` needs a named reviewer, and `tool` a software agent, so neither is proposed
either. `model` and `unknown` are handled the same way (docs/11 §5), so a wrong proposal gives no permission.

Git runs read-only and without network: no lazy fetch of a partial clone (`GIT_NO_LAZY_FETCH`), no transport
(`protocol.allow=never`), no replace refs, no fsmonitor, no signature check, no pager, no external diff.
"""
import hashlib
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from .ids import normalize_path
from .kstd import MANIFEST

TIMEOUT_S = 120
EVIDENCE_COMMITS = 10  # commits listed per item; the reason gives the full count
SHORT = 12
_GIT = ("git", "--no-pager", "--no-replace-objects", "-c", "protocol.allow=never", "-c", "core.fsmonitor=false",
        "-c", "log.showSignature=false", "-c", "color.ui=false", "-c", "core.quotePath=false")
_ENV = {"GIT_NO_LAZY_FETCH": "1", "GIT_TERMINAL_PROMPT": "0", "GIT_OPTIONAL_LOCKS": "0", "GIT_PAGER": "cat",
        "GIT_NO_REPLACE_OBJECTS": "1", "LC_ALL": "C"}
_STATUS = re.compile(r"\A[ACDMRTUXB]\d*\Z")
_HASH = re.compile(r"\A(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")
# Known model agents: a service address, a bot account, or a model name. A first name alone ("Claude Monet",
# "Devin Smith") is not a model.
_AGENT_ADDRESS = re.compile(
    r"(?i)<(?:noreply@anthropic\.com|[^<>@\s]*@openai\.com|cursoragent@cursor\.com|noreply@aider\.chat|"
    r"(?:\d+\+)?(?:copilot|copilot-swe-agent|claude|devin-ai-integration|google-labs-jules|gemini-code-assist|"
    r"chatgpt-codex-connector|openai-codex)(?:\[bot\])?@users\.noreply\.github\.com)>")
_AGENT_NAME = re.compile(
    r"(?i)\A(?:claude(?:[ -](?:code|opus|sonnet|haiku|instant|\d)\b.*|\[bot\])|(?:chat)?gpt-?\d.*|chatgpt\b.*|"
    r"o\d(?:-mini|-pro)?|(?:openai )?codex\b.*|(?:github )?copilot\b.*|copilot-swe-agent.*|"
    r"gemini(?: \d.*| code assist.*| cli.*|-code-assist.*)|aider\b.*|cursor ?agent\b.*|devin-ai(?:-integration)?\b.*|"
    r"google-labs-jules.*)\Z")


class GitError(ValueError):
    pass


@dataclass(frozen=True)
class Proposal:
    origin: str               # model | unknown, never more
    reason: str               # one line: the match and the count
    evidence: list = field(default_factory=list)  # "<commit> <trailer line>" or "<commit> no model trailer"


@dataclass(frozen=True)
class Proposals:
    repo: str
    commit: str
    shallow: bool
    items: dict               # path → Proposal


def names_model(trailer_value: str) -> bool:
    """A `Co-Authored-By` value (`Name <address>`) that names a known model agent."""
    name = trailer_value.split("<", 1)[0].strip()
    return bool(_AGENT_ADDRESS.search(trailer_value) or _AGENT_NAME.match(name))


def _run(repo: Path, *args: str, check: bool = True) -> bytes:
    """git in `repo` itself: GIT_CEILING_DIRECTORIES stops the search for an enclosing repository."""
    env = {**os.environ, **_ENV, "GIT_CEILING_DIRECTORIES": str(repo.resolve().parent)}
    try:
        out = subprocess.run([*_GIT, "-C", str(repo), *args], capture_output=True, timeout=TIMEOUT_S, check=False,
                             stdin=subprocess.DEVNULL, env=env)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise GitError(f"git {args[0]} failed: {type(exc).__name__}") from None
    if check and out.returncode != 0:
        raise GitError(f"git {args[0]}: {out.stderr.decode('utf-8', 'replace').strip() or out.returncode}")
    return out.stdout


def _path(raw: bytes) -> str | None:
    try:
        return normalize_path(raw.decode("utf-8", "surrogateescape"))
    except ValueError:
        return None


def _open(repo, rev: str) -> tuple[Path, str, str, bool]:
    """(repository, full commit id, object format, shallow). Local repositories only."""
    if re.match(r"\A[A-Za-z][A-Za-z0-9+.-]*://", str(repo)) or re.match(r"\A[^/]+@[^/:]+:", str(repo)):
        raise GitError(f"{repo}: not a local path (kstd-init reads only local repositories)")
    repo = Path(repo)
    if not repo.is_dir():
        raise GitError(f"{repo}: not a directory")
    if not _run(repo, "rev-parse", "--git-dir", check=False).strip():
        raise GitError(f"{repo}: not a git repository (the folder itself, not a parent)")
    if rev.startswith("-"):
        raise GitError(f"--commit {rev!r}: not a revision")
    commit = _run(repo, "rev-parse", "--verify", "--quiet", "--end-of-options", f"{rev}^{{commit}}",
                  check=False).decode().strip()
    if not _HASH.match(commit):
        raise GitError(f"--commit {rev!r}: no such commit in {repo}")
    fmt = _run(repo, "rev-parse", "--show-object-format").decode().strip() or "sha1"
    shallow = _run(repo, "rev-parse", "--is-shallow-repository").decode().strip() == "true"
    return repo, commit, fmt, shallow


def _blob_id(data: bytes, fmt: str) -> str:
    return hashlib.new("sha256" if fmt == "sha256" else "sha1", b"blob %d\0" % len(data) + data).hexdigest()


def _tree(repo: Path, commit: str) -> dict[str, str]:
    """{path: blob id} of the commit's tree (regular files and symlinks; no submodules)."""
    tree = {}
    for entry in _run(repo, "ls-tree", "-r", "-z", "--full-tree", commit).split(b"\0"):
        if not entry:
            continue
        meta, _, raw = entry.partition(b"\t")
        _mode, kind, oid = meta.decode().split(" ")
        if kind == "blob" and (path := _path(raw)) is not None:
            tree[path] = oid
    return tree


def _history(repo: Path, commit: str) -> list[tuple[str, list[tuple[str, str | None, str]]]]:
    """[(commit id, [(status, old path, new path)])], newest first (topological), non-merge commits only."""
    tokens = _run(repo, "log", "-z", "-M", "--no-merges", "--topo-order", "--name-status", "--no-ext-diff",
                  "--no-textconv", "--format=%H", commit, "--").split(b"\0")
    commits, i = [], 0
    while i < len(tokens):
        token = tokens[i].lstrip(b"\n").decode("utf-8", "surrogateescape")
        i += 1
        if not token:
            continue
        if _HASH.match(token):
            commits.append((token, []))
        elif _STATUS.match(token) and commits:
            if token[0] in "RC":
                old, new = _path(tokens[i]), _path(tokens[i + 1])
                i += 2
            else:
                old, new = None, _path(tokens[i])
                i += 1
            if new is not None:
                commits[-1][1].append((token[0], old, new))
        else:
            raise GitError(f"git log: unexpected output near {token[:40]!r}")
    return commits


def _trailers(repo: Path, commit: str) -> dict[str, list[str]]:
    """{commit id: its Co-Authored-By trailer lines}, as git parses the trailers of each message."""
    out = {}
    raw = _run(repo, "log", "-z", "--no-merges", "--format=%H%n%(trailers:key=Co-authored-by,unfold)", commit, "--")
    for record in raw.decode("utf-8", "replace").split("\0"):
        lines = record.strip("\n").split("\n")
        if lines and _HASH.match(lines[0]):
            out[lines[0]] = [" ".join(t.split()) for t in lines[1:] if t.strip()]
    return out


def _commits_of(path: str, history, index: dict[str, list[int]]) -> list[str]:
    """The commits that changed `path`, newest first, following renames back to the commit that added it."""
    found, name, start = [], path, 0
    while True:
        later = [n for n in index.get(name, ()) if n >= start]
        if not later:
            return found
        n = later[0]
        found.append(history[n][0])
        status, old = next((s, o) for s, o, new in history[n][1] if new == name)
        if status == "A" or (status in "RC" and old is None):
            return found
        if status in "RC":
            name = old
        start = n + 1


def propose(repo: Path, files: list, rev: str = "HEAD") -> Proposals:
    """A Proposal for every file of the copy except kstd.yaml (source.SourceFile list)."""
    repo, commit, fmt, shallow = _open(repo, rev)
    tree, history = _tree(repo, commit), _history(repo, commit)
    trailers = _trailers(repo, commit)
    by_blob: dict[str, list[str]] = {}
    tails: dict[str, list[str]] = {}  # "b/c.md" → ["a/b/c.md"]: a copy of a subfolder keeps the end of each path
    for path, oid in sorted(tree.items()):
        by_blob.setdefault(oid, []).append(path)
        parts = path.split("/")
        for n in range(1, len(parts)):
            tails.setdefault("/".join(parts[n:]), []).append(path)
    index: dict[str, list[int]] = {}
    for n, (_, changes) in enumerate(history):
        for status, _, new in changes:
            if status != "D":
                index.setdefault(new, []).append(n)
    short = commit[:SHORT]
    items = {}
    for f in files:
        if f.path == MANIFEST:
            continue
        oid = _blob_id(f.data, fmt)
        same_path = [f.path] if f.path in tree else tails.get(f.path, [])
        if oid in by_blob:
            matched = next((p for p in same_path if tree[p] == oid), by_blob[oid][0])
            how = f"{matched} at {short} ({'same path and content' if matched in same_path else 'same content'})"
        elif len(same_path) == 1:
            items[f.path] = Proposal("unknown", f"the content differs from {same_path[0]} at {short}: no evidence "
                                                f"for the change (another --commit?)")
            continue
        else:
            items[f.path] = Proposal("unknown", f"not in the source repository at {short} (no path or content "
                                                f"match)")
            continue
        commits = _commits_of(matched, history, index)
        named = {c: [t for t in trailers.get(c, []) if names_model(t.split(":", 1)[1])] for c in commits}
        lines = []
        for c in commits[:EVIDENCE_COMMITS]:
            own = named[c] or trailers.get(c, [])
            lines += [f"{c[:SHORT]} {t}" for t in own] + ([] if named[c] else [f"{c[:SHORT]} no model trailer"])
        if len(commits) > EVIDENCE_COMMITS:
            lines.append(f"… {len(commits) - EVIDENCE_COMMITS} older commits")
        models = sum(1 for c in commits if named[c])
        origin = "model" if commits and models == len(commits) else "unknown"
        items[f.path] = Proposal(origin, f"{models} of {len(commits)} commits name a model; {how}", lines)
    return Proposals(str(repo), commit, shallow, items)
