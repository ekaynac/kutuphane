"""The passage map (#140): after a re-index, a citation or a passage link follows to the new passage.

A publication that makes a new (content, profile) current gives every passage of the book a new handle. Notes cite
passages and link to them (`about`, `derived_from`) by the exact handle, and that handle stays: it is part of the
note (audit), and the old passage still opens. The map adds the successor of an old passage in the version that is
current now, for the same path:

- `exact`: a passage with the same text (so the same embedded text, `vectors.input_sha256`);
- `overlap`: else, when the content version is the same (only the profile cuts differently, so the source text is
  the same), the passage that holds the largest share of the old passage's word pairs, at least OVERLAP_MIN; when
  the content changed, only a passage that holds the whole old text (Astra review #20: a changed word, `enable` to
  `disable`, can keep most word pairs and change the meaning);
- `none`: else no successor. The reads show the citation as `stale`; nothing is dropped.

The reads show a passage reference as `current` (in the current version), `moved` (with `moved_to` and `match`) or
`stale`. The map is written for every referenced passage: by the publication that changes the current version
(`map_book`, in its transaction), by a note write that references an old passage (`ensure`), and by
`kutuphane reindex-map <book>` for books published before migration 040. A read that finds no stored row computes
the same answer without writing it, so a reference is never shown as current or dropped by mistake; the skill-block
gate (SQL `note_skill_blocked`, migration 040) reads the stored rows."""
import re
from collections import Counter
from dataclasses import dataclass

MATCHES = ("exact", "overlap", "none")
OVERLAP_MIN = 0.5  # the share of the old passage's word pairs that its successor must hold
_WORD = re.compile(r"\w+")


@dataclass(frozen=True)
class Successor:
    """The state of one passage reference now: `current`, `moved` (to `moved_to`, by `match`) or `stale`."""
    status: str
    moved_to: str | None = None
    match: str | None = None

    def out(self) -> dict:
        """The keys a read adds to a passage reference, in a fixed order."""
        if self.status != "moved":
            return {"status": self.status}
        return {"status": self.status, "moved_to": self.moved_to, "match": self.match}


CURRENT = Successor("current")
STALE = Successor("stale")


def handle(key) -> str:
    """A passage key (book, content_id, profile_id, path, ordinal) as its citation handle."""
    book, content_id, profile_id, path, ordinal = key
    return f"{book}@{content_id}/{profile_id}/{path}#{ordinal}"


def _grams(text: str) -> Counter:
    words = _WORD.findall(text.casefold())
    return Counter(zip(words, words[1:])) if len(words) > 1 else Counter((w,) for w in words)


def _flat(text: str) -> str:
    return " ".join(_WORD.findall(text.casefold()))


def choose(text: str, ordinal: int, candidates: list[tuple[int, str]], *,
           same_content: bool = True) -> tuple[int | None, str]:
    """(successor ordinal or None, match) of an old passage among the passages of the same path in the target
    version ([(ordinal, text)]). Ties go to the ordinal nearest the old one, then the lower ordinal. Across a
    changed content version (`same_content` false), an overlap must hold the whole old text."""
    def near(o: int) -> tuple[int, int]:
        return abs(o - ordinal), o

    exact = [o for o, t in candidates if t == text]
    if exact:
        return min(exact, key=near), "exact"
    if not same_content:
        flat = _flat(text)
        candidates = [(o, t) for o, t in candidates if flat and f" {flat} " in f" {_flat(t)} "]
    old = _grams(text)
    total = sum(old.values())
    best = None
    for o, t in candidates:
        share = sum((old & _grams(t)).values()) / total if total else 0.0
        if share >= OVERLAP_MIN and (best is None or (-share, *near(o)) < best[0]):
            best = ((-share, *near(o)), o)
    return (best[1], "overlap") if best else (None, "none")


def _current(conn, books) -> dict:
    """{book: (content_id, profile_id)} of the books with a current version."""
    return {b: (c, p) for b, c, p in conn.execute(
        "SELECT slug, current_content, current_profile FROM book WHERE slug = ANY(%s) AND current_content IS NOT NULL",
        (sorted(set(books)),))}


def _stored(conn, keys, current: dict) -> dict:
    """{key: (to_ordinal, match)} of the stored rows from `keys` to the version in `current` (the version that the
    caller read, never the live book row: a publication between the two reads must not mix versions)."""
    rows = [(*k, *current[k[0]]) for k in keys if k[0] in current]
    if not rows:
        return {}
    cols = [list(c) for c in zip(*rows)]
    return {tuple(r[:5]): (r[5], r[6]) for r in conn.execute(
        "SELECT m.book, m.content_id, m.profile_id, m.path, m.ordinal, m.to_ordinal, m.match FROM passage_map m "
        "JOIN unnest(%s::text[], %s::text[], %s::text[], %s::text[], %s::int[], %s::text[], %s::text[]) "
        "  AS k(b, c, p, path, o, tc, tp) ON (m.book, m.content_id, m.profile_id, m.path, m.ordinal, "
        "  m.to_content_id, m.to_profile_id) = (k.b, k.c, k.p, k.path, k.o, k.tc, k.tp)", cols)}


def _compute(conn, keys, current: dict) -> dict:
    """{key: (to_ordinal, match)} computed from the chunk texts; nothing is written. A key whose passage does not
    exist maps to none."""
    if not keys:
        return {}
    cols = [list(c) for c in zip(*keys)]
    texts = {tuple(r[:5]): r[5] for r in conn.execute(
        "SELECT c.book, c.content_id, c.profile_id, c.path, c.ordinal, c.text FROM chunk c "
        "JOIN unnest(%s::text[], %s::text[], %s::text[], %s::text[], %s::int[]) AS k(b, ci, pi, p, o) "
        "  ON (c.book, c.content_id, c.profile_id, c.path, c.ordinal) = (k.b, k.ci, k.pi, k.p, k.o)", cols)}
    out, candidates = {}, {}
    for key in sorted(keys):
        book, old_content, _p, path, ordinal = key
        if (book, path) not in candidates:
            content_id, profile_id = current[book]
            candidates[(book, path)] = conn.execute(
                "SELECT ordinal, text FROM chunk WHERE book = %s AND content_id = %s AND profile_id = %s AND path = %s "
                "ORDER BY ordinal", (book, content_id, profile_id, path)).fetchall()
        same = old_content == current[book][0]
        out[key] = choose(texts[key], ordinal, candidates[(book, path)], same_content=same) if key in texts \
            else (None, "none")
    return out


def _old(keys, current: dict) -> list:
    """The keys of passages outside the current version of their book."""
    return sorted({k for k in keys if k[0] in current and (k[1], k[2]) != current[k[0]]})


def resolve(conn, keys) -> dict:
    """{key: Successor} for passage keys, from the stored map; a missing row is computed, not written."""
    keys = {tuple(k) for k in keys}
    current = _current(conn, {k[0] for k in keys})
    old = _old(keys, current)
    found = _stored(conn, old, current)
    found |= _compute(conn, [k for k in old if k not in found], current)
    out = {}
    for k in keys:
        if k[0] not in current:
            out[k] = STALE
        elif (k[1], k[2]) == current[k[0]]:
            out[k] = CURRENT
        else:
            to, match = found[k]
            out[k] = STALE if to is None else Successor("moved", handle((k[0], *current[k[0]], k[3], to)), match)
    return out


def successor_key(key, successor: Successor):
    """The key of the passage that a reference stands for now: itself when current, its successor when moved, else
    None."""
    if successor.status == "current":
        return tuple(key)
    if successor.status == "moved":
        book, rest = successor.moved_to.split("@", 1)
        head, ordinal = rest.rsplit("#", 1)
        content_id, profile_id, path = head.split("/", 2)
        return (book, content_id, profile_id, path, int(ordinal))
    return None


def _referenced(conn, book: str, path: str | None = None) -> set:
    """The passage keys of `book` (optionally one path) that a note cites or links to."""
    p = {"b": book, "p": path}
    return {tuple(r) for r in conn.execute(
        "SELECT cite_book, content_id, profile_id, path, ordinal FROM note_citation "
        " WHERE kind = 'passage' AND cite_book = %(b)s AND (%(p)s::text IS NULL OR path = %(p)s) "
        "UNION SELECT dst_book, dst_content_id, dst_profile_id, dst_path, dst_ordinal FROM note_link "
        " WHERE dst_book = %(b)s AND (%(p)s::text IS NULL OR dst_path = %(p)s)", p)}


def family(conn, key) -> list:
    """The passages that stand for the same passage now: `key`, its successor in the current version, and every
    referenced passage that maps to that successor. A stale passage is alone."""
    key = tuple(key)
    succ = successor_key(key, resolve(conn, [key])[key])
    if succ is None:
        return [key]
    book, content_id, profile_id, path, ordinal = succ
    preds = {tuple(r) for r in conn.execute(
        "SELECT book, content_id, profile_id, path, ordinal FROM passage_map WHERE book = %s AND to_content_id = %s "
        "AND to_profile_id = %s AND path = %s AND to_ordinal = %s", succ)}
    rest = _referenced(conn, book, path) - preds - {key, succ}
    preds |= {k for k, s in resolve(conn, rest).items() if successor_key(k, s) == succ}
    return sorted({key, succ} | preds)


def _write(conn, rows: dict, current: dict) -> None:
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO passage_map (book, content_id, profile_id, path, ordinal, to_content_id, to_profile_id, "
            "to_ordinal, match) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
            [(*k, *current[k[0]], to, match) for k, (to, match) in sorted(rows.items())])


def ensure(conn, keys) -> None:
    """A note write that references passages: map each one outside the current version of its book. The book rows
    are locked FOR SHARE, so a publication waits for this write (and maps it) or this write sees its version."""
    keys = {tuple(k) for k in keys}
    if not keys:
        return
    books = sorted({k[0] for k in keys})
    conn.execute("SELECT 1 FROM book WHERE slug = ANY(%s) ORDER BY slug FOR SHARE", (books,))
    current = _current(conn, books)
    old = _old(keys, current)
    stored = _stored(conn, old, current)
    _write(conn, _compute(conn, [k for k in old if k not in stored], current), current)


def map_book(conn, book: str, *, write: bool = True) -> dict:
    """Map every referenced passage of `book` outside its current version to that version (idempotent: a stored row
    stays). The counts over all those passages: {book, content_id, profile_id, passages, added (the rows that were
    not stored yet), exact, overlap, none}. `write=False` computes the same counts and writes nothing."""
    current = _current(conn, [book])
    if book not in current:
        raise ValueError(f"{book} has no published content version")
    old = _old(_referenced(conn, book), current)
    stored = _stored(conn, old, current)
    added = _compute(conn, [k for k in old if k not in stored], current)
    if write:
        _write(conn, added, current)
    counts = Counter(match for _to, match in (stored | added).values())
    content_id, profile_id = current[book]
    return {"book": book, "content_id": content_id, "profile_id": profile_id, "passages": len(old),
            "added": len(added), **{m: counts.get(m, 0) for m in MATCHES}}
