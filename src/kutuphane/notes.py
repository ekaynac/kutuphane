"""Agent notes (docs/24 §3–§8). Slice A owns this module; this is the minimal contract-exact read part that the
read path (slice B) needs. Slice A's version replaces it at integration."""
import re

from . import ids, search

KIND_ROLE = {"decision_proposal": "rule", "convention": "rule", "finding": "evidence", "lesson": "evidence",
             "dead_end": "evidence", "test_result": "evidence"}
_REF = re.compile(r"^([a-z0-9][a-z0-9-]{0,62})@(nt_[0-9a-f]{64})\Z")


def parse_ref(ref: str) -> tuple[str, str]:
    """`<book>@nt_<64 hex>` -> (book, note id)."""
    m = _REF.match(ref) if isinstance(ref, str) else None
    if not m:
        raise ValueError("malformed note reference")
    return m.group(1), m.group(2)


def parse_passage(handle) -> search.Citation:
    """A passage handle `book@ct_…/pf_…/path#ordinal`, as `open_citation` takes it."""
    if not isinstance(handle, str) or re.search(r"[\x00-\x1f\x7f]", handle):
        raise ValueError("malformed passage handle")
    try:
        head, ordinal = handle.rsplit("#", 1)
        book, rest = head.split("@", 1)
        content_id, profile_id, path = rest.split("/", 2)
        return search.Citation(book, content_id, profile_id, ids.normalize_path(path), int(ordinal))
    except ValueError:
        raise ValueError("malformed passage handle") from None


def effective_standing(conn, seqs, w: int) -> dict:
    """{seq: (value, event_seq | None)}: the latest Standing event with seq <= w, else the implicit pending."""
    out = {s: ("pending", None) for s in seqs}
    for note_seq, value, seq in conn.execute(
            "SELECT DISTINCT ON (note_seq) note_seq, value, seq FROM standing_event "
            "WHERE note_seq = ANY(%s) AND seq <= %s ORDER BY note_seq, seq DESC", (list(seqs), w)):
        out[note_seq] = (value, seq)
    return out


def clusters(conn, book: str, w: int) -> dict:
    """{note_seq: min seq of its same_as component}, for every note of the book with seq <= w."""
    rows = conn.execute("""
        WITH RECURSIVE e AS (
            SELECT src AS a, dst_note AS b FROM note_link
             WHERE type = 'same_as' AND src_book = %(b)s AND seq <= %(w)s
            UNION ALL
            SELECT dst_note, src FROM note_link
             WHERE type = 'same_as' AND src_book = %(b)s AND seq <= %(w)s),
        reach(root, n) AS (
            SELECT seq, seq FROM note WHERE book = %(b)s AND seq <= %(w)s
            UNION
            SELECT r.root, e.b FROM reach r JOIN e ON e.a = r.n)
        SELECT n, min(root) FROM reach GROUP BY n""", {"b": book, "w": w}).fetchall()
    return dict(rows)


def item_info(conn, note_seq: int) -> dict:
    """kstd-shaped rights of a note: its stored restrictions AND its journal's current values."""
    row = conn.execute(
        "SELECT n.search AND j.search, n.ai_input AND j.ai_input, "
        "       (SELECT CASE WHEN bool_or(w.origin = 'model') THEN 'model' ELSE 'unknown' END "
        "          FROM write_record w WHERE w.note_seq = n.seq AND w.action = 'propose') "
        "  FROM note n JOIN journal j ON j.book = n.book WHERE n.seq = %s", (note_seq,)).fetchone()
    yn = {True: "y", False: "n"}
    return {"origin": row[2], "ai_use": {"search": yn[row[0]], "ai_input": yn[row[1]]}}
