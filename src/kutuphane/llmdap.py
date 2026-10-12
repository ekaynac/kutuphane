"""The only way Kütüphane reaches a model (D3): the LLMDAP bridge. Stdlib HTTP, no SDKs.

Today the bridge trusts a shared secret plus subject headers; LLMDAP #223 replaces that with OIDC. Every call
carries our correlation id; LLMDAP answers with its namespaced form, which we store so the unified audit can join
both logs (AT-09). Every attempt is recorded in `model_call`, including failures.
"""
import http.client
import json
import os
import uuid
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

from .gate import Actor

ENV = {"url": "KUTUPHANE_LLMDAP_URL", "route": "KUTUPHANE_LLMDAP_ROUTE", "secret": "KUTUPHANE_LLMDAP_TRUST_SECRET",
       "route_class": "KUTUPHANE_LLMDAP_ROUTE_CLASS"}
TIMEOUT_SECONDS = 120
CHAT_PATH = "/v1/chat/completions"  # openai schema on the bridge route


class EgressError(RuntimeError):
    pass


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Never follow redirects: they would carry the trust secret to another host."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_OPENER = urllib.request.build_opener(_NoRedirect)


ROUTE_CLASSES = ("local", "cloud")


@dataclass(frozen=True)
class Bridge:
    url: str
    route: str
    secret: str
    route_class: str  # operator-declared: does this route keep data on premises ("local") or not ("cloud")?

    @classmethod
    def from_env(cls) -> "Bridge":
        missing = [v for v in ENV.values() if not os.environ.get(v)]
        if missing:
            raise RuntimeError(f"LLMDAP not configured: set {', '.join(missing)}")
        return cls(os.environ[ENV["url"]].rstrip("/"), os.environ[ENV["route"]], os.environ[ENV["secret"]],
                   os.environ[ENV["route_class"]])

    def __post_init__(self):
        if urllib.parse.urlsplit(self.url).scheme not in ("http", "https"):
            raise RuntimeError("LLMDAP url must be http(s)")
        if not self.route.replace("-", "").replace("_", "").isalnum():
            raise RuntimeError("LLMDAP route must be a plain name")
        if self.route_class not in ROUTE_CLASSES:
            raise RuntimeError(f"LLMDAP route class must be one of {', '.join(ROUTE_CLASSES)}")


def _record(conn, actor: Actor, bridge: Bridge, call_id: str, model: str, books, status, derived, error) -> None:
    conn.execute("INSERT INTO model_call (correlation_id, call_id, derived_correlation_id, principal, on_behalf_of, "
                 "route, model, http_status, error, source_books) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                 (actor.correlation_id, call_id, derived, actor.principal, actor.on_behalf_of, bridge.route, model,
                  status, error, list(books)))


def _check_egress(conn, bridge: Bridge, books: list[str]) -> None:
    """Content of a `local_only` book never goes to a cloud route (E5 egress, D24). Policies are read now."""
    if bridge.route_class == "local" or not books:
        return
    rows = conn.execute("SELECT b.slug, p.doc->>'egress' FROM book b JOIN policy_version p ON p.id = b.current_policy "
                        "WHERE b.slug = ANY(%s)", (list(books),)).fetchall()
    known = {slug: egress for slug, egress in rows}
    blocked = sorted(b for b in books if known.get(b) != "cloud_ok")  # unknown books are blocked too
    if blocked:
        raise EgressError(f"egress policy forbids sending {', '.join(blocked)} to cloud route {bridge.route}")


def chat(conn, bridge: Bridge, actor: Actor, *, model: str, messages: list[dict], source_books: list[str],
         purpose: str | None = None) -> dict:
    """`source_books`: every book whose content is in `messages` (may be empty). Required, so no caller forgets."""
    call_id = f"{actor.correlation_id}.{uuid.uuid4().hex[:12]}"
    try:
        _check_egress(conn, bridge, source_books)
    except EgressError as exc:
        _record(conn, actor, bridge, call_id, model, source_books, None, None, "egress policy")
        raise exc from None
    headers = {
        "content-type": "application/json",
        "x-llmdap-auth": bridge.secret,
        "x-llmdap-user": actor.principal,
        "x-llmdap-correlation-id": call_id,
    }
    if actor.on_behalf_of:
        headers["x-llmdap-for-subject"] = actor.on_behalf_of
    if purpose:
        headers["x-llmdap-purpose"] = purpose
    body = json.dumps({"model": model, "messages": messages, "stream": False}).encode()
    request = urllib.request.Request(f"{bridge.url}/bridge/{bridge.route}{CHAT_PATH}", data=body, headers=headers,
                                     method="POST")
    status = derived = None
    try:
        with _OPENER.open(request, timeout=TIMEOUT_SECONDS) as resp:
            status, derived = resp.status, resp.headers.get("x-llmdap-correlation-id-derived")
            payload = json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        derived = exc.headers.get("x-llmdap-correlation-id-derived") if exc.headers else None
        _record(conn, actor, bridge, call_id, model, source_books, exc.code, derived, f"http {exc.code}")
        raise EgressError(f"LLMDAP refused the call (HTTP {exc.code})") from None
    except (OSError, http.client.HTTPException, ValueError) as exc:  # network, truncated body, invalid JSON
        _record(conn, actor, bridge, call_id, model, source_books, status, derived, type(exc).__name__)
        raise EgressError(f"LLMDAP unreachable or invalid answer: {type(exc).__name__}") from None
    _record(conn, actor, bridge, call_id, model, source_books, status, derived, None)
    return payload
