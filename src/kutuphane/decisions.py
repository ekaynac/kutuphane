"""The decision export (docs/24 §21.4, #74): one JSON record per `decision_proposal` note, as labels for decision
models: the context, the options offered, the choice, the actor, the outcome rows and the `ai_use` rights.

- `read` on each exported journal, by the gate of `gate.guard_many`; each book gets one `access_event` with
  `action = export_decisions` and `items = [{ref, standing_seq}]` (AT-09; the #79 report finds it).
- A record holds the text, the options and the choice only when the note's `ai_input` and `train` (note AND journal
  now) are both true. Else it holds references and SHA-256 hashes only. The hashes are always present.
- Passage citations and links into books that the reader may not read now are left out (as `query_notes`).
"""
import hashlib
from datetime import datetime, timezone

from . import authz, coderepo, gate, notes, notesquery
from .gate import Actor

ACTION = "export_decisions"
WITHHELD = "rights do not allow AI training (ai_input and train)"

_DECISIONS = """
SELECT n.seq, n.book, n.id, n.body, n.class_key, n.scope_repo, n.scope_branch, n.scope_paths, n.observed_commit,
       n.written_at, n.options, n.choice, n.search AND j.search, n.ai_input AND j.ai_input, n.train AND j.train
  FROM note n JOIN note_journal j ON j.seq = n.seq
 WHERE n.book = ANY(%s) AND n.kind = 'decision_proposal' AND n.seq <= %s
 ORDER BY n.book, n.seq
"""


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _iso(t: datetime) -> str:
    return t.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _yn(value: bool) -> str:
    return "y" if value else "n"


def _by_note(rows) -> dict:
    out = {}
    for seq, *rest in rows:
        out.setdefault(seq, []).append(rest)
    return out


def _context_refs(conn, seqs: list[int], read: set, w: int) -> tuple[dict, dict]:
    """({seq: citation refs in order}, {seq: [{type, ref}] creation links}) without unreadable books."""
    citations = {}
    for seq, kind, book, content_id, profile_id, path, ordinal, repo, commit, start, end, symbol in conn.execute(
            "SELECT note_seq, kind, cite_book, content_id, profile_id, path, ordinal, repo, commit, line_start, "
            "line_end, symbol FROM note_citation WHERE note_seq = ANY(%s) ORDER BY note_seq, n", (seqs,)):
        if kind == "code":  # the note's own repositories: no other book
            citations.setdefault(seq, []).append(str(coderepo.CodeCitation(repo, commit, path, start, end, symbol)))
        elif f"book:{book}" in read:
            citations.setdefault(seq, []).append(f"{book}@{content_id}/{profile_id}/{path}#{ordinal}")
    links = {}
    for src, type_, n_book, n_id, p_book, p_ct, p_pf, p_path, p_ord in conn.execute(
            "SELECT l.src, l.type, d.book, d.id, l.dst_book, l.dst_content_id, l.dst_profile_id, l.dst_path, "
            "l.dst_ordinal FROM note_link l LEFT JOIN note d ON d.seq = l.dst_note "
            "WHERE l.src = ANY(%s) AND l.creation AND l.seq <= %s ORDER BY l.src, l.type, l.seq", (seqs, w)):
        book = n_book or p_book
        if f"book:{book}" in read:
            ref = f"{n_book}@{n_id}" if n_book else f"{p_book}@{p_ct}/{p_pf}/{p_path}#{p_ord}"
            links.setdefault(src, []).append({"type": type_, "ref": ref})
    return citations, links


def _records(conn, actor: Actor, books: list[str]) -> tuple[list[dict], int]:
    w = notesquery.watermark(conn)
    read = authz.allowed(conn, actor.principal, actor.on_behalf_of, ["read"]).objects("read")
    rows = conn.execute(_DECISIONS, (books, w)).fetchall()
    seqs = [r[0] for r in rows]
    standing = notes.effective_standing(conn, seqs, w)
    writers = {s: rest for s, *rest in conn.execute(
        "SELECT note_seq, principal, on_behalf_of, client_id, origin FROM write_record "
        "WHERE note_seq = ANY(%s) AND creates", (seqs,))}
    outcomes = _by_note(conn.execute(
        "SELECT note_seq, task_ref, result, at, principal, on_behalf_of, origin FROM outcome "
        "WHERE note_seq = ANY(%s) AND seq <= %s ORDER BY seq", (seqs, w)))
    citations, links = _context_refs(conn, seqs, read, w)
    records = []
    for (seq, book, note_id, body, class_key, repo, branch, paths, commit, written_at, options, choice, search,
         ai_input, train) in rows:
        shown = ai_input and train
        principal, behalf, client_id, origin = writers[seq]
        records.append({
            "ref": f"{book}@{note_id}", "book": book, "written_at": _iso(written_at), "standing": standing[seq][0],
            "context": {"text": body if shown else None, "text_sha256": _sha(body), "class_key": class_key,
                        "scope": None if repo is None else {"repo": repo, "branch": branch, "paths": list(paths)},
                        "commit": commit, "citations": citations.get(seq, []), "links": links.get(seq, [])},
            "options": list(options) if shown and options else None, "choice": choice if shown else None,
            "options_sha256": [_sha(o) for o in options] if options else None,
            "choice_sha256": _sha(choice) if choice else None,
            "actor": {"principal": principal, "on_behalf_of": behalf, "client_id": client_id, "origin": origin},
            "outcomes": [{"task_ref": t, "result": r, "at": _iso(at), "principal": p, "on_behalf_of": b,
                          "origin": o} for t, r, at, p, b, o in outcomes.get(seq, [])],
            "ai_use": {"search": _yn(search), "ai_input": _yn(ai_input), "train": _yn(train)},
            "withheld": None if shown else WITHHELD,
            "_standing_seq": standing[seq][1]})
    return records, w


def export(conn, actor: Actor, books: list[str] | None = None) -> tuple[list[dict], dict]:
    """(records, summary). `books`: the journals to export; None = every journal the reader may read now."""
    if books is None:
        readable = authz.allowed(conn, actor.principal, actor.on_behalf_of, ["read"]).objects("read")
        journals = {b for (b,) in conn.execute("SELECT book FROM journal")}
        books = sorted(b for b in (o.removeprefix("book:") for o in readable) if b in journals)
    else:
        for b in books:
            if not isinstance(b, str) or not notes.BOOK.match(b):
                raise ValueError("book must be a book slug")
        books = sorted(set(books))
    if not books:
        return [], {"records": 0, "withheld": 0, "books": [], "watermark": notesquery.watermark(conn)}
    items = {f"book:{b}": [] for b in books}  # filled by the work, logged by guard_many after the final decision

    def work():
        records, w = _records(conn, actor, books)
        for r in records:
            items[f"book:{r['book']}"].append({"ref": r["ref"], "standing_seq": r.pop("_standing_seq")})
        return records, w

    records, w = gate.guard_many(conn, actor, {f"book:{b}": {"read"} for b in books}, work, action=ACTION,
                                 items=items)
    return records, {"records": len(records), "withheld": sum(r["withheld"] is not None for r in records),
                     "books": books, "watermark": w}
