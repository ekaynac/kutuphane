"""G13 (docs/18): the CLI on the host reads no compose file. Every `KUTUPHANE_*` value that a compose file gives
Core has the same default in the code, or the code stops with a message that names the setting. A route class is
never defaulted: `local` skips the egress check, so a wrong default would send `local_only` text to a cloud route."""
import json
import os
import re
from pathlib import Path

import jwt
import pytest
import yaml
from cryptography.hazmat.primitives.asymmetric import ec

from kutuphane import coderepo, confirm, curatorweb, db, identity, llmdap

ROOT = Path(__file__).resolve().parent.parent
COMPOSE_FILES = ("compose.yaml", "deploy/compose.full.yaml")
URL, KEY, ROUTE = "http://127.0.0.1:9", "llmdap_sk_" + "k" * 43, "emb"
JWKS = json.dumps({"keys": [{**json.loads(jwt.algorithms.ECAlgorithm.to_jwk(ec.generate_private_key(ec.SECP256R1())
                                                                            .public_key())), "kid": "k1"}]})


def compose_values() -> dict[str, set[str]]:
    """The values that the compose files give, after `${X:-default}`; a `${X:?…}` value has no default."""
    out: dict[str, set[str]] = {}
    for name in COMPOSE_FILES:
        for svc in yaml.safe_load((ROOT / name).read_text(encoding="utf-8"))["services"].values():
            for var, raw in (svc.get("environment") or {}).items():
                if not var.startswith("KUTUPHANE_") or re.fullmatch(r"\$\{\w+:\?[^}]*\}", str(raw)):
                    continue
                value = re.sub(r"\$\{\w+:-([^}]*)\}", r"\1", str(raw))
                if value:
                    out.setdefault(var, set()).add(value)
    return out


SAME_DEFAULT = {"KUTUPHANE_OIDC_AUDIENCE": identity.DEFAULT_AUDIENCE, "KUTUPHANE_CONFIRM_HOURS": str(confirm.DEFAULT_HOURS)}
ROUTES = {env["route_class"]: env for env in (llmdap.ENV, llmdap.EMBED_ENV, llmdap.RERANK_ENV)}
# The full stack's local-models routes and models: compose defaults, never CLI defaults. Without them the host CLI uses
# no such route (operations.md); no gate depends on them, unlike the route classes.
LOCAL_MODELS = {"KUTUPHANE_LLMDAP_ROUTE", "KUTUPHANE_ANSWER_MODEL", "KUTUPHANE_LLMDAP_EMBED_ROUTE",
                "KUTUPHANE_EMBED_MODEL", "KUTUPHANE_LLMDAP_RERANK_ROUTE", "KUTUPHANE_RERANK_MODEL"}


def _bridge(m, class_env):
    env = ROUTES[class_env]
    for var, value in ((llmdap.ENV["url"], URL), (llmdap.ENV["key"], KEY), (env["route"], ROUTE)):
        m.setenv(var, value)
    return llmdap.Bridge.from_env(env["route"], class_env)


def _verifier(m, tmp_path):
    m.setenv(identity.ENV["issuer"], "https://idp.test")
    return identity.Verifier.from_env()


# The compose value is a container address or path, or a route class: the host sets its own, else this stops.
NAMED = {
    db.DSN_ENV: lambda m, tmp_path: db.connect(),
    curatorweb.DSN_ENV: lambda m, tmp_path: curatorweb.app_from_env(),
    identity.ENV["jwks"]: _verifier,
    coderepo.ROOTS_ENV: lambda m, tmp_path: coderepo.check_git_dir(os.path.realpath(tmp_path)),
    llmdap.ENV["url"]: lambda m, tmp_path: (m.setenv(llmdap.ENV["key"], KEY), m.setenv(llmdap.ENV["route"], ROUTE),
                                            m.setenv(llmdap.ENV["route_class"], "local"), llmdap.Bridge.from_env()),
    **{class_env: (lambda c: lambda m, tmp_path: _bridge(m, c))(class_env) for class_env in ROUTES},
}


@pytest.fixture
def bare_env(monkeypatch):
    for var in {*compose_values(), *SAME_DEFAULT, *NAMED, *llmdap.ENV.values(), *llmdap.EMBED_ENV.values(),
                *llmdap.RERANK_ENV.values(), *identity.ENV.values()}:
        monkeypatch.delenv(var, raising=False)
    return monkeypatch


def test_every_compose_value_is_the_cli_default_or_named(bare_env, tmp_path):  # G13
    values = compose_values()
    assert set(values) == set(SAME_DEFAULT) | set(NAMED) | LOCAL_MODELS
    for var, default in SAME_DEFAULT.items():
        assert values[var] == {default}, var
    for var, trigger in NAMED.items():
        with bare_env.context() as m, pytest.raises((RuntimeError, ValueError)) as err:
            trigger(m, tmp_path)
        assert var in str(err.value), (var, str(err.value))


@pytest.mark.parametrize("value", [None, ""])  # compose `${X:-default}` reads an empty value as not set
def test_compose_defaults_are_the_cli_defaults(bare_env, tmp_path, value):  # G13
    (tmp_path / "jwks.json").write_text(JWKS, encoding="utf-8")
    bare_env.setenv(identity.ENV["jwks"], str(tmp_path / "jwks.json"))
    for var in SAME_DEFAULT:
        if value is not None:
            bare_env.setenv(var, value)
    assert _verifier(bare_env, tmp_path).audience == "kutuphane"
    assert confirm.hours() == 24


@pytest.mark.parametrize("class_env", list(ROUTES))
def test_a_route_class_is_never_defaulted(bare_env, class_env):  # G13: no default can loosen the egress gate
    with pytest.raises(RuntimeError) as err:
        _bridge(bare_env, class_env)
    message = str(err.value)
    assert f"set {class_env}" in message and "local or cloud" in message and "compose.full.yaml sets local" in message
    bare_env.setenv(class_env, "onprem")
    with pytest.raises(RuntimeError, match=f"{class_env} must be local or cloud"):
        _bridge(bare_env, class_env)
    bare_env.setenv(class_env, "cloud")
    assert _bridge(bare_env, class_env).route_class == "cloud"
