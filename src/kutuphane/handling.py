"""Handling labels on MCP read results (#80): what the content of a result needs from the client that receives it.

The labels go under the namespaced `_meta` key `kutuphane/handling` of `search_library`, `open_citation`,
`read_document` and `query_notes` results, of `skills/list` and `skills/get` entries, and of `skill://` reads:
- `books`: the E5 policy now (Sensitivity, Egress) of every book whose content is in the result: the book of each
  passage or file, the journal of each note and its `source_books` (the books that the note text came from) that the
  caller may read now. A source book the caller cannot read is never named (T24, review #18);
- `unnamed_sources`: notes only, the number of source books left out of `books` that way (absent when none);
- `sensitivity`, `egress`: the strictest over every book of the result, the unnamed source books included, so a note
  derived from restricted text stays restricted (`restricted` over `normal`, `local_only` over `cloud_ok`), so a
  client can apply one rule to the whole result. Absent when the result holds no content: "no claim", never
  "normal";
- `skill_scans`: for each skill folder (D71) that holds a file or passage of the result, a reference to its latest
  scan record (the curator proposal that `kutuphane skill show <book>` lists by `id`). Absent when no scan record
  applies.

The labels describe the result; they grant nothing and refuse nothing (the gate did that before). The mapping to
the experimental `io.modelcontextprotocol/trust-annotations` extension is planned in docs/guide/mcp.md, section 4.4;
nothing here depends on that draft.
"""
from collections.abc import Iterable

KEY = "kutuphane/handling"
STRICT = {"sensitivity": "restricted", "egress": "local_only"}

_SCANS = """
SELECT DISTINCT ON (s.book, s.content_id, s.skill_path)
       s.book, s.content_id, s.skill_path, s.id, s.status, s.recommendation,
       EXISTS (SELECT 1 FROM skill_block b
                WHERE b.book = s.book AND b.content_id = s.content_id AND b.skill_path = s.skill_path)
  FROM unnest(%s::text[], %s::text[], %s::text[]) AS f(book, content_id, path)
  JOIN skill_scan s ON s.book = f.book AND s.content_id = f.content_id
                   AND (s.skill_path = '.' OR starts_with(f.path, s.skill_path || '/'))
 ORDER BY s.book, s.content_id, s.skill_path, s.id DESC
"""


def policies(conn, books: Iterable[str]) -> dict:
    """{book: {sensitivity, egress}} of the policy in force now."""
    books = sorted(set(books))
    if not books:
        return {}
    rows = conn.execute("SELECT b.slug, p.doc->>'sensitivity', p.doc->>'egress' FROM book b "
                        "JOIN policy_version p ON p.id = b.current_policy WHERE b.slug = ANY(%s) ORDER BY b.slug",
                        (books,)).fetchall()
    return {slug: {"sensitivity": sensitivity, "egress": egress} for slug, sensitivity, egress in rows}


def scans(conn, files: Iterable[tuple[str, str, str]]) -> list[dict]:
    """The latest scan record of every skill folder that holds one of the (book, content_id, path) files."""
    files = sorted(set(files))
    if not files:
        return []
    rows = conn.execute(_SCANS, ([f[0] for f in files], [f[1] for f in files], [f[2] for f in files])).fetchall()
    return [{"book": b, "content_id": c, "skill_path": p, "scan_id": i, "status": status,
             "recommendation": recommendation, "blocking": blocking}
            for b, c, p, i, status, recommendation, blocking in rows]


def build(per_book: dict, skill_scans: list[dict], unnamed: Iterable[dict] = ()) -> dict:
    """The labels of a result from its books' policies and its scan references. `unnamed`: the policies of books
    whose content is in the result but that the caller cannot read; they make the overall labels stricter, and
    only their number is shown."""
    unnamed = list(unnamed)
    out: dict = {"books": dict(sorted(per_book.items()))}
    if unnamed:
        out["unnamed_sources"] = len(unnamed)
    if per_book or unnamed:
        for name, strict in STRICT.items():
            values = {p[name] for p in (*per_book.values(), *unnamed)}
            out[name] = strict if strict in values else values.pop()  # else one value: E5 has two per attribute
    if skill_scans:
        out["skill_scans"] = skill_scans
    return out


def labels(conn, books: Iterable[str], files: Iterable[tuple[str, str, str]] = ()) -> dict:
    """`books`: the books whose content is in the result. `files`: (book, content_id, path) of its files and
    passages, for the skill-scan references."""
    return build(policies(conn, books), scans(conn, files))


def note_labels(conn, refs: Iterable[str], readable: Iterable[str]) -> dict:
    """The labels of notes (`book@nt_…`): `readable`, the books (slugs) of the caller's final read set."""
    readable = set(readable)
    per_book = policies(conn, note_books(conn, refs))
    return build({b: p for b, p in per_book.items() if b in readable}, [],
                 [p for b, p in per_book.items() if b not in readable])


def note_books(conn, refs: Iterable[str]) -> set[str]:
    """The journals of these note references (`book@nt_…`) and the books their text came from (`source_books`)."""
    pairs = [ref.split("@", 1) for ref in sorted(set(refs))]
    if not pairs:
        return set()
    rows = conn.execute("SELECT n.book, n.source_books FROM note n "
                        "JOIN unnest(%s::text[], %s::text[]) AS r(book, id) ON n.book = r.book AND n.id = r.id",
                        ([b for b, _ in pairs], [i for _, i in pairs])).fetchall()
    return {b for book, sources in rows for b in (book, *sources)}
