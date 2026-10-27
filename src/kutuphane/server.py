"""HTTP API and Kütüphane MCP (M1e): one ASGI app, the same functions as the CLI.

- The caller is ONLY what a verified access token says (D50, AT-11): `Authorization: Bearer <jwt>`; no header can
  set or change the principal or the user acted for. Each request gets a fresh correlation id.
- Every content path is the authorization gate the library already uses (search, citations, files, answers).
- Errors are short and uniform (401/403/404/400/409/502); no stack traces or internals in responses.
"""
import contextlib
import dataclasses
import functools
import logging
import os
import urllib.parse
import uuid

from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.provider import AccessToken
from mcp.server.auth.settings import AuthSettings
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from . import answers, db, feedback, gate, identity, kstd, llmdap, retrieval, search
from .gate import Actor
from .ids import normalize_path

# Feature modules (docs/24 §16 P0). Each may define `register_mcp(mcp, deps)` (adds its MCP tools) and
# `http_routes(deps, endpoint) -> list[Route]` (its HTTP routes). They are called in this order, after the built-in
# tools and routes, so the tool list and the route table stay in a fixed order.
FEATURES: tuple = ()

log = logging.getLogger(__name__)
ENV = {"model": "KUTUPHANE_ANSWER_MODEL", "public_url": "KUTUPHANE_PUBLIC_URL"}
TEXT_TYPES = ("text/markdown", "text/plain")


class BadRequest(ValueError):
    pass


def parse_citation(handle: str) -> search.Citation:
    """`book@ct_…/pf_…/path#ordinal`; the path may contain '/' but is validated like any stored path."""
    try:
        head, ordinal = handle.rsplit("#", 1)
        book, rest = head.split("@", 1)
        content_id, profile_id, path = rest.split("/", 2)
        return search.Citation(book, content_id, profile_id, normalize_path(path), int(ordinal))
    except ValueError:
        raise BadRequest("malformed citation handle") from None


# --- shared operations (HTTP and MCP call the same code) ---------------------------------------------------

def _run(dsn, fn):
    with db.connect(dsn) as conn:
        return fn(conn)


def _for_model(actor: Actor, model_reader: bool) -> bool:
    """MCP callers and agent principals put what they read into a model's context: that is AI input (kstd)."""
    return model_reader or actor.principal.startswith("agent:")


def _text(text, item, for_model: bool) -> dict:
    """The passage text, or None with a reason when its kstd rights do not allow AI input for this reader."""
    if for_model and not kstd.allows(item, "ai_input"):
        return {"text": None, "withheld": "rights do not allow AI input"}
    return {"text": text}


def _check_query(query) -> None:
    """The query limits, before any model call or the query cache (Astra review #12: search AND ask)."""
    try:
        search.check_query(query)
    except ValueError as exc:
        raise BadRequest(str(exc)) from None


def op_search(dsn, stages, actor: Actor, query: str, k: int, model_reader: bool = False,
              scope: search.Scope = search.Scope()) -> list[dict]:
    _check_query(query)

    def go(conn):
        hits, rights, ai = retrieval.retrieve(conn, actor, query, k, stages, scope), kstd.Rights(conn), \
            _for_model(actor, model_reader)
        out = []
        for h in hits:
            item = rights.info(h.citation.book, h.citation.content_id, h.citation.path)
            out.append({"citation": h.citation.handle, "page": h.page, "line": h.line, "score": round(h.score, 4),
                        **_text(h.text, item, ai), "item": item})
        return out
    return _run(dsn, go)


def op_citation(dsn, actor: Actor, handle: str, model_reader: bool = False) -> dict:
    def go(conn):
        hit = search.open_citation(conn, actor, parse_citation(handle))
        c = hit.citation
        item = kstd.Rights(conn).info(c.book, c.content_id, c.path)
        return {"citation": c.handle, "page": hit.page, "line": hit.line,
                **_text(hit.text, item, _for_model(actor, model_reader)),
                "item": item}
    return _run(dsn, go)


def op_ask(dsn, bridge, model: str, stages, actor: Actor, question: str, scope: search.Scope = search.Scope()) -> dict:
    if not isinstance(question, str) or not question.strip():
        raise BadRequest("question is required")
    _check_query(question)
    return _run(dsn, lambda c: answers.ask(c, bridge, actor, question, model=model, stages=stages, scope=scope))


def _flag(value) -> bool:
    """A query-string boolean: true/1 or false/0 (absent: false)."""
    if value in (None, "", "false", "0"):
        return False
    if value in ("true", "1"):
        return True
    raise BadRequest("current_only must be true or false")


def op_reopen(dsn, actor: Actor, answer_id: str, model_reader: bool = False) -> dict:
    out = _run(dsn, lambda c: answers.reopen(c, actor, answer_id))
    ai = _for_model(actor, model_reader)
    return {**out, "evidence": [{**e, **_text(e["text"], e["item"], ai)} for e in out["evidence"]]}


def op_file(dsn, actor: Actor, book: str, content_id: str, path: str,
             model_reader: bool = False) -> tuple[bytes, str]:
    def go(conn):
        norm = normalize_path(path)
        item = kstd.Rights(conn).info(book, content_id, norm)
        if _for_model(actor, model_reader) and not kstd.allows(item, "ai_input"):
            # Callers who may not read get the ordinary refusal; the rights refusal is only for readers.
            gate.check_many(conn, actor, {f"book:{book}": {"read"}}, action="model-read")
            raise gate.Denied(f"{norm}: its rights do not allow AI input")  # nothing is delivered
        data = gate.deliver_file(conn, actor, book, content_id, norm)
        entry = conn.execute("SELECT m.entry->>'media_type' FROM content_version c CROSS JOIN LATERAL "
                             "jsonb_array_elements(c.manifest) AS m(entry) WHERE c.book = %s AND c.id = %s "
                             "AND m.entry->>'path' = %s", (book, content_id, norm)).fetchone()
        return data, entry[0] if entry else "application/octet-stream"
    return _run(dsn, go)


def op_feedback(dsn, actor: Actor, body) -> dict:
    if not isinstance(body, dict):
        raise BadRequest("JSON object required")
    fields = {k: body.get(k) for k in ("book", "content_id", "path", "outcome", "tested_on", "note")}
    if not all(isinstance(fields[k], str) for k in ("book", "content_id", "path", "outcome")):
        raise BadRequest("book, content_id, path and outcome are required strings")
    for k in ("tested_on", "note"):
        if fields[k] is not None and not isinstance(fields[k], str):
            raise BadRequest(f"{k} must be a string")
    fields["path"] = normalize_path(fields["path"])
    return {"id": _run(dsn, lambda c: feedback.record(c, actor, **fields))}


def op_feedback_list(dsn, actor: Actor, book: str, content_id: str, path: str) -> list[dict]:
    return _run(dsn, lambda c: feedback.for_version(c, actor, book=book, content_id=content_id,
                                                    path=normalize_path(path)))


# --- HTTP --------------------------------------------------------------------------------------------------

ERRORS = [  # order matters: subclasses first
    (identity.AuthenticationError, 401, "unauthenticated"),
    (search.SearchChanged, 409, "authorization changed during the request; retry"),
    (gate.Denied, 403, "forbidden"),
    (gate.NotFound, 404, "not found"),
    (llmdap.EgressError, 502, "model service unavailable or refused"),
    (ValueError, 400, None),  # BadRequest, query/k validation, path validation: message is safe and useful
]


def _classify(exc: Exception) -> tuple[int, str] | None:
    """(status, safe message) for expected errors; None for anything else (never shown to the caller)."""
    for kind, status, message in ERRORS:
        if isinstance(exc, kind):
            return status, message or str(exc)
    return None


def _error(exc: Exception) -> Response:
    known = _classify(exc)
    if known is None:
        raise exc
    status, message = known
    headers = {"WWW-Authenticate": "Bearer"} if status == 401 else None
    return JSONResponse({"error": message}, status_code=status, headers=headers)


class SecurityHeaders:
    """Strict headers on every response. The UI renders model output as plain text and loads nothing external
    (Astra review #3): a CSP that only allows this origin makes that a property, not a convention."""
    HEADERS = [
        (b"content-security-policy", b"default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self'; "
                                     b"connect-src 'self'; font-src 'self'; base-uri 'none'; form-action 'self'; "
                                     b"frame-ancestors 'none'"),
        (b"x-content-type-options", b"nosniff"),
        (b"referrer-policy", b"no-referrer"),
        (b"x-frame-options", b"DENY"),
    ]

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                names = {k.lower() for k, _ in message.get("headers", [])}
                message["headers"] = list(message.get("headers", [])) + [h for h in self.HEADERS if h[0] not in names]
            await send(message)
        await self.app(scope, receive, send_with_headers)


@dataclasses.dataclass(frozen=True)
class Deps:
    """What the server gives a feature module: the configuration, and the MCP helpers every tool must use (the
    caller from the verified token, and the uniform errors)."""
    dsn: str
    bridge: llmdap.Bridge | None
    model: str | None
    stages: retrieval.Stages

    @staticmethod
    def mcp_actor() -> Actor:
        return _mcp_actor()

    @staticmethod
    def mcp_errors(tool):
        return _mcp_errors(tool)


def create_app(*, dsn: str, verifier: identity.Verifier, bridge: llmdap.Bridge | None, model: str | None,
               public_url: str, ui_dir: str | None = None,
               stages: retrieval.Stages = retrieval.Stages(), features: tuple | None = None) -> Starlette:
    features = FEATURES if features is None else features
    deps = Deps(dsn, bridge, model, stages)

    def actor_of(request: Request) -> Actor:
        scheme, _, token = request.headers.get("authorization", "").partition(" ")
        if scheme.lower() != "bearer":
            raise identity.AuthenticationError("bearer token required")
        return dataclasses.replace(verifier.verify(token.strip()), channel="http")  # set here, never by the client

    def endpoint(work):
        async def handler(request: Request) -> Response:
            try:
                actor = actor_of(request)
                return await work(request, actor)
            except Exception as exc:  # mapped to a uniform status; unknown errors propagate (500, logged)
                return _error(exc)
        return handler

    async def h_search(request, actor):
        p = request.query_params
        try:
            k = int(p.get("k", search.DEFAULT_K))
        except ValueError:
            raise BadRequest("k must be an integer") from None
        scope = search.Scope.of(p.getlist("book"), p.get("path"), p.getlist("origin"), _flag(p.get("current_only")))
        return JSONResponse({"correlation_id": actor.correlation_id,
                             "results": await run_in_threadpool(op_search, dsn, stages, actor, p.get("q", ""), k,
                                                                False, scope)})

    async def h_citation(request, actor):
        return JSONResponse(await run_in_threadpool(op_citation, dsn, actor, request.query_params.get("handle", "")))

    async def h_ask(request, actor):
        if bridge is None or not model:
            raise llmdap.EgressError("no model route configured")
        try:
            body = await request.json()
        except ValueError:
            raise BadRequest("JSON body required") from None
        if not isinstance(body, dict):
            raise BadRequest("JSON object required")
        scope = search.Scope.of(body.get("book"), body.get("path"), body.get("origin"), body.get("current_only", False))
        result = await run_in_threadpool(op_ask, dsn, bridge, model, stages, actor, body.get("question"), scope)
        return JSONResponse({**result, "correlation_id": actor.correlation_id})

    async def h_answer(request, actor):
        return JSONResponse(await run_in_threadpool(op_reopen, dsn, actor, request.path_params["answer_id"]))

    async def h_file(request, actor):
        p = request.path_params
        data, media_type = await run_in_threadpool(op_file, dsn, actor, p["book"], p["content_id"], p["path"])
        return Response(data, media_type=media_type, headers={"X-Content-Type-Options": "nosniff",
                                                              "Content-Disposition": "attachment"})

    async def h_feedback(request, actor):
        if request.method == "POST":
            try:
                body = await request.json()
            except ValueError:
                raise BadRequest("JSON body required") from None
            return JSONResponse(await run_in_threadpool(op_feedback, dsn, actor, body), status_code=201)
        q = request.query_params
        return JSONResponse(await run_in_threadpool(op_feedback_list, dsn, actor, q.get("book", ""),
                                                    q.get("content_id", ""), q.get("path", "")))

    async def h_health(_request):
        return JSONResponse({"ok": True})

    async def h_whoami(_request, actor):
        return JSONResponse({"principal": actor.principal, "on_behalf_of": actor.on_behalf_of})

    mcp = build_mcp(dsn=dsn, verifier=verifier, bridge=bridge, model=model, public_url=public_url, stages=stages,
                    features=features)

    @contextlib.asynccontextmanager
    async def lifespan(_app):
        async with mcp.session_manager.run():
            yield

    app = Starlette(routes=[
        Route("/healthz", h_health),
        Route("/v1/whoami", endpoint(h_whoami)),
        *([Mount("/ui", app=StaticFiles(directory=ui_dir, html=True))] if ui_dir else []),
        Route("/v1/search", endpoint(h_search)),
        Route("/v1/citation", endpoint(h_citation)),
        Route("/v1/ask", endpoint(h_ask), methods=["POST"]),
        Route("/v1/answers/{answer_id}", endpoint(h_answer)),
        Route("/v1/files/{book}/{content_id}/{path:path}", endpoint(h_file)),
        Route("/v1/feedback", endpoint(h_feedback), methods=["GET", "POST"]),
        *(route for f in features if hasattr(f, "http_routes") for route in f.http_routes(deps, endpoint)),
        Mount("/", app=mcp.streamable_http_app()),  # serves /mcp and the protected-resource metadata
    ], lifespan=lifespan)
    app.add_middleware(SecurityHeaders)
    return app


# --- MCP ---------------------------------------------------------------------------------------------------

class _Verifier:
    """MCP adapter: the same JWT verification; the verified principal travels in the token's claims."""

    def __init__(self, verifier: identity.Verifier):
        self.verifier = verifier

    async def verify_token(self, token: str) -> AccessToken | None:
        try:
            actor = self.verifier.verify(token)
        except identity.AuthenticationError:
            return None
        return AccessToken(token=token, client_id="kutuphane-mcp", scopes=[], subject=actor.principal,
                           claims={"kutuphane_principal": actor.principal,
                                   "kutuphane_on_behalf_of": actor.on_behalf_of})


def _mcp_errors(tool):
    """The same short, uniform errors as HTTP (Astra review #4): the SDK would otherwise send the exception text,
    internals included, to the client. Unexpected errors are logged here and reported generically."""
    @functools.wraps(tool)
    async def wrapper(*args, **kwargs):
        try:
            return await tool(*args, **kwargs)
        except Exception as exc:
            known = _classify(exc)
            if known is None:
                log.exception("MCP tool %s failed", tool.__name__)
            raise ToolError(known[1] if known else "internal error") from None
    return wrapper


def _mcp_actor() -> Actor:
    token = get_access_token()
    if token is None or not token.claims:
        raise identity.AuthenticationError("no verified token")
    return Actor(token.claims["kutuphane_principal"], token.claims["kutuphane_on_behalf_of"],
                 correlation_id=uuid.uuid4().hex, channel="mcp")


def build_mcp(*, dsn: str, verifier: identity.Verifier, bridge, model, public_url: str,
              stages: retrieval.Stages = retrieval.Stages(), features: tuple | None = None) -> FastMCP:
    features = FEATURES if features is None else features
    public = urllib.parse.urlsplit(public_url)
    security = TransportSecuritySettings(enable_dns_rebinding_protection=True, allowed_hosts=[public.netloc],
                                         allowed_origins=[f"{public.scheme}://{public.netloc}"])
    mcp = FastMCP("kutuphane", token_verifier=_Verifier(verifier), stateless_http=True, transport_security=security,
                  auth=AuthSettings(issuer_url=verifier.issuer, resource_server_url=public_url,
                                    validate_token_resource=False))  # our verifier checks `aud` itself

    @mcp.tool()
    @_mcp_errors
    async def search_library(query: str, k: int = search.DEFAULT_K, book: list[str] | None = None,
                             path: str | None = None, origin: list[str] | None = None,
                             current_only: bool = False) -> list[dict]:
        """Search the books you may read now. Results carry citation handles for open_citation.
        Optional filters narrow the evidence before ranking: `book` (slugs), `path` (prefix, e.g. "data/"),
        `origin` (kstd origins: human, assisted, model, tool, unknown), `current_only` (kstd validity includes now)."""
        scope = search.Scope.of(book, path, origin, current_only)
        return await run_in_threadpool(op_search, dsn, stages, _mcp_actor(), query, k, True, scope)

    @mcp.tool()
    @_mcp_errors
    async def open_citation(handle: str) -> dict:
        """Open a citation handle: the exact passage of that version, if you may read it now."""
        return await run_in_threadpool(op_citation, dsn, _mcp_actor(), handle, True)

    @mcp.tool()
    @_mcp_errors
    async def ask_library(question: str, book: list[str] | None = None, path: str | None = None,
                          origin: list[str] | None = None, current_only: bool = False) -> dict:
        """Answer from the library with [n] citations, or status not_in_library. The optional filters are those of
        search_library."""
        if bridge is None or not model:
            raise llmdap.EgressError("no model route configured")
        scope = search.Scope.of(book, path, origin, current_only)
        return await run_in_threadpool(op_ask, dsn, bridge, model, stages, _mcp_actor(), question, scope)

    @mcp.tool()
    @_mcp_errors
    async def reopen_answer(answer_id: str) -> dict:
        """Show a stored answer and its evidence again (no model call; current rights apply)."""
        return await run_in_threadpool(op_reopen, dsn, _mcp_actor(), answer_id, True)

    @mcp.tool()
    @_mcp_errors
    async def read_document(book: str, content_id: str, path: str) -> str:
        """Read a text document of a specific version (agent instructions need an activate grant)."""
        data, media_type = await run_in_threadpool(op_file, dsn, _mcp_actor(), book, content_id, path, True)
        if media_type not in TEXT_TYPES:
            raise BadRequest("not a text document; use search_library and open_citation for its passages")
        return data.decode("utf-8")

    @mcp.tool()
    @_mcp_errors
    async def record_runbook_feedback(book: str, content_id: str, path: str, outcome: str,
                                      tested_on: str | None = None, note: str | None = None) -> dict:
        """Record how applying a runbook went: outcome is worked, failed or changed (for that exact version)."""
        return await run_in_threadpool(op_feedback, dsn, _mcp_actor(),
                                       {"book": book, "content_id": content_id, "path": path, "outcome": outcome,
                                        "tested_on": tested_on, "note": note})

    deps = Deps(dsn, bridge, model, stages)
    for f in features:
        if hasattr(f, "register_mcp"):
            f.register_mcp(mcp, deps)
    return mcp


def app_from_env() -> Starlette:
    """uvicorn --factory kutuphane.server:app_from_env"""
    missing = [v for v in ENV.values() if not os.environ.get(v)]
    if missing:
        raise RuntimeError(f"server not configured: set {', '.join(missing)}")
    bridge = llmdap.Bridge.from_env() if os.environ.get(llmdap.ENV["url"]) else None
    with db.connect(os.environ[db.DSN_ENV]) as conn:  # refuse to serve a schema the code does not match
        waiting = db.pending(conn)
    if waiting:
        raise RuntimeError(f"database needs migrations ({', '.join(waiting)}): run `kutuphane migrate`")
    ui_dir = os.environ.get("KUTUPHANE_UI_DIR") or None
    return create_app(dsn=os.environ[db.DSN_ENV], verifier=identity.Verifier.from_env(), bridge=bridge,
                      model=os.environ[ENV["model"]], public_url=os.environ[ENV["public_url"]], ui_dir=ui_dir,
                      stages=retrieval.Stages.from_env())
