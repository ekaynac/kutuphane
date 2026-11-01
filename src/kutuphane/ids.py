"""Version identifiers (D26): content, profile and policy each get a content-addressed id.

An id is SHA-256 over a versioned canonical JSON encoding. Only meaning goes in: file paths and bytes for
content; component versions and settings for a profile; the policy document for a policy. File order,
timestamps and transport metadata never do (AT-01).
"""
import hashlib
import json
import re
import unicodedata

ENCODING_VERSION = 1
SLUG = r"[a-z0-9][a-z0-9-]{0,62}"  # a book slug, unanchored: callers anchor it
CONTROL = re.compile(r"[\x00-\x1f\x7f]")  # a control character: never in a path, a handle or a name
PREFIX = {"content": "ct", "profile": "pf", "policy": "pl"}


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _make(kind: str, body) -> str:
    digest = sha256_hex(canonical({"kind": kind, "v": ENCODING_VERSION, "body": body}))
    return f"{PREFIX[kind]}_{digest}"


def normalize_path(path: str) -> str:
    """POSIX, NFC, relative, no '.'/'..' segments; raises ValueError otherwise."""
    norm = unicodedata.normalize("NFC", path.replace("\\", "/"))
    parts = norm.split("/")
    if norm.startswith("/") or any(p in ("", ".", "..") for p in parts):
        raise ValueError(f"unsafe or non-canonical path: {path!r}")
    return norm


def content_id(files: dict) -> str:
    """files: {relative path: sha256 hex of its bytes}."""
    return _make("content", sorted((normalize_path(p), h) for p, h in files.items()))


def profile_id(spec: dict) -> str:
    return _make("profile", spec)


def policy_id(doc: dict) -> str:
    return _make("policy", doc)


def request_digest(args) -> bytes:
    """SHA-256 of the canonical JSON of a request's arguments (docs/24 §6.4): the idempotency check. Key order does
    not count; every value does. The caller leaves out the idempotency key itself."""
    return hashlib.sha256(canonical(args)).digest()


class IdempotencyConflict(ValueError):
    """docs/24 §6.4, §12.2: the same idempotency key with another request (HTTP 409)."""


class LimitExceeded(ValueError):
    """docs/24 §13: the daily write limit or the open-job limit (HTTP 429)."""
