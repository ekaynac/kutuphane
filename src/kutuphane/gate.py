"""The single authorization gate (docs/07 §3). Every path that hands content out goes through `deliver`.

- The decision is taken before the fetch and taken again right before delivery, so a revocation that lands
  while a request is in flight still stops the content (AT-04, AT-05).
- Agent instructions (K3) reach an agent only with a separate `activate` grant, logged as its own event
  (D37, AT-12). People may read them as reference with `read`. A skill that a SkillSpector scan blocks (D71,
  skillscan.py) is refused to agents even with that grant, until a curator clears it; a scan never grants. The
  final decision and the block are read by ONE statement (Astra review #15): `authz.decide(skills=…)`,
  `authz.allowed(skills=…, notes=…)`.
- Every decision, allowed or not, is written to `access_event` with the policy and grant rows behind it.
"""
import uuid
from dataclasses import dataclass, field, replace

from psycopg.types.json import Jsonb

from . import authz, catalog
from .agentfiles import is_instruction  # the K3 rule; the gate owns its use


class Denied(PermissionError):
    pass


class NotFound(LookupError):
    pass


CHANNELS = ("cli", "http", "mcp")


@dataclass(frozen=True)
class Actor:
    principal: str
    on_behalf_of: str | None = None
    correlation_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    # docs/24 §5.1: what the authenticated token's client is (recorded only, never a right), and the entry point
    # the request came through. Only the server entry points set the channel; anything else is the CLI.
    client_id: str | None = None
    channel: str = "cli"

    def __post_init__(self):
        if self.channel not in CHANNELS:
            raise ValueError(f"channel must be one of {', '.join(CHANNELS)}")


def log_event(conn, actor: Actor, action: str, obj: str, mode: str, d: authz.Decision, policy_id, content_id, path,
         reason: str | None = None, profile_id=None, items=None, memory_seq=None) -> None:
    conn.execute("INSERT INTO access_event (correlation_id, principal, on_behalf_of, action, object, mode, allowed, "
                 "reason, policy_id, grant_ids, delegation_id, content_id, path, profile_id, items, memory_seq) "
                 "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                 (actor.correlation_id, actor.principal, actor.on_behalf_of, action, obj, mode, d.allowed,
                  reason or d.reason, policy_id, list(d.grant_ids), d.delegation_id, content_id, path, profile_id,
                  Jsonb(items) if items is not None else None, memory_seq))


def guard(conn, actor: Actor, obj: str, modes: list[str], fetch, *, action: str, content_id=None, path=None,
          profile_id=None, items=None, blocks_of=None):
    """Decide, fetch, decide again, then log and hand out. Every single-object content path goes through here.
    An agent's `activate` on a file inside a skill that a scan blocks (D71) is refused in that final step.
    `blocks_of(data)`, if given: the (book, content_id, path) files whose skill block refuses this delivery (a
    whole skill, #80); by default the file `content_id`/`path` when `activate` is asked."""
    def log(mode, d, policy_id, reason=None):
        log_event(conn, actor, action if mode == "read" else mode, obj, mode, d, policy_id, content_id, path, reason,
             profile_id, items if d.allowed else None)

    first = authz.decide(conn, actor.principal, actor.on_behalf_of, obj, modes)
    for mode, d in first.decisions.items():
        if not d.allowed:
            log(mode, d, first.policy_id)
            raise Denied(f"{mode} on {obj}: {d.reason}")
    # The work (a read, or a write such as feedback) and the final decision share one transaction: if the final
    # decision says no, a write is rolled back and nothing is handed out. The refusal is logged after rollback.
    revoked, blocked = None, False
    try:
        with conn.transaction():
            data = fetch()
            # Again, right before handing anything out: one statement for every mode, the policy in force and, for
            # `activate`, the skill block of this file (or of every file `blocks_of` names).
            skills = blocks_of(data) if blocks_of is not None else \
                [(obj.removeprefix("book:"), content_id, path)] if "activate" in modes and content_id is not None else []
            final = authz.decide(conn, actor.principal, actor.on_behalf_of, obj, modes, skills=skills)
            revoked = next(((m, d) for m, d in final.decisions.items() if not d.allowed), None)
            blocked = revoked is None and bool(final.blocked_files)
            if revoked or blocked:
                raise _Rollback
    except _Rollback:
        if blocked:
            d = replace(final.decisions["activate"], allowed=False, reason=SKILL_BLOCKED)
            log("activate", d, final.policy_id)
            raise Denied(f"activate on {obj}: {SKILL_BLOCKED}") from None
        mode, d = revoked
        log(mode, d, final.policy_id, f"revoked before delivery: {d.reason}")
        raise Denied(f"{mode} on {obj}: revoked before delivery") from None
    for mode, d in final.decisions.items():
        log(mode, d, final.policy_id)
    return data


class _Rollback(Exception):
    pass


def modes_for(actor: Actor, instruction: bool) -> list[str]:
    return ["read", "activate"] if instruction and actor.principal.startswith("agent:") else ["read"]


SKILL_BLOCKED = "skill blocked by a scan (D71); only a curator clears it"
# A note that depends on a blocked skill (SQL `note_skill_blocked`): its text is withheld from readers that put it
# into a model, as for ai_input = false (Astra review #15).
SKILL_WITHHELD = "derived from a skill blocked by a scan (D71); only a curator clears it"


def log_blocked(conn, actor: Actor, blocked, policies: dict) -> None:
    """One refused `activate` event per file of a blocked skill. `blocked`: (book, content_id, path); `policies`:
    the policy in force per object, from the same final decision."""
    for book, content_id, path in sorted(blocked):
        log_event(conn, actor, "activate", f"book:{book}", "activate", authz.Decision(False, SKILL_BLOCKED),
                  policies.get(f"book:{book}"), content_id, path)


def deliver_file(conn, actor: Actor, book: str, content_id: str, path: str) -> bytes:
    entry = catalog.manifest_entry(conn, book, content_id, path)
    instruction = bool(entry) and is_instruction(entry, catalog.skill_dirs(conn, book, content_id))
    modes = modes_for(actor, instruction)

    def fetch():
        if entry is None:
            raise NotFound(f"{book}@{content_id}:{path}")
        return catalog.read_file(conn, book, content_id, path)
    return guard(conn, actor, f"book:{book}", modes, fetch, action="read", content_id=content_id, path=path)


def check_many(conn, actor: Actor, needs: dict, *, action: str, items: dict | None = None,
               policies_out: dict | None = None, skills=()) -> None:
    """Right before handing out something built from several books (an answer, a reopened answer): decide every
    book and mode in ONE statement, log, and refuse unless all hold. `needs`: {object: {modes}}. `skills`: the
    (book, content_id, path) of the instruction passages an agent receives; the same statement reads their skill
    blocks (D71), and a blocked one refuses the whole delivery."""
    if not needs:
        return
    modes = ["read", "activate"] if any("activate" in m for m in needs.values()) else ["read"]
    final = authz.allowed(conn, actor.principal, actor.on_behalf_of, modes, skills=sorted(set(skills)))
    missing = sorted(o for o, m in needs.items() if not set(m) <= set(final.decisions.get(o, {})))
    if missing:
        for obj in missing:
            log_event(conn, actor, action, obj, "read", authz.Decision(False, "no current right"),
                      final.policies.get(obj), None, None)
        raise Denied(f"{action}: no current right on {', '.join(missing)}")
    if final.blocked_files:
        log_blocked(conn, actor, final.blocked_files, final.policies)
        raise Denied(f"{action}: activate refused: {SKILL_BLOCKED}")
    for obj, ms in needs.items():
        for mode in sorted(ms, key=modes.index):
            log_event(conn, actor, action if mode == "read" else mode, obj, mode, final.decisions[obj][mode],
                      final.policies.get(obj), None, None, items=(items or {}).get(obj))
    if policies_out is not None:
        policies_out.update(final.policies)


def guard_many(conn, actor: Actor, needs: dict, work, *, action: str, items: dict | None = None, finish=None,
               notes_of=None):
    """`guard` for work that depends on several books (docs/24 §6.1, a write such as a note that cites other books).
    `needs`: {object: {modes}}. Every object and mode is decided in ONE statement before the work, so a refused
    request does nothing. The work runs in a transaction, and every object and mode is decided again in ONE
    statement inside it: if any right was lost meanwhile, the work is rolled back and nothing is handed out. Each
    decision is logged; a refusal is logged after the rollback, so it stays on record.
    `finish(final, data) -> data`, if given, runs in the transaction right after that final decision (which then
    also decides `read` on every book): what the work built from optional rights outside `needs` is cut to it.
    `notes_of(data) -> note seqs`, if given: the final statement also reads which of those notes depend on a
    blocked skill (`final.blocked_notes`, D71), for `finish` to withhold their text."""
    if not needs:
        raise ValueError("guard_many needs at least one object")
    wanted = {m for ms in needs.values() for m in ms} | ({"read"} if finish else set())
    modes = sorted(wanted, key=authz.MODES.index)

    def lost(verdict: authz.Allowed) -> list[tuple[str, str]]:
        return [(o, m) for o in sorted(needs) for m in sorted(needs[o], key=modes.index)
                if m not in verdict.decisions.get(o, {})]

    def refuse(verdict: authz.Allowed, missing, reason: str) -> None:
        for obj, mode in missing:
            log_event(conn, actor, action if mode == "read" else mode, obj, mode, authz.Decision(False, reason),
                      verdict.policies.get(obj), None, None)

    first = authz.allowed(conn, actor.principal, actor.on_behalf_of, modes)
    if missing := lost(first):
        refuse(first, missing, "no current right")
        raise Denied(f"{action}: no current right on {', '.join(sorted({o for o, _ in missing}))}")
    try:
        with conn.transaction():
            data = work()
            final = authz.allowed(conn, actor.principal, actor.on_behalf_of, modes,
                                  notes=notes_of(data) if notes_of else ())
            if missing := lost(final):
                raise _Rollback
            if finish is not None:
                data = finish(final, data)
    except _Rollback:
        refuse(final, missing, "revoked before delivery: no current right")
        raise Denied(f"{action}: revoked before delivery") from None
    for obj in sorted(needs):
        for mode in sorted(needs[obj], key=modes.index):
            log_event(conn, actor, action if mode == "read" else mode, obj, mode, final.decisions[obj][mode],
                      final.policies.get(obj), None, None, items=(items or {}).get(obj))
    return data
