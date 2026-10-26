"""Chunk embeddings for hybrid search (D16, D31). Vectors are made only through LLMDAP (D17, #222).

Indexing embeds the chunks of a book's current version that have no vector for the configured model yet; book
content goes to the embeddings route under the same egress policy as any model call (a local_only book never goes
to a cloud route). A query is embedded per search; if that fails, the search still answers with full text alone and
the failed call stays on record in `model_call`.
"""
import logging

from . import kstd, llmdap, search
from .gate import Actor

log = logging.getLogger(__name__)
BATCH = 32
BATCH_CHARS = 24_000  # long passages (JSON, HTML) make a 32-passage batch outlast the gateway timeout on CPU
EMBED_CHARS = BATCH_CHARS  # a longer passage is embedded by this prefix only (Astra #11); its text stays whole
INDEXER = "service:indexer"  # the principal recorded for indexing calls (an operation, not a person's request)

_MISSING = """
SELECT c.book, c.content_id, c.profile_id, c.path, c.ordinal, c.text
  FROM chunk c
  JOIN book b ON b.slug = c.book AND b.current_content = c.content_id AND b.current_profile = c.profile_id
 WHERE c.book = %s AND NOT EXISTS (
       SELECT 1 FROM chunk_vector v
        WHERE (v.book, v.content_id, v.profile_id, v.path, v.ordinal) = (c.book, c.content_id, c.profile_id, c.path,
                                                                         c.ordinal) AND v.model = %s)
 ORDER BY c.path, c.ordinal
"""


def stored_dims(conn, model: str) -> int | None:
    row = conn.execute("SELECT vector_dims(embedding) FROM chunk_vector WHERE model = %s LIMIT 1", (model,)).fetchone()
    return row[0] if row else None


def index(conn, embedder: llmdap.Routed, book: str) -> int:
    """Embed the book's current chunks that lack a vector of this model; returns how many vectors were added.
    All vectors of one model have one width: a model that changed its output needs a new model name.
    A passage whose kstd rights do not allow `ai_input` is never sent to the embedder (full text still finds it).
    A passage longer than EMBED_CHARS is embedded by its first EMBED_CHARS characters and its vector is marked
    `truncated`; the stored chunk text, and so full text search, keep the whole passage."""
    rights = kstd.Rights(conn)
    rows = [r for r in conn.execute(_MISSING, (book, embedder.model)).fetchall()
            if rights.allows(r[0], r[1], r[3], "ai_input")]
    actor = Actor(INDEXER)
    dims = stored_dims(conn, embedder.model)
    for batch in _batches(rows):
        vectors = llmdap.embed(conn, embedder, actor, [r[5][:EMBED_CHARS] for r in batch], source_books=[book],
                               purpose="index")
        dims = dims or len(vectors[0])
        if len(vectors[0]) != dims:
            raise llmdap.EgressError(f"{embedder.model} returned {len(vectors[0])} dimensions; stored are {dims}")
        with conn.cursor() as cur:
            cur.executemany("INSERT INTO chunk_vector (book, content_id, profile_id, path, ordinal, model, embedding, "
                            "truncated) VALUES (%s, %s, %s, %s, %s, %s, %s::vector, %s) ON CONFLICT DO NOTHING",
                            [(*r[:5], embedder.model, search.QueryVector(embedder.model, v).literal(),
                              len(r[5]) > EMBED_CHARS) for r, v in zip(batch, vectors)])
    return len(rows)


def _batches(rows: list) -> list[list]:
    """At most BATCH passages and at most BATCH_CHARS embedded characters per embedding call; a passage counts by the
    prefix that is sent (EMBED_CHARS), so no call carries more than the budget."""
    out, size = [], 0
    for r in rows:
        n = min(len(r[5]), EMBED_CHARS)
        if not out or len(out[-1]) == BATCH or size + n > BATCH_CHARS:
            out.append([])
            size = 0
        out[-1].append(r)
        size += n
    return out


def query_vector(conn, embedder: llmdap.Routed | None, actor: Actor, query: str) -> search.QueryVector | None:
    if embedder is None:
        return None
    try:
        (values,) = llmdap.embed(conn, embedder, actor, [query], source_books=[], purpose="search")
    except llmdap.EgressError as exc:
        log.warning("query embedding failed, searching full text only: %s", exc)
        return None
    if len(values) != stored_dims(conn, embedder.model):  # also when nothing is indexed for this model yet
        log.warning("query vector does not fit the stored %s vectors, searching full text only", embedder.model)
        return None
    return search.QueryVector(embedder.model, values)
