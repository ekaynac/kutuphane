"""Credential check for every file that enters a book (ingest and package receipt). A hit refuses the whole book.

Two checks, both fail closed:
- credential-like file NAMES (key stores, credential files, `settings.local.json`) are refused whatever they hold;
- file TEXT (anything that decodes as UTF-8, and the text layer of PDFs) is matched against credential patterns.

The patterns start from the labelling scanner (experiments/labeling/secret_scan.py) and are tuned for books that
hold code: a value that is an expression (`token = request.headers.get(...)`) or a key that only names a setting
(`AUTH_MODE`, `TOKEN_URL`) is not a credential. In source code (`.py`, `.ts`, `.js`, …) a bare identifier after
`password =` is a variable, so there only quoted literals and fixed token formats count. Heuristic only: a miss
is not proof of absence. Reports name the file and the kind of match, never the matched value.
"""
import re
from pathlib import PurePosixPath

_KEYWORD = (r"(?:pass(?:word|wd|phrase)?|pwd|secret|token|api[_-]?key|access[_-]?key|private[_-]?key|"
            r"client[_-]?secret|auth(?!or)|bearer|credential)")
_VALUE = r"[A-Za-z0-9_\-/+=]"  # no dots, brackets or parentheses: those are expressions, not literals
_PLACEHOLDER = r"(?!<|\$|\{\{|xxx|\*\*\*|changeme|example|placeholder|redacted|your)"
# Keys that NAME a credential setting rather than hold one (AUTH_MODE, TOKEN_URL, PASSWORD_FILE, SECRET_ENV).
_KEY = _KEYWORD + r"\w*" + "".join(f"(?<!{s})" for s in (
    "mode", "type", "types", "url", "uri", "endpoint", "method", "provider", "file", "path", "env", "name", "header",
    "scheme", "dir", "kind", "format", "id", "period", "usage", "label", "field", "param", "prefix", "length", "size",
    "count", "ttl", "version", "helper", "command", "var"))
_END = r"(?![\w.(\[])"
_NOT_ENV_NAME = r"(?-i:(?=" + _VALUE + r"*[a-z0-9]))"  # LLMDAP_TRUST_SECRET names a variable; it is not a value

_ASSIGNED = ("assigned credential", re.compile(  # key = value that looks generated (letters + digits, 8+ chars)
    rf"(?i){_KEY}\s*[:=]\s*['\"]?{_PLACEHOLDER}(?={_VALUE}*\d)(?={_VALUE}*[A-Za-z]){_VALUE}{{8,}}{_END}"))
_LINE = ("credential line", re.compile(  # KEY=longliteral / key: longliteral as a whole line (.env, YAML, ini)
    rf"(?im)^\s*(?:export\s+)?\w*{_KEY}(?:=|\s*:\s*){_PLACEHOLDER}{_NOT_ENV_NAME}{_VALUE}{{12,}}\s*$"))
_ALWAYS = (
    ("quoted credential", re.compile(  # key = "long literal" (all-letter passphrases too)
        rf"(?i){_KEY}\s*[:=]\s*(['\"]){_PLACEHOLDER}{_NOT_ENV_NAME}{_VALUE}{{12,}}\1")),
    ("authorization header", re.compile(r"(?i)\bauthorization:\s*(?:bearer|basic)\s+[A-Za-z0-9._~+/=-]{8,}")),
    ("private key", re.compile(  # the armor line with a key body after it (a lone header is a format constant)
        r"-----BEGIN [A-Z ]*PRIVATE KEY(?: BLOCK)?-----[ \t]*\r?\n(?:[\w-]+:[^\n]*\n)*\s*[A-Za-z0-9+/=]{20,}")),
    ("API key", re.compile(r"\b(?:sk|pk|rk)[-_](?:live|test|proj|ant)?[-_]?[A-Za-z0-9_-]{16,}")),
    ("access token", re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr|github_pat|glpat|xox[abprs])[-_][A-Za-z0-9_-]{16,}")),
    ("AWS access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("JWT", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}")),
    ("URI with password", re.compile(  # user:password@host, not the documentation forms user:password@ or ${VAR}
        r"(?i)\b[a-z][a-z0-9+.-]*://[^\s:/@]+:(?!(?:pass(?:word|wd)?|pwd|secret|xxx+|\*+)@)[^\s/@$<{][^\s/@]{2,}@")),
    ("Hugging Face token", re.compile(r"\bhf_[A-Za-z0-9]{30,}")),
)
PATTERNS = (_ASSIGNED, _LINE, *_ALWAYS)
CODE_SUFFIXES = (".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs")

CREDENTIAL_NAMES = frozenset({
    "settings.local.json", "credentials", "credentials.json", "credentials.yaml", "credentials.yml", "auth.json",
    "secrets.json", "secrets.yaml", "secrets.yml", "secrets.toml", "token.json",
    "id_rsa", "id_dsa", "id_ecdsa", "id_ed25519", "htpasswd",
})
CREDENTIAL_SUFFIXES = (".env", ".p12", ".pfx", ".jks", ".keystore", ".kdbx", ".ppk")


def credential_name(path: str) -> bool:
    name = PurePosixPath(path).name.casefold()
    return name in CREDENTIAL_NAMES or name.endswith(CREDENTIAL_SUFFIXES) or name.startswith("client_secret")


def find(text: str, path: str = "") -> str | None:
    """The kind of the first credential-like match in the text of the file at `path`, or None."""
    patterns = _ALWAYS if path.casefold().endswith(CODE_SUFFIXES) else PATTERNS
    return next((kind for kind, rx in patterns if rx.search(text)), None)
