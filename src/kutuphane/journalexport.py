"""The journal export (R3, 2026-11-01): `kutuphane journal export`. One JSON record per note of a journal, in the
`note import` record shape (`noteimport.FIELDS`), so an export is a backup and a git path that imports back.

- **Record:** `id` is the note id; `links` name a note of the same file as `{type, record}` and anything else as
  `{type, ref}`, so an import into a journal with the same slug (a restore, another installation) gives the same
  note ids and links. The note id hashes its creation links with their book: into another slug, a note with a
  `derived_from` or `supersedes` link to a note of the file gets a new id.
- **What only the export carries:** `standing_history` [{value, set_by, reason, at}], `writers` (the propose writes:
  principal, on_behalf_of, channel, client_id, origin, at), `outcomes`, `ai_use` and `withheld`. `standing` is the
  Standing now and `origin` the shown origin (docs/25 §7.6). The import validates these fields and keeps only the
  latest Standing as a claim (`noteimport`); the file is the complete record.
- **Rights:** `read` on the journal and on every book that its notes cite or link, by the gate of
  `gate.guard_many`, never the owner credential; the journal gets one `access_event` with `action = export_journal`
  and `items = [{ref, standing_seq}]` (AT-09: rollback finds the export).
- **Refusals, as packages and the decision export:** a `restricted` journal is refused; a note with a `restricted`
  book in its `source_books` (count `restricted`) or derived from a file with `license: unknown` (count
  `licence_unknown`, #143) is left out; a note that depends on a blocked skill (D71) has `text` and `decision` null
  and `withheld` set, and does not import.
- **Rights travel with the note (docs/23 principle 5):** `ai_input` and `train` limit model use, not a copy, so the
  text goes out with `ai_use` (note AND journal closure now). The decision export, a training set, gates on them.
"""
from . import catalog, decisions, gate, noteimport, notes, notesquery
from . import origin as origins
from .gate import Actor

ACTION = "export_journal"

_NOTES = f"""
SELECT n.seq, n.id, n.kind, n.body, n.class_key, n.scope_repo, n.scope_branch, n.scope_paths, n.observed_commit,
       n.applies_to, n.written_at, n.options, n.choice, {decisions.RESTRICTED_SOURCE}
  FROM note n WHERE n.book = %s AND n.seq <= %s ORDER BY n.seq
"""
_NAMED_BOOKS = """
SELECT c.cite_book FROM note_citation c JOIN note n ON n.seq = c.note_seq
 WHERE n.book = %(book)s AND n.seq <= %(w)s AND c.cite_book IS NOT NULL
UNION
SELECT coalesce(l.dst_note_book, l.dst_book) FROM note_link l WHERE l.src_book = %(book)s AND l.seq <= %(w)s
"""


def _links(conn, seqs: list[int], w: int) -> dict:
    """{seq: [{type, record | ref}]}: creation links first, then later links, each in write order."""
    ids = dict(conn.execute("SELECT seq, id FROM note WHERE seq = ANY(%s)", (seqs,)).fetchall())
    out = {}
    for src, type_, dst, n_book, n_id, p_book, p_ct, p_pf, p_path, p_ord in conn.execute(
            "SELECT l.src, l.type, l.dst_note, d.book, d.id, l.dst_book, l.dst_content_id, l.dst_profile_id, "
            "l.dst_path, l.dst_ordinal FROM note_link l LEFT JOIN note d ON d.seq = l.dst_note "
            "WHERE l.src = ANY(%s) AND l.seq <= %s ORDER BY l.src, NOT l.creation, l.seq", (seqs, w)):
        target = {"record": ids[dst]} if dst in ids else {
            "ref": f"{n_book}@{n_id}" if n_book else f"{p_book}@{p_ct}/{p_pf}/{p_path}#{p_ord}"}
        out.setdefault(src, []).append({"type": type_, **target})
    return out


def _records(conn, book: str, w: int) -> tuple[list[dict], dict]:
    found = conn.execute(_NOTES, (book, w)).fetchall()
    free = [r[:-1] for r in found if not r[-1]]
    unlicensed = notes.unknown_licence(conn, [r[0] for r in free])  # #143: never exported
    rows = [r for r in free if r[0] not in unlicensed]
    seqs = [r[0] for r in rows]
    standing = notes.effective_standing(conn, seqs, w)
    origin = origins.shown(conn, seqs, w)
    cited = decisions.citations(conn, seqs)
    links = _links(conn, seqs, w)
    history = decisions._by_note(conn.execute(
        "SELECT note_seq, value, set_by, reason, at FROM standing_event WHERE note_seq = ANY(%s) AND seq <= %s "
        "ORDER BY seq", (seqs, w)))
    writers = decisions._by_note(conn.execute(
        "SELECT note_seq, principal, on_behalf_of, channel, client_id, origin, at FROM write_record "
        "WHERE action = 'propose' AND note_seq = ANY(%s) AND seq <= %s ORDER BY seq", (seqs, w)))
    outcomes = decisions._by_note(conn.execute(
        "SELECT note_seq, task_ref, result, at, principal, on_behalf_of, origin FROM outcome "
        "WHERE note_seq = ANY(%s) AND seq <= %s ORDER BY seq", (seqs, w)))
    records = []
    for (seq, note_id, kind, body, class_key, repo, branch, paths, commit, applies_to, written_at, options,
         choice) in rows:
        records.append({
            "id": note_id, "kind": kind, "text": body, "standing": standing[seq][0], "role": notes.KIND_ROLE[kind],
            "window": noteimport.KIND_TIME[kind], "origin": origin[seq][0], "created_at": decisions._iso(written_at),
            "scope": None if repo is None else {"repo": repo, "branch": branch, "paths": list(paths)},
            "commit": commit, "citations": [ref for _book, ref in cited.get(seq, [])],
            "links": links.get(seq, []), "class_key": class_key,
            "decision": {"options": list(options), "choice": choice} if options else None,
            "applies_to": applies_to,
            "standing_history": [{"value": v, "set_by": s, "reason": r, "at": decisions._iso(at)}
                                 for v, s, r, at in history.get(seq, [])],
            "writers": [{"principal": p, "on_behalf_of": b, "channel": ch, "client_id": c, "origin": o,
                         "at": decisions._iso(at)} for p, b, ch, c, o, at in writers.get(seq, [])],
            "outcomes": [{"task_ref": t, "result": r, "at": decisions._iso(at), "principal": p, "on_behalf_of": b,
                          "origin": o} for t, r, at, p, b, o in outcomes.get(seq, [])],
            "_seq": seq, "_standing_seq": standing[seq][1]})
    return records, {"restricted": len(found) - len(free), "licence_unknown": len(unlicensed)}


def _finish(conn, final, records: list[dict]) -> list[dict]:
    """Inside the export transaction, after the final decision: `ai_use` now, and the text withheld only for a note
    that depends on a blocked skill in that decision."""
    now = decisions.rights(conn, final, [r["_seq"] for r in records])
    for r in records:
        seq = r.pop("_seq")
        r["ai_use"], r["withheld"] = now[seq][0], gate.SKILL_WITHHELD if seq in final.blocked_notes else None
        if r["withheld"]:
            r["text"], r["decision"] = None, None
    return records


def export(conn, actor: Actor, book: str) -> tuple[list[dict], dict]:
    """(records, summary) of the journal `book`, in note order, read as `actor`."""
    if not isinstance(book, str) or not notes.BOOK.match(book):
        raise ValueError("book must be a book slug")
    notes._journal(conn, book)
    obj = f"book:{book}"
    notes._decide(conn, actor, {obj: {"read"}}, ACTION)  # before any read of its notes
    if catalog.book_state(conn, book)["policy"]["sensitivity"] == "restricted":  # docs/09 §1
        raise ValueError(f"{book} is restricted: restricted content never leaves this installation")
    w = notesquery.watermark(conn)
    needs = {obj: {"read"}} | {f"book:{b}": {"read"} for (b,) in conn.execute(_NAMED_BOOKS, {"book": book, "w": w})}
    items, left_out = {obj: []}, {}

    def work():
        records, counts = _records(conn, book, w)
        left_out.update(counts)
        items[obj].extend({"ref": f"{book}@{r['id']}", "standing_seq": r.pop("_standing_seq")} for r in records)
        return records

    records = gate.guard_many(conn, actor, needs, work, action=ACTION, items=items,
                              finish=lambda final, data: _finish(conn, final, data),
                              notes_of=lambda data: [r["_seq"] for r in data])
    return records, {"records": len(records), "withheld": sum(r["withheld"] is not None for r in records),
                     **left_out, "book": book, "watermark": w}
