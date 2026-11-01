"""Read and validate an ingest source: an OKF/markdown bundle directory or a single file.

Minimally opinionated (D21): every file's bytes are kept as-is, so unknown frontmatter keys survive. Markdown
frontmatter, when present, must be a YAML mapping; its `type` is recorded. Input is untrusted: symlinks are never
followed, sizes are bounded, YAML aliases are refused, hidden paths stay out (except the agent folders of
agentfiles.py), and a credential-like file name or credential-like text refuses the whole source (secretscan.py).
Both the original text and the extracted text that gets cut into passages (`extracted_text`: HTML's visible text
with entities decoded, a PDF's text layer) are scanned.

The one exception is narrow and on record: `--accept-finding <path>@sha256:<file digest>:<rule>` accepts one rule's
findings in exactly that file content (AcceptedFinding). A changed file has another digest, so the acceptance no
longer applies; an acceptance that matches no finding refuses the source. Publication records what was accepted.

Personal-data and fleet-data findings (datascan.py, G35) never refuse a source: each file carries its open ones
(`data_findings`, the ones that no acceptance covers), and catalog.py records and gates them. `kstd.yaml` is
metadata and is not scanned for them (it names its issuer).

A file that is safe but cannot be extracted (a PDF without a text layer, an unreadable or encrypted PDF, a text
file that is not UTF-8 or holds NUL bytes) is not refused: it is stored and listed, and `quarantine` says why it
is not indexed (G3). Its quarantine ends with the version that fixes it.
"""
import errno
import io
import mimetypes
import os
import re
import stat
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath

import yaml
from pypdf import PdfReader

from . import agentfiles, datascan, secretscan
from .ids import CONTROL, normalize_path, sha256_hex
from .kstd import MANIFEST

MAX_FILE_BYTES = 50 * 1024 * 1024
MAX_SOURCE_BYTES = 200 * 1024 * 1024
MAX_FRONTMATTER_CHARS = 64 * 1024
MAX_TYPE_CHARS = 200
MAX_PDF_PAGES = 5000
MARKDOWN = "text/markdown"
PDF = "application/pdf"
HTML = "text/html"
JSONL = "application/jsonl"
CSV = "text/csv"
# Text formats that are searched (G1), by suffix. A file is text only if it decodes as UTF-8 and has no NUL.
TEXT_TYPES = {
    ".md": MARKDOWN, ".markdown": MARKDOWN,
    ".txt": "text/plain", ".mdc": "text/plain",
    ".json": "application/json", ".jsonl": JSONL, ".ndjson": JSONL,
    ".yaml": "application/yaml", ".yml": "application/yaml", ".toml": "application/toml",
    ".sh": "text/x-sh", ".py": "text/x-python", ".js": "text/javascript", ".ts": "text/x-typescript",
    ".html": HTML, ".htm": HTML, ".xml": "application/xml", ".csv": CSV,
}


class SourceError(ValueError):
    pass


@dataclass(frozen=True)
class SourceFile:
    path: str
    data: bytes
    sha256: str
    media_type: str
    okf_type: str | None
    quarantine: str | None = None  # why a searchable file cannot be indexed; None: indexed normally
    accepted: tuple[str, ...] = ()  # secretscan/datascan rules whose findings in these exact bytes an operator accepted
    data_findings: tuple = ()  # ((where, secretscan.Finding), …): open datascan findings; where: "" or " of the …"


@dataclass(frozen=True, order=True)
class AcceptedFinding:
    """`<path>@sha256:<file digest>:<rule>`: one rule's findings in one exact file content, nothing else."""
    path: str
    sha256: str
    rule: str

    @classmethod
    def parse(cls, spec: str) -> "AcceptedFinding":
        path, sep, rest = spec.rpartition("@sha256:")
        digest, _, rule = rest.partition(":")
        if not sep or not path or not re.fullmatch(r"[0-9a-f]{64}", digest) or rule not in RULES:
            raise SourceError(f"--accept-finding needs <path>@sha256:<64 hex digits>:<rule>, rule one of "
                              f"{', '.join(sorted(RULES))}")
        return cls(normalize_path(path), digest, rule)

    def __str__(self) -> str:
        return f"{self.path}@sha256:{self.sha256}:{self.rule}"


RULES = secretscan.RULES | datascan.RULES  # the rules that --accept-finding can name


def media_type_of(path: str) -> str:
    suffix = PurePosixPath(path).suffix.casefold()
    return TEXT_TYPES.get(suffix) or mimetypes.guess_type(path)[0] or "application/octet-stream"


class _NoAliasLoader(yaml.SafeLoader):
    """Frontmatter never needs anchors/aliases, and they allow expansion bombs."""

    def compose_node(self, parent, index):
        if self.check_event(yaml.AliasEvent):
            raise yaml.YAMLError("YAML aliases are not allowed in frontmatter")
        return super().compose_node(parent, index)


def normalize_text(text: str) -> str:
    """Classification and extraction only: line endings and a BOM are normalized; stored bytes stay untouched."""
    return text.removeprefix("\ufeff").replace("\r\n", "\n").replace("\r", "\n")


class _VisibleText(HTMLParser):
    """Text a reader sees: no script/style/template content, no comments; block elements become paragraphs."""
    HIDDEN = frozenset({"script", "style", "template"})
    BLOCKS = frozenset({"address", "article", "aside", "blockquote", "caption", "dd", "details", "div", "dl", "dt",
                        "figcaption", "figure", "footer", "form", "h1", "h2", "h3", "h4", "h5", "h6", "header", "hr",
                        "li", "main", "nav", "ol", "p", "pre", "section", "summary", "table", "td", "th", "title",
                        "tr", "ul"})

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.hidden, self.pre = [], 0, 0

    def handle_starttag(self, tag, attrs):
        if tag in self.HIDDEN:
            self.hidden += 1
        elif tag == "br":
            self.parts.append("\n")
        elif tag in self.BLOCKS:
            self.pre += tag == "pre"
            self.parts.append("\n\n")

    def handle_startendtag(self, tag, attrs):
        if tag not in self.HIDDEN:
            self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        if tag in self.HIDDEN:
            self.hidden = max(0, self.hidden - 1)
        elif tag in self.BLOCKS:
            self.pre = max(0, self.pre - (tag == "pre"))
            self.parts.append("\n\n")

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data if self.pre else re.sub(r"\s+", " ", data))


def html_text(source: str) -> str:
    parser = _VisibleText()
    parser.feed(source)
    parser.close()
    text = re.sub(r"[ \t]*\n[ \t]*", "\n", "".join(parser.parts))
    return re.sub(r"\n{3,}", "\n\n", text).strip("\n") + "\n"


def extracted_text(media_type: str, text: str) -> str:
    """The text of a searched text format exactly as profiles.py cuts it: HTML's visible text (entities decoded),
    every other format with normalized line endings."""
    text = normalize_text(text)
    return html_text(text) if media_type == HTML else text


def frontmatter(text: str) -> dict | None:
    text = normalize_text(text)
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


def pdf_text(data: bytes) -> tuple[str, str | None]:
    """(text layer, quarantine reason). Raises SourceError only for the page limit (a size limit)."""
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            return "", "encrypted PDF"
        if len(reader.pages) > MAX_PDF_PAGES:
            raise SourceError(f"more than {MAX_PDF_PAGES} pages")
        text = "".join(page.extract_text() or "" for page in reader.pages)
    except SourceError:
        raise
    except Exception as exc:  # pypdf raises many types on malformed input; all mean "unreadable"
        return "", f"unreadable PDF ({type(exc).__name__}: {exc})"
    return text, None if text.strip() else "PDF has no text layer (OCR is not available yet)"


def _credentials(path: str, sha256: str, texts: list[tuple[str, str]], accept: frozenset) -> tuple[str, ...]:
    """Scan every representation of the file; return the rules whose findings an acceptance covers, or refuse
    with the other findings. Only the line and the rule are reported, never the matched text."""
    acceptable = {a.rule for a in accept if (a.path, a.sha256) == (path, sha256)}
    refused, used = {}, set()
    for where, text in texts:
        for f in secretscan.findings(text, path):
            if f.rule in acceptable:
                used.add(f.rule)
            else:
                refused[f"line {f.line}{where} ({f.rule})"] = None
    if refused:
        raise SourceError(f"{path}: looks like it holds a credential: {', '.join(refused)}; remove it from the source "
                          f"(a reviewed false positive: --accept-finding {path}@sha256:<file digest>:<rule>)")
    return tuple(sorted(used))


def _personal_data(path: str, sha256: str, texts: list[tuple[str, str]], accept: frozenset,
                    names) -> tuple[tuple[str, ...], tuple]:
    """(accepted rules, open findings) of the datascan rules. A rule found in the original text is not reported
    again from the extracted text (the lines differ); a rule found only in the extracted text says so."""
    if path == MANIFEST:
        return (), ()
    acceptable = {a.rule for a in accept if (a.path, a.sha256) == (path, sha256)}
    used, found, seen = set(), [], set()
    for where, text in texts:
        hits = [f for f in datascan.findings(text, names) if f.rule not in seen]
        seen |= {f.rule for f in hits}
        used |= {f.rule for f in hits if f.rule in acceptable}
        found += [(where, f) for f in hits if f.rule not in acceptable]
    return tuple(sorted(used)), tuple(found)


def read_file(rel: str, data: bytes, accept: frozenset = frozenset(), names=None) -> SourceFile:
    """`accept`: AcceptedFinding values (ingest and package approval; package receipt accepts nothing). `names`: the
    compiled deny-list of datascan.load_names, or None."""
    if CONTROL.search(rel):  # Astra review #22: a passage handle with this path could never be opened
        raise SourceError(f"{rel!r}: control character in the path")
    path = normalize_path(rel)
    if not agentfiles.admitted(tuple(path.split("/"))):
        raise SourceError(f"{path}: hidden path outside the agent folders")
    if len(data) > MAX_FILE_BYTES:
        raise SourceError(f"{path}: larger than {MAX_FILE_BYTES} bytes")
    if secretscan.credential_name(path):
        raise SourceError(f"{path}: credential-like file name; remove it from the source")
    media_type, digest = media_type_of(path), sha256_hex(data)
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        text = None
    okf_type, quarantine, extracted = None, None, None
    if media_type == MARKDOWN:  # frontmatter decides K3, so markdown that cannot be classified is refused
        if text is None:
            raise SourceError(f"{path}: markdown is not UTF-8")
        try:
            okf_type = okf_type_of(frontmatter(text))
        except SourceError as exc:
            raise SourceError(f"{path}: {exc}") from None
    if media_type == PDF:
        try:
            extracted, quarantine = pdf_text(data)
        except SourceError as exc:
            raise SourceError(f"{path}: {exc}") from None
    elif media_type in TEXT_TYPES.values() and text is not None and "\x00" not in text:
        extracted = extracted_text(media_type, text)  # exactly what profiles.py cuts into passages
    texts = [("", text)] if text else []
    if extracted and extracted != text:
        texts.append((" of the extracted text", extracted))
    accepted = _credentials(path, digest, texts, accept)
    data_accepted, data_found = _personal_data(path, digest, texts, accept, names)
    if media_type in TEXT_TYPES.values():
        if text is None:
            quarantine = "not UTF-8 text"
        elif "\x00" in text:
            quarantine = "holds NUL bytes (binary, not text)"
    return SourceFile(path, data, digest, media_type, okf_type, quarantine, tuple(sorted(accepted + data_accepted)),
                      data_found)


def _read_regular(name: str, shown: str, dir_fd: int | None = None) -> bytes:
    """Open without following symlinks, relative to an already-open directory, then check the opened file
    itself: neither the file nor a parent directory can be swapped for a symlink between check and read."""
    try:
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=dir_fd)
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


def _raw_files(root: Path):
    """Yield (relative path, bytes). Directories are walked with os.fwalk (directory fds, symlinks never
    followed), so the tree cannot be redirected mid-walk. Hidden paths are skipped unless agentfiles admits them."""
    try:
        mode = os.lstat(root).st_mode
    except FileNotFoundError:
        raise SourceError(f"{root}: not found") from None
    if stat.S_ISLNK(mode):
        raise SourceError(f"{root}: symlinks are not followed")
    if stat.S_ISREG(mode):
        yield root.name, _read_regular(str(root), root.name)
        return
    if not stat.S_ISDIR(mode):
        raise SourceError(f"{root}: not a file or directory")
    for dirpath, dirnames, filenames, dir_fd in os.fwalk(root, follow_symlinks=False):
        rel_dir = Path(dirpath).relative_to(root)
        parts = rel_dir.parts
        kept = sorted(d for d in dirnames if agentfiles.admitted((*parts, d), is_dir=True))
        for d in kept:
            if stat.S_ISLNK(os.stat(d, dir_fd=dir_fd, follow_symlinks=False).st_mode):
                raise SourceError(f"{(rel_dir / d).as_posix()}: symlinks are not followed")
        dirnames[:] = kept
        for f in sorted(filenames):
            if agentfiles.admitted((*parts, f)):
                rel = (rel_dir / f).as_posix()
                yield rel, _read_regular(f, rel, dir_fd=dir_fd)


def read_source(root: Path, accept=(), names=None) -> list[SourceFile]:
    """Directory: every admitted regular file below it. File: just that file. `accept`: AcceptedFinding values;
    each must match a finding in the exact file content it names. `names`: datascan.load_names, or None."""
    accept = frozenset(accept)
    files, seen, total = [], set(), 0
    for rel, data in _raw_files(root):
        sf = read_file(rel, data, accept, names)
        if sf.path in seen:  # e.g. NFC and NFD spellings of one name
            raise SourceError(f"{sf.path}: two files normalize to the same path")
        seen.add(sf.path)
        total += len(sf.data)
        if total > MAX_SOURCE_BYTES:
            raise SourceError(f"{root}: larger than {MAX_SOURCE_BYTES} bytes")
        files.append(sf)
    if not files:
        raise SourceError(f"{root}: no files")
    used = {AcceptedFinding(f.path, f.sha256, rule) for f in files for rule in f.accepted}
    if unused := sorted(accept - used):
        raise SourceError(f"--accept-finding {unused[0]} matches no finding: the file changed (another digest), is "
                          f"not in the source, or that rule does not fire there")
    return files
