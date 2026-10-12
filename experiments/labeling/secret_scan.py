"""Heuristic secret detector shared by corpus selection and the labelling server.

Heuristic only: a hit excludes the document (fail-closed); a miss is not proof of absence,
which is why content is served only on the local host / VPN to the operator.
"""
import re

_KEYWORD = r"(?:pass(?:word|wd|phrase)?|pwd|secret|token|api[_-]?key|access[_-]?key|private[_-]?key|client[_-]?secret|auth|bearer|credential)"

PATTERNS = [
    # key = value / key: value whose value looks generated (letters + digits, 8+ chars)
    re.compile(rf"(?i)\b{_KEYWORD}\w*\s*[:=]\s*['\"]?(?!<|\$\{{|\{{\{{|xxx|\*\*\*|changeme|example|placeholder|redacted)"
               r"(?=[^\s'\"<>]*\d)(?=[^\s'\"<>]*[A-Za-z])[^\s'\"<>]{8,}"),
    # ...or any long value (all-letter passphrases too); kept from the first scanner, never narrower
    re.compile(rf"(?i)\b{_KEYWORD}\w*\s*[:=]\s*['\"]?[A-Za-z0-9_\-/+=.]{{12,}}"),
    re.compile(r"(?i)\bauthorization:\s*(?:bearer|basic)\s+[A-Za-z0-9._~+/=-]{8,}"),
    re.compile(r"-----BEGIN [A-Z ]*(?:PRIVATE KEY|CERTIFICATE)-----"),
    re.compile(r"\b(?:sk|pk|rk)[-_](?:live|test|proj|ant)?[-_]?[A-Za-z0-9_-]{16,}"),
    re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr|github_pat|glpat|xox[abprs])[-_][A-Za-z0-9_-]{16,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),  # JWT
    re.compile(r"(?i)\b[a-z][a-z0-9+.-]*://[^\s:/@]+:[^\s/@]{3,}@"),  # URI with user:password@
    re.compile(r"(?i)\bhf_[A-Za-z0-9]{30,}"),
]


def find_secret(text: str):
    """Return the name of the first matching pattern index, or None."""
    for i, rx in enumerate(PATTERNS):
        if rx.search(text):
            return f"p{i}"
    return None
