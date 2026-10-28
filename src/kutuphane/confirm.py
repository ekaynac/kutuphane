"""D70 R3 "my words" confirmation and R7 withdrawal (docs/25 §7, migration 024).

- **A request** is a propose write whose `human` or `assisted` claim was refused (`write_record.confirmable`). It is
  open for `KUTUPHANE_CONFIRM_HOURS` (24) hours after its write. The propose receipt and the MCP tool
  `confirm_origin` give its URL in curator web (`KUTUPHANE_CURATOR_URL` + `/c/<book>/<nt_id>`): the URL holds no
  secret and gives no right.
- **Only a person confirms**, in curator web, with a `confirm` passkey act over the exact note digest, the request,
  the claim and the writer. `human` ("These are my words, verbatim") only by the request's person (the user acted
  for, or the user who wrote: a database key); `assisted` ("I reviewed it in substance") by the person or by a
  direct curator of the book. The confirmer must also hold `read` directly.
- **One changed byte is another note**: a confirmation names one note id and never moves, also not along
  `supersedes`.
- **R7**: only the confirmer withdraws the latest confirmation, with a `withdraw` act. The shown origin
  (`origin.shown`) then falls back to the write-path value; an older confirmation never comes back.
- **MCP**: `confirm_origin` never uses a form. A 2026-07-28 client with the `elicitation.url` capability gets an
  `InputRequiredResult` with one URL-mode request on the first round; the retry gets the state. An `accept` only
  means "the URL was opened": it confirms nothing.
"""
import json
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from mcp.server.mcpserver import Context
from mcp_types import ElicitRequest, ElicitRequestURLParams, InputRequiredResult
from mcp_types.version import is_version_at_least

from . import authz, canonical, curation, db, gate, notes
from . import origin as origins
from .gate import Actor

HOURS_ENV = "KUTUPHANE_CONFIRM_HOURS"
URL_ENV = "KUTUPHANE_CURATOR_URL"
DEFAULT_HOURS = 24
URL_MODE_VERSION = "2026-07-28"
CLAIMS = origins.CONFIRMABLE
WORDS = {"human": "These are my words, verbatim (I wrote or dictated them).",
         "assisted": "A model wrote or reworded this. I reviewed it in substance."}
ELICIT_MESSAGE = ("Open this page in your own browser to confirm whose words this note holds. "
                  "Only you can confirm it there, with your passkey.")


def hours() -> int:
    """The request lifetime in hours (docs/25 §7.5, §14 Q8)."""
    raw = os.environ.get(HOURS_ENV) or str(DEFAULT_HOURS)  # empty is not set, as `${…:-24}` in compose (G13)
    try:
        value = int(raw)
    except ValueError:
        raise RuntimeError(f"{HOURS_ENV} must be a whole number of hours") from None
    if not 1 <= value <= 24 * 30:
        raise RuntimeError(f"{HOURS_ENV} must be 1..720")
    return value


def url(ref: str) -> str | None:
    """The confirmation page of a note in curator web, or None when `KUTUPHANE_CURATOR_URL` is not set."""
    base = os.environ.get(URL_ENV, "").rstrip("/")
    if not base:
        return None
    book, note_id = notes.parse_ref(ref)
    return f"{base}/c/{book}/{note_id}"


def _iso(t: datetime) -> str:
    return t.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class Request:
    write: int
    entered_by: str            # the writer of the request
    person: str | None         # who may confirm `human` (024 `write_record.person`)
    on_behalf_of: str | None
    client_id: str | None
    requested: str             # the claim the writer asked for
    at: datetime
    expires_at: datetime
    open: bool                 # at clock_timestamp()

    def out(self) -> dict:
        return {"write": self.write, "entered_by": self.entered_by, "on_behalf_of": self.on_behalf_of,
                "client_id": self.client_id, "requested": self.requested, "at": _iso(self.at),
                "expires_at": _iso(self.expires_at), "open": self.open}


_REQUESTS = """
SELECT w.seq, w.principal, w.person, w.on_behalf_of, w.client_id, w.origin_requested, w.at,
       w.at + make_interval(hours => %(h)s), clock_timestamp() < w.at + make_interval(hours => %(h)s)
  FROM write_record w
 WHERE w.note_seq = %(seq)s AND w.confirmable AND (%(write)s::bigint IS NULL OR w.seq = %(write)s)
 ORDER BY w.seq DESC
"""


def requests_of(conn, note_seq: int, write: int | None = None) -> list[Request]:
    """The requests of a note, newest first."""
    return [Request(*r) for r in conn.execute(_REQUESTS, {"seq": note_seq, "write": write, "h": hours()})]


def receipt(conn, write_seq: int, ref: str) -> dict:
    """The `confirmation` key of a propose receipt whose write is a request (docs/25 §7.1)."""
    expires = conn.execute("SELECT at + make_interval(hours => %s) FROM write_record WHERE seq = %s",
                           (hours(), write_seq)).fetchone()[0]
    return {"url": url(ref), "expires_at": _iso(expires)}


def claims_for(conn, principal: str, request: Request, book: str) -> list[str]:
    """The claims that `principal` may confirm for this request now (docs/25 §7.4): `read` directly on the book,
    and then `human` + `assisted` for the request's person, or `assisted` for a direct curator."""
    obj = f"book:{book}"
    if not authz.direct(conn, principal, obj, "read").allowed:
        return []
    if request.person is not None and request.person == principal:
        return list(CLAIMS)
    return ["assisted"] if authz.direct(conn, principal, obj, "curate").allowed else []


def _live(conn, note_seq: int):
    """(seq, claim, entered_by, confirmed_by, write) of the latest confirmation of a note, if it is not withdrawn."""
    return conn.execute(
        "SELECT c.seq, c.claim, c.entered_by, c.confirmed_by, c.write_seq FROM origin_confirmation c "
        "WHERE c.note_seq = %s AND NOT EXISTS (SELECT 1 FROM origin_withdrawal x WHERE x.confirmation = c.seq) "
        "AND c.seq = (SELECT max(seq) FROM origin_confirmation WHERE note_seq = %s)", (note_seq, note_seq)).fetchone()


def state(conn, note_seq: int, ref: str) -> dict:
    """The `confirmation` of `confirm_origin` (docs/25 §7.2): confirmed (a live confirmation), open (the latest
    request is open), expired (requests, none open) or none."""
    live = _live(conn, note_seq)
    if live:
        return {"state": "confirmed", "claim": live[1], "entered_by": live[2], "confirmed_by": live[3]}
    found = requests_of(conn, note_seq)
    if not found:
        return {"state": "none"}
    latest = found[0]
    if latest.open:
        link = url(ref)
        return {"state": "open", **({"url": link} if link else {}), "expires_at": _iso(latest.expires_at),
                "claim": latest.requested, "entered_by": latest.entered_by}
    return {"state": "expired", "expires_at": _iso(latest.expires_at), "claim": latest.requested,
            "entered_by": latest.entered_by}


# --- Core: confirm_origin and GET /v1/notes/{book}/{id}/confirmation (a read; no write) -----------------------

def confirmation(conn, actor: Actor, ref: str) -> dict:
    """`read` on the note's book, decided with the gate (as `open_citation`)."""
    book, note_id = notes.parse_ref(ref)

    def fetch():
        row = conn.execute("SELECT seq FROM note WHERE book = %s AND id = %s", (book, note_id)).fetchone()
        if row is None:
            raise gate.NotFound(ref)
        shown = origins.shown(conn, [row[0]], None)[row[0]][0]
        return {"ref": ref, "origin": shown, "confirmation": state(conn, row[0], ref)}

    return gate.guard(conn, actor, f"book:{book}", ["read"], fetch, action="confirmation", items=[{"ref": ref}])


def op_confirmation(dsn, actor: Actor, ref) -> dict:
    if not isinstance(ref, str):
        raise ValueError("ref must be a note reference (book@nt_…)")
    with db.connect(dsn) as conn:
        return confirmation(conn, actor, ref)


def _url_mode(ctx: Context) -> bool:
    version, caps = ctx.protocol_version, ctx.client_capabilities
    return bool(version and is_version_at_least(version, URL_MODE_VERSION) and caps is not None
                and caps.elicitation is not None and caps.elicitation.url is not None)


def elicit(out: dict) -> InputRequiredResult:
    """One URL-mode elicitation (never a form). The request state is sealed by the SDK (`RequestStateSecurity`)."""
    params = ElicitRequestURLParams(message=ELICIT_MESSAGE, url=out["confirmation"]["url"],
                                    elicitation_id="cf_" + uuid.uuid4().hex)
    return InputRequiredResult(input_requests={"confirm": ElicitRequest(params=params)},
                               request_state=json.dumps({"ref": out["ref"]}))


def register_mcp(mcp, deps) -> None:
    from starlette.concurrency import run_in_threadpool

    @mcp.tool()
    @deps.mcp_errors
    async def confirm_origin(ref: str, ctx: Context) -> dict | InputRequiredResult:
        """Ask the person to confirm whose words a note holds (D70 R3; needs read on the note's book). Only the
        person can confirm, in curator web with a passkey; this tool never confirms. Returns {ref, origin,
        confirmation: {state: open, confirmed, expired or none, url?, expires_at?, claim?, entered_by?,
        confirmed_by?}}. Show the url to the person."""
        out = await run_in_threadpool(op_confirmation, deps.dsn, deps.mcp_actor(), ref)
        if ctx.request_state is None and out["confirmation"]["state"] == "open" and out["confirmation"].get("url") \
                and _url_mode(ctx):
            return elicit(out)
        return out  # the retry (an `accept` changes nothing), and every other client: the state now


def http_routes(deps, endpoint) -> list:
    from starlette.concurrency import run_in_threadpool
    from starlette.responses import JSONResponse
    from starlette.routing import Route

    async def h_confirmation(request, actor):
        p = request.path_params
        out = await run_in_threadpool(op_confirmation, deps.dsn, actor, f"{p['book']}@{p['id']}")
        return JSONResponse(out)

    return [Route("/v1/notes/{book}/{id}/confirmation", endpoint(h_confirmation), methods=["GET"])]


# --- curator web: the requests, the page, the confirm and withdraw acts -------------------------------------------

def _note(conn, principal: str, ref) -> tuple[str, str, int]:
    """The note of `ref` for `principal`: `read` directly on the book of the parsed ref first, so a person without it
    gets one refusal whether the note exists, has a request or has a confirmation (security review #17)."""
    if not isinstance(ref, str):
        raise ValueError("ref must be a note reference (book@nt_…)")
    book, _ = notes.parse_ref(ref)
    if not authz.direct(conn, principal, f"book:{book}", "read").allowed:
        raise gate.Denied(f"{principal} does not hold read on book:{book}")
    book, note_id, row = curation._note(conn, ref)
    return book, note_id, row[0]


def _replaces_another(live, principal: str) -> bool:
    """R7: a live confirmation by another person stays until its confirmer withdraws it."""
    return live is not None and live[3] != principal


def _page_item(conn, principal: str, book: str, note_id: str, seq: int, request: Request | None) -> dict:
    computed, body = canonical.canonical_of(conn, seq)
    whole = computed == note_id
    shown = origins.shown(conn, [seq], None)[seq]
    live = _live(conn, seq)
    read = authz.allowed(conn, principal, None, ["read"]).objects("read")
    cited = conn.execute("SELECT cite_book FROM note_citation WHERE note_seq = %s ORDER BY n", (seq,)).fetchall()
    # docs/25 §6.1: a citation or a link into a book that this person may not read shows no name and no text
    citations = [c if b is None or f"book:{b}" in read else None for c, (b,) in zip(body["citations"], cited)]
    links = [link if f"book:{link['target'].split('@')[0]}" in read else {"type": link["type"], "target": None}
             for link in body["links"]]
    return {"ref": f"{book}@{note_id}", "book": book, "kind": body["kind"], "role": notes.KIND_ROLE[body["kind"]],
            "text": body["text"], "class_key": body["class_key"], "scope": body["scope"], "commit": body["commit"],
            "citations": citations, "links": links, "decision": body.get("decision"),
            "integrity": None if whole else "note-integrity",
            "origin": shown[0], "entered_by": shown[1], "confirmed_by": shown[2],
            "request": request.out() if request else None,
            "claims": [{"claim": c, "words": WORDS[c]} for c in claims_for(conn, principal, request, book)]
            if request and request.open and whole and not _replaces_another(live, principal) else [],
            "withdraw": live[0] if live and live[3] == principal else None}


def requests_for(conn, principal: str) -> list[dict]:
    """The open requests that `principal` may confirm (docs/25 §7.4): the latest open request of each note."""
    out = []
    for seq, book, note_id in conn.execute(
            "SELECT DISTINCT ON (w.note_seq) n.seq, n.book, n.id FROM write_record w JOIN note n ON n.seq = w.note_seq "
            "WHERE w.confirmable AND clock_timestamp() < w.at + make_interval(hours => %s) "
            "ORDER BY w.note_seq, w.seq DESC", (hours(),)).fetchall():
        request = requests_of(conn, seq)[0]
        if request.open and claims_for(conn, principal, request, book) and _live(conn, seq) is None:
            out.append(_page_item(conn, principal, book, note_id, seq, request))
    return out


def page(conn, principal: str, ref: str) -> dict:
    """One note for the confirmation page: who asks, the full text and canonical fields after the digest check, the
    claims this person may give now, and whether this person may withdraw the live confirmation."""
    book, note_id, seq = _note(conn, principal, ref)
    found = requests_of(conn, seq)
    request = next((r for r in found if r.open), found[0] if found else None)
    return _page_item(conn, principal, book, note_id, seq, request)


def _open_request(conn, principal: str, seq: int, book: str, claim, write=None) -> Request:
    if claim not in CLAIMS:
        raise ValueError(f"claim must be one of {', '.join(CLAIMS)}")
    if write is not None and type(write) is not int:
        raise ValueError("write must be an integer")
    found = requests_of(conn, seq, write)
    if not found:
        raise ValueError("no confirmation request for this note: the writer did not ask for human or assisted")
    request = next((r for r in found if r.open), None)
    if request is None:
        raise ValueError(f"request-expired: the request is open {hours()} hours after its write; propose the same "
                         "bytes again for a new one")
    if _replaces_another(_live(conn, seq), principal):
        raise gate.Denied("this note has a live confirmation by another person: only that person withdraws it (R7)")
    allowed = claims_for(conn, principal, request, book)
    if claim not in allowed:
        raise gate.Denied(f"{principal} may not confirm {claim} for this note"
                          + (" (human: only the person the words are entered for)" if claim == "human" else ""))
    return request


def confirm_fields(conn, principal: str, body: dict) -> dict:
    """The `confirm` statement (docs/25 §5.2): item {ref, id, write}, claim, entered_by. Nothing is stored here."""
    book, note_id, seq = _note(conn, principal, body.get("ref"))
    curation.check_integrity(conn, seq, note_id)
    request = _open_request(conn, principal, seq, book, body.get("claim"), body.get("write"))
    return {"item": {"ref": f"{book}@{note_id}", "id": note_id, "write": request.write},
            "claim": body["claim"], "entered_by": request.entered_by}


def confirm_act(conn, act) -> dict:
    """The row of a verified `confirm` act (docs/25 §5.4 step 7), in the act's transaction under the memory lock:
    the digest, the open request and the right are decided again now; the database checks the statement."""
    p = act.payload
    book, note_id, seq = _note(conn, act.principal, p["item"]["ref"])
    if note_id != p["item"]["id"]:
        raise curation.IntegrityRefused("note-integrity: the statement names another note id")
    curation.check_integrity(conn, seq, note_id)
    request = _open_request(conn, act.principal, seq, book, p["claim"], p["item"]["write"])
    if request.entered_by != p["entered_by"]:
        raise ValueError("the statement names another writer")
    row = conn.execute("INSERT INTO origin_confirmation (note_seq, book, note_id, write_seq, claim, entered_by, "
                       "confirmed_by, act) VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING seq",
                       (seq, book, note_id, request.write, p["claim"], request.entered_by, act.principal,
                        act.seq)).fetchone()
    return {"act": act.seq, "confirmation": row[0], "ref": f"{book}@{note_id}", "origin": p["claim"],
            "entered_by": request.entered_by, "confirmed_by": act.principal}


def withdraw_fields(conn, principal: str, body: dict) -> dict:
    """The `withdraw` statement: the live confirmation of the note and the note; only its confirmer (R7)."""
    book, note_id, seq = _note(conn, principal, body.get("ref"))
    live = _live(conn, seq)
    if live is None:
        raise ValueError("this note has no live confirmation")
    if live[3] != principal:
        raise gate.Denied("only the confirmer withdraws a confirmation (R7)")
    return {"confirmation": live[0], "item": {"ref": f"{book}@{note_id}", "id": note_id}}


def withdraw_act(conn, act) -> dict:
    p = act.payload
    book, note_id, seq = _note(conn, act.principal, p["item"]["ref"])
    live = _live(conn, seq)
    if note_id != p["item"]["id"] or live is None or live[0] != p["confirmation"]:
        raise curation.Changed("the confirmation changed since it was shown: reload")
    if live[3] != act.principal:
        raise gate.Denied("only the confirmer withdraws a confirmation (R7)")
    row = conn.execute("INSERT INTO origin_withdrawal (confirmation, withdrawn_by, act) VALUES (%s, %s, %s) "
                       "RETURNING seq", (live[0], act.principal, act.seq)).fetchone()
    return {"act": act.seq, "withdrawal": row[0], "ref": f"{book}@{note_id}",
            "origin": origins.shown(conn, [seq], None)[seq][0]}
