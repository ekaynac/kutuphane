"""Search and citations (M1d).

- Pre-filter: the query only ever sees books the caller may `read` now (and, for agents, instruction chunks only
  where `activate` is held), so ranks, counts and snippets cannot leak other books (AT-04).
- Before results are handed out, the whole result set is decided again in ONE statement (the request's
  linearization point). If rights changed in between, the search runs again with current rights (so revoked books
  never consume `k`); a second change refuses the request. Delivered chunks are logged by citation handle.
- A citation names book, content id, profile id, path and ordinal. Opening it serves the stored chunk of that exact
  version through the gate with the caller's *current* rights (AT-07, D36).

Ranking today is Postgres full text (`ts_rank_cd`). Vector search and the reranker join after LLMDAP #222 and the
M0 measurement (D31); they change the ranking, not this contract.
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
       c.instruction, ts_rank_cd(c.tsv, terms.q, %(norm)s) AS score
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


class SearchChanged(gate.Denied):
    """Rights changed while the search ran, twice in a row; the caller should retry."""


def _needs(actor: Actor, rows) -> dict:
    """Modes each book in the result needs: read, plus activate for agents receiving instruction chunks."""
    needs = {}
    for r in rows:
        needs.setdefault(f"book:{r[0]}", set()).update(gate.modes_for(actor, r[9]))
    return needs


def search(conn, actor: Actor, query: str, k: int = DEFAULT_K, attempts: int = 2) -> list[Hit]:
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
                                      "activate": sorted(activate), "k": k,
                                      "norm": RANK_NORMALIZATION}).fetchall()
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
