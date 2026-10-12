"""Runbook outcome feedback (D13, AT-15): "worked / failed / changed", who applied it, where it was tested, and the
exact content version. Giving or reading feedback needs a current `read` right on the book (the gate logs it)."""
from . import catalog, gate
from .gate import Actor, NotFound

OUTCOMES = ("worked", "failed", "changed")
MAX_TESTED_ON = 200
MAX_NOTE = 2000


def record(conn, actor: Actor, *, book: str, content_id: str, path: str, outcome: str, tested_on: str | None = None,
           note: str | None = None) -> int:
    if outcome not in OUTCOMES:
        raise ValueError(f"outcome must be one of {', '.join(OUTCOMES)}")
    if tested_on is not None and (not tested_on.strip() or len(tested_on) > MAX_TESTED_ON):
        raise ValueError(f"tested_on must be 1..{MAX_TESTED_ON} characters")
    if note is not None and len(note) > MAX_NOTE:
        raise ValueError(f"note must be at most {MAX_NOTE} characters")

    def insert():
        if catalog.manifest_entry(conn, book, content_id, path) is None:
            raise NotFound(f"{book}@{content_id}:{path}")
        return conn.execute(
            "INSERT INTO runbook_feedback (correlation_id, book, content_id, path, outcome, principal, on_behalf_of, "
            "tested_on, note) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
            (actor.correlation_id, book, content_id, path, outcome, actor.principal, actor.on_behalf_of, tested_on,
             note)).fetchone()[0]
    return gate.guard(conn, actor, f"book:{book}", ["read"], insert, action="feedback", content_id=content_id,
                      path=path)


def for_version(conn, actor: Actor, *, book: str, content_id: str, path: str) -> list[dict]:
    """Feedback on exactly this version of the file; other versions' feedback is not mixed in."""
    def fetch():
        rows = conn.execute("SELECT at, outcome, principal, on_behalf_of, tested_on, note FROM runbook_feedback "
                            "WHERE book = %s AND content_id = %s AND path = %s ORDER BY id",
                            (book, content_id, path)).fetchall()
        return [{"at": r[0].isoformat(), "outcome": r[1], "principal": r[2], "on_behalf_of": r[3],
                 "tested_on": r[4], "note": r[5]} for r in rows]
    return gate.guard(conn, actor, f"book:{book}", ["read"], fetch, action="read_feedback", content_id=content_id,
                      path=path)
