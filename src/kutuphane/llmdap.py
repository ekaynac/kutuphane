"""The only way Kütüphane reaches a model (D3): the LLMDAP bridge, for chat and for embeddings (D17, #222).
Stdlib HTTP, no SDKs.

Core authenticates as its own LLMDAP subject with a subject key (`GATEWAY_AUTH_MODE=subject-keys`, LLMDAP #228):
the credential names the subject, so no header can claim another one. The person served (the user, or the user an
agent acts for) travels as the `x-llmdap-for-subject` attribution label; who exactly called — agent included — is in
our own `model_call`, joined by the call id (AT-09). LLMDAP answers with its namespaced form of that id, which we
store. Every attempt is recorded in `model_call`, including failures.
"""
import http.client
import json
import math
import os
import uuid
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

from .gate import Actor

ENV = {"url": "KUTUPHANE_LLMDAP_URL", "key": "KUTUPHANE_LLMDAP_KEY", "route": "KUTUPHANE_LLMDAP_ROUTE",
       "route_class": "KUTUPHANE_LLMDAP_ROUTE_CLASS"}
EMBED_ENV = {"route": "KUTUPHANE_LLMDAP_EMBED_ROUTE", "route_class": "KUTUPHANE_LLMDAP_EMBED_ROUTE_CLASS",
             "model": "KUTUPHANE_EMBED_MODEL"}
RERANK_ENV = {"route": "KUTUPHANE_LLMDAP_RERANK_ROUTE", "route_class": "KUTUPHANE_LLMDAP_RERANK_ROUTE_CLASS",
              "model": "KUTUPHANE_RERANK_MODEL"}
TIMEOUT_SECONDS = 120
CHAT_PATH = "/v1/chat/completions"  # openai schema on the bridge route
EMBED_PATH = "/v1/embeddings"       # openai schema on an LLMDAP `surface: "embeddings"` route
RERANK_PATH = "/v1/rerank"          # openai-compatible schema on an LLMDAP `surface: "rerank"` route (#236)
SYSTEMONE_PATH = "/v1/systemone"    # typed decisions on an LLMDAP `schema: "systemone"` route (D44, #225)


class EgressError(RuntimeError):
    pass


class PolicyRefused(EgressError):
    """Our own egress check refused the call: nothing was sent, and a retry would be refused the same way."""


NOT_SENT_POLICY = "not_sent:egress_policy"      # refused by our own egress check; never left the host
NOT_SENT_UNREACHABLE = "not_sent:unreachable"   # connection refused; nothing was transmitted


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Never follow redirects: they would carry our LLMDAP credential to another host."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_OPENER = urllib.request.build_opener(_NoRedirect)


ROUTE_CLASSES = ("local", "cloud")
# G13: never a default. `local` skips the egress check (_check_egress), so a default would turn a cloud route the
# operator did not declare into one that gets `local_only` text. compose.yaml sets `local` for its own LLMDAP; the
# CLI on the host reads no compose file, so it stops and names the setting.
ROUTE_CLASS_HINT = ("local or cloud: does the route keep the data on premises? compose.yaml sets local for its own "
                    "LLMDAP; outside compose there is no default")


@dataclass(frozen=True)
class Bridge:
    url: str
    route: str
    key: str          # Core's LLMDAP subject key; sent only as the Authorization bearer, never logged
    route_class: str  # operator-declared: does this route keep data on premises ("local") or not ("cloud")?

    @classmethod
    def from_env(cls, route_env: str = ENV["route"], class_env: str = ENV["route_class"]) -> "Bridge":
        missing = [v for v in (ENV["url"], ENV["key"], route_env, class_env) if not os.environ.get(v)]
        if missing:
            hint = f" ({class_env}: {ROUTE_CLASS_HINT})" if class_env in missing else ""
            raise RuntimeError(f"LLMDAP not configured: set {', '.join(missing)}{hint}")
        if os.environ[class_env] not in ROUTE_CLASSES:
            raise RuntimeError(f"{class_env} must be {' or '.join(ROUTE_CLASSES)}")
        return cls(os.environ[ENV["url"]].rstrip("/"), os.environ[route_env], os.environ[ENV["key"]],
                   os.environ[class_env])

    def __post_init__(self):
        if urllib.parse.urlsplit(self.url).scheme not in ("http", "https"):
            raise RuntimeError("LLMDAP url must be http(s)")
        if not self.route.replace("-", "").replace("_", "").isalnum():
            raise RuntimeError("LLMDAP route must be a plain name")
        if self.route_class not in ROUTE_CLASSES:
            raise RuntimeError(f"LLMDAP route class must be one of {', '.join(ROUTE_CLASSES)}")


@dataclass(frozen=True)
class Routed:
    """A model behind one LLMDAP route: the embedder (vectors are stored with its name) or the reranker."""
    bridge: Bridge
    model: str  # the route's pinned model, as LLMDAP serves it

    @classmethod
    def from_env(cls, env: dict) -> "Routed | None":
        """None when the route is not configured: search then works without that stage."""
        if not os.environ.get(env["route"]):
            return None
        if not os.environ.get(env["model"]):
            raise RuntimeError(f"LLMDAP route not configured: set {env['model']}")
        return cls(Bridge.from_env(env["route"], env["route_class"]), os.environ[env["model"]])


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
        raise PolicyRefused(f"egress policy forbids sending {', '.join(blocked)} to cloud route {bridge.route}")


def _post(conn, bridge: Bridge, actor: Actor, path: str, body: dict, *, model: str, source_books: list[str],
          purpose: str | None) -> dict:
    """One governed call: our egress check, then the bridge; every attempt lands in `model_call`."""
    call_id = f"{actor.correlation_id}.{uuid.uuid4().hex[:12]}"
    try:
        _check_egress(conn, bridge, source_books)
    except EgressError as exc:
        _record(conn, actor, bridge, call_id, model, source_books, None, None, NOT_SENT_POLICY)
        raise exc from None
    headers = {
        "content-type": "application/json",
        "authorization": f"Bearer {bridge.key}",
        "x-llmdap-correlation-id": call_id,
        "x-llmdap-for-subject": actor.on_behalf_of or actor.principal,
    }
    if purpose:
        headers["x-llmdap-purpose"] = purpose
    request = urllib.request.Request(f"{bridge.url}/bridge/{bridge.route}{path}", data=json.dumps(body).encode(),
                                     headers=headers, method="POST")
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
        # Only a refused connection proves nothing was sent; anything later is uncertain (LLMDAP may have acted).
        reason = getattr(exc, "reason", exc)
        error = NOT_SENT_UNREACHABLE if isinstance(reason, ConnectionRefusedError) and status is None \
            else f"uncertain:{type(exc).__name__}"
        _record(conn, actor, bridge, call_id, model, source_books, status, derived, error)
        raise EgressError(f"LLMDAP unreachable or invalid answer: {type(exc).__name__}") from None
    _record(conn, actor, bridge, call_id, model, source_books, status, derived, None)
    return payload


def chat(conn, bridge: Bridge, actor: Actor, *, model: str, messages: list[dict], source_books: list[str],
         purpose: str | None = None, options: dict | None = None) -> dict:
    """`source_books`: every book whose content is in `messages` (may be empty). Required, so no caller forgets.
    `options`: more request fields (for example `temperature`); they never replace the model or the messages."""
    return _post(conn, bridge, actor, CHAT_PATH, {**(options or {}), "model": model, "messages": messages,
                                                  "stream": False},
                 model=model, source_books=source_books, purpose=purpose)


def systemone(conn, bridge: Bridge, actor: Actor, *, model: str, body: dict, source_books: list[str],
              purpose: str | None = None) -> dict:
    """A typed decision on an LLMDAP `schema: "systemone"` route (D44: choice questions, class probabilities)."""
    return _post(conn, bridge, actor, SYSTEMONE_PATH, {**body, "model": model}, model=model,
                 source_books=source_books, purpose=purpose)


def embed(conn, embedder: Routed, actor: Actor, texts: list[str], *, source_books: list[str],
          purpose: str) -> list[list[float]]:
    """Vectors in input order. `source_books` as for chat: book content is subject to the same egress policy."""
    payload = _post(conn, embedder.bridge, actor, EMBED_PATH, {"model": embedder.model, "input": texts},
                    model=embedder.model, source_books=source_books, purpose=purpose)
    try:
        rows = sorted(payload["data"], key=lambda d: d["index"])
        indexes = [d["index"] for d in rows]
        vectors = [[float(x) for x in d["embedding"]] for d in rows]
    except (KeyError, TypeError, ValueError):
        raise EgressError("embeddings answer is not data[].embedding") from None
    if indexes != list(range(len(texts))) or len({len(v) for v in vectors}) != 1:
        raise EgressError("embeddings answer does not match the input")  # a vector must never land on another chunk
    if not all(math.isfinite(x) for v in vectors for x in v) or not all(any(v) for v in vectors):
        raise EgressError("embeddings answer has empty, zero or non-finite vectors")
    return vectors


def rerank(conn, reranker: Routed, actor: Actor, query: str, documents: list[str], *, source_books: list[str],
           purpose: str) -> list[float]:
    """Relevance scores in input order. Every document must come back exactly once with a finite score."""
    payload = _post(conn, reranker.bridge, actor, RERANK_PATH,
                    {"model": reranker.model, "query": query, "documents": documents, "top_n": len(documents)},
                    model=reranker.model, source_books=source_books, purpose=purpose)
    try:
        pairs = [(r["index"], float(r["relevance_score"])) for r in payload["results"]]
    except (KeyError, TypeError, ValueError):
        raise EgressError("rerank answer is not results[].relevance_score") from None
    if sorted(i for i, _ in pairs) != list(range(len(documents))) or not all(type(i) is int for i, _ in pairs):
        raise EgressError("rerank answer does not match the documents")  # a score must never land on another passage
    if not all(math.isfinite(score) for _, score in pairs):
        raise EgressError("rerank answer has non-finite scores")
    return [score for _, score in sorted(pairs)]
