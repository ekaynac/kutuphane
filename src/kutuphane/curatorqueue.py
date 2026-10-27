"""The curator queue and its measures (docs/25 §6; #77; slice Q).

**The queue** is a function of the memory rows with `seq <= w` and of the person's books now (direct `curate` and
`read`): the same `w` and the same rights give the same bytes. A book-local `same_as` cluster with a pending note is
one group. Groups go by (tier, oldest pending seq), members by seq (§6.2). A group shows every member, pending or not,
with its Standing at `w`. Linked and cited content in a book that the person cannot read now shows no book name and no
text (§6.1). Each page is one `access_event` per book (action `curate_view`, items `{ref, standing_seq}`, memory_seq
`w`), so the #79 report lists who saw a note.

**Suggestions** (`note_suggestion`, migration 025) and sample membership (`delegation_use.sampled`) are never read for
the order and never put into a queue or note response (D67, D43, D44). Only `receipt` reads them, after the act.

**The report** (`report`) gives the measures of §6.7: curator seconds per approved note, the share still pending
after 7 days, who decided, and the live agreement of each delegation (§8.7).
"""
import base64
import binascii
import json
import statistics
from datetime import datetime, timedelta

from . import authz, gate, notes, notesquery, origin, outcomes

PAGE_GROUPS = 20
MAX_PAGE_GROUPS = 100
PENDING_DAYS = 7
UNREADABLE_PASSAGE = "a passage in a book you cannot read"
UNREADABLE_NOTE = "a note in a book you cannot read"
TIER_OF_KIND = {"decision_proposal": 2, "convention": 3, "finding": 4, "lesson": 5, "dead_end": 5, "test_result": 6}
WHY = {2: "a decision proposal: a rule", 3: "a convention: a rule", 4: "a finding: evidence",
       5: "a lesson or a dead end: evidence", 6: "a test result: history, never current"}
WHY_SUPERSEDES = "its approval retires an approved rule of the same scope"
WHY_CONTRADICTS = "it contradicts an approved note"


# --- rights and the watermark ------------------------------------------------------------------------------------

def books(conn, principal: str) -> tuple[list[str], list[str], authz.Allowed]:
    """(the books with direct `curate` and `read` now, the books with `curate` but no `read`, the decisions).
    `curate` is never delegated, so the person's own rights decide (no on_behalf_of)."""
    rights = authz.allowed(conn, principal, None, ["curate", "read"])
    curate, read = rights.objects("curate"), rights.objects("read")
    return (sorted(o.removeprefix("book:") for o in curate & read),
            sorted(o.removeprefix("book:") for o in curate - read), rights)


def watermark(conn) -> int:
    """The highest memory seq that the queue reads: notes, writes, links, Standing, outcomes and the R3 rows."""
    return max(notesquery.watermark(conn), conn.execute(
        "SELECT greatest((SELECT max(seq) FROM origin_confirmation), (SELECT max(seq) FROM origin_withdrawal), 0)"
    ).fetchone()[0])


def _cursor(w: int, key: tuple) -> str:
    return base64.urlsafe_b64encode(json.dumps([w, *key]).encode()).decode().rstrip("=")


def _uncursor(text: str) -> tuple[int, tuple]:
    try:
        value = json.loads(base64.urlsafe_b64decode(text + "=" * (-len(text) % 4)))
    except (ValueError, binascii.Error):
        raise ValueError("malformed cursor") from None
    if not (isinstance(value, list) and len(value) == 3 and all(type(v) is int for v in value)):
        raise ValueError("malformed cursor")
    return value[0], (value[1], value[2])


def _at(conn, w, cursor) -> tuple[int, tuple | None]:
    now = watermark(conn)
    after = None
    if cursor is not None:
        cw, after = _uncursor(cursor)
        if w is not None and w != cw:
            raise ValueError("the cursor belongs to another w")
        w = cw
    if w is None:
        return now, after
    if type(w) is not int or not 0 <= w <= now:
        raise ValueError(f"w must be an integer in 0..{now}")
    return w, after


# --- the risk order (§6.2) ---------------------------------------------------------------------------------------

def tiers(conn, rows: dict, w: int) -> dict:
    """{seq: (tier, why)} for `rows` = {seq: (kind, scope)}. Tier 1: a rule-role note with a creation `supersedes`
    link to a note approved at `w` with the same scope, or any note in a `contradicts` link to a note approved at
    `w`. Else the tier of its kind. The reason never names the other note (it may be in an unreadable book)."""
    seqs = list(rows)
    links = conn.execute(
        "SELECT l.src, l.type, l.dst_note, d.scope_repo, d.scope_branch, d.scope_paths FROM note_link l "
        "JOIN note d ON d.seq = l.dst_note WHERE l.seq <= %(w)s AND l.src = ANY(%(s)s) "
        "AND ((l.type = 'supersedes' AND l.creation) OR l.type = 'contradicts') "
        "UNION ALL SELECT l.dst_note, l.type, l.src, NULL, NULL, NULL FROM note_link l "
        "WHERE l.seq <= %(w)s AND l.type = 'contradicts' AND l.dst_note = ANY(%(s)s)", {"w": w, "s": seqs}).fetchall()
    standing = notes.effective_standing(conn, {r[2] for r in links}, w)
    out = {s: (TIER_OF_KIND[kind], WHY[TIER_OF_KIND[kind]]) for s, (kind, _scope) in rows.items()}
    for src, type_, dst, repo, branch, paths in links:
        if standing[dst][0] != "approved":
            continue
        kind, scope = rows[src]
        if type_ == "contradicts":
            out[src] = (1, WHY_CONTRADICTS)
        elif notes.KIND_ROLE[kind] == "rule" and scope == (repo, branch, sorted(paths or [])) and \
                out[src][1] != WHY_CONTRADICTS:
            out[src] = (1, WHY_SUPERSEDES)
    return out


_PENDING = """
SELECT n.seq FROM note n
  LEFT JOIN LATERAL (SELECT value FROM standing_event e WHERE e.note_seq = n.seq AND e.seq <= %(w)s
                      ORDER BY e.seq DESC LIMIT 1) e ON true
 WHERE n.book = ANY(%(books)s) AND n.seq <= %(w)s AND coalesce(e.value, 'pending') = 'pending'
"""

_ROWS = """
SELECT seq, book, id, kind, body, class_key, scope_repo, scope_branch, scope_paths, observed_commit, options, choice,
       written_at
  FROM note WHERE seq = ANY(%s)
"""


def _rows(conn, seqs) -> dict:
    return {r[0]: r for r in conn.execute(_ROWS, (list(seqs),)).fetchall()}


def _scope(row) -> tuple:
    return row[6], row[7], sorted(row[8] or [])


def _groups(conn, book_list: list[str], w: int) -> tuple[list[dict], dict]:
    """Every group with a pending note at w, in queue order: [{key, tier, why, pending, members}], and the note
    rows of every member."""
    pending = [s for (s,) in conn.execute(_PENDING, {"w": w, "books": book_list}).fetchall()]
    if not pending:
        return [], {}
    components = notes._components(conn, pending, w)
    rows = _rows(conn, {m for members in components.values() for m in members})
    tier = tiers(conn, {s: (rows[s][3], _scope(rows[s])) for s in pending}, w)
    groups = {}
    for s in sorted(pending):
        members = components[s]
        g = groups.setdefault(members[0], {"members": members, "pending": []})
        g["pending"].append(s)
    out = []
    for g in groups.values():
        best = min((tier[s][0], s) for s in g["pending"])
        out.append({"key": (best[0], g["pending"][0]), "tier": best[0], "why": tier[best[1]][1],
                    "pending": g["pending"], "members": g["members"], "tiers": {s: tier[s] for s in g["pending"]}})
    out.sort(key=lambda g: g["key"])
    return out, rows


# --- what each item shows (§6.2, §6.3, §6.6) ---------------------------------------------------------------------

def _writers(conn, seqs, w: int) -> dict:
    out = {}
    for seq, principal, behalf, client in conn.execute(
            "SELECT note_seq, principal, on_behalf_of, client_id FROM write_record WHERE action = 'propose' "
            "AND note_seq = ANY(%s) AND seq <= %s ORDER BY seq", (list(seqs), w)):
        writer = {"principal": principal, "on_behalf_of": behalf, "client_id": client}
        if writer not in out.setdefault(seq, []):
            out[seq].append(writer)
    return out


def _cluster_counts(conn, members: list[int], w: int) -> tuple[int, int]:
    """(recurrence: the propose writes over the cluster, proposed again after rejection: the propose writes over the
    cluster after its first `rejected` event), both with seq <= w (docs/24 §6.1, §7)."""
    return conn.execute(
        "WITH r AS (SELECT min(seq) AS first FROM standing_event WHERE note_seq = ANY(%(m)s) AND seq <= %(w)s "
        "           AND value = 'rejected') "
        "SELECT count(*), count(*) FILTER (WHERE w.seq > r.first) FROM write_record w, r "
        "WHERE w.action = 'propose' AND w.note_seq = ANY(%(m)s) AND w.seq <= %(w)s", {"m": members, "w": w}).fetchone()


def _handle(book, content_id, profile_id, path, ordinal) -> str:
    return f"{book}@{content_id}/{profile_id}/{path}#{ordinal}"


def _citations(conn, seqs, readable: set) -> dict:
    out = {}
    for seq, kind, book, cid, pid, path, ordinal, repo, commit, start, end, symbol in conn.execute(
            "SELECT note_seq, kind, cite_book, content_id, profile_id, path, ordinal, repo, commit, line_start, "
            "line_end, symbol FROM note_citation WHERE note_seq = ANY(%s) ORDER BY note_seq, n", (list(seqs),)):
        if kind == "code":
            ref = f"{repo}@{commit}:{path}:{start}-{end}" + (f"#{symbol}" if symbol else "")
            out.setdefault(seq, []).append({"kind": "code", "ref": ref})
        elif book in readable:
            out.setdefault(seq, []).append({"kind": "passage", "ref": _handle(book, cid, pid, path, ordinal)})
        else:
            out.setdefault(seq, []).append({"kind": "passage", "hidden": UNREADABLE_PASSAGE})
    return out


def _passage_texts(conn, keys) -> dict:
    """{(book, content_id, profile_id, path, ordinal): text} of passages."""
    keys = sorted(set(keys))
    if not keys:
        return {}
    return {tuple(r[:5]): r[5] for r in conn.execute(
        "SELECT c.book, c.content_id, c.profile_id, c.path, c.ordinal, c.text FROM chunk c "
        "JOIN unnest(%s::text[], %s::text[], %s::text[], %s::text[], %s::int[]) AS k(b, ci, pi, p, o) "
        "ON c.book = k.b AND c.content_id = k.ci AND c.profile_id = k.pi AND c.path = k.p AND c.ordinal = k.o",
        [list(col) for col in zip(*keys)]).fetchall()}


def _links(conn, seqs, readable: set, w: int) -> dict:
    """Every link of the notes at w, out and in, in link seq order, with the target's text (a note or a passage):
    the creation links are part of what the person approves (review #16 finding 1). A target in a book that the
    person cannot read now is only "a note (passage) in a book you cannot read"."""
    rows = conn.execute(
        "SELECT l.seq, l.src, l.type, l.creation, l.dst_note, l.dst_book, l.dst_content_id, l.dst_profile_id, "
        "l.dst_path, l.dst_ordinal FROM note_link l WHERE l.seq <= %(w)s "
        "AND (l.src = ANY(%(s)s) OR l.dst_note = ANY(%(s)s)) ORDER BY l.seq", {"w": w, "s": list(seqs)}).fetchall()
    others = {r[4] for r in rows if r[4] is not None} | {r[1] for r in rows}
    info = {r[0]: r for r in conn.execute("SELECT seq, book, id, kind, body FROM note WHERE seq = ANY(%s)",
                                          (list(others),)).fetchall()}
    standing = notes.effective_standing(conn, others, w)
    passages = _passage_texts(conn, [tuple(r[5:]) for r in rows if r[4] is None and r[5] in readable])
    out = {}
    for _lseq, src, type_, creation, dst, dbook, cid, pid, path, ordinal in rows:
        for this, other, direction in ((src, dst, "out"), (dst, src, "in")):
            if this not in seqs or (direction == "in" and dst is None):
                continue
            link = {"type": type_, "direction": direction, "creation": creation}
            if other is None:  # a passage target
                link.update({"ref": _handle(dbook, cid, pid, path, ordinal),
                             "text": passages.get((dbook, cid, pid, path, ordinal))} if dbook in readable
                            else {"hidden": UNREADABLE_PASSAGE})
            elif info[other][1] in readable:
                _s, obook, oid, okind, text = info[other]
                link.update({"ref": f"{obook}@{oid}", "kind": okind, "standing": standing[other][0], "text": text})
            else:
                link["hidden"] = UNREADABLE_NOTE
            out.setdefault(this, []).append(link)
    return out


def _hidden_parts(citations: list[dict], links: list[dict]) -> int:
    """The parts of a note that its id covers (citations, its own creation links) and that the person cannot see."""
    return sum("hidden" in c for c in citations) + \
        sum("hidden" in link for link in links if link["creation"] and link["direction"] == "out")


def unseen_parts(conn, principal: str, seq: int) -> int:
    """`_hidden_parts` of one note now, for the act options: an approval needs every part shown (review #16)."""
    readable = {o.removeprefix("book:") for o in authz.allowed(conn, principal, None, ["read"]).objects("read")}
    return conn.execute(
        "SELECT (SELECT count(*) FROM note_citation WHERE note_seq = %(s)s AND kind = 'passage' "
        "        AND NOT cite_book = ANY(%(r)s)) "
        "     + (SELECT count(*) FROM note_link WHERE src = %(s)s AND creation "
        "        AND NOT coalesce(dst_note_book, dst_book) = ANY(%(r)s))", {"s": seq, "r": sorted(readable)}).fetchone()[0]


def _items(conn, seqs: list[int], rows: dict, w: int, readable: set, tier: dict) -> dict:
    """{seq: item}. Keys in a fixed order (the same w and rights give the same bytes). No suggestion, no sample."""
    standing = notes.effective_standing(conn, seqs, w)
    writers = _writers(conn, seqs, w)
    shown = origin.shown(conn, seqs, w)
    counted = outcomes.counts(conn, seqs, w)
    cites = _citations(conn, seqs, readable)
    links = _links(conn, seqs, readable, w)
    out = {}
    for s in seqs:
        seq, book, note_id, kind, text, class_key, repo, branch, paths, commit, options, choice, written = rows[s]
        value, event = standing[s]
        shown_origin, entered_by, confirmed_by = shown.get(s, (None, None, None))
        item = {"ref": f"{book}@{note_id}", "book": book, "kind": kind, "role": notes.KIND_ROLE[kind],
                "standing": value, "was": event, "pending": value == "pending",
                "why": tier[s][1] if s in tier else None, "text": text, "class_key": class_key,
                "scope": {"repo": repo, "branch": branch, "paths": list(paths)} if repo else None,
                "commit": commit,
                "decision": {"options": list(options), "choice": choice} if options is not None else None,
                "written_at": notesquery._iso(written), "writers": writers.get(s, []), "origin": shown_origin,
                "entered_by": entered_by, "confirmed_by": confirmed_by, "outcomes": counted.get(s, {}),
                "citations": cites.get(s, []), "links": links.get(s, []),
                "hidden_parts": _hidden_parts(cites.get(s, []), links.get(s, [])),
                "integrity": None if notes.canonical_of(conn, s)[0] == note_id else "note-integrity"}
        out[s] = item
    return out


def _pairs(conn, members: list[int], w: int, refs: dict) -> list[list[str]]:
    """The members joined by `contradicts` (marked as a pair on the card; never approved in one act)."""
    return [[refs[a], refs[b]] for a, b in conn.execute(
        "SELECT src, dst_note FROM note_link WHERE type = 'contradicts' AND seq <= %(w)s AND src = ANY(%(m)s) "
        "AND dst_note = ANY(%(m)s) ORDER BY seq", {"w": w, "m": members}).fetchall()]


def _log(conn, principal: str, rights: authz.Allowed, items: list[dict], w: int, channel: str) -> None:
    """One access_event per book with shown notes (action `curate_view`, items `{ref, standing_seq}`, w)."""
    actor = gate.Actor(principal, channel=channel)
    by_book = {}
    for i in items:
        by_book.setdefault(i["book"], {})[i["ref"]] = i["was"]
    for book in sorted(by_book):
        obj = f"book:{book}"
        gate.log_event(conn, actor, "curate_view", obj, "curate", rights.decisions[obj]["curate"],
                       rights.policies.get(obj), None, None,
                       items=[{"ref": r, "standing_seq": s} for r, s in by_book[book].items()], memory_seq=w)


def queue(conn, principal: str, *, w: int | None = None, cursor: str | None = None, limit: int = PAGE_GROUPS,
          book: str | None = None, channel: str = "cli") -> dict:
    """One page of the queue at `w` (default: now). `cursor` continues a page at its own `w`. `book` narrows it to one
    of the person's books. The caller commits (the view is logged)."""
    if type(limit) is not int or not 1 <= limit <= MAX_PAGE_GROUPS:
        raise ValueError(f"limit must be an integer in 1..{MAX_PAGE_GROUPS}")
    w, after = _at(conn, w, cursor)
    book_list, read_needed, rights = books(conn, principal)
    if book is not None:
        if book not in book_list:
            raise gate.Denied(f"{principal} does not hold curate and read on book:{book}")
        book_list = [book]
    groups, rows = _groups(conn, book_list, w)
    total = sum(len(g["pending"]) for g in groups)
    todo = [g for g in groups if after is None or g["key"] > after]
    page, rest = todo[:limit], todo[limit:]
    readable = {o.removeprefix("book:") for o in rights.objects("read")}
    seqs = [m for g in page for m in g["members"]]
    tier = {s: t for g in page for s, t in g["tiers"].items()}
    items = _items(conn, seqs, rows, w, readable, tier) if seqs else {}
    out_groups = []
    for g in page:
        recurrence, again = _cluster_counts(conn, g["members"], w)
        refs = {m: items[m]["ref"] for m in g["members"]}
        out_groups.append({"tier": g["tier"], "why": g["why"], "pending": len(g["pending"]),
                           "recurrence": recurrence, "proposed_again_after_rejection": again,
                           "pairs": _pairs(conn, g["members"], w, refs),
                           "members": [items[m] for m in g["members"]]})
    _log(conn, principal, rights, list(items.values()), w, channel)
    return {"watermark": w, "books": book_list, "read_needed": read_needed, "pending": total,
            "groups": out_groups, "next_cursor": _cursor(w, page[-1]["key"]) if rest else None}


def note(conn, principal: str, ref: str, *, w: int | None = None, channel: str = "cli") -> dict:
    """One note at `w` with its group and the text of every readable cited or linked passage (§10.1)."""
    w, _ = _at(conn, w, None)
    book, note_id = notes.parse_ref(ref)
    book_list, _, rights = books(conn, principal)
    if book not in book_list:
        raise gate.Denied(f"{principal} does not hold curate and read on book:{book}")
    found = conn.execute("SELECT seq, kind, scope_repo, scope_branch, scope_paths FROM note "
                         "WHERE book = %s AND id = %s AND seq <= %s", (book, note_id, w)).fetchone()
    if found is None:
        raise gate.NotFound(f"no such note: {ref}")
    seq = found[0]
    members = notes._components(conn, [seq], w)[seq]
    rows = _rows(conn, members)
    readable = {o.removeprefix("book:") for o in rights.objects("read")}
    standing = notes.effective_standing(conn, members, w)
    pending = {s: (rows[s][3], _scope(rows[s])) for s in members if standing[s][0] == "pending"}
    items = _items(conn, members, rows, w, readable, tiers(conn, pending, w) if pending else {})
    handles = [c["ref"] for c in items[seq]["citations"] if c["kind"] == "passage" and "ref" in c] + \
              [link["ref"] for link in items[seq]["links"] if "ref" in link and "kind" not in link]
    passages = []
    for handle in dict.fromkeys(handles):
        c = notes.parse_passage(handle)
        text = conn.execute("SELECT text FROM chunk WHERE book = %s AND content_id = %s AND profile_id = %s "
                            "AND path = %s AND ordinal = %s",
                            (c.book, c.content_id, c.profile_id, c.path, c.ordinal)).fetchone()
        passages.append({"ref": handle, "text": text[0] if text else None})
    recurrence, again = _cluster_counts(conn, members, w)
    _log(conn, principal, rights, [items[seq]], w, channel)
    return {"watermark": w, "item": items[seq], "group": [items[m]["ref"] for m in members],
            "recurrence": recurrence, "proposed_again_after_rejection": again,
            "pairs": _pairs(conn, members, w, {m: items[m]["ref"] for m in members}), "passages": passages}


# --- after the act (§5.4 step 8, §6.4, §8.4) ---------------------------------------------------------------------

def receipt(conn, items: list[dict]) -> list[dict]:
    """The act's items with, for each note, the suggestions written before its event ("agrees" or "differs" with the
    person's value; `abstain` neither) and, for a sample of a delegation, that delegation. Read only after the act."""
    out = []
    for item in items:
        book, note_id = notes.parse_ref(item["ref"])
        seq = conn.execute("SELECT seq FROM note WHERE book = %s AND id = %s", (book, note_id)).fetchone()[0]
        suggestions = [{"decider": d, "value": v, "confidence": round(float(c), 4),
                        "agrees": None if v == "abstain" else v == item["standing"]}
                       for d, v, c in conn.execute(
                           "SELECT decider, value, confidence FROM note_suggestion WHERE note_seq = %s AND seq < %s "
                           "ORDER BY seq", (seq, item["event_seq"])).fetchall()]
        sample = conn.execute("SELECT delegation FROM delegation_use WHERE note_seq = %s AND sampled",
                              (seq,)).fetchone()
        out.append({**item, "suggestions": suggestions, "sample": sample[0] if sample else None})
    return out


# --- the measures (§6.7) -----------------------------------------------------------------------------------------

def _median(values) -> float | None:
    return round(statistics.median(values), 3) if values else None


def _share(part: int, whole: int) -> float | None:
    return round(part / whole, 4) if whole else None


def _seconds(conn, start: datetime, end: datetime) -> dict:
    acts = conn.execute(
        "SELECT a.seq, a.shown_ms, a.backup_state, count(e.seq), count(e.seq) FILTER (WHERE e.value = 'approved') "
        "FROM curator_act a LEFT JOIN standing_event e ON e.act = a.seq "
        "WHERE a.action = 'standing' AND a.at >= %s AND a.at < %s GROUP BY a.seq ORDER BY a.seq",
        (start, end)).fetchall()
    timed = [(ms, n, approved) for _seq, ms, _bs, n, approved in acts if ms is not None and n]
    approving = [(ms, approved) for ms, _n, approved in timed if approved]
    approved_notes = sum(a for _ms, a in approving)
    return {"acts": len(acts), "acts_without_time": sum(1 for a in acts if a[1] is None),
            "acts_by_synced_passkey": sum(1 for a in acts if a[2]),
            "approved_notes": sum(a[4] for a in acts),
            "seconds_per_approved_note": round(sum(ms for ms, _a in approving) / 1000 / approved_notes, 3)
            if approved_notes else None,
            "median_seconds_per_act": _median([ms / 1000 for ms, _n, _a in timed]),
            "median_seconds_per_decided_note": _median([ms / 1000 / n for ms, n, _a in timed for _ in range(n)])}


def _pending_share(conn, start: datetime, end: datetime) -> dict:
    """Among the notes written in [start, end - 7 days] (and at least 7 days ago): the share with no Standing event
    at written_at + 7 days, by tier (the tier at the current watermark) and by book."""
    rows = conn.execute(
        "SELECT n.seq, n.book, n.kind, n.scope_repo, n.scope_branch, n.scope_paths, NOT EXISTS ("
        "  SELECT 1 FROM standing_event e WHERE e.note_seq = n.seq AND e.at <= n.written_at + %(d)s) "
        "FROM note n WHERE n.written_at >= %(s)s AND n.written_at <= %(e)s::timestamptz - %(d)s "
        "AND n.written_at + %(d)s <= clock_timestamp() ORDER BY n.seq",
        {"s": start, "e": end, "d": timedelta(days=PENDING_DAYS)}).fetchall()
    tier = tiers(conn, {r[0]: (r[2], (r[3], r[4], sorted(r[5] or []))) for r in rows}, notes.NOW) if rows else {}

    def part(key):
        counts = {}
        for r in rows:
            c = counts.setdefault(key(r), [0, 0])
            c[0] += 1
            c[1] += r[6]
        return {str(k): {"notes": n, "pending": p, "share": _share(p, n)} for k, (n, p) in sorted(counts.items())}
    waiting = sum(r[6] for r in rows)
    return {"notes": len(rows), "pending": waiting, "share": _share(waiting, len(rows)),
            "by_tier": part(lambda r: tier[r[0]][0]), "by_book": part(lambda r: r[1])}


def _decided_by(conn, start: datetime, end: datetime) -> dict:
    out = {"people_web": {}, "people_cli": {}, "delegations": {}, "system": {}}
    for who, value, n in conn.execute(
            "SELECT CASE WHEN act IS NOT NULL THEN 'people_web' WHEN set_by LIKE 'user:%%' THEN 'people_cli' "
            "WHEN set_by LIKE 'model:%%' THEN 'delegations' ELSE 'system' END, value, count(*) "
            "FROM standing_event WHERE at >= %s AND at < %s GROUP BY 1, 2 ORDER BY 1, 2", (start, end)):
        out[who][value] = n
    return out


_DELEGATIONS = """
SELECT d.id, d.book, d.kind, d.decider, d.created_by, d.created_at, d.expires_at, x.cause, x.at,
       count(u.seq) FILTER (WHERE u.at >= %(s)s AND u.at < %(e)s),
       count(u.seq) FILTER (WHERE u.at >= %(s)s AND u.at < %(e)s AND NOT u.sampled),
       count(u.seq) FILTER (WHERE u.at >= %(s)s AND u.at < %(e)s AND u.sampled AND f.set_by LIKE 'user:%%'
                            AND f.value = 'approved'),
       count(u.seq) FILTER (WHERE u.at >= %(s)s AND u.at < %(e)s AND u.sampled AND f.set_by LIKE 'user:%%'
                            AND f.value <> 'approved'),
       count(u.seq) FILTER (WHERE u.at >= %(s)s AND u.at < %(e)s AND u.sampled AND f.seq IS NULL),
       count(u.seq) FILTER (WHERE u.at >= %(s)s AND u.at < %(e)s AND u.sampled AND f.set_by = 'system')
  FROM curate_delegation d
  LEFT JOIN delegation_end x ON x.delegation = d.id
  LEFT JOIN delegation_use u ON u.delegation = d.id
  LEFT JOIN LATERAL (SELECT seq, set_by, value FROM standing_event e WHERE e.note_seq = u.note_seq
                      ORDER BY e.seq LIMIT 1) f ON true
 WHERE d.created_at < %(e)s AND (x.at IS NULL OR x.at >= %(s)s)
 GROUP BY d.id, x.cause, x.at ORDER BY d.created_at, d.id
"""

_CLASS = """
SELECT count(*),
       count(*) FILTER (WHERE EXISTS (SELECT 1 FROM standing_event e JOIN delegation_use u ON u.seq = e.delegation_use
                                       WHERE e.note_seq = n.seq AND u.delegation = %(id)s))
  FROM note n WHERE n.book = %(book)s AND n.kind = %(kind)s AND n.written_at >= %(s)s AND n.written_at < %(e)s
"""

_OUTCOMES = """
SELECT CASE WHEN a.set_by LIKE 'model:%%' THEN 'delegated' ELSE 'human' END, o.result, count(*)
  FROM note n
  JOIN LATERAL (SELECT value, set_by FROM standing_event e WHERE e.note_seq = n.seq ORDER BY e.seq DESC LIMIT 1) a
       ON a.value = 'approved'
  JOIN outcome o ON o.note_seq = n.seq
 WHERE n.book = %(book)s AND n.kind = %(kind)s AND (a.set_by LIKE 'model:%%' OR a.set_by LIKE 'user:%%')
 GROUP BY 1, 2 ORDER BY 1, 2
"""


def _delegations(conn, start: datetime, end: datetime) -> list[dict]:
    """§8.7 per delegation live in the period: its uses, the live agreement of its samples, the coverage of its
    class, and the outcome counts of delegated vs human approvals in force of the same class."""
    out = []
    for (did, book, kind, decider, by, created, expires, cause, ended, uses, approved, agreed, disagreed, open_,
         closed) in conn.execute(_DELEGATIONS, {"s": start, "e": end}).fetchall():
        written, covered = conn.execute(_CLASS, {"id": did, "book": book, "kind": kind, "s": start,
                                                 "e": end}).fetchone()
        compared = {"delegated": {}, "human": {}}
        for who, result, n in conn.execute(_OUTCOMES, {"book": book, "kind": kind}):
            compared[who][result] = n
        out.append({"id": did, "book": book, "kind": kind, "decider": decider, "created_by": by,
                    "created_at": notesquery._iso(created), "expires_at": notesquery._iso(expires),
                    "ended": {"cause": cause, "at": notesquery._iso(ended)} if cause else None,
                    "uses": uses, "approved": approved,
                    "samples": {"agreed": agreed, "disagreed": disagreed, "open": open_, "closed_no_verdict": closed},
                    "coverage": {"notes": written, "approved_by_delegation": covered,
                                 "share": _share(covered, written)},
                    "outcomes": compared})
    return out


def report(conn, start: datetime, end: datetime) -> dict:
    """`kutuphane curator report --from D1 --to D2` (§6.7): read only, owner credential. [start, end)."""
    if start.tzinfo is None or end.tzinfo is None or not start < end:
        raise ValueError("--from and --to must be times with a zone, and --from before --to")
    return {"from": notesquery._iso(start), "to": notesquery._iso(end),
            "curator_time": _seconds(conn, start, end),
            "pending_after_7_days": _pending_share(conn, start, end),
            "decided_by": _decided_by(conn, start, end),
            "delegations": _delegations(conn, start, end)}
