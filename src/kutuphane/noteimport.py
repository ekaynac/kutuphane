"""Bulk import of an orchestrator's local memory into a journal (#75, docs/24 §23): `kutuphane note import`.

- One JSON object per line (JSONL), close to the nöbetçi local SQLite shape (`FIELDS`). Every record becomes a note
  through the propose rules of `notes.py`: the same canonical body and note id, secret scan, rights by derivation.
- **Standing:** every note is `pending`. A `standing` in the record is kept as a claim (`note_import`), never as an
  event; only a curator sets Standing (§8.2). The fields that `journal export` adds (`standing_history`, `writers`,
  `outcomes`, `ai_use`, `withheld`) are validated and not stored: the export file keeps them. A `withheld` record
  (the export left out its text) is refused.
- **Rights:** journal AND derivation, as `propose`; a record's `ai_use` narrows a new note further (a note exported
  from a stricter journal keeps its limits), never widens it. A note that already exists keeps its rights.
- **Origin (D70):** computed from the importer over the CLI channel: an `agent:` importer is `model`, a `user:`
  importer is `unknown`. An `origin` in the record is a claim (`write_record.origin_requested`); `human`,
  `assisted` and `tool` are refused with the notice `origin-claim-refused`.
- **Role and window** are checked against the kind (§8.1): a note has no own Role or Time in R1.
- **Links** name a record (`record`, in this file or an earlier import into the same journal) or an existing note
  or passage (`ref`). `derived_from` and `supersedes` are creation links: part of the note identity, pointing back,
  never in a cycle. Every other type is a later link (§6.3), so symmetric links such as `same_as` both ways import.
- **Idempotency:** the record id is the key in its journal (`note_import`). A known record id that gives the same
  note is a no-op; one that gives another note refuses the file (a note never changes: a correction is a new record
  with `supersedes`).
- **Order:** the whole file is validated first; nothing is written when a line is wrong. The pre-decision (`propose`
  on the journal, `read` on every book that a citation or link names) comes before any repository read; the writes
  run in ONE transaction under `gate.guard_many`: all records or none. Embeddings run after the commit, one note at
  a time, under the egress check of each note's `source_books`.
- **Limits:** the import is an operator act on the host (CLI only; no MCP tool or HTTP route). It has no daily write
  limit, and its writes do not count against the importer's MCP and HTTP limit (`notes._check_limit`). One file
  holds at most MAX_RECORDS records and MAX_BYTES bytes.
"""
import json
import re
from dataclasses import dataclass, field
from datetime import datetime

from . import gate, notes, origin as origins, secretscan
from .gate import Actor

FIELDS = ("id", "kind", "text", "standing", "role", "window", "scope", "commit", "origin", "created_at",
          "updated_at", "citations", "links", "class_key", "decision", "applies_to",
          "standing_history", "writers", "outcomes", "ai_use", "withheld")  # the last five: `journal export`
EXPORTED = {"standing_history": ("value", "set_by", "reason", "at"),  # validated, never stored (the file keeps them)
            "writers": ("principal", "on_behalf_of", "channel", "client_id", "origin", "at"),
            "outcomes": ("task_ref", "result", "at", "principal", "on_behalf_of", "origin")}
PROPOSED = ("kind", "text", "scope", "commit", "origin", "citations", "class_key", "decision",
            "applies_to")  # to notes.Draft
KIND_TIME = {k: "as_of" if k == "test_result" else "durable" for k in notes.KINDS}  # §8.1
RECORD_ID = re.compile(r"^[A-Za-z0-9._:-]{1,128}\Z")
MAX_RECORDS = 10_000
MAX_BYTES = 64 * 1024 * 1024
ERRORS_SHOWN = 5


@dataclass
class Record:
    line: int
    id: str
    args: dict                                    # the propose arguments, links left out
    creation: list = field(default_factory=list)  # [(type, "record" | "ref", value)]: derived_from, supersedes
    later: list = field(default_factory=list)     # the same for every other type
    standing: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    draft: notes.Draft | None = None
    resolved: list = field(default_factory=list)  # later links as [(type, notes._target)]
    ai_use: dict | None = None                    # the exported rights: they narrow a new note's rights, never widen


def read(path) -> list[str]:
    """The lines of a JSONL file, at most MAX_BYTES."""
    with open(path, "rb") as f:
        data = f.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError(f"{path}: more than {MAX_BYTES} bytes; split the file")
    try:
        return data.decode("utf-8").splitlines()
    except UnicodeDecodeError:
        raise ValueError(f"{path}: not UTF-8") from None


# --- step 1: validate every record (no I/O) ----------------------------------------------------------------------

def _time(name: str, value) -> datetime | None:
    if value is None:
        return None
    try:
        t = datetime.fromisoformat(value) if isinstance(value, str) else None
    except ValueError:
        t = None
    if t is None or t.tzinfo is None:
        raise ValueError(f"{name} must be an ISO 8601 time with a time zone")
    return t


def _links(rid: str, value) -> tuple[list, list]:
    creation, later = [], []
    if value is None:
        return creation, later
    if not isinstance(value, list) or len(value) > notes.MAX_LINKS:
        raise ValueError(f"links must be a list of at most {notes.MAX_LINKS}")
    for link in value:
        if not isinstance(link, dict) or set(link) not in ({"type", "record"}, {"type", "ref"}):
            raise ValueError("a link must be {type, record} or {type, ref}")
        kind, (how, target) = link["type"], next((k, v) for k, v in link.items() if k != "type")
        if kind not in notes.LINK_TYPES or not isinstance(target, str):
            raise ValueError(f"link type must be one of {', '.join(notes.LINK_TYPES)}, with a string target")
        if how == "record" and target == rid:
            raise ValueError("a record cannot link to itself")
        (creation if kind in notes.CREATION_ONLY else later).append((kind, how, target))
    return creation, later


def _exported(obj: dict) -> None:
    """The fields that only `journal export` writes: their shape is checked. Only `ai_use` has an effect: it narrows
    the rights of a new note (`_write_note`); the others are never trusted or stored."""
    if obj.get("withheld") is not None:
        raise ValueError(f"withheld: the export left out the text ({obj['withheld']}); the record cannot be imported")
    for name, keys in EXPORTED.items():
        value = obj.get(name, [])
        if not isinstance(value, list) or any(not isinstance(e, dict) or set(e) != set(keys) for e in value):
            raise ValueError(f"{name} must be a list of {{{', '.join(keys)}}}")
        for e in value:
            if any(v is not None and not isinstance(v, str) for v in e.values()):
                raise ValueError(f"{name}: every value must be a string or null")
            if _time(f"{name}.at", e["at"]) is None:
                raise ValueError(f"{name}.at is required")
            if name == "standing_history" and e["value"] not in notes.STANDINGS:
                raise ValueError(f"standing_history.value must be one of {', '.join(notes.STANDINGS)}")
    ai_use = obj.get("ai_use")
    if ai_use is not None and (not isinstance(ai_use, dict) or set(ai_use) != {"search", "ai_input", "train"}
                               or set(ai_use.values()) - {"y", "n"}):
        raise ValueError("ai_use must be {search, ai_input, train} of y or n")


def _record(line: int, obj) -> Record:
    if not isinstance(obj, dict):
        raise ValueError("not a JSON object")
    unknown = sorted(set(obj) - set(FIELDS))
    if unknown:
        raise ValueError(f"unknown field(s) {', '.join(unknown)}; fields: {', '.join(FIELDS)}")
    rid, kind = obj.get("id"), obj.get("kind")
    if not isinstance(rid, str) or not RECORD_ID.match(rid):
        raise ValueError("id must match [A-Za-z0-9._:-]{1,128}")
    if kind not in notes.KINDS:
        raise ValueError(f"kind must be one of {', '.join(notes.KINDS)}")
    if obj.get("role") not in (None, notes.KIND_ROLE[kind]):
        raise ValueError(f"role must be {notes.KIND_ROLE[kind]} for kind {kind} (the kind gives the Role)")
    if obj.get("window") not in (None, KIND_TIME[kind]):
        raise ValueError(f"window must be {KIND_TIME[kind]} for kind {kind} (a note has no own time window)")
    if obj.get("standing") not in (None, *notes.STANDINGS):
        raise ValueError(f"standing must be one of {', '.join(notes.STANDINGS)}")
    _exported(obj)
    creation, later = _links(rid, obj.get("links"))
    return Record(line, rid, {k: obj[k] for k in PROPOSED if k in obj}, creation, later, obj.get("standing"),
                  _time("created_at", obj.get("created_at")), _time("updated_at", obj.get("updated_at")),
                  ai_use=obj.get("ai_use"))


def _parse(lines) -> list[Record]:
    records, errors, seen = [], [], set()
    for n, text in enumerate(lines, start=1):
        if not text.strip():
            continue
        try:
            try:
                obj = json.loads(text)
            except json.JSONDecodeError:
                obj = None
            r = _record(n, obj)
            if r.id in seen:
                raise ValueError(f"duplicate record id {r.id}")
            seen.add(r.id)
            records.append(r)
        except ValueError as exc:
            errors.append(f"line {n}: {exc}")
    _refuse(errors)
    if not records:
        raise ValueError("the file has no records")
    if len(records) > MAX_RECORDS:
        raise ValueError(f"more than {MAX_RECORDS} records; split the file")
    return records


def _refuse(errors: list[str]) -> None:
    if errors:
        more = f" (and {len(errors) - ERRORS_SHOWN} more)" if len(errors) > ERRORS_SHOWN else ""
        raise ValueError("import refused, nothing written: " + "; ".join(errors[:ERRORS_SHOWN]) + more)


def _order(records: list[Record]) -> list[Record]:
    """File order, changed only where a creation link needs its target record first (creation links point back)."""
    index = {r.id: i for i, r in enumerate(records)}
    deps = [[index[t] for _, how, t in r.creation if how == "record" and t in index] for r in records]
    state, out = [None] * len(records), []
    for start in range(len(records)):
        if state[start]:
            continue
        state[start], stack = "open", [(start, iter(deps[start]))]
        while stack:
            i, rest = stack[-1]
            nxt = next(rest, None)
            if nxt is None:
                state[i] = "done"
                out.append(records[i])
                stack.pop()
            elif state[nxt] == "open":
                raise ValueError(f"import refused, nothing written: line {records[nxt].line}: creation links "
                                 f"(derived_from, supersedes) form a cycle through record {records[nxt].id}")
            elif state[nxt] is None:
                state[nxt] = "open"
                stack.append((nxt, iter(deps[nxt])))
    return out


# --- steps 2-3: resolve records, build the drafts (database reads only) -------------------------------------------

def _known(conn, book: str, rids) -> dict:
    """{record id: note id} of earlier imports into the journal."""
    return dict(conn.execute("SELECT i.record, n.id FROM note_import i JOIN note n ON n.seq = i.note_seq "
                             "WHERE i.book = %s AND i.record = ANY(%s)", (book, sorted(rids))).fetchall())


def _record_ids(records: list[Record]) -> set[str]:
    """The record ids that the file gives or names in a link."""
    return {r.id for r in records} | {t for r in records for _, how, t in r.creation + r.later if how == "record"}


def _drafts(book: str, ordered: list[Record], known: dict) -> None:
    """Builds each record's draft and resolves its later links. Every error names its line."""
    ids, errors = {}, []

    def resolve(how: str, target: str) -> str:
        if how == "ref":
            return target
        if target in ids:
            return f"{book}@{ids[target]}"
        if target in known:
            return f"{book}@{known[target]}"
        raise ValueError(f"no record {target} in this file or in an earlier import into {book}")

    for r in ordered:  # a creation link's target record comes first in `ordered`
        try:
            links = [{"type": kind, "ref": resolve(how, t)} for kind, how, t in r.creation]
            r.draft = notes.Draft({**r.args, "book": book, "links": links})
            rules = sorted({f.rule for t in [r.draft.text, *(r.draft.options or [])] for f in secretscan.findings(t)})
            if rules:
                raise ValueError(f"text refused: credential-like content ({', '.join(rules)})")
            if r.id in known and known[r.id] != r.draft.id:
                raise ValueError(f"record {r.id} was imported as {book}@{known[r.id]}; this file gives another note "
                                 "(a note never changes: a correction is a new record with a supersedes link)")
            ids[r.id] = r.draft.id
        except (ValueError, gate.NotFound) as exc:
            errors.append((r.line, f"line {r.line}: {exc}"))
    for r in ordered:  # later links may name any record of the file
        if r.draft is None:
            continue
        try:
            r.resolved = [(kind, notes._target(resolve(how, t))) for kind, how, t in r.later]
            _check_later(r)
        except ValueError as exc:
            errors.append((r.line, f"line {r.line}: {exc}"))
    _refuse([e for _, e in sorted(errors)])


def _check_later(r: Record) -> None:
    seen = set()
    for kind, target in r.resolved:
        if target[0] == "passage" and kind not in notes.PASSAGE_LINKS:
            raise ValueError(f"a passage can only be the target of {' or '.join(notes.PASSAGE_LINKS)}")
        if kind == "same_as" and target[1] != r.draft.book:
            raise ValueError("same_as stays inside one book")
        if target[0] == "note" and (target[1], target[2]) == (r.draft.book, r.draft.id):
            raise ValueError("a note cannot link to itself")
        key = (kind, notes._target_text(target))
        if key in seen:
            raise ValueError("the same link is given twice")
        seen.add(key)


def _needs(records: list[Record]) -> dict:
    needs = {}
    for r in records:
        for obj, modes in r.draft.needs().items():
            needs.setdefault(obj, set()).update(modes)
        for _, target in r.resolved:
            needs.setdefault(f"book:{notes._target_book(target)}", set()).add("read")
    return needs


# --- steps 4-6: decide, write, embed ------------------------------------------------------------------------------

def _write_note(conn, actor: Actor, r: Record, excerpts: dict) -> tuple[dict, tuple | None]:
    d = r.draft
    allow_search, allow_ai, allow_train, books, found = notes._derive(conn, d)
    if r.ai_use:  # an exported note keeps its rights in a looser journal: a claim may narrow, never widen
        allow_search, allow_ai, allow_train = (allow_search and r.ai_use["search"] == "y",
                                               allow_ai and r.ai_use["ai_input"] == "y",
                                               allow_train and r.ai_use["train"] == "y")
    row = conn.execute("SELECT seq FROM note WHERE book = %s AND id = %s", (d.book, d.id)).fetchone()
    seq = row[0] if row else notes._insert_note(conn, d, allow_search, allow_ai, allow_train, books)
    stored, notice = origins.compute(actor, d.origin_requested)
    write_seq = notes._write_record(conn, actor, "propose", seq, row is None, d.origin_requested, stored, notice)
    if row is None:
        notes._insert_parts(conn, d, seq, write_seq, found, excerpts)
    conn.execute("INSERT INTO note_import (book, record, note_seq, write_seq, standing_claimed, created_at, "
                 "updated_at) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                 (d.book, r.id, seq, write_seq, r.standing, r.created_at, r.updated_at))
    item = {"status": "existing" if row else "created", "origin": stored, "origin_notice": notice}
    return item, None if row else (allow_search, allow_ai, books, seq)


def _write_link(conn, actor: Actor, r: Record, kind: str, target) -> bool:
    found = notes._notes(conn, [("note", r.draft.book, r.draft.id)] + ([target] if target[0] == "note" else []))
    if target[0] == "passage":
        notes._passages_exist(conn, [target[1]])
    src = found[(r.draft.book, r.draft.id)][0]
    if notes._existing_link(conn, src, kind, target, found):
        return False
    stored, _ = origins.compute(actor, None)
    write_seq = notes._write_record(conn, actor, "link", None, False, None, stored, None)
    notes._insert_link(conn, src, r.draft.book, kind, target, found, creation=False, write_seq=write_seq)
    return True


def run(conn, actor: Actor, book: str, lines, embedder=None) -> dict:
    """Import the JSONL `lines` into the journal `book` as `actor` (the `--by` principal). Returns the report."""
    if actor.channel != "cli" or actor.on_behalf_of is not None:
        raise ValueError("notes are imported only by the CLI, as one principal")
    notes._principal("importer", actor.principal)
    if not notes.BOOK.match(book):
        raise ValueError("book must be a book slug")
    notes._journal(conn, book)
    records = _parse(lines)
    ordered = _order(records)
    rids = _record_ids(records)
    known = _known(conn, book, rids)
    _drafts(book, ordered, known)
    needs = _needs(records)
    notes._decide(conn, actor, needs, "import")                                  # before any repository read
    new = [r for r in ordered if r.id not in known]
    excerpts = {}
    for r in new:
        try:
            excerpts[r.id] = notes._excerpts(conn, r.draft)
        except ValueError as exc:
            _refuse([f"line {r.line}: {exc}"])
    items = {r.id: {"status": "unchanged", "origin": None, "origin_notice": None} for r in records}

    def work():
        notes._lock(conn)
        if _known(conn, book, rids) != known:                                   # under the lock: a racing import
            raise ValueError("another import into this journal ran meanwhile; run the import again")
        embeds, made = {}, {"created": 0, "existing": 0}
        for r in new:
            items[r.id], embed = _write_note(conn, actor, r, excerpts[r.id])
            if embed:
                embeds[r.id] = embed
        for r in ordered:
            for kind, target in r.resolved:
                made["created" if _write_link(conn, actor, r, kind, target) else "existing"] += 1
        seqs = dict(conn.execute("SELECT id, seq FROM note WHERE book = %s AND id = ANY(%s)",
                                 (book, sorted({r.draft.id for r in records}))).fetchall())
        standing = notes.effective_standing(conn, list(seqs.values()), notes.NOW)
        for r in records:
            items[r.id]["standing"] = standing[seqs[r.draft.id]][0]
        return embeds, made

    embeds, made = gate.guard_many(conn, actor, needs, work, action="import",
                                   items={f"book:{book}": [{"ref": r.draft.ref} for r in new]})
    report = []
    for r in records:
        item = items[r.id]
        vector = None
        if r.id in embeds:
            allow_search, allow_ai, books, seq = embeds[r.id]
            value, vector = notes._embed(conn, embedder, actor, r.draft, allow_search, allow_ai, books)
            if value is not None:
                conn.execute("INSERT INTO note_vector (note_seq, model, embedding) VALUES (%s, %s, %s::vector) "
                             "ON CONFLICT DO NOTHING", (seq, value.model, value.literal()))
        report.append({"record": r.id, "ref": r.draft.ref, "status": item["status"], "standing": item["standing"],
                       "standing_claimed": r.standing, "origin": item["origin"],
                       "origin_notice": item["origin_notice"], "vector": vector})
    return {"book": book, "records": len(records),
            **{s: sum(i["status"] == s for i in report) for s in ("created", "existing", "unchanged")},
            "links": made, "items": report}
