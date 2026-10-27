"""A software WebAuthn authenticator for tests (docs/25 §12): real keys and real signatures, no mock of py_webauthn.

It answers `navigator.credentials.create/get` options in the JSON form that `webauthn.options_to_json` gives, and
returns the JSON form of a `PublicKeyCredential` that a browser sends. Every field that the server must check is a
parameter: the origin, `crossOrigin`, `topOrigin`, the client data type, the UP/UV/BE/BS flags and the counter.
"""
import base64
import hashlib
import json
import secrets
import struct

import cbor2
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed25519

UP, UV, BE, BS, AT = 0x01, 0x04, 0x08, 0x10, 0x40


def b64u(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def unb64u(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


class Credential:
    def __init__(self, alg: str, user_handle: bytes):
        self.id = secrets.token_bytes(32)
        self.alg = alg
        self.user_handle = user_handle
        self.counter = 0
        if alg == "es256":
            self.key = ec.generate_private_key(ec.SECP256R1())
            nums = self.key.public_key().public_numbers()
            self.cose = {1: 2, 3: -7, -1: 1, -2: nums.x.to_bytes(32, "big"), -3: nums.y.to_bytes(32, "big")}
        else:
            self.key = ed25519.Ed25519PrivateKey.generate()
            raw = self.key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
            self.cose = {1: 1, 3: -8, -1: 6, -2: raw}

    def sign(self, data: bytes) -> bytes:
        if self.alg == "es256":
            return self.key.sign(data, ec.ECDSA(hashes.SHA256()))
        return self.key.sign(data)


class SoftAuthenticator:
    """One authenticator. `counter_step` 0 behaves as a synced passkey (the counter stays 0)."""

    def __init__(self, origin: str, *, alg: str = "es256", synced: bool = True, counter_step: int = 0):
        self.origin = origin
        self.alg = alg
        self.synced = synced
        self.counter_step = counter_step
        self.credentials: dict[bytes, Credential] = {}

    def _client_data(self, kind: str, challenge: str, origin, cross_origin, top_origin) -> bytes:
        data = {"type": kind, "challenge": challenge, "origin": origin or self.origin}
        if cross_origin is not None:
            data["crossOrigin"] = cross_origin
        if top_origin is not None:
            data["topOrigin"] = top_origin
        return json.dumps(data, separators=(",", ":")).encode()

    def _flags(self, uv: bool, attested: bool = False) -> int:
        flags = UP | (UV if uv else 0) | ((BE | BS) if self.synced else 0)
        return flags | (AT if attested else 0)

    def create(self, options: dict, *, origin=None, uv=True, cross_origin=False, top_origin=None,
               kind="webauthn.create", rp_id=None) -> dict:
        cred = Credential(self.alg, unb64u(options["user"]["id"]))
        self.credentials[cred.id] = cred
        rp_hash = hashlib.sha256((rp_id or options["rp"]["id"]).encode()).digest()
        attested = bytes(16) + struct.pack(">H", len(cred.id)) + cred.id + cbor2.dumps(cred.cose)
        auth_data = rp_hash + bytes([self._flags(uv, attested=True)]) + struct.pack(">I", 0) + attested
        client_data = self._client_data(kind, options["challenge"], origin, cross_origin, top_origin)
        attestation = cbor2.dumps({"fmt": "none", "attStmt": {}, "authData": auth_data})
        return {"id": b64u(cred.id), "rawId": b64u(cred.id), "type": "public-key",
                "response": {"clientDataJSON": b64u(client_data), "attestationObject": b64u(attestation),
                             "transports": ["internal"]},
                "clientExtensionResults": {}, "authenticatorAttachment": "platform"}

    def get(self, options: dict, *, credential: bytes | None = None, origin=None, uv=True, cross_origin=False,
            top_origin=None, kind="webauthn.get", user_handle=True, counter: int | None = None, rp_id=None) -> dict:
        allowed = [unb64u(c["id"]) for c in options.get("allowCredentials") or []]
        cid = credential or next((c for c in allowed if c in self.credentials), None) or next(iter(self.credentials))
        cred = self.credentials[cid]
        cred.counter += self.counter_step
        count = cred.counter if counter is None else counter
        rp_hash = hashlib.sha256((rp_id or options["rpId"]).encode()).digest()
        auth_data = rp_hash + bytes([self._flags(uv)]) + struct.pack(">I", count)
        client_data = self._client_data(kind, options["challenge"], origin, cross_origin, top_origin)
        signature = cred.sign(auth_data + hashlib.sha256(client_data).digest())
        response = {"clientDataJSON": b64u(client_data), "authenticatorData": b64u(auth_data),
                    "signature": b64u(signature)}
        if user_handle:
            response["userHandle"] = b64u(cred.user_handle if user_handle is True else user_handle)
        return {"id": b64u(cid), "rawId": b64u(cid), "type": "public-key", "response": response,
                "clientExtensionResults": {}, "authenticatorAttachment": "platform"}
