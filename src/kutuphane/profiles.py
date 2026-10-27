"""Presentation profiles (D26): how one content version is cut into what gets served and searched.

`whole` serves each file as one piece; `chunked` cuts at headings and blank lines into ~TARGET_CHARS pieces. Both
are deterministic: same bytes + same profile → same chunks and offsets. A profile's id covers every component
version and setting, so changing the cutter or the search configuration is a new profile, never a silent change.

Searched formats (G1): markdown, PDF text layers, and the plain-text formats of source.TEXT_TYPES. Markdown cuts at
headings; other text at blank lines; CSV at rows (merged); JSONL gives one passage per record, and every passage of
a text file carries the line it starts on (for JSONL: the record's line). HTML is searched by its visible text
only: no scripts, styles, templates or comments. Quarantined files (source.py) are stored but never cut.

Markdown (G27, G28): a heading is an ATX heading line (`#` to `######` and a space) outside a code fence, so
`#41` and a shell comment in a fence are text. A cut that holds only headings, thematic breaks (`---`) or HTML
comments (a leading source comment) is not a passage: it joins the passage after it (at the end of the file, the
passage before it). Every other passage keeps exactly the text that the cut without this step gives, so its
embedded text, and so its vector (vectors.py), stays the same.
"""
import io
import re
from bisect import bisect_right
from dataclasses import dataclass
from importlib.metadata import version

from pypdf import PdfReader

from .agentfiles import is_instruction
from .source import CSV, HTML, JSONL, MARKDOWN, PDF, TEXT_TYPES, SourceFile, extracted_text

READER_VERSION = 3  # 3: G1 text formats, G3 quarantine, G5 agent folders. Bump when source.py's classification changes.
CHUNKER_VERSION = 5  # 5: a heading, `---` or comment alone joins the next passage; ATX headings outside fences only
TARGET_CHARS = 1200
FTS_CONFIG = "turkish"  # Postgres text search configuration; part of the profile id
MAX_CHUNK_CHARS = 4 * TARGET_CHARS  # a single huge block is cut at whitespace, so nothing escapes the index
WHOLE_MAX_CHARS = 500_000  # tsvector holds at most 1 MB; larger files must use the chunked profile
_TEXT = frozenset(TEXT_TYPES.values())


def _components(chunker: str) -> dict:
    return {"reader": f"kutuphane.source@{READER_VERSION}", "pdf": f"pypdf@{version('pypdf')}",
            "chunker": f"{chunker}@{CHUNKER_VERSION}"}


CANONICAL = ("whole", "chunked")
JOURNAL = "journal"  # the profile of a journal's notes (docs/24 §3): no cutting; one note is one block
NOTE_MAX_CHARS = 8000


def spec(name: str) -> dict:
    if name == "whole":
        return {"name": "whole", "components": _components("whole"), "settings": {"fts": FTS_CONFIG}}
    if name == "chunked":
        return {"name": "chunked", "components": _components("paragraph"),
                "settings": {"fts": FTS_CONFIG, "target_chars": TARGET_CHARS}}
    if name == JOURNAL:  # the id covers the normalizer of norm_sha256 and the FTS configuration of tsv (D26)
        return {"name": JOURNAL, "components": {"notes": "kutuphane.notes@1", "normalizer": "nfc-casefold-ws@1"},
                "settings": {"fts": FTS_CONFIG, "max_chars": NOTE_MAX_CHARS}}
    raise ValueError(f"unknown profile {name!r} (whole, chunked, journal)")


@dataclass(frozen=True)
class Chunk:
    path: str
    ordinal: int
    page: int | None
    start: int
    end: int
    text: str
    instruction: bool
    line: int | None = None  # text files: 1-based line the passage starts on (JSONL: the record's line)


def _pages(f: SourceFile) -> list[tuple[int | None, str]]:
    if f.quarantine:
        return []
    if f.media_type == PDF:
        return [(n, page.extract_text() or "") for n, page in enumerate(PdfReader(io.BytesIO(f.data)).pages, 1)]
    if f.media_type in _TEXT:
        return [(None, extracted_text(f.media_type, f.data.decode("utf-8")))]  # the text source.py scanned
    return []  # other assets are stored and citable as files, not searched


def _frontmatter_end(text: str) -> int:
    if not text.startswith("---\n"):
        return 0
    end = text.find("\n---", 4)
    if end < 0:
        return 0
    close = text.find("\n", end + 4)
    return len(text) if close < 0 else close + 1


def _lines(text: str):
    """(offset, line) with its line end. A line ends only at "\\n" (text is normalized, so "\\r\\n" is one end too),
    never at the other characters str.splitlines() breaks on: U+2028 or U+0085 inside a JSON string is content.
    Citation line numbers (split's `line_of`) count the same "\\n"."""
    for m in re.finditer(r"[^\n]*\n|[^\n]+\Z", text):
        yield m.start(), m.group()


_HEADING = re.compile(r" {0,3}#{1,6}(?:[ \t]|$)")                  # CommonMark ATX heading
_FENCE = re.compile(r" {0,3}(`{3,}|~{3,})")
_BREAK = re.compile(r" {0,3}([-*_])(?:[ \t]*\1){2,}[ \t]*$")        # a thematic break: ---, ***, ___
_COMMENTS = re.compile(r"(?:\s*<!--.*?-->)+\s*", re.DOTALL)


def _paragraph_spans(text: str, base: int, headings: bool) -> list[tuple[int, int, bool, bool]]:
    """Blank-line separated blocks as (start, end, heading, bare); with `headings` (markdown), a heading line always
    starts a new block. `heading`: the block starts with a heading. `bare`: markdown, and the block holds only
    headings and thematic breaks, or only HTML comments."""
    spans, start, end, fence, marks = [], None, 0, None, True

    def close(stop: int) -> None:
        bare = headings and (marks or _COMMENTS.fullmatch(text, start, stop) is not None)
        spans.append((base + start, base + stop, headings and heading_start, bare))

    heading_start = False
    for i, line in _lines(text):
        body = line.rstrip("\n")
        opener = _FENCE.match(body) if headings else None
        heading = headings and fence is None and _HEADING.match(body) is not None
        blank = not line.strip()
        if (blank or heading) and start is not None:
            close(i)
            start = None
        if not blank and start is None:
            start, heading_start, marks = i, heading, True
        if not blank:
            marks = marks and fence is None and opener is None and (heading or _BREAK.match(body) is not None)
        if opener and (fence is None or opener.group(1)[0] == fence[0] and len(opener.group(1)) >= len(fence)):
            fence = None if fence else opener.group(1)
        end = i + len(line)
    if start is not None:
        close(end)
    return spans


def _line_spans(text: str, base: int) -> list[tuple[int, int, bool, bool]]:
    """One span per non-blank line (a CSV row, a JSONL record), line end included."""
    return [(base + i, base + i + len(line), False, False) for i, line in _lines(text) if line.strip()]


def _cap(spans: list[tuple[int, int, bool, bool]], text: str) -> list[tuple[int, int, bool, bool]]:
    """Cut blocks longer than MAX_CHUNK_CHARS: at the last line end in the second half of the window, else at the
    last space, else hard."""
    out = []
    for s, e, heading, bare in spans:
        while e - s > MAX_CHUNK_CHARS:
            cut = text.rfind("\n", s + MAX_CHUNK_CHARS // 2, s + MAX_CHUNK_CHARS)
            if cut < 0:
                cut = text.rfind(" ", s + 1, s + MAX_CHUNK_CHARS)
            cut = cut + 1 if cut > s else s + MAX_CHUNK_CHARS
            out.append((s, cut, heading, False))
            s, heading = cut, False
        out.append((s, e, heading, bare))
    return out


def _merge(spans: list[tuple[int, int, bool, bool]]) -> list[tuple[int, int, bool]]:
    """Greedy: join consecutive blocks up to TARGET_CHARS; a heading block starts a new chunk. (start, end, bare):
    a chunk is bare when all its blocks are."""
    out = []
    for s, e, heading, bare in spans:
        if out and not heading and e - out[-1][0] <= TARGET_CHARS:
            out[-1] = (out[-1][0], e, out[-1][2] and bare)
        else:
            out.append((s, e, bare))
    return out


def _attach_bare(merged: list[tuple[int, int, bool]]) -> list[tuple[int, int]]:
    """G27, G28: a bare chunk joins the next chunk (at the end, the one before it); no other chunk changes."""
    out, pending = [], None
    for s, e, bare in merged:
        start = s if pending is None else pending
        if bare:
            pending = start
            continue
        out.append((start, e))
        pending = None
    if pending is not None:
        end = merged[-1][1]
        out[-1:] = [(out[-1][0], end)] if out else [(pending, end)]
    return out


def _cut(f: SourceFile, text: str, base: int, full: str) -> list[tuple[int, int]]:
    """Spans of one page `text` that starts at `base` in `full` (the file's extracted text)."""
    if f.media_type == JSONL:
        return [(s, e) for s, e, _h, _b in _cap(_line_spans(text, base), full)]  # one record, one passage
    if f.media_type == CSV:
        return _attach_bare(_merge(_cap(_line_spans(text, base), full)))
    markdown = f.media_type == MARKDOWN
    skip = _frontmatter_end(text) if markdown else 0  # metadata, not passage text
    return _attach_bare(_merge(_cap(_paragraph_spans(text[skip:], base + skip, markdown), full)))


def split(profile: dict, f: SourceFile, skills: frozenset[str] = frozenset()) -> list[Chunk]:
    """`skills`: agentfiles.skill_dirs() of the whole content version, so skill folders mark their files."""
    instruction = is_instruction({"path": f.path, "okf_type": f.okf_type}, skills)
    pages = _pages(f)
    if not pages:
        return []
    full = "".join(t for _, t in pages)
    lines = [m.start() for m in re.finditer("\n", full)] if f.media_type in _TEXT - {HTML} else None

    def line_of(start: int) -> int | None:
        return None if lines is None else bisect_right(lines, start - 1) + 1

    if profile["name"] == "whole":
        if len(full) > WHOLE_MAX_CHARS:
            raise ValueError(f"{f.path}: {len(full)} characters is too long for the whole profile; use chunked")
        return [Chunk(f.path, 0, pages[0][0], 0, len(full), full, instruction, line_of(0))] if full.strip() else []
    chunks, offset = [], 0
    for page, text in pages:
        for s, e in _cut(f, text, offset, full):
            chunks.append(Chunk(f.path, len(chunks), page, s, e, full[s:e], instruction, line_of(s)))
        offset += len(text)
    return chunks


def check_profile(profile) -> dict:
    """M1 accepts only the canonical profiles, so a profile id always describes what the code actually does."""
    name = profile.get("name") if isinstance(profile, dict) else None
    if name not in CANONICAL or profile != spec(name):
        raise ValueError(f"unsupported profile; use one of {', '.join(CANONICAL)} as defined by profiles.spec")
    return profile
