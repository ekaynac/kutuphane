"""Read and validate an ingest source: an OKF/markdown bundle directory or a single file.

Minimally opinionated (D21): every file's bytes are kept as-is, so unknown frontmatter keys survive. Markdown
frontmatter, when present, must be a YAML mapping; its `type` is recorded. PDFs must carry a text layer
(M1 has no OCR). Input is untrusted: symlinks are never followed, sizes are bounded, YAML aliases are refused.
"""
import errno
import io
import mimetypes
import os
import stat
from dataclasses import dataclass
from pathlib import Path

import yaml
from pypdf import PdfReader

from .ids import normalize_path, sha256_hex

MAX_FILE_BYTES = 50 * 1024 * 1024
MAX_SOURCE_BYTES = 200 * 1024 * 1024
MAX_FRONTMATTER_CHARS = 64 * 1024
MAX_TYPE_CHARS = 200
MAX_PDF_PAGES = 5000
MARKDOWN = "text/markdown"
PDF = "application/pdf"


class SourceError(ValueError):
    pass


@dataclass(frozen=True)
class SourceFile:
    path: str
    data: bytes
    sha256: str
    media_type: str
    okf_type: str | None


def media_type_of(path: str) -> str:
    if path.lower().endswith((".md", ".markdown")):
        return MARKDOWN
    return mimetypes.guess_type(path)[0] or "application/octet-stream"


class _NoAliasLoader(yaml.SafeLoader):
    """Frontmatter never needs anchors/aliases, and they allow expansion bombs."""

    def compose_node(self, parent, index):
        if self.check_event(yaml.AliasEvent):
            raise yaml.YAMLError("YAML aliases are not allowed in frontmatter")
        return super().compose_node(parent, index)


def frontmatter(text: str) -> dict | None:
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---", 4)
    if end < 0:
        raise SourceError("frontmatter is not closed")
    if end > MAX_FRONTMATTER_CHARS:
        raise SourceError(f"frontmatter longer than {MAX_FRONTMATTER_CHARS} characters")
    try:
        meta = yaml.load(text[4:end], Loader=_NoAliasLoader)  # SafeLoader subclass
    except yaml.YAMLError as exc:
        raise SourceError(f"frontmatter is not valid YAML: {exc}") from None
    if meta is None:
        return {}
    if not isinstance(meta, dict):
        raise SourceError("frontmatter must be a mapping")
    return meta


def okf_type_of(meta: dict | None) -> str | None:
    if not meta or "type" not in meta:
        return None
    value = meta["type"]
    if not isinstance(value, str) or not value or len(value) > MAX_TYPE_CHARS:
        raise SourceError(f"`type` must be a non-empty string of at most {MAX_TYPE_CHARS} characters")
    return value


def check_pdf(data: bytes) -> None:
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise SourceError("encrypted PDFs are not supported")
        if len(reader.pages) > MAX_PDF_PAGES:
            raise SourceError(f"more than {MAX_PDF_PAGES} pages")
        has_text = any((page.extract_text() or "").strip() for page in reader.pages)
    except SourceError:
        raise
    except Exception as exc:  # pypdf raises many types on malformed input; all mean "unreadable"
        raise SourceError(f"unreadable PDF ({type(exc).__name__}: {exc})") from None
    if not has_text:
        raise SourceError("PDF has no text layer (OCR is out of M1 scope)")


def read_file(rel: str, data: bytes) -> SourceFile:
    path = normalize_path(rel)
    if len(data) > MAX_FILE_BYTES:
        raise SourceError(f"{path}: larger than {MAX_FILE_BYTES} bytes")
    media_type = media_type_of(path)
    okf_type = None
    try:
        if media_type == MARKDOWN:
            okf_type = okf_type_of(frontmatter(data.decode("utf-8")))
        elif media_type == PDF:
            check_pdf(data)
    except UnicodeDecodeError:
        raise SourceError(f"{path}: markdown is not UTF-8") from None
    except SourceError as exc:
        raise SourceError(f"{path}: {exc}") from None
    return SourceFile(path, data, sha256_hex(data), media_type, okf_type)


def _read_regular(path: Path, shown: str) -> bytes:
    """Open without following symlinks, then check the opened file itself (no check-then-read race)."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            raise SourceError(f"{shown}: symlinks are not followed") from None
        raise SourceError(f"{shown}: cannot open ({exc.strerror})") from None
    with os.fdopen(fd, "rb") as f:
        if not stat.S_ISREG(os.fstat(f.fileno()).st_mode):
            raise SourceError(f"{shown}: not a regular file")
        data = f.read(MAX_FILE_BYTES + 1)
    if len(data) > MAX_FILE_BYTES:
        raise SourceError(f"{shown}: larger than {MAX_FILE_BYTES} bytes")
    return data


def _entries(root: Path) -> list[tuple[str, Path]]:
    try:
        mode = os.lstat(root).st_mode
    except FileNotFoundError:
        raise SourceError(f"{root}: not found") from None
    if stat.S_ISLNK(mode):
        raise SourceError(f"{root}: symlinks are not followed")
    if stat.S_ISREG(mode):
        return [(root.name, root)]
    if not stat.S_ISDIR(mode):
        raise SourceError(f"{root}: not a file or directory")
    entries = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        here = Path(dirpath)
        for d in [d for d in dirnames if not d.startswith(".") and (here / d).is_symlink()]:
            raise SourceError(f"{(here / d).relative_to(root)}: symlinks are not followed")
        dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
        entries += [((here / f).relative_to(root).as_posix(), here / f)
                    for f in sorted(filenames) if not f.startswith(".")]
    return entries


def read_source(root: Path) -> list[SourceFile]:
    """Directory: every non-hidden regular file below it. File: just that file."""
    entries = _entries(root)
    if not entries:
        raise SourceError(f"{root}: no files")
    files, seen, total = [], set(), 0
    for rel, p in entries:
        sf = read_file(rel, _read_regular(p, rel))
        if sf.path in seen:  # e.g. NFC and NFD spellings of one name
            raise SourceError(f"{sf.path}: two files normalize to the same path")
        seen.add(sf.path)
        total += len(sf.data)
        if total > MAX_SOURCE_BYTES:
            raise SourceError(f"{root}: larger than {MAX_SOURCE_BYTES} bytes")
        files.append(sf)
    return files
