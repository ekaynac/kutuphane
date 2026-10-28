"""Search snippets: a size budget per hit for agent loops (#121).

`search_library(max_chars=…)` and `GET /v1/search?max_chars=…` give each hit a fixed window of its passage in place
of the full text. The citation handle stays, so `open_citation` is the path to the full passage.

- The window is around the best-matching span: the passage words whose lexemes (the search's text search
  configuration, `profiles.FTS_CONFIG`) are query lexemes. The best window holds the most distinct query lexemes,
  then the most matches, then starts first. Without a match it starts at the passage start.
- It is cut at white space where it can be (a single word longer than the window is cut inside), and `…` marks
  each side that was cut. The snippet, the marks included, is at most `max_chars` characters.
- No clock, no randomness, no model: the same passage and query give the same bytes (provider prompt caches).
- Snippets are made after ranking and after the gates, from the text the caller receives: they never change the
  order, and a withheld passage has no text to cut.
"""
import itertools
import re

from . import profiles

MIN_CHARS = 80
MAX_CHARS = profiles.MAX_CHUNK_CHARS  # the largest passage the chunker makes
MARK = "…"
_SPACE = re.compile(r"\s")

# The distinct words of each passage (by its index; the configuration's parser) whose lexemes include a query
# lexeme, with the smallest such lexeme. Only distinct words are normalized: ts_debug over every token was 6x slower.
_MATCHES = """
WITH q AS (SELECT tsvector_to_array(to_tsvector(%(cfg)s::regconfig, %(q)s)) AS lexemes),
words AS (
    SELECT DISTINCT t.i, p.token
      FROM unnest(%(texts)s::text[]) WITH ORDINALITY AS t(body, i)
     CROSS JOIN LATERAL ts_parse((SELECT cfgparser FROM pg_ts_config WHERE oid = %(cfg)s::regconfig), t.body) AS p)
SELECT w.i, w.token, m.lexeme
  FROM words w CROSS JOIN q
 CROSS JOIN LATERAL (SELECT min(l) AS lexeme FROM unnest(tsvector_to_array(to_tsvector(%(cfg)s::regconfig, w.token)))
                     AS l WHERE l = ANY(q.lexemes)) AS m
 WHERE m.lexeme IS NOT NULL
"""


def check(max_chars) -> None:
    """None (the full text) or a whole number MIN_CHARS..MAX_CHARS; checked before the search runs."""
    if max_chars is None:
        return
    if isinstance(max_chars, bool) or not isinstance(max_chars, int) or not MIN_CHARS <= max_chars <= MAX_CHARS:
        raise ValueError(f"max_chars must be {MIN_CHARS}..{MAX_CHARS}")


def cut(conn, query: str, texts: list[str], max_chars: int) -> list[tuple[str, bool]]:
    """(snippet, truncated) for each text, in order. A text that fits is returned whole (truncated false)."""
    long = [i for i, t in enumerate(texts) if len(t) > max_chars]
    terms: dict[int, dict[str, str]] = {i: {} for i in long}
    if long:
        for n, token, lexeme in conn.execute(_MATCHES, {"texts": [texts[i] for i in long], "q": query,
                                                        "cfg": profiles.FTS_CONFIG}):
            terms[long[n - 1]][token] = lexeme
    return [window(t, _spans(t, terms[i]), max_chars) if i in terms else (t, False) for i, t in enumerate(texts)]


def _spans(text: str, terms: dict[str, str]) -> list[tuple[int, int, str]]:
    """(start, end, lexeme) of every whole-word occurrence of the matched words, in text order."""
    return sorted((m.start(), m.end(), lexeme) for token, lexeme in terms.items()
                  for m in re.finditer(r"(?<!\w)" + re.escape(token) + r"(?!\w)", text))


def window(text: str, spans: list[tuple[int, int, str]], max_chars: int) -> tuple[str, bool]:
    """The snippet of `text` around the best group of `spans` (sorted), at most `max_chars` characters."""
    if len(text) <= max_chars:
        return text, False
    room = max_chars - 2 * len(MARK)
    first = last = 0
    if spans:
        best = None
        for i, (a, end_i, lexeme) in enumerate(spans):
            near = itertools.takewhile(lambda s, limit=a + room: s[0] < limit, spans[i:])
            group = [s for s in near if s[1] <= a + room] or [(a, min(end_i, a + room), lexeme)]
            key = (len({s[2] for s in group}), len(group))
            if best is None or key > best[0]:
                best = (key, a, max(s[1] for s in group))
        _, first, last = best
    start = max(0, first - (room - (last - first)) // 2)
    end = min(len(text), start + room)
    start = max(0, end - room)
    if start > 0 and not text[start - 1].isspace():  # move forward to a word start, never past the span
        space = _SPACE.search(text, start, first)
        start = space.end() if space else first
    if end < len(text) and not text[end].isspace() and not text[end - 1].isspace():  # back to a word end
        cut_at = max((m.start() for m in _SPACE.finditer(text, max(last, start + 1), end)), default=None)
        end = cut_at if cut_at is not None else end
    body = text[start:end].strip()
    return (MARK if start > 0 else "") + body + (MARK if end < len(text) else ""), True
