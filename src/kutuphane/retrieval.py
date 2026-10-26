"""Finding passages (D31): the one entry point for HTTP, MCP, CLI and answers.

1. Query vector through the LLMDAP embeddings route (optional; full text alone without it). Vectors of recent
   queries are kept in memory (QUERY_CACHE entries per process), so a repeated query costs no embedding call.
2. Hybrid search: the pre-filtered, linearized `search.search` (FTS + vector, RRF).
3. Reranking through the LLMDAP rerank route (optional): the top RERANK_POOL hits are reordered and their
   scores become the reranker's relevance. The reranker reads the first RERANK_CHARS characters of each passage
   (G26); the passage itself stays whole. If the reranker fails, the hybrid order stands; the failed call is
   on record in `model_call`. Reranking only reorders passages the search already authorized and logged (the
   pool is logged as read on the caller's behalf, since its text goes to the reranker). Passages in the other
   language (Turkish/English) that the hybrid search ranked in its top k keep up to LANGUAGE_RESERVE places (G19).
"""
import dataclasses
import logging
import re
import threading
from collections import OrderedDict
from dataclasses import dataclass

from . import kstd, llmdap, profiles, search, vectors
from .gate import Actor

log = logging.getLogger(__name__)
RERANK_POOL = 30  # M0: bge-reranker-v2-m3 over the top 30 hybrid hits, R@1 0.34 -> 0.41
# G26: the reranker (CPU) reads a passage of the target chunk size whole; only oversize JSON/HTML blocks are cut.
# Pilot radar, 7 questions: 36–58 % fewer characters to rerank; the top 8 kept the evidence passages (docs/18 §4).
RERANK_CHARS = profiles.TARGET_CHARS
QUERY_CACHE = 256
# G19: bge-reranker-v2-m3 scores a passage in the other language near zero even when it answers the question (pilot
# radar, question 2: hybrid rank 7 -> rerank rank 10). So up to LANGUAGE_RESERVE passages of the other language that
# the hybrid search put in its top k keep a place in the top k after reranking.
LANGUAGE_RESERVE = 2

# Language detection for the two languages of the library (G19, G20): common function words, plus the letters that
# only Turkish uses. Good enough to tell a Turkish question or passage from an English one; anything else is None.
_WORD = re.compile(r"\w+")
_TR_LETTERS = re.compile(r"[çğışöüÇĞİŞÖÜ]")
_TR_WORDS = frozenset("ve veya bir bu şu ne neden niçin nasıl hangi hangisi mi mı mu mü için ile son nedir kim kaç "
                      "var yok olan gibi daha çok da de ki ya göre hakkında değil ama fakat her hiç ise".split())
_EN_WORDS = frozenset("the a an and or of to in on for with what which why how who when where is are was were be "
                      "do does did about from by this that these those not but it its has have had".split())


def language(text: str) -> str | None:
    """'tr', 'en' or None (no clear signal)."""
    words = _WORD.findall(text.lower())
    tr = sum(w in _TR_WORDS for w in words) + len(_TR_LETTERS.findall(text))
    en = sum(w in _EN_WORDS for w in words)
    return "tr" if tr > en else "en" if en > tr else None


def _keep_other_language(query: str, ranked: list[search.Hit], hybrid: list[search.Hit], k: int) -> list[search.Hit]:
    """The top k of `ranked`, where the best hybrid passages in the other language replace the lowest-ranked
    passages in the query's language until LANGUAGE_RESERVE such passages are present (G19). They go last, in
    hybrid order. Without a clear query language, or when the hybrid top k has no such passage, nothing changes."""
    lang = language(query)
    top = ranked[:k]
    if lang is None:
        return top
    langs = {h.citation: language(h.text) for h in ranked}  # `ranked` holds every hybrid hit
    other = {c for c, lg in langs.items() if lg not in (None, lang)}
    present = {h.citation for h in top}
    add = [h.citation for h in hybrid[:k] if h.citation in other and h.citation not in present]
    same = [i for i, h in enumerate(top) if langs[h.citation] == lang]
    add = add[:max(0, min(LANGUAGE_RESERVE - len(present & other), len(same)))]
    drop = set(same[len(same) - len(add):]) if add else set()
    by_citation = {h.citation: h for h in ranked}
    return [h for i, h in enumerate(top) if i not in drop] + [by_citation[c] for c in add]


@dataclass(frozen=True)
class Stages:
    embedder: llmdap.Routed | None = None
    reranker: llmdap.Routed | None = None

    @classmethod
    def from_env(cls) -> "Stages":
        return cls(llmdap.Routed.from_env(llmdap.EMBED_ENV), llmdap.Routed.from_env(llmdap.RERANK_ENV))


_vectors: OrderedDict = OrderedDict()  # (route url, route, model, query) -> QueryVector, least recently used first
_vectors_lock = threading.Lock()


def query_vector(conn, embedder: llmdap.Routed | None, actor: Actor, query: str) -> search.QueryVector | None:
    """`vectors.query_vector` with a per-process cache. Only vectors are cached, never a failure: a query whose
    embedding failed is embedded again next time."""
    if embedder is None:
        return None
    key = (embedder.bridge.url, embedder.bridge.route, embedder.model, query)
    with _vectors_lock:
        if key in _vectors:
            _vectors.move_to_end(key)
            return _vectors[key]
    vector = vectors.query_vector(conn, embedder, actor, query)
    if vector is not None:
        with _vectors_lock:
            _vectors[key] = vector
            while len(_vectors) > QUERY_CACHE:
                _vectors.popitem(last=False)
    return vector


def retrieve(conn, actor: Actor, query: str, k: int = search.DEFAULT_K, stages: Stages = Stages(),
             scope: search.Scope = search.Scope()) -> list[search.Hit]:
    vector = query_vector(conn, stages.embedder, actor, query)
    if stages.reranker is None:
        return search.search(conn, actor, query, k, vector=vector, scope=scope)
    pool = search.search(conn, actor, query, max(k, RERANK_POOL), vector=vector, scope=scope)
    rights = kstd.Rights(conn)
    slots = [i for i, h in enumerate(pool)  # kstd: only passages whose rights allow ai_input go to the reranker
             if rights.allows(h.citation.book, h.citation.content_id, h.citation.path, "ai_input")]
    if len(slots) < 2:
        return pool[:k]
    try:
        scores = llmdap.rerank(conn, stages.reranker, actor, query, [pool[i].text[:RERANK_CHARS] for i in slots],
                               source_books=sorted({pool[i].citation.book for i in slots}), purpose="rerank")
    except llmdap.EgressError as exc:
        log.warning("reranking failed, keeping the hybrid order: %s", exc)
        return pool[:k]
    order = sorted(range(len(slots)), key=lambda j: -scores[j])  # stable: ties keep the hybrid order
    out = list(pool)  # passages that were not reranked keep their hybrid position
    for slot, j in zip(slots, order):
        out[slot] = dataclasses.replace(pool[slots[j]], score=scores[j])
    return _keep_other_language(query, out, pool, k)
