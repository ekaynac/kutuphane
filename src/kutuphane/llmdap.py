"""The way Kütüphane reaches a model (D3, D88): the LLMDAP bridge or, per stage, a direct OpenAI-compatible endpoint,
for chat and for embeddings (D17, #222). Stdlib HTTP, no SDKs.

Core authenticates as its own LLMDAP subject with a subject key (`GATEWAY_AUTH_MODE=subject-keys`, LLMDAP #228):
the credential names the subject, so no header can claim another one. The person served (the user, or the user an
agent acts for) travels as the `x-llmdap-for-subject` attribution label; who exactly called — agent included — is in
our own `model_call`, joined by the call id (AT-09). LLMDAP answers with its namespaced form of that id, which we
store. Every attempt is recorded in `model_call`, including failures.

The `openai` provider (D88 (2)) sends the same bodies to `<url>/v1/...` with the stage's API key as the bearer and no
`x-llmdap-*` header: that provider must not learn who asks. Our rights and egress checks run first for both
providers, and the declared class of the provider (`local` or `cloud`) feeds the egress check. Rerank has no standard
OpenAI endpoint, so it stays on LLMDAP.
"""
import http.client
import json
import math
import os
import uuid
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field

from .gate import Actor

ENV = {"url": "KUTUPHANE_LLMDAP_URL", "key": "KUTUPHANE_LLMDAP_KEY", "route": "KUTUPHANE_LLMDAP_ROUTE",
       "route_class": "KUTUPHANE_LLMDAP_ROUTE_CLASS", "provider": "KUTUPHANE_ANSWER_PROVIDER",
       "openai_url": "KUTUPHANE_ANSWER_OPENAI_URL", "openai_key": "KUTUPHANE_ANSWER_OPENAI_KEY",
       "openai_class": "KUTUPHANE_ANSWER_OPENAI_CLASS"}
EMBED_ENV = {"route": "KUTUPHANE_LLMDAP_EMBED_ROUTE", "route_class": "KUTUPHANE_LLMDAP_EMBED_ROUTE_CLASS",
             "model": "KUTUPHANE_EMBED_MODEL", "provider": "KUTUPHANE_EMBED_PROVIDER",
             "openai_url": "KUTUPHANE_EMBED_OPENAI_URL", "openai_key": "KUTUPHANE_EMBED_OPENAI_KEY",
             "openai_class": "KUTUPHANE_EMBED_OPENAI_CLASS"}
RERANK_ENV = {"route": "KUTUPHANE_LLMDAP_RERANK_ROUTE", "route_class": "KUTUPHANE_LLMDAP_RERANK_ROUTE_CLASS",
              "model": "KUTUPHANE_RERANK_MODEL", "provider": "KUTUPHANE_RERANK_PROVIDER"}  # only unset or `llmdap`
TIMEOUT_SECONDS = 120
CHAT_PATH = "/v1/chat/completions"  # openai schema on the bridge route
EMBED_PATH = "/v1/embeddings"       # openai schema on an LLMDAP `surface: "embeddings"` route
RERANK_PATH = "/v1/rerank"          # openai-compatible schema on an LLMDAP `surface: "rerank"` route (#236)
# #165: every call names one of these as `x-llmdap-purpose`, so one shared LLMDAP chain (D76) tells our calls apart.
# The product is the LLMDAP subject (`svc-kutuphane`), so the names carry no product prefix.
PURPOSES = ("answer", "search", "index", "translate", "rerank", "note", "decide", "health")


class EgressError(RuntimeError):
    pass


class PolicyRefused(EgressError):
    """Our own egress check refused the call: nothing was sent, and a retry would be refused the same way."""


NOT_SENT_POLICY = "not_sent:egress_policy"      # refused by our own egress check; never left the host
NOT_SENT_UNREACHABLE = "not_sent:unreachable"   # connection refused; nothing was transmitted


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Never follow redirects: they would carry our credential (LLMDAP key or provider API key) to another host."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_OPENER = urllib.request.build_opener(_NoRedirect)


ROUTE_CLASSES = ("local", "cloud")
PROVIDERS = ("llmdap", "openai")
DIRECT_ROUTE_PREFIX = "openai:"  # `model_call.route` of a direct call; an LLMDAP route name has no colon
# G13: never a default. `local` skips the egress check (_check_egress), so a default would turn a cloud route the
# operator did not declare into one that gets `local_only` text. deploy/compose.full.yaml sets `local` for its own
# LLMDAP; the CLI on the host reads no compose file, so it stops and names the setting.
ROUTE_CLASS_HINT = ("local or cloud: does the route keep the data on premises? deploy/compose.full.yaml sets local "
                    "for its own LLMDAP; outside compose there is no default")
PROVIDER_CLASS_HINT = "local or cloud: does the provider keep the data on premises? there is no default"


def provider_of(env: dict) -> str:
    """The provider of one model stage: `llmdap` unless its setting says `openai` (unset or empty is `llmdap`).
    Any other value stops start-up. Rerank (no `openai_url` in its settings) is LLMDAP-only: OpenAI has no standard
    rerank endpoint, so `openai` there is refused, not ignored."""
    name = env["provider"]
    value = os.environ.get(name) or "llmdap"
    allowed = PROVIDERS if "openai_url" in env else PROVIDERS[:1]
    if value not in allowed:
        why = "" if allowed == PROVIDERS else ": rerank is LLMDAP-only (OpenAI has no standard rerank endpoint)"
        raise RuntimeError(f"{name} must be {' or '.join(allowed)}{why}")
    return value


@dataclass(frozen=True)
class Bridge:
    url: str
    route: str
    key: str = field(repr=False)  # the LLMDAP subject key or the provider's API key; only the Authorization bearer
    route_class: str  # operator-declared: does this route keep data on premises ("local") or not ("cloud")?
    provider: str = "llmdap"

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

    @classmethod
    def openai_from_env(cls, env: dict) -> "Bridge":
        """The direct provider of one stage: URL, API key and class are all required, the class has no default."""
        names = (env["openai_url"], env["openai_key"], env["openai_class"])
        missing = [v for v in names if not os.environ.get(v)]
        if missing:
            hint = f" ({env['openai_class']}: {PROVIDER_CLASS_HINT})" if env["openai_class"] in missing else ""
            raise RuntimeError(f"OpenAI provider not configured: set {', '.join(missing)}{hint}")
        if os.environ[env["openai_class"]] not in ROUTE_CLASSES:
            raise RuntimeError(f"{env['openai_class']} must be {' or '.join(ROUTE_CLASSES)}")
        url = os.environ[env["openai_url"]].rstrip("/")
        host = urllib.parse.urlsplit(url).netloc.rpartition("@")[2]
        return cls(url, DIRECT_ROUTE_PREFIX + host, os.environ[env["openai_key"]], os.environ[env["openai_class"]],
                   "openai")

    @classmethod
    def for_stage(cls, env: dict) -> "Bridge":
        """The bridge of one model stage (ENV: answer, EMBED_ENV, RERANK_ENV) by its provider setting."""
        if provider_of(env) == "openai":
            return cls.openai_from_env(env)
        return cls.from_env(env["route"], env["route_class"])

    @property
    def label(self) -> str:
        return "LLMDAP" if self.provider == "llmdap" else "OpenAI provider"

    def __post_init__(self):
        if self.provider not in PROVIDERS:
            raise RuntimeError(f"model provider must be one of {', '.join(PROVIDERS)}")
        parts = urllib.parse.urlsplit(self.url)
        if parts.scheme not in ("http", "https") or (self.provider == "openai" and not parts.hostname):
            raise RuntimeError(f"{self.label} url must be http(s)")
        if self.provider == "llmdap" and not self.route.replace("-", "").replace("_", "").isalnum():
            raise RuntimeError("LLMDAP route must be a plain name")
        if self.route_class not in ROUTE_CLASSES:
            raise RuntimeError(f"{self.label} route class must be one of {', '.join(ROUTE_CLASSES)}")


@dataclass(frozen=True)
class Routed:
    """A model behind one LLMDAP route or one direct provider: the embedder (vectors are stored with its name) or the
    reranker (LLMDAP only)."""
    bridge: Bridge
    model: str  # the route's pinned model, as LLMDAP serves it; for a direct provider, the model name it takes

    @classmethod
    def from_env(cls, env: dict) -> "Routed | None":
        """None when the stage is not configured: search then works without it. A stage whose provider is `openai`
        is always configured, so a missing setting stops start-up."""
        provider = provider_of(env)
        if provider == "llmdap" and not os.environ.get(env["route"]):
            return None
        if not os.environ.get(env["model"]):
            raise RuntimeError(f"{'LLMDAP route' if provider == 'llmdap' else 'OpenAI provider'} not configured: "
                               f"set {env['model']}")
        return cls(Bridge.for_stage(env), os.environ[env["model"]])


def _record(conn, actor: Actor, bridge: Bridge, call_id: str, model: str, books, status, derived, error) -> None:
    conn.execute("INSERT INTO model_call (correlation_id, caller_correlation_id, call_id, derived_correlation_id, "
                 "principal, on_behalf_of, route, model, http_status, error, source_books) "
                 "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                 (actor.correlation_id, actor.caller_correlation_id, call_id, derived, actor.principal,
                  actor.on_behalf_of, bridge.route, model, status, error, list(books)))


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
          purpose: str) -> dict:
    """One governed call: our egress check, then the bridge; every attempt lands in `model_call`. The call id starts
    with the caller's correlation id when there is one (#156), so the shared LLMDAP chain holds it too."""
    if purpose not in PURPOSES:
        raise ValueError(f"LLMDAP purpose must be one of {', '.join(PURPOSES)}")
    call_id = ".".join(filter(None, (actor.caller_correlation_id, actor.correlation_id, uuid.uuid4().hex[:12])))
    try:
        _check_egress(conn, bridge, source_books)
    except EgressError as exc:
        _record(conn, actor, bridge, call_id, model, source_books, None, None, NOT_SENT_POLICY)
        raise exc from None
    headers = {"content-type": "application/json", "authorization": f"Bearer {bridge.key}"}
    direct = bridge.provider == "openai"
    if not direct:
        headers |= {"x-llmdap-correlation-id": call_id, "x-llmdap-for-subject": actor.on_behalf_of or actor.principal,
                    "x-llmdap-purpose": purpose}
    request = urllib.request.Request(f"{bridge.url}{path}" if direct else f"{bridge.url}/bridge/{bridge.route}{path}",
                                     data=json.dumps(body).encode(), headers=headers, method="POST")
    status = derived = None
    try:
        with _OPENER.open(request, timeout=TIMEOUT_SECONDS) as resp:
            status, derived = resp.status, None if direct else resp.headers.get("x-llmdap-correlation-id-derived")
            payload = json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        derived = exc.headers.get("x-llmdap-correlation-id-derived") if exc.headers and not direct else None
        _record(conn, actor, bridge, call_id, model, source_books, exc.code, derived, f"http {exc.code}")
        raise EgressError(f"{bridge.label} refused the call (HTTP {exc.code})") from None
    except (OSError, http.client.HTTPException, ValueError) as exc:  # network, truncated body, invalid JSON
        # Only a refused connection proves nothing was sent; anything later is uncertain (the model may have acted).
        reason = getattr(exc, "reason", exc)
        error = NOT_SENT_UNREACHABLE if isinstance(reason, ConnectionRefusedError) and status is None \
            else f"uncertain:{type(exc).__name__}"
        _record(conn, actor, bridge, call_id, model, source_books, status, derived, error)
        raise EgressError(f"{bridge.label} unreachable or invalid answer: {type(exc).__name__}") from None
    _record(conn, actor, bridge, call_id, model, source_books, status, derived, None)
    return payload


def chat(conn, bridge: Bridge, actor: Actor, *, model: str, messages: list[dict], source_books: list[str],
         purpose: str, options: dict | None = None) -> dict:
    """`source_books`: every book whose content is in `messages` (may be empty). Required, so no caller forgets.
    `options`: more request fields (for example `temperature`); they never replace the model or the messages."""
    return _post(conn, bridge, actor, CHAT_PATH, {**(options or {}), "model": model, "messages": messages,
                                                  "stream": False},
                 model=model, source_books=source_books, purpose=purpose)


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
