"""AT-11 (Core side; the LLMDAP side waits for #223): only verified token claims decide who is calling."""
import json
import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from kutuphane import authz
from kutuphane.identity import AuthenticationError, Verifier

ISS, AUD = "https://idp.test/realms/kurum", "kutuphane"


@pytest.fixture(scope="module")
def keys():
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return private, other


@pytest.fixture
def verifier(keys, tmp_path):
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(keys[0].public_key()))
    jwks = tmp_path / "jwks.json"
    jwks.write_text(json.dumps({"keys": [{**jwk, "kid": "k1", "use": "sig", "alg": "RS256"}]}))
    return Verifier.from_files(ISS, AUD, jwks)


def token(keys, *, key=0, kid="k1", alg="RS256", **claims):
    now = int(time.time())
    body = {"iss": ISS, "aud": AUD, "sub": "ayse", "iat": now, "exp": now + 300, **claims}
    body = {k: v for k, v in body.items() if v is not None}
    return jwt.encode(body, keys[key], algorithm=alg, headers={"kid": kid})


def test_user_token(verifier, keys):
    actor = verifier.verify(token(keys))
    assert (actor.principal, actor.on_behalf_of) == ("user:ayse", None)


def test_agent_token(verifier, keys):
    actor = verifier.verify(token(keys, sub="kobra-7", **{"kutuphane/principal_type": "agent"}))
    assert actor.principal == "agent:kobra-7"


def test_delegated_token_uses_rfc8693_actor_claim(verifier, keys):
    actor = verifier.verify(token(keys, act={"sub": "kobra-7"}))
    assert (actor.principal, actor.on_behalf_of) == ("agent:kobra-7", "user:ayse")


def test_email_subject_maps_to_principal(verifier, keys):
    assert verifier.verify(token(keys, sub="ayse@kurum.local")).principal == "user:ayse@kurum.local"


@pytest.mark.parametrize("sub", ["Ayse", "AYSE@kurum.local", "ayşe", "İrem"])
def test_subjects_are_not_normalized_into_collisions(verifier, keys, sub):
    with pytest.raises(AuthenticationError):
        verifier.verify(token(keys, sub=sub))


@pytest.mark.parametrize("bad", [
    dict(exp=int(time.time()) - 120),               # expired beyond leeway
    dict(iss="https://evil.test"),                   # wrong issuer
    dict(aud="baska-servis"),                        # wrong audience
    dict(sub=None),                                  # no subject
    dict(act={"sub": "a", "act": {"sub": "b"}}),     # two-level delegation
    dict(sub="ayse\n"),                              # newline smuggling
    dict(**{"kutuphane/principal_type": "admin"}),   # unknown kind
])
def test_rejected_claims(verifier, keys, bad):
    with pytest.raises(AuthenticationError):
        verifier.verify(token(keys, **bad))


def test_wrong_key_unknown_kid_and_tampering(verifier, keys):
    with pytest.raises(AuthenticationError):
        verifier.verify(token(keys, key=1))          # signed by someone else
    with pytest.raises(AuthenticationError):
        verifier.verify(token(keys, kid="k9"))
    good = token(keys)
    head, body, sig = good.split(".")
    forged = jwt.utils.base64url_encode(json.dumps({**jwt.decode(good, options={"verify_signature": False}),
                                                    "sub": "mehmet"}).encode()).decode()
    with pytest.raises(AuthenticationError):
        verifier.verify(f"{head}.{forged}.{sig}")


def test_alg_none_and_hmac_confusion_rejected(verifier, keys):
    now = int(time.time())
    claims = {"iss": ISS, "aud": AUD, "sub": "ayse", "iat": now, "exp": now + 300}
    unsigned = jwt.encode(claims, None, algorithm="none", headers={"kid": "k1"})
    with pytest.raises(AuthenticationError):
        verifier.verify(unsigned)
    with pytest.raises(AuthenticationError):
        verifier.verify("")


def test_principal_pattern_rejects_trailing_newline():
    assert not authz.PRINCIPAL.match("user:ayse\n")
    assert not authz.OBJECT.match("book:kitap\n")
