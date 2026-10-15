"""Finding passages (D31): the one entry point for HTTP, MCP, CLI and answers.

1. Query vector through the LLMDAP embeddings route (optional; full text alone without it).
2. Hybrid search: the pre-filtered, linearized `search.search` (FTS + vector, RRF).
3. Reranking through the LLMDAP rerank route (optional): the top RERANK_POOL hits are reordered and their
   scores become the reranker's relevance. If the reranker fails, the hybrid order stands; the failed call is
   on record in `model_call`. Reranking only reorders passages the search already authorized and logged (the
   pool is logged as read on the caller's behalf, since its text goes to the reranker).
"""
import dataclasses
import logging
from dataclasses import dataclass

from . import llmdap, search, vectors
from .gate import Actor

log = logging.getLogger(__name__)
RERANK_POOL = 30  # M0: bge-reranker-v2-m3 over the top 30 hybrid hits, R@1 0.34 -> 0.41


@dataclass(frozen=True)
class Stages:
    embedder: llmdap.Routed | None = None
    reranker: llmdap.Routed | None = None

    @classmethod
    def from_env(cls) -> "Stages":
        return cls(llmdap.Routed.from_env(llmdap.EMBED_ENV), llmdap.Routed.from_env(llmdap.RERANK_ENV))


def retrieve(conn, actor: Actor, query: str, k: int = search.DEFAULT_K, stages: Stages = Stages()) -> list[search.Hit]:
    vector = vectors.query_vector(conn, stages.embedder, actor, query)
    if stages.reranker is None:
        return search.search(conn, actor, query, k, vector=vector)
    pool = search.search(conn, actor, query, max(k, RERANK_POOL), vector=vector)
    if len(pool) < 2:
        return pool[:k]
    try:
        scores = llmdap.rerank(conn, stages.reranker, actor, query, [h.text for h in pool],
                               source_books=sorted({h.citation.book for h in pool}), purpose="rerank")
    except llmdap.EgressError as exc:
        log.warning("reranking failed, keeping the hybrid order: %s", exc)
        return pool[:k]
    order = sorted(range(len(pool)), key=lambda i: -scores[i])  # stable: ties keep the hybrid order
    return [dataclasses.replace(pool[i], score=scores[i]) for i in order[:k]]
