"""Chunk embeddings for hybrid search (D16, D31). Vectors are made only through LLMDAP (D17, #222).

Indexing embeds the chunks of a book's current version that have no vector for the configured model yet; book
content goes to the embeddings route under the same egress policy as any model call (a local_only book never goes
to a cloud route). A query is embedded per search; if that fails, the search still answers with full text alone and
the failed call stays on record in `model_call`.
"""
import logging

from . import llmdap, search
from .gate import Actor

log = logging.getLogger(__name__)
BATCH = 32
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
    All vectors of one model have one width: a model that changed its output needs a new model name."""
    rows = conn.execute(_MISSING, (book, embedder.model)).fetchall()
    actor = Actor(INDEXER)
    dims = stored_dims(conn, embedder.model)
    for start in range(0, len(rows), BATCH):
        batch = rows[start:start + BATCH]
        vectors = llmdap.embed(conn, embedder, actor, [r[5] for r in batch], source_books=[book], purpose="index")
        dims = dims or len(vectors[0])
        if len(vectors[0]) != dims:
            raise llmdap.EgressError(f"{embedder.model} returned {len(vectors[0])} dimensions; stored are {dims}")
        with conn.cursor() as cur:
            cur.executemany("INSERT INTO chunk_vector (book, content_id, profile_id, path, ordinal, model, embedding) "
                            "VALUES (%s, %s, %s, %s, %s, %s, %s::vector) ON CONFLICT DO NOTHING",
                            [(*r[:5], embedder.model, search.QueryVector(embedder.model, v).literal())
                             for r, v in zip(batch, vectors)])
    return len(rows)


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
