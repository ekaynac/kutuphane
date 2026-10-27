"""The notes read path (docs/24 §9, §11, #71): `query_notes`, `neighbours` and notes in `open_citation`.

SQL only: no model call, no embedding, no reranker. Every read evaluates the memory rows at one watermark `w`
(`memory_seq`, commit order, §4) and decides rights now, with the gates of `search_library`: one `authz.allowed`
statement before, one more at the end, one rerun when a book was lost, then `SearchChanged`. One predicate,
`current`, decides "current" for every read (§9.2).
"""
import base64
import binascii
import inspect
import json
import math
import re
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone

from . import authz, coderepo, gate, notes, profiles
from .gate import Actor
from .search import SearchChanged

SETS = ("current", "open", "history")
ORDERS = ("newest", "oldest", "relevance")
DIRECTIONS = ("out", "in", "both")
LINK_TYPES = ("derived_from", "same_as", "about", "fixed_by", "violates", "decided_by", "supersedes", "contradicts")
NOTE_ORIGINS = ("model", "unknown")
ROLES = ("rule", "evidence")
BUDGET_TOKENS = (200, 16000)
MAX_BYTES = (8192, 131072)
MAX_NODES = 200
MAX_TEXT_CHARS = 1000
MAX_BOOKS = 50
RANK_NORMALIZATION = 4
WITHHELD = "rights do not allow AI input"
_SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}\Z")
_REPO = re.compile(r"^[a-z0-9][a-z0-9._-]{0,62}\Z")
_CLASS_KEY = re.compile(r"^[a-z0-9][a-z0-9._:/-]{0,79}\Z")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


def _dumps(obj) -> str:
    """The one serialization the size limits count (the HTTP body is exactly these bytes)."""
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def _size(obj) -> int:
    return len(_dumps(obj).encode())


# --- request context and the "current" predicate (§9.2) ------------------------------------------------------

@dataclass(frozen=True)
class Context:
    """The request context: the code target (`repo` + `commit`, or `repo` + `branch`) and the scope values."""
    repo: str | None = None
    branch: str | None = None
    path: str | None = None    # one path, or a directory prefix that ends with "/"
    commit: str | None = None

    def __post_init__(self):
        if self.repo is not None and not (isinstance(self.repo, str) and _REPO.match(self.repo)):
            raise ValueError("repo must be a repository slug")
        for name in ("branch", "path", "commit"):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, str) or not value or _CONTROL.search(value)
                                      or len(value) > 1000):
                raise ValueError(f"{name} must be a non-empty string without control characters")
        if self.path is not None and (self.path.startswith("/") or ".." in self.path.split("/")):
            raise ValueError("path must be relative, without '..'")
        if self.commit is not None and self.repo is None:
            raise ValueError("commit needs repo")


@dataclass
class Note:
    """One note evaluated at `w`: its row, effective Standing, shown origin, and the code statuses at the
    request's targets."""
    seq: int
    book: str
    id: str
    kind: str
    body: str
    class_key: str | None
    scope_repo: str | None
    scope_branch: str | None
    scope_paths: list
    observed_commit: str | None
    written_at: datetime
    ai_input: bool               # note AND the journals of its closure now (docs/24 §20.3)
    path_ok: bool                # a file path in the context matches a scope glob (SQL, scope_path_re)
    origin: str
    rank: float = 0.0
    w: int = 0
    standing: str = "pending"
    standing_seq: int | None = None
    citations: list = field(default_factory=list)  # [(kind, ref, Status | None)]; None: not verified yet
    checks: list = field(default_factory=list)     # [(index in citations, (book, CodeCitation, stored hash))]

    @property
    def ref(self) -> str:
        return f"{self.book}@{self.id}"

    @property
    def role(self) -> str:
        return notes.KIND_ROLE[self.kind]


def _glob_prefix_ok(glob: str, prefix: str) -> bool:
    """A directory prefix matches a glob when the glob's literal head and the prefix agree as far as both go."""
    head = re.split(r"[*?]", glob, maxsplit=1)[0]
    return head.startswith(prefix) or prefix.startswith(head)


def scope_verdict(note: Note, ctx: Context) -> str:
    """`match`, `mismatch` (a bounded dimension that the context contradicts) or `needs_context` (a bounded
    dimension that the context does not give)."""
    missing = False
    if note.scope_repo is not None:
        if ctx.repo is None:
            missing = True
        elif ctx.repo != note.scope_repo:
            return "mismatch"
    if note.scope_branch is not None:
        if ctx.branch is None:
            missing = True
        elif ctx.branch != note.scope_branch:
            return "mismatch"
    if note.scope_paths:
        if ctx.path is None:
            missing = True
        elif ctx.path.endswith("/"):
            if not any(_glob_prefix_ok(g, ctx.path) for g in note.scope_paths):
                return "mismatch"
        elif not note.path_ok:
            return "mismatch"
    return "needs_context" if missing else "match"


def current(note: Note, ctx: Context, w: int) -> str | None:
    """THE "current" predicate (docs/24 §9.2): None when the note is current at `w` in this context, else why not:
    `standing`, `time`, `needs_context`, `scope` or `code`. The note carries its Standing at `w` and the statuses of
    its code citations at the context's targets."""
    if note.w != w:
        raise ValueError("note was evaluated at another watermark")
    if note.standing != "approved":
        return "standing"
    if note.kind == "test_result":  # Time as_of(written_at): history at any later time
        return "time"
    scope = scope_verdict(note, ctx)
    if scope == "mismatch":
        return "scope"
    if scope == "needs_context" and note.role == "rule":
        return "needs_context"
    if any(kind == "code" and st is not None and st.status not in ("verified", "not_checked")
           for kind, _, st in note.citations):
        return "code"  # a failed check never restores authority
    return None


def _placement(note: Note, ctx: Context, w: int, sets, include_unverified: bool) -> tuple[bool, bool, str | None]:
    """(in the requested sets, current, the `excluded` counter to bump)."""
    if scope_verdict(note, ctx) == "mismatch":
        return False, False, None
    why = current(note, ctx, w)
    if why is None:
        return "current" in sets, True, None
    if note.standing == "pending":
        return "open" in sets, False, None
    if note.standing in ("rejected", "retired") or why == "time":
        return "history" in sets, False, None
    # approved, durable, in scope, but not current here
    if "current" not in sets:
        return False, False, None
    if why == "code":
        return include_unverified, False, "code"
    return False, False, why


def _set_at(standing: str, kind: str, sets) -> bool:
    """Set membership by Standing and Time only: what a tombstone compares (§9.5)."""
    if standing == "pending":
        return "open" in sets
    if standing in ("rejected", "retired") or kind == "test_result":
        return "history" in sets
    return "current" in sets


# --- loading and annotating notes at w ------------------------------------------------------------------------

def watermark(conn) -> int:
    """The highest memory_seq visible now. Writers take `seq` under one advisory lock held to commit, so every row
    with seq <= this value is committed (§4, §9.5)."""
    return conn.execute(
        "SELECT greatest((SELECT max(seq) FROM note), (SELECT max(seq) FROM write_record), "
        "                (SELECT max(seq) FROM note_link), (SELECT max(seq) FROM standing_event), 0)").fetchone()[0]


_NOTES = """
SELECT n.seq, n.book, n.id, n.kind, n.body, n.class_key, n.scope_repo, n.scope_branch, n.scope_paths,
       n.observed_commit, n.written_at, n.ai_input AND j.ai_input,
       (%(path)s::text IS NULL OR cardinality(n.scope_path_re) = 0
        OR EXISTS (SELECT 1 FROM unnest(n.scope_path_re) r WHERE %(path)s::text ~ r)),
       (SELECT CASE WHEN bool_or(wr.origin = 'model') THEN 'model' ELSE 'unknown' END FROM write_record wr
         WHERE wr.note_seq = n.seq AND wr.action = 'propose' AND wr.seq <= %(w)s),
       CASE WHEN %(text)s::text IS NULL THEN 0
            ELSE ts_rank_cd(n.tsv, websearch_to_tsquery(%(cfg)s::regconfig, %(text)s::text), %(norm)s) END
  FROM note n JOIN note_journal j ON j.seq = n.seq
 WHERE n.book = ANY(%(books)s::text[]) AND n.seq <= %(w)s
   AND (%(seqs)s::bigint[] IS NULL OR n.seq = ANY(%(seqs)s::bigint[]))
   AND (%(kinds)s::text[] IS NULL OR n.kind = ANY(%(kinds)s::text[]))
   AND (%(class_key)s::text IS NULL OR n.class_key = %(class_key)s::text)
   AND (%(after)s::timestamptz IS NULL OR n.written_at > %(after)s::timestamptz)
   AND (%(before)s::timestamptz IS NULL OR n.written_at < %(before)s::timestamptz)
   AND (%(text)s::text IS NULL OR (n.search AND j.search
        AND n.tsv @@ websearch_to_tsquery(%(cfg)s::regconfig, %(text)s::text)))
"""


def _load(conn, books, w: int, ctx: Context, *, seqs=None, kinds=None, class_key=None, after=None, before=None,
          text=None) -> list[Note]:
    rows = conn.execute(_NOTES, {
        "books": sorted(books), "w": w, "seqs": seqs, "kinds": kinds, "class_key": class_key, "after": after,
        "before": before, "text": text, "cfg": profiles.FTS_CONFIG, "norm": RANK_NORMALIZATION,
        "path": ctx.path if ctx.path and not ctx.path.endswith("/") else None}).fetchall()
    out = [Note(*r[:13], origin=r[13], rank=float(r[14]), w=w) for r in rows]
    standing = notes.effective_standing(conn, [n.seq for n in out], w)
    for n in out:
        n.standing, n.standing_seq = standing[n.seq]
    return out


NOT_CHECKED = coderepo.Status("not_checked")


def _citations(conn, items: list[Note], read: set, targets: dict) -> None:
    """Each note's citations in order. Passage citations into a book the caller cannot read are left out. A code
    citation into a repository without a target at the request is `not_checked` (no git process runs); one with a
    target waits in `checks` for `_verify`, which only the notes that a read may show need."""
    if not items:
        return
    by_seq = {n.seq: n for n in items}
    rows = conn.execute(
        "SELECT note_seq, book, kind, cite_book, content_id, profile_id, path, ordinal, repo, commit, line_start, "
        "line_end, symbol, excerpt_sha256 FROM note_citation WHERE note_seq = ANY(%s) ORDER BY note_seq, n",
        (list(by_seq),)).fetchall()
    for r in rows:
        note = by_seq[r[0]]
        if r[2] == "passage":
            if f"book:{r[3]}" in read:
                note.citations.append(("passage", f"{r[3]}@{r[4]}/{r[5]}/{r[6]}#{r[7]}", None))
        else:
            cite = coderepo.CodeCitation(r[8], r[9], r[6], r[10], r[11], r[12])
            targeted = (r[1], cite.repo) in targets
            note.citations.append(("code", str(cite), None if targeted else NOT_CHECKED))
            if targeted:
                note.checks.append((len(note.citations) - 1, (r[1], cite, bytes(r[13]))))


def _verify(verifier: coderepo.Verifier, items: list[Note]) -> None:
    """The statuses of the waiting code citations of `items`, in batches of at most coderepo.MAX_CITATIONS, with the
    request's one verifier (one cache)."""
    waiting = [(n, i, c) for n in items for i, c in n.checks]
    for n in items:
        n.checks = []
    for start in range(0, len(waiting), coderepo.MAX_CITATIONS):
        batch = waiting[start:start + coderepo.MAX_CITATIONS]
        for (note, i, _), st in zip(batch, verifier.verify([c for _, _, c in batch])):
            kind, ref, _ = note.citations[i]
            note.citations[i] = (kind, ref, st)


@dataclass
class Graph:
    """The memory edges at w that touch a set of notes, restricted to edges whose other end the caller may read."""
    edges: list   # (link seq, src seq, type, dst seq | None, passage handle | None)
    refs: dict    # note seq -> ref, for every readable note at either end
    standing: dict


def _graph(conn, seqs, read: set, w: int) -> Graph:
    rows = conn.execute(
        "SELECT l.seq, l.src, l.src_book, s.id, l.type, l.dst_note, l.dst_note_book, d.id, l.dst_book, "
        "       l.dst_content_id, l.dst_profile_id, l.dst_path, l.dst_ordinal "
        "  FROM note_link l JOIN note s ON s.seq = l.src LEFT JOIN note d ON d.seq = l.dst_note "
        " WHERE l.seq <= %s AND (l.src = ANY(%s) OR l.dst_note = ANY(%s)) ORDER BY l.seq",
        (w, list(seqs), list(seqs))).fetchall()
    edges, refs = [], {}
    for (seq, src, src_book, src_id, type_, dst, dst_book, dst_id, p_book, p_ct, p_pf, p_path, p_ord) in rows:
        if f"book:{src_book}" not in read or f"book:{dst_book or p_book}" not in read:
            continue
        refs[src] = f"{src_book}@{src_id}"
        if dst is not None:
            refs[dst] = f"{dst_book}@{dst_id}"
        edges.append((seq, src, type_, dst, None if dst is not None else f"{p_book}@{p_ct}/{p_pf}/{p_path}#{p_ord}"))
    return Graph(edges, refs, notes.effective_standing(conn, list(refs), w) if refs else {})


def _recurrence(conn, items: list[Note], w: int) -> tuple[dict, dict]:
    """({note seq: propose write records with seq <= w over its book-local same_as cluster}, {note seq: cluster})
    (§7)."""
    clusters, members = {}, {}
    for book in sorted({n.book for n in items}):
        for seq, root in notes.clusters(conn, book, w).items():
            clusters[seq] = root
            members.setdefault(root, []).append(seq)
    if not clusters:
        return {}, {}
    counts = dict(conn.execute(
        "SELECT note_seq, count(*) FROM write_record WHERE action = 'propose' AND seq <= %s "
        "AND note_seq = ANY(%s) GROUP BY note_seq",
        (w, sorted({s for n in items for s in members.get(clusters.get(n.seq, n.seq), [n.seq])}))).fetchall())
    total = {root: sum(counts.get(s, 0) for s in ms) for root, ms in members.items()}
    return {n.seq: total.get(clusters.get(n.seq, n.seq), counts.get(n.seq, 0)) for n in items}, clusters


def _iso(t: datetime) -> str:
    return t.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _item(note: Note, is_current: bool, recurrence: int, graph: Graph, for_model: bool) -> dict:
    """One note, with keys in a fixed order (deterministic bytes). Its code citations must be verified."""
    if note.checks:
        raise ValueError("a note is shown only after _verify")
    links = {}
    for _, src, type_, dst, _p in graph.edges:
        if note.seq in (src, dst):
            links[type_] = links.get(type_, 0) + 1
    withheld = for_model and not note.ai_input
    item = {"ref": note.ref, "kind": note.kind, "role": note.role, "standing": note.standing,
            "current": is_current, "origin": note.origin,
            "text": None if withheld else note.body, "withheld": WITHHELD if withheld else None,
            "class_key": note.class_key,
            "scope": None if note.scope_repo is None else {"repo": note.scope_repo, "branch": note.scope_branch,
                                                            "paths": list(note.scope_paths)},
            "observed_commit": note.observed_commit, "written_at": _iso(note.written_at),
            "recurrence": recurrence, "links": {t: links[t] for t in LINK_TYPES if t in links},
            "citations": [_citation(k, ref, st) for k, ref, st in note.citations]}
    if note.standing == "retired":
        item["successor"] = _successor(note.seq, graph)
    return item


def _citation(kind: str, ref: str, st) -> dict:
    if kind == "passage":
        return {"ref": ref}
    out = {"ref": ref, "status": st.status}
    if st.moved_to is not None:
        out["moved_to"] = st.moved_to
    if st.symbol_found_at:
        out["symbol_found_at"] = list(st.symbol_found_at)
    if st.reason is not None:
        out["reason"] = st.reason
    return out


def _successor(seq: int, graph: Graph) -> str | None:
    """The readable note that supersedes this one (a creation link), oldest first."""
    return next((graph.refs[src] for _, src, type_, dst, _p in graph.edges if type_ == "supersedes" and dst == seq),
                None)


def _unfixed(note: Note, graph: Graph) -> bool:
    """A finding with no fixed_by edge to a readable note that is approved or pending (§9.1)."""
    return note.kind == "finding" and not any(
        type_ == "fixed_by" and src == note.seq and dst is not None
        and graph.standing.get(dst, ("pending", None))[0] in ("approved", "pending")
        for _, src, type_, dst, _p in graph.edges)


# --- size limits ------------------------------------------------------------------------------------------

def _fits(nbytes: int, max_bytes: int, budget_tokens: int) -> bool:
    return nbytes <= max_bytes and math.ceil(nbytes / 4) <= budget_tokens


def _cut(envelope_bytes: int, item: dict, max_bytes: int, budget_tokens: int) -> dict:
    """The first item alone does not fit: cut its text until the whole response fits (`text_cut: true`). The
    budget estimate gives way only when the item's metadata alone exceeds it."""
    def total(it):
        return envelope_bytes + _size(it)
    if item.get("text") is None:  # withheld, or a tombstone: nothing to cut
        return item
    cut = {**item, "text": "", "text_cut": True}
    limit = max_bytes if total(cut) > budget_tokens * 4 else min(max_bytes, budget_tokens * 4)
    text = item["text"] or ""
    lo, hi = 0, len(text)
    while lo < hi:  # the longest prefix that fits
        mid = (lo + hi + 1) // 2
        if total({**cut, "text": text[:mid]}) <= limit:
            lo = mid
        else:
            hi = mid - 1
    return {**cut, "text": text[:lo]}


def _page(envelope: dict, entries, cursor_of, max_bytes: int, budget_tokens: int):
    """Entries in order while both limits hold, counting the whole serialized response: `envelope` (its lists
    empty, `next_cursor` null) plus every entry, comma and the continuation. `entries` yields (list name, entry, sort
    key) lazily; the next entry is read ahead only on the page's boundary, where an entry fits only without a
    continuation. Returns ({list name: entries}, next cursor, the sort key of the last entry taken)."""
    base_null = _size(envelope)

    def fits(cursor, nbytes) -> bool:
        base = base_null if cursor is None else base_null - 4 + len(_dumps(cursor).encode())
        return _fits(base + nbytes, max_bytes, budget_tokens)

    taken, total, last = {}, 0, None
    ahead = iter(entries)
    current = next(ahead, None)
    while current is not None:
        name, entry, sort_key = current
        new_total = total + _size(entry) + (1 if taken.get(name) else 0)
        if fits(cursor_of(sort_key), new_total):  # fits even with a continuation after it
            taken.setdefault(name, []).append(entry)
            total, last, current = new_total, sort_key, next(ahead, None)
            continue
        if taken and not fits(None, new_total):
            return taken, cursor_of(last), last
        following = next(ahead, None)
        nxt = cursor_of(sort_key) if following is not None else None
        if nxt is None and fits(None, new_total):  # the last entry, without a continuation
            taken.setdefault(name, []).append(entry)
            return taken, None, sort_key
        if not taken:  # the first entry does not fit: cut its text
            base = base_null if nxt is None else base_null - 4 + len(_dumps(nxt).encode())
            return {name: [_cut(base, entry, max_bytes, budget_tokens)]}, nxt, sort_key
        return taken, cursor_of(last), last
    return taken, None, last


LEFT = "left"  # the sort key ("left", note seq) of a tombstone; tombstones come before the items (§9.5)


def _cursor(w: int, sort_key) -> str:
    return base64.urlsafe_b64encode(_dumps([w, *sort_key]).encode()).decode().rstrip("=")


def _uncursor(text: str) -> tuple[int, tuple]:
    """(w, sort key): an item's sort key, or (LEFT, seq) to continue the tombstones after `seq`."""
    try:
        value = json.loads(base64.urlsafe_b64decode(text + "=" * (-len(text) % 4)))
        if (isinstance(value, list) and len(value) in (2, 3) and all(type(v) is int for v in (value[0], value[-1]))
                and (len(value) == 2 or value[1] == LEFT or type(value[1]) in (int, float))):
            return value[0], tuple(value[1:])
    except (ValueError, binascii.Error, UnicodeDecodeError):
        pass
    raise ValueError("invalid cursor")


# --- the gates (§11) ---------------------------------------------------------------------------------------

def _read(conn, actor: Actor) -> authz.Allowed:
    return authz.allowed(conn, actor.principal, actor.on_behalf_of, ["read"])


def _journals(conn, objects, wanted) -> list[str]:
    books = sorted(o.removeprefix("book:") for o in objects)
    if wanted is not None:
        books = sorted(set(books) & set(wanted))
    return [r[0] for r in conn.execute("SELECT book FROM journal WHERE book = ANY(%s) ORDER BY book", (books,))]


def _lost(conn, actor: Actor, action: str, pre: authz.Allowed, final: authz.Allowed) -> bool:
    """Books readable before the query and not at its end; each loss is logged."""
    lost = sorted(pre.objects("read") - final.objects("read"))
    for obj in lost:
        gate.log_event(conn, actor, action, obj, "read", authz.Decision(False, "changed during query"),
                       final.policies.get(obj), None, None)
    return bool(lost)


def _log(conn, actor: Actor, action: str, final: authz.Allowed, delivered: list[Note], w: int) -> None:
    """One access_event per book with delivered notes: items = [{ref, standing_seq}], memory_seq = w (AT-09)."""
    by_book = {}
    for n in delivered:
        by_book.setdefault(n.book, {})[n.ref] = n.standing_seq
    for book in sorted(by_book):
        obj = f"book:{book}"
        gate.log_event(conn, actor, action, obj, "read", final.decisions[obj]["read"], final.policies.get(obj),
                       None, None, items=[{"ref": r, "standing_seq": s} for r, s in by_book[book].items()],
                       memory_seq=w)


# --- query_notes (§9.1) --------------------------------------------------------------------------------------

def _strings(name: str, value, allowed=None, pattern=None) -> list[str] | None:
    if value is None:
        return None
    value = [value] if isinstance(value, str) else value
    if not isinstance(value, (list, tuple)) or not value or not all(isinstance(v, str) for v in value):
        raise ValueError(f"{name} must be a non-empty list of strings")
    bad = [v for v in value if (allowed is not None and v not in allowed) or (pattern and not pattern.match(v))]
    if bad:
        raise ValueError(f"{name}: unknown value {bad[0]!r}")
    return sorted(set(value))


def _int(name: str, value, lo: int, hi: int) -> int:
    if type(value) is not int or not lo <= value <= hi:
        raise ValueError(f"{name} must be an integer in {lo}..{hi}")
    return value


def _time(name: str, value) -> datetime | None:
    if value is None:
        return None
    try:
        t = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be an ISO 8601 time") from None
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def _sets(value) -> list[str]:
    return _strings("sets", value, SETS)


def _kinds(kind, role) -> list[str] | None:
    kinds = _strings("kind", kind, tuple(notes.KIND_ROLE))
    roles = _strings("role", role, ROLES)
    if roles is not None:
        by_role = [k for k, r in notes.KIND_ROLE.items() if r in roles]
        kinds = sorted(set(kinds or by_role) & set(by_role))
    return kinds


def _as_of(conn, as_of, cursor) -> tuple[int, tuple | None]:
    now = watermark(conn)
    after = None
    if cursor is not None:
        w, after = _uncursor(cursor)
        if as_of is not None and as_of != w:
            raise ValueError("cursor implies its own as_of")
        as_of = w
    if as_of is None:
        return now, None
    if type(as_of) is not int or not 0 <= as_of <= now:
        raise ValueError("as_of must be a watermark that was handed out")
    return as_of, after


def _targets(conn, books, ctx: Context) -> dict:
    return coderepo.resolve_targets(conn, books, ctx.repo, ctx.branch, ctx.commit)


def _targets_out(targets: dict) -> dict:
    return {f"{b}/{r}": (t if isinstance(t, str) else None) for (b, r), t in sorted(targets.items())}


def query_notes(conn, actor: Actor, *, for_model: bool, book=None, sets=("current",), kind=None, role=None,
                origin=None, class_key=None, repo=None, branch=None, path=None, commit=None, commits=None,
                written_after=None, written_before=None, since=None, text=None, unfixed: bool = False,
                collapse: bool = False, include_unverified: bool = False, order: str = "newest",
                budget_tokens: int = 2000, max_bytes: int = 32768, as_of=None, cursor=None,
                attempts: int = 2) -> dict:
    """docs/24 §9.1. `for_model`: the reader puts the text into a model's context (`server._for_model`)."""
    wanted = _strings("book", book, pattern=_SLUG)
    if wanted is not None and len(wanted) > MAX_BOOKS:
        raise ValueError(f"at most {MAX_BOOKS} books")
    sets = _sets(list(sets))
    kinds = _kinds(kind, role)
    origins = _strings("origin", origin, NOTE_ORIGINS)
    if class_key is not None and not (isinstance(class_key, str) and _CLASS_KEY.match(class_key)):
        raise ValueError("invalid class_key")
    ctx = Context(repo, branch, path, commit)
    rng = None
    if commits is not None:
        if repo is None:
            raise ValueError("commits needs repo")
        rng = coderepo.parse_range(commits)
    after, before = _time("written_after", written_after), _time("written_before", written_before)
    if text is not None and (not isinstance(text, str) or not text.strip() or len(text) > MAX_TEXT_CHARS):
        raise ValueError(f"text must be 1..{MAX_TEXT_CHARS} characters")
    if order not in ORDERS:
        raise ValueError(f"order must be one of {', '.join(ORDERS)}")
    if order == "relevance" and text is None:
        raise ValueError("order relevance needs text")
    for name, value in (("unfixed", unfixed), ("collapse", collapse), ("include_unverified", include_unverified)):
        if type(value) is not bool:
            raise ValueError(f"{name} must be true or false")
    budget_tokens = _int("budget_tokens", budget_tokens, *BUDGET_TOKENS)
    max_bytes = _int("max_bytes", max_bytes, *MAX_BYTES)
    w, after_key = _as_of(conn, as_of, cursor)
    if since is not None:
        since = _int("since", since, 0, w)

    for _ in range(attempts):
        pre = _read(conn, actor)
        read = pre.objects("read")
        books = _journals(conn, read, wanted)
        targets = _targets(conn, books, ctx)
        revs = {}
        if rng is not None:
            for b in books:
                if conn.execute("SELECT 1 FROM code_repo WHERE book = %s AND slug = %s AND removed_at IS NULL",
                                (b, repo)).fetchone():
                    revs[b] = set(coderepo.rev_list(conn, b, repo, *rng))
        found = _load(conn, books, w, ctx, kinds=kinds, class_key=class_key, after=after, before=before, text=text)
        if rng is not None:
            found = [n for n in found if n.scope_repo == repo and n.observed_commit in revs.get(n.book, ())]
        if origins is not None:
            found = [n for n in found if n.origin in origins]
        _citations(conn, found, read, targets)
        graph = _graph(conn, [n.seq for n in found], read, w)
        recurrence, clusters = _recurrence(conn, found, w) if found else ({}, {})

        changed = _changed(conn, [n.seq for n in found], since, w, read) if since is not None else None
        then = notes.effective_standing(conn, [n.seq for n in found], since) if since is not None else {}
        candidates, left = [], []
        for n in found:
            if unfixed and not _unfixed(n, graph):
                continue
            if changed is not None and n.seq not in changed:
                continue
            candidates.append(n)
            if since is not None and n.seq <= since and n.seq in changed["standing"] \
                    and _set_at(then[n.seq][0], n.kind, sets) and not _set_at(n.standing, n.kind, sets):
                left.append(n)  # out of the sets by Standing or Time alone: never an item too
        key = {"newest": lambda n: (-n.seq,), "oldest": lambda n: (n.seq,),
               "relevance": lambda n: (-n.rank, -n.seq)}[order]
        candidates.sort(key=key)
        in_left = after_key is not None and after_key[0] == LEFT
        tombstones = sorted((n for n in left if not in_left or n.seq > after_key[1]), key=lambda n: n.seq) \
            if after_key is None or in_left else []
        items_after = None if after_key is None or in_left else after_key
        members = {}
        for n in candidates:
            members.setdefault(clusters.get(n.seq, n.seq), []).append(n)
        verifier = coderepo.Verifier(conn, targets)
        placed, kept, passed = {}, {}, []

        def place(group):
            """The placement of each note; its code citations are verified only when they decide it or show."""
            fresh = [n for n in group if n.seq not in placed]
            _verify(verifier, [n for n in fresh if _placement(n, ctx, w, sets, include_unverified)[0]])
            placed.update({n.seq: _placement(n, ctx, w, sets, include_unverified) for n in fresh})

        def entries():
            """Tombstones (by note seq), then items in order, built and verified as the page needs them; `passed`
            gets the sort key and the counter of each excluded note on the way."""
            for n in tombstones:
                yield "left", {"ref": n.ref, "standing": n.standing, "seq": n.standing_seq,
                               "successor": _successor(n.seq, graph)}, (LEFT, n.seq)
            for n in candidates:
                if items_after is not None and key(n) <= items_after:
                    continue
                root = clusters.get(n.seq, n.seq)
                place(members[root] if collapse else [n])
                in_sets, is_current, why = placed[n.seq]
                if in_sets and collapse:
                    if root not in kept:
                        kept[root] = _kept([m for m in members[root] if placed[m.seq][0]], graph)
                    if n.seq not in kept[root]:
                        continue
                if in_sets:
                    yield "items", _item(n, is_current, recurrence.get(n.seq, 0), graph, for_model), key(n)
                elif why in ("code", "needs_context"):
                    passed.append((key(n), why))

        # The counts are known after the page; their upper bound is sized in, so the response never grows past it.
        bound = len(candidates)
        envelope = {"items": [], "left": [], "books": books, "watermark": w, "next_cursor": None,
                    "excluded": {"code": bound, "needs_context": bound}, "targets": _targets_out(targets)}
        taken, nxt, last = _page(envelope, entries(), lambda k: _cursor(w, k), max_bytes, budget_tokens)
        excluded = {"code": 0, "needs_context": 0}  # the notes this page passed over (§9.1)
        for k, why in passed:
            if nxt is None or (last[0] != LEFT and k <= last):
                excluded[why] += 1
        final = _read(conn, actor)
        if _lost(conn, actor, "query_notes", pre, final):
            continue  # the whole query, counts included, again with the rights as they are now

        by_ref = {n.ref: n for n in candidates}
        items, gone = taken.get("items", []), taken.get("left", [])
        _log(conn, actor, "query_notes", final, [by_ref[e["ref"]] for e in items + gone], w)
        return {**envelope, "items": items, "left": gone, "next_cursor": nxt, "excluded": excluded}
    raise SearchChanged("authorization changed during the query; retry")


def _changed(conn, seqs, since: int, w: int, read: set) -> dict:
    """{note seq: True} for notes with a memory event in (since, w], plus "standing": the notes with a Standing
    event there (§9.5: written, linked, a Standing event, or a recurrence). A link counts only from the authorized
    graph: the caller may read both of its ends now."""
    if not seqs:
        return {"standing": set()}
    p = {"s": list(seqs), "a": since, "w": w, "b": sorted(o.removeprefix("book:") for o in read)}
    out = {r[0]: True for r in conn.execute("""
        SELECT seq FROM note WHERE seq = ANY(%(s)s) AND seq > %(a)s
        UNION SELECT note_seq FROM write_record WHERE note_seq = ANY(%(s)s) AND seq > %(a)s AND seq <= %(w)s
        UNION SELECT src FROM note_link WHERE src = ANY(%(s)s) AND seq > %(a)s AND seq <= %(w)s
                                          AND coalesce(dst_note_book, dst_book) = ANY(%(b)s)
        UNION SELECT dst_note FROM note_link WHERE dst_note = ANY(%(s)s) AND seq > %(a)s AND seq <= %(w)s
                                               AND src_book = ANY(%(b)s)
        UNION SELECT note_seq FROM standing_event WHERE note_seq = ANY(%(s)s) AND seq > %(a)s AND seq <= %(w)s""", p)}
    out["standing"] = {r[0] for r in conn.execute(
        "SELECT DISTINCT note_seq FROM standing_event WHERE note_seq = ANY(%(s)s) AND seq > %(a)s AND seq <= %(w)s",
        p)}
    return out


def _kept(group: list, graph: Graph) -> set:
    """`collapse` within one book-local same_as cluster (`group`: its members in the sets): the newest member stays,
    and so does every member that a visible `contradicts` edge joins to another member. So no two contradicting
    members are ever collapsed together, and none of them is dropped (§9.1)."""
    seqs = {n.seq for n in group}
    contra = {s for _, src, t, dst, _p in graph.edges if t == "contradicts" and src in seqs and dst in seqs
              for s in (src, dst)}
    return ({max(seqs)} if seqs else set()) | contra


# --- neighbours (§9.3) -------------------------------------------------------------------------------------

def neighbours(conn, actor: Actor, *, for_model: bool, ref: str, types=None, depth: int = 1,
               direction: str = "both", sets=("current",), repo=None, branch=None, path=None, commit=None,
               max_nodes: int = 50, budget_tokens: int = 2000, max_bytes: int = 32768, as_of=None,
               attempts: int = 2) -> dict:
    types = _strings("types", types, LINK_TYPES)
    depth = _int("depth", depth, 1, 2)
    if direction not in DIRECTIONS:
        raise ValueError(f"direction must be one of {', '.join(DIRECTIONS)}")
    sets = _sets(list(sets))
    ctx = Context(repo, branch, path, commit)
    max_nodes = _int("max_nodes", max_nodes, 1, MAX_NODES)
    budget_tokens = _int("budget_tokens", budget_tokens, *BUDGET_TOKENS)
    max_bytes = _int("max_bytes", max_bytes, *MAX_BYTES)
    if not isinstance(ref, str):
        raise ValueError("ref must be a note reference or a passage handle")
    try:
        root_book, root_id = notes.parse_ref(ref)
        passage = None
    except ValueError:
        passage = notes.parse_passage(ref)
        root_book, root_id = passage.book, None
    w, _ = _as_of(conn, as_of, None)

    for _ in range(attempts):
        pre = _read(conn, actor)
        read = pre.objects("read")
        if f"book:{root_book}" not in read:
            gate.log_event(conn, actor, "neighbours", f"book:{root_book}", "read",
                           authz.Decision(False, "no read right"), pre.policies.get(f"book:{root_book}"), None, None)
            raise gate.Denied(f"read on book:{root_book}: no read right")
        books = _journals(conn, read, None)
        targets = _targets(conn, books, ctx)
        verifier = coderepo.Verifier(conn, targets)
        root = None
        if root_id is not None:
            row = conn.execute("SELECT seq FROM note WHERE book = %s AND id = %s AND seq <= %s",
                               (root_book, root_id, w)).fetchone()
            if row is None:
                raise gate.NotFound(ref)
            loaded = _load(conn, books, w, ctx, seqs=[row[0]])
            if not loaded:
                raise gate.NotFound(ref)
            root = loaded[0]
            _citations(conn, [root], read, targets)
            _verify(verifier, [root])

        evaluated = {root.seq: root} if root else {}
        nodes, edges, seen_links = [], [], set()
        included = {root.seq} if root else set()
        frontier, truncated = ([root.seq] if root else []), False
        for level in range(depth):
            links = _links(conn, frontier, passage if level == 0 else None, direction, types, w)
            fresh = sorted({s for _, src, _t, dst, _p in links for s in (src, dst) if s is not None} - set(evaluated))
            if fresh:
                loaded = _load(conn, books, w, ctx, seqs=fresh)
                _citations(conn, loaded, read, targets)
                # code statuses only for a note that can be a node: they can only drop it from the sets
                _verify(verifier, [n for n in loaded if _placement(n, ctx, w, sets, False)[0]])
                evaluated.update({n.seq: n for n in loaded})
            nxt = []
            for lseq, src, type_, dst, phandle in links:
                if lseq in seen_links:
                    continue
                other = [s for s in (src, dst) if s is not None and s not in included]
                ok = True
                for s in other:
                    n = evaluated.get(s)  # None: an unreadable book or a note that is not a journal note
                    if n is None or not _placement(n, ctx, w, sets, False)[0]:
                        ok = False
                    elif len(nodes) >= max_nodes:
                        ok, truncated = False, True
                    else:
                        included.add(s)
                        nodes.append(n)
                        nxt.append(s)
                if not ok or not all(s in included for s in (src, dst) if s is not None):
                    continue
                seen_links.add(lseq)
                edges.append((lseq, src, type_, dst, phandle))
            frontier = nxt
            if not frontier:
                break

        all_notes = ([root] if root else []) + nodes
        graph = _graph(conn, [n.seq for n in all_notes], read, w)
        recurrence, _ = _recurrence(conn, all_notes, w) if all_notes else ({}, {})
        final = _read(conn, actor)
        if _lost(conn, actor, "neighbours", pre, final):
            continue

        refs = {n.seq: n.ref for n in all_notes}

        def item(n):
            return _item(n, current(n, ctx, w) is None, recurrence.get(n.seq, 0), graph, for_model)
        envelope = {"root": item(root) if root else None, "nodes": [],
                    "edges": [{"src": refs[s], "type": t, "dst": refs[d] if d is not None else p}
                              for _, s, t, d, p in edges],
                    "targets": _targets_out(targets), "watermark": w, "truncated": truncated}
        if root is not None and _size(envelope) > max_bytes:
            envelope["root"] = _cut(_size({**envelope, "root": None}), envelope["root"], max_bytes, budget_tokens)
        taken, _nxt, _last = _page(envelope, [("nodes", item(n), (0,)) for n in nodes], lambda k: None,
                                   max_bytes, budget_tokens)
        page = taken.get("nodes", [])
        delivered = {i["ref"] for i in page}
        if len(page) < len(nodes):  # an edge to a node that did not fit is dropped too
            shown = delivered | {ref}
            envelope["truncated"] = True
            envelope["edges"] = [e for e in envelope["edges"] if e["src"] in shown and e["dst"] in shown]
        _log(conn, actor, "neighbours", final, ([root] if root else []) + [n for n in nodes if n.ref in delivered], w)
        return {**envelope, "nodes": page}
    raise SearchChanged("authorization changed during the query; retry")


def _links(conn, frontier, passage, direction: str, types, w: int) -> list:
    """Links at w from the frontier notes (or into a passage root), in link seq order."""
    if passage is not None:
        return [(r[0], r[1], r[2], None, passage.handle) for r in conn.execute(
            "SELECT seq, src, type FROM note_link WHERE seq <= %s AND dst_book = %s AND dst_content_id = %s "
            "AND dst_profile_id = %s AND dst_path = %s AND dst_ordinal = %s AND type IN ('about', 'derived_from') "
            "AND (%s::text[] IS NULL OR type = ANY(%s::text[])) AND %s <> 'out' ORDER BY seq",
            (w, passage.book, passage.content_id, passage.profile_id, passage.path, passage.ordinal, types, types,
             direction))]
    if not frontier:
        return []
    out_ = direction in ("out", "both")
    in_ = direction in ("in", "both")
    rows = conn.execute(
        "SELECT seq, src, type, dst_note FROM note_link WHERE seq <= %(w)s AND dst_note IS NOT NULL "
        "AND (%(t)s::text[] IS NULL OR type = ANY(%(t)s::text[])) "
        "AND ((%(o)s AND src = ANY(%(f)s)) OR (%(i)s AND dst_note = ANY(%(f)s))) ORDER BY seq",
        {"w": w, "t": types, "o": out_, "i": in_, "f": list(frontier)}).fetchall()
    return [(r[0], r[1], r[2], r[3], None) for r in rows]


# --- notes in open_citation (§9.4) --------------------------------------------------------------------------

def open_note(conn, actor: Actor, *, for_model: bool, ref: str, repo=None, branch=None, path=None,
              commit=None, attempts: int = 2) -> dict:
    """One note with its full text (the `ai_input` gate applies) and any Standing, `current` from the shared
    predicate. The gates of `query_notes`: citations, link counts and the successor come from the whole read set,
    which is decided again at the end; a lost book runs it all again once, then `SearchChanged`."""
    book, note_id = notes.parse_ref(ref)
    ctx = Context(repo, branch, path, commit)
    obj = f"book:{book}"
    first = authz.decide(conn, actor.principal, actor.on_behalf_of, obj, ["read"])
    if not first.allowed:
        gate.log_event(conn, actor, "cite", obj, "read", first.decisions["read"], first.policy_id, None, None)
        raise gate.Denied(f"read on {obj}: {first.decisions['read'].reason}")
    w = watermark(conn)
    row = conn.execute("SELECT seq FROM note WHERE book = %s AND id = %s AND seq <= %s", (book, note_id, w)).fetchone()
    if row is None:
        raise gate.NotFound(ref)
    for _ in range(attempts):
        pre = _read(conn, actor)
        read = pre.objects("read")
        targets = _targets(conn, [book], ctx)
        note = _load(conn, [book], w, ctx, seqs=[row[0]])[0]
        _citations(conn, [note], read, targets)
        _verify(coderepo.Verifier(conn, targets), [note])
        graph = _graph(conn, [note.seq], read, w)
        recurrence, _ = _recurrence(conn, [note], w)
        item = _item(note, current(note, ctx, w) is None, recurrence.get(note.seq, 0), graph, for_model)
        final = _read(conn, actor)
        if obj not in final.objects("read"):
            gate.log_event(conn, actor, "cite", obj, "read", authz.Decision(False, "no current right"),
                           final.policies.get(obj), None, None, reason="revoked before delivery: no current right")
            raise gate.Denied(f"read on {obj}: revoked before delivery")
        if _lost(conn, actor, "cite", pre, final):
            continue  # link counts and the successor again, with the rights as they are now
        gate.log_event(conn, actor, "cite", obj, "read", final.decisions[obj]["read"], final.policies.get(obj),
                       None, None, items=[{"ref": note.ref, "standing_seq": note.standing_seq}], memory_seq=w)
        return {"citation": note.ref, "note": item, "targets": _targets_out(targets), "watermark": w}
    raise SearchChanged("authorization changed during the query; retry")


_QUERY, _NEIGHBOURS = query_notes, neighbours
_PARAMS = {f: frozenset(inspect.signature(f).parameters) for f in (_QUERY, _NEIGHBOURS)}


def is_note_ref(handle) -> bool:
    try:
        notes.parse_ref(handle)
    except ValueError:
        return False
    return True


# --- MCP tools and HTTP routes ---------------------------------------------------------------------------

def _for_model(actor: Actor, model_reader: bool) -> bool:
    return model_reader or actor.principal.startswith("agent:")  # the rule of server._for_model


def register_mcp(mcp, deps) -> None:
    from starlette.concurrency import run_in_threadpool

    from . import db

    def run(fn, **kw):
        actor = deps.mcp_actor()
        with db.connect(deps.dsn) as conn:
            return fn(conn, actor, for_model=_for_model(actor, True), **kw)

    @mcp.tool()
    @deps.mcp_errors
    async def query_notes(book: list[str] | None = None, sets: list[str] = ["current"],  # noqa: B006
                          kind: list[str] | None = None, role: list[str] | None = None,
                          origin: list[str] | None = None, class_key: str | None = None, repo: str | None = None,
                          branch: str | None = None, path: str | None = None, commit: str | None = None,
                          commits: str | None = None, written_after: str | None = None,
                          written_before: str | None = None, since: int | None = None, text: str | None = None,
                          unfixed: bool = False, collapse: bool = False, include_unverified: bool = False,
                          order: str = "newest", budget_tokens: int = 2000, max_bytes: int = 32768,
                          as_of: int | None = None, cursor: str | None = None) -> dict:
        """List agent notes in the journals you may read: fast SQL filters, no model call. `sets`: current
        (approved, in your context), open (pending, not accepted), history. Context: repo, branch, path, commit.
        Use `since` with the last watermark to get changes and `left` tombstones; `cursor` for the next page."""
        args = {k: v for k, v in locals().items() if k in _PARAMS[_QUERY]}  # the tool arguments
        return await run_in_threadpool(lambda: run(_QUERY, **args))

    @mcp.tool()
    @deps.mcp_errors
    async def neighbours(ref: str, types: list[str] | None = None, depth: int = 1, direction: str = "both",
                         sets: list[str] = ["current"], repo: str | None = None,  # noqa: B006
                         branch: str | None = None, path: str | None = None, commit: str | None = None,
                         max_nodes: int = 50, budget_tokens: int = 2000, max_bytes: int = 32768,
                         as_of: int | None = None) -> dict:
        """The notes linked to a note reference or a passage handle (depth 1 or 2), only those you may read and
        that are in `sets` in your context."""
        args = {k: v for k, v in locals().items() if k in _PARAMS[_NEIGHBOURS]}
        return await run_in_threadpool(lambda: run(_NEIGHBOURS, **args))


def _query_args(p) -> dict:
    """GET /v1/notes query string -> query_notes arguments (list parameters repeat)."""
    def flag(name):
        value = p.get(name)
        if value in (None, "false", "0"):
            return False
        if value in ("true", "1"):
            return True
        raise ValueError(f"{name} must be true or false")

    def number(name, default=None):
        value = p.get(name)
        if value is None:
            return default
        try:
            return int(value)
        except ValueError:
            raise ValueError(f"{name} must be an integer") from None

    def many(name, default=None):
        return p.getlist(name) or default
    return {"book": many("book"), "sets": many("sets", ["current"]), "kind": many("kind"), "role": many("role"),
            "origin": many("origin"), "class_key": p.get("class_key"), "repo": p.get("repo"),
            "branch": p.get("branch"), "path": p.get("path"), "commit": p.get("commit"), "commits": p.get("commits"),
            "written_after": p.get("written_after"), "written_before": p.get("written_before"),
            "since": number("since"), "text": p.get("text"), "unfixed": flag("unfixed"),
            "collapse": flag("collapse"), "include_unverified": flag("include_unverified"),
            "order": p.get("order", "newest"), "budget_tokens": number("budget_tokens", 2000),
            "max_bytes": number("max_bytes", 32768), "as_of": number("as_of"), "cursor": p.get("cursor")}


def http_routes(deps, endpoint) -> list:
    from starlette.concurrency import run_in_threadpool
    from starlette.responses import Response
    from starlette.routing import Route

    from . import db

    def respond(actor, fn, **kw):
        def go():
            with db.connect(deps.dsn) as conn:
                return fn(conn, actor, for_model=_for_model(actor, False), **kw)
        return go

    async def h_notes(request, actor):
        body = await run_in_threadpool(respond(actor, query_notes, **_query_args(request.query_params)))
        # the correlation id goes in a header, so the body stays byte-identical for the same request (§9.1)
        return Response(_dumps(body), media_type="application/json",
                        headers={"X-Correlation-Id": actor.correlation_id})

    async def h_neighbours(request, actor):
        p, q = request.path_params, request.query_params
        args = _query_args(q)
        try:
            extra = {k: int(q[k]) for k in ("depth", "max_nodes") if k in q}
        except ValueError:
            raise ValueError("depth and max_nodes must be integers") from None
        body = await run_in_threadpool(respond(
            actor, neighbours, ref=f"{p['book']}@{p['id']}", types=q.getlist("types") or None,
            direction=q.get("direction", "both"), sets=args["sets"], repo=args["repo"], branch=args["branch"],
            path=args["path"], commit=args["commit"], budget_tokens=args["budget_tokens"],
            max_bytes=args["max_bytes"], as_of=args["as_of"], **extra))
        return Response(_dumps(body), media_type="application/json",
                        headers={"X-Correlation-Id": actor.correlation_id})

    return [Route("/v1/notes", endpoint(h_notes), methods=["GET"]),  # POST /v1/notes is the write path's route
            Route("/v1/notes/{book}/{id}/neighbours", endpoint(h_neighbours), methods=["GET"])]
