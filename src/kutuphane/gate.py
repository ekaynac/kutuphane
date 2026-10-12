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

# Frontmatter `type`s and file names that mark an agent instruction (K3). Open vocabulary: extend as needed.
INSTRUCTION_TYPES = frozenset({"skill", "prompt", "agent-card", "agent-instructions"})
INSTRUCTION_FILES = frozenset({"AGENTS.md", "CLAUDE.md", "SKILL.md"})


class Denied(PermissionError):
    pass


class NotFound(LookupError):
    pass


@dataclass(frozen=True)
class Actor:
    principal: str
    on_behalf_of: str | None = None
    correlation_id: str = field(default_factory=lambda: uuid.uuid4().hex)


def is_instruction(entry: dict) -> bool:
    return entry.get("okf_type") in INSTRUCTION_TYPES or PurePosixPath(entry["path"]).name in INSTRUCTION_FILES


def _log(conn, actor: Actor, action: str, obj: str, mode: str, d: authz.Decision, policy_id, content_id, path,
         reason: str | None = None) -> None:
    conn.execute("INSERT INTO access_event (correlation_id, principal, on_behalf_of, action, object, mode, allowed, "
                 "reason, policy_id, grant_ids, delegation_id, content_id, path) "
                 "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                 (actor.correlation_id, actor.principal, actor.on_behalf_of, action, obj, mode, d.allowed,
                  reason or d.reason, policy_id, list(d.grant_ids), d.delegation_id, content_id, path))


def _decide(conn, actor: Actor, modes: list[str], obj: str) -> list[authz.Decision]:
    return [authz.authorize(conn, actor.principal, actor.on_behalf_of, obj, m) for m in modes]


def deliver_file(conn, actor: Actor, book: str, content_id: str, path: str) -> bytes:
    obj = f"book:{book}"
    policy_id = catalog.current_policy(conn, book)
    entry = catalog.manifest_entry(conn, book, content_id, path)
    modes = ["read"]
    if entry and actor.principal.startswith("agent:") and is_instruction(entry):
        modes.append("activate")

    for mode, d in zip(modes, _decide(conn, actor, modes, obj)):
        if not d.allowed:
            _log(conn, actor, mode, obj, mode, d, policy_id, content_id, path)
            raise Denied(f"{mode} on {obj}: {d.reason}")
    if entry is None:
        raise NotFound(f"{book}@{content_id}:{path}")

    data = catalog.read_file(conn, book, content_id, path)

    final = _decide(conn, actor, modes, obj)  # again, right before handing anything out
    for mode, d in zip(modes, final):
        if not d.allowed:
            _log(conn, actor, mode, obj, mode, d, policy_id, content_id, path, f"revoked before delivery: {d.reason}")
            raise Denied(f"{mode} on {obj}: revoked before delivery")
    for mode, d in zip(modes, final):
        _log(conn, actor, mode, obj, mode, d, policy_id, content_id, path)
    return data
