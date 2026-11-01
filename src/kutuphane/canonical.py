"""The canonical body of a stored note (docs/24 §3), computed again from every stored part: what a person sees and
signs (docs/25 §5.2). The note id is `nt_` + the SHA-256 of this body, so a confirmation (`origin_confirmation
.note_id`) or an approval (the `ref` of a signed `standing` item) is of exactly these parts.

Since migration 039 the database writes a citation or a creation link only in the transaction of its note, so the
parts cannot change after a person signed them (Astra review #19 finding 2). The readers still compare (defense in
depth, and rows written before 039): a shown origin and an approval count only while the parts give the signed id.
"""
from . import ids
from .gate import NotFound

_PARTS = """
SELECT n.seq, n.id, n.kind, n.body, n.class_key, n.scope_repo, n.scope_branch, n.scope_paths, n.observed_commit,
       n.options, n.choice,
       ARRAY(SELECT CASE c.kind
                      WHEN 'passage' THEN c.cite_book || '@' || c.content_id || '/' || c.profile_id || '/' || c.path
                                          || '#' || c.ordinal
                      ELSE c.repo || '@' || c.commit || ':' || c.path || ':' || c.line_start || '-' || c.line_end
                           || coalesce('#' || c.symbol, '') END
               FROM note_citation c WHERE c.note_seq = n.seq ORDER BY c.n),
       ARRAY(SELECT jsonb_build_object('type', l.type, 'target', CASE WHEN l.dst_note IS NOT NULL
                 THEN l.dst_note_book || '@' || d.id
                 ELSE l.dst_book || '@' || l.dst_content_id || '/' || l.dst_profile_id || '/' || l.dst_path || '#'
                      || l.dst_ordinal END)
               FROM note_link l LEFT JOIN note d ON d.seq = l.dst_note WHERE l.src = n.seq AND l.creation),
       n.applies_to
  FROM note n WHERE n.seq = ANY(%s)
"""


def _computed(row) -> tuple[str, dict]:
    kind, text, class_key, repo, branch, paths, commit, options, choice, cited, links, applies_to = row
    body = {"v": 1, "kind": kind, "text": text, "class_key": class_key,
            "scope": None if repo is None else {"repo": repo, "branch": branch, "paths": list(paths)},
            "commit": commit, "citations": list(cited),
            "links": sorted(links, key=lambda link: (link["type"], link["target"]))}
    if options is not None:
        body["decision"] = {"options": list(options), "choice": choice}
    if applies_to is not None:
        body["applies_to"] = applies_to
    return "nt_" + ids.sha256_hex(ids.canonical(body)), body


def canonical_of(conn, note_seq: int) -> tuple[str, dict]:
    """(id, body) of the note's stored parts. A caller compares this id with the stored or the signed one."""
    row = conn.execute(_PARTS, ([note_seq],)).fetchone()
    if row is None:
        raise NotFound(f"no such note: {note_seq}")
    return _computed(row[2:])


def intact(conn, seqs) -> set[int]:
    """The notes among `seqs` whose stored parts give their stored id (one statement)."""
    seqs = sorted(set(seqs))
    if not seqs:
        return set()
    return {row[0] for row in conn.execute(_PARTS, (seqs,)) if _computed(row[2:])[0] == row[1]}
