"""Search and citations (M1d).

- Pre-filter: the query only ever sees books the caller may `read` now (and, for agents, instruction chunks only
  where `activate` is held), so ranks, counts and snippets cannot leak other books (AT-04).
- Before results are handed out, every book in them is decided again in one statement and logged (`search`);
  a book revoked in between is dropped.
- A citation names book, content id, profile id, path and ordinal. Opening it serves the stored chunk of that exact
  version through the gate with the caller's *current* rights (AT-07, D36).

Ranking today is Postgres full text (`ts_rank_cd`). Vector search and the reranker join after LLMDAP #222 and the
M0 measurement (D31); they change the ranking, not this contract.
"""
from dataclasses import dataclass

from . import authz, gate, profiles
from .gate import Actor, NotFound

DEFAULT_K = 8
MAX_K = 50
MAX_QUERY_CHARS = 1000


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


_SEARCH = """
SELECT c.book, c.content_id, c.profile_id, c.path, c.ordinal, c.page, c.start_char, c.end_char, c.text,
       c.instruction, ts_rank_cd(c.tsv, terms.q) AS score
  FROM chunk c
  JOIN book b ON b.slug = c.book AND b.current_content = c.content_id AND b.current_profile = c.profile_id
 CROSS JOIN (  -- any stemmed query word may match; ts_rank_cd rewards matching more of them, closer together
       SELECT to_tsquery('simple', string_agg(quote_literal(l), ' | ')) AS q
         FROM unnest(tsvector_to_array(to_tsvector(%(cfg)s::regconfig, %(q)s))) AS l) AS terms
 WHERE ('book:' || c.book) = ANY(%(read)s) AND c.tsv @@ terms.q
   AND (NOT c.instruction OR ('book:' || c.book) = ANY(%(activate)s))
 ORDER BY score DESC, c.book, c.path, c.ordinal
 LIMIT %(k)s
"""


def search(conn, actor: Actor, query: str, k: int = DEFAULT_K) -> list[Hit]:
    if not isinstance(query, str) or not query.strip() or len(query) > MAX_QUERY_CHARS:
        raise ValueError(f"query must be 1..{MAX_QUERY_CHARS} characters")
    if not 1 <= k <= MAX_K:
        raise ValueError(f"k must be 1..{MAX_K}")
    read = authz.allowed_objects(conn, actor.principal, actor.on_behalf_of, "read")
    if not read:
        return []
    agent = actor.principal.startswith("agent:")
    activate = authz.allowed_objects(conn, actor.principal, actor.on_behalf_of, "activate") if agent else read
    rows = conn.execute(_SEARCH, {"cfg": profiles.FTS_CONFIG, "q": query, "read": sorted(read),
                                  "activate": sorted(activate), "k": k}).fetchall()

    by_book: dict[str, list] = {}
    for row in rows:
        by_book.setdefault(row[0], []).append(row)
    kept = set()
    for book, book_rows in by_book.items():
        modes = gate.modes_for(actor, any(r[9] for r in book_rows))
        try:
            gate.guard(conn, actor, f"book:{book}", modes, lambda: None, action="search", content_id=book_rows[0][1])
            kept.add(book)
        except gate.Denied:
            pass  # revoked between pre-filter and delivery; guard logged it
    return [Hit(Citation(*r[:5]), r[5], r[6], r[7], r[8], float(r[10])) for r in rows if r[0] in kept]


def open_citation(conn, actor: Actor, citation: Citation) -> Hit:
    """The stored passage of exactly that version and profile; rights are checked as of now."""
    row = conn.execute("SELECT page, start_char, end_char, text, instruction FROM chunk WHERE book = %s AND "
                       "content_id = %s AND profile_id = %s AND path = %s AND ordinal = %s",
                       (citation.book, citation.content_id, citation.profile_id, citation.path,
                        citation.ordinal)).fetchone()
    modes = gate.modes_for(actor, bool(row and row[4]))

    def fetch():
        if row is None:
            raise NotFound(citation.handle)
        return Hit(citation, row[0], row[1], row[2], row[3], 0.0)
    return gate.guard(conn, actor, f"book:{citation.book}", modes, fetch, action="cite",
                      content_id=citation.content_id, path=citation.path)
