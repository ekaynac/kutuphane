"""The single authorization gate (docs/07 §3). Every path that hands content out goes through `deliver`.

- The decision is taken before the fetch and taken again right before delivery, so a revocation that lands
  while a request is in flight still stops the content (AT-04, AT-05).
- Agent instructions (K3) reach an agent only with a separate `activate` grant, logged as its own event
  (D37, AT-12). People may read them as reference with `read`.
- Every decision, allowed or not, is written to `access_event` with the policy and grant rows behind it.
"""
import uuid
from dataclasses import dataclass, field
from pathlib import PurePosixPath

from . import authz, catalog

# Frontmatter `type`s and file names that mark an agent instruction (K3), compared case- and separator-
# insensitively so `Skill`, `agent_card` or `agents.md` cannot slip past the activation gate. K3 status is
# curator-declared metadata; content that hides instructions under another type is caught (if at all) by the
# import scan (D29, M1f), not here.
INSTRUCTION_TYPES = frozenset({"skill", "prompt", "agentcard", "agentinstructions", "systemprompt"})
INSTRUCTION_FILES = frozenset({"agents.md", "claude.md", "skill.md", "gemini.md"})


class Denied(PermissionError):
    pass


class NotFound(LookupError):
    pass


@dataclass(frozen=True)
class Actor:
    principal: str
    on_behalf_of: str | None = None
    correlation_id: str = field(default_factory=lambda: uuid.uuid4().hex)


def _fold(value: str) -> str:
    return "".join(ch for ch in value.casefold() if ch.isalnum())


def is_instruction(entry: dict) -> bool:
    okf_type = entry.get("okf_type") or ""
    name = PurePosixPath(entry["path"]).name.casefold()
    return _fold(okf_type) in INSTRUCTION_TYPES or name in INSTRUCTION_FILES


def _log(conn, actor: Actor, action: str, obj: str, mode: str, d: authz.Decision, policy_id, content_id, path,
         reason: str | None = None) -> None:
    conn.execute("INSERT INTO access_event (correlation_id, principal, on_behalf_of, action, object, mode, allowed, "
                 "reason, policy_id, grant_ids, delegation_id, content_id, path) "
                 "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                 (actor.correlation_id, actor.principal, actor.on_behalf_of, action, obj, mode, d.allowed,
                  reason or d.reason, policy_id, list(d.grant_ids), d.delegation_id, content_id, path))


def deliver_file(conn, actor: Actor, book: str, content_id: str, path: str) -> bytes:
    obj = f"book:{book}"
    entry = catalog.manifest_entry(conn, book, content_id, path)
    modes = ["read"]
    if entry and actor.principal.startswith("agent:") and is_instruction(entry):
        modes.append("activate")

    first = authz.decide(conn, actor.principal, actor.on_behalf_of, obj, modes)
    for mode, d in first.decisions.items():
        if not d.allowed:
            _log(conn, actor, mode, obj, mode, d, first.policy_id, content_id, path)
            raise Denied(f"{mode} on {obj}: {d.reason}")
    if entry is None:
        raise NotFound(f"{book}@{content_id}:{path}")

    data = catalog.read_file(conn, book, content_id, path)

    # Again, right before handing anything out: one statement for every mode and the policy in force.
    final = authz.decide(conn, actor.principal, actor.on_behalf_of, obj, modes)
    for mode, d in final.decisions.items():
        if not d.allowed:
            _log(conn, actor, mode, obj, mode, d, final.policy_id, content_id, path,
                 f"revoked before delivery: {d.reason}")
            raise Denied(f"{mode} on {obj}: revoked before delivery")
    for mode, d in final.decisions.items():
        _log(conn, actor, mode, obj, mode, d, final.policy_id, content_id, path)
    return data
