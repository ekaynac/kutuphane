"""Search and citations (M1d).

- Pre-filter: the query only ever sees books the caller may `read` now (and, for agents, instruction chunks only
  where `activate` is held), so ranks, counts and snippets cannot leak other books (AT-04).
- Before results are handed out, the whole result set is decided again in ONE statement (the request's
  linearization point). If rights changed in between, the search runs again with current rights (so revoked books
  never consume `k`); a second change refuses the request. Delivered chunks are logged by citation handle.
- A citation names book, content id, profile id, path and ordinal. Opening it serves the stored chunk of that exact
  version through the gate with the caller's *current* rights (AT-07, D36).

Ranking is hybrid (D31, M0 measurement in experiments/retrieval): Postgres full text (`ts_rank_cd`) and, when the
caller brings a query vector (embedded through LLMDAP), exact cosine distance over the same pre-filtered chunks,
fused by reciprocal rank (RRF). Without a vector the order is full text alone. One statement either way.
"""
from dataclasses import dataclass

from . import authz, gate, profiles
from .gate import Actor, NotFound

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


# The pre-filter, written once and used by both rankings: current version and profile of books readable now;
# instruction chunks only where `activate` is held too (agents).
_ALLOWED = """
  JOIN book b ON b.slug = c.book AND b.current_content = c.content_id AND b.current_profile = c.profile_id
 WHERE ('book:' || c.book) = ANY(%(read)s) AND (NOT c.instruction OR ('book:' || c.book) = ANY(%(activate)s))"""

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
       c.instruction, f.score
  FROM fused f JOIN chunk c USING (book, content_id, profile_id, path, ordinal)
 ORDER BY f.score DESC, c.book, c.path, c.ordinal
 LIMIT %(k)s
"""


@dataclass(frozen=True)
class QueryVector:
    """The query embedded through LLMDAP by `model`; compared only with chunk vectors of the same model."""
    model: str
    values: list[float]

    def literal(self) -> str:
        return "[" + ",".join(repr(float(x)) for x in self.values) + "]"


class SearchChanged(gate.Denied):
    """Rights changed while the search ran, twice in a row; the caller should retry."""


def _needs(actor: Actor, rows) -> dict:
    """Modes each book in the result needs: read, plus activate for agents receiving instruction chunks."""
    needs = {}
    for r in rows:
        needs.setdefault(f"book:{r[0]}", set()).update(gate.modes_for(actor, r[9]))
    return needs


def search(conn, actor: Actor, query: str, k: int = DEFAULT_K, attempts: int = 2,
           vector: QueryVector | None = None) -> list[Hit]:
    if not isinstance(query, str) or not query.strip() or len(query) > MAX_QUERY_CHARS:
        raise ValueError(f"query must be 1..{MAX_QUERY_CHARS} characters")
    if not 1 <= k <= MAX_K:
        raise ValueError(f"k must be 1..{MAX_K}")
    agent = actor.principal.startswith("agent:")
    modes = ["read", "activate"] if agent else ["read"]
    for _ in range(attempts):
        pre = authz.allowed(conn, actor.principal, actor.on_behalf_of, modes)
        read = pre.objects("read")
        if not read:
            return []
        activate = pre.objects("activate") if agent else read
        rows = conn.execute(_SEARCH, {"cfg": profiles.FTS_CONFIG, "q": query, "read": sorted(read),
                                      "activate": sorted(activate), "k": k, "norm": RANK_NORMALIZATION,
                                      "pool": max(POOL, k), "rrf": RRF_K,
                                      "qv": vector.literal() if vector else None,
                                      "model": vector.model if vector else None}).fetchall()
        needs = _needs(actor, rows)
        # One final statement for the whole result set: the request's single linearization point.
        final = authz.allowed(conn, actor.principal, actor.on_behalf_of, modes)
        lost = {o for o, ms in needs.items() if not ms <= set(final.decisions.get(o, {}))}
        if lost:
            for obj in sorted(lost):
                gate.log_event(conn, actor, "search", obj, "read", authz.Decision(False, "changed during search"),
                               final.policies.get(obj), None, None)
            continue  # search again with the rights as they are now, so revoked books never consume `k`
        hits = [Hit(Citation(*r[:5]), r[5], r[6], r[7], r[8], float(r[10])) for r in rows]
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
                      content_id=citation.content_id, path=citation.path, profile_id=citation.profile_id,
                      items=[citation.handle])
