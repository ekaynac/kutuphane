"""`ask_library` as a durable background job (docs/24 §12.2, `018_ask_job.sql`).

- A submission stores the request and returns a job id at once. An idempotency key, scoped to
  (principal, on_behalf_of), makes a retry return the original job; the same key with another request is refused.
  At most `MAX_OPEN` queued or running jobs per principal.
- Workers run in the server process. They claim with `FOR UPDATE SKIP LOCKED`, renew the lease while the ask runs,
  and run `answers.ask` with the job's principal and on_behalf_of, so the rights at run time apply. A lease is renewed
  only while it is running and unexpired: an ended lease is never revived.
- A running job whose lease ended becomes `failed: interrupted`. It never runs again (model cost), and its worker
  stores no answer.
- A cancel stops a queued job at once; a running job checks it (and its lease) before the model call and before it
  stores the answer. The answer's insert, a last check under the job-row lock and the success update are one
  transaction, so a cancel or an expiry that commits before it wins and the answer is rolled back.
- Status, result and cancel have the visibility of `answers.reopen`; anyone else gets "not found". The result is
  `answers.reopen` of the stored answer, so current rights decide it.
- Finished jobs are deleted after `RETENTION`, with their idempotency keys; the answer and its audit stay.
"""
import dataclasses
import logging
import os
import re
import threading
import uuid

from psycopg.types.json import Jsonb

from . import answers, db, ids, search
from .gate import Actor, NotFound

log = logging.getLogger(__name__)

WORKERS_ENV = "KUTUPHANE_JOB_WORKERS"
DEFAULT_WORKERS = 1
MAX_OPEN = 3
LEASE_SECONDS = 60
POLL_SECONDS = 1.0
RETENTION = "7 days"
INTERRUPTED = "interrupted"
JOB_ID = re.compile(r"jb_[0-9a-f]{32}\Z")
KEY = re.compile(r"[A-Za-z0-9._:-]{8,128}\Z")
OPEN = ("queued", "running")


def workers_from_env() -> int:
    """`KUTUPHANE_JOB_WORKERS`: worker threads in the server process (default 1; 0 runs no jobs)."""
    value = os.environ.get(WORKERS_ENV, str(DEFAULT_WORKERS))
    if not value.isdigit():
        raise RuntimeError(f"{WORKERS_ENV} must be a whole number")
    return int(value)


class Cancelled(Exception):
    pass


class Expired(Exception):
    """The job's lease ended (or another process already failed the job): the worker stops."""


def _scope_doc(scope: search.Scope) -> dict:
    return {k: list(v) if isinstance(v, tuple) else v for k, v in dataclasses.asdict(scope).items()}


def _scope(doc: dict) -> search.Scope:
    return search.Scope.of(doc["books"], doc["path"], doc["origins"], doc["current_only"])


def submit(conn, actor: Actor, question: str, scope: search.Scope,
           idempotency_key: str | None = None) -> tuple[dict, bool]:
    """({job_id, status}, created). A retry with the same key and request gives the original job (created False)."""
    if idempotency_key is not None and not (isinstance(idempotency_key, str) and KEY.match(idempotency_key)):
        raise ValueError("idempotency_key must be 8 to 128 characters of A-Z, a-z, 0-9, '.', '_', ':', '-'")
    doc = _scope_doc(scope)
    digest = ids.request_digest({"question": question, "scope": doc}) if idempotency_key else None
    with conn.transaction():
        # One submission per principal at a time: the open-job count and the key lookup stay true until commit.
        conn.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (f"ask_job:{actor.principal}",))
        if idempotency_key:
            row = conn.execute("SELECT id, status, request_sha256 FROM ask_job WHERE principal = %s "
                               "AND coalesce(on_behalf_of, '') = coalesce(%s, '') AND idempotency_key = %s",
                               (actor.principal, actor.on_behalf_of, idempotency_key)).fetchone()
            if row is not None:
                if bytes(row[2]) != digest:
                    raise ids.IdempotencyConflict("idempotency_key reused with another request")
                return {"job_id": row[0], "status": row[1]}, False
        (open_jobs,) = conn.execute("SELECT count(*) FROM ask_job WHERE principal = %s AND status = ANY(%s)",
                                    (actor.principal, list(OPEN))).fetchone()
        if open_jobs >= MAX_OPEN:
            raise ids.LimitExceeded(f"at most {MAX_OPEN} open jobs per principal")
        job_id = f"jb_{uuid.uuid4().hex}"
        conn.execute("INSERT INTO ask_job (id, principal, on_behalf_of, correlation_id, question, scope, "
                     "idempotency_key, request_sha256, status) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'queued')",
                     (job_id, actor.principal, actor.on_behalf_of, actor.correlation_id, question, Jsonb(doc),
                      idempotency_key, digest))
    return {"job_id": job_id, "status": "queued"}, True


def expire(conn, job_id: str | None = None) -> None:
    """A running job whose lease ended is failed, never run again."""
    conn.execute("UPDATE ask_job SET status = 'failed', error = %s, finished_at = now(), lease_until = NULL "
                 "WHERE status = 'running' AND lease_until < now() AND (%s::text IS NULL OR id = %s)",
                 (INTERRUPTED, job_id, job_id))


def cleanup(conn) -> None:
    conn.execute("DELETE FROM ask_job WHERE status <> ALL(%s) AND finished_at < now() - %s::interval",
                 (list(OPEN), RETENTION))


def _visible_row(conn, actor: Actor, job_id, columns: str):
    if not isinstance(job_id, str) or not JOB_ID.match(job_id):
        raise NotFound("job")
    expire(conn, job_id)
    row = conn.execute(f"SELECT principal, on_behalf_of, {columns} FROM ask_job WHERE id = %s", (job_id,)).fetchone()
    if row is None or not answers.visible(actor, row[0], row[1]):
        raise NotFound("job")
    return row[2:]


def _iso(value):
    return value.isoformat() if value is not None else None


def status(conn, actor: Actor, job_id: str) -> dict:
    state, created, started, finished, error = _visible_row(
        conn, actor, job_id, "status, created_at, started_at, finished_at, error")
    return {"status": state, "created_at": _iso(created), "started_at": _iso(started),
            "finished_at": _iso(finished), "error": error}


def result(conn, actor: Actor, job_id: str) -> dict:
    """`answers.reopen` of the job's answer: current rights on every source book decide it."""
    state, answer_id = _visible_row(conn, actor, job_id, "status, answer_id")
    if state != "succeeded":
        raise ValueError(f"job has no result: {state}")
    return answers.reopen(conn, actor, answer_id)


def cancel(conn, actor: Actor, job_id: str) -> dict:
    _visible_row(conn, actor, job_id, "status")
    conn.execute("UPDATE ask_job SET cancel_requested_at = coalesce(cancel_requested_at, now()), "
                 "status = CASE WHEN status = 'queued' THEN 'cancelled' ELSE status END, "
                 "finished_at = CASE WHEN status = 'queued' THEN now() ELSE finished_at END "
                 "WHERE id = %s AND status = ANY(%s)", (job_id, list(OPEN)))
    return status(conn, actor, job_id)


def claim(conn, lease_seconds: float = LEASE_SECONDS):
    """The oldest queued job, now running under a lease; None when there is none."""
    return conn.execute(
        "UPDATE ask_job SET status = 'running', started_at = now(), lease_until = now() + make_interval(secs => %s) "
        "WHERE id = (SELECT id FROM ask_job WHERE status = 'queued' ORDER BY created_at, id "
        "            FOR UPDATE SKIP LOCKED LIMIT 1) "
        "RETURNING id, principal, on_behalf_of, correlation_id, question, scope", (lease_seconds,)).fetchone()


def renew(conn, job_id: str, lease_seconds: float = LEASE_SECONDS) -> bool:
    """Extend the lease of a running job whose lease has not ended. False when it ended: never revived."""
    return conn.execute("UPDATE ask_job SET lease_until = now() + make_interval(secs => %s) "
                        "WHERE id = %s AND status = 'running' AND lease_until > clock_timestamp() RETURNING 1",
                        (lease_seconds, job_id)).fetchone() is not None


def run(conn, dsn: str, job, ask, safe_error, lease_seconds: float = LEASE_SECONDS) -> None:
    """Run one claimed job. `ask(conn, actor, question, scope, check, commit) -> answer id` is `answers.ask` with
    both hooks: `check()` before the model call and before the store, `commit(answer id)` in the transaction that
    stores the answer, which records the success. `safe_error(exc)` is the short message stored for a failure (the
    HTTP error classes)."""
    job_id, principal, on_behalf_of, correlation_id, question, scope = job
    actor = Actor(principal, on_behalf_of, correlation_id=correlation_id)
    done = threading.Event()

    def heartbeat_loop():
        with db.connect(dsn) as c:
            while not done.wait(lease_seconds / 3):
                if not renew(c, job_id, lease_seconds):
                    return  # the lease ended; the worker's next check stops it

    def fence(lock: bool) -> None:
        """The job must still be running, uncancelled, under an unexpired lease."""
        row = conn.execute("SELECT status, cancel_requested_at, lease_until > clock_timestamp() FROM ask_job "
                           f"WHERE id = %s{' FOR UPDATE' if lock else ''}", (job_id,)).fetchone()
        if row is None or row[1] is not None:
            raise Cancelled(job_id)
        if row[0] != "running" or not row[2]:
            raise Expired(job_id)

    def check():
        fence(lock=False)

    def commit(answer_id: str):  # in the answer's transaction: the job row is locked until it commits
        fence(lock=True)
        conn.execute("UPDATE ask_job SET status = 'succeeded', answer_id = %s, error = NULL, finished_at = now(), "
                     "lease_until = NULL WHERE id = %s", (answer_id, job_id))

    heartbeat = threading.Thread(target=heartbeat_loop, name=f"lease-{job_id}", daemon=True)
    heartbeat.start()
    try:
        try:
            ask(conn, actor, question, _scope(scope), check, commit)
            return  # succeeded: recorded with the answer
        except Cancelled:
            outcome = ("cancelled", None)
        except Expired:
            outcome = ("failed", INTERRUPTED)
        except Exception as exc:  # stored as a short, safe message; the details only in the server log
            log.warning("ask job %s failed", job_id, exc_info=True)
            outcome = ("failed", safe_error(exc)[:500])
        conn.execute("UPDATE ask_job SET status = %s, error = %s, finished_at = now(), lease_until = NULL "
                     "WHERE id = %s AND status = 'running'", (*outcome, job_id))
    finally:
        done.set()
        heartbeat.join()


def work_one(conn, dsn: str, ask, safe_error, lease_seconds: float = LEASE_SECONDS) -> bool:
    """Expire, clean up, then claim and run one job. False when no job was queued."""
    expire(conn)
    cleanup(conn)
    job = claim(conn, lease_seconds)
    if job is None:
        return False
    run(conn, dsn, job, ask, safe_error, lease_seconds)
    return True


class Workers:
    """`count` worker threads in the server process."""

    def __init__(self, dsn: str, ask, safe_error, count: int):
        self.dsn, self.ask, self.safe_error, self.count = dsn, ask, safe_error, count
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []

    def start(self) -> None:
        for n in range(self.count):
            t = threading.Thread(target=self._loop, name=f"ask-job-{n}", daemon=True)
            t.start()
            self._threads.append(t)

    def stop(self) -> None:
        """Stop claiming; a job that is running finishes first."""
        self._stop.set()
        for t in self._threads:
            t.join()

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                with db.connect(self.dsn) as conn:
                    while not self._stop.is_set():
                        if not work_one(conn, self.dsn, self.ask, self.safe_error):
                            self._stop.wait(POLL_SECONDS)
            except Exception:
                log.exception("ask job worker failed; retrying")
                self._stop.wait(POLL_SECONDS)
