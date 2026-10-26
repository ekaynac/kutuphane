"""Finding passages (D31): the one entry point for HTTP, MCP, CLI and answers.

1. Query vector through the LLMDAP embeddings route (optional; full text alone without it). Vectors of recent
   queries are kept in memory (QUERY_CACHE entries per process), so a repeated query costs no embedding call.
2. Hybrid search: the pre-filtered, linearized `search.search` (FTS + vector, RRF).
3. Reranking through the LLMDAP rerank route (optional): the top RERANK_POOL hits are reordered and their
   scores become the reranker's relevance. The reranker reads the first RERANK_CHARS characters of each passage
   (G26); the passage itself stays whole. If the reranker fails, the hybrid order stands; the failed call is
   on record in `model_call`. Reranking only reorders passages the search already authorized and logged (the
   pool is logged as read on the caller's behalf, since its text goes to the reranker).
   Two languages (G19): when the pool holds passages in both Turkish and English, the answer model translates the
   query (`translator`), a second hybrid search runs with the translation, the two pools are merged, and each
   passage is reranked against the query in its own language. Without a translation, passages in the other
   language that the hybrid search ranked in its top k keep up to LANGUAGE_RESERVE places.
4. A question about recent things prefers newer passages among the most relevant ones (G22, `_prefer_recent`).
"""
import dataclasses
import logging
import os
import re
import threading
from collections import OrderedDict
from dataclasses import dataclass
from datetime import date

from . import kstd, llmdap, profiles, search, vectors
from .gate import Actor

log = logging.getLogger(__name__)
RERANK_POOL = 30  # M0: bge-reranker-v2-m3 over the top 30 hybrid hits, R@1 0.34 -> 0.41
# G26: the reranker (CPU) reads a passage of the target chunk size whole; only oversize JSON/HTML blocks are cut.
# Pilot radar, 7 questions: 36–58 % fewer characters to rerank; the top 8 kept the evidence passages (docs/18 §4).
RERANK_CHARS = profiles.TARGET_CHARS
QUERY_CACHE = 256
# G19: bge-reranker-v2-m3 scores a passage in the other language near zero even when it answers the question (pilot
# radar, question 2: hybrid rank 7 -> rerank rank 10, and the English question got "not in library").
LANGUAGE_RESERVE = 2
OTHER_LANGUAGE = {"tr": "en", "en": "tr"}
TRANSLATE = {"tr": "Translate the user's question into Turkish. Write only the translated question.",
             "en": "Translate the user's question into English. Write only the translated question."}
ANSWER_MODEL_ENV = "KUTUPHANE_ANSWER_MODEL"

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


# G22: a question that asks for recent things ("recent", "latest", "son", "en yeni", …) ranks the top 2k passages by
# relevance rank + date rank (newest first), so a newer passage of about the same relevance comes first. A passage's
# date is its kstd valid_from, else the first date (YYYY-MM-DD or ISO week YYYY-Www) in its path, else the first in
# its text (a record's own date, e.g. `classified_at`). The date rank counts the passages with a newer date; an
# undated passage ranks after every dated one.
_RECENT = re.compile(r"\b(recent|recently|lately|latest|newest|last (?:week|weeks|month|months)|this (?:week|month)|"
                     r"son|en yeni|güncel|yakın zamanda|bu hafta|geçen hafta)\b", re.IGNORECASE)
_DATE = re.compile(r"(?<!\d)(20\d\d)-(?:(\d\d)-(\d\d)|W(\d\d))(?!\d)")


def asks_recent(query: str) -> bool:
    return _RECENT.search(query) is not None


def _first_date(text: str) -> date | None:
    for m in _DATE.finditer(text):
        year, month, day, week = m.groups()
        try:
            return date.fromisocalendar(int(year), int(week), 1) if week else date(int(year), int(month), int(day))
        except ValueError:
            continue
    return None


def passage_date(rights: kstd.Rights, hit: search.Hit) -> date | None:
    c = hit.citation
    info = rights.info(c.book, c.content_id, c.path)
    if info and info.get("valid_from"):
        return date.fromisoformat(info["valid_from"])
    return _first_date(c.path) or _first_date(hit.text)


def _prefer_recent(conn, ranked: list[search.Hit], k: int) -> list[search.Hit]:
    head, rights = ranked[:2 * k], kstd.Rights(conn)
    dates = [passage_date(rights, h) for h in head]
    known = [d for d in dates if d]
    date_rank = [sum(e > d for e in known) if d else len(known) for d in dates]
    order = sorted(range(len(head)), key=lambda i: (i + date_rank[i], i))  # ties: the more relevant first
    return [head[i] for i in order] + ranked[2 * k:]


@dataclass(frozen=True)
class Stages:
    embedder: llmdap.Routed | None = None
    reranker: llmdap.Routed | None = None
    translator: llmdap.Routed | None = None  # the answer model on its chat route; translates queries (G19)

    @classmethod
    def from_env(cls, answer_model: str | None = None) -> "Stages":
        model = answer_model or os.environ.get(ANSWER_MODEL_ENV)
        translator = llmdap.Routed(llmdap.Bridge.from_env(), model) if model and os.environ.get(
            llmdap.ENV["route"]) else None
        return cls(llmdap.Routed.from_env(llmdap.EMBED_ENV), llmdap.Routed.from_env(llmdap.RERANK_ENV), translator)


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
    recent = asks_recent(query)
    if stages.reranker is None:
        hits = search.search(conn, actor, query, min(2 * k, search.MAX_K) if recent else k, vector=vector,
                             scope=scope)
        return _prefer_recent(conn, hits, k)[:k] if recent else hits
    size = max(k, RERANK_POOL)
    pool = search.search(conn, actor, query, size, vector=vector, scope=scope)
    translated = translate(conn, stages.translator, actor, query, pool)
    if translated:
        second = search.search(conn, actor, translated, size, scope=scope,
                               vector=query_vector(conn, stages.embedder, actor, translated))
        pool = _merge(pool, second, size)
    queries = {OTHER_LANGUAGE[language(query)]: translated} if translated else {}
    ranked = _rerank(conn, stages.reranker, actor, query, queries, pool)
    if recent:
        ranked = _prefer_recent(conn, ranked, k)
    return ranked[:k] if translated else _keep_other_language(query, ranked, pool, k)


def translate(conn, translator: llmdap.Routed | None, actor: Actor, query: str,
              pool: list[search.Hit]) -> str | None:
    """The query in the other language, if the pool holds passages in that language and the answer model can
    translate it; else None. Only the query goes to the model (no book content)."""
    lang = language(query)
    if translator is None or lang is None or not any(language(h.text) == OTHER_LANGUAGE[lang] for h in pool):
        return None
    target = OTHER_LANGUAGE[lang]
    try:
        payload = llmdap.chat(conn, translator.bridge, actor, model=translator.model, source_books=[],
                              purpose="translate", messages=[{"role": "system", "content": TRANSLATE[target]},
                                                             {"role": "user", "content": query}])
        text = payload["choices"][0]["message"]["content"]
    except (llmdap.EgressError, KeyError, IndexError, TypeError) as exc:
        log.warning("query translation failed, reranking with the question only: %s", exc)
        return None
    text = " ".join(text.split())[:search.MAX_QUERY_CHARS] if isinstance(text, str) else ""
    return text if text and text != query and language(text) == target else None


def _merge(first: list[search.Hit], second: list[search.Hit], size: int) -> list[search.Hit]:
    """Both hybrid lists in turns (1st, 1st, 2nd, 2nd, …), each passage once, at most `size` passages."""
    out, seen = [], set()
    for pair in zip(first + [None] * len(second), second + [None] * len(first)):
        for h in pair:
            if h is not None and h.citation not in seen:
                seen.add(h.citation)
                out.append(h)
    return out[:size]


def _rerank(conn, reranker: llmdap.Routed, actor: Actor, query: str, queries: dict, pool: list[search.Hit]
            ) -> list[search.Hit]:
    """The pool in the reranker's order, with its scores; the hybrid order if reranking is not possible.
    `queries` maps a passage language to the query to rerank it with (default: `query`)."""
    rights = kstd.Rights(conn)
    slots = [i for i, h in enumerate(pool)  # kstd: only passages whose rights allow ai_input go to the reranker
             if rights.allows(h.citation.book, h.citation.content_id, h.citation.path, "ai_input")]
    if len(slots) < 2:
        return pool
    groups: dict[str, list[int]] = {}
    for j, i in enumerate(slots):
        groups.setdefault(queries.get(language(pool[i].text), query), []).append(j)
    scores = [0.0] * len(slots)
    try:
        for q, members in groups.items():
            got = llmdap.rerank(conn, reranker, actor, q, [pool[slots[j]].text[:RERANK_CHARS] for j in members],
                                source_books=sorted({pool[slots[j]].citation.book for j in members}),
                                purpose="rerank")
            for j, s in zip(members, got):
                scores[j] = s
    except llmdap.EgressError as exc:
        log.warning("reranking failed, keeping the hybrid order: %s", exc)
        return pool
    order = sorted(range(len(slots)), key=lambda j: -scores[j])  # stable: ties keep the hybrid order
    out = list(pool)  # passages that were not reranked keep their hybrid position
    for slot, j in zip(slots, order):
        out[slot] = dataclasses.replace(pool[slots[j]], score=scores[j])
    return out
