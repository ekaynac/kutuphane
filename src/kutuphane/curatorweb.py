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

from . import authz, curation, db, delegation, gate, notes, passkey
from .server import SecurityHeaders

COOKIE = "__Host-kc"
DSN_ENV = "KUTUPHANE_CURATOR_WEB_DSN"
UI_DIR = Path(__file__).parent / "curator_ui"
PENDING_LIMIT = 50
SESSION_SECONDS = 8 * 3600

_PENDING = """
SELECT n.seq, n.book, n.id, n.kind, n.body, n.class_key, n.scope_repo, n.scope_branch, n.scope_paths, n.written_at,
       e.seq, e.value,
       ARRAY(SELECT jsonb_build_object('principal', w.principal, 'on_behalf_of', w.on_behalf_of,
                                       'client_id', w.client_id, 'origin', w.origin)
               FROM write_record w WHERE w.note_seq = n.seq AND w.action = 'propose' ORDER BY w.seq)
  FROM note n
  LEFT JOIN LATERAL (SELECT seq, value FROM standing_event s WHERE s.note_seq = n.seq ORDER BY s.seq DESC LIMIT 1) e
         ON true
 WHERE n.book = ANY(%s) AND (e.value IS NULL OR e.value = 'pending')
 ORDER BY n.seq
 LIMIT %s
"""


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


def _standing(conn, act: passkey.Act) -> dict:
    """The rows of a `standing` statement (docs/25 §5.4 step 7, §6.5)."""
    items = [{"ref": i["ref"], "to": i["to"], "was": i["was"]} for i in act.payload["items"]]
    out = curation.apply(conn, principal=act.principal, items=items, reason=act.payload["reason"], act=act.seq,
                         need_read=True, check_was=True, integrity=True)
    return {"act": act.seq, "items": out}


HANDLERS = {"standing": _standing}  # slices R and D add confirm, withdraw, delegate, end_delegation


def _standing_fields(conn, principal: str, body: dict) -> dict:
    items, reason = body.get("items"), body.get("reason")
    prepared = curation.prepare(conn, principal=principal, items=items if isinstance(items, list) else None,
                                reason=reason, need_read=True, integrity=True)
    return {"items": sorted(({"ref": i["ref"], "id": i["id"], "was": i["was"], "to": i["to"]} for i in prepared),
                            key=lambda i: i["ref"]),
            "reason": reason}


FIELDS = {"standing": _standing_fields}
# docs/25 §8 (slice D): a `delegate` act creates one delegation; an `end_delegation` act ends one.
HANDLERS.update({"delegate": delegation.apply_delegate, "end_delegation": delegation.apply_end})
FIELDS.update({"delegate": delegation.delegate_fields, "end_delegation": delegation.end_fields})


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

    # --- the pending notes (slice Q replaces the order with the risk order of §6.2) -------------------------------
    def pending(conn, request, _raw):
        _, principal, _ = session_of(conn, request)
        rights = authz.allowed(conn, principal, None, ["curate", "read"])
        books = sorted(o.removeprefix("book:") for o in rights.objects("curate") & rights.objects("read"))
        items, delivered = [], []
        for (seq, book, note_id, kind, text, class_key, repo, branch, paths, written, ev, _value,
             writers) in conn.execute(_PENDING, (books, PENDING_LIMIT)).fetchall():
            ref = f"{book}@{note_id}"
            whole = notes.canonical_of(conn, seq)[0] == note_id
            items.append({"ref": ref, "book": book, "kind": kind, "role": notes.KIND_ROLE[kind], "text": text,
                          "class_key": class_key, "scope": {"repo": repo, "branch": branch, "paths": list(paths)}
                          if repo else None, "written_at": written.isoformat(), "was": ev, "writers": writers,
                          "integrity": None if whole else "note-integrity"})
            delivered.append({"ref": ref, "standing_seq": ev})
        _log(conn, principal, "curate_view", True, "pending notes", delivered)
        return JSONResponse({"books": books, "items": items})

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

    # --- delegations (docs/25 §8; slice D) ------------------------------------------------------------------------
    def curated_books(conn, principal: str) -> list[str]:
        rights = authz.allowed(conn, principal, None, ["curate", "read"])
        return sorted(o.removeprefix("book:") for o in rights.objects("curate") & rights.objects("read"))

    def delegations(conn, request, _raw):
        """The delegations of the person's books, and the shadow agreement of each decider spec per evidence class:
        what the person sees before signing a `delegate` act (§8.2)."""
        _, principal, _ = session_of(conn, request)
        books = curated_books(conn, principal)
        return JSONResponse({"books": books, "kinds": list(delegation.EVIDENCE_KINDS), "defaults": delegation.DEFAULTS,
                             "max_days": delegation.MAX_DAYS, "delegations": delegation.list_(conn, books),
                             "shadow": delegation.shadow_classes(conn, books)})

    def delegation_view(conn, request, _raw):
        """One delegation: the report (§8.6) and the review list of the notes it approved (§8.4)."""
        _, principal, _ = session_of(conn, request)
        out = delegation.report(conn, request.path_params["id"])
        if out["delegation"]["book"] not in curated_books(conn, principal):
            raise gate.NotFound(f"no such delegation: {request.path_params['id']}")
        out["review"] = delegation.review_list(conn, request.path_params["id"])
        _log(conn, principal, "curate_view", True, f"delegation {request.path_params['id']}",
             [{"ref": r["ref"], "standing_seq": r["was"]} for r in out["review"]])
        return JSONResponse(out)

    routes = [
        Route("/", page), Route("/enroll", page),
        Route("/api/enroll/session", answer(enroll_session), methods=["POST"]),
        Route("/api/enroll/options", answer(enroll_options), methods=["POST"]),
        Route("/api/enroll", answer(enroll_register), methods=["POST"]),
        Route("/auth/passkey/options", answer(login_options), methods=["POST"]),
        Route("/auth/passkey", answer(login), methods=["POST"]),
        Route("/auth/logout", answer(logout), methods=["POST"]),
        Route("/api/me", answer(me)),
        Route("/api/pending", answer(pending)),
        Route("/api/act/options", answer(act_options), methods=["POST"]),
        Route("/api/act", answer(act), methods=["POST"]),
        Route("/api/delegations", answer(delegations)),
        Route("/api/delegations/{id}", answer(delegation_view)),
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
