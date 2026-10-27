"""D73 delegated curate (docs/25 §8): the signed delegation, its end, the shadow agreement and the audit report.

A person with direct `curate` (and `read`) on a journal signs a `delegate` passkey act; the statement holds every
field, and the database accepts only that row (migration 025). A delegation covers `pending → approved` of fresh
evidence notes of one (book, kind) by one decider and spec, for at most 30 days. The database checks each use, draws
the sample, writes the approval, pauses at 3 open samples, forces a sample after 2N unsampled uses, and ends the
delegation at the first human disagreement on every Standing path. This module builds the statements, applies them,
and reads the measures; it never writes Standing.
"""
import math
import os
import re
import secrets
import uuid
from datetime import timedelta

from psycopg.types.json import Jsonb

from . import authz, gate, notes

EVIDENCE_KINDS = ("finding", "lesson", "dead_end", "test_result")
MIN_SHADOW_ENV = "KUTUPHANE_DELEGATION_MIN_SHADOW"
MIN_SHADOW_DEFAULT = 30
DEFAULTS = {"days": 14, "sample_every": 10, "min_confidence": 0.90}  # docs/25 §14 Q6
MAX_DAYS = 30
THRESHOLDS = (0.5, 0.6, 0.7, 0.8, 0.9, 0.95)
Z95 = 1.959964
ID = re.compile(r"^cd_[0-9a-f]{32}\Z")
DECIDER = re.compile(r"^[a-z0-9][a-z0-9._-]{0,62}@[A-Za-z0-9._+-]{1,64}\Z")
SPEC = re.compile(r"^[0-9a-f]{64}\Z")


def min_shadow() -> int:
    """The shadow decisions a delegation needs (§8.2): a whole number, at least 1. Curator web checks it at start."""
    raw = os.environ.get(MIN_SHADOW_ENV) or str(MIN_SHADOW_DEFAULT)
    try:
        value = int(raw)
    except ValueError:
        raise RuntimeError(f"{MIN_SHADOW_ENV} must be a whole number") from None
    if value < 1:
        raise RuntimeError(f"{MIN_SHADOW_ENV} must be at least 1")
    return value


def _rights(conn, principal: str, book: str, modes=("curate", "read")) -> None:
    """The rights of the act now (`authz.direct`: `curate` is never delegated, docs/25 §5.4 step 7)."""
    for mode in modes:
        if not authz.direct(conn, principal, f"book:{book}", mode).allowed:
            raise gate.Denied(f"{principal} does not hold {mode} on book:{book}")


# --- agreement (§8.7) -----------------------------------------------------------------------------------------------

def wilson_lower(agreed: int, n: int) -> float | None:
    if n == 0:
        return None
    p, z2 = agreed / n, Z95 * Z95
    return (p + z2 / (2 * n) - Z95 * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n))) / (1 + z2 / n)


# A suggestion counts only when it was written before the note's first human Standing event (§6.4), and only notes
# whose first human event is a verdict (approved or rejected).
_SHADOW = """
SELECT s.confidence, f.value
  FROM note_suggestion s
  JOIN note n ON n.seq = s.note_seq
  JOIN LATERAL (SELECT e.seq, e.value FROM standing_event e WHERE e.note_seq = s.note_seq AND e.set_by LIKE 'user:%%'
                 ORDER BY e.seq LIMIT 1) f ON true
 WHERE s.decider = %s AND s.spec_sha256 = %s AND n.book = %s AND n.kind = %s AND s.value = 'approved'
   AND s.seq < f.seq AND f.value IN ('approved', 'rejected')
"""


def agreement(conn, decider: str, spec_sha256: bytes, book: str, kind: str) -> list[dict]:
    """The shadow agreement of one decider and spec in one (book, kind), per threshold: n, the share of the human
    verdicts that are `approved`, and the Wilson 95 % lower bound (information only)."""
    rows = conn.execute(_SHADOW, (decider, spec_sha256, book, kind)).fetchall()
    out = []
    for c in THRESHOLDS:
        verdicts = [value for confidence, value in rows if confidence >= c - 1e-6]
        agreed = sum(1 for v in verdicts if v == "approved")
        lower = wilson_lower(agreed, len(verdicts))
        out.append({"threshold": c, "n": len(verdicts), "agreed": agreed,
                    "share": round(agreed / len(verdicts), 4) if verdicts else None,
                    "wilson_lower": round(lower, 4) if lower is not None else None})
    return out


def shadow_n(conn, decider: str, spec_sha256: bytes, book: str, kind: str, min_confidence: float) -> int:
    rows = conn.execute(_SHADOW, (decider, spec_sha256, book, kind)).fetchall()
    return sum(1 for confidence, _ in rows if confidence >= min_confidence - 1e-6)


def _shadow_enough(conn, d: dict) -> None:
    n = shadow_n(conn, d["decider"], bytes.fromhex(d["spec_sha256"]), d["book"], d["kind"], d["min_confidence"])
    if n < min_shadow():
        raise ValueError(f"{n} shadow decisions of {d['decider']} in {d['book']}/{d['kind']} at "
                         f"{d['min_confidence']}: a delegation needs at least {min_shadow()}")


# --- create (a `delegate` act) --------------------------------------------------------------------------------------

def _number(name: str, value, lo, hi, kind):
    if isinstance(value, bool) or not isinstance(value, kind) or not lo <= value <= hi:
        raise ValueError(f"{name} must be {lo}..{hi}")
    return value


def delegate_fields(conn, principal: str, body: dict) -> dict:
    """The statement fields of a `delegate` act (docs/25 §5.2): every field of the row. A pre-check refusal writes
    nothing (§5.3)."""
    book, kind, decider, spec = (body.get(k) for k in ("book", "kind", "decider", "spec_sha256"))
    if not isinstance(book, str) or not notes.BOOK.match(book):
        raise ValueError("book must be a journal slug")
    if kind not in EVIDENCE_KINDS:
        raise ValueError(f"kind must be an evidence kind: {', '.join(EVIDENCE_KINDS)}")
    if not isinstance(decider, str) or not DECIDER.match(decider):
        raise ValueError("decider must be name@version")
    if not isinstance(spec, str) or not SPEC.match(spec):
        raise ValueError("spec_sha256 must be 64 hex digits")
    min_confidence = round(float(_number("min_confidence", body.get("min_confidence", DEFAULTS["min_confidence"]),
                                         0.5, 1, (int, float))), 2)
    sample_every = _number("sample_every", body.get("sample_every", DEFAULTS["sample_every"]), 2, 100, int)
    days = _number("days", body.get("days", DEFAULTS["days"]), 1, MAX_DAYS, int)
    if not conn.execute("SELECT 1 FROM journal WHERE book = %s", (book,)).fetchone():
        raise gate.NotFound(f"{book} is not a journal")
    _rights(conn, principal, book)
    now = conn.execute("SELECT date_trunc('second', clock_timestamp())").fetchone()[0]
    d = {"id": "cd_" + secrets.token_hex(16), "book": book, "kind": kind, "decider": decider, "spec_sha256": spec,
         "min_confidence": min_confidence, "sample_every": sample_every,
         "expires_at": (now + timedelta(days=days)).isoformat()}
    _shadow_enough(conn, d)
    return {"delegation": d}


def apply_delegate(conn, act) -> dict:
    """The row of a `delegate` statement, in the act transaction (docs/25 §5.4 step 7): the rights and the shadow
    evidence are decided again now; the trigger checks that the row is the statement, field by field."""
    d = act.payload["delegation"]
    _rights(conn, act.principal, d["book"])
    _shadow_enough(conn, d)
    conn.execute("INSERT INTO curate_delegation (id, book, kind, decider, spec_sha256, min_confidence, sample_every, "
                 "created_by, act, expires_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::timestamptz)",
                 (d["id"], d["book"], d["kind"], d["decider"], bytes.fromhex(d["spec_sha256"]), d["min_confidence"],
                  d["sample_every"], act.principal, act.seq, d["expires_at"]))
    return {"act": act.seq, "delegation": d["id"]}


# --- end (an `end_delegation` act, or the CLI) ----------------------------------------------------------------------

def _live(conn, delegation_id) -> tuple:
    if not isinstance(delegation_id, str) or not ID.match(delegation_id):
        raise ValueError("delegation must be a cd_ id")
    row = conn.execute("SELECT d.book, e.cause FROM curate_delegation d LEFT JOIN delegation_end e "
                       "ON e.delegation = d.id WHERE d.id = %s", (delegation_id,)).fetchone()
    if row is None:
        raise gate.NotFound(f"no such delegation: {delegation_id}")
    if row[1] is not None:
        raise ValueError(f"delegation {delegation_id} has ended ({row[1]}); an end is final")
    return row[0]


def end_fields(conn, principal: str, body: dict) -> dict:
    reason = body.get("reason")
    if not isinstance(reason, str) or not 1 <= len(reason) <= 500:
        raise ValueError("reason must be 1..500 characters")
    _rights(conn, principal, _live(conn, body.get("delegation")))
    return {"delegation": body["delegation"], "reason": reason}


def apply_end(conn, act) -> dict:
    book = _live(conn, act.payload["delegation"])
    _rights(conn, act.principal, book)
    conn.execute("INSERT INTO delegation_end (delegation, cause, ended_by, act) VALUES (%s, 'revoked', %s, %s)",
                 (act.payload["delegation"], act.principal, act.seq))
    return {"act": act.seq, "delegation": act.payload["delegation"], "ended": "revoked"}


def end(conn, delegation_id: str, *, curator: str, reason: str) -> dict:
    """`kutuphane delegation end` (owner credential; ending only tightens). The curator must hold `curate` on the
    book now. The reason goes to the access record of the end."""
    notes._curation(curator, reason)
    with conn.transaction():
        notes._lock(conn)
        book = _live(conn, delegation_id)
        _rights(conn, curator, book, modes=("curate",))
        conn.execute("INSERT INTO delegation_end (delegation, cause, ended_by) VALUES (%s, 'revoked', %s)",
                     (delegation_id, curator))
        conn.execute("INSERT INTO access_event (correlation_id, principal, action, object, mode, allowed, reason) "
                     "VALUES (%s, %s, 'delegation_end', %s, 'curate', true, %s)",
                     (uuid.uuid4().hex, curator, f"book:{book}", f"{delegation_id}: {reason}"))
    return {"delegation": delegation_id, "ended": "revoked", "ended_by": curator}


# --- verify-acts (docs/25 §5.6) -------------------------------------------------------------------------------------

def delegate_effects(conn, act: int, payload: dict) -> bool:
    """The delegation that names the act is exactly the statement's row."""
    rows = conn.execute(
        "SELECT x.id = s #>> '{delegation,id}' AND x.book = s #>> '{delegation,book}' "
        "   AND x.kind = s #>> '{delegation,kind}' AND x.decider = s #>> '{delegation,decider}' "
        "   AND encode(x.spec_sha256, 'hex') = s #>> '{delegation,spec_sha256}' "
        "   AND x.min_confidence = (s #>> '{delegation,min_confidence}')::real "
        "   AND x.sample_every = (s #>> '{delegation,sample_every}')::integer "
        "   AND x.expires_at = (s #>> '{delegation,expires_at}')::timestamptz "
        "  FROM curate_delegation x, (SELECT %s::jsonb AS s) p WHERE x.act = %s",
        (Jsonb(payload), act)).fetchall()
    return rows == [(True,)]


def end_effects(conn, act: int, payload: dict) -> bool:
    rows = conn.execute("SELECT delegation, cause FROM delegation_end WHERE act = %s", (act,)).fetchall()
    return rows == [(payload.get("delegation"), "revoked")]


# --- reads: list, report, review list -------------------------------------------------------------------------------

_LIST = """
SELECT d.id, d.book, d.kind, d.decider, encode(d.spec_sha256, 'hex'), d.min_confidence, d.sample_every, d.created_by,
       d.act, d.created_at, d.expires_at, e.cause, e.ended_by, e.at,
       (SELECT count(*) FROM delegation_use u WHERE u.delegation = d.id),
       (SELECT count(*) FROM delegation_use u WHERE u.delegation = d.id AND NOT u.sampled),
       (SELECT count(*) FROM delegation_use u WHERE u.delegation = d.id AND u.sampled),
       (SELECT count(*) FROM delegation_use u WHERE u.delegation = d.id AND u.sampled
           AND NOT EXISTS (SELECT 1 FROM standing_event s WHERE s.note_seq = u.note_seq)),
       clock_timestamp() >= d.expires_at
  FROM curate_delegation d LEFT JOIN delegation_end e ON e.delegation = d.id
 WHERE (%(books)s::text[] IS NULL OR d.book = ANY(%(books)s::text[])) AND (%(id)s::text IS NULL OR d.id = %(id)s::text)
 ORDER BY d.created_at DESC, d.id
"""


def _state(cause, expired) -> str:
    return f"ended:{cause}" if cause else "expired" if expired else "live"


def list_(conn, books=None, delegation_id=None) -> list[dict]:
    """Every delegation (of `books`, or the one `delegation_id`), newest first, with its state and use counts."""
    out = []
    for (did, book, kind, decider, spec, c, n, by, act, created, expires, cause, ended_by, ended_at, uses, approved,
         samples, open_samples, expired) in conn.execute(_LIST, {"books": books, "id": delegation_id}):
        out.append({"id": did, "book": book, "kind": kind, "decider": decider, "approver": f"model:{decider}",
                    "spec_sha256": spec, "min_confidence": round(c, 4), "sample_every": n, "created_by": by,
                    "act": act, "created_at": created.isoformat(), "expires_at": expires.isoformat(),
                    "state": _state(cause, expired), "ended_by": ended_by,
                    "ended_at": ended_at.isoformat() if ended_at else None,
                    "uses": uses, "approved": approved, "samples": samples, "open_samples": open_samples})
    return out


_USES = """
SELECT u.seq, n.book || '@' || n.id, u.sampled, u.correlation_id, u.at, s.seq, s.value, s.confidence,
       m.id, m.call_id, m.derived_correlation_id, m.route, m.model, m.http_status,
       (SELECT e.seq FROM standing_event e WHERE e.delegation_use = u.seq),
       (SELECT jsonb_build_object('seq', e.seq, 'value', e.value, 'set_by', e.set_by) FROM standing_event e
         WHERE e.note_seq = u.note_seq ORDER BY e.seq LIMIT 1)
  FROM delegation_use u
  JOIN note n ON n.seq = u.note_seq
  JOIN note_suggestion s ON s.seq = u.suggestion
  JOIN model_call m ON m.id = s.model_call
 WHERE u.delegation = %s
 ORDER BY u.seq
"""


def _verdict(sampled: bool, first) -> str:
    """A sample's state (§8.7 live agreement): open, agreed, disagreed, or closed with no verdict (a system event)."""
    if not sampled:
        return "delegated"
    if first is None:
        return "open"
    if first["set_by"] == "system":
        return "closed"
    return "agreed" if first["value"] == "approved" else "disagreed"


_OUTCOMES = """
SELECT CASE WHEN a.set_by LIKE 'model:%%' THEN 'delegated' ELSE 'human' END, o.result, count(*)
  FROM outcome o
  JOIN note n ON n.seq = o.note_seq
  JOIN LATERAL (SELECT e.set_by FROM standing_event e WHERE e.note_seq = n.seq AND e.value = 'approved'
                 ORDER BY e.seq LIMIT 1) a ON true
 WHERE n.book = %s AND n.kind = %s
 GROUP BY 1, 2 ORDER BY 1, 2
"""


def report(conn, delegation_id: str) -> dict:
    """`kutuphane delegation report` (§8.6): the signed creation, the end, every use with its suggestion, `model_call`
    and correlation id, the live agreement, coverage, and the outcome counts of delegated vs human approvals."""
    if not isinstance(delegation_id, str) or not ID.match(delegation_id):
        raise ValueError("delegation must be a cd_ id")
    found = list_(conn, delegation_id=delegation_id)
    if not found:
        raise gate.NotFound(f"no such delegation: {delegation_id}")
    d = found[0]
    signed = conn.execute("SELECT principal, at, backup_state FROM curator_act WHERE seq = %s", (d["act"],)).fetchone()
    end_row = conn.execute("SELECT cause, ended_by, event, act, at FROM delegation_end WHERE delegation = %s",
                           (delegation_id,)).fetchone()
    uses, live = [], {"agreed": 0, "disagreed": 0, "open": 0, "closed": 0}
    for (seq, ref, sampled, correlation, at, s_seq, s_value, s_conf, m_id, call_id, derived, route, model, status,
         event, first) in conn.execute(_USES, (delegation_id,)):
        verdict = _verdict(sampled, first)
        if sampled:
            live[verdict] += 1
        uses.append({"use": seq, "ref": ref, "sampled": sampled, "correlation_id": correlation, "at": at.isoformat(),
                     "suggestion": {"seq": s_seq, "value": s_value, "confidence": round(s_conf, 4)},
                     "model_call": {"id": m_id, "call_id": call_id, "derived_correlation_id": derived,
                                    "route": route, "model": model, "http_status": status},
                     "event_seq": event, "verdict": verdict})
    total = conn.execute("SELECT count(*) FROM note WHERE book = %s AND kind = %s",
                         (d["book"], d["kind"])).fetchone()[0]
    outcomes: dict = {"delegated": {}, "human": {}}
    for who, result, count in conn.execute(_OUTCOMES, (d["book"], d["kind"])):
        outcomes[who][result] = count
    return {"delegation": d,
            "signed": {"act": d["act"], "principal": signed[0], "at": signed[1].isoformat(),
                       "synced_passkey": signed[2]} if signed else None,
            "end": {"cause": end_row[0], "ended_by": end_row[1], "event": end_row[2], "act": end_row[3],
                    "at": end_row[4].isoformat()} if end_row else None,
            "uses": uses, "live_agreement": live,
            "coverage": {"class_notes": total, "approved": d["approved"],
                         "share": round(d["approved"] / total, 4) if total else None},
            "outcomes": outcomes}


_REVIEW = """
SELECT n.book || '@' || n.id, n.kind, left(n.body, 120), e.seq, e.at, cur.seq, cur.value
  FROM standing_event e
  JOIN delegation_use u ON u.seq = e.delegation_use
  JOIN note n ON n.seq = e.note_seq
  JOIN LATERAL (SELECT c.seq, c.value FROM standing_event c WHERE c.note_seq = n.seq ORDER BY c.seq DESC LIMIT 1) cur
       ON true
 WHERE u.delegation = %s
 ORDER BY e.seq DESC
"""


def review_list(conn, delegation_id: str) -> list[dict]:
    """Every note that the delegation approved, newest first (§8.4): after an end the curator may retire them in one
    `standing` act (`was` = the event in force). There is no automatic retirement (§14 Q7)."""
    return [{"ref": ref, "kind": kind, "head": head, "approval_seq": approval, "approved_at": at.isoformat(),
             "was": was, "standing": value, "retirable": value == "approved"}
            for ref, kind, head, approval, at, was, value in conn.execute(_REVIEW, (delegation_id,))]


_SHADOW_CLASSES = """
SELECT DISTINCT n.book, n.kind, s.decider, s.spec_sha256
  FROM note_suggestion s JOIN note n ON n.seq = s.note_seq
 WHERE n.book = ANY(%s) AND n.kind = ANY(%s)
 ORDER BY 1, 2, 3, 4
"""


def shadow_classes(conn, books: list[str]) -> list[dict]:
    """The shadow agreement of every decider and spec that wrote suggestions in an evidence class of `books`: what
    the page shows before a person signs a delegation (§8.2)."""
    return [{"book": book, "kind": kind, "decider": decider, "spec_sha256": bytes(spec).hex(),
             "agreement": agreement(conn, decider, bytes(spec), book, kind), "min_shadow": min_shadow()}
            for book, kind, decider, spec in conn.execute(_SHADOW_CLASSES, (books, list(EVIDENCE_KINDS)))]
