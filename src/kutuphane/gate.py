"""The single authorization gate (docs/07 §3). Every path that hands content out goes through `deliver`.

- The decision is taken before the fetch and taken again right before delivery, so a revocation that lands
  while a request is in flight still stops the content (AT-04, AT-05).
- Agent instructions (K3) reach an agent only with a separate `activate` grant, logged as its own event
  (D37, AT-12). People may read them as reference with `read`.
- Every decision, allowed or not, is written to `access_event` with the policy and grant rows behind it.
"""
import uuid
from dataclasses import dataclass, field

from psycopg.types.json import Jsonb

from . import authz, catalog
from .profiles import is_instruction  # noqa: F401  (re-exported: the gate owns the K3 rule's use)


class Denied(PermissionError):
    pass


class NotFound(LookupError):
    pass


@dataclass(frozen=True)
class Actor:
    principal: str
    on_behalf_of: str | None = None
    correlation_id: str = field(default_factory=lambda: uuid.uuid4().hex)


def log_event(conn, actor: Actor, action: str, obj: str, mode: str, d: authz.Decision, policy_id, content_id, path,
         reason: str | None = None, profile_id=None, items=None) -> None:
    conn.execute("INSERT INTO access_event (correlation_id, principal, on_behalf_of, action, object, mode, allowed, "
                 "reason, policy_id, grant_ids, delegation_id, content_id, path, profile_id, items) "
                 "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                 (actor.correlation_id, actor.principal, actor.on_behalf_of, action, obj, mode, d.allowed,
                  reason or d.reason, policy_id, list(d.grant_ids), d.delegation_id, content_id, path, profile_id,
                  Jsonb(items) if items is not None else None))


def guard(conn, actor: Actor, obj: str, modes: list[str], fetch, *, action: str, content_id=None, path=None,
          profile_id=None, items=None):
    """Decide, fetch, decide again, then log and hand out. Every single-object content path goes through here."""
    def log(mode, d, policy_id, reason=None):
        log_event(conn, actor, action if mode == "read" else mode, obj, mode, d, policy_id, content_id, path, reason,
             profile_id, items if d.allowed else None)

    first = authz.decide(conn, actor.principal, actor.on_behalf_of, obj, modes)
    for mode, d in first.decisions.items():
        if not d.allowed:
            log(mode, d, first.policy_id)
            raise Denied(f"{mode} on {obj}: {d.reason}")
    data = fetch()
    # Again, right before handing anything out: one statement for every mode and the policy in force.
    final = authz.decide(conn, actor.principal, actor.on_behalf_of, obj, modes)
    for mode, d in final.decisions.items():
        if not d.allowed:
            log(mode, d, final.policy_id, f"revoked before delivery: {d.reason}")
            raise Denied(f"{mode} on {obj}: revoked before delivery")
    for mode, d in final.decisions.items():
        log(mode, d, final.policy_id)
    return data


def modes_for(actor: Actor, instruction: bool) -> list[str]:
    return ["read", "activate"] if instruction and actor.principal.startswith("agent:") else ["read"]


def deliver_file(conn, actor: Actor, book: str, content_id: str, path: str) -> bytes:
    entry = catalog.manifest_entry(conn, book, content_id, path)
    modes = modes_for(actor, bool(entry) and is_instruction(entry))

    def fetch():
        if entry is None:
            raise NotFound(f"{book}@{content_id}:{path}")
        return catalog.read_file(conn, book, content_id, path)
    return guard(conn, actor, f"book:{book}", modes, fetch, action="read", content_id=content_id, path=path)


def check_many(conn, actor: Actor, needs: dict, *, action: str, items: dict | None = None,
               policies_out: dict | None = None) -> None:
    """Right before handing out something built from several books (an answer, a reopened answer): decide every
    book and mode in ONE statement, log, and refuse unless all hold. `needs`: {object: {modes}}."""
    if not needs:
        return
    modes = ["read", "activate"] if any("activate" in m for m in needs.values()) else ["read"]
    final = authz.allowed(conn, actor.principal, actor.on_behalf_of, modes)
    missing = sorted(o for o, m in needs.items() if not set(m) <= set(final.decisions.get(o, {})))
    if missing:
        for obj in missing:
            log_event(conn, actor, action, obj, "read", authz.Decision(False, "no current right"),
                      final.policies.get(obj), None, None)
        raise Denied(f"{action}: no current right on {', '.join(missing)}")
    for obj, ms in needs.items():
        for mode in sorted(ms, key=modes.index):
            log_event(conn, actor, action if mode == "read" else mode, obj, mode, final.decisions[obj][mode],
                      final.policies.get(obj), None, None, items=(items or {}).get(obj))
    if policies_out is not None:
        policies_out.update(final.policies)
