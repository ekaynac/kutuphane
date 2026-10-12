"""The only way Kütüphane reaches a model (D3): the LLMDAP bridge. Stdlib HTTP, no SDKs.

Today the bridge trusts a shared secret plus subject headers; LLMDAP #223 replaces that with OIDC. Every call
carries our correlation id; LLMDAP answers with its namespaced form, which we store so the unified audit can join
both logs (AT-09). Every attempt is recorded in `model_call`, including failures.
"""
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

from .gate import Actor

ENV = {"url": "KUTUPHANE_LLMDAP_URL", "route": "KUTUPHANE_LLMDAP_ROUTE", "secret": "KUTUPHANE_LLMDAP_TRUST_SECRET"}
TIMEOUT_SECONDS = 120
CHAT_PATH = "/v1/chat/completions"  # openai schema on the bridge route


class EgressError(RuntimeError):
    pass


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Never follow redirects: they would carry the trust secret to another host."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_OPENER = urllib.request.build_opener(_NoRedirect)


@dataclass(frozen=True)
class Bridge:
    url: str
    route: str
    secret: str

    @classmethod
    def from_env(cls) -> "Bridge":
        missing = [v for v in ENV.values() if not os.environ.get(v)]
        if missing:
            raise RuntimeError(f"LLMDAP not configured: set {', '.join(missing)}")
        return cls(os.environ[ENV["url"]].rstrip("/"), os.environ[ENV["route"]], os.environ[ENV["secret"]])

    def __post_init__(self):
        if urllib.parse.urlsplit(self.url).scheme not in ("http", "https"):
            raise RuntimeError("LLMDAP url must be http(s)")
        if not self.route.replace("-", "").replace("_", "").isalnum():
            raise RuntimeError("LLMDAP route must be a plain name")


def _record(conn, actor: Actor, bridge: Bridge, model: str, status, derived, error) -> None:
    conn.execute("INSERT INTO model_call (correlation_id, derived_correlation_id, principal, on_behalf_of, route, "
                 "model, http_status, error) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                 (actor.correlation_id, derived, actor.principal, actor.on_behalf_of, bridge.route, model, status,
                  error))


def chat(conn, bridge: Bridge, actor: Actor, *, model: str, messages: list[dict], purpose: str | None = None) -> dict:
    headers = {
        "content-type": "application/json",
        "x-llmdap-auth": bridge.secret,
        "x-llmdap-user": actor.principal,
        "x-llmdap-correlation-id": actor.correlation_id,
    }
    if actor.on_behalf_of:
        headers["x-llmdap-for-subject"] = actor.on_behalf_of
    if purpose:
        headers["x-llmdap-purpose"] = purpose
    body = json.dumps({"model": model, "messages": messages, "stream": False}).encode()
    request = urllib.request.Request(f"{bridge.url}/bridge/{bridge.route}{CHAT_PATH}", data=body, headers=headers,
                                     method="POST")
    try:
        with _OPENER.open(request, timeout=TIMEOUT_SECONDS) as resp:
            derived = resp.headers.get("x-llmdap-correlation-id-derived")
            payload = json.loads(resp.read())
            _record(conn, actor, bridge, model, resp.status, derived, None)
            return payload
    except urllib.error.HTTPError as exc:
        derived = exc.headers.get("x-llmdap-correlation-id-derived") if exc.headers else None
        _record(conn, actor, bridge, model, exc.code, derived, f"http {exc.code}")
        raise EgressError(f"LLMDAP refused the call (HTTP {exc.code})") from None
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        _record(conn, actor, bridge, model, None, None, type(exc).__name__)
        raise EgressError(f"LLMDAP unreachable or invalid answer: {type(exc).__name__}") from None
