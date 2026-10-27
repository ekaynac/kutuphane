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
  and no file of the skill blocked by a scan (D71). The final rights and the blocks come from one statement.
- No prefetch: `skills/list` and `skills/get` give entries only. The bytes of a file go out only on
  `resources/read`, one file for each request, through `gate.guard`.
"""
import datetime
import math
import re
import urllib.parse
from dataclasses import dataclass
from itertools import groupby

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


def _skills(conn, books) -> list[Skill]:
    """The conforming skills of the current version of these books (no right is checked here)."""
    rows = conn.execute("SELECT b.slug, b.current_content, c.manifest FROM book b "
                        "JOIN content_version c ON c.book = b.slug AND c.id = b.current_content "
                        "WHERE b.slug = ANY(%s) ORDER BY b.slug", (sorted(set(books)),)).fetchall()
    found = []
    for book, content_id, manifest in rows:
        paths = {e["path"] for e in manifest}
        for folder in sorted(agentfiles.skill_dirs(paths)):
            files = tuple(e for e in manifest if agentfiles.relative(folder, e["path"]) is not None)
            md = SKILL_MD if folder == "." else f"{folder}/{SKILL_MD}"
            if md in paths and len(files) <= MAX_FILES and sum(f["size"] for f in files) <= MAX_BYTES:
                found.append((book, content_id, folder, files, next(f for f in files if f["path"] == md)["sha256"]))
    blobs = dict(conn.execute("SELECT sha256, data FROM blob WHERE sha256 = ANY(%s)",
                              (sorted({f[4] for f in found}),)).fetchall()) if found else {}
    out = []
    for book, content_id, folder, files, digest in found:
        meta = _conforming(book, folder, bytes(blobs[digest]) if digest in blobs else None)
        if meta is not None:
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


def _current(conn, book: str) -> str | None:
    row = conn.execute("SELECT current_content FROM book WHERE slug = %s", (book,)).fetchone()
    return row[0] if row else None


def get(conn, actor: Actor, value) -> dict:
    """`skills/get`: the entry of one skill by the URI of its SKILL.md, through the gate (`skills_get` and
    `activate` events)."""
    book, path = parse(value)
    if path.rsplit("/", 1)[-1] != SKILL_MD:
        raise gate.NotFound("not the URI of a SKILL.md")
    content_id = _current(conn, book)

    def fetch() -> Skill:
        skill = next((s for s in _skills(conn, [book]) if s.path == path), None)
        if skill is None:
            raise gate.NotFound(value)
        if not _ai_input(kstd.Rights(conn), skill):
            raise gate.Denied(f"{value}: {NO_AI_INPUT}")
        return skill
    skill = gate.guard(conn, actor, f"book:{book}", MODES, fetch, action=GET_ACTION, content_id=content_id, path=path,
                       items=[uri(book, path)], blocks_of=Skill.triples)
    return skill.entry(handling.labels(conn, [book], skill.triples()))


def read(conn, actor: Actor, value) -> tuple[bytes, str, dict]:
    """`resources/read` of a `skill://` file: (bytes, media type, handling labels). The file must be inside a
    conforming skill; the innermost one decides `ai_input` and the block, for every file it holds."""
    book, path = parse(value)
    content_id = _current(conn, book)

    def fetch() -> tuple[Skill, bytes]:
        mine = [s for s in _skills(conn, [book]) if any(f["path"] == path for f in s.files)]
        if not mine:
            raise gate.NotFound(value)
        skill = max(mine, key=lambda s: s.depth)
        if not _ai_input(kstd.Rights(conn), skill):
            raise gate.Denied(f"{value}: {NO_AI_INPUT}")
        return skill, bytes(conn.execute("SELECT data FROM blob WHERE sha256 = %s",
                                         (next(f for f in skill.files if f["path"] == path)["sha256"],)).fetchone()[0])
    skill, data = gate.guard(conn, actor, f"book:{book}", MODES, fetch, action="read", content_id=content_id,
                             path=path, blocks_of=lambda found: found[0].triples())
    media_type = next(f["media_type"] for f in skill.files if f["path"] == path)
    return data, media_type, handling.labels(conn, [book], [(book, content_id, path)])


def is_text(media_type: str) -> bool:
    return media_type.startswith("text/") or media_type in TEXT_TYPES
