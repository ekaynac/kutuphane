"""Republished record text (G23, docs/18 §7): a passage that repeats a whole field value of a JSONL record points to
that record, and `ask` gives the record to the answer model before its copy.

- **The source rule:** the record is the source. A record (one JSONL line, one passage) has an id and a line (G15);
  a longer text that repeats one of its whole field values was assembled from it. Publication time does not decide:
  a book that bots re-publish every few hours (G17) would become "newer" than its own copies. A record is never a
  copy, so two records with the same value are not linked.
- **Identity is text, never a vector:** the sha256 of a string value (at any depth of the record) after white-space
  folding, at least MIN_CHARS characters; shorter values are labels (`event_type`, tags), not quotations. A passage
  repeats the value when the same digest comes from one of its units: a JSON string literal, a line, or a line
  without its markdown list, quote or heading mark. A value inside a longer line is not found.
- **Stored at publication** (`record_value`, migration 037; versions published before it are filled by the
  migration with the same folding in SQL). Looked up at read time against the current version of each book, so a
  re-published book never leaves a stale link.
- **Rights:** a pointer names only a record in a book that the caller may read now, and that passes the same scope
  filters as the evidence (book, path prefix, kstd origin, validity). Instruction passages are never sources. The
  passages and the records that they name are decided again in ONE final statement (`search.authorize`, Astra
  review #19): a book lost since the search drops its passages and every pointer into it, so no answer holds a
  passage and a record that were never readable at the same instant; the loss is logged, and each book whose records
  are named gets one `access_event` (action `quote`, items = the record handles). `ask` adds a source only when its
  rights allow AI input; its book is then a source book of the answer, decided again with the others before anything
  is handed out.
"""
import hashlib
import json
import re

from . import authz, gate, kstd, search
from .gate import Actor
from .source import JSONL, media_type_of

MIN_CHARS = 40
MAX_POINTERS = 10  # per passage, in (book, path, ordinal) order
_FOLD = re.compile(r"[ \t\n\r\f\v]+")  # the same class in SQL (037): [ \t\n\r\f\v]+
_JSON_STRING = re.compile(r'"(?:[^"\\\n]|\\.)*"')
_MARK = re.compile(r"^(?:[-*+>]|#{1,6}|\d{1,9}[.)])[ \t]+")


def folded(value: str) -> str:
    return _FOLD.sub(" ", value).strip(" ")


def digest(value: str) -> bytes:
    return hashlib.sha256(value.encode("utf-8")).digest()


def _strings(value, keys: bool = False):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for k, v in value.items():
            if keys:
                yield k
            yield from _strings(v, keys)
    elif isinstance(value, list):
        for v in value:
            yield from _strings(v, keys)


def _no_constant(name):
    raise ValueError(f"{name} is not JSON")


def record_values(text: str) -> set[bytes]:
    """The digests of the folded string values (MIN_CHARS or more) of one record passage; empty for a passage that
    is not exactly one JSON object (a cut record, the `whole` profile). Postgres jsonb refuses NaN/Infinity, NUL
    and lone surrogates anywhere in a record, so the migration backfill skips such a record; so does this."""
    try:
        record = json.loads(text, parse_constant=_no_constant)
        if not isinstance(record, dict):
            return set()
        for s in _strings(record, keys=True):
            if "\x00" in s:
                return set()
            s.encode("utf-8")
    except (ValueError, RecursionError, UnicodeEncodeError):
        return set()
    return {digest(v) for v in {folded(s) for s in _strings(record)} if len(v) >= MIN_CHARS}


def units(text: str) -> set[bytes]:
    """The digests of the units of any passage: its JSON string literals, its lines, and its lines without a
    markdown mark."""
    out = set()
    for m in _JSON_STRING.finditer(text):
        try:
            value = json.loads(m.group())
        except ValueError:
            continue
        out.add(folded(value))
    for line in text.splitlines():
        line = folded(line)
        out.update((line, _MARK.sub("", line)))
    found = set()
    for value in out:
        if len(value) >= MIN_CHARS:
            try:
                found.add(digest(value))
            except UnicodeEncodeError:
                continue
    return found


def is_record(path: str) -> bool:
    return media_type_of(path) == JSONL


def rows(book: str, content_id: str, profile_id: str, chunks) -> list[tuple]:
    """`record_value` rows of the new passages of one version (publication)."""
    return [(book, content_id, profile_id, c.path, c.ordinal, sha) for c in chunks if is_record(c.path)
            for sha in sorted(record_values(c.text))]


_SOURCES = """
SELECT DISTINCT r.sha256, c.book, c.content_id, c.profile_id, c.path, c.ordinal, c.page, c.start_char, c.end_char,
       c.text, c.line
  FROM record_value r
  JOIN book b ON b.slug = r.book AND b.current_content = r.content_id AND b.current_profile = r.profile_id
  JOIN chunk c USING (book, content_id, profile_id, path, ordinal)
 WHERE r.sha256 = ANY(%(shas)s) AND r.book = ANY(%(books)s) AND NOT c.instruction
   AND (%(prefix)s::text IS NULL OR starts_with(r.path, %(prefix)s))
 ORDER BY c.book, c.path, c.ordinal
"""


def quoted(conn, actor: Actor, hits: list[search.Hit], scope: search.Scope = search.Scope(), log: bool = True
           ) -> tuple[list[search.Hit], dict[search.Citation, list[search.Hit]]]:
    """(the hits, {citation of a passage: the record passages whose whole field values it repeats}), the map only
    for passages that repeat one; the records come from books that the caller may read now and that pass `scope`.
    When a record is named, the hits and the records are decided together once more (see the module text). `log`:
    the `quote` events of the named records; `ask` logs its sources at its own final gate instead."""
    copies = {h.citation: units(h.text) for h in hits if not is_record(h.citation.path)}
    shas = sorted(set().union(*copies.values())) if copies else []
    if not shas:
        return hits, {}
    read = {o.removeprefix("book:") for o in authz.allowed(conn, actor.principal, actor.on_behalf_of,
                                                           ["read"]).objects("read")}
    if scope.books:
        read &= set(scope.books)
    if not read:
        return hits, {}
    found = conn.execute(_SOURCES, {"shas": shas, "books": sorted(read), "prefix": scope.path}).fetchall()
    rights, records = kstd.Rights(conn), {}
    for r in found:
        hit = search.Hit(search.Citation(*r[1:6]), r[6], r[7], r[8], r[9], 0.0, r[10])
        if not scope.filters_files or scope.admits(rights.info(*r[1:3], r[4])):
            records.setdefault(bytes(r[0]), []).append(hit)
    pointers = {}
    for citation, mine in copies.items():
        seen = {}
        for sha in mine:
            for hit in records.get(sha, []):
                seen.setdefault(hit.citation, hit)
        if seen:
            pointers[citation] = sorted(seen.values(), key=lambda h: (h.citation.book, h.citation.path,
                                                                      h.citation.ordinal))[:MAX_POINTERS]
    if not pointers:
        return hits, {}
    named = list({r.citation: r for rs in pointers.values() for r in rs}.values())
    kept, final = search.authorize(conn, actor, hits + named)
    keep = {h.citation for h in kept}
    out = {c: [r for r in rs if r.citation in keep] for c, rs in pointers.items() if c in keep}
    out = {c: rs for c, rs in out.items() if rs}
    if log:
        _log(conn, actor, final, out)
    return [h for h in hits if h.citation in keep], out


def _log(conn, actor: Actor, final: authz.Allowed, out: dict) -> None:
    """One `access_event` per book whose records the result names (AT-09: what was handed out, under which decision)."""
    by_book = {}
    for rs in out.values():
        for r in rs:
            by_book.setdefault(r.citation.book, {}).setdefault(r.citation.handle, r.citation)
    for book in sorted(by_book):
        obj, first = f"book:{book}", by_book[book][min(by_book[book])]
        gate.log_event(conn, actor, "quote", obj, "read", final.decisions[obj]["read"], final.policies.get(obj),
                       first.content_id, None, profile_id=first.profile_id, items=sorted(by_book[book]))


def handles(found: dict, citation: search.Citation) -> list[str]:
    return [h.citation.handle for h in found.get(citation, [])]
