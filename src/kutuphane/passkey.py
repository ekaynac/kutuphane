"""Passkey (WebAuthn) ceremonies of curator web (docs/25 §3.3, §3.4, §5; D72).

- **Enrollment** (owner credential, the CLI): a person (`curator_person`, one stable WebAuthn user handle) and a
  one-time code, valid 15 minutes. The code gives an `enrollment` session that may only register one passkey.
- **Login**: a discoverable passkey with user verification signs a `login` challenge; `userHandle` names the person.
- **Act**: the passkey signs `SHA-256(DOMAIN || canonical(statement))`. The statement holds the action, every note
  reference and digest, the Standing in force, the new values, the reason, a fresh 32-byte nonce and the expiry. The
  database accepts an effect only as an item of the act's stored statement (migration 023).

Every ceremony checks the exact origin and RP ID, user verification, the raw `crossOrigin` and `topOrigin` fields
(py_webauthn does not keep them), and the counter of the passkey over logins and acts. Times are compared with the
database `clock_timestamp()`. Curator web is in the trusted base (docs/25 §3.5): the page that shows a statement also
chooses what the person signs; `verify_acts` finds rows that no stored passkey signed.
"""
import base64
import hashlib
import json
import os
import secrets
import urllib.parse
from dataclasses import dataclass

import webauthn
from psycopg.types.json import Jsonb
from webauthn.helpers.exceptions import InvalidAuthenticationResponse, InvalidRegistrationResponse
from webauthn.helpers.structs import (AuthenticatorSelectionCriteria, PublicKeyCredentialDescriptor,
                                      ResidentKeyRequirement, UserVerificationRequirement)

from . import authz, ids

DOMAIN = b"kutuphane/curator-act/v1\n"
CHALLENGE_TTL = "5 minutes"
SESSION_TTL = "8 hours"
ENROLL_TTL = "15 minutes"
TIMEOUT_MS = 120_000
ACTIONS = ("standing", "confirm", "withdraw", "delegate", "end_delegation")
ENV = {"rp_id": "KUTUPHANE_WEBAUTHN_RP_ID", "origin": "KUTUPHANE_WEBAUTHN_ORIGIN"}


class CeremonyRefused(PermissionError):
    """A refused ceremony. The message is a short, safe reason (it never holds a credential or a code)."""


def b64u(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def unb64u(text: str) -> bytes:
    if not isinstance(text, str):
        raise CeremonyRefused("malformed credential")
    try:
        return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))
    except ValueError:
        raise CeremonyRefused("malformed credential") from None


def digest(secret: str) -> bytes:
    """The stored form of a one-time code or a session cookie value."""
    return hashlib.sha256(secret.encode()).digest()


@dataclass(frozen=True)
class Config:
    """The relying party: the full host name as RP ID, and one exact origin (docs/25 §3.2)."""
    rp_id: str
    origin: str
    rp_name: str = "Kütüphane"

    def __post_init__(self):
        parts = urllib.parse.urlsplit(self.origin)
        local = parts.hostname == "localhost"  # a secure context for development only (WebAuthn, cookies)
        if parts.scheme not in (("https", "http") if local else ("https",)) or parts.path or parts.query \
                or parts.hostname != self.rp_id or (parts.port is not None and not local):
            raise ValueError("the WebAuthn origin must be https://<rp id> (http://localhost:<port> for development)")

    @classmethod
    def from_env(cls) -> "Config":
        missing = [v for v in ENV.values() if not os.environ.get(v)]
        if missing:
            raise RuntimeError(f"curator web not configured: set {', '.join(missing)}")
        return cls(os.environ[ENV["rp_id"]], os.environ[ENV["origin"]])


def challenge_of(payload: dict) -> bytes:
    return hashlib.sha256(DOMAIN + ids.canonical(payload)).digest()


def _now(conn):
    return conn.execute("SELECT clock_timestamp()").fetchone()[0]


def _store(conn, cfg: Config, *, session, principal, action: str, fields: dict) -> tuple[str, dict, bytes]:
    """A new statement and its challenge row; the challenge is the digest of the statement (docs/25 §5.2)."""
    now = _now(conn)
    expires = conn.execute(f"SELECT %s::timestamptz + interval '{CHALLENGE_TTL}'", (now,)).fetchone()[0]
    payload = {"v": 1, "action": action, "rp_id": cfg.rp_id, "principal": principal, "nonce": b64u(secrets.token_bytes(32)),
               "expires_at": expires.isoformat(), **fields}
    challenge = challenge_of(payload)
    cid = "ch_" + secrets.token_hex(16)
    conn.execute("INSERT INTO curator_challenge (id, session, principal, action, payload, challenge, created_at, "
                 "expires_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                 (cid, session, principal, action, Jsonb(payload), challenge, now, expires))
    return cid, payload, challenge


def _challenge(conn, cid, *, session, principal, action):
    """The live, unused challenge row, checked at clock_timestamp(). One use is a database key (an act per
    challenge, a session per login challenge); the caller holds the memory lock, so two uses never race."""
    row = conn.execute(
        "SELECT payload, challenge FROM curator_challenge c WHERE id = %s AND action = %s "
        "AND session IS NOT DISTINCT FROM %s AND principal IS NOT DISTINCT FROM %s AND clock_timestamp() < expires_at "
        "AND NOT EXISTS (SELECT 1 FROM curator_act a WHERE a.challenge = c.id) "
        "AND NOT EXISTS (SELECT 1 FROM curator_session s WHERE s.login_challenge = c.id)",
        (cid, action, session, principal)).fetchone()
    if row is None:
        raise CeremonyRefused("challenge unknown, used, expired or of another session")
    payload, stored = row
    if challenge_of(payload) != bytes(stored):
        raise CeremonyRefused("the statement does not give its challenge")
    return payload, bytes(stored)


def _client_data(credential: dict, kind: str) -> dict:
    """The raw clientDataJSON checks that py_webauthn does not make: no cross-origin call and no iframe."""
    try:
        data = json.loads(unb64u(credential["response"]["clientDataJSON"]))
    except (KeyError, TypeError, ValueError):
        raise CeremonyRefused("malformed credential") from None
    if not isinstance(data, dict) or data.get("type") != kind:
        raise CeremonyRefused("wrong ceremony type")
    if data.get("crossOrigin") not in (None, False) or "topOrigin" in data:
        raise CeremonyRefused("cross-origin or framed ceremony")
    return data


def _reason(exc: Exception) -> str:
    text = str(exc)
    if "User verification" in text:
        return "user-verification-missing"
    if "sign count" in text:
        return "sign-count-regressed: the passkey counter did not increase"
    if "origin" in text.lower():
        return "wrong origin"
    if "RP ID" in text:
        return "wrong RP ID"
    return "the assertion does not verify"


# --- enrollment (owner) and registration (curator web) ----------------------------------------------------------

def enroll(conn, principal: str, *, created_by: str) -> tuple[str, str]:
    """(enrollment id, one-time code). The owner credential: it makes the person at the first enrollment."""
    if not (isinstance(principal, str) and authz.PRINCIPAL.match(principal) and principal.startswith("user:")):
        raise ValueError("a curator is a user:")
    code = b64u(secrets.token_bytes(16))
    eid = "en_" + secrets.token_hex(16)
    with conn.transaction():
        conn.execute("INSERT INTO curator_person (principal, user_handle) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                     (principal, secrets.token_bytes(32)))
        now = _now(conn)
        conn.execute("INSERT INTO curator_enrollment (id, principal, code_sha256, created_by, created_at, expires_at) "
                     f"VALUES (%s, %s, %s, %s, %s, %s::timestamptz + interval '{ENROLL_TTL}')",
                     (eid, principal, digest(code), created_by, now, now))
    return eid, code


def _new_session(conn, principal: str, login: str, *, login_challenge=None, ttl: str = SESSION_TTL) -> str:
    token = b64u(secrets.token_bytes(32))
    now = _now(conn)
    conn.execute("INSERT INTO curator_session (id_sha256, principal, login, login_challenge, created_at, expires_at) "
                 f"VALUES (%s, %s, %s, %s, %s, %s::timestamptz + interval '{ttl}')",
                 (digest(token), principal, login, login_challenge, now, now))
    return token


def enrollment_session(conn, code: str) -> tuple[str, str]:
    """(cookie value, principal) for a live, unused code. The session may only register, until the code expires."""
    if not isinstance(code, str) or not 1 <= len(code) <= 64:
        raise CeremonyRefused("unknown, used or expired code")
    row = conn.execute("SELECT principal, expires_at - clock_timestamp() FROM curator_enrollment e "
                       "WHERE code_sha256 = %s AND clock_timestamp() < expires_at "
                       "AND NOT EXISTS (SELECT 1 FROM passkey p WHERE p.enrollment = e.id)",
                       (digest(code),)).fetchone()
    if row is None:
        raise CeremonyRefused("unknown, used or expired code")
    token = _new_session(conn, row[0], "enrollment", ttl=f"{max(1, int(row[1].total_seconds()))} seconds")
    return token, row[0]


def _enrollment_of(conn, principal: str) -> str:
    row = conn.execute("SELECT id FROM curator_enrollment e WHERE principal = %s AND clock_timestamp() < expires_at "
                       "AND NOT EXISTS (SELECT 1 FROM passkey p WHERE p.enrollment = e.id) ORDER BY created_at DESC "
                       "LIMIT 1", (principal,)).fetchone()
    if row is None:
        raise CeremonyRefused("no live enrollment")
    return row[0]


def registration_options(conn, cfg: Config, session: bytes, principal: str) -> tuple[str, dict]:
    enrollment = _enrollment_of(conn, principal)
    handle = bytes(conn.execute("SELECT user_handle FROM curator_person WHERE principal = %s",
                                (principal,)).fetchone()[0])
    cid, _, challenge = _store(conn, cfg, session=session, principal=principal, action="register",
                               fields={"enrollment": enrollment, "user_handle": b64u(handle)})
    existing = [PublicKeyCredentialDescriptor(id=bytes(r[0])) for r in conn.execute(
        "SELECT credential_id FROM passkey WHERE principal = %s", (principal,)).fetchall()]
    options = webauthn.generate_registration_options(
        rp_id=cfg.rp_id, rp_name=cfg.rp_name, user_id=handle, user_name=principal.removeprefix("user:"),
        user_display_name=principal, challenge=challenge, timeout=TIMEOUT_MS, exclude_credentials=existing,
        authenticator_selection=AuthenticatorSelectionCriteria(resident_key=ResidentKeyRequirement.REQUIRED,
                                                               user_verification=UserVerificationRequirement.REQUIRED))
    return cid, json.loads(webauthn.options_to_json(options))


def register(conn, cfg: Config, session: bytes, principal: str, cid: str, credential: dict) -> dict:
    """Verify a registration with UV and insert the passkey. The database refuses an expired or used enrollment."""
    payload, challenge = _challenge(conn, cid, session=session, principal=principal, action="register")
    _client_data(credential, "webauthn.create")
    try:
        v = webauthn.verify_registration_response(credential=credential, expected_challenge=challenge,
                                                  expected_rp_id=cfg.rp_id, expected_origin=cfg.origin,
                                                  require_user_verification=True)
    except (InvalidRegistrationResponse, KeyError, TypeError, ValueError) as exc:
        raise CeremonyRefused(_reason(exc)) from None
    eligible = v.credential_device_type.value == "multi_device"
    conn.execute("INSERT INTO passkey (credential_id, principal, user_handle, enrollment, public_key, sign_count, "
                 "backup_eligible) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                 (v.credential_id, principal, unb64u(payload["user_handle"]), payload["enrollment"],
                  v.credential_public_key, v.sign_count, eligible))
    conn.execute("UPDATE curator_session SET ended_at = clock_timestamp() WHERE id_sha256 = %s", (session,))
    return {"credential_id": b64u(v.credential_id), "principal": principal, "backup_eligible": eligible}


# --- login and sessions -------------------------------------------------------------------------------------------

def login_options(conn, cfg: Config) -> tuple[str, dict]:
    cid, _, challenge = _store(conn, cfg, session=None, principal=None, action="login", fields={})
    options = webauthn.generate_authentication_options(rp_id=cfg.rp_id, challenge=challenge, timeout=TIMEOUT_MS,
                                                       user_verification=UserVerificationRequirement.REQUIRED)
    return cid, json.loads(webauthn.options_to_json(options))


def _assert(conn, cfg: Config, credential: dict, challenge: bytes, *, principal=None, need_handle: bool) -> tuple:
    """The common assertion checks (docs/25 §5.4 steps 4–6). Returns (principal, credential id, backed up)."""
    if not isinstance(credential, dict):
        raise CeremonyRefused("malformed credential")
    _client_data(credential, "webauthn.get")
    cred_id = unb64u(credential.get("rawId") or credential.get("id"))
    row = conn.execute("SELECT p.principal, p.public_key, p.sign_count, p.user_handle FROM passkey p "
                       "WHERE p.credential_id = %s AND p.revoked_at IS NULL FOR UPDATE", (cred_id,)).fetchone()
    if row is None or (principal is not None and row[0] != principal):
        raise CeremonyRefused("unknown or revoked passkey")
    owner, public_key, count, handle = row
    given = (credential.get("response") or {}).get("userHandle")
    if (need_handle and not given) or (given and unb64u(given) != bytes(handle)):
        raise CeremonyRefused("the passkey does not name this person")
    try:
        v = webauthn.verify_authentication_response(
            credential=credential, expected_challenge=challenge, expected_rp_id=cfg.rp_id, expected_origin=cfg.origin,
            credential_public_key=bytes(public_key), credential_current_sign_count=count,
            require_user_verification=True)
    except (InvalidAuthenticationResponse, KeyError, TypeError, ValueError) as exc:
        raise CeremonyRefused(_reason(exc)) from None
    if conn.execute("UPDATE passkey SET sign_count = %s WHERE credential_id = %s AND sign_count = %s",
                    (v.new_sign_count, cred_id, count)).rowcount != 1:
        raise CeremonyRefused("sign-count-regressed: the passkey counter did not increase")
    return owner, cred_id, v.credential_backed_up


def login(conn, cfg: Config, cid: str, credential: dict) -> tuple[str, str]:
    """(cookie value, principal). The assertion must carry the person's user handle."""
    _, challenge = _challenge(conn, cid, session=None, principal=None, action="login")
    principal, _, _ = _assert(conn, cfg, credential, challenge, need_handle=True)
    return _new_session(conn, principal, "passkey", login_challenge=cid), principal


def session(conn, token) -> tuple[bytes, str, str] | None:
    """(id digest, principal, login) of a live session, or None."""
    if not isinstance(token, str) or not token:
        return None
    row = conn.execute("SELECT id_sha256, principal, login FROM curator_session WHERE id_sha256 = %s "
                       "AND ended_at IS NULL AND clock_timestamp() < expires_at", (digest(token),)).fetchone()
    return (bytes(row[0]), row[1], row[2]) if row else None


def logout(conn, session_id: bytes) -> None:
    conn.execute("UPDATE curator_session SET ended_at = clock_timestamp() WHERE id_sha256 = %s AND ended_at IS NULL",
                 (session_id,))


# --- acts -----------------------------------------------------------------------------------------------------------

def act_options(conn, cfg: Config, session_id: bytes, principal: str, action: str, fields: dict) -> tuple[str, dict, dict]:
    """(challenge id, statement, WebAuthn request options) for one act of this person."""
    if action not in ACTIONS:
        raise ValueError(f"action must be one of {', '.join(ACTIONS)}")
    cid, payload, challenge = _store(conn, cfg, session=session_id, principal=principal, action=action, fields=fields)
    allowed = [PublicKeyCredentialDescriptor(id=bytes(r[0])) for r in conn.execute(
        "SELECT credential_id FROM passkey WHERE principal = %s AND revoked_at IS NULL", (principal,)).fetchall()]
    options = webauthn.generate_authentication_options(rp_id=cfg.rp_id, challenge=challenge, timeout=TIMEOUT_MS,
                                                       allow_credentials=allowed,
                                                       user_verification=UserVerificationRequirement.REQUIRED)
    return cid, payload, json.loads(webauthn.options_to_json(options))


@dataclass(frozen=True)
class Act:
    seq: int
    principal: str
    action: str
    payload: dict


def verify_act(conn, cfg: Config, session_id: bytes, principal: str, cid: str, credential: dict,
               shown_ms=None) -> Act:
    """docs/25 §5.4 steps 2–6 and the act row. The caller holds the transaction and the memory lock, and then
    writes the rows of the statement (step 7) in the same transaction."""
    if shown_ms is not None and not (isinstance(shown_ms, int) and 0 <= shown_ms <= 3_600_000):
        shown_ms = None
    row = conn.execute("SELECT action FROM curator_challenge WHERE id = %s", (cid,)).fetchone()
    if row is None or row[0] not in ACTIONS:
        raise CeremonyRefused("challenge unknown, used, expired or of another session")
    payload, challenge = _challenge(conn, cid, session=session_id, principal=principal, action=row[0])
    _, cred_id, backed_up = _assert(conn, cfg, credential, challenge, principal=principal, need_handle=False)
    response = credential["response"]
    seq = conn.execute("INSERT INTO curator_act (challenge, principal, action, credential_id, authenticator_data, "
                       "client_data_json, signature, backup_state, shown_ms) "
                       "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING seq",
                       (cid, principal, row[0], cred_id, unb64u(response["authenticatorData"]),
                        unb64u(response["clientDataJSON"]), unb64u(response["signature"]), backed_up,
                        shown_ms)).fetchone()[0]
    return Act(seq, principal, row[0], payload)


# --- the offline check (docs/25 §5.6) -------------------------------------------------------------------------------

def _standing_effects(conn, act: int, payload: dict) -> bool:
    want = sorted((i["ref"], i["to"], payload["reason"]) for i in payload.get("items", []))
    got = sorted(tuple(r) for r in conn.execute(
        "SELECT n.book || '@' || n.id, e.value, e.reason FROM standing_event e JOIN note n ON n.seq = e.note_seq "
        "WHERE e.act = %s", (act,)).fetchall())
    return want == got


EFFECTS = {"standing": _standing_effects}  # slices R and D add their actions


def verify_acts(conn, cfg: Config, since: int = 0) -> dict:
    """Check every stored act again: the statement gives the challenge, the assertion verifies with UV against the
    stored passkey, and the rows that name the act are exactly the ones its statement asks for."""
    rows = conn.execute(
        "SELECT a.seq, a.action, a.credential_id, a.authenticator_data, a.client_data_json, a.signature, c.payload, "
        "c.challenge, p.public_key FROM curator_act a JOIN curator_challenge c ON c.id = a.challenge "
        "JOIN passkey p ON p.credential_id = a.credential_id WHERE a.seq > %s ORDER BY a.seq", (since,)).fetchall()
    problems = []
    for seq, action, cred_id, auth_data, client_data, signature, payload, challenge, public_key in rows:
        if challenge_of(payload) != bytes(challenge):
            problems.append({"act": seq, "problem": "statement"})
            continue
        credential = {"id": b64u(bytes(cred_id)), "rawId": b64u(bytes(cred_id)), "type": "public-key",
                      "response": {"clientDataJSON": b64u(bytes(client_data)),
                                   "authenticatorData": b64u(bytes(auth_data)), "signature": b64u(bytes(signature))}}
        try:
            _client_data(credential, "webauthn.get")
            webauthn.verify_authentication_response(
                credential=credential, expected_challenge=bytes(challenge), expected_rp_id=cfg.rp_id,
                expected_origin=cfg.origin, credential_public_key=bytes(public_key), credential_current_sign_count=0,
                require_user_verification=True)
        except (CeremonyRefused, InvalidAuthenticationResponse, ValueError):
            problems.append({"act": seq, "problem": "signature"})
            continue
        check = EFFECTS.get(action)
        if check is None:
            problems.append({"act": seq, "problem": f"no effect check for {action}"})
        elif not check(conn, seq, payload):
            problems.append({"act": seq, "problem": "effects"})
    return {"acts": len(rows), "problems": problems}
