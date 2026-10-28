"""Caller identity (D38, D50): Kütüphane verifies OIDC/JWT access tokens itself; it never trusts headers.

- Signature against a JWKS (file path; air-gapped friendly), algorithm allowlist, required `exp`, `iat`, `iss`,
  `aud`, `sub`; small clock leeway. `iss` must equal the one configured issuer exactly (no normalization; RFC 9207,
  docs/24 §12.5).
- Principal kind comes from the namespaced claim `kutuphane/principal_type` (`user` default, or `agent`); the
  IdP is configured to emit it.
- Delegation travels as the RFC 8693 actor claim: `sub` = user, `act.sub` = agent. One level only; nested
  `act` is refused. A token never grants anything by itself: the agent still needs a live delegation (authz).
- Headless clients (docs/24 §12.4): OAuth client credentials at the IdP, whose mapper sets the principal type
  `agent` and `sub` = the agent name; on-behalf-of work is an RFC 8693 token exchange (`act`), as above.
- The client is the claim `client_id` (RFC 9068), else `azp`. It is recorded only: it never changes rights or
  origin (docs/24 §5.1).
"""
import json
import os
from dataclasses import dataclass
from pathlib import Path

import jwt

from .authz import PRINCIPAL
from .gate import Actor

ALGORITHMS = ["RS256", "ES256", "EdDSA"]
LEEWAY_SECONDS = 30
TYPE_CLAIM = "kutuphane/principal_type"
ENV = {"issuer": "KUTUPHANE_OIDC_ISSUER", "audience": "KUTUPHANE_OIDC_AUDIENCE", "jwks": "KUTUPHANE_OIDC_JWKS"}
DEFAULT_AUDIENCE = "kutuphane"  # the compose default (G13); tokens must still name it exactly


class AuthenticationError(PermissionError):
    pass


@dataclass(frozen=True)
class Verifier:
    issuer: str
    audience: str
    jwks: jwt.PyJWKSet

    @classmethod
    def from_env(cls) -> "Verifier":
        audience = os.environ.get(ENV["audience"]) or DEFAULT_AUDIENCE
        missing = [v for k, v in ENV.items() if k != "audience" and not os.environ.get(v)]
        if missing:
            raise RuntimeError(f"identity not configured: set {', '.join(missing)}")
        return cls.from_files(os.environ[ENV["issuer"]], audience, Path(os.environ[ENV["jwks"]]))

    @classmethod
    def from_files(cls, issuer: str, audience: str, jwks_path: Path) -> "Verifier":
        return cls(issuer, audience, jwt.PyJWKSet.from_dict(json.loads(jwks_path.read_text())))

    def _key(self, token: str):
        try:
            kid = jwt.get_unverified_header(token).get("kid")
        except jwt.PyJWTError as exc:
            raise AuthenticationError(f"malformed token: {exc}") from None
        keys = self.jwks.keys
        if kid is not None:
            keys = [k for k in keys if k.key_id == kid]
        if len(keys) != 1:
            raise AuthenticationError("no unique signing key for token")
        return keys[0]

    def verify(self, token: str) -> Actor:
        if not token:
            raise AuthenticationError("missing token")
        try:
            claims = jwt.decode(token, self._key(token).key, algorithms=ALGORITHMS, audience=self.audience,
                                issuer=self.issuer, leeway=LEEWAY_SECONDS,
                                options={"require": ["exp", "iat", "iss", "aud", "sub"]})
        except jwt.PyJWTError as exc:
            raise AuthenticationError(f"invalid token: {exc}") from None
        return actor_from_claims(claims)


def _principal(kind: str, name) -> str:
    """No normalization: two distinct IdP subjects must never map to one principal. The IdP mapper emits
    lowercase names in the principal alphabet; anything else is refused."""
    principal = f"{kind}:{name}" if isinstance(name, str) else ""
    if not PRINCIPAL.match(principal):
        raise AuthenticationError(f"subject cannot be mapped to a principal: {name!r}")
    return principal


def _client_id(claims: dict) -> str | None:
    value = claims.get("client_id", claims.get("azp"))
    if value is not None and not (isinstance(value, str) and value):
        raise AuthenticationError("client_id must be a non-empty string")
    return value


def actor_from_claims(claims: dict) -> Actor:
    client_id = _client_id(claims)
    act = claims.get("act")
    if act is not None:
        if not isinstance(act, dict) or "act" in act:
            raise AuthenticationError("only one level of delegation (act) is accepted")
        return Actor(_principal("agent", act.get("sub")), on_behalf_of=_principal("user", claims["sub"]),
                     client_id=client_id)
    kind = claims.get(TYPE_CLAIM, "user")
    if kind not in ("user", "agent"):
        raise AuthenticationError(f"{TYPE_CLAIM} must be user or agent")
    return Actor(_principal(kind, claims["sub"]), client_id=client_id)
