"""The curator act on Standing (docs/24 §8, docs/25 §6.5): one function for the CLI and for curator web.

`apply` writes one Standing event per item, with one reason, in the caller's transaction (the caller holds the memory
lock). The CLI (`kutuphane note standing`) passes no act: the operator is trusted (docs/24 §8.2). Curator web passes
the act of a verified passkey assertion, and the database accepts each event only as an item of that act's signed
statement (migration 023).
"""
import uuid

from . import authz, gate
from . import notes as notes_

MAX_ITEMS = 50
ROLE_RULE = {k for k, r in notes_.KIND_ROLE.items() if r == "rule"}


class Changed(ValueError):
    """The Standing in force is not the one the person saw (`was`): another curator acted in between (HTTP 409)."""


class IntegrityRefused(PermissionError):
    """The stored parts of a note do not give its id (docs/25 §5.2): the note is not shown or signed."""


def check_reason(principal, reason) -> None:
    if not notes_._principal("curator", principal).startswith("user:"):
        raise ValueError("a curator is a user:")
    if not isinstance(reason, str) or not 1 <= len(reason) <= 500:
        raise ValueError("reason must be 1..500 characters")


def check_integrity(conn, seq: int, note_id: str) -> None:
    if notes_.canonical_of(conn, seq)[0] != note_id:
        raise IntegrityRefused(f"note-integrity: the stored parts of {note_id} do not give its id")


def _note(conn, ref: str):
    book, note_id = notes_.parse_ref(ref)
    row = conn.execute("SELECT seq, kind, scope_repo, scope_branch, scope_paths FROM note WHERE book = %s AND id = %s",
                       (book, note_id)).fetchone()
    if row is None:
        raise gate.NotFound(f"no such note: {ref}")
    return book, note_id, row


def prepare(conn, *, principal: str, items: list[dict], reason: str, need_read: bool = False,
            check_was: bool = False, integrity: bool = False) -> list[dict]:
    """Every rule of an act that the database state can decide now, with no write: the rights, the transitions,
    D68, at most one rule-role approval, no approved `contradicts` pair, the note digest and the Standing in force
    (`was`). Returns the items with `seq`, `kind`, `scope`, `current` and `was` (the event in force)."""
    check_reason(principal, reason)
    if not isinstance(items, list) or not 1 <= len(items) <= MAX_ITEMS:
        raise ValueError(f"an act has 1..{MAX_ITEMS} items")
    refs = [i.get("ref") if isinstance(i, dict) else None for i in items]
    if len(set(refs)) != len(refs):
        raise ValueError("the same note is given twice")
    modes = ("curate", "read") if need_read else ("curate",)
    out = []
    for item in items:
        if set(item) - {"ref", "to", "was"} or item.get("to") not in notes_.STANDINGS:
            raise ValueError(f"an item is {{ref, to}}; to is one of {', '.join(notes_.STANDINGS)}")
        book, note_id, (seq, kind, repo, branch, paths) = _note(conn, item["ref"])
        for mode in modes:
            if not authz.direct(conn, principal, f"book:{book}", mode).allowed:
                raise gate.Denied(f"{principal} does not hold {mode} on book:{book}")
        if integrity:
            check_integrity(conn, seq, note_id)
        current, event = notes_.effective_standing(conn, [seq], notes_.NOW)[seq]
        if check_was and item.get("was") != event:
            raise Changed(f"{item['ref']} changed since it was shown: reload")
        if (current, item["to"]) not in notes_.TRANSITIONS:
            raise ValueError(f"{current} -> {item['to']} is not a Standing transition")
        if item["to"] == "rejected" and notes_._ever_approved(conn, seq):
            raise ValueError(f"{item['ref']} was approved before: rejected means never accepted (D68); use retired")
        out.append({"ref": item["ref"], "id": note_id, "book": book, "seq": seq, "kind": kind,
                     "scope": (repo, branch, sorted(paths)), "current": current, "was": event, "to": item["to"]})
    approved = [i for i in out if i["to"] == "approved"]
    if sum(i["kind"] in ROLE_RULE for i in approved) > 1:
        raise ValueError("at most one rule-role approval per act: a rule is read alone")
    seqs = [i["seq"] for i in approved]
    if len(seqs) > 1 and conn.execute(
            "SELECT EXISTS (SELECT 1 FROM note_link WHERE type = 'contradicts' AND src = ANY(%s) AND dst_note = ANY(%s))",
            (seqs, seqs)).fetchone()[0]:
        raise ValueError("two notes joined by contradicts are never approved in one act")
    return out


def _event(conn, seq: int, value: str, set_by: str, reason: str, correlation: str, *, act=None, cause=None) -> int:
    return conn.execute("INSERT INTO standing_event (note_seq, value, set_by, cause_seq, reason, correlation_id, act) "
                        "VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING seq",
                        (seq, value, set_by, cause, reason, correlation, act)).fetchone()[0]


def _supersede(conn, item: dict, event: int, correlation: str) -> dict:
    """docs/24 §8.3: the approval of a rule note retires the approved predecessors it supersedes with exactly the
    same scope (system events, cause = its event); the curator sees the other current rules of the repository."""
    book, seq = item["book"], item["seq"]
    retired = []
    for p_seq, p_id, repo, branch, paths in conn.execute(
            "SELECT p.seq, p.id, p.scope_repo, p.scope_branch, p.scope_paths FROM note_link l "
            "JOIN note p ON p.seq = l.dst_note WHERE l.src = %s AND l.type = 'supersedes' AND l.creation "
            "AND p.book = %s ORDER BY p.seq", (seq, book)).fetchall():
        same_scope = (repo, branch, sorted(paths)) == item["scope"]
        if same_scope and notes_.effective_standing(conn, [p_seq], notes_.NOW)[p_seq][0] == "approved":
            _event(conn, p_seq, "retired", "system", f"superseded by {item['ref']}", correlation, cause=event)
            retired.append(f"{book}@{p_id}")
    rules = conn.execute("SELECT seq, id FROM note WHERE book = %s AND seq <> %s AND kind = ANY(%s) "
                         "AND scope_repo IS NOT DISTINCT FROM %s ORDER BY seq",
                         (book, seq, sorted(ROLE_RULE), item["scope"][0])).fetchall()
    standing = notes_.effective_standing(conn, [s for s, _ in rules], notes_.NOW)
    return {"retired": retired, "rules_same_repo": [f"{book}@{i}" for s, i in rules if standing[s][0] == "approved"]}


def apply(conn, *, principal: str, items: list[dict], reason: str, act: int | None = None, need_read: bool = False,
          check_was: bool = False, integrity: bool = False, correlation: str | None = None) -> list[dict]:
    """The act. The caller holds the transaction and the memory lock (`notes._lock`)."""
    prepared = prepare(conn, principal=principal, items=items, reason=reason, need_read=need_read,
                       check_was=check_was, integrity=integrity)
    correlation = correlation or uuid.uuid4().hex
    out = []
    for item in prepared:
        event = _event(conn, item["seq"], item["to"], principal, reason, correlation, act=act)
        result = {"ref": item["ref"], "standing": item["to"], "event_seq": event}
        if item["to"] == "approved" and item["kind"] in ROLE_RULE:
            result.update(_supersede(conn, item, event, correlation))
        out.append(result)
    return out
