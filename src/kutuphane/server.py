"""HTTP API and Kütüphane MCP (M1e): one ASGI app, the same functions as the CLI.

- The caller is ONLY what a verified access token says (D50, AT-11): `Authorization: Bearer <jwt>`; no header can
  set or change the principal or the user acted for. Each request gets a fresh correlation id.
- Every content path is the authorization gate the library already uses (search, citations, files, answers).
- Errors are short and uniform (401/403/404/400/409/429/502); no stack traces or internals in responses.
- MCP: the SDK v2 `MCPServer`, stateless; it serves 2025-11-25 clients (with `initialize`) and 2026-07-28 clients
  (without) from one app (docs/24 §12.1). A long `ask_library` can run as a durable job (`jobs`, §12.2).
- MCP Skills (SEP-2640, #80): `skills/list`, `skills/get` and `skill://` reads (`skills.py`); the read tools put the
  handling labels under `_meta["kutuphane/handling"]` (`handling.py`).
"""
import contextlib
import dataclasses
import functools
import logging
import os
import urllib.parse
import uuid
from typing import Annotated

import pydantic_core
from mcp.server import CacheHint, MCPServer
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.provider import AccessToken
from mcp.server.auth.settings import AuthSettings
from mcp.server.extension import Extension, MethodBinding
from mcp.server.lowlevel.helper_types import ReadResourceContents
from mcp.server.mcpserver import require_client_extension
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from mcp.shared.exceptions import MCPError
from mcp_types import (INTERNAL_ERROR, INVALID_PARAMS, CallToolResult, PaginatedRequestParams, RequestParams,
                       TextContent)
from mcp_types.version import MODERN_PROTOCOL_VERSIONS
from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from . import (answers, catalog, coderepo, confirm, db, feedback, gate, handling, identity, ids, jobs, kstd, llmdap,
               notes, notesquery, outcomes, quotes, retrieval, search, skills, snippets)
from .gate import Actor
from .ids import normalize_path

# Feature modules (docs/24 §16 P0). Each may define `register_mcp(mcp, deps)` (adds its MCP tools) and
# `http_routes(deps, endpoint) -> list[Route]` (its HTTP routes). They are called in this order, after the built-in
# tools and routes, so the tool list and the route table stay in a fixed order.
FEATURES: tuple = (notes, coderepo, notesquery, outcomes, confirm)

log = logging.getLogger(__name__)
ENV = {"model": "KUTUPHANE_ANSWER_MODEL", "public_url": "KUTUPHANE_PUBLIC_URL"}  # the model: only with LLMDAP
TEXT_TYPES = ("text/markdown", "text/plain")
NO_ANSWERS = "answers are not available: this install has no model gateway (LLMDAP); search is full text only"


class AnswersUnavailable(RuntimeError):
    """No LLMDAP bridge (the light install, #76): Core reaches no model, so it cannot answer."""


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
              scope: search.Scope = search.Scope(), labels_out: dict | None = None,
              max_chars: int | None = None) -> list[dict]:
    """`labels_out`, if given, gets the handling labels of the hits (handling.py), from the same connection.
    `max_chars` (#121): each delivered text becomes a snippet of at most that size, with `truncated`; the hits, their
    order and the gates do not change, and a withheld text stays withheld."""
    _check_query(query)
    snippets.check(max_chars)

    def go(conn):
        # G23: the records each passage repeats; the hits and those records in one final decision (Astra review #19)
        hits, found = quotes.quoted(conn, actor, retrieval.retrieve(conn, actor, query, k, stages, scope), scope)
        rights, ai = kstd.Rights(conn), _for_model(actor, model_reader)
        items = [rights.info(h.citation.book, h.citation.content_id, h.citation.path) for h in hits]
        texts = [_text(h.text, item, ai) for h, item in zip(hits, items)]
        if max_chars is not None:
            shown = [t for t in texts if t["text"] is not None]
            for t, (text, truncated) in zip(shown, snippets.cut(conn, query, [t["text"] for t in shown], max_chars)):
                t.update(text=text, truncated=truncated)
        out = [{"citation": h.citation.handle, "page": h.page, "line": h.line, "score": round(h.score, 4), **t,
                "item": item, "quoted_records": quotes.handles(found, h.citation)}
               for h, item, t in zip(hits, items, texts)]
        if labels_out is not None:
            cited = [h.citation for h in hits]
            labels_out.update(handling.labels(conn, [c.book for c in cited],
                                              [(c.book, c.content_id, c.path) for c in cited]))
        return out
    return _run(dsn, go)


def op_citation(dsn, actor: Actor, handle: str, model_reader: bool = False, context: dict | None = None,
                labels_out: dict | None = None) -> dict:
    """A passage handle, or a note reference with the optional context (docs/24 §9.4). `labels_out`: as op_search;
    a note's labels cover its journal and its `source_books`; only the readable ones are named (handling.py)."""
    if notesquery.is_note_ref(handle):
        def note(conn):
            readable: set = set()
            out = notesquery.open_note(conn, actor, for_model=_for_model(actor, model_reader), ref=handle,
                                       **(context or {}), readable_out=readable)
            if labels_out is not None:
                labels_out.update(handling.note_labels(conn, [out["citation"]], readable))
            return out
        return _run(dsn, note)

    def go(conn):
        hit = search.open_citation(conn, actor, parse_citation(handle))
        c = hit.citation
        item = kstd.Rights(conn).info(c.book, c.content_id, c.path)
        if labels_out is not None:
            labels_out.update(handling.labels(conn, [c.book], [(c.book, c.content_id, c.path)]))
        return {"citation": c.handle, "page": hit.page, "line": hit.line,
                **_text(hit.text, item, _for_model(actor, model_reader)),
                "item": item, "outcomes": outcomes.passage_counts(conn, c)}
    return _run(dsn, go)


def _check_question(question) -> None:
    if not isinstance(question, str) or not question.strip():
        raise BadRequest("question is required")
    _check_query(question)


def op_ask(dsn, bridge, model: str, stages, actor: Actor, question: str, scope: search.Scope = search.Scope()) -> dict:
    _check_question(question)
    return _run(dsn, lambda c: answers.ask(c, bridge, actor, question, model=model, stages=stages, scope=scope))


def op_submit(dsn, actor: Actor, question: str, scope: search.Scope, idempotency_key) -> tuple[dict, bool]:
    """`ask_library(background=true)`: ({job_id, status}, created) at once (docs/24 §12.2)."""
    _check_question(question)
    return _run(dsn, lambda c: jobs.submit(c, actor, question, scope, idempotency_key))


def _flag(value) -> bool:
    """A query-string boolean: true/1 or false/0 (absent: false)."""
    if value in (None, "", "false", "0"):
        return False
    if value in ("true", "1"):
        return True
    raise BadRequest("current_only must be true or false")


def _shown_answer(out: dict, actor: Actor, model_reader: bool) -> dict:
    ai = _for_model(actor, model_reader)
    return {**out, "evidence": [{**e, **_text(e["text"], e["item"], ai)} for e in out["evidence"]]}


def op_reopen(dsn, actor: Actor, answer_id: str, model_reader: bool = False) -> dict:
    return _shown_answer(_run(dsn, lambda c: answers.reopen(c, actor, answer_id)), actor, model_reader)


def op_job_status(dsn, actor: Actor, job_id: str) -> dict:
    return _run(dsn, lambda c: jobs.status(c, actor, job_id))


def op_job_result(dsn, actor: Actor, job_id: str, model_reader: bool = False) -> dict:
    """The `reopen_answer` of the job's answer, with the same text rules for model readers."""
    return _shown_answer(_run(dsn, lambda c: jobs.result(c, actor, job_id)), actor, model_reader)


def op_job_cancel(dsn, actor: Actor, job_id: str) -> dict:
    return _run(dsn, lambda c: jobs.cancel(c, actor, job_id))


def op_file(dsn, actor: Actor, book: str, content_id: str, path: str,
            model_reader: bool = False, labels_out: dict | None = None) -> tuple[bytes, str]:
    def go(conn):
        norm = normalize_path(path)
        rights = kstd.Rights(conn)
        # A file inside a skill folder stands for its whole skill (review #18, the rule of skills.py): a model
        # reader gets it only when kstd allows AI input for every file of the innermost skill that holds it.
        scope = catalog.skill_files(conn, book, content_id, norm) if _for_model(actor, model_reader) else []
        if not all(kstd.allows(rights.info(book, content_id, p), "ai_input") for p in scope):
            # Callers who may not read get the ordinary refusal; the rights refusal is only for readers.
            gate.check_many(conn, actor, {f"book:{book}": {"read"}}, action="model-read")
            raise gate.Denied(f"{norm}: its rights do not allow AI input")  # nothing is delivered
        data = gate.deliver_file(conn, actor, book, content_id, norm)
        entry = conn.execute("SELECT m.entry->>'media_type' FROM content_version c CROSS JOIN LATERAL "
                             "jsonb_array_elements(c.manifest) AS m(entry) WHERE c.book = %s AND c.id = %s "
                             "AND m.entry->>'path' = %s", (book, content_id, norm)).fetchone()
        if labels_out is not None:
            labels_out.update(handling.labels(conn, [book], [(book, content_id, norm)]))
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
    (AnswersUnavailable, 503, NO_ANSWERS),
    (llmdap.EgressError, 502, "model service unavailable or refused"),
    (ids.IdempotencyConflict, 409, None),
    (ids.LimitExceeded, 429, None),
    (ValueError, 400, None),  # BadRequest, query/k validation, path validation: message is safe and useful
]


def _classify(exc: Exception) -> tuple[int, str] | None:
    """(status, safe message) for expected errors; None for anything else (never shown to the caller)."""
    for kind, status, message in ERRORS:
        if isinstance(exc, kind):
            return status, message or str(exc)
    return None


def _safe_error(exc: Exception) -> str:
    """The short message a failed job stores: the HTTP error class text, never the exception's internals."""
    known = _classify(exc)
    return known[1] if known else "internal error"


def _background(background, idempotency_key) -> bool:
    if not isinstance(background, bool):
        raise BadRequest("background must be true or false")
    if idempotency_key is not None and not background:
        raise BadRequest("idempotency_key needs background: true")
    return background


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

    @staticmethod
    def handled(value, labels: dict, *, structured: bool = False) -> CallToolResult:
        return _handled(value, labels, structured=structured)


def create_app(*, dsn: str, verifier: identity.Verifier, bridge: llmdap.Bridge | None, model: str | None,
               public_url: str, ui_dir: str | None = None,
               stages: retrieval.Stages = retrieval.Stages(), features: tuple | None = None,
               job_workers: int = jobs.DEFAULT_WORKERS) -> Starlette:
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
        try:
            max_chars = int(p["max_chars"]) if "max_chars" in p else None
        except ValueError:
            raise BadRequest("max_chars must be an integer") from None
        scope = search.Scope.of(p.getlist("book"), p.get("path"), p.getlist("origin"), _flag(p.get("current_only")))
        return JSONResponse({"correlation_id": actor.correlation_id,
                             "results": await run_in_threadpool(op_search, dsn, stages, actor, p.get("q", ""), k,
                                                                False, scope, None, max_chars)})

    async def h_citation(request, actor):
        q = request.query_params
        context = {k: q[k] for k in ("repo", "branch", "path", "commit") if k in q}
        return JSONResponse(await run_in_threadpool(op_citation, dsn, actor, q.get("handle", ""), False, context))

    async def h_ask(request, actor):
        if bridge is None or not model:
            raise AnswersUnavailable()
        try:
            body = await request.json()
        except ValueError:
            raise BadRequest("JSON body required") from None
        if not isinstance(body, dict):
            raise BadRequest("JSON object required")
        scope = search.Scope.of(body.get("book"), body.get("path"), body.get("origin"), body.get("current_only", False))
        key = body.get("idempotency_key")
        if _background(body.get("background", False), key):
            job, created = await run_in_threadpool(op_submit, dsn, actor, body.get("question"), scope, key)
            return JSONResponse({**job, "correlation_id": actor.correlation_id}, status_code=202 if created else 200)
        result = await run_in_threadpool(op_ask, dsn, bridge, model, stages, actor, body.get("question"), scope)
        return JSONResponse({**result, "correlation_id": actor.correlation_id})

    async def h_answer(request, actor):
        return JSONResponse(await run_in_threadpool(op_reopen, dsn, actor, request.path_params["answer_id"]))

    async def h_job(request, actor):
        return JSONResponse(await run_in_threadpool(op_job_status, dsn, actor, request.path_params["job_id"]))

    async def h_job_result(request, actor):
        return JSONResponse(await run_in_threadpool(op_job_result, dsn, actor, request.path_params["job_id"]))

    async def h_job_cancel(request, actor):
        return JSONResponse(await run_in_threadpool(op_job_cancel, dsn, actor, request.path_params["job_id"]))

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

    def run_ask(conn, actor, question, scope, check, commit) -> str:
        return answers.ask(conn, bridge, actor, question, model=model, stages=stages, scope=scope, check=check,
                           commit=commit)["id"]

    workers = jobs.Workers(dsn, run_ask, _safe_error, job_workers if bridge is not None and model else 0)

    @contextlib.asynccontextmanager
    async def lifespan(_app):
        async with mcp.session_manager.run():
            workers.start()
            try:
                yield
            finally:
                await run_in_threadpool(workers.stop)

    app = Starlette(routes=[
        Route("/healthz", h_health),
        Route("/v1/whoami", endpoint(h_whoami)),
        *([Mount("/ui", app=StaticFiles(directory=ui_dir, html=True))] if ui_dir else []),
        Route("/v1/search", endpoint(h_search)),
        Route("/v1/citation", endpoint(h_citation)),
        Route("/v1/ask", endpoint(h_ask), methods=["POST"]),
        Route("/v1/answers/{answer_id}", endpoint(h_answer)),
        Route("/v1/jobs/{job_id}", endpoint(h_job)),
        Route("/v1/jobs/{job_id}/result", endpoint(h_job_result)),
        Route("/v1/jobs/{job_id}/cancel", endpoint(h_job_cancel), methods=["POST"]),
        Route("/v1/files/{book}/{content_id}/{path:path}", endpoint(h_file)),
        Route("/v1/feedback", endpoint(h_feedback), methods=["GET", "POST"]),
        *(route for f in features if hasattr(f, "http_routes") for route in f.http_routes(deps, endpoint)),
        Mount("/", app=mcp_http_app(mcp, public_url)),  # serves /mcp and the protected-resource metadata
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
                                   "kutuphane_on_behalf_of": actor.on_behalf_of,
                                   "kutuphane_client_id": actor.client_id})


class _ClientCredentials(Extension):
    """Advertised in `server/discover` (docs/24 §12.4): headless clients get tokens by OAuth client credentials at
    the IdP. The resource server only verifies them; it stores no client secret."""
    identifier = "io.modelcontextprotocol/oauth-client-credentials"


class _ListSkillsParams(PaginatedRequestParams):
    pass


class _GetSkillParams(RequestParams):
    uri: str


def _method_error(exc: Exception) -> MCPError:
    """A JSON-RPC error with the same short messages as HTTP: an expected refusal or an unknown skill or file is
    -32602 (Invalid params, as SEP-2640 and `resources/read` use for what the server does not serve); anything else
    is logged and is `internal error`."""
    known = _classify(exc)
    if known is None:
        log.exception("MCP skills request failed")
        return MCPError(code=INTERNAL_ERROR, message="internal error")
    status, message = known
    return MCPError(code=INVALID_PARAMS if status < 500 else INTERNAL_ERROR, message=message)


def _cacheable(ctx) -> dict:
    """SEP-2549 list caching on 2026-07-28 (the entries are per caller and rights change: never reuse them)."""
    return {"ttlMs": 0, "cacheScope": "private"} if ctx.protocol_version in MODERN_PROTOCOL_VERSIONS else {}


class _Skills(Extension):
    """SEP-2640 (#80): `skills/list` and `skills/get` for a client that declares `io.modelcontextprotocol/skills`;
    the files are `skill://` resources (`_Server.read_resource`). The `extensions` capability is 2026-07-28 wire
    (the SDK drops it from a 2025-11-25 `initialize`, and a stateless server sees no `initialize` on the next
    request): on 2025-11-25 the capabilities are unknown, so the call itself is the client's declaration. The gate
    is the same on both versions (skills.py)."""
    identifier = skills.EXTENSION_ID

    def __init__(self, dsn: str):
        self.dsn = dsn

    def methods(self):
        return [MethodBinding("skills/list", _ListSkillsParams, self._list),
                MethodBinding("skills/get", _GetSkillParams, self._get)]

    @staticmethod
    def _declared(ctx) -> None:
        if ctx.session.client_capabilities is not None:
            require_client_extension(ctx, skills.EXTENSION_ID)

    async def _list(self, ctx, params: _ListSkillsParams) -> dict:
        self._declared(ctx)
        if params.cursor is not None:
            raise MCPError(code=INVALID_PARAMS, message="unknown cursor: skills/list has one page")
        try:
            actor = _mcp_actor()
            entries = await run_in_threadpool(_run, self.dsn, lambda c: skills.listing(c, actor))
        except Exception as exc:
            raise _method_error(exc) from None
        return {"skills": entries, **_cacheable(ctx)}

    async def _get(self, ctx, params: _GetSkillParams) -> dict:
        self._declared(ctx)
        try:
            actor = _mcp_actor()
            entry = await run_in_threadpool(_run, self.dsn, lambda c: skills.get(c, actor, params.uri))
        except Exception as exc:
            raise _method_error(exc) from None
        return {"skill": entry, **_cacheable(ctx)}


class _Server(MCPServer):
    """`resources/read` also reads `skill://` files (SEP-2640) through the skill gate, with the file's own media type
    and the handling labels in the content `_meta`. Every other URI goes to the SDK."""

    def __init__(self, *args, dsn: str, **kwargs):
        super().__init__(*args, **kwargs)
        self._dsn = dsn

    async def read_resource(self, uri, context=None):
        if not str(uri).startswith(f"{skills.SCHEME}://"):
            return await super().read_resource(uri, context)
        try:
            actor = _mcp_actor()
            data, media_type, labels = await run_in_threadpool(_run, self._dsn,
                                                               lambda c: skills.read(c, actor, str(uri)))
        except Exception as exc:
            raise _method_error(exc) from None
        content: str | bytes = data
        if skills.is_text(media_type):
            try:
                content = data.decode("utf-8")
            except UnicodeDecodeError:
                pass  # sent as a blob: the bytes, and so the digest, stay exact
        return [ReadResourceContents(content=content, mime_type=media_type, meta={handling.KEY: labels})]


def _handled(value, labels: dict, *, structured: bool = False) -> CallToolResult:
    """The result the SDK makes of a tool's return value (one JSON text block per list item, or the text itself;
    `structuredContent` {"result": …} for a tool with an output schema), with the handling labels in `_meta` (#80)."""
    blocks = [TextContent(type="text", text=v if isinstance(v, str) else
                          pydantic_core.to_json(v, fallback=str, indent=2).decode())
              for v in (value if isinstance(value, list) else [value])]
    return CallToolResult(content=blocks, structured_content={"result": value} if structured else None,
                          _meta={handling.KEY: labels})


# docs/24 §12.1: the tool list is the same for every caller and changes only with a deployment.
CACHE_HINTS = {"tools/list": CacheHint(ttl_ms=300_000, scope="public"),
               "server/discover": CacheHint(ttl_ms=300_000, scope="public")}


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
                 correlation_id=uuid.uuid4().hex, client_id=token.claims.get("kutuphane_client_id"), channel="mcp")


def build_mcp(*, dsn: str, verifier: identity.Verifier, bridge, model, public_url: str,
              stages: retrieval.Stages = retrieval.Stages(), features: tuple | None = None) -> MCPServer:
    """The MCP server. Its tools are registered in a fixed order (built-ins, then features), so `tools/list` is
    stable. The list depends on the deployment only, never on the caller (#121: grants change during a session, and
    the list has public cache hints): without LLMDAP it has no `ask_library` and no job tools. Each description names
    the grant the tool needs. The host app mounts `mcp_http_app` of it."""
    features = FEATURES if features is None else features
    auth = AuthSettings(issuer_url=verifier.issuer, resource_server_url=public_url,
                        validate_token_resource=False)  # our verifier checks `aud` itself
    if str(auth.issuer_url) != verifier.issuer:  # docs/24 §12.5: advertise exactly the issuer we verify
        raise RuntimeError(f"issuer {verifier.issuer!r} would be advertised as {str(auth.issuer_url)!r}: "
                           "write KUTUPHANE_OIDC_ISSUER exactly as the IdP's tokens carry it, in that normal form")
    mcp = _Server("kutuphane", dsn=dsn, token_verifier=_Verifier(verifier),
                  extensions=[_ClientCredentials(), _Skills(dsn)], cache_hints=CACHE_HINTS, auth=auth)

    @mcp.tool()
    @_mcp_errors
    async def search_library(query: str, k: int = search.DEFAULT_K, book: list[str] | None = None,
                             path: str | None = None, origin: list[str] | None = None,
                             current_only: bool = False, max_chars: int | None = None,
                             ) -> Annotated[CallToolResult, list[dict]]:
        """Search the books you may read now (needs read; agents also need activate for instruction passages).
        Results carry citation handles for open_citation. Optional filters narrow the evidence before ranking:
        `book` (slugs), `path` (prefix, e.g. "data/"), `origin` (kstd origins: human, assisted, model, tool, unknown),
        `current_only` (kstd validity includes now). `max_chars` (80-4800) makes each text a snippet around the
        match with `truncated`; open_citation gives the full passage. Use it in agent loops."""
        scope, labels = search.Scope.of(book, path, origin, current_only), {}
        hits = await run_in_threadpool(op_search, dsn, stages, _mcp_actor(), query, k, True, scope, labels,
                                       max_chars)
        return _handled(hits, labels, structured=True)

    @mcp.tool()
    @_mcp_errors
    async def open_citation(handle: str, repo: str | None = None, branch: str | None = None,
                            path: str | None = None, commit: str | None = None) -> CallToolResult:
        """Open a citation handle: the exact passage of that version, if you may read it now (needs read on the
        book; agents also need activate for an instruction passage). A note reference (book@nt_…) gives the note,
        with `current` in the optional context (repo, branch, path, commit)."""
        context, labels = {"repo": repo, "branch": branch, "path": path, "commit": commit}, {}
        cited = await run_in_threadpool(op_citation, dsn, _mcp_actor(), handle, True, context, labels)
        return _handled(cited, labels)

    answering = bridge is not None and bool(model)  # the deployment has LLMDAP and an answer model
    if answering:
        @mcp.tool()
        @_mcp_errors
        async def ask_library(question: str, book: list[str] | None = None, path: str | None = None,
                              origin: list[str] | None = None, current_only: bool = False, background: bool = False,
                              idempotency_key: str | None = None) -> dict:
            """Answer from the library with [n] citations, or status not_in_library (needs read on the books it
            uses). The optional filters are those of search_library. With `background: true` it returns {job_id,
            status: queued} at once: poll job_status, then job_result. An `idempotency_key` (8-128 characters) makes
            a retried submission return the same job."""
            scope = search.Scope.of(book, path, origin, current_only)
            if _background(background, idempotency_key):
                job, _created = await run_in_threadpool(op_submit, dsn, _mcp_actor(), question, scope,
                                                        idempotency_key)
                return job
            return await run_in_threadpool(op_ask, dsn, bridge, model, stages, _mcp_actor(), question, scope)

    @mcp.tool()
    @_mcp_errors
    async def reopen_answer(answer_id: str) -> dict:
        """Show your stored answer and its evidence again (needs read on its books now; no model call)."""
        return await run_in_threadpool(op_reopen, dsn, _mcp_actor(), answer_id, True)

    @mcp.tool()
    @_mcp_errors
    async def read_document(book: str, content_id: str, path: str) -> Annotated[CallToolResult, str]:
        """Read a text document of a specific version (needs read on the book; agent instructions need activate)."""
        labels = {}
        data, media_type = await run_in_threadpool(op_file, dsn, _mcp_actor(), book, content_id, path, True, labels)
        if media_type not in TEXT_TYPES:
            raise BadRequest("not a text document; use search_library and open_citation for its passages")
        return _handled(data.decode("utf-8"), labels, structured=True)

    @mcp.tool()
    @_mcp_errors
    async def record_runbook_feedback(book: str, content_id: str, path: str, outcome: str,
                                      tested_on: str | None = None, note: str | None = None) -> dict:
        """Record how applying a runbook went: outcome is worked, failed or changed (for that exact version; needs
        read on the book)."""
        return await run_in_threadpool(op_feedback, dsn, _mcp_actor(),
                                       {"book": book, "content_id": content_id, "path": path, "outcome": outcome,
                                        "tested_on": tested_on, "note": note})

    if answering:
        @mcp.tool()
        @_mcp_errors
        async def job_status(job_id: str) -> dict:
            """The state of your background ask_library job (no grant; your own jobs only): queued, running,
            succeeded, failed or cancelled."""
            return await run_in_threadpool(op_job_status, dsn, _mcp_actor(), job_id)

        @mcp.tool()
        @_mcp_errors
        async def job_result(job_id: str) -> dict:
            """The answer of your succeeded job, as reopen_answer shows it (needs read on its books now)."""
            return await run_in_threadpool(op_job_result, dsn, _mcp_actor(), job_id, True)

        @mcp.tool()
        @_mcp_errors
        async def job_cancel(job_id: str) -> dict:
            """Cancel your background job (no grant; your own jobs only): a queued job stops at once; a running one
            before its model call or its result."""
            return await run_in_threadpool(op_job_cancel, dsn, _mcp_actor(), job_id)

    deps = Deps(dsn, bridge, model, stages)
    for f in features:
        if hasattr(f, "register_mcp"):
            f.register_mcp(mcp, deps)
    return mcp


def mcp_http_app(mcp: MCPServer, public_url: str) -> Starlette:
    """/mcp and the protected-resource metadata: stateless (no `Mcp-Session-Id`; both protocol eras), and only for
    the public host and origin (DNS rebinding)."""
    public = urllib.parse.urlsplit(public_url)
    security = TransportSecuritySettings(enable_dns_rebinding_protection=True, allowed_hosts=[public.netloc],
                                         allowed_origins=[f"{public.scheme}://{public.netloc}"])
    return mcp.streamable_http_app(stateless_http=True, transport_security=security)


def app_from_env() -> Starlette:
    """uvicorn --factory kutuphane.server:app_from_env"""
    with_models = bool(os.environ.get(llmdap.ENV["url"]))
    missing = [v for k, v in ENV.items() if not os.environ.get(v) and (k != "model" or with_models)]
    if missing:
        raise RuntimeError(f"server not configured: set {', '.join(missing)}")
    bridge = llmdap.Bridge.from_env() if with_models else None
    with db.connect(os.environ[db.DSN_ENV]) as conn:  # refuse to serve a schema the code does not match
        waiting = db.pending(conn)
    if waiting:
        raise RuntimeError(f"database needs migrations ({', '.join(waiting)}): run `kutuphane migrate`")
    ui_dir = os.environ.get("KUTUPHANE_UI_DIR") or None
    return create_app(dsn=os.environ[db.DSN_ENV], verifier=identity.Verifier.from_env(), bridge=bridge,
                      model=os.environ.get(ENV["model"]), public_url=os.environ[ENV["public_url"]], ui_dir=ui_dir,
                      stages=retrieval.Stages.from_env(), job_workers=jobs.workers_from_env())
