"""Chunk embeddings for hybrid search (D16, D31). Vectors are made only through LLMDAP (D17, #222).

Indexing embeds the chunks of a book's current version that have no vector for the configured model yet; book
content goes to the embeddings route under the same egress policy as any model call (a local_only book never goes
to a cloud route). A query is embedded per search; if that fails, the search still answers with full text alone and
the failed call stays on record in `model_call`.

Incremental (G17): a vector records the sha256 of the text that was embedded. A new content version copies the
vector of every passage whose embedded text is unchanged (same book, model and width) and embeds only the others;
vectors never cross a book. A new profile of the same book copies them too (G27: a new chunker version re-embeds
only the passages whose text it changed): a vector depends on the embedded text and the model only. A vector whose
embedded text is not known for certain has no key (NULL, migration 015) and is never copied.

Failures (G12): a failed embedding call is retried with backoff; a batch that still fails is reported and the run
goes on with the next batch. After `give_up_after` failed batches in a row the embedder is taken as down and the
rest is not attempted. A refused egress policy and a changed vector width stop the run: every batch would fail.

Load (G18): the local embedder runs one request at a time, so a query embedding waits for the index call in front
of it. Small calls and one call in flight (the defaults of Settings) keep that wait short.
"""
import hashlib
import logging
import os
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import dataclass, field, replace

from . import kstd, llmdap, search
from .gate import Actor

log = logging.getLogger(__name__)
EMBED_CHARS = 24_000  # a longer passage is embedded by this prefix only (Astra #11); its text stays whole
INDEXER = "service:indexer"  # the principal recorded for indexing calls (an operation, not a person's request)
MAX_CONCURRENCY = 4   # the local embedder answers 503 above MODELS_MAX_INFLIGHT (8) requests: leave room for searches
SETTINGS_ENV = {"batch": "KUTUPHANE_INDEX_BATCH", "batch_chars": "KUTUPHANE_INDEX_BATCH_CHARS",
                "concurrency": "KUTUPHANE_INDEX_CONCURRENCY"}


@dataclass(frozen=True)
class Settings:
    """How hard `index` loads the embedder. A call carries at most `batch` passages and `batch_chars` embedded
    characters (one longer passage goes alone); `concurrency` calls are in flight at once."""
    # pilot radar briefs (docs/18 G18): a search embedding waited 52 s (median) behind 32-passage/24,000-character
    # calls and 2.5 s behind these
    batch: int = 8
    batch_chars: int = 8_000
    concurrency: int = 1
    retries: int = 2          # more attempts of a failed call
    backoff: float = 5.0      # seconds before the first retry, doubled for each further retry
    give_up_after: int = 3    # failed batches in a row: the embedder is down, the rest is not attempted

    def __post_init__(self):
        for name in ("batch", "batch_chars", "concurrency", "give_up_after"):
            if getattr(self, name) < 1:
                raise ValueError(f"index {name} must be at least 1")
        if self.concurrency > MAX_CONCURRENCY:
            raise ValueError(f"index concurrency must be at most {MAX_CONCURRENCY}")
        if self.retries < 0 or self.backoff < 0:
            raise ValueError("index retries and backoff must not be negative")

    @classmethod
    def from_env(cls, **overrides) -> "Settings":
        """Settings from KUTUPHANE_INDEX_*; an override that is not None (a command line option) wins."""
        values = {}
        for name, var in SETTINGS_ENV.items():
            raw = os.environ.get(var)
            if raw:
                try:
                    values[name] = int(raw)
                except ValueError:
                    raise ValueError(f"{var} must be an integer") from None
        values.update({k: v for k, v in overrides.items() if v is not None})
        return replace(cls(), **values)


@dataclass
class Indexed:
    embedded: int = 0
    reused: int = 0
    failed: list[dict] = field(default_factory=list)  # [{path, ordinal, error}]: still failing after the retries
    not_attempted: int = 0                             # passages left after give_up_after failed batches in a row

    @property
    def complete(self) -> bool:
        return not self.failed and not self.not_attempted

    def report(self) -> dict:
        return {"vectors_added": self.embedded + self.reused, "vectors_reused": self.reused,
                "failed": self.failed, "not_attempted": self.not_attempted}


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

# One vector per passage of the current version whose embedded text already has a vector of this model and width
# in the same book (any earlier version or profile). The profiles are listed, so the reuse index stays usable.
_REUSE = """
INSERT INTO chunk_vector (book, content_id, profile_id, path, ordinal, model, embedding, truncated, input_sha256)
SELECT %(book)s, %(content)s, %(profile)s, m.path, m.ordinal, %(model)s, v.embedding, m.truncated, m.sha
  FROM unnest(%(paths)s::text[], %(ordinals)s::int[], %(shas)s::bytea[], %(truncated)s::boolean[])
       AS m(path, ordinal, sha, truncated)
 CROSS JOIN LATERAL (SELECT embedding FROM chunk_vector
                      WHERE book = %(book)s AND profile_id = ANY(%(profiles)s::text[]) AND model = %(model)s
                        AND input_sha256 = m.sha AND vector_dims(embedding) = %(dims)s LIMIT 1) v
    ON CONFLICT DO NOTHING
RETURNING path, ordinal
"""


def stored_dims(conn, model: str) -> int | None:
    row = conn.execute("SELECT vector_dims(embedding) FROM chunk_vector WHERE model = %s LIMIT 1", (model,)).fetchone()
    return row[0] if row else None


def embedded_text(text: str) -> str:
    return text[:EMBED_CHARS]


def input_sha256(text: str) -> bytes:
    """The reuse key of a passage: sha256 of the UTF-8 text that is sent (migration 015 computes the same in SQL)."""
    return hashlib.sha256(embedded_text(text).encode("utf-8")).digest()


def index(conn, embedder: llmdap.Routed, book: str, settings: Settings | None = None) -> Indexed:
    """Give every current chunk of the book a vector of this model: copy it from an earlier version when the
    embedded text is unchanged, otherwise embed it. All vectors of one model have one width: a model that changed
    its output needs a new model name.
    A passage whose kstd rights do not allow `ai_input` is never sent to the embedder (full text still finds it).
    A passage longer than EMBED_CHARS is embedded by its first EMBED_CHARS characters and its vector is marked
    `truncated`; the stored chunk text, and so full text search, keep the whole passage."""
    settings = settings or Settings()
    rights = kstd.Rights(conn)
    rows = [r for r in conn.execute(_MISSING, (book, embedder.model)).fetchall()
            if rights.allows(r[0], r[1], r[3], "ai_input")]
    dims = stored_dims(conn, embedder.model)
    result = Indexed()
    reused = _reuse(conn, embedder.model, dims, rows)
    result.reused = len(reused)
    rows = [r for r in rows if (r[3], r[4]) not in reused]
    actor = Actor(INDEXER)
    batches = iter(_batches(rows, settings))
    pending: dict = {}  # future -> batch; at most settings.concurrency calls are in flight, none is queued
    in_a_row = 0
    with ThreadPoolExecutor(max_workers=settings.concurrency, thread_name_prefix="index") as pool:
        while True:
            while in_a_row < settings.give_up_after and len(pending) < settings.concurrency \
                    and (batch := next(batches, None)):
                pending[pool.submit(_embed, conn, embedder, actor, book, batch, settings)] = batch
            if not pending:
                break
            done, _ = wait(pending, return_when=FIRST_COMPLETED)
            for future in done:
                batch = pending.pop(future)
                try:
                    vectors = future.result()
                except llmdap.PolicyRefused:
                    raise
                except llmdap.EgressError as exc:
                    log.warning("embedding %d passages failed after %d retries: %s", len(batch), settings.retries,
                                exc)
                    result.failed += [{"path": r[3], "ordinal": r[4], "error": str(exc)} for r in batch]
                    in_a_row += 1
                    continue
                in_a_row = 0
                dims = dims or len(vectors[0])
                if len(vectors[0]) != dims:
                    raise llmdap.EgressError(f"{embedder.model} returned {len(vectors[0])} dimensions; "
                                             f"stored are {dims}")
                _store(conn, embedder.model, batch, vectors)
                result.embedded += len(batch)
    result.not_attempted = sum(len(b) for b in batches)
    return result


def _reuse(conn, model: str, dims: int | None, rows: list) -> set[tuple[str, int]]:
    """(path, ordinal) of the passages that got a copied vector."""
    if not rows or dims is None:
        return set()
    book, content, profile = rows[0][:3]  # _MISSING returns the current version of one book only
    profiles = [r[0] for r in conn.execute("SELECT DISTINCT profile_id FROM publication WHERE book = %s", (book,))]
    copied = conn.execute(_REUSE, {
        "book": book, "content": content, "profile": profile, "profiles": profiles, "model": model, "dims": dims,
        "paths": [r[3] for r in rows], "ordinals": [r[4] for r in rows], "shas": [input_sha256(r[5]) for r in rows],
        "truncated": [len(r[5]) > EMBED_CHARS for r in rows]}).fetchall()
    return {(p, o) for p, o in copied}


def _embed(conn, embedder: llmdap.Routed, actor: Actor, book: str, batch: list, settings: Settings) -> list:
    """One batch, retried with backoff. Every attempt is on record in `model_call`."""
    for attempt in range(settings.retries + 1):
        try:
            return llmdap.embed(conn, embedder, actor, [embedded_text(r[5]) for r in batch], source_books=[book],
                                purpose="index")
        except llmdap.PolicyRefused:
            raise
        except llmdap.EgressError as exc:
            if attempt == settings.retries:
                raise
            delay = settings.backoff * 2 ** attempt
            log.warning("embedding call failed (%s); retry %d of %d in %.0f s", exc, attempt + 1, settings.retries,
                        delay)
            time.sleep(delay)
    raise AssertionError("unreachable")


def _store(conn, model: str, batch: list, vectors: list) -> None:
    with conn.cursor() as cur:
        cur.executemany("INSERT INTO chunk_vector (book, content_id, profile_id, path, ordinal, model, embedding, "
                        "truncated, input_sha256) VALUES (%s, %s, %s, %s, %s, %s, %s::vector, %s, %s) "
                        "ON CONFLICT DO NOTHING",
                        [(*r[:5], model, search.QueryVector(model, v).literal(), len(r[5]) > EMBED_CHARS,
                          input_sha256(r[5])) for r, v in zip(batch, vectors)])


def _batches(rows: list, settings: Settings) -> list[list]:
    """At most settings.batch passages and settings.batch_chars embedded characters per embedding call; a passage
    counts by the prefix that is sent (EMBED_CHARS), and a longer one goes alone."""
    out, size = [], 0
    for r in rows:
        n = len(embedded_text(r[5]))
        if not out or len(out[-1]) == settings.batch or size + n > settings.batch_chars:
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
