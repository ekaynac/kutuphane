"""Search and citations (M1d).

- Pre-filter: the query only ever sees books the caller may `read` now (and, for agents, instruction chunks only
  where `activate` is held and the skill is not blocked by a scan, D71), so ranks, counts and snippets cannot leak
  other books (AT-04).
- Optional scope filters (book, path prefix, kstd origin, valid now, request context; G14, #137) narrow that
  pre-filter in the same statement, before ranking. They never add a book.
- Before results are handed out, the whole result set is decided again in ONE statement (the request's
  linearization point). If rights changed in between, the search runs again with current rights (so revoked books
  never consume `k`); a second change refuses the request. Delivered chunks are logged by citation handle.
- A citation names book, content id, profile id, path and ordinal. Opening it serves the stored chunk of that exact
  version through the gate with the caller's *current* rights (AT-07, D36).

Ranking is hybrid (D31, M0 measurement in experiments/retrieval): Postgres full text (`ts_rank_cd`) and, when the
caller brings a query vector (embedded through LLMDAP), exact cosine distance over the same pre-filtered chunks,
fused by reciprocal rank (RRF). Without a vector the order is full text alone. One statement either way.
"""
import re
from dataclasses import dataclass

from . import authz, gate, ids, kstd, profiles
from .gate import Actor, NotFound
from .ids import normalize_path

DEFAULT_K = 8
# ts_rank_cd normalization 4 (divide by mean harmonic distance between extents). M0 baseline on hand-checked
# Turkish legal QA (experiments/retrieval): recall@10 0.245 -> 0.563, MRR 0.09 -> 0.29 vs. no normalization.
RANK_NORMALIZATION = 4
MAX_K = 50
MAX_QUERY_CHARS = 1000
POOL = 50      # candidates per ranking before fusion
RRF_K = 60     # reciprocal rank fusion constant (M0: hybrid R@10 0.56 -> 0.71 on the legal QA set)


@dataclass(frozen=True)
class Citation:
    book: str
    content_id: str
    profile_id: str
    path: str
    ordinal: int

    @property
    def handle(self) -> str:
        return f"{self.book}@{self.content_id}/{self.profile_id}/{self.path}#{self.ordinal}"


@dataclass(frozen=True)
class Hit:
    citation: Citation
    page: int | None
    start: int
    end: int
    text: str
    score: float
    line: int | None = None  # text files: the line the passage starts on (JSONL: the record's line)
    instruction: bool = False  # an instruction chunk: agents need `activate` for it too


# The pre-filter, written once and used by both rankings: current version and profile of books readable now;
# instruction chunks only where `activate` is held too (agents), and, for agents, never inside a skill that a scan
# blocks (D71). The scope filters (G14) only narrow it further.
_ALLOWED = """
  JOIN book b ON b.slug = c.book AND b.current_content = c.content_id AND b.current_profile = c.profile_id
 WHERE ('book:' || c.book) = ANY(%(read)s) AND (NOT c.instruction OR ('book:' || c.book) = ANY(%(activate)s))
   AND NOT (%(agent)s AND c.instruction AND skill_blocked(c.book, c.content_id, c.path))
   AND (%(prefix)s::text IS NULL OR starts_with(c.path, %(prefix)s))
   AND (%(files)s::text[] IS NULL OR (c.book || '/' || c.content_id || '/' || c.path) = ANY(%(files)s::text[]))"""

_SEARCH = f"""
WITH terms AS (  -- any stemmed query word may match; ts_rank_cd rewards matching more of them, closer together
    SELECT to_tsquery('simple', string_agg(quote_literal(l), ' | ')) AS q
      FROM unnest(tsvector_to_array(to_tsvector(%(cfg)s::regconfig, %(q)s))) AS l),
lexical AS (
    SELECT c.book, c.content_id, c.profile_id, c.path, c.ordinal,
           row_number() OVER (ORDER BY ts_rank_cd(c.tsv, terms.q, %(norm)s) DESC, c.book, c.path, c.ordinal) AS r
      FROM chunk c CROSS JOIN terms {_ALLOWED} AND c.tsv @@ terms.q
     ORDER BY r LIMIT %(pool)s),
semantic AS (
    SELECT c.book, c.content_id, c.profile_id, c.path, c.ordinal,
           row_number() OVER (ORDER BY v.embedding <=> %(qv)s::vector, c.book, c.path, c.ordinal) AS r
      FROM chunk c
      JOIN chunk_vector v USING (book, content_id, profile_id, path, ordinal) {_ALLOWED}
       AND %(qv)s::vector IS NOT NULL AND v.model = %(model)s
     ORDER BY r LIMIT %(pool)s),
fused AS (
    SELECT book, content_id, profile_id, path, ordinal, sum(1.0 / (%(rrf)s + r)) AS score
      FROM (SELECT * FROM lexical UNION ALL SELECT * FROM semantic) AS ranked
     GROUP BY book, content_id, profile_id, path, ordinal)
SELECT c.book, c.content_id, c.profile_id, c.path, c.ordinal, c.page, c.start_char, c.end_char, c.text,
       c.instruction, f.score, c.line
  FROM fused f JOIN chunk c USING (book, content_id, profile_id, path, ordinal)
 ORDER BY f.score DESC, c.book, c.path, c.ordinal
 LIMIT %(k)s
"""


MAX_SCOPE_BOOKS = 50
_SLUG = re.compile(rf"^{ids.SLUG}\Z")


@dataclass(frozen=True)
class Scope:
    """Optional evidence filters (G14). They are applied inside the pre-filter, in the ranking statement, so they
    narrow the passages before ranking and `k`. They never widen it: a book the caller may not read stays out
    whatever the filter names, and naming such a book gives the same empty result as naming one that does not
    exist. Origin, validity and `applies_to` come from the kstd item information of the book's current version; a
    book without kstd.yaml has none, so it counts as origin `unknown` (docs/11 §5), as current (no validity
    stated) and as unbounded.

    `platform` and `version` are the request context (docs/09 §2, Scope): an unbounded item always matches; an
    item whose `applies_to` the context contradicts is left out; a bound that the context does not give keeps the
    item, shown with `scope: needs_context`."""
    books: tuple[str, ...] = ()      # only these books
    path: str | None = None          # only files whose path starts with this text ("data/" = below data/)
    origins: tuple[str, ...] = ()    # only files with one of these kstd origins
    current_only: bool = False       # only files whose kstd validity includes now
    platform: str | None = None      # the request context: the caller's platform
    version: str | None = None       # the request context: the caller's version (e.g. "7.0.3")

    @classmethod
    def of(cls, books=None, path=None, origins=None, current_only=False, context=None) -> "Scope":
        """A checked scope from request values; raises ValueError for a malformed value."""
        books, origins = _strings("book", books), _strings("origin", origins)
        if len(books) > MAX_SCOPE_BOOKS or not all(_SLUG.match(b) for b in books):
            raise ValueError(f"book must be up to {MAX_SCOPE_BOOKS} book slugs")
        if any(o not in kstd.ORIGINS for o in origins):
            raise ValueError(f"origin must be one of {', '.join(kstd.ORIGINS)}")
        if path is not None:
            if not isinstance(path, str) or not path.strip("/") or len(path) > MAX_QUERY_CHARS:
                raise ValueError("path must be a relative path prefix")
            path = normalize_path(path.rstrip("/")) + ("/" if path.endswith("/") else "")
        if not isinstance(current_only, bool):
            raise ValueError("current_only must be true or false")
        platform, version = _context(context)
        return cls(tuple(sorted(set(books))), path, tuple(sorted(set(origins))), current_only, platform, version)

    @property
    def context(self) -> tuple[str | None, str | None]:
        return self.platform, self.version

    @property
    def filters_files(self) -> bool:
        """Whether a filter reads the kstd item information (origin, validity, context)."""
        return bool(self.origins) or self.current_only or self.context != (None, None)

    def admits(self, info: dict | None) -> bool:
        """Whether a file with this kstd item information (None: no manifest) passes the origin, time and context
        filters."""
        if self.origins and (info["origin"] if info else "unknown") not in self.origins:
            return False
        if info and kstd.scope_verdict(info["applies_to"], *self.context) == "mismatch":
            return False
        return not self.current_only or info is None or kstd.is_current(info)


def _context(context) -> tuple[str | None, str | None]:
    """(platform, version) of a request context {platform, version}; both optional."""
    if context is None:
        return None, None
    if not isinstance(context, dict) or set(context) - set(kstd.APPLIES_KEYS):
        raise ValueError(f"context must be a mapping with only {', '.join(kstd.APPLIES_KEYS)}")
    platform, version = context.get("platform"), context.get("version")
    if platform is not None and not (isinstance(platform, str) and platform.strip() and len(platform) <= 200
                                     and platform.isprintable()):
        raise ValueError("context platform must be a non-empty string")
    if version is not None and not (isinstance(version, str) and len(version) <= 100 and kstd.VERSION.match(version)):
        raise ValueError("context version must be a version such as 7.0.3")
    return platform, version


def _strings(name: str, value) -> list[str]:
    value = [] if value is None else [value] if isinstance(value, str) else value
    if not isinstance(value, (list, tuple)) or not all(isinstance(v, str) and v for v in value):
        raise ValueError(f"{name} must be one or more names")
    return list(value)


def _scope_files(conn, scope: Scope, books: list[str]) -> list[str] | None:
    """`book/content_id/path` of the current files that pass the origin and time filters (None: no such filter).
    Keyed by content id, so a version published meanwhile matches nothing here: the filter fails closed."""
    if not scope.filters_files:
        return None
    rights, out = kstd.Rights(conn), []
    rows = conn.execute("SELECT b.slug, v.id, v.manifest FROM book b JOIN content_version v ON v.book = b.slug AND "
                        "v.id = b.current_content WHERE b.slug = ANY(%s)", (books,)).fetchall()
    for book, content_id, manifest in rows:
        out += [f"{book}/{content_id}/{f['path']}" for f in manifest
                if scope.admits(rights.info(book, content_id, f["path"]))]
    return out


def _refuse_journals(conn, read: set[str], scope: Scope) -> None:
    """G33: notes are not passages, so a journal in the book filter would give a silent empty list. A readable
    journal named there is refused with a notice; one the caller may not read stays as a book that does not exist."""
    named = [b for b in scope.books if f"book:{b}" in read]
    journals = [r[0] for r in conn.execute("SELECT book FROM journal WHERE book = ANY(%s) ORDER BY book", (named,))
                ] if named else []
    if journals:
        raise ValueError(f"journal: use query_notes for {', '.join(journals)}; notes are not in search_library or "
                         "ask_library")


def check_scope(conn, actor: Actor, scope: Scope) -> None:
    """The journal notice before any model call (retrieval: the query embedding, the translation)."""
    if scope.books:
        _refuse_journals(conn, authz.allowed(conn, actor.principal, actor.on_behalf_of, _modes(actor)).objects("read"),
                         scope)


@dataclass(frozen=True)
class QueryVector:
    """The query embedded through LLMDAP by `model`; compared only with chunk vectors of the same model."""
    model: str
    values: list[float]

    def literal(self) -> str:
        return "[" + ",".join(repr(float(x)) for x in self.values) + "]"


class SearchChanged(gate.Denied):
    """Rights changed while the search ran, twice in a row; the caller should retry."""


def _needs(actor: Actor, passages) -> dict:
    """Modes each book needs for these (book, instruction) passages: read, plus activate for agents receiving
    instruction chunks."""
    needs = {}
    for book, instruction in passages:
        needs.setdefault(f"book:{book}", set()).update(gate.modes_for(actor, instruction))
    return needs


def _modes(actor: Actor) -> list[str]:
    return ["read", "activate"] if actor.principal.startswith("agent:") else ["read"]


def _lost(conn, actor: Actor, needs: dict, final: authz.Allowed) -> set[str]:
    """The books in `needs` that lack a needed mode in `final`; each loss is logged."""
    lost = {o for o, ms in needs.items() if not ms <= set(final.decisions.get(o, {}))}
    for obj in sorted(lost):
        gate.log_event(conn, actor, "search", obj, "read", authz.Decision(False, "changed during search"),
                       final.policies.get(obj), None, None)
    return lost


def check_query(query) -> None:
    """The query limits, checked before anything else uses the query: embedding, the query cache, the search."""
    if not isinstance(query, str) or not query.strip() or len(query) > MAX_QUERY_CHARS:
        raise ValueError(f"query must be 1..{MAX_QUERY_CHARS} characters")


def authorize(conn, actor: Actor, hits: list[Hit]) -> tuple[list[Hit], authz.Allowed | None]:
    """The hits the caller may receive now, decided in ONE statement for the whole list, and that final decision
    (None for no hits). A pool merged from two searches (retrieval, G19), or hits with the records they repeat
    (quotes.py), has no common linearization point otherwise: rights may change between the reads (Astra reviews
    #12, #19). A passage of a book that lost a needed mode is dropped; the loss is logged. An agent's instruction
    passage inside a skill that a scan blocked meanwhile (D71) is dropped too."""
    needs = _needs(actor, ((h.citation.book, h.instruction) for h in hits))
    if not needs:
        return [], None
    final = authz.allowed(conn, actor.principal, actor.on_behalf_of, _modes(actor), skills=_skills(
        actor, ((h.citation.book, h.citation.content_id, h.citation.path, h.instruction) for h in hits)))
    lost = _lost(conn, actor, needs, final)
    return [h for h in hits if f"book:{h.citation.book}" not in lost
            and (h.citation.book, h.citation.content_id, h.citation.path) not in final.blocked_files], final


def _skills(actor: Actor, passages) -> list[tuple[str, str, str]]:
    """(book, content_id, path) of an agent's instruction passages: the final statement reads their skill blocks
    (D71) together with the rights (Astra review #15)."""
    if not actor.principal.startswith("agent:"):
        return []
    return sorted({(b, c, p) for b, c, p, instruction in passages if instruction})


def search(conn, actor: Actor, query: str, k: int = DEFAULT_K, attempts: int = 2,
           vector: QueryVector | None = None, scope: Scope = Scope()) -> list[Hit]:
    check_query(query)
    if not 1 <= k <= MAX_K:
        raise ValueError(f"k must be 1..{MAX_K}")
    agent = actor.principal.startswith("agent:")
    modes = _modes(actor)
    for _ in range(attempts):
        pre = authz.allowed(conn, actor.principal, actor.on_behalf_of, modes)
        read = pre.objects("read")
        _refuse_journals(conn, read, scope)
        if scope.books:  # an intersection: the filter can only remove readable books
            read = read & {f"book:{b}" for b in scope.books}
        if not read:
            return []
        activate = pre.objects("activate") if agent else read
        files = _scope_files(conn, scope, sorted(o.removeprefix("book:") for o in read))
        rows = conn.execute(_SEARCH, {"cfg": profiles.FTS_CONFIG, "q": query, "read": sorted(read),
                                      "activate": sorted(activate), "agent": agent, "k": k,
                                      "norm": RANK_NORMALIZATION,
                                      "pool": max(POOL, k), "rrf": RRF_K,
                                      "qv": vector.literal() if vector else None,
                                      "model": vector.model if vector else None,
                                      "prefix": scope.path, "files": files}).fetchall()
        needs = _needs(actor, ((r[0], r[9]) for r in rows))
        # One final statement for the whole result set, rights and skill blocks: the single linearization point.
        final = authz.allowed(conn, actor.principal, actor.on_behalf_of, modes,
                              skills=_skills(actor, ((r[0], r[1], r[3], r[9]) for r in rows)))
        if _lost(conn, actor, needs, final):
            continue  # search again with the rights as they are now, so revoked books never consume `k`
        if final.blocked_files:
            continue  # a scan blocked a skill meanwhile (D71): the next pre-filter leaves it out
        hits = [Hit(Citation(*r[:5]), r[5], r[6], r[7], r[8], float(r[10]), r[11], r[9]) for r in rows]
        for obj, ms in needs.items():
            book = obj.removeprefix("book:")
            mine = [h for h in hits if h.citation.book == book]
            for mode in sorted(ms, key=modes.index):
                gate.log_event(conn, actor, "search" if mode == "read" else mode, obj, mode, final.decisions[obj][mode],
                               final.policies.get(obj), mine[0].citation.content_id, None,
                               profile_id=mine[0].citation.profile_id, items=[h.citation.handle for h in mine])
        return hits
    raise SearchChanged("authorization changed during search; retry")


def open_citation(conn, actor: Actor, citation: Citation) -> Hit:
    """The stored passage of exactly that version and profile; rights are checked as of now."""
    row = conn.execute("SELECT page, start_char, end_char, text, instruction, line FROM chunk WHERE book = %s AND "
                       "content_id = %s AND profile_id = %s AND path = %s AND ordinal = %s",
                       (citation.book, citation.content_id, citation.profile_id, citation.path,
                        citation.ordinal)).fetchone()
    modes = gate.modes_for(actor, bool(row and row[4]))

    def fetch():
        if row is None:
            raise NotFound(citation.handle)
        return Hit(citation, row[0], row[1], row[2], row[3], 0.0, row[5], bool(row[4]))
    return gate.guard(conn, actor, f"book:{citation.book}", modes, fetch, action="cite",
                      content_id=citation.content_id, path=citation.path, profile_id=citation.profile_id,
                      items=[citation.handle])
