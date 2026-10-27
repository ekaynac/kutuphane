"""Curator web (docs/25 §3, §5, §6; D72): the phone page. A separate process with its own database role
(`kutuphane_curator_web`, deploy/db-roles-curator.sql) and its own origin; no MCP, no bearer token, no book file.

A session comes from a passkey login (or, once, from an enrollment code); it gives sight of the pending notes. Only an
act changes anything: a passkey assertion with user verification over a stored statement, verified and applied in one
transaction under the memory lock (docs/25 §5.4). Every state-changing request needs this origin and JSON.

    uvicorn --factory kutuphane.curatorweb:app_from_env      (or: kutuphane curator web)
"""
import json
import os
import uuid
from pathlib import Path

import psycopg
from psycopg.types.json import Jsonb
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse
from starlette.concurrency import run_in_threadpool
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from . import curation, curatorqueue, db, gate, notes, passkey
from .server import SecurityHeaders

COOKIE = "__Host-kc"
DSN_ENV = "KUTUPHANE_CURATOR_WEB_DSN"
UI_DIR = Path(__file__).parent / "curator_ui"
SESSION_SECONDS = 8 * 3600


class Refused(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


STATUS = ((passkey.CeremonyRefused, 403), (curation.IntegrityRefused, 403), (gate.Denied, 403),
          (curation.Changed, 409), (gate.NotFound, 404), (ValueError, 400))


def _status(exc: Exception) -> int | None:
    return next((code for kind, code in STATUS if isinstance(exc, kind)), None)


def _log(conn, principal: str, action: str, allowed: bool, reason: str, items=None, correlation=None) -> None:
    conn.execute("INSERT INTO access_event (correlation_id, principal, action, object, mode, allowed, reason, items) "
                 "VALUES (%s, %s, %s, 'curator-web', 'curate', %s, %s, %s)",
                 (correlation or uuid.uuid4().hex, principal, action, allowed, reason[:500],
                  Jsonb(items) if items is not None else None))


def _shown_whole(conn, principal: str, items) -> None:
    """An approval needs every part of the note that its id covers shown to the person (review #16 finding 1): a
    citation or a creation link into a book that the person cannot read now refuses it, at the options and the act."""
    for item in items if isinstance(items, list) else []:
        if isinstance(item, dict) and item.get("to") == "approved" and isinstance(item.get("ref"), str):
            book, note_id = notes.parse_ref(item["ref"])
            row = conn.execute("SELECT seq FROM note WHERE book = %s AND id = %s", (book, note_id)).fetchone()
            if row and curatorqueue.unseen_parts(conn, principal, row[0]):
                raise gate.Denied(f"{item['ref']} has a part in a book you cannot read: it cannot be approved here")


def _standing(conn, act: passkey.Act) -> dict:
    """The rows of a `standing` statement (docs/25 §5.4 step 7, §6.5). The receipt adds, after the act, each note's
    suggestions and, for a sample, its delegation (§5.4 step 8, §6.4, §8.4)."""
    items = [{"ref": i["ref"], "to": i["to"], "was": i["was"]} for i in act.payload["items"]]
    _shown_whole(conn, act.principal, items)
    out = curation.apply(conn, principal=act.principal, items=items, reason=act.payload["reason"], act=act.seq,
                         need_read=True, check_was=True, integrity=True)
    return {"act": act.seq, "items": curatorqueue.receipt(conn, out)}


HANDLERS = {"standing": _standing}  # slices R and D add confirm, withdraw, delegate, end_delegation


def _standing_fields(conn, principal: str, body: dict) -> dict:
    items, reason = body.get("items"), body.get("reason")
    _shown_whole(conn, principal, items)
    prepared = curation.prepare(conn, principal=principal, items=items if isinstance(items, list) else None,
                                reason=reason, need_read=True, integrity=True)
    return {"items": sorted(({"ref": i["ref"], "id": i["id"], "was": i["was"], "to": i["to"]} for i in prepared),
                            key=lambda i: i["ref"]),
            "reason": reason}


FIELDS = {"standing": _standing_fields}


def create_app(*, dsn: str, cfg: passkey.Config, ui_dir: Path = UI_DIR) -> Starlette:
    def body_of(request: Request, raw: bytes) -> dict:
        if request.headers.get("origin") != cfg.origin:
            raise Refused(403, "this origin only")
        if request.headers.get("content-type", "").split(";")[0].strip() != "application/json":
            raise Refused(415, "JSON only")
        try:
            body = json.loads(raw or b"{}")
        except ValueError:
            raise Refused(400, "malformed JSON") from None
        if not isinstance(body, dict):
            raise Refused(400, "malformed JSON")
        return body

    def session_of(conn, request: Request, login: str = "passkey"):
        found = passkey.session(conn, request.cookies.get(COOKIE))
        if found is None or found[2] != login:
            raise Refused(401, "no session")
        return found

    def answer(fn):
        """Run a handler with one connection; a refusal is a JSON error with a safe message."""
        async def endpoint(request: Request):
            raw = await request.body() if request.method == "POST" else b""

            def run():
                try:
                    with db.connect(dsn) as conn:
                        return fn(conn, request, raw)
                except Refused as exc:
                    return JSONResponse({"error": str(exc)}, status_code=exc.status)
                except psycopg.Error:
                    return JSONResponse({"error": "refused by the database"}, status_code=403)
                except Exception as exc:  # noqa: BLE001 — a known class becomes its status; others are 500
                    code = _status(exc)
                    if code is None:
                        raise
                    return JSONResponse({"error": str(exc)}, status_code=code)
            return await run_in_threadpool(run)
        return endpoint

    def with_cookie(payload: dict, token: str, seconds: int) -> JSONResponse:
        response = JSONResponse(payload)
        response.set_cookie(COOKIE, token, max_age=seconds, path="/", secure=True, httponly=True, samesite="strict")
        return response

    # --- pages ---------------------------------------------------------------------------------------------------
    def page(_request):
        return FileResponse(ui_dir / "index.html")

    # --- enrollment ----------------------------------------------------------------------------------------------
    def enroll_session(conn, request, raw):
        body = body_of(request, raw)
        with conn.transaction():
            token, principal = passkey.enrollment_session(conn, body.get("code"))
        return with_cookie({"principal": principal}, token, 15 * 60)

    def enroll_options(conn, request, raw):
        body_of(request, raw)
        sid, principal, _ = session_of(conn, request, "enrollment")
        with conn.transaction():
            cid, options = passkey.registration_options(conn, cfg, sid, principal)
        return JSONResponse({"challenge_id": cid, "publicKey": options})

    def enroll_register(conn, request, raw):
        body = body_of(request, raw)
        sid, principal, _ = session_of(conn, request, "enrollment")
        with conn.transaction():
            out = passkey.register(conn, cfg, sid, principal, body.get("challenge_id"), body.get("credential"))
        response = JSONResponse(out)
        response.delete_cookie(COOKIE, path="/", secure=True, httponly=True, samesite="strict")
        return response

    # --- login ---------------------------------------------------------------------------------------------------
    def login_options(conn, request, raw):
        body_of(request, raw)
        with conn.transaction():
            cid, options = passkey.login_options(conn, cfg)
        return JSONResponse({"challenge_id": cid, "publicKey": options})

    def login(conn, request, raw):
        body = body_of(request, raw)
        with conn.transaction():
            notes._lock(conn)  # the counter of a passkey is shared by logins and acts
            token, principal = passkey.login(conn, cfg, body.get("challenge_id"), body.get("credential"))
        return with_cookie({"principal": principal}, token, SESSION_SECONDS)

    def logout(conn, request, raw):
        body_of(request, raw)
        found = passkey.session(conn, request.cookies.get(COOKIE))
        if found:
            passkey.logout(conn, found[0])
        response = JSONResponse({"logged_out": True})
        response.delete_cookie(COOKIE, path="/", secure=True, httponly=True, samesite="strict")
        return response

    def me(conn, request, _raw):
        return JSONResponse({"principal": session_of(conn, request)[1]})

    # --- the queue (docs/25 §6): risk order at a watermark; no suggestion and no sample mark ----------------------
    def _int_param(request, name):
        value = request.query_params.get(name)
        if value is None:
            return None
        if not value.isdigit():
            raise Refused(400, f"{name} must be an integer")
        return int(value)

    def queue(conn, request, _raw):
        _, principal, _ = session_of(conn, request)
        with conn.transaction():
            out = curatorqueue.queue(conn, principal, w=_int_param(request, "w"),
                                     cursor=request.query_params.get("cursor"), channel="http")
        return JSONResponse(out)

    def note_view(conn, request, _raw):
        _, principal, _ = session_of(conn, request)
        ref = f"{request.path_params['book']}@{request.path_params['id']}"
        with conn.transaction():
            out = curatorqueue.note(conn, principal, ref, w=_int_param(request, "w"), channel="http")
        return JSONResponse(out)

    # --- acts ----------------------------------------------------------------------------------------------------
    def act_options(conn, request, raw):
        body = body_of(request, raw)
        sid, principal, _ = session_of(conn, request)
        action = body.get("action")
        if action not in FIELDS:
            raise Refused(400, f"action must be one of {', '.join(FIELDS)}")
        with conn.transaction():
            fields = FIELDS[action](conn, principal, body)
            cid, statement, options = passkey.act_options(conn, cfg, sid, principal, action, fields)
        return JSONResponse({"challenge_id": cid, "statement": statement, "publicKey": options})

    def act(conn, request, raw):
        body = body_of(request, raw)
        token = request.cookies.get(COOKIE)
        principal = None
        correlation = uuid.uuid4().hex
        try:
            with conn.transaction():
                notes._lock(conn)  # docs/25 §5.4: the lock first, then every time at clock_timestamp()
                sid, principal, _ = session_of(conn, request)
                act_ = passkey.verify_act(conn, cfg, sid, principal, body.get("challenge_id"), body.get("credential"),
                                          body.get("shown_ms"))
                out = HANDLERS[act_.action](conn, act_)
                _log(conn, principal, "curate", True, act_.action, [
                    {"ref": i["ref"], "standing_seq": i["event_seq"]} for i in out.get("items", [])], correlation)
            return JSONResponse(out)
        except Exception as exc:
            code = exc.status if isinstance(exc, Refused) else _status(exc)
            if code is None and not isinstance(exc, psycopg.Error):
                raise
            if principal is not None:  # the refusal record, in its own transaction (reason only)
                _log(conn, principal, "curate", False, str(exc) or type(exc).__name__, correlation=correlation)
            if isinstance(exc, psycopg.Error):
                raise Refused(403, "refused by the database") from None
            raise

    routes = [
        Route("/", page), Route("/enroll", page),
        Route("/api/enroll/session", answer(enroll_session), methods=["POST"]),
        Route("/api/enroll/options", answer(enroll_options), methods=["POST"]),
        Route("/api/enroll", answer(enroll_register), methods=["POST"]),
        Route("/auth/passkey/options", answer(login_options), methods=["POST"]),
        Route("/auth/passkey", answer(login), methods=["POST"]),
        Route("/auth/logout", answer(logout), methods=["POST"]),
        Route("/api/me", answer(me)),
        Route("/api/queue", answer(queue)),
        Route("/api/note/{book}/{id}", answer(note_view)),
        Route("/api/act/options", answer(act_options), methods=["POST"]),
        Route("/api/act", answer(act), methods=["POST"]),
        Mount("/static", StaticFiles(directory=ui_dir)),
    ]
    app = Starlette(routes=routes)
    app.add_middleware(SecurityHeaders)
    return app


def app_from_env() -> Starlette:
    """uvicorn --factory kutuphane.curatorweb:app_from_env"""
    dsn = os.environ.get(DSN_ENV)
    if not dsn:
        raise RuntimeError(f"curator web not configured: set {DSN_ENV} (the kutuphane_curator_web role)")
    cfg = passkey.Config.from_env()
    with db.connect(dsn) as conn:
        waiting = db.pending(conn)
    if waiting:
        raise RuntimeError(f"database needs migrations ({', '.join(waiting)}): run `kutuphane migrate`")
    return create_app(dsn=dsn, cfg=cfg)
