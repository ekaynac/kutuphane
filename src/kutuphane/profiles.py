"""Presentation profiles (D26): how one content version is cut into what gets served and searched.

`whole` serves each file as one piece; `chunked` cuts at headings and blank lines into ~TARGET_CHARS pieces. Both
are deterministic: same bytes + same profile → same chunks and offsets. A profile's id covers every component
version and setting, so changing the cutter or the search configuration is a new profile, never a silent change.
"""
import io
from dataclasses import dataclass
from importlib.metadata import version
from pathlib import PurePosixPath

from pypdf import PdfReader

from .source import MARKDOWN, PDF, SourceFile

READER_VERSION = 2  # 2: CRLF/BOM-tolerant frontmatter. Bump when source.py's classification changes.
CHUNKER_VERSION = 1
TARGET_CHARS = 1200
FTS_CONFIG = "turkish"  # Postgres text search configuration; part of the profile id
TSV_MAX_CHARS = 500_000  # tsvector is limited to 1 MB per value

# Frontmatter `type`s and file names that mark an agent instruction (K3), compared case- and separator-
# insensitively so `Skill`, `agent_card` or `agents.md` cannot slip past the activation gate. K3 status is
# curator-declared metadata; content that hides instructions under another type is caught (if at all) by the
# import scan (D29, M1f), not here.
INSTRUCTION_TYPES = frozenset({"skill", "prompt", "agentcard", "agentinstructions", "systemprompt"})
INSTRUCTION_FILES = frozenset({"agents.md", "claude.md", "skill.md", "gemini.md"})


def _fold(value: str) -> str:
    return "".join(ch for ch in value.casefold() if ch.isalnum())


def is_instruction(entry: dict) -> bool:
    okf_type = entry.get("okf_type") or ""
    name = PurePosixPath(entry["path"]).name.casefold()
    return _fold(okf_type) in INSTRUCTION_TYPES or name in INSTRUCTION_FILES


def _components(chunker: str) -> dict:
    return {"reader": f"kutuphane.source@{READER_VERSION}", "pdf": f"pypdf@{version('pypdf')}",
            "chunker": f"{chunker}@{CHUNKER_VERSION}"}


def spec(name: str) -> dict:
    if name == "whole":
        return {"name": "whole", "components": _components("whole"), "settings": {"fts": FTS_CONFIG}}
    if name == "chunked":
        return {"name": "chunked", "components": _components("paragraph"),
                "settings": {"fts": FTS_CONFIG, "target_chars": TARGET_CHARS}}
    raise ValueError(f"unknown profile {name!r} (whole, chunked)")


@dataclass(frozen=True)
class Chunk:
    path: str
    ordinal: int
    page: int | None
    start: int
    end: int
    text: str
    instruction: bool


def _pages(f: SourceFile) -> list[tuple[int | None, str]]:
    if f.media_type == MARKDOWN:
        return [(None, f.data.decode("utf-8").removeprefix("﻿").replace("\r\n", "\n").replace("\r", "\n"))]
    if f.media_type == PDF:
        return [(n, page.extract_text() or "") for n, page in enumerate(PdfReader(io.BytesIO(f.data)).pages, 1)]
    return []  # other assets are stored and citable as files, not searched


def _frontmatter_end(text: str) -> int:
    if not text.startswith("---\n"):
        return 0
    end = text.find("\n---", 4)
    if end < 0:
        return 0
    close = text.find("\n", end + 4)
    return len(text) if close < 0 else close + 1


def _paragraph_spans(text: str, base: int) -> list[tuple[int, int]]:
    """Blank-line separated blocks; a markdown heading always starts a new block."""
    spans, start, i = [], None, 0
    for line in text.splitlines(keepends=True):
        blank, heading = not line.strip(), line.lstrip().startswith("#")
        if (blank or heading) and start is not None:
            spans.append((start, i))
            start = None
        if not blank and start is None:
            start = i
        i += len(line)
    if start is not None:
        spans.append((start, i))
    return [(base + s, base + e) for s, e in spans]


def _merge(spans: list[tuple[int, int]], text: str) -> list[tuple[int, int]]:
    """Greedy: join consecutive blocks up to TARGET_CHARS; a heading block starts a new chunk."""
    out = []
    for s, e in spans:
        heading = text[s:e].lstrip().startswith("#")
        if out and not heading and e - out[-1][0] <= TARGET_CHARS:
            out[-1] = (out[-1][0], e)
        else:
            out.append((s, e))
    return out


def split(profile: dict, f: SourceFile) -> list[Chunk]:
    instruction = is_instruction({"path": f.path, "okf_type": f.okf_type})
    pages = _pages(f)
    if not pages:
        return []
    full = "".join(t for _, t in pages)
    if profile["name"] == "whole":
        return [Chunk(f.path, 0, pages[0][0], 0, len(full), full, instruction)] if full.strip() else []
    chunks, offset = [], 0
    for page, text in pages:
        skip = _frontmatter_end(text) if f.media_type == MARKDOWN else 0  # metadata, not passage text
        for s, e in _merge(_paragraph_spans(text[skip:], offset + skip), full):
            chunks.append(Chunk(f.path, len(chunks), page, s, e, full[s:e], instruction))
        offset += len(text)
    return chunks
