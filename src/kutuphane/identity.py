"""Caller identity (D38, D50): Kütüphane verifies OIDC/JWT access tokens itself; it never trusts headers.

- Signature against a JWKS (file path; air-gapped friendly), algorithm allowlist, required `exp`, `iat`, `iss`,
  `aud`, `sub`; small clock leeway. `iss` must equal a configured issuer exactly (no normalization; RFC 9207,
  docs/24 §12.5).
- More than one issuer (#157): the primary (`KUTUPHANE_OIDC_*`) and the issuers of `KUTUPHANE_OIDC_ISSUERS`, each
  with its own audience and JWKS and bound to principal prefixes. A principal under another issuer's prefix comes
  only from that issuer, and that issuer names nothing else. `curate` is never granted to its principals unless it
  says `"curate": true` (`refuse_curate`).
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
import re
from dataclasses import dataclass, replace
from pathlib import Path

import jwt

from .authz import PRINCIPAL, AuthzError
from .gate import Actor

ALGORITHMS = ["RS256", "ES256", "EdDSA"]
LEEWAY_SECONDS = 30
TYPE_CLAIM = "kutuphane/principal_type"
ENV = {"issuer": "KUTUPHANE_OIDC_ISSUER", "audience": "KUTUPHANE_OIDC_AUDIENCE", "jwks": "KUTUPHANE_OIDC_JWKS"}
DEFAULT_AUDIENCE = "kutuphane"  # the compose default (G13); tokens must still name it exactly
ISSUERS_ENV = "KUTUPHANE_OIDC_ISSUERS"  # #157: a JSON file with a list of more issuers
ISSUER_KEYS = ("issuer", "audience", "jwks", "principal_prefixes")  # and the optional "curate"
PREFIX = re.compile(r"^(user|agent):[a-z0-9][a-z0-9._@-]{0,60}\Z")  # never `role:`, never a whole kind


class AuthenticationError(PermissionError):
    pass


@dataclass(frozen=True)
class Verifier:
    issuer: str
    audience: str
    jwks: jwt.PyJWKSet
    prefixes: tuple[str, ...] = ()       # the principals it may name; () for the primary: all that no other owns
    curate: bool = True                  # may its principals be granted `curate`? Another issuer: only if it says so
    others: tuple["Verifier", ...] = ()  # the primary's more issuers (#157)

    @classmethod
    def from_env(cls) -> "Verifier":
        audience = os.environ.get(ENV["audience"]) or DEFAULT_AUDIENCE
        missing = [v for k, v in ENV.items() if k != "audience" and not os.environ.get(v)]
        if missing:
            raise RuntimeError(f"identity not configured: set {', '.join(missing)}")
        primary = cls.from_files(os.environ[ENV["issuer"]], audience, Path(os.environ[ENV["jwks"]]))
        others = issuers_from_env()
        if any(o.issuer == primary.issuer for o in others):
            raise RuntimeError(f"{ISSUERS_ENV}: {primary.issuer} is the primary issuer ({ENV['issuer']})")
        return replace(primary, others=others)

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

    def _claims(self, token: str) -> dict:
        try:
            return jwt.decode(token, self._key(token).key, algorithms=ALGORITHMS, audience=self.audience,
                              issuer=self.issuer, leeway=LEEWAY_SECONDS,
                              options={"require": ["exp", "iat", "iss", "aud", "sub"]})
        except jwt.PyJWTError as exc:
            raise AuthenticationError(f"invalid token: {exc}") from None

    def _owner(self, principal: str) -> "Verifier":
        return next((v for v in self.others if principal.startswith(v.prefixes)), self)

    def verify(self, token: str) -> Actor:
        if not token:
            raise AuthenticationError("missing token")
        try:
            iss = jwt.decode(token, options={"verify_signature": False}).get("iss")
        except jwt.PyJWTError as exc:
            raise AuthenticationError(f"malformed token: {exc}") from None
        # The exact `iss` picks the issuer whose key, audience and name are then verified; any other `iss` goes to
        # the primary, which refuses it.
        chosen = next((v for v in self.others if v.issuer == iss), self)
        actor = actor_from_claims(chosen._claims(token))
        for principal in filter(None, (actor.principal, actor.on_behalf_of)):
            if self._owner(principal) is not chosen:
                raise AuthenticationError(f"issuer {chosen.issuer} may not name {principal}")
        return actor


def _issuer(entry) -> Verifier:
    if not (isinstance(entry, dict) and set(ISSUER_KEYS) <= entry.keys() <= {*ISSUER_KEYS, "curate"}):
        raise ValueError(f"each issuer is {{{', '.join(ISSUER_KEYS)}}}, and optionally curate")
    if not all(isinstance(entry[k], str) and entry[k] for k in ("issuer", "audience", "jwks")):
        raise ValueError("issuer, audience and jwks must be non-empty strings")
    prefixes, curate = entry["principal_prefixes"], entry.get("curate", False)
    if not (isinstance(prefixes, list) and prefixes and all(isinstance(p, str) and PREFIX.match(p) for p in prefixes)):
        raise ValueError("principal_prefixes: one or more of user:<start of a name> or agent:<start of a name>")
    if not isinstance(curate, bool):
        raise ValueError("curate must be true or false")
    verifier = Verifier.from_files(entry["issuer"], entry["audience"], Path(entry["jwks"]))
    return replace(verifier, prefixes=tuple(prefixes), curate=curate)


def issuers_from_env() -> tuple[Verifier, ...]:
    """The issuers of `KUTUPHANE_OIDC_ISSUERS` (none when it is not set). Two issuers never share a prefix."""
    path = os.environ.get(ISSUERS_ENV)
    if not path:
        return ()
    try:
        entries = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(entries, list):
            raise ValueError("a JSON list of issuers")
        issuers = tuple(_issuer(e) for e in entries)
    except (OSError, ValueError, jwt.PyJWTError) as exc:
        raise RuntimeError(f"{ISSUERS_ENV}: {exc}") from None
    if len({v.issuer for v in issuers}) != len(issuers):
        raise RuntimeError(f"{ISSUERS_ENV}: an issuer is listed twice")
    owned = [(p, v.issuer) for v in issuers for p in v.prefixes]
    for a, x in owned:
        for b, y in owned:
            if x != y and a.startswith(b):
                raise RuntimeError(f"{ISSUERS_ENV}: the prefixes {a} and {b} of two issuers overlap")
    return issuers


def refuse_curate(subject: str) -> None:
    """#157: `curate` for a principal under another issuer's prefix only when that issuer says `"curate": true`."""
    owner = next((v for v in issuers_from_env() if subject.startswith(v.prefixes)), None)
    if owner is not None and not owner.curate:
        raise AuthzError(f"curate is refused to the principals of issuer {owner.issuer} "
                         f"(set \"curate\": true on it in {ISSUERS_ENV} to allow it)")


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
