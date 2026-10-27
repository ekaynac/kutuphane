"""Development-only tokens (M1 has no IdP in the box, D50). Refuses to run unless KUTUPHANE_DEV=1.

`dev-keys DIR` writes a private key (mode 600) and the matching JWKS; point KUTUPHANE_OIDC_JWKS at the JWKS.
`dev-token` signs a short-lived token with the same claims an IdP would emit: `sub`, optional
`kutuphane/principal_type: agent`, optional RFC 8693 `act` for an agent acting for the user, optional `client_id`
(RFC 9068: the OAuth client the token was issued to).
"""
import json
import os
import time
from pathlib import Path

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

KID = "dev-1"
TTL_SECONDS = 8 * 3600


def _require_dev() -> None:
    if os.environ.get("KUTUPHANE_DEV") != "1":
        raise RuntimeError("development tokens are disabled (set KUTUPHANE_DEV=1 on a development machine only)")


def make_keys(directory: Path) -> dict:
    _require_dev()
    directory.mkdir(parents=True, exist_ok=True)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private = directory / "dev-private.pem"
    fd = os.open(private, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                  serialization.NoEncryption()))
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
    jwks = directory / "jwks.json"
    jwks.write_text(json.dumps({"keys": [{**jwk, "kid": KID, "use": "sig", "alg": "RS256"}]}))
    return {"private_key": str(private), "jwks": str(jwks)}


def make_token(private_key: Path, *, issuer: str, audience: str, sub: str, agent: bool = False,
               act: str | None = None, client_id: str | None = None) -> str:
    _require_dev()
    now = int(time.time())
    claims = {"iss": issuer, "aud": audience, "sub": sub, "iat": now, "exp": now + TTL_SECONDS}
    if agent:
        claims["kutuphane/principal_type"] = "agent"
    if act:
        claims["act"] = {"sub": act}
    if client_id:
        claims["client_id"] = client_id
    key = serialization.load_pem_private_key(private_key.read_bytes(), password=None)
    return jwt.encode(claims, key, algorithm="RS256", headers={"kid": KID})
