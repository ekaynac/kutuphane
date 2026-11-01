"""The decision export (docs/24 §21.4, #74): one JSON record per `decision_proposal` note, as labels for decision
models: the context, the options offered, the choice, the actor, the outcome rows and the `ai_use` rights.

- `read` on each exported journal, by the gate of `gate.guard_many`; each book gets one `access_event` with
  `action = export_decisions` and `items = [{ref, standing_seq}]` (AT-09; the #79 report finds it).
- A record holds the text, the options and the choice only when the note's `ai_input` and `train` (note AND journal
  now) are both true. Else it holds references and SHA-256 hashes only. The hashes are always present.
- Passage citations and links into books that the reader may not read now are left out (as `query_notes`). Each
  kept passage reference has its state now in `context.passages` {handle: {status[, moved_to, match]}} (#140: a
  re-index moves it, or leaves it stale); the handles stay as written.
- Both cuts use the FINAL decision of the gate (`guard_many(finish=…)`, Astra review #14): a read revoked, or a
  source journal restricted, while the records were built is applied before anything is handed out.
- A record of a note that depends on a skill that a scan blocks (D71, SQL `note_skill_blocked`) is cut in the same
  way, whoever exports: the export is model input. The final statement of the gate reads those blocks with the
  rights (Astra review #15).
- A note with a `restricted` book in its `source_books` (book policy now) is left out: Sensitivity owns export
  (docs/09 §1, docs/24 §23). The summary counts them (`restricted`).
- A note derived from a file with `license: unknown` (its citations and `derived_from` passages, also through its
  `derived_from` notes, `notes.unknown_licence`) is left out: derivation stays in this installation (#143, docs/11
  §5.2). The summary counts them (`licence_unknown`).
"""
import hashlib
from datetime import datetime, timezone

from . import authz, coderepo, gate, notes, notesquery, passagemap
from . import origin as origins
from .gate import Actor

ACTION = "export_decisions"
WITHHELD = "rights do not allow AI training (ai_input and train)"

# A note with a `restricted` book in its sources (book policy now): Sensitivity owns export (docs/09 §1)
RESTRICTED_SOURCE = """EXISTS (SELECT 1 FROM book b JOIN policy_version p ON p.id = b.current_policy
                WHERE b.slug = ANY(n.source_books) AND p.doc->>'sensitivity' = 'restricted')"""

_DECISIONS = f"""
SELECT n.seq, n.book, n.id, n.body, n.class_key, n.scope_repo, n.scope_branch, n.scope_paths, n.observed_commit,
       n.written_at, n.options, n.choice, n.search AND j.search, n.ai_input AND j.ai_input, n.train AND j.train,
       {RESTRICTED_SOURCE}
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


def citations(conn, seqs: list[int]) -> dict:
    """{seq: [(book, citation ref)]} in order. The book is None for a code citation (the note's own repositories)."""
    out = {}
    for seq, kind, book, content_id, profile_id, path, ordinal, repo, commit, start, end, symbol in conn.execute(
            "SELECT note_seq, kind, cite_book, content_id, profile_id, path, ordinal, repo, commit, line_start, "
            "line_end, symbol FROM note_citation WHERE note_seq = ANY(%s) ORDER BY note_seq, n", (seqs,)):
        if kind == "code":
            out.setdefault(seq, []).append((None, str(coderepo.CodeCitation(repo, commit, path, start, end, symbol))))
        else:
            out.setdefault(seq, []).append((book, f"{book}@{content_id}/{profile_id}/{path}#{ordinal}"))
    return out


def _context_refs(conn, seqs: list[int], w: int) -> tuple[dict, dict]:
    """(`citations`, {seq: [(book, {type, ref})]} creation links), in order. The read filter runs in `_finish`, on
    the final decision."""
    links = {}
    for src, type_, n_book, n_id, p_book, p_ct, p_pf, p_path, p_ord in conn.execute(
            "SELECT l.src, l.type, d.book, d.id, l.dst_book, l.dst_content_id, l.dst_profile_id, l.dst_path, "
            "l.dst_ordinal FROM note_link l LEFT JOIN note d ON d.seq = l.dst_note "
            "WHERE l.src = ANY(%s) AND l.creation AND l.seq <= %s ORDER BY l.src, l.type, l.seq", (seqs, w)):
        ref = f"{n_book}@{n_id}" if n_book else f"{p_book}@{p_ct}/{p_pf}/{p_path}#{p_ord}"
        links.setdefault(src, []).append((n_book or p_book, {"type": type_, "ref": ref}))
    return citations(conn, seqs), links


def rights(conn, final, seqs: list[int]) -> dict:
    """{seq: (ai_use, withheld reason or None)} now, inside the export transaction after the final decision: the text
    goes out only when the note's `ai_input` and `train` (note AND every journal of its closure, `note_journal`) hold
    and the note depends on no blocked skill in that decision (`final.blocked_notes`)."""
    out = {}
    for seq, search, ai_input, train in conn.execute(
            "SELECT n.seq, n.search AND j.search, n.ai_input AND j.ai_input, n.train AND j.train "
            "FROM note n JOIN note_journal j ON j.seq = n.seq WHERE n.seq = ANY(%s)", (seqs,)):
        reason = WITHHELD if not (ai_input and train) else gate.SKILL_WITHHELD if seq in final.blocked_notes else None
        out[seq] = {"search": _yn(search), "ai_input": _yn(ai_input), "train": _yn(train)}, reason
    return out


def _passage_states(conn, handles: set) -> dict:
    """{handle: state now} of passage handles (#140: current, moved or stale)."""
    keys = {(c.book, c.content_id, c.profile_id, c.path, c.ordinal) for c in map(notes.parse_passage, handles)}
    return {passagemap.handle(k): s.out() for k, s in passagemap.resolve(conn, keys).items()}


def _records(conn, actor: Actor, books: list[str]) -> tuple[list[dict], int, int]:
    w = notesquery.watermark(conn)
    found = conn.execute(_DECISIONS, (books, w)).fetchall()
    rows = [r[:-1] for r in found if not r[-1]]
    seqs = [r[0] for r in rows]
    standing = notes.effective_standing(conn, seqs, w)
    writers = {s: rest for s, *rest in conn.execute(
        "SELECT note_seq, principal, on_behalf_of, client_id FROM write_record "
        "WHERE note_seq = ANY(%s) AND creates", (seqs,))}
    origin_at = origins.shown(conn, seqs, w)  # docs/25 §7.6: a live R3 confirmation, else the write path
    outcomes = _by_note(conn.execute(
        "SELECT note_seq, task_ref, result, at, principal, on_behalf_of, origin FROM outcome "
        "WHERE note_seq = ANY(%s) AND seq <= %s ORDER BY seq", (seqs, w)))
    citations, links = _context_refs(conn, seqs, w)
    records = []
    for (seq, book, note_id, body, class_key, repo, branch, paths, commit, written_at, options, choice, search,
         ai_input, train) in rows:
        shown = ai_input and train
        principal, behalf, client_id = writers[seq]
        origin, entered_by, confirmed_by = origin_at[seq]
        records.append({
            "ref": f"{book}@{note_id}", "book": book, "written_at": _iso(written_at), "standing": standing[seq][0],
            "context": {"text": body if shown else None, "text_sha256": _sha(body), "class_key": class_key,
                        "scope": None if repo is None else {"repo": repo, "branch": branch, "paths": list(paths)},
                        "commit": commit, "citations": [], "links": []},
            "options": list(options) if shown and options else None, "choice": choice if shown else None,
            "options_sha256": [_sha(o) for o in options] if options else None,
            "choice_sha256": _sha(choice) if choice else None,
            "actor": {"principal": principal, "on_behalf_of": behalf, "client_id": client_id, "origin": origin,
                      **({"entered_by": entered_by, "confirmed_by": confirmed_by} if confirmed_by else {})},
            "outcomes": [{"task_ref": t, "result": r, "at": _iso(at), "principal": p, "on_behalf_of": b,
                          "origin": o} for t, r, at, p, b, o in outcomes.get(seq, [])],
            "ai_use": {"search": _yn(search), "ai_input": _yn(ai_input), "train": _yn(train)},
            "withheld": None if shown else WITHHELD,
            "_standing_seq": standing[seq][1], "_seq": seq,
            "_citations": citations.get(seq, []), "_links": links.get(seq, [])})
    return records, w, len(found) - len(rows)


def _finish(conn, final, data):
    """Inside the export transaction, right after the final read decision (Astra review #14): a reference is kept
    only when its book is readable in that decision, and the text, options and choice only by `rights`; else the
    record is cut to references and hashes."""
    records, w, restricted = data
    read = final.objects("read")
    now = rights(conn, final, [r["_seq"] for r in records])
    kept = []  # per record: the passage handles it keeps
    for r in records:
        seq = r.pop("_seq")
        cited = [(book, ref) for book, ref in r.pop("_citations") if book is None or f"book:{book}" in read]
        r["context"]["citations"] = [ref for _book, ref in cited]
        r["context"]["links"] = [link for book, link in r.pop("_links") if f"book:{book}" in read]
        kept.append([ref for book, ref in cited if book is not None]
                    + [link["ref"] for link in r["context"]["links"] if not notesquery.is_note_ref(link["ref"])])
        r["ai_use"], withheld = now[seq]
        if withheld:
            r["context"]["text"], r["options"], r["choice"], r["withheld"] = None, None, None, withheld
    states = _passage_states(conn, {h for hs in kept for h in hs})
    for r, hs in zip(records, kept):
        r["context"]["passages"] = {h: states[h] for h in hs}
    return records, w, restricted


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
        return [], {"records": 0, "withheld": 0, "restricted": 0, "licence_unknown": 0, "books": [],
                    "watermark": notesquery.watermark(conn)}
    items = {f"book:{b}": [] for b in books}  # filled by the work, logged by guard_many after the final decision
    left_out = {"licence_unknown": 0}

    def work():
        records, w, restricted = _records(conn, actor, books)
        unlicensed = notes.unknown_licence(conn, [r["_seq"] for r in records])  # #143: never exported
        records = [r for r in records if r["_seq"] not in unlicensed]
        left_out["licence_unknown"] = len(unlicensed)
        for r in records:
            items[f"book:{r['book']}"].append({"ref": r["ref"], "standing_seq": r.pop("_standing_seq")})
        return records, w, restricted

    records, w, restricted = gate.guard_many(conn, actor, {f"book:{b}": {"read"} for b in books}, work,
                                             action=ACTION, items=items,
                                             finish=lambda final, data: _finish(conn, final, data),
                                             notes_of=lambda data: [r["_seq"] for r in data[0]])
    return records, {"records": len(records), "withheld": sum(r["withheld"] is not None for r in records),
                     "restricted": restricted, **left_out, "books": books, "watermark": w}
