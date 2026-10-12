"""Regression tests: the shared scanner must never be narrower than the first one.

Run: python3 -I test_secret_scan.py
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from secret_scan import find_secret  # noqa: E402

# The scanner select_corpus.py shipped with first; everything it caught must still be caught.
ORIGINAL = re.compile(
    r"(?i)(password|passwd|secret|token|api[_-]?key|bearer)\s*[:=]\s*['\"]?[A-Za-z0-9_\-/+]{12,}"
    r"|-----BEGIN [A-Z ]*PRIVATE KEY-----"
    r"|\b(sk|ghp|gho|github_pat|xox[bp])[-_][A-Za-z0-9_]{16,}"
)

MUST_MATCH = [
    "DB_PASSWORD=abcdefghijklmnop",
    "MY_SECRET: abcdefghijklmnopq",
    "x_api_key='abcdefghijklmnop'",
    "password: correcthorsebatterystaple",
    "token = abc123def456",
    "Authorization: Bearer abcdefgh12345678",
    "-----BEGIN OPENSSH PRIVATE KEY-----",
    "ghp_abcdefghijklmnopqrstuvwxyz",
    "postgres://user:hunter22@db.internal",
    "AKIAABCDEFGHIJKLMNOP",
    "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.abcdefghijklmnop",
]
MUST_NOT_MATCH = [
    "the token: is rotated weekly",
    "api_key: ${API_KEY}",
    "password: <redacted>",
]


def main() -> int:
    failures = [s for s in MUST_MATCH if not find_secret(s)]
    failures += [f"original-only: {s}" for s in MUST_MATCH if ORIGINAL.search(s) and not find_secret(s)]
    failures += [f"false positive: {s}" for s in MUST_NOT_MATCH if find_secret(s)]
    for f in failures:
        print("FAIL", f)
    print("ok" if not failures else f"{len(failures)} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
