"""Agent files: which hidden folders are ingested, and which files are agent instructions (K3, D37).

Ingest skips hidden files and folders, except the agent folders below, so the instructions that agents actually
load are in the library and behind the `activate` gate. Inside an agent folder, dotfiles and other hidden
folders are still skipped. `.git/`, `.env*` and every other hidden path never enter a book, from a folder walk or
from a package.

A file is an instruction if any of these holds (names compared case-insensitively):
- its frontmatter `type` is an instruction type (`skill`, `prompt`, `agent_card`, …; separators ignored);
- its name starts with an instruction file name (`AGENTS.md`, `AGENTS.md.hostile`, `CLAUDE.local.md`, …);
- its name has an instruction suffix (`.mdc` Cursor rules; Copilot `.instructions.md`, `.prompt.md`, `.agent.md`,
  `.chatmode.md`);
- it is inside an agent folder (`.claude/agents/`, `.cursor/rules/`, `.github/instructions/`, `.agents/`, …);
- it is inside a skill folder: a folder that holds a `SKILL.md` (its `references/`, `scripts/`, assets).
The rule is fail closed: a false positive only means an agent also needs `activate`; people read with `read`.
Content that hides instructions under another name is caught (if at all) by the import scan (D29, M1f), not here.
"""
from collections.abc import Iterable
from pathlib import PurePosixPath

INSTRUCTION_TYPES = frozenset({"skill", "prompt", "agentcard", "agentinstructions", "systemprompt"})
INSTRUCTION_NAMES = ("agents.md", "agents.override.md", "claude.md", "claude.local.md", "gemini.md", "skill.md",
                     "copilot-instructions.md")
INSTRUCTION_SUFFIXES = (".mdc", ".instructions.md", ".prompt.md", ".agent.md", ".chatmode.md")
SKILL_FILE = "skill.md"
# Hidden folder -> the subfolders that are ingested (None: all of it). Files directly in the hidden folder are
# ingested only when they are instruction files (`.claude/CLAUDE.md`, `.github/copilot-instructions.md`), so
# `.claude/settings.local.json`, `.cursor/mcp.json` and the like never enter a book.
AGENT_FOLDERS = {
    ".claude": frozenset({"agents", "commands", "rules", "skills", "hooks"}),
    ".cursor": frozenset({"rules"}),
    ".github": frozenset({"instructions", "prompts", "agents", "chatmodes"}),
    ".agents": None,
    ".codex": None,
}


def _fold(value: str) -> str:
    return "".join(ch for ch in value.casefold() if ch.isalnum())


def instruction_name(name: str) -> bool:
    name = name.casefold()
    return name.startswith(INSTRUCTION_NAMES) or name.endswith(INSTRUCTION_SUFFIXES)


def admitted(parts: tuple[str, ...], is_dir: bool = False) -> bool:
    """Whether a relative path (as segments) is ingested: no hidden segment, or exactly one that is an agent
    folder, entered through an allowed subfolder (or naming an instruction file directly inside it)."""
    hidden = [i for i, p in enumerate(parts) if p.startswith(".")]
    if not hidden:
        return True
    if len(hidden) > 1 or parts[hidden[0]] not in AGENT_FOLDERS:
        return False
    subfolders, rest = AGENT_FOLDERS[parts[hidden[0]]], parts[hidden[0] + 1:]
    if not rest:
        return is_dir
    if len(rest) == 1 and not is_dir:
        return subfolders is None or instruction_name(rest[0])
    return subfolders is None or rest[0] in subfolders


def skill_dirs(paths: Iterable[str]) -> frozenset[str]:
    """Folders that hold a SKILL.md ("." for the book root): everything below them belongs to the skill."""
    return frozenset(str(PurePosixPath(p).parent) for p in paths if PurePosixPath(p).name.casefold() == SKILL_FILE)


def relative(folder: str, path: str) -> str | None:
    """The path relative to a skill folder ("." for the book root), or None when the file is not inside it."""
    if folder == ".":
        return path
    return path[len(folder) + 1:] if path.startswith(folder + "/") else None


def is_instruction(entry: dict, skills: frozenset[str] = frozenset()) -> bool:
    """`entry`: a manifest entry (path, okf_type). `skills`: skill_dirs() of every path in the same version."""
    path = PurePosixPath(entry["path"])
    return (_fold(entry.get("okf_type") or "") in INSTRUCTION_TYPES
            or instruction_name(path.name)
            or any(part in AGENT_FOLDERS for part in path.parts[:-1])
            or any(str(parent) in skills for parent in path.parents))
