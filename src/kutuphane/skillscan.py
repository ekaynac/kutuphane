"""SkillSpector as an optional external scanner of skill folders (D71, docs/24 §22).

SkillSpector is never imported, vendored or shipped: it runs as a subprocess from its own venv
(deploy/skillspector/install.sh), only in static mode (`--no-llm`), with a minimal environment: no provider keys, no
`LANGSMITH_*`, only PATH, HOME (an empty temporary folder) and LANG. Its SC4 check still sends dependency names to
api.osv.dev; KUTUPHANE_SKILLSPECTOR_PROXY gives the subprocess a proxy (a dead port blocks that egress, and SC4 then
uses its bundled list). Nothing else reaches the network from here.

One scan record per skill folder (a folder with SKILL.md, agentfiles.skill_dirs) and content version. A record is a
curator proposal with origin `tool` and software_agent {skillspector, version}, never an approval:
- `DO_NOT_INSTALL`, coverage that is not `complete`, or a failed scan (crash, timeout, bad report) blocks `activate`
  on every file of that skill at once (R1: an unconfirmed gate proposal applies when it is stricter). A failed scan
  blocks, so a skill cannot escape the scanner by breaking it.
- A later, looser scan never lifts a block. Only a person who holds `curate` lifts it (`kutuphane skill clear`),
  for exactly those bytes (input digest) and that report (tool version, report digest).
- `SAFE` grants nothing: an agent still needs its `activate` grant.
- `not_scanned` (no tool configured, or a version that is not allowed) does not block.
- A scan with another tool version marks the records of other versions `stale`; the next ingest of that content, or
  `kutuphane skill rescan`, scans again. A stale record keeps its block.

The block itself is the SQL function `skill_blocked` (migration 021), which the gate and the search use.
"""
import json
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from psycopg.types.json import Jsonb

from . import agentfiles, authz, ids

TOOL = "skillspector"
TESTED_VERSION = "2.13.1"  # == deploy/skillspector/skillspector.pin SKILLSPECTOR_VERSION
MODE = "no-llm"  # static rules that people wrote: origin `tool` (D63/D64); an LLM mode would be `model`
BIN_ENV = "KUTUPHANE_SKILLSPECTOR_BIN"
ALLOW_ENV = "KUTUPHANE_SKILLSPECTOR_ALLOW_VERSION"  # one exact other version the operator allows
TIMEOUT_ENV = "KUTUPHANE_SKILLSPECTOR_TIMEOUT"
PROXY_ENV = "KUTUPHANE_SKILLSPECTOR_PROXY"
DEFAULT_TIMEOUT = 120.0
RECOMMENDATIONS = ("SAFE", "CAUTION", "DO_NOT_INSTALL")
VOLATILE = frozenset({"finding_id", "scanned_at"})  # random or a clock: never part of the report digest
VERSION = re.compile(r"\bv?(\d+\.\d+\.\d+[0-9A-Za-z.+-]*)\s*\Z")
MAX_REASON = 500


@dataclass(frozen=True)
class Tool:
    bin: str
    version: str


@dataclass(frozen=True)
class Scan:
    """One scan of one skill folder. `status`: scanned | failed | not_scanned."""
    status: str
    input_digest: str
    tool_version: str | None = None
    report_digest: str | None = None
    recommendation: str | None = None
    score: int | None = None
    completeness: str | None = None
    findings: list = field(default_factory=list)
    reason: str | None = None

    @property
    def blocking(self) -> bool:
        """The same rule as the view `skill_block` (before a curator clears it)."""
        return self.status == "failed" or (self.status == "scanned" and (
            self.recommendation == "DO_NOT_INSTALL" or self.completeness != "complete"))


class Unavailable(Exception):
    """The tool cannot be used (not configured, not runnable, a version that is not allowed): `not_scanned`."""


# --- the tool ------------------------------------------------------------------------------------------------

def _timeout() -> float:
    value = os.environ.get(TIMEOUT_ENV)
    try:
        timeout = float(value) if value else DEFAULT_TIMEOUT
    except ValueError:
        raise ValueError(f"{TIMEOUT_ENV} must be a number of seconds") from None
    if timeout <= 0:
        raise ValueError(f"{TIMEOUT_ENV} must be positive")
    return timeout


def _env(home: str) -> dict:
    """The whole environment of the subprocess: nothing of ours (keys, tokens, LANGSMITH_*) is passed on."""
    env = {"PATH": "/usr/bin:/bin", "HOME": home, "LANG": "C.UTF-8", "NO_COLOR": "1",
           "SKILLSPECTOR_LOG_LEVEL": "ERROR"}
    if proxy := os.environ.get(PROXY_ENV):
        env |= {"HTTPS_PROXY": proxy, "HTTP_PROXY": proxy, "ALL_PROXY": proxy}
    return env


def probe() -> Tool:
    """The configured tool and its version, or Unavailable. An unknown version is refused unless allowed."""
    bin_ = os.environ.get(BIN_ENV)
    if not bin_:
        raise Unavailable(f"SkillSpector is not configured ({BIN_ENV} is not set)")
    if not (os.path.isfile(bin_) and os.access(bin_, os.X_OK)):
        raise Unavailable(f"{BIN_ENV} is not an executable file")
    with tempfile.TemporaryDirectory(prefix="skillscan-") as home:
        try:
            out = subprocess.run([bin_, "--version"], env=_env(home), cwd=home, capture_output=True,
                                 timeout=_timeout(), check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise Unavailable(f"`{TOOL} --version` failed: {type(exc).__name__}") from None
    match = VERSION.search(out.stdout.decode("utf-8", errors="replace").strip())
    if out.returncode != 0 or not match:
        raise Unavailable(f"`{TOOL} --version` gave no version (exit {out.returncode})")
    version = match.group(1)
    if version not in (TESTED_VERSION, os.environ.get(ALLOW_ENV)):
        raise Unavailable(f"{TOOL} {version} is not the tested {TESTED_VERSION}; set {ALLOW_ENV}={version} to "
                          "allow it")
    return Tool(bin_, version)


def _normalize(value, root: str, skill_path: str):
    """Drop the volatile keys; name the scanned folder by its path in the book, not by the temporary folder."""
    if isinstance(value, dict):
        return {k: _normalize(v, root, skill_path) for k, v in value.items() if k not in VOLATILE}
    if isinstance(value, list):
        return [_normalize(v, root, skill_path) for v in value]
    if isinstance(value, str):
        return value.replace(root, skill_path)
    return value


def _failed(digest: str, tool: Tool, reason: str) -> Scan:
    return Scan("failed", digest, tool.version, reason=reason[:MAX_REASON])


def _report(digest: str, tool: Tool, raw: bytes, root: str, skill_path: str) -> Scan:
    try:
        report = _normalize(json.loads(raw), root, skill_path)
        risk, completeness = report["risk_assessment"], report["analysis_completeness"]
        recommendation, score, status = risk["recommendation"], risk["score"], completeness["status"]
        version, issues = report["metadata"]["skillspector_version"], report["issues"]
    except (ValueError, TypeError, KeyError) as exc:
        return _failed(digest, tool, f"no valid report: {type(exc).__name__}")
    if version != tool.version:
        return _failed(digest, tool, f"the report names version {version!r}, not {tool.version}")
    if (recommendation not in RECOMMENDATIONS or not isinstance(score, int) or isinstance(score, bool)
            or not 0 <= score <= 100 or not isinstance(status, str) or not isinstance(issues, list)):
        return _failed(digest, tool, "the report has an unknown recommendation, score, completeness or issue list")
    return Scan("scanned", digest, tool.version, ids.sha256_hex(ids.canonical(report)), recommendation, score,
                status, issues)


def input_digest(files: dict[str, str]) -> str:
    """`files`: {path relative to the skill folder: sha256}. The exact bytes a scan (and a clearance) is about."""
    return ids.sha256_hex(ids.canonical({"kind": "skill_input", "v": 1, "files": sorted(files.items())}))


def run(tool: Tool, skill_path: str, files: dict[str, bytes]) -> Scan:
    """Scan one skill folder. `files`: {path relative to the skill folder: bytes}. Never raises for the tool's
    behavior: a crash, a timeout or a bad report is a `failed` scan."""
    digest = input_digest({p: ids.sha256_hex(d) for p, d in files.items()})
    with tempfile.TemporaryDirectory(prefix="skillscan-") as work:
        root = os.path.join(work, "skill")
        for rel, data in files.items():
            parts = PurePosixPath(ids.normalize_path(rel)).parts  # no absolute path, no '..'
            target = Path(root, *parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        try:
            out = subprocess.run([tool.bin, "scan", root, "--no-llm", "--format", "json"], env=_env(work), cwd=work,
                                 capture_output=True, timeout=_timeout(), check=False)
        except subprocess.TimeoutExpired:
            return _failed(digest, tool, f"timeout after {_timeout():g} s")
        except OSError as exc:
            return _failed(digest, tool, f"could not run: {type(exc).__name__}")
        if out.returncode not in (0, 1):  # 0 and 1 carry a verdict; 2 is an execution failure
            return _failed(digest, tool, f"exit {out.returncode}")
        return _report(digest, tool, out.stdout, root, skill_path)


def _under(skill_path: str, path: str) -> str | None:
    """The path relative to the skill folder, or None when the file is not inside it."""
    if skill_path == ".":
        return path
    return path[len(skill_path) + 1:] if path.startswith(skill_path + "/") else None


def skill_files(skill_path: str, files) -> dict:
    """{relative path: file} of the files (anything with .path) inside one skill folder."""
    return {rel: f for f in files if (rel := _under(skill_path, f.path)) is not None}


def scan_files(files) -> list[tuple[str, Scan]]:
    """Scan every skill folder of a file list, without a database (package receive). `files`: .path, .data."""
    files = list(files)
    skills = sorted(agentfiles.skill_dirs(f.path for f in files))
    if not skills:
        return []
    try:
        tool = probe()
    except Unavailable as exc:
        return [(s, _not_scanned(s, files, str(exc))) for s in skills]
    return [(s, run(tool, s, {r: f.data for r, f in skill_files(s, files).items()})) for s in skills]


def _not_scanned(skill_path: str, files, reason: str) -> Scan:
    return Scan("not_scanned", input_digest({r: f.sha256 for r, f in skill_files(skill_path, files).items()}),
                reason=reason[:MAX_REASON])


def finding(skill_path: str, scan: Scan) -> dict:
    """A package-import finding: the proposal, for the person who approves the import."""
    out = {"path": skill_path, "kind": "skill_scan", "status": scan.status, "blocking": scan.blocking}
    if scan.tool_version:
        out |= {"origin": "tool", "software_agent": {"name": TOOL, "version": scan.tool_version}}
    if scan.status == "scanned":
        out |= {"recommendation": scan.recommendation, "score": scan.score, "completeness": scan.completeness,
                "issues": len(scan.findings)}
    else:
        out["note"] = scan.reason
    return out


# --- records ------------------------------------------------------------------------------------------------

_COLUMNS = ("status", "input_digest", "tool_version", "report_digest", "recommendation", "score", "completeness",
            "findings", "reason")


def _scan_of(row) -> Scan:
    return Scan(*row[:7], row[7] if row[7] is not None else [], row[8])


def plan(conn, book: str, content_id: str, files) -> list[tuple[str, Scan]]:
    """The scans to record for one content version, made before its publication transaction. `files`: .path,
    .sha256, .data. A skill with a fresh `scanned` record of this version and tool version needs nothing; a record
    of the same bytes and tool version in this book is reused; anything else runs the tool. Without a usable tool,
    a skill with no record at all gets `not_scanned`."""
    files = list(files)
    skills = sorted(agentfiles.skill_dirs(f.path for f in files))
    if not skills:
        return []
    try:
        tool = probe()
    except Unavailable as exc:
        recorded = {p for (p,) in conn.execute("SELECT DISTINCT skill_path FROM skill_scan WHERE book = %s AND "
                                               "content_id = %s", (book, content_id))}
        return [(s, _not_scanned(s, files, str(exc))) for s in skills if s not in recorded]
    out = []
    for skill_path in skills:
        mine = skill_files(skill_path, files)
        digest = input_digest({r: f.sha256 for r, f in mine.items()})
        fresh = conn.execute("SELECT 1 FROM skill_scan WHERE book = %s AND content_id = %s AND skill_path = %s "
                             "AND input_digest = %s AND status = 'scanned' AND tool_version = %s AND mode = %s "
                             "AND NOT stale LIMIT 1", (book, content_id, skill_path, digest, tool.version, MODE)
                             ).fetchone()
        if fresh:
            continue
        same = conn.execute(f"SELECT {', '.join(_COLUMNS)} FROM skill_scan WHERE book = %s AND input_digest = %s "
                            "AND status = 'scanned' AND tool_version = %s AND mode = %s AND NOT stale "
                            "ORDER BY id DESC LIMIT 1", (book, digest, tool.version, MODE)).fetchone()
        out.append((skill_path, _scan_of(same) if same else run(tool, skill_path,
                                                                 {r: f.data for r, f in mine.items()})))
    return out


def store(conn, book: str, content_id: str, scans: list[tuple[str, Scan]]) -> None:
    """Record the planned scans (inside the publication transaction, so a block is in force with the version), and
    mark the records of every other tool version stale."""
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO skill_scan (book, content_id, skill_path, status, input_digest, tool_version, mode, "
            "report_digest, recommendation, score, completeness, findings, reason) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            [(book, content_id, p, s.status, s.input_digest, s.tool_version,
              None if s.status == "not_scanned" else MODE, s.report_digest, s.recommendation, s.score,
              s.completeness, Jsonb(s.findings) if s.status == "scanned" else None, s.reason) for p, s in scans])
    versions = {s.tool_version for _, s in scans if s.tool_version}
    for version in versions:
        conn.execute("UPDATE skill_scan SET stale = true WHERE NOT stale AND status <> 'not_scanned' "
                     "AND tool_version <> %s", (version,))


def summary(scans: list[tuple[str, Scan]]) -> list[dict]:
    """What a publication reports about its skill scans."""
    return [{"skill_path": p, "status": s.status, "recommendation": s.recommendation, "score": s.score,
             "completeness": s.completeness, "blocking": s.blocking, "reason": s.reason} for p, s in scans]


class _Blob:
    __slots__ = ("path", "sha256", "data")

    def __init__(self, path, sha256, data):
        self.path, self.sha256, self.data = path, sha256, data


def _current(conn, book: str | None) -> list[tuple[str, str]]:
    rows = conn.execute("SELECT slug, current_content FROM book WHERE current_content IS NOT NULL "
                        "AND (%(b)s::text IS NULL OR slug = %(b)s) ORDER BY slug", {"b": book}).fetchall()
    if book is not None and not rows:
        raise LookupError(f"no published book: {book}")
    return rows


def rescan(conn, book: str | None = None) -> list[dict]:
    """Scan the skills of the current version of one book (or of every book) again where no fresh record of the
    configured tool version exists: stale, failed, never scanned, or scanned by another version."""
    out = []
    for slug, content_id in _current(conn, book):
        manifest = conn.execute("SELECT m.entry->>'path', m.entry->>'sha256' FROM content_version c "
                                "CROSS JOIN LATERAL jsonb_array_elements(c.manifest) AS m(entry) "
                                "WHERE c.book = %s AND c.id = %s", (slug, content_id)).fetchall()
        skills = agentfiles.skill_dirs(p for p, _ in manifest)
        inside = [(p, h) for p, h in manifest if any(_under(s, p) is not None for s in skills)]
        blobs = dict(conn.execute("SELECT sha256, data FROM blob WHERE sha256 = ANY(%s)",
                                  ([h for _, h in inside],)).fetchall())
        scans = plan(conn, slug, content_id, [_Blob(p, h, bytes(blobs[h])) for p, h in inside])
        with conn.transaction():
            store(conn, slug, content_id, scans)
        out += [{"book": slug, "content_id": content_id, **s} for s in summary(scans)]
    return out


def show(conn, book: str) -> list[dict]:
    """Every scan record of the book's current version, oldest first: the proposals a curator decides on."""
    [(slug, content_id)] = _current(conn, book)
    rows = conn.execute(
        "SELECT s.id, s.skill_path, s.status, s.tool_version, s.mode, s.input_digest, s.report_digest, "
        "s.recommendation, s.score, s.completeness, s.findings, s.reason, s.stale, s.scanned_at, "
        "EXISTS (SELECT 1 FROM skill_block b WHERE b.id = s.id), "
        "(SELECT jsonb_agg(jsonb_build_object('curator', k.curator, 'reason', k.reason, 'at', k.at) ORDER BY k.id) "
        "   FROM skill_clearance k WHERE k.book = s.book AND k.input_digest = s.input_digest "
        "    AND k.tool_version = s.tool_version AND k.report_digest IS NOT DISTINCT FROM s.report_digest) "
        "FROM skill_scan s WHERE s.book = %s AND s.content_id = %s ORDER BY s.id", (slug, content_id)).fetchall()
    return [{"id": r[0], "book": slug, "content_id": content_id, "skill_path": r[1], "status": r[2],
             "origin": "tool" if r[3] else None,
             "software_agent": {"name": TOOL, "version": r[3]} if r[3] else None, "mode": r[4],
             "input_digest": r[5], "report_digest": r[6], "recommendation": r[7], "score": r[8],
             "completeness": r[9], "findings": r[10], "reason": r[11], "stale": r[12],
             "scanned_at": r[13].isoformat(), "blocking": r[14], "cleared": r[15] or []} for r in rows]


def clear(conn, book: str, skill_path: str, *, curator: str, reason: str) -> dict:
    """The curator act that lifts the blocks on one skill of the book's current version. Needs the owner
    credential (the app role cannot write skill_clearance) and a curator who holds `curate` on the book now. The
    clearance covers exactly those bytes and that report: another version of the skill, or another tool version,
    is a new proposal."""
    if not isinstance(curator, str) or not authz.PRINCIPAL.match(curator) or not curator.startswith("user:"):
        raise ValueError("a curator is a user:")
    if not isinstance(reason, str) or not 1 <= len(reason) <= MAX_REASON:
        raise ValueError(f"reason must be 1..{MAX_REASON} characters")
    [(slug, content_id)] = _current(conn, book)
    with conn.transaction():
        if not authz.direct(conn, curator, f"book:{slug}", "curate").allowed:
            raise PermissionError(f"{curator} does not hold curate on book:{slug}")
        blocks = conn.execute("SELECT DISTINCT ON (input_digest, tool_version, report_digest) id, input_digest, "
                              "tool_version, report_digest, status, recommendation, completeness FROM skill_block "
                              "WHERE book = %s AND content_id = %s AND skill_path = %s "
                              "ORDER BY input_digest, tool_version, report_digest, id DESC",
                              (slug, content_id, skill_path)).fetchall()
        if not blocks:
            raise LookupError(f"no block on skill {skill_path!r} of {slug}@{content_id}")
        for scan_id, digest, version, report, *_ in blocks:
            conn.execute("INSERT INTO skill_clearance (book, input_digest, tool_version, report_digest, scan_id, "
                         "curator, reason) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                         (slug, digest, version, report, scan_id, curator, reason))
    return {"book": slug, "content_id": content_id, "skill_path": skill_path, "curator": curator,
            "cleared": [{"scan_id": b[0], "status": b[4], "recommendation": b[5], "completeness": b[6]}
                        for b in sorted(blocks, key=lambda b: b[0])]}
