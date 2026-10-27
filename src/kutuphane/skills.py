"""Skills over MCP (SEP-2640, #80): the skill folders of the current book versions, as the extension
`io.modelcontextprotocol/skills` serves them, for a principal who holds `activate` (K3, D37).

- A skill is a folder with a `SKILL.md` (agentfiles.skill_dirs) in a book's current content version, whose
  frontmatter has the Agent Skills `name` (1-64 of a-z, 0-9 and single hyphens) and `description` (1-1024
  characters), where `name` is the folder name (the book slug for a skill at the book root). A skill has at most
  512 files and 16 MiB. Other instruction files (AGENTS.md, rules, prompts) and skills that do not conform are not
  served here; `read_document` still reads them.
- URI: `skill://<book>/<folder>/<file>`, path segments percent-encoded. A URI names the file in the current
  version: after a new version, the same URI reads the new bytes, and a fresh entry has the new digests.
- Entry: `frontmatter` (the YAML as JSON; dates as ISO 8601 text) and `resources`: every file of the folder,
  nested skills included, with `digest` = `sha256:` + the file's SHA-256 from the content manifest (the bytes the
  content id covers) and `size`. `_meta` has the content id and the handling labels (handling.py).
- Gate, the same for `skills/list`, `skills/get` and `resources/read`: `read` and `activate` on the book for every
  principal (also people: a skill is for a model to load), `ai_input` that kstd allows for every file of the skill,
  and no file of the skill blocked by a scan (D71). The final rights and the blocks come from one statement. A
  refusal inside the fetch (`ai_input`, not found) is logged too (gate.guard). The events and labels name the
  content id of the version whose entry or bytes are served.
- No prefetch: `skills/list` and `skills/get` give entries only. The bytes of a file go out only on
  `resources/read`, one file for each request, through `gate.guard`. An active media type (HTML, JavaScript, SVG,
  XML) is sent as `text/plain` (`application/octet-stream` when not UTF-8); the bytes and the digest are unchanged.
- Cost: the validated frontmatter is stored at publication (`skill_frontmatter`, migration 033; a version published
  before it is indexed once, at its first skills call). A call reads that row and the manifest, never a SKILL.md
  blob; `skills/get` and `resources/read` take only the skills whose folder holds the requested path.
"""
import datetime
import math
import re
import urllib.parse
from dataclasses import dataclass
from itertools import groupby

from psycopg.types.json import Jsonb

from . import agentfiles, authz, gate, handling, kstd
from .gate import Actor
from .ids import normalize_path
from .source import SourceError, frontmatter

EXTENSION_ID = "io.modelcontextprotocol/skills"
SCHEME = "skill"
SKILL_MD = "SKILL.md"
MODES = ["read", "activate"]
MAX_FILES = 512
MAX_BYTES = 16 * 1024 * 1024
MAX_NAME, MAX_DESCRIPTION = 64, 1024
NAME = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
TEXT_TYPES = ("application/json", "application/yaml", "application/toml")
LIST_ACTION, GET_ACTION = "skills_list", "skills_get"
NO_AI_INPUT = "rights do not allow AI input"
ACTIVE_TYPES = ("text/html", "image/svg+xml", "application/xhtml+xml")  # with any *javascript*, *ecmascript*, *xml


def uri(book: str, path: str) -> str:
    return f"{SCHEME}://{book}/{urllib.parse.quote(path, safe='/')}"


def parse(value) -> tuple[str, str]:
    """A `skill://` URI -> (book, path in the book). Only the exact form that `uri()` writes is accepted."""
    parts = urllib.parse.urlsplit(value) if isinstance(value, str) else None
    if parts is None or parts.scheme != SCHEME or not authz.OBJECT.match(f"book:{parts.netloc}"):
        raise gate.NotFound("not a skill URI")
    try:
        path = normalize_path(urllib.parse.unquote(parts.path.removeprefix("/"), errors="strict"))
    except (ValueError, UnicodeDecodeError):
        raise gate.NotFound("not a skill URI") from None
    if uri(parts.netloc, path) != value:
        raise gate.NotFound("not a skill URI")
    return parts.netloc, path


def _json(value):
    """YAML frontmatter as JSON values, or ValueError (a key that is not text, NaN, a binary value)."""
    if isinstance(value, dict):
        if not all(isinstance(k, str) for k in value):
            raise ValueError("frontmatter key is not text")
        return {k: _json(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json(v) for v in value]
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("frontmatter number is not finite")
    if isinstance(value, (datetime.date, datetime.datetime)):
        return value.isoformat()
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise ValueError("frontmatter value has no JSON form")


@dataclass(frozen=True)
class Skill:
    book: str
    content_id: str
    folder: str           # the folder that holds SKILL.md; "." is the book root
    frontmatter: dict
    files: tuple          # the manifest entries (path, sha256, size, media_type, …) of every file in the folder

    @property
    def path(self) -> str:
        return SKILL_MD if self.folder == "." else f"{self.folder}/{SKILL_MD}"

    @property
    def uri(self) -> str:
        return uri(self.book, self.path)

    @property
    def depth(self) -> int:
        return 0 if self.folder == "." else self.folder.count("/") + 1

    def triples(self) -> list[tuple[str, str, str]]:
        return [(self.book, self.content_id, f["path"]) for f in self.files]

    def entry(self, labels: dict) -> dict:
        return {"uri": self.uri, "frontmatter": self.frontmatter,
                "resources": [{"uri": uri(self.book, f["path"]), "digest": f"sha256:{f['sha256']}", "size": f["size"]}
                              for f in self.files],
                "_meta": {"kutuphane/source": {"book": self.book, "content_id": self.content_id, "path": self.path},
                          handling.KEY: labels}}


def _conforming(book: str, folder: str, data: bytes | None) -> dict | None:
    """The frontmatter of a SKILL.md as JSON, when the skill conforms to SEP-2640; None otherwise."""
    try:
        meta = _json(frontmatter(data.decode("utf-8")))
    except (AttributeError, UnicodeDecodeError, SourceError, ValueError):  # AttributeError: no bytes
        return None
    if not meta:
        return None
    name, description = meta.get("name"), meta.get("description")
    expected = book if folder == "." else folder.rsplit("/", 1)[-1]
    if not (isinstance(name, str) and len(name) <= MAX_NAME and NAME.fullmatch(name) and name == expected):
        return None
    if not (isinstance(description, str) and 1 <= len(description) <= MAX_DESCRIPTION):
        return None
    return meta


def _md(folder: str) -> str:
    return SKILL_MD if folder == "." else f"{folder}/{SKILL_MD}"


def _index(book: str, paths, load) -> dict:
    """{folder: frontmatter} of the conforming skills of one content version. `load(path)`: the bytes of a file."""
    out = {}
    for folder in sorted(agentfiles.skill_dirs(paths)):
        if _md(folder) in paths and (meta := _conforming(book, folder, load(_md(folder)))) is not None:
            out[folder] = meta
    return out


def store(conn, book: str, content_id: str, files) -> None:
    """At publication (catalog.publish): store the validated frontmatter of the version's skills (migration 033),
    so a skills call never parses a SKILL.md blob."""
    data = {f.path: f.data for f in files}
    conn.execute("INSERT INTO skill_frontmatter (book, content_id, skills) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                 (book, content_id, Jsonb(_index(book, set(data), data.get))))


def _stored(conn, book: str, content_id: str, manifest: list[dict]) -> dict:
    """The stored frontmatter of a version published before migration 033: computed once, from its SKILL.md
    blobs only, then stored."""
    paths = {e["path"] for e in manifest}
    digests = {e["path"]: e["sha256"] for e in manifest if e["path"] in {_md(d) for d in agentfiles.skill_dirs(paths)}}
    blobs = dict(conn.execute("SELECT sha256, data FROM blob WHERE sha256 = ANY(%s)",
                              (sorted(set(digests.values())),)).fetchall()) if digests else {}
    index = _index(book, paths, lambda p: bytes(blobs[digests[p]]) if digests.get(p) in blobs else None)
    conn.execute("INSERT INTO skill_frontmatter (book, content_id, skills) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                 (book, content_id, Jsonb(index)))
    return index


def _skills(conn, books, path: str | None = None) -> list[Skill]:
    """The conforming skills of the current version of these books (no right is checked here); with `path`, only
    the skills whose folder holds it. The frontmatter comes from `skill_frontmatter` (review #18): no blob is read."""
    rows = conn.execute("SELECT b.slug, b.current_content, c.manifest, s.skills FROM book b "
                        "JOIN content_version c ON c.book = b.slug AND c.id = b.current_content "
                        "LEFT JOIN skill_frontmatter s ON s.book = b.slug AND s.content_id = b.current_content "
                        "WHERE b.slug = ANY(%s) ORDER BY b.slug", (sorted(set(books)),)).fetchall()
    out = []
    for book, content_id, manifest, stored in rows:
        if stored is None:
            stored = _stored(conn, book, content_id, manifest)
        for folder, meta in sorted(stored.items()):
            if path is not None and agentfiles.relative(folder, path) is None:
                continue
            files = tuple(e for e in manifest if agentfiles.relative(folder, e["path"]) is not None)
            if len(files) <= MAX_FILES and sum(f["size"] for f in files) <= MAX_BYTES:
                out.append(Skill(book, content_id, folder, meta, files))
    return out


def _ai_input(rights: kstd.Rights, skill: Skill) -> bool:
    return all(rights.allows(skill.book, skill.content_id, f["path"], "ai_input") for f in skill.files)


def _labels(per_book: dict, scans: list[dict], skill: Skill) -> dict:
    files = [f["path"] for f in skill.files]
    mine = [s for s in scans if s["book"] == skill.book and s["content_id"] == skill.content_id
            and any(agentfiles.relative(s["skill_path"], p) is not None for p in files)]
    return handling.build({skill.book: per_book[skill.book]} if skill.book in per_book else {}, mine)


def listing(conn, actor: Actor) -> list[dict]:
    """`skills/list`: the entries of every skill the caller may load now. A skill that a scan blocks is left out
    (one refused `activate` event for its SKILL.md); each book with skills in the list gets one `skills_list` and one
    `activate` event, with the skill URIs as items."""
    pre = authz.allowed(conn, actor.principal, actor.on_behalf_of, MODES)
    held = {o.removeprefix("book:") for o in pre.objects("read") & pre.objects("activate")}
    rights = kstd.Rights(conn)
    candidates = [s for s in _skills(conn, held) if _ai_input(rights, s)]
    final = authz.allowed(conn, actor.principal, actor.on_behalf_of, MODES,
                          skills=[t for s in candidates for t in s.triples()])
    held = final.objects("read") & final.objects("activate")
    served, blocked = [], []
    for s in candidates:
        if f"book:{s.book}" in held:
            (blocked if any(t in final.blocked_files for t in s.triples()) else served).append(s)
    gate.log_blocked(conn, actor, [(s.book, s.content_id, s.path) for s in blocked], final.policies)
    for book, group in groupby(served, key=lambda s: s.book):
        obj, uris = f"book:{book}", [s.uri for s in group]
        for mode in MODES:
            gate.log_event(conn, actor, LIST_ACTION if mode == "read" else mode, obj, mode, final.decisions[obj][mode],
                           final.policies.get(obj), None, None, items=uris)
    per_book = handling.policies(conn, {s.book for s in served})
    scans = handling.scans(conn, [t for s in served for t in s.triples()])
    return [s.entry(_labels(per_book, scans, s)) for s in served]


def get(conn, actor: Actor, value) -> dict:
    """`skills/get`: the entry of one skill by the URI of its SKILL.md, through the gate (`skills_get` and
    `activate` events, with the content id of the version served)."""
    book, path = parse(value)
    if path.rsplit("/", 1)[-1] != SKILL_MD:
        raise gate.NotFound("not the URI of a SKILL.md")

    def fetch() -> Skill:
        skill = next((s for s in _skills(conn, [book], path) if s.path == path), None)
        if skill is None:
            raise gate.NotFound(value)
        if not _ai_input(kstd.Rights(conn), skill):
            raise gate.Denied(f"{value}: {NO_AI_INPUT}")
        return skill
    skill = gate.guard(conn, actor, f"book:{book}", MODES, fetch, action=GET_ACTION, path=path,
                       items=[uri(book, path)], blocks_of=Skill.triples, content_of=lambda s: s.content_id)
    return skill.entry(handling.labels(conn, [book], skill.triples()))


def read(conn, actor: Actor, value) -> tuple[bytes, str, dict]:
    """`resources/read` of a `skill://` file: (bytes, media type, handling labels). The file must be inside a
    conforming skill; the innermost one decides `ai_input` and the block, for every file it holds. The events and
    the labels name the content version whose bytes are served (review #18). An active media type is served as
    `served_type` says."""
    book, path = parse(value)

    def fetch() -> tuple[Skill, bytes]:
        mine = [s for s in _skills(conn, [book], path) if any(f["path"] == path for f in s.files)]
        if not mine:
            raise gate.NotFound(value)
        skill = max(mine, key=lambda s: s.depth)
        if not _ai_input(kstd.Rights(conn), skill):
            raise gate.Denied(f"{value}: {NO_AI_INPUT}")
        return skill, bytes(conn.execute("SELECT data FROM blob WHERE sha256 = %s",
                                         (next(f for f in skill.files if f["path"] == path)["sha256"],)).fetchone()[0])
    skill, data = gate.guard(conn, actor, f"book:{book}", MODES, fetch, action="read", path=path,
                             blocks_of=lambda found: found[0].triples(), content_of=lambda found: found[0].content_id)
    media_type = next(f["media_type"] for f in skill.files if f["path"] == path)
    return data, served_type(media_type, data), handling.labels(conn, [book], [(book, skill.content_id, path)])


def served_type(media_type: str, data: bytes) -> str:
    """The media type a `skill://` read is sent with (review #18): an active type (HTML, JavaScript, SVG, XML) goes
    out as `text/plain`, or `application/octet-stream` when it is not UTF-8, so no host renders or runs it. The
    bytes, and so the digest, stay the same."""
    folded = media_type.lower()
    if not (folded in ACTIVE_TYPES or "javascript" in folded or "ecmascript" in folded or folded.endswith("xml")):
        return media_type
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        return "application/octet-stream"
    return "text/plain"


def is_text(media_type: str) -> bool:
    return media_type.startswith("text/") or media_type in TEXT_TYPES
