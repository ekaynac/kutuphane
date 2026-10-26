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

from . import kstd, llmdap, search, vectors
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


def retrieve(conn, actor: Actor, query: str, k: int = search.DEFAULT_K, stages: Stages = Stages(),
             scope: search.Scope = search.Scope()) -> list[search.Hit]:
    vector = vectors.query_vector(conn, stages.embedder, actor, query)
    if stages.reranker is None:
        return search.search(conn, actor, query, k, vector=vector, scope=scope)
    pool = search.search(conn, actor, query, max(k, RERANK_POOL), vector=vector, scope=scope)
    rights = kstd.Rights(conn)
    slots = [i for i, h in enumerate(pool)  # kstd: only passages whose rights allow ai_input go to the reranker
             if rights.allows(h.citation.book, h.citation.content_id, h.citation.path, "ai_input")]
    if len(slots) < 2:
        return pool[:k]
    try:
        scores = llmdap.rerank(conn, stages.reranker, actor, query, [pool[i].text for i in slots],
                               source_books=sorted({pool[i].citation.book for i in slots}), purpose="rerank")
    except llmdap.EgressError as exc:
        log.warning("reranking failed, keeping the hybrid order: %s", exc)
        return pool[:k]
    order = sorted(range(len(slots)), key=lambda j: -scores[j])  # stable: ties keep the hybrid order
    out = list(pool)  # passages that were not reranked keep their hybrid position
    for slot, j in zip(slots, order):
        out[slot] = dataclasses.replace(pool[slots[j]], score=scores[j])
    return out[:k]
