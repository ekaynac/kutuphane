"""Authorization core (M1b): grants, role membership, one-level user→agent delegation, decisions.

Rules (docs/07 §3, D28):
- E9 modes (discover, read, use, activate) are independent; holding one never implies another.
- An agent acting for a user needs a live delegation for that object and mode AND the user's *current* right;
  losing either one denies at once (AT-05). Delegations cannot be created beyond the delegator's rights.
- `now() < expires_at`: a grant is already expired at its expiry instant (AT-06).
- Identity is not verified here; callers are trusted until M1c.
"""
import re
from dataclasses import dataclass, field
from datetime import datetime

# propose: write notes and links into a journal (docs/24 §4.2). curate: may be named as a curator by the CLI; only
# user principals hold it, directly, and no delegation carries it (the database refuses both, migration 016).
MODES = ("discover", "read", "use", "activate", "propose", "curate")
NOT_DELEGABLE = ("curate",)
# At most 128 characters in all, so a principal is always a valid LLMDAP chain label (x-llmdap-for-subject).
PRINCIPAL = re.compile(r"^(user|agent|role):[a-z0-9][a-z0-9._@-]{0,121}\Z")
OBJECT = re.compile(r"^book:[a-z0-9][a-z0-9-]{0,62}\Z")


class AuthzError(ValueError):
    pass


@dataclass(frozen=True)
class Decision:
    allowed: bool
    reason: str
    grant_ids: tuple = field(default_factory=tuple)
    delegation_id: int | None = None


def _check(pattern, value: str, what: str) -> str:
    if not isinstance(value, str) or not pattern.match(value):
        raise AuthzError(f"invalid {what}: {value!r}")
    return value


def _mode(mode: str) -> str:
    if mode not in MODES:
        raise AuthzError(f"mode must be one of {', '.join(MODES)} (E9 is mandatory)")
    return mode


# --- grants -------------------------------------------------------------------------------------------------

def grant(conn, obj: str, mode: str, subject: str) -> int:
    """Give `subject` (a principal, or `role:x#member`) mode on a book."""
    _check(OBJECT, obj, "object")
    _mode(mode)
    base, _, userset = subject.partition("#")
    _check(PRINCIPAL, base, "subject")
    if userset and (userset != "member" or not base.startswith("role:")):
        raise AuthzError("only role:<name>#member usersets are supported")
    if mode == "curate" and not subject.startswith("user:"):
        raise AuthzError("curate is held only by users, directly")
    return _insert_tuple(conn, obj, mode, subject)


def add_member(conn, role: str, user: str) -> int:
    if not _check(PRINCIPAL, role, "role").startswith("role:"):
        raise AuthzError("membership target must be a role")
    if not _check(PRINCIPAL, user, "member").startswith(("user:", "agent:")):
        raise AuthzError("members are users or agents")
    return _insert_tuple(conn, role, "member", user)


def _insert_tuple(conn, obj: str, relation: str, subject: str) -> int:
    row = conn.execute("INSERT INTO grant_tuple (object, relation, subject) VALUES (%s, %s, %s) "
                       "ON CONFLICT (object, relation, subject) WHERE revoked_at IS NULL DO NOTHING RETURNING id",
                       (obj, relation, subject)).fetchone()
    if row:
        return row[0]
    return conn.execute("SELECT id FROM grant_tuple WHERE object = %s AND relation = %s AND subject = %s "
                        "AND revoked_at IS NULL", (obj, relation, subject)).fetchone()[0]


def revoke(conn, obj: str, relation: str, subject: str) -> bool:
    row = conn.execute("UPDATE grant_tuple SET revoked_at = now() WHERE object = %s AND relation = %s "
                       "AND subject = %s AND revoked_at IS NULL RETURNING id", (obj, relation, subject)).fetchone()
    return row is not None


# --- delegation ---------------------------------------------------------------------------------------------

def delegate(conn, *, delegator: str, delegate_to: str, obj: str, mode: str, expires_at: datetime,
             purpose: str | None = None) -> int:
    """One level, time-boxed, never wider than what the delegator holds right now (AT-06)."""
    if not _check(PRINCIPAL, delegator, "delegator").startswith("user:"):
        raise AuthzError("only users delegate (one level)")
    if not _check(PRINCIPAL, delegate_to, "delegate").startswith("agent:"):
        raise AuthzError("delegation goes to an agent")
    _check(OBJECT, obj, "object")
    _mode(mode)
    if mode in NOT_DELEGABLE:
        raise AuthzError(f"{mode} cannot be delegated")
    if not direct(conn, delegator, obj, mode).allowed:
        raise AuthzError(f"{delegator} does not hold {mode} on {obj}")
    return conn.execute("INSERT INTO delegation (delegator, delegate, object, mode, purpose, expires_at) "
                        "VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
                        (delegator, delegate_to, obj, mode, purpose, expires_at)).fetchone()[0]


def revoke_delegation(conn, delegation_id: int) -> bool:
    row = conn.execute("UPDATE delegation SET revoked_at = now() WHERE id = %s AND revoked_at IS NULL RETURNING id",
                       (delegation_id,)).fetchone()
    return row is not None


# --- decisions ----------------------------------------------------------------------------------------------
#
# All modes of one request, the delegation, the holder's grants and the book's current policy are read by ONE
# statement, so they come from one snapshot. Linearization point: a revocation committed before that statement
# starts is honored; one committed after it is not. Expiry uses clock_timestamp(), never a transaction's frozen
# now().
#
# A delivery that a skill scan can block (D71) passes the files (`skills`: (book, content_id, path)) and the notes
# (`notes`: seq) to check: the same statement reads their blocks (SQL `skill_blocked`, `note_skill_blocked`, both
# STABLE, so they see the statement's snapshot). There is no instant between the right and the block (Astra review
# #15): a right revoked and a block cleared in one transaction can never give a permit together.

_BLOCKED_FILES = ("ARRAY(SELECT r.n FROM unnest(%(sb)s::text[], %(sc)s::text[], %(sp)s::text[]) WITH ORDINALITY "
                  "AS r(b, c, p, n) WHERE skill_blocked(r.b, r.c, r.p))")
_BLOCKED_NOTES = "ARRAY(SELECT s FROM unnest(%(ns)s::bigint[]) AS s WHERE note_skill_blocked(s))"

_DECIDE = """
SELECT m.mode,
       (SELECT d.id FROM delegation d
         WHERE %(behalf)s::text IS NOT NULL AND d.delegate = %(p)s AND d.delegator = %(behalf)s
           AND d.object = %(o)s AND d.mode = m.mode AND d.revoked_at IS NULL AND clock_timestamp() < d.expires_at
         ORDER BY d.id DESC LIMIT 1) AS delegation_id,
       ARRAY(SELECT DISTINCT x FROM grant_tuple g
               LEFT JOIN grant_tuple mem ON mem.relation = 'member' AND mem.subject = %(holder)s
                    AND mem.revoked_at IS NULL AND g.subject = mem.object || '#member'
               CROSS JOIN LATERAL unnest(ARRAY[g.id, mem.id]) AS x
              WHERE g.object = %(o)s AND g.relation = m.mode AND g.revoked_at IS NULL
                AND (g.subject = %(holder)s OR mem.id IS NOT NULL) AND x IS NOT NULL
              ORDER BY x) AS grant_ids,
       (SELECT b.current_policy FROM book b WHERE 'book:' || b.slug = %(o)s) AS policy_id,
       {files} AS blocked_files, {notes} AS blocked_notes
  FROM unnest(%(modes)s::text[]) WITH ORDINALITY AS m(mode, n)
 ORDER BY m.n
""".format(files=_BLOCKED_FILES, notes=_BLOCKED_NOTES)


def _blocks(skills, notes) -> dict:
    """The statement parameters of the blocks to read, and the order of `skills` (ordinals come back)."""
    skills = list(skills)
    return {"sb": [b for b, _, _ in skills], "sc": [c for _, c, _ in skills], "sp": [p for _, _, p in skills],
            "ns": sorted(set(notes))}


def _blocked(skills, ordinals, seqs) -> tuple[frozenset, frozenset]:
    skills = list(skills)
    return frozenset(tuple(skills[n - 1]) for n in ordinals or ()), frozenset(seqs or ())


@dataclass(frozen=True)
class Verdict:
    """Decisions for every requested mode, taken together, plus the policy in force at that instant, and the
    asked-for files and notes that a skill scan blocks at that instant."""
    decisions: dict
    policy_id: str | None
    blocked_files: frozenset = frozenset()
    blocked_notes: frozenset = frozenset()

    @property
    def allowed(self) -> bool:
        return all(d.allowed for d in self.decisions.values())


def decide(conn, principal: str, on_behalf_of: str | None, obj: str, modes: list[str], *, skills=(),
           notes=()) -> Verdict:
    """`skills`, `notes`: the files and notes whose skill block is read in the same statement (see above)."""
    _check(PRINCIPAL, principal, "principal")
    _check(OBJECT, obj, "object")
    if not modes:
        raise ValueError("at least one mode")
    for m in modes:
        _mode(m)
    if on_behalf_of is not None:
        _check(PRINCIPAL, on_behalf_of, "on_behalf_of")
    skills = list(skills)
    rows = conn.execute(_DECIDE, {"p": principal, "behalf": on_behalf_of, "holder": on_behalf_of or principal,
                                  "o": obj, "modes": list(modes), **_blocks(skills, notes)}).fetchall()
    decisions, policy_id = {}, None
    for mode, delegation_id, grant_ids, policy_id, *_ in rows:
        ids = tuple(grant_ids)
        if on_behalf_of is None:
            d = Decision(True, "grant", ids) if ids else Decision(False, "no grant")
        elif delegation_id is None:
            d = Decision(False, "no live delegation")
        elif not ids:
            d = Decision(False, "delegator no longer holds the right", delegation_id=delegation_id)
        else:
            d = Decision(True, "delegation", ids, delegation_id)
        decisions[mode] = d
    return Verdict(decisions, policy_id, *_blocked(skills, rows[0][4], rows[0][5]))


def authorize(conn, principal: str, on_behalf_of: str | None, obj: str, mode: str) -> Decision:
    return decide(conn, principal, on_behalf_of, obj, [mode]).decisions[mode]


def direct(conn, principal: str, obj: str, mode: str) -> Decision:
    """The principal's own right: a direct tuple, or membership in a role that holds it."""
    return authorize(conn, principal, None, obj, mode)


_ALLOWED = """
WITH held AS (
    SELECT g.object, g.relation AS mode, array_agg(DISTINCT x ORDER BY x) AS grant_ids
      FROM grant_tuple g
      LEFT JOIN grant_tuple mem ON mem.relation = 'member' AND mem.subject = %(holder)s AND mem.revoked_at IS NULL
           AND g.subject = mem.object || '#member'
     CROSS JOIN LATERAL unnest(ARRAY[g.id, mem.id]) AS x
     WHERE g.relation = ANY(%(modes)s) AND g.revoked_at IS NULL AND g.object LIKE 'book:%%'
       AND (g.subject = %(holder)s OR mem.id IS NOT NULL) AND x IS NOT NULL
     GROUP BY g.object, g.relation),
dels AS (
    SELECT DISTINCT ON (d.object, d.mode) d.object, d.mode, d.id
      FROM delegation d
     WHERE %(behalf)s::text IS NOT NULL AND d.delegate = %(p)s AND d.delegator = %(behalf)s
       AND d.mode = ANY(%(modes)s) AND d.revoked_at IS NULL AND clock_timestamp() < d.expires_at
     ORDER BY d.object, d.mode, d.id DESC)
SELECT h.object, h.mode, h.grant_ids, dels.id, b.current_policy, NULL::bigint[], NULL::bigint[]
  FROM held h
  LEFT JOIN dels ON dels.object = h.object AND dels.mode = h.mode
  JOIN book b ON 'book:' || b.slug = h.object
 WHERE %(behalf)s::text IS NULL OR dels.id IS NOT NULL
UNION ALL  -- one more row: the blocks, in the same statement
SELECT NULL, NULL, NULL, NULL, NULL, {files}, {notes}
""".format(files=_BLOCKED_FILES, notes=_BLOCKED_NOTES)


@dataclass(frozen=True)
class Allowed:
    """What the caller may do on every book, read in ONE statement (one snapshot): {object: {mode: Decision}}
    and the policy in force per object, and the asked-for files and notes that a skill scan blocks. Used as the
    search pre-filter and as its single final check."""
    decisions: dict
    policies: dict
    blocked_files: frozenset = frozenset()
    blocked_notes: frozenset = frozenset()

    def objects(self, mode: str) -> set[str]:
        return {o for o, modes in self.decisions.items() if mode in modes}


def allowed(conn, principal: str, on_behalf_of: str | None, modes: list[str], *, skills=(), notes=()) -> Allowed:
    """`skills`, `notes`: the files and notes whose skill block is read in the same statement (see above)."""
    _check(PRINCIPAL, principal, "principal")
    for m in modes:
        _mode(m)
    if on_behalf_of is not None:
        _check(PRINCIPAL, on_behalf_of, "on_behalf_of")
    skills = list(skills)
    rows = conn.execute(_ALLOWED, {"p": principal, "behalf": on_behalf_of, "holder": on_behalf_of or principal,
                                   "modes": list(modes), **_blocks(skills, notes)}).fetchall()
    decisions, policies, blocked = {}, {}, (frozenset(), frozenset())
    for obj, mode, grant_ids, delegation_id, policy_id, files, seqs in rows:
        if obj is None:
            blocked = _blocked(skills, files, seqs)
            continue
        reason = "delegation" if on_behalf_of else "grant"
        decisions.setdefault(obj, {})[mode] = Decision(True, reason, tuple(grant_ids), delegation_id)
        policies[obj] = policy_id
    return Allowed(decisions, policies, *blocked)
