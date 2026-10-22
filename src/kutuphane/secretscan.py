"""Credential check for every file that enters a book (ingest and package receipt). A finding refuses the whole
book, unless the operator accepted exactly that finding for exactly that file content (`--accept-finding`,
source.AcceptedFinding).

Two checks, both fail closed:
- credential-like file NAMES (key stores, credential files, `settings.local.json`) are refused whatever they hold;
- file TEXT (anything that decodes as UTF-8, the text layer of PDFs, the visible text of HTML) is matched against
  credential rules.

How a value is judged (heuristic only: a miss is not proof of absence):
- a credential key (`password`, `api_key`, `"token"`: quoted keys too) with a value is `assigned-credential`. A key
  that only names a setting (`AUTH_MODE`, `TOKEN_URL`, `tokenizer`) does not count.
- a quoted string literal is taken whole, whatever characters it holds (`password = "aB3!very.secret-password"`);
  an unquoted value stops at expression characters (`token = request.headers.get(...)` is code). In source code
  (`.py`, `.ts`, `.js`, …) a bare identifier after `password =` is a variable, so there only quoted literals, JSON
  string pairs and fixed token formats count.
- JSON string pairs are decoded first, so escaped keys and values (`"pass\\u0077ord"`) are judged as a reader sees them.
- not a credential: placeholders (`${PASSWORD}`, `<your-key>`, `changeme`, `example…`, `***`), environment variable
  names (`LLMDAP_TRUST_SECRET`), semantic constants made of lower-case words (`refresh_token`, `client-credentials`),
  URLs, and literals with whitespace (messages).
- fixed token formats (private key blocks, `sk-…`, `ghp_…`, AWS keys, JWTs, `user:password@host`, …) count anywhere.
A finding names the rule and the line, never the matched value.
"""
import json
import re
from dataclasses import dataclass
from pathlib import PurePosixPath

ASSIGNED = "assigned-credential"
_KEYWORD = (r"(?:pass(?:word|wd|phrase)?|pwd|secret|token|api[_-]?key|access[_-]?key|private[_-]?key|"
            r"client[_-]?secret|auth(?!or)|bearer|credential)")
_VALUE = r"[A-Za-z0-9_\-/+=]"  # unquoted: no dots, brackets or parentheses, those are expressions, not literals
# Keys that NAME a credential setting rather than hold one (AUTH_MODE, TOKEN_URL, PASSWORD_FILE, tokenizer, passage).
_KEY = _KEYWORD + r"\w*" + "".join(f"(?<!{s})" for s in (
    "mode", "type", "types", "url", "uri", "endpoint", "method", "provider", "file", "path", "env", "name", "header",
    "scheme", "dir", "kind", "format", "id", "period", "usage", "label", "field", "param", "prefix", "length", "size",
    "count", "ttl", "version", "helper", "command", "var", "izer", "izers", "ize", "ized", "ization", "age", "ages",
    "limit", "limits", "timeout", "expiry", "expires", "policy"))
_QK = r"['\"]?"  # a quoted key: "password": …, 'token': …
_END = r"(?![\w.(\[])"

_UNQUOTED = re.compile(  # key = value that looks generated (letters + digits, 8+ chars)
    rf"(?i){_KEY}{_QK}\s*[:=]\s*['\"]?(?P<v>{_VALUE}{{8,}}){_END}")
_QUOTED = re.compile(  # key = "literal": the whole literal, any characters, escapes kept
    rf"(?i){_KEY}{_QK}\s*[:=]\s*(?P<q>['\"])(?P<v>(?:\\.|(?!(?P=q))[^\\\n])*)(?P=q)")
_LINE = re.compile(  # KEY=longliteral / key: longliteral as a whole line (.env, YAML, ini)
    rf"(?im)^[ \t]*(?:export[ \t]+)?{_QK}\w*{_KEY}{_QK}(?:=|[ \t]*:[ \t]*)(?P<v>{_VALUE}{{12,}})[ \t\r]*$")
_JSON_STRING = re.compile(r'"(?:[^"\\\x00-\x1f]|\\.)*"')
_JSON_COLON = re.compile(r"\s*:\s*")
_JSON_KEY = re.compile(rf"(?i){_KEY}\Z")

_FIXED = (
    ("authorization-header", re.compile(r"(?i)\bauthorization:\s*(?:bearer|basic)\s+[A-Za-z0-9._~+/=-]{8,}")),
    ("private-key", re.compile(  # the armor line with a key body after it (a lone header is a format constant)
        r"-----BEGIN [A-Z ]*PRIVATE KEY(?: BLOCK)?-----[ \t]*\r?\n(?:[\w-]+:[^\n]*\n)*\s*[A-Za-z0-9+/=]{20,}")),
    ("api-key", re.compile(r"\b(?:sk|pk|rk)[-_](?:live|test|proj|ant)?[-_]?[A-Za-z0-9_-]{16,}")),
    ("access-token", re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr|github_pat|glpat|xox[abprs])[-_][A-Za-z0-9_-]{16,}")),
    ("aws-access-key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}")),
    ("uri-password", re.compile(  # user:password@host, not the documentation forms user:password@ or ${VAR}
        r"(?i)\b[a-z][a-z0-9+.-]*://[^\s:/@]+:(?!(?:pass(?:word|wd)?|pwd|secret|xxx+|\*+)@)[^\s/@$<{][^\s/@]{2,}@")),
    ("hf-token", re.compile(r"\bhf_[A-Za-z0-9]{30,}")),
)
RULES = frozenset({ASSIGNED, *(rule for rule, _ in _FIXED)})
CODE_SUFFIXES = (".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs")

_PLACEHOLDERS = ("<", "$", "{{", "%", "xxx", "***", "changeme", "example", "placeholder", "redacted", "your")
_SEMANTIC = re.compile(r"[a-z]{1,15}(?:[_.-][a-z]{1,15})+")  # refresh_token, client-credentials, my.app.name
_URL = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*://")

CREDENTIAL_NAMES = frozenset({
    "settings.local.json", "credentials", "credentials.json", "credentials.yaml", "credentials.yml", "auth.json",
    "secrets.json", "secrets.yaml", "secrets.yml", "secrets.toml", "token.json",
    "id_rsa", "id_dsa", "id_ecdsa", "id_ed25519", "htpasswd",
})
CREDENTIAL_SUFFIXES = (".env", ".p12", ".pfx", ".jks", ".keystore", ".kdbx", ".ppk")


@dataclass(frozen=True, order=True)
class Finding:
    line: int  # 1-based line of the text that was scanned
    rule: str


def credential_name(path: str) -> bool:
    name = PurePosixPath(path).name.casefold()
    return name in CREDENTIAL_NAMES or name.endswith(CREDENTIAL_SUFFIXES) or name.startswith("client_secret")


def _credential(value: str, long: float) -> bool:
    """A value of a credential key: 8+ characters with letters and digits, or `long`+ characters; never a
    placeholder, an environment variable name (no lower-case letter, no digit) or a semantic constant."""
    if len(value) < 8 or value.casefold().startswith(_PLACEHOLDERS) or _SEMANTIC.fullmatch(value):
        return False
    if not re.search(r"[a-z0-9]", value):
        return False
    return len(value) >= long or bool(re.search(r"\d", value) and re.search(r"[A-Za-z]", value))


def _literal(value: str) -> bool:
    """A quoted or decoded string literal: taken whole, whatever characters it holds."""
    return not any(c.isspace() for c in value) and not _URL.match(value) and _credential(value, 12)


def _json_pairs(text: str):
    """(offset, key, value) of every `"key": "value"` string pair, both decoded (escapes resolved). Outside a JSON
    string there is no quote, so reading string tokens left to right follows the document exactly."""
    tokens = list(_JSON_STRING.finditer(text))
    for key, value in zip(tokens, tokens[1:]):
        colon = _JSON_COLON.match(text, key.end())
        if not colon or colon.end() != value.start():
            continue
        try:
            yield key.start(), json.loads(key.group()), json.loads(value.group())
        except ValueError:  # an invalid escape: not JSON, the regex rules still see the raw text
            continue


def findings(text: str, path: str = "") -> list[Finding]:
    """Every credential-like match in the text of the file at `path`, by line and rule (never the value)."""
    code = path.casefold().endswith(CODE_SUFFIXES)
    hits = {(rule, m.start()) for rule, rx in _FIXED for m in rx.finditer(text)}
    hits |= {(ASSIGNED, m.start()) for m in _QUOTED.finditer(text) if _literal(m["v"])}
    hits |= {(ASSIGNED, at) for at, key, value in _json_pairs(text)
             if isinstance(key, str) and isinstance(value, str) and _JSON_KEY.search(key) and _literal(value)}
    if not code:
        hits |= {(ASSIGNED, m.start()) for m in _UNQUOTED.finditer(text) if _credential(m["v"], float("inf"))}
        hits |= {(ASSIGNED, m.start()) for m in _LINE.finditer(text) if _credential(m["v"], 12)}
    return sorted({Finding(text.count("\n", 0, at) + 1, rule) for rule, at in hits})
