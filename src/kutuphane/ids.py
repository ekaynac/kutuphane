"""Version identifiers (D26): content, profile and policy each get a content-addressed id.

An id is SHA-256 over a versioned canonical JSON encoding. Only meaning goes in: file paths and bytes for
content; component versions and settings for a profile; the policy document for a policy. File order,
timestamps and transport metadata never do (AT-01).
"""
import hashlib
import json
import unicodedata

ENCODING_VERSION = 1
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
