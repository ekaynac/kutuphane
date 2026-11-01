"""AT-11 (Core side; the LLMDAP side waits for #223): only verified token claims decide who is calling."""
import json
import os
import time
from pathlib import Path

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


def test_hmac_with_public_key_is_rejected(verifier, keys):  # algorithm confusion
    from cryptography.hazmat.primitives import serialization
    pem = keys[0].public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    now = int(time.time())
    claims = {"iss": ISS, "aud": AUD, "sub": "ayse", "iat": now, "exp": now + 300}
    import hmac, hashlib, base64
    def b64(b):
        return base64.urlsafe_b64encode(b).rstrip(b"=").decode()
    head = b64(json.dumps({"alg": "HS256", "typ": "JWT", "kid": "k1"}).encode())
    body = b64(json.dumps(claims).encode())
    sig = b64(hmac.new(pem, f"{head}.{body}".encode(), hashlib.sha256).digest())
    with pytest.raises(AuthenticationError):
        verifier.verify(f"{head}.{body}.{sig}")


@pytest.mark.parametrize("bad", [
    dict(exp=None), dict(iat=None),                                   # required claims missing
    dict(nbf=int(time.time()) + 3600),                                # not valid yet
    dict(iat=int(time.time()) + 3600),                                # issued in the future
])
def test_missing_or_future_time_claims(verifier, keys, bad):
    with pytest.raises(AuthenticationError):
        verifier.verify(token(keys, **bad))


def test_client_credentials_token_is_an_agent_with_its_client(verifier, keys):  # docs/24 T37, §12.4
    actor = verifier.verify(token(keys, sub="adc", client_id="adc-orchestrator", azp="other",
                                  **{"kutuphane/principal_type": "agent"}))
    assert (actor.principal, actor.on_behalf_of, actor.client_id) == ("agent:adc", None, "adc-orchestrator")


def test_token_exchange_token_acts_for_the_user_and_keeps_azp(verifier, keys):  # T37: RFC 8693, `azp` fallback
    actor = verifier.verify(token(keys, act={"sub": "adc"}, azp="adc-orchestrator"))
    assert (actor.principal, actor.on_behalf_of, actor.client_id) == ("agent:adc", "user:ayse", "adc-orchestrator")
    assert verifier.verify(token(keys)).client_id is None


@pytest.mark.parametrize("bad", [dict(client_id=7), dict(client_id=""), dict(azp=["a"])])
def test_malformed_client_id_is_refused(verifier, keys, bad):
    with pytest.raises(AuthenticationError):
        verifier.verify(token(keys, **bad))


@pytest.mark.parametrize("iss", [
    ISS + "/",                                        # trailing slash
    "https://IDP.test/realms/kurum",                  # host case
    "https://idp.test:443/realms/kurum",              # default port
    "https://idp.test/realms/kur%75m",                # percent-encoding
    "https://idp.test/realms/kuru",                   # prefix of ours
    "https://idp.test/realms/kurum2",                 # ours is a prefix
    "https://idp.test/realms",                        # ours contains it (PyJWT 2.10.0, CVE-2024-53861)
])
def test_issuer_is_compared_exactly(verifier, keys, iss):  # docs/24 §12.5: RFC 3986 §6.2.1, no normalization
    machine = dict(sub="adc", client_id="adc", **{"kutuphane/principal_type": "agent"})  # client credentials
    assert verifier.verify(token(keys, **machine)).principal == "agent:adc"
    with pytest.raises(AuthenticationError, match="issuer"):
        verifier.verify(token(keys, iss=iss, **machine))


def test_a_cimd_client_id_url_is_accepted_as_it_is(verifier, keys):  # docs/24 §12.6
    url = "https://adc.example/oauth/client-metadata.json"
    assert verifier.verify(token(keys, act={"sub": "adc"}, client_id=url)).client_id == url


def test_dev_token_carries_client_id(monkeypatch, tmp_path):
    from kutuphane import devauth
    monkeypatch.setenv("KUTUPHANE_DEV", "1")
    paths = devauth.make_keys(tmp_path / "keys")
    dev = Verifier.from_files(ISS, AUD, Path(paths["jwks"]))
    raw = devauth.make_token(Path(paths["private_key"]), issuer=ISS, audience=AUD, sub="adc", agent=True,
                             client_id="adc-orchestrator")
    actor = dev.verify(raw)
    assert (actor.principal, actor.client_id) == ("agent:adc", "adc-orchestrator")


# --- #157: more than one issuer, each bound to principal prefixes -------------------------------------------------

ISS_B, AUD_B, PREFIXES_B = "https://inframedic.test/auth", "kutuphane-im", ["user:inframedic.", "agent:inframedic-"]


def _jwks(tmp_path, key, name: str):
    path = tmp_path / name
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
    path.write_text(json.dumps({"keys": [{**jwk, "kid": "k1", "use": "sig", "alg": "RS256"}]}))
    return path


def _issuers(tmp_path, keys, monkeypatch, **extra):
    entry = {"issuer": ISS_B, "audience": AUD_B, "jwks": str(_jwks(tmp_path, keys[1], "b.json")),
             "principal_prefixes": PREFIXES_B, **extra}
    path = tmp_path / "issuers.json"
    path.write_text(json.dumps([entry]))
    monkeypatch.setenv("KUTUPHANE_OIDC_ISSUER", ISS)
    monkeypatch.setenv("KUTUPHANE_OIDC_AUDIENCE", AUD)
    monkeypatch.setenv("KUTUPHANE_OIDC_JWKS", str(_jwks(tmp_path, keys[0], "a.json")))
    monkeypatch.setenv("KUTUPHANE_OIDC_ISSUERS", str(path))
    return path


def b_token(keys, **claims):
    return token(keys, key=1, **{"iss": ISS_B, "aud": AUD_B, **claims})


@pytest.fixture
def two(keys, tmp_path, monkeypatch):
    _issuers(tmp_path, keys, monkeypatch)
    return Verifier.from_env()


def test_two_issuers_on_one_verifier(two, keys):
    assert two.verify(token(keys)).principal == "user:ayse"                                  # the primary, as before
    assert two.verify(b_token(keys, sub="inframedic.ayse")).principal == "user:inframedic.ayse"
    agent = two.verify(b_token(keys, sub="inframedic-triage", **{"kutuphane/principal_type": "agent"}))
    assert agent.principal == "agent:inframedic-triage"
    acting = two.verify(b_token(keys, sub="inframedic.ayse", act={"sub": "inframedic-triage"}))
    assert (acting.principal, acting.on_behalf_of) == ("agent:inframedic-triage", "user:inframedic.ayse")


@pytest.mark.parametrize("make", [
    lambda k: b_token(k, sub="ayse"),                                           # B names a primary user
    lambda k: b_token(k, sub="inframedic.ayse", act={"sub": "kobra-7"}),        # B names a primary agent
    lambda k: b_token(k, sub="ayse", act={"sub": "inframedic-triage"}),         # B acts for a primary user
    lambda k: b_token(k, sub="inframedic-triage"),                              # the agent prefix, used for a user
    lambda k: token(k, sub="inframedic.ayse"),                                  # the primary names a B user
    lambda k: token(k, act={"sub": "inframedic-triage"}),                       # the primary names a B agent
])
def test_a_cross_prefix_token_is_refused(two, keys, make):
    with pytest.raises(AuthenticationError, match="may not name"):
        two.verify(make(keys))


@pytest.mark.parametrize("make", [
    lambda k: token(k, key=1, iss=ISS_B, aud=AUD, sub="inframedic.ayse"),       # B with the primary's audience
    lambda k: token(k, key=0, iss=ISS_B, aud=AUD_B, sub="inframedic.ayse"),     # B's issuer, the primary's key
    lambda k: token(k, key=1, sub="ayse"),                                      # the primary's issuer, B's key
    lambda k: token(k, key=1, iss=ISS_B + "/", aud=AUD_B, sub="inframedic.ayse"),  # not exactly B's issuer
])
def test_each_issuer_keeps_its_own_key_audience_and_exact_name(two, keys, make):
    with pytest.raises(AuthenticationError):
        two.verify(make(keys))


@pytest.mark.parametrize("change", [
    {"principal_prefixes": []},                                     # an issuer with no prefix would own everything
    {"principal_prefixes": ["role:inframedic."]},                   # roles are Kütüphane's, never a token's
    {"principal_prefixes": ["user:"]},                              # a whole kind
    {"principal_prefixes": ["user:Inframedic."]},                   # not the principal alphabet
    {"issuer": ISS},                                                # the primary again
    {"audience": ""},
    {"curate": "yes"},
    {"groups": ["x"]},                                              # unknown key
])
def test_a_bad_issuer_config_stops_the_start(keys, tmp_path, monkeypatch, change):
    path = _issuers(tmp_path, keys, monkeypatch)
    entry = {**json.loads(path.read_text())[0], **change}
    path.write_text(json.dumps([entry]))
    with pytest.raises(RuntimeError, match="KUTUPHANE_OIDC_ISSUERS"):
        Verifier.from_env()


def test_two_extra_issuers_may_not_share_a_prefix(keys, tmp_path, monkeypatch):
    path = _issuers(tmp_path, keys, monkeypatch)
    entry = json.loads(path.read_text())[0]
    path.write_text(json.dumps([entry, {**entry, "issuer": "https://other.test",
                                        "principal_prefixes": ["user:inframedic.ops."]}]))
    with pytest.raises(RuntimeError, match="overlap"):
        Verifier.from_env()


def test_curate_is_refused_to_another_issuers_principals_by_default(conn, keys, tmp_path, monkeypatch, capsys):
    from kutuphane import cli, identity
    path = _issuers(tmp_path, keys, monkeypatch)
    with pytest.raises(authz.AuthzError, match="curate"):
        identity.refuse_curate("user:inframedic.ayse")
    identity.refuse_curate("user:ayse")                                       # the primary's people: as before
    monkeypatch.setenv("KUTUPHANE_DSN", os.environ["KUTUPHANE_TEST_DSN"])
    monkeypatch.setenv("KUTUPHANE_CURATOR_DSN", os.environ["KUTUPHANE_TEST_DSN"])
    assert cli.main(["grant", "book:kitap", "curate", "user:inframedic.ayse"]) != 0
    assert "curate" in capsys.readouterr().err
    assert not conn.execute("SELECT 1 FROM grant_tuple WHERE subject = 'user:inframedic.ayse'").fetchone()
    assert cli.main(["grant", "book:kitap", "read", "user:inframedic.ayse"]) == 0     # other modes: as before
    path.write_text(json.dumps([{**json.loads(path.read_text())[0], "curate": True}]))  # explicitly configured
    identity.refuse_curate("user:inframedic.ayse")
    assert cli.main(["grant", "book:kitap", "curate", "user:inframedic.ayse"]) == 0
