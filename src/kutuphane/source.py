"""Read and validate an ingest source: an OKF/markdown bundle directory or a single file.

Minimally opinionated (D21): every file's bytes are kept as-is, so unknown frontmatter keys survive. Markdown
frontmatter, when present, must be a YAML mapping; its `type` is recorded. PDFs must carry a text layer
(M1 has no OCR).
"""
import io
import mimetypes
from dataclasses import dataclass
from pathlib import Path

import yaml
from pypdf import PdfReader
from pypdf.errors import PdfReadError

from .ids import normalize_path, sha256_hex

MAX_FILE_BYTES = 50 * 1024 * 1024
MAX_SOURCE_BYTES = 200 * 1024 * 1024
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


def frontmatter(text: str) -> dict | None:
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---", 4)
    if end < 0:
        raise SourceError("frontmatter is not closed")
    try:
        meta = yaml.safe_load(text[4:end])
    except yaml.YAMLError as exc:
        raise SourceError(f"frontmatter is not valid YAML: {exc}") from None
    if meta is None:
        return {}
    if not isinstance(meta, dict):
        raise SourceError("frontmatter must be a mapping")
    return meta


def check_pdf(data: bytes) -> None:
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise SourceError("encrypted PDFs are not supported")
        has_text = any((page.extract_text() or "").strip() for page in reader.pages)
    except PdfReadError as exc:
        raise SourceError(f"unreadable PDF: {exc}") from None
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
            meta = frontmatter(data.decode("utf-8"))
            okf_type = str(meta["type"]) if meta and "type" in meta else None
        elif media_type == PDF:
            check_pdf(data)
    except UnicodeDecodeError:
        raise SourceError(f"{path}: markdown is not UTF-8") from None
    except SourceError as exc:
        raise SourceError(f"{path}: {exc}") from None
    return SourceFile(path, data, sha256_hex(data), media_type, okf_type)


def read_source(root: Path) -> list[SourceFile]:
    """Directory: every regular, non-hidden file below it. File: just that file."""
    if root.is_symlink():
        raise SourceError(f"{root}: symlinks are not followed")
    if root.is_file():
        entries = [(root.name, root)]
    elif root.is_dir():
        entries = []
        for p in sorted(root.rglob("*")):
            rel = p.relative_to(root)
            if any(part.startswith(".") for part in rel.parts):
                continue
            if p.is_symlink():
                raise SourceError(f"{rel}: symlinks are not followed")
            if p.is_file():
                entries.append((rel.as_posix(), p))
    else:
        raise SourceError(f"{root}: not found")
    if not entries:
        raise SourceError(f"{root}: no files")
    total = sum(p.stat().st_size for _, p in entries)
    if total > MAX_SOURCE_BYTES:
        raise SourceError(f"{root}: larger than {MAX_SOURCE_BYTES} bytes")
    return [read_file(rel, p.read_bytes()) for rel, p in entries]
