"""Installation signing keys (D29, D51): Ed25519, detached signatures over the canonical package manifest.

The private key is a PEM file readable only by its owner; its path comes from KUTUPHANE_SIGNING_KEY. A key is
named by its fingerprint: `ed25519:` + SHA-256 of the raw public key.
"""
import hashlib
import os
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

KEY_ENV = "KUTUPHANE_SIGNING_KEY"


def fingerprint(public: Ed25519PublicKey) -> str:
    raw = public.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return "ed25519:" + hashlib.sha256(raw).hexdigest()


def generate(private_path: Path) -> dict:
    key = Ed25519PrivateKey.generate()
    fd = os.open(private_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                  serialization.NoEncryption()))
    public_path = private_path.with_suffix(".pub.pem")
    public_path.write_bytes(public_pem(key.public_key()))
    return {"private_key": str(private_path), "public_key": str(public_path),
            "fingerprint": fingerprint(key.public_key())}


def public_pem(public: Ed25519PublicKey) -> bytes:
    return public.public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)


def load_private(path: Path | None = None) -> Ed25519PrivateKey:
    path = path or Path(os.environ.get(KEY_ENV, ""))
    if not path or not path.is_file():
        raise RuntimeError(f"signing key not found: set {KEY_ENV}")
    if path.stat().st_mode & 0o077:
        raise RuntimeError(f"{path} must be private (chmod 600)")
    key = serialization.load_pem_private_key(path.read_bytes(), password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise RuntimeError("signing key must be Ed25519")
    return key


def load_public(pem: bytes) -> Ed25519PublicKey:
    key = serialization.load_pem_public_key(pem)
    if not isinstance(key, Ed25519PublicKey):
        raise ValueError("public key must be Ed25519")
    return key


def raw_public(public: Ed25519PublicKey) -> bytes:
    return public.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)


def verify(public_raw: bytes, signature: bytes, message: bytes) -> bool:
    try:
        Ed25519PublicKey.from_public_bytes(public_raw).verify(signature, message)
        return True
    except (InvalidSignature, ValueError):
        return False
