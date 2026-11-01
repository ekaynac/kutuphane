"""Outcome feedback on an exact item version (docs/24 §21, #74): `record_outcome(ref, task_ref, result)`.

- The item is a note (`book@nt_…`, the digest of its bytes) or a passage at its content version
  (`book@ct_…/pf_…/path#ordinal`). An outcome never moves to another version.
- It needs `propose` and `read` on the item's book, decided before and again in one statement at commit. Without
  `read`, "found" or "not found" would tell a propose-only caller that a note with those bytes exists (§6.1).
- The server computes the origin from the write path (`origin.py`, §5.2). The rows are append-only, and a required
  idempotency key makes a retry return the first receipt: a retried outcome that counts twice is a false label.
- An outcome never changes Standing and the "current" predicate never reads it. Reads show counts (§21.2) and can
  filter on them (`min_passed`, `exclude_failed`); a `passed` outcome resets the expiry clock of a note (§8.4).
"""
import re

from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse
from starlette.routing import Route

from . import db, gate, ids, notes, origin as origins, search
from .gate import Actor, NotFound

RESULTS = ("passed", "failed", "reverted", "reopened")
FAILED = ("failed", "reverted")  # a latest outcome that `exclude_failed` excludes
FIELDS = ("ref", "task_ref", "result", "idempotency_key")
TASK_REF = re.compile(r"^[A-Za-z0-9._:/#@+-]{1,200}\Z")


def _args(args) -> tuple:
    if not isinstance(args, dict) or set(args) != set(FIELDS):
        raise ValueError(f"fields: {', '.join(FIELDS)} (all required; idempotency_key makes a retry safe)")
    ref, task_ref, result, key = (notes._string(f, args[f]) for f in FIELDS)
    target = notes._target(ref)
    if not TASK_REF.match(task_ref):
        raise ValueError("task_ref must match [A-Za-z0-9._:/#@+-]{1,200}")
    if result not in RESULTS:
        raise ValueError(f"result must be one of {', '.join(RESULTS)}")
    if not notes.IDEMPOTENCY_KEY.match(key):
        raise ValueError("idempotency_key must match [A-Za-z0-9._:-]{8,128}")
    return target, task_ref, result, key


def _prior(conn, actor: Actor, key: str):
    return conn.execute("SELECT request_sha256, origin FROM outcome WHERE principal = %s "
                        "AND coalesce(on_behalf_of, '') = coalesce(%s, '') AND idempotency_key = %s",
                        (actor.principal, actor.on_behalf_of, key)).fetchone()


def _same_request(prior, digest: bytes) -> None:
    if bytes(prior[0]) != digest:
        raise ids.IdempotencyConflict("idempotency_key reused with another request")


_INSERT = """
INSERT INTO outcome (correlation_id, book, note_seq, content_id, profile_id, path, ordinal, task_ref, result,
                     principal, on_behalf_of, channel, client_id, origin, idempotency_key, request_sha256)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""


def record(conn, actor: Actor, args: dict) -> tuple[dict, bool]:
    """`record_outcome` (§21.1). Returns (receipt, retry): retry is true for an idempotent retry (HTTP 200)."""
    notes._writer(actor)
    target, task_ref, result, key = _args(args)
    ref, book = notes._target_text(target), notes._target_book(target)
    digest = ids.request_digest({"ref": ref, "task_ref": task_ref, "result": result})
    prior = _prior(conn, actor, key)
    if prior:
        _same_request(prior, digest)
    else:
        notes._check_limit(conn, actor)
    obj = f"book:{book}"
    stored, _ = origins.compute(actor, None)

    def work():
        notes._lock(conn)
        again = _prior(conn, actor, key)
        if again:
            _same_request(again, digest)
            return {"ref": ref, "task_ref": task_ref, "result": result, "origin": again[1]}, True
        notes._check_limit(conn, actor)
        if target[0] == "note":
            found = conn.execute("SELECT seq FROM note WHERE book = %s AND id = %s", (book, target[2])).fetchone()
            if found is None:
                raise NotFound(f"no such note: {ref}")
            item = (found[0], None, None, None, None)
        else:
            c = target[1]
            notes._passages_exist(conn, [c])
            item = (None, c.content_id, c.profile_id, c.path, c.ordinal)
        conn.execute(_INSERT, (actor.correlation_id, book, *item, task_ref, result, actor.principal,
                               actor.on_behalf_of, actor.channel, actor.client_id, stored, key, digest))
        return {"ref": ref, "task_ref": task_ref, "result": result, "origin": stored}, False

    return gate.guard_many(conn, actor, {obj: {"propose", "read"}}, work, action="outcome",
                           items={obj: [{"ref": ref}]})


def _ordered(counts: dict) -> dict:
    return {r: counts[r] for r in RESULTS if counts.get(r)}


def counts(conn, seqs, w: int) -> dict:
    """{note seq: {result: count}} over the outcome rows with seq <= w; only non-zero counts, in RESULTS order."""
    out = {}
    for seq, result, n in conn.execute("SELECT note_seq, result, count(*) FROM outcome WHERE note_seq = ANY(%s) "
                                       "AND seq <= %s GROUP BY note_seq, result", (list(seqs), w)):
        out.setdefault(seq, {})[result] = n
    return {seq: _ordered(c) for seq, c in out.items()}


def latest(conn, seqs, w: int) -> dict:
    """{note seq: the result of its latest outcome row with seq <= w}."""
    return dict(conn.execute("SELECT DISTINCT ON (note_seq) note_seq, result FROM outcome WHERE note_seq = ANY(%s) "
                             "AND seq <= %s ORDER BY note_seq, seq DESC", (list(seqs), w)).fetchall())


def passage_counts(conn, cite: search.Citation) -> dict:
    """{result: count} for one passage at its content version."""
    return _ordered(dict(conn.execute(
        "SELECT result, count(*) FROM outcome WHERE book = %s AND content_id = %s AND profile_id = %s AND path = %s "
        "AND ordinal = %s GROUP BY result",
        (cite.book, cite.content_id, cite.profile_id, cite.path, cite.ordinal)).fetchall()))


# --- MCP and HTTP (feature hooks, docs/24 §16 P0) ------------------------------------------------------------

def op_record(dsn, actor: Actor, args) -> tuple[dict, bool]:
    with db.connect(dsn) as conn:
        return record(conn, actor, args)


def register_mcp(mcp, deps) -> None:
    @mcp.tool()
    @deps.mcp_errors
    async def record_outcome(ref: str, task_ref: str, result: str, idempotency_key: str) -> dict:
        """Record how an item worked in a task (needs propose and read on its book). ref: a note (book@nt_…) or a
        passage handle; both name one exact version. task_ref: your task or run id. result: passed, failed,
        reverted or reopened. Outcomes are counts on the item; they never change its Standing. A retry with the
        same idempotency_key returns the first receipt."""
        receipt, _ = await run_in_threadpool(op_record, deps.dsn, deps.mcp_actor(),
                                             {"ref": ref, "task_ref": task_ref, "result": result,
                                              "idempotency_key": idempotency_key})
        return receipt


def http_routes(deps, endpoint) -> list[Route]:
    async def h_record(request, actor):
        receipt, retry = await run_in_threadpool(op_record, deps.dsn, actor, await notes._body(request))
        return JSONResponse(receipt, status_code=200 if retry else 201)

    return [Route("/v1/outcomes", endpoint(h_record), methods=["POST"])]
