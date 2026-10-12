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

MODES = ("discover", "read", "use", "activate")
PRINCIPAL = re.compile(r"^(user|agent|role):[a-z0-9][a-z0-9._-]{0,62}$")
OBJECT = re.compile(r"^book:[a-z0-9][a-z0-9-]{0,62}$")


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
       (SELECT b.current_policy FROM book b WHERE 'book:' || b.slug = %(o)s) AS policy_id
  FROM unnest(%(modes)s::text[]) WITH ORDINALITY AS m(mode, n)
 ORDER BY m.n
"""


@dataclass(frozen=True)
class Verdict:
    """Decisions for every requested mode, taken together, plus the policy in force at that instant."""
    decisions: dict
    policy_id: str | None

    @property
    def allowed(self) -> bool:
        return all(d.allowed for d in self.decisions.values())


def decide(conn, principal: str, on_behalf_of: str | None, obj: str, modes: list[str]) -> Verdict:
    _check(PRINCIPAL, principal, "principal")
    _check(OBJECT, obj, "object")
    for m in modes:
        _mode(m)
    if on_behalf_of is not None:
        _check(PRINCIPAL, on_behalf_of, "on_behalf_of")
    rows = conn.execute(_DECIDE, {"p": principal, "behalf": on_behalf_of, "holder": on_behalf_of or principal,
                                  "o": obj, "modes": list(modes)}).fetchall()
    decisions, policy_id = {}, None
    for mode, delegation_id, grant_ids, policy_id in rows:
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
    return Verdict(decisions, policy_id)


def authorize(conn, principal: str, on_behalf_of: str | None, obj: str, mode: str) -> Decision:
    return decide(conn, principal, on_behalf_of, obj, [mode]).decisions[mode]


def direct(conn, principal: str, obj: str, mode: str) -> Decision:
    """The principal's own right: a direct tuple, or membership in a role that holds it."""
    return authorize(conn, principal, None, obj, mode)
