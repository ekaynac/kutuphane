"""Agent memory, the write core (docs/24 §3–§8, slice A): journals, notes, links, rights by derivation, duplicate
candidates, idempotency, Standing and supersession.

- A note is content-addressed: `nt_` + SHA-256 of its canonical body, creation links included (§3). The same bytes
  in one book are the same note; one more write record counts the recurrence. Only identical bytes are automatic: a
  normalized, vector or class match is a candidate, and an agent or a person decides with `link_notes` (§7).
- The server computes origin (`origin.py`). The rights of a note follow its derivation (§6.2): `search` and
  `ai_input` are the AND of the journal and every dependency; `source_books` is the union, for the egress check.
- No repository access and no model call happens before the pre-decision (§6.1 step 5). The writes run inside
  `gate.guard_many`: a right lost before the final decision rolls everything back.
- Standing has its own append-only event table. Curation is the CLI (`set_standing`, `rollback`), through the owner
  database credential, or a passkey act in curator web (docs/25; `curation.apply` holds the rules of both); no MCP
  tool and no HTTP route of Core changes Standing (§8.2, §20).
- Every memory write takes the advisory lock MEMORY_LOCK before its first `nextval('memory_seq')`, so `seq` order is
  commit order (§4).
"""
import hashlib
import os
import re
import unicodedata
import uuid
from typing import NotRequired, TypedDict

from psycopg.types.json import Jsonb
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from . import authz, db, gate, ids, kstd, llmdap, origin as origins, profiles, search, secretscan, vectors
from .gate import Actor, NotFound
from .policy import check_policy

KINDS = ("finding", "decision_proposal", "dead_end", "convention", "lesson", "test_result")
KIND_ROLE = {"decision_proposal": "rule", "convention": "rule", "finding": "evidence", "lesson": "evidence",
             "dead_end": "evidence", "test_result": "evidence"}
LINK_TYPES = ("derived_from", "same_as", "about", "fixed_by", "violates", "decided_by", "supersedes", "contradicts")
CREATION_ONLY = ("derived_from", "supersedes")  # they change rights and retirement: part of what a curator approves
PASSAGE_LINKS = ("derived_from", "about")
STANDINGS = ("approved", "pending", "rejected", "retired")
TRANSITIONS = {("pending", "approved"), ("pending", "rejected"), ("approved", "retired"), ("rejected", "pending"),
               ("retired", "pending")}  # §8.2; a re-proposal never reopens a note
MAX_CITATIONS = MAX_LINKS = MAX_PATHS = MAX_OPTIONS = 20
OPTION_CHARS = 500
CANDIDATE_CHARS = 300
CANDIDATES_PER_MATCH = 5
WRITES_ENV, WRITES_DEFAULT = "KUTUPHANE_NOTE_WRITES_PER_DAY", 500
SIMILARITY_ENV, SIMILARITY_DEFAULT = "KUTUPHANE_NOTE_DUP_SIMILARITY", 0.90
MEMORY_LOCK = 0x6B75747570  # pg_advisory_xact_lock key of every memory write
NOW = 2 ** 63 - 1  # a watermark above every seq: "the rows committed now"
WITHHELD = "rights do not allow AI input"

BOOK = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}\Z")
REF = re.compile(r"^([a-z0-9][a-z0-9-]{0,62})@(nt_[0-9a-f]{64})\Z")
REPO = re.compile(r"^[a-z0-9][a-z0-9._-]{0,62}\Z")
CLASS_KEY = re.compile(r"^[a-z0-9][a-z0-9._:/-]{0,79}\Z")
COMMIT = re.compile(r"^[0-9a-f]{40}([0-9a-f]{24})?\Z")
IDEMPOTENCY_KEY = re.compile(r"^[A-Za-z0-9._:-]{8,128}\Z")
CONTROL = re.compile(r"[\x00-\x1f\x7f]")
PROPOSE_FIELDS = ("book", "kind", "text", "citations", "scope", "commit", "links", "class_key", "decision", "origin",
                  "idempotency_key")


# --- references ----------------------------------------------------------------------------------------------

def parse_ref(ref) -> tuple[str, str]:
    """`<book>@nt_<64 hex>` -> (book, note id)."""
    m = REF.match(ref) if isinstance(ref, str) else None
    if not m:
        raise ValueError("malformed note reference (book@nt_<64 hex>)")
    return m.group(1), m.group(2)


def parse_passage(handle) -> search.Citation:
    """A passage handle `book@ct_…/pf_…/path#ordinal`, as `open_citation` takes it."""
    if not isinstance(handle, str) or CONTROL.search(handle):
        raise ValueError("malformed passage handle")
    try:
        head, ordinal = handle.rsplit("#", 1)
        book, rest = head.split("@", 1)
        content_id, profile_id, path = rest.split("/", 2)
        cite = search.Citation(book, content_id, profile_id, ids.normalize_path(path), int(ordinal))
    except ValueError:
        raise ValueError("malformed passage handle") from None
    if not BOOK.match(book) or not content_id.startswith("ct_") or not profile_id.startswith("pf_") \
            or cite.ordinal < 0:
        raise ValueError("malformed passage handle")
    return cite


def _target(ref):
    """A link target: ("note", book, id) or ("passage", Citation)."""
    if isinstance(ref, str) and REF.match(ref):
        return ("note", *parse_ref(ref))
    return ("passage", parse_passage(ref))


def _target_text(target) -> str:
    return f"{target[1]}@{target[2]}" if target[0] == "note" else target[1].handle


def _target_book(target) -> str:
    return target[1] if target[0] == "note" else target[1].book


def glob_re(glob: str) -> str:
    """The SQL regular expression of a scope glob: `**` any characters, `*` any except `/`, `?` one except `/`."""
    out, i = [], 0
    while i < len(glob):
        if glob.startswith("**", i):
            out.append(".*")
            i += 2
            continue
        c = glob[i]
        out.append("[^/]*" if c == "*" else "[^/]" if c == "?" else re.escape(c))
        i += 1
    return "^" + "".join(out) + "$"


def normalized_sha256(text: str) -> bytes:
    """`nfc-casefold-ws@1`: NFC, case fold, white space collapsed. Equal values make a `normalized` candidate only."""
    norm = " ".join(unicodedata.normalize("NFC", text).casefold().split())
    return hashlib.sha256(norm.encode("utf-8")).digest()


# --- validation (step 1, no I/O) -----------------------------------------------------------------------------

def _string(name: str, value, *, optional: bool = False) -> str | None:
    if value is None and optional:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a string")
    return value


def _list(name: str, value, limit: int) -> list:
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > limit:
        raise ValueError(f"{name} must be a list of at most {limit}")
    return value


def _no_control(name: str, value: str) -> str:
    if not value or CONTROL.search(value):
        raise ValueError(f"{name} must be non-empty without control characters")
    return value


def _code(text: str):
    from . import coderepo  # slice C; only a note with code citations needs it
    return coderepo.parse(text)


def _scope(value) -> dict | None:
    if value is None:
        return None
    if not isinstance(value, dict) or "repo" not in value or set(value) - {"repo", "branch", "paths"}:
        raise ValueError("scope must be {repo, branch?, paths?}")
    repo = _string("scope.repo", value["repo"])
    if not REPO.match(repo):
        raise ValueError("scope.repo must be a registered repository slug")
    branch = _string("scope.branch", value.get("branch"), optional=True)
    if branch is not None:
        _no_control("scope.branch", branch)
    paths = []
    for p in _list("scope.paths", value.get("paths"), MAX_PATHS):
        paths.append(ids.normalize_path(_no_control("scope.paths", _string("scope.paths", p))))
    return {"repo": repo, "branch": branch, "paths": paths}


def _decision(value, kind: str) -> tuple[list[str] | None, str | None]:
    """docs/24 §21.3: the options offered (in order) and the choice of a decision note, or (None, None)."""
    if value is None:
        return None, None
    if not isinstance(value, dict) or set(value) != {"options", "choice"}:
        raise ValueError("decision must be {options, choice}")
    if kind != "decision_proposal":
        raise ValueError("decision is only for kind decision_proposal")
    options = [unicodedata.normalize("NFC", _no_control("decision.options", _string("decision.options", o)))
               for o in _list("decision.options", value["options"], MAX_OPTIONS)]
    if len(options) < 2 or len(set(options)) != len(options) \
            or any(not o.strip() or len(o) > OPTION_CHARS for o in options):
        raise ValueError(f"decision.options must be 2..{MAX_OPTIONS} different options of 1..{OPTION_CHARS} "
                         "characters")
    choice = unicodedata.normalize("NFC", _string("decision.choice", value["choice"]))
    if choice not in options:
        raise ValueError("decision.choice must be one of decision.options")
    return options, choice


class Draft:
    """A validated propose request and its canonical body (§3)."""

    def __init__(self, args: dict):
        if not isinstance(args, dict) or set(args) - set(PROPOSE_FIELDS):
            raise ValueError(f"fields: {', '.join(PROPOSE_FIELDS)}")
        self.book = _string("book", args.get("book"))
        if not BOOK.match(self.book):
            raise ValueError("book must be a book slug")
        self.kind = _string("kind", args.get("kind"))
        if self.kind not in KINDS:
            raise ValueError(f"kind must be one of {', '.join(KINDS)}")
        self.text = unicodedata.normalize("NFC", _string("text", args.get("text")))
        if not self.text.strip() or len(self.text) > profiles.NOTE_MAX_CHARS or "\x00" in self.text:
            raise ValueError(f"text must be 1..{profiles.NOTE_MAX_CHARS} characters (one note is one block)")
        self.class_key = _string("class_key", args.get("class_key"), optional=True)
        if self.class_key is not None and not CLASS_KEY.match(self.class_key):
            raise ValueError("class_key must match [a-z0-9][a-z0-9._:/-]{0,79}")
        self.scope = _scope(args.get("scope"))
        self.commit = _string("commit", args.get("commit"), optional=True)
        if self.commit is not None and (self.scope is None or not COMMIT.match(self.commit)):
            raise ValueError("commit must be a full commit id and needs scope.repo")
        self.passages, self.codes, cited = [], [], []  # passages/codes: (n, citation)
        for n, c in enumerate(_list("citations", args.get("citations"), MAX_CITATIONS), start=1):
            _no_control("citation", _string("citation", c))
            if c.partition("@")[2].startswith("ct_"):
                cite = parse_passage(c)
                self.passages.append((n, cite))
                cited.append(cite.handle)
            else:
                cite = _code(c)
                self.codes.append((n, cite))
                cited.append(str(cite))
        self.links = []  # (type, target)
        for link in _list("links", args.get("links"), MAX_LINKS):
            if not isinstance(link, dict) or set(link) != {"type", "ref"}:
                raise ValueError("a link must be {type, ref}")
            kind = _string("link type", link["type"])
            if kind not in LINK_TYPES:
                raise ValueError(f"link type must be one of {', '.join(LINK_TYPES)}")
            target = _target(_string("link ref", link["ref"]))
            if target[0] == "passage" and kind not in PASSAGE_LINKS:
                raise ValueError(f"a passage can only be the target of {' or '.join(PASSAGE_LINKS)}")
            if kind == "same_as" and target[1] != self.book:
                raise ValueError("same_as stays inside one book")
            self.links.append((kind, target))
        links = sorted((k, _target_text(t)) for k, t in self.links)
        if len(set(links)) != len(links):
            raise ValueError("the same link is given twice")
        self.origin_requested = _string("origin", args.get("origin"), optional=True)
        if self.origin_requested is not None and self.origin_requested not in kstd.ORIGINS:
            raise ValueError(f"origin must be one of {', '.join(kstd.ORIGINS)}")
        self.key = _string("idempotency_key", args.get("idempotency_key"), optional=True)
        if self.key is not None and not IDEMPOTENCY_KEY.match(self.key):
            raise ValueError("idempotency_key must match [A-Za-z0-9._:-]{8,128}")
        self.options, self.choice = _decision(args.get("decision"), self.kind)
        self.body = {"v": 1, "kind": self.kind, "text": self.text, "class_key": self.class_key, "scope": self.scope,
                     "commit": self.commit, "citations": cited,
                     "links": [{"type": k, "target": t} for k, t in links]}
        if self.options is not None:  # only when given: a note without it keeps its id (§21.3)
            self.body["decision"] = {"options": self.options, "choice": self.choice}
        self.id = "nt_" + ids.sha256_hex(ids.canonical(self.body))
        self.ref = f"{self.book}@{self.id}"
        # §6.4: every argument except the key, with the defaults filled in, so MCP and HTTP retries are equal. An
        # absent decision is left out, so the digests of requests made before it existed do not change.
        self.digest = ids.request_digest({f: args.get(f) for f in PROPOSE_FIELDS
                                          if f != "idempotency_key" and (f != "decision" or self.options)}
                                         | {"citations": args.get("citations") or [],
                                            "links": args.get("links") or []})

    def needs(self) -> dict:
        """propose on the journal; read on the book of every cited passage and every linked note or passage."""
        needs = {f"book:{self.book}": {"propose"}}
        for _, cite in self.passages:
            needs.setdefault(f"book:{cite.book}", set()).add("read")
        for _, target in self.links:
            needs.setdefault(f"book:{_target_book(target)}", set()).add("read")
        return needs


# --- shared helpers ------------------------------------------------------------------------------------------

def _principal(what: str, value) -> str:
    if not isinstance(value, str) or not authz.PRINCIPAL.match(value):
        raise ValueError(f"invalid {what}: {value!r}")
    return value


def _for_model(actor: Actor) -> bool:
    """As `server._for_model`: MCP callers and agent principals put what they read into a model's context."""
    return actor.channel == "mcp" or actor.principal.startswith("agent:")


def _writer(actor: Actor) -> None:
    if actor.channel not in ("mcp", "http"):
        raise ValueError("notes are written over MCP or HTTP")


def _decide(conn, actor: Actor, needs: dict, action: str) -> authz.Allowed:
    """The pre-decision (§6.1 step 5): every need in ONE statement before any work; a missing need is logged."""
    modes = sorted({m for ms in needs.values() for m in ms} | {"read"}, key=authz.MODES.index)
    verdict = authz.allowed(conn, actor.principal, actor.on_behalf_of, modes)
    missing = [(o, m) for o in sorted(needs) for m in sorted(needs[o], key=modes.index)
               if m not in verdict.decisions.get(o, {})]
    for obj, mode in missing:
        gate.log_event(conn, actor, action if mode == "read" else mode, obj, mode,
                       authz.Decision(False, "no current right"), verdict.policies.get(obj), None, None)
    if missing:
        raise gate.Denied(f"{action}: no current right on {', '.join(sorted({o for o, _ in missing}))}")
    return verdict


def _lock(conn) -> None:
    conn.execute("SELECT pg_advisory_xact_lock(%s)", (MEMORY_LOCK,))


def _check_limit(conn, actor: Actor) -> None:
    """One daily budget per principal for every memory write over MCP and HTTP: proposes, links and outcomes (§6.1,
    §21.1). The operator's CLI import (§23) is not counted."""
    limit = int(os.environ.get(WRITES_ENV) or WRITES_DEFAULT)
    count = conn.execute("SELECT (SELECT count(*) FROM write_record WHERE principal = %(p)s AND channel <> 'cli' "
                         "                                     AND at > now() - interval '1 day') "
                         "     + (SELECT count(*) FROM outcome WHERE principal = %(p)s "
                         "                                     AND at > now() - interval '1 day')",
                         {"p": actor.principal}).fetchone()[0]
    if count >= limit:
        raise ids.LimitExceeded(f"daily note write limit reached ({limit})")


def _journal(conn, book: str) -> tuple[bool, bool, bool]:
    row = conn.execute("SELECT search, ai_input, train FROM journal WHERE book = %s", (book,)).fetchone()
    if row is None:
        raise NotFound(f"{book} is not a journal")
    return row


def _notes(conn, targets) -> dict:
    """{(book, id): (seq, search, ai_input, source_books, train)} with search, ai_input and train ANDed with the
    journals of the note's closure now (`note_journal`, docs/24 §20.3, §21.3)."""
    keys = sorted({(t[1], t[2]) for t in targets})
    rows = conn.execute("SELECT n.book, n.id, n.seq, n.search AND j.search, n.ai_input AND j.ai_input, n.source_books, "
                        "n.train AND j.train FROM note n JOIN note_journal j ON j.seq = n.seq "
                        "JOIN unnest(%s::text[], %s::text[]) AS k(book, id) ON (n.book, n.id) = (k.book, k.id)",
                        ([b for b, _ in keys], [i for _, i in keys])).fetchall()
    found = {(b, i): rest for b, i, *rest in rows}
    missing = [f"{b}@{i}" for b, i in keys if (b, i) not in found]
    if missing:
        raise NotFound(f"no such note: {missing[0]}")
    return found


def _passages_exist(conn, cites) -> None:
    for c in cites:
        if not conn.execute("SELECT 1 FROM chunk WHERE book = %s AND content_id = %s AND profile_id = %s "
                            "AND path = %s AND ordinal = %s",
                            (c.book, c.content_id, c.profile_id, c.path, c.ordinal)).fetchone():
            raise NotFound(f"no such passage: {c.handle}")


def effective_standing(conn, seqs, w: int) -> dict:
    """{seq: (value, event seq)}: the latest Standing event with seq <= w, else ("pending", None) (§4.2)."""
    rows = conn.execute("SELECT s.seq, e.value, e.seq FROM unnest(%s::bigint[]) AS s(seq) "
                        "LEFT JOIN LATERAL (SELECT value, seq FROM standing_event WHERE note_seq = s.seq "
                        "AND seq <= %s ORDER BY seq DESC LIMIT 1) e ON true", (list(seqs), w)).fetchall()
    return {seq: (value or "pending", event) for seq, value, event in rows}


_COMPONENTS = """
WITH RECURSIVE e(a, b) AS (
    SELECT src, dst_note FROM note_link WHERE type = 'same_as' AND seq <= %(w)s
    UNION ALL
    SELECT dst_note, src FROM note_link WHERE type = 'same_as' AND seq <= %(w)s),
reach(n, m) AS (
    SELECT s, s FROM unnest(%(starts)s::bigint[]) AS s
    UNION
    SELECT r.n, e.b FROM reach r JOIN e ON e.a = r.m)
SELECT n, array_agg(m ORDER BY m) FROM reach GROUP BY n
"""


def _components(conn, starts, w: int) -> dict:
    """{start: sorted members of its same_as component, links with seq <= w}. same_as is book-local (016)."""
    return {n: members for n, members in conn.execute(_COMPONENTS, {"starts": list(starts), "w": w})}


def clusters(conn, book: str, w: int) -> dict:
    """{note seq: cluster key} for every note of the book with seq <= w; the key is the lowest seq of its same_as
    component (links with seq <= w). Computed at read time: nothing is stored, so `as_of` gives the old clusters."""
    seqs = [s for (s,) in conn.execute("SELECT seq FROM note WHERE book = %s AND seq <= %s", (book, w))]
    return {n: members[0] for n, members in _components(conn, seqs, w).items()}


def recurrence(conn, seq: int, w: int) -> int:
    """The propose write records with seq <= w over the note's cluster (§7)."""
    members = _components(conn, [seq], w)[seq]
    return conn.execute("SELECT count(*) FROM write_record WHERE action = 'propose' AND note_seq = ANY(%s) "
                        "AND seq <= %s", (members, w)).fetchone()[0]


def item_info(conn, note_seq: int) -> dict:
    """kstd-shaped item information of a note, for `server._text` and `kstd.allows`: its rights ANDed with the
    current ones of the journals of its closure, and its shown origin now (docs/25 §7.6) with the kstd origin
    details of a live confirmation (`assisted` + `reviewed_by`; `human` + `entered_by` and `confirmed_by`)."""
    row = conn.execute("SELECT n.search AND j.search, n.ai_input AND j.ai_input "
                       "FROM note n JOIN note_journal j ON j.seq = n.seq WHERE n.seq = %s", (note_seq,)).fetchone()
    if row is None:
        raise NotFound(f"no such note: {note_seq}")
    yn = {True: "y", False: "n"}
    shown = origins.shown(conn, [note_seq], None)[note_seq]
    return {"origin": shown[0], **origins.details(*shown), "ai_use": {"search": yn[row[0]], "ai_input": yn[row[1]]}}


_CANONICAL_PARTS = """
SELECT n.kind, n.body, n.class_key, n.scope_repo, n.scope_branch, n.scope_paths, n.observed_commit, n.options,
       n.choice,
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
               FROM note_link l LEFT JOIN note d ON d.seq = l.dst_note WHERE l.src = n.seq AND l.creation)
  FROM note n WHERE n.seq = %s
"""


def canonical_of(conn, note_seq: int) -> tuple[str, dict]:
    """(id, body) computed again from every stored part of a note: what a person sees and signs (docs/25 §5.2). The
    app role can add citations and creation links to a stored note, so the stored id alone does not prove the bytes;
    a caller compares this id with the stored one."""
    row = conn.execute(_CANONICAL_PARTS, (note_seq,)).fetchone()
    if row is None:
        raise NotFound(f"no such note: {note_seq}")
    kind, text, class_key, repo, branch, paths, commit, options, choice, cited, links = row
    body = {"v": 1, "kind": kind, "text": text, "class_key": class_key,
            "scope": None if repo is None else {"repo": repo, "branch": branch, "paths": list(paths)},
            "commit": commit, "citations": list(cited),
            "links": sorted(links, key=lambda link: (link["type"], link["target"]))}
    if options is not None:
        body["decision"] = {"options": list(options), "choice": choice}
    return "nt_" + ids.sha256_hex(ids.canonical(body)), body


# --- journals (CLI) ------------------------------------------------------------------------------------------

def create_journal(conn, *, book: str, title: str, search: bool, ai_input: bool, policy: dict, by: str,
                   train: bool = False) -> dict:
    """A journal is a new book with no content version and the `journal` profile; `search` and `ai_input` are both
    stated (missing = deny, docs/22 §3). `train` (§21.3) is false unless stated: missing = deny. A `restricted`
    journal never leaves the installation (§23), so it never allows `train`."""
    if not BOOK.match(book):
        raise ValueError("book must be a book slug")
    _principal("creator", by)
    policy = check_policy(policy)
    if train and policy["sensitivity"] == "restricted":
        raise ValueError("a restricted journal cannot allow train: its notes are never exported")
    profile = profiles.spec(profiles.JOURNAL)
    policy_id, profile_id = ids.policy_id(policy), ids.profile_id(profile)
    with conn.transaction():
        if conn.execute("SELECT 1 FROM book WHERE slug = %s", (book,)).fetchone():
            raise ValueError(f"{book} exists; a journal is a new book")
        conn.execute("INSERT INTO policy_version (id, doc) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                     (policy_id, Jsonb(policy)))
        conn.execute("INSERT INTO profile_version (id, spec) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                     (profile_id, Jsonb(profile)))
        conn.execute("INSERT INTO book (slug, title, current_policy, current_profile) VALUES (%s, %s, %s, %s)",
                     (book, title, policy_id, profile_id))
        conn.execute("INSERT INTO journal (book, search, ai_input, train, created_by) VALUES (%s, %s, %s, %s, %s)",
                     (book, search, ai_input, train, by))
    return {"book": book, "search": search, "ai_input": ai_input, "train": train, "policy_id": policy_id,
            "profile_id": profile_id}


def restrict_journal(conn, book: str, *, search: bool = False, ai_input: bool = False, train: bool = False) -> dict:
    """Tighten a journal: `search=True` turns search off, `ai_input=True` turns AI input off, `train=True` turns
    training use off. R1 never loosens a journal (a new journal is needed); reads, model calls and the decision
    export AND every note with these current values."""
    if not (search or ai_input or train):
        raise ValueError("give --no-search, --no-ai-input, --no-train or more of them")
    row = conn.execute("UPDATE journal SET search = search AND NOT %s, ai_input = ai_input AND NOT %s, "
                       "train = train AND NOT %s WHERE book = %s RETURNING search, ai_input, train",
                       (search, ai_input, train, book)).fetchone()
    if row is None:
        raise NotFound(f"{book} is not a journal")
    return {"book": book, "search": row[0], "ai_input": row[1], "train": row[2]}


# --- propose (§6.1) ------------------------------------------------------------------------------------------

def _prior(conn, actor: Actor, key: str):
    return conn.execute("SELECT seq, note_seq, creates, request_sha256, origin, notice FROM write_record "
                        "WHERE principal = %s AND coalesce(on_behalf_of, '') = coalesce(%s, '') "
                        "AND idempotency_key = %s", (actor.principal, actor.on_behalf_of, key)).fetchone()


def _same_request(prior, draft: Draft) -> None:
    if bytes(prior[3]) != draft.digest:
        raise ids.IdempotencyConflict("idempotency_key reused with another request")


def _derive(conn, draft: Draft) -> tuple[bool, bool, bool, list[str], dict]:
    """Step 6 (database only): the note's search, ai_input, train (§21.3) and source_books from its dependencies
    (passage citations and derived_from targets), and the seq of every linked note. Every target must exist."""
    j_search, j_ai, j_train = _journal(conn, draft.book)
    note_targets = [t for _, t in draft.links if t[0] == "note"]
    found = _notes(conn, note_targets) if note_targets else {}
    _passages_exist(conn, [c for _, c in draft.passages] + [t[1] for _, t in draft.links if t[0] == "passage"])
    rights = kstd.Rights(conn)
    allow_search, allow_ai, allow_train, books = j_search, j_ai, j_train, {draft.book}
    dependencies = [c for _, c in draft.passages] + [t[1] for k, t in draft.links
                                                     if k == "derived_from" and t[0] == "passage"]
    for c in dependencies:
        allow_search = allow_search and rights.allows(c.book, c.content_id, c.path, "search")
        allow_ai = allow_ai and rights.allows(c.book, c.content_id, c.path, "ai_input")
        allow_train = allow_train and rights.allows(c.book, c.content_id, c.path, "train")
        books.add(c.book)
    for k, t in draft.links:
        if k == "derived_from" and t[0] == "note":
            _, n_search, n_ai, n_books, n_train = found[(t[1], t[2])]
            allow_search, allow_ai, allow_train = allow_search and n_search, allow_ai and n_ai, allow_train and n_train
            books |= {t[1], *n_books}
    return allow_search, allow_ai, allow_train, sorted(books), found


def _excerpts(conn, draft: Draft) -> dict:
    """Step 7: {n: excerpt sha256} of every code citation; a scope names a live repository of the journal."""
    if draft.scope is not None and not conn.execute(
            "SELECT 1 FROM code_repo WHERE book = %s AND slug = %s AND removed_at IS NULL",
            (draft.book, draft.scope["repo"])).fetchone():
        raise ValueError(f"scope.repo: no registered repository {draft.scope['repo']} in {draft.book}")
    if not draft.codes:
        return {}
    from . import coderepo
    return {n: coderepo.excerpt(conn, draft.book, cite) for n, cite in draft.codes}


def _embed(conn, embedder: llmdap.Routed | None, actor: Actor, draft: Draft, allow_search: bool, allow_ai: bool,
           books: list[str]) -> tuple[search.QueryVector | None, str]:
    """Step 8: only for a note that may be searched and sent to a model, through the egress check of its
    source_books. A refusal or failure does not stop the write."""
    if not allow_search:
        return None, "skipped:search"
    if not allow_ai:
        return None, "skipped:ai_input"
    if embedder is None:
        return None, "skipped:no_route"
    if conn.execute("SELECT 1 FROM note_vector v JOIN note n ON n.seq = v.note_seq WHERE n.book = %s AND n.id = %s "
                    "AND v.model = %s", (draft.book, draft.id, embedder.model)).fetchone():
        return None, "stored"
    try:
        (values,) = llmdap.embed(conn, embedder, actor, [vectors.embedded_text(draft.text)], source_books=books,
                                 purpose="note")
    except llmdap.PolicyRefused:
        return None, "skipped:egress"
    except llmdap.EgressError:
        return None, "skipped:error"
    dims = conn.execute("SELECT vector_dims(embedding) FROM note_vector WHERE model = %s LIMIT 1",
                        (embedder.model,)).fetchone()
    if dims and dims[0] != len(values):
        return None, "skipped:dimensions"
    return search.QueryVector(embedder.model, values), "stored"


_NOTE_INSERT = """
INSERT INTO note (book, id, profile_id, kind, body, norm_sha256, class_key, scope_repo, scope_branch, scope_paths,
                  scope_path_re, observed_commit, search, ai_input, train, source_books, options, choice, tsv)
VALUES (%(book)s, %(id)s, %(profile)s, %(kind)s, %(body)s, %(norm)s, %(class_key)s, %(repo)s, %(branch)s, %(paths)s,
        %(path_re)s, %(commit)s, %(search)s, %(ai_input)s, %(train)s, %(books)s, %(options)s, %(choice)s,
        CASE WHEN %(search)s THEN to_tsvector(%(fts)s::regconfig, %(body)s) END)
RETURNING seq
"""

_WRITE_INSERT = """
INSERT INTO write_record (correlation_id, action, note_seq, creates, principal, on_behalf_of, channel, client_id,
                          origin_requested, origin, notice, idempotency_key, request_sha256)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
RETURNING seq
"""


def _write_record(conn, actor: Actor, action: str, note_seq, creates: bool, requested, stored: str, notice,
                  key=None, digest=None) -> int:
    return conn.execute(_WRITE_INSERT, (actor.correlation_id, action, note_seq, creates, actor.principal,
                                        actor.on_behalf_of, actor.channel, actor.client_id, requested, stored,
                                        notice, key, digest)).fetchone()[0]


def _insert_note(conn, draft: Draft, allow_search: bool, allow_ai: bool, allow_train: bool, books: list[str]) -> int:
    profile = profiles.spec(profiles.JOURNAL)
    profile_id = ids.profile_id(profile)
    conn.execute("INSERT INTO profile_version (id, spec) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                 (profile_id, Jsonb(profile)))
    scope = draft.scope or {"repo": None, "branch": None, "paths": []}
    return conn.execute(_NOTE_INSERT, {
        "book": draft.book, "id": draft.id, "profile": profile_id, "kind": draft.kind, "body": draft.text,
        "norm": normalized_sha256(draft.text), "class_key": draft.class_key, "repo": scope["repo"],
        "branch": scope["branch"], "paths": scope["paths"], "path_re": [glob_re(p) for p in scope["paths"]],
        "commit": draft.commit, "search": allow_search, "ai_input": allow_ai, "train": allow_train, "books": books,
        "options": draft.options, "choice": draft.choice, "fts": profile["settings"]["fts"]}).fetchone()[0]


def _insert_parts(conn, draft: Draft, seq: int, write_seq: int, found: dict, excerpts: dict) -> None:
    """The citations and the creation links of a new note; the creating write owns the links (016 keys)."""
    for n, c in draft.passages:
        conn.execute("INSERT INTO note_citation (note_seq, book, n, kind, cite_book, content_id, profile_id, ordinal, "
                     "path) VALUES (%s, %s, %s, 'passage', %s, %s, %s, %s, %s)",
                     (seq, draft.book, n, c.book, c.content_id, c.profile_id, c.ordinal, c.path))
    for n, c in draft.codes:
        conn.execute("INSERT INTO note_citation (note_seq, book, n, kind, path, repo, commit, line_start, line_end, "
                     "symbol, excerpt_sha256) VALUES (%s, %s, %s, 'code', %s, %s, %s, %s, %s, %s, %s)",
                     (seq, draft.book, n, c.path, c.repo, c.commit, c.line_start, c.line_end, c.symbol,
                      excerpts[n]))
    for kind, t in draft.links:
        _insert_link(conn, seq, draft.book, kind, t, found, creation=True, write_seq=write_seq)


def _existing_link(conn, src: int, kind: str, target, found: dict) -> bool:
    if target[0] == "note":
        return conn.execute("SELECT 1 FROM note_link WHERE src = %s AND type = %s AND dst_note = %s",
                            (src, kind, found[(target[1], target[2])][0])).fetchone() is not None
    c = target[1]
    return conn.execute("SELECT 1 FROM note_link WHERE src = %s AND type = %s AND dst_book = %s "
                        "AND dst_content_id = %s AND dst_profile_id = %s AND dst_path = %s AND dst_ordinal = %s",
                        (src, kind, c.book, c.content_id, c.profile_id, c.path, c.ordinal)).fetchone() is not None


def _insert_link(conn, src: int, src_book: str, kind: str, target, found: dict, *, creation: bool,
                 write_seq: int) -> int:
    if target[0] == "note":
        dst = (found[(target[1], target[2])][0], target[1], None, None, None, None, None)
    else:
        c = target[1]
        dst = (None, None, c.book, c.content_id, c.profile_id, c.path, c.ordinal)
    return conn.execute("INSERT INTO note_link (src, src_book, type, dst_note, dst_note_book, dst_book, "
                        "dst_content_id, dst_profile_id, dst_path, dst_ordinal, creation, write_seq) "
                        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING seq",
                        (src, src_book, kind, *dst, creation, write_seq)).fetchone()[0]


_CANDIDATE_COLUMNS = "n.seq, n.book, n.id, n.kind, n.body, n.ai_input AND j.ai_input"
_SEARCHABLE = "n.search AND j.search AND n.book = ANY(%(books)s) AND n.seq <> %(self)s"


def _candidates(conn, seq: int, draft: Draft, readable: list[str], embedder, for_model: bool) -> list[dict]:
    """§7: normalized, vector and class matches; only from readable books and searchable notes. Never merged."""
    params = {"books": readable, "self": seq, "norm": normalized_sha256(draft.text), "book": draft.book,
              "class_key": draft.class_key, "limit": CANDIDATES_PER_MATCH}
    found = [(row, "normalized", None) for row in conn.execute(
        f"SELECT {_CANDIDATE_COLUMNS} FROM note n JOIN note_journal j ON j.seq = n.seq "
        f"WHERE n.norm_sha256 = %(norm)s AND {_SEARCHABLE} ORDER BY n.seq DESC LIMIT %(limit)s", params)]
    if embedder is not None:
        params |= {"model": embedder.model,
                   "threshold": float(os.environ.get(SIMILARITY_ENV) or SIMILARITY_DEFAULT)}
        found += [(row[:6], "vector", round(row[6], 4)) for row in conn.execute(
            f"WITH q AS (SELECT embedding FROM note_vector WHERE note_seq = %(self)s AND model = %(model)s) "
            f"SELECT {_CANDIDATE_COLUMNS}, 1 - (v.embedding <=> q.embedding) AS similarity "
            f"FROM q CROSS JOIN note_vector v JOIN note n ON n.seq = v.note_seq JOIN note_journal j ON j.seq = n.seq "
            f"WHERE v.model = %(model)s AND vector_dims(v.embedding) = vector_dims(q.embedding) AND {_SEARCHABLE} "
            f"AND 1 - (v.embedding <=> q.embedding) >= %(threshold)s "
            f"ORDER BY v.embedding <=> q.embedding, n.seq DESC LIMIT %(limit)s", params)]
    if draft.class_key is not None and draft.book in readable:
        found += [(row, "class", None) for row in conn.execute(
            f"SELECT {_CANDIDATE_COLUMNS} FROM note n JOIN note_journal j ON j.seq = n.seq "
            f"WHERE n.book = %(book)s AND n.class_key = %(class_key)s AND {_SEARCHABLE} "
            f"ORDER BY n.seq DESC LIMIT %(limit)s", params)]
    seen, unique = set(), []
    for row, match, similarity in found:
        if row[0] not in seen:
            seen.add(row[0])
            unique.append((row, match, similarity))
    standing = effective_standing(conn, [r[0] for r, _, _ in unique], NOW)
    out = []
    for (n_seq, book, nid, kind, body, ai), match, similarity in unique:
        withheld = for_model and not ai
        out.append({"ref": f"{book}@{nid}", "match": match, "similarity": similarity, "kind": kind,
                    "standing": standing[n_seq][0], "text": None if withheld else body[:CANDIDATE_CHARS],
                    "withheld": WITHHELD if withheld else None, "_standing_seq": standing[n_seq][1],
                    "_seq": n_seq})
    return out


def _counts(conn, seq: int, draft: Draft) -> dict:
    """recurrence over the note's cluster; class_count = distinct clusters with the class key in the book;
    guard_due = class_count >= 2 and no approved convention note with that class key in the book (§7)."""
    out = {"recurrence": recurrence(conn, seq, NOW), "class_count": 0, "guard_due": False}
    if draft.class_key is None:
        return out
    rows = conn.execute("SELECT seq, kind FROM note WHERE book = %s AND class_key = %s",
                        (draft.book, draft.class_key)).fetchall()
    out["class_count"] = len({members[0] for members in _components(conn, [s for s, _ in rows], NOW).values()})
    conventions = [s for s, kind in rows if kind == "convention"]
    approved = any(v == "approved" for v, _ in effective_standing(conn, conventions, NOW).values())
    out["guard_due"] = out["class_count"] >= 2 and not approved
    return out


def propose(conn, actor: Actor, args: dict, embedder: llmdap.Routed | None = None) -> tuple[dict, bool]:
    """`propose_note` (§6.1). Returns (receipt, retry): retry is true for an idempotent retry (HTTP 200)."""
    _writer(actor)
    draft = Draft(args)                                                                       # 1. validate
    rules = sorted({f.rule for t in [draft.text, *(draft.options or [])] for f in secretscan.findings(t)})  # 2. scan
    if rules:
        raise ValueError(f"text refused: credential-like content ({', '.join(rules)})")
    prior = _prior(conn, actor, draft.key) if draft.key else None                            # 3. idempotency
    if prior:
        _same_request(prior, draft)
    else:
        _check_limit(conn, actor)                                                            # 4. daily limit
    needs = draft.needs()
    _decide(conn, actor, needs, "propose")                                                   # 5. pre-decision
    allow_search, allow_ai, allow_train, books, found = _derive(conn, draft)                 # 6. dependencies
    excerpts = _excerpts(conn, draft)                                                        # 7. code excerpts
    vector, vector_status = _embed(conn, embedder, actor, draft, allow_search, allow_ai, books)  # 8. embedding
    journal = f"book:{draft.book}"
    stored, notice = origins.compute(actor, draft.origin_requested)

    def work():                                                                              # 9. transaction
        _lock(conn)
        again = _prior(conn, actor, draft.key) if draft.key else None
        if again:
            _same_request(again, draft)
            write_seq, seq, status, origin, origin_notice = again[0], again[1], "created" if again[2] else "existing", \
                again[4], again[5]
        else:
            _check_limit(conn, actor)
            row = conn.execute("SELECT seq FROM note WHERE book = %s AND id = %s", (draft.book, draft.id)).fetchone()
            seq = row[0] if row else _insert_note(conn, draft, allow_search, allow_ai, allow_train, books)
            write_seq = _write_record(conn, actor, "propose", seq, row is None, draft.origin_requested, stored,
                                      notice, draft.key, draft.digest if draft.key else None)
            if row is None:
                _insert_parts(conn, draft, seq, write_seq, found, excerpts)
            status, origin, origin_notice = "created" if row is None else "existing", stored, notice
        if vector is not None:
            conn.execute("INSERT INTO note_vector (note_seq, model, embedding) VALUES (%s, %s, %s::vector) "
                         "ON CONFLICT DO NOTHING", (seq, vector.model, vector.literal()))
        reads = authz.allowed(conn, actor.principal, actor.on_behalf_of, ["read"])  # the receipt level, decided now
        request = {}
        if origin_notice == origins.REFUSED and draft.origin_requested in origins.CONFIRMABLE:  # docs/25 §7.1
            from . import confirm  # confirm imports curation, which needs this module loaded
            request = {"confirmation": confirm.receipt(conn, write_seq, draft.ref)}
        minimal = {"ref": draft.ref, "status": "recorded", "origin": origin, "origin_notice": origin_notice, **request}
        if journal not in reads.objects("read"):
            return minimal, again is not None, minimal, []  # propose-only: nothing about existence or counts
        readable = sorted(o.removeprefix("book:") for o in reads.objects("read"))
        candidates = _candidates(conn, seq, draft, readable, embedder, _for_model(actor)) if allow_search else []
        receipt = {"ref": draft.ref, "status": status, "standing": effective_standing(conn, [seq], NOW)[seq][0],
                   "origin": origin, "origin_notice": origin_notice, **request, "candidates": candidates,
                   **_counts(conn, seq, draft), "vector": vector_status}
        return receipt, again is not None, minimal, candidates

    def finish(final: authz.Allowed, data):
        """The receipt as the final decision allows it (§11): without read on the journal, the minimal receipt;
        a candidate only from a book that is still readable; for a model reader, the text of a candidate that
        depends on a blocked skill is withheld (D71, read by the same final statement)."""
        receipt, retry, minimal, candidates = data
        readable = final.objects("read")
        if receipt is minimal or journal not in readable:
            return minimal, retry, [], final
        kept = [c for c in candidates if f"book:{c['ref'].split('@')[0]}" in readable]
        shown = [{k: v for k, v in c.items() if k not in ("_standing_seq", "_seq")}
                 | ({"text": None, "withheld": gate.SKILL_WITHHELD} if c["_seq"] in final.blocked_notes else {})
                 for c in kept]
        return {**receipt, "candidates": shown}, retry, kept, final

    def shown_text(data) -> list[int]:
        """The candidates whose text a model reader would get: the final statement reads their skill blocks."""
        return [c["_seq"] for c in data[3] if c["text"] is not None] if _for_model(actor) else []

    receipt, retry, candidates, final = gate.guard_many(conn, actor, needs, work, action="propose",
                                                        items={journal: [{"ref": draft.ref}]}, finish=finish,
                                                        notes_of=shown_text)
    by_book = {}
    for c in candidates:  # each delivered candidate is on record with the Standing event in force (AT-09)
        by_book.setdefault(f"book:{c['ref'].split('@')[0]}", []).append({"ref": c["ref"],
                                                                         "standing_seq": c["_standing_seq"]})
    for obj, items in sorted(by_book.items()):
        gate.log_event(conn, actor, "propose", obj, "read", final.decisions[obj]["read"], final.policies.get(obj),
                       None, None, items=items)
    return receipt, retry


# --- later links (§6.3) --------------------------------------------------------------------------------------

def link(conn, actor: Actor, src: str, kind: str, dst: str) -> tuple[dict, bool]:
    """`link_notes`: a later link from a note to a note or passage. Returns (result, created)."""
    _writer(actor)
    src_book, src_id = parse_ref(_string("src", src))
    kind = _string("type", kind)
    if kind in CREATION_ONLY:
        raise ValueError(f"{kind} exists only as a creation link (propose_note links)")
    if kind not in LINK_TYPES:
        raise ValueError(f"type must be one of {', '.join(t for t in LINK_TYPES if t not in CREATION_ONLY)}")
    target = _target(_string("dst", dst))
    if target[0] == "passage" and kind not in PASSAGE_LINKS:
        raise ValueError(f"a passage can only be the target of {' or '.join(PASSAGE_LINKS)}")
    if kind == "same_as" and target[1] != src_book:
        raise ValueError("same_as stays inside one book")
    _check_limit(conn, actor)
    needs = {f"book:{src_book}": {"propose"}}
    needs.setdefault(f"book:{_target_book(target)}", set()).add("read")
    _decide(conn, actor, needs, "link")
    stored, _ = origins.compute(actor, None)
    result = {"src": f"{src_book}@{src_id}", "type": kind, "dst": _target_text(target)}

    def work():
        _lock(conn)
        found = _notes(conn, [("note", src_book, src_id)] + ([target] if target[0] == "note" else []))
        src_seq = found[(src_book, src_id)][0]
        if target[0] == "passage":
            _passages_exist(conn, [target[1]])
        if _existing_link(conn, src_seq, kind, target, found):
            return {**result, "status": "existing"}, False
        if target[0] == "note" and found[(target[1], target[2])][0] == src_seq:
            raise ValueError("a note cannot link to itself")
        _check_limit(conn, actor)
        write_seq = _write_record(conn, actor, "link", None, False, None, stored, None)
        _insert_link(conn, src_seq, src_book, kind, target, found, creation=False, write_seq=write_seq)
        return {**result, "status": "created"}, True

    return gate.guard_many(conn, actor, needs, work, action="link",
                           items={f"book:{src_book}": [{"ref": result["src"]}]})


# --- Standing (the CLI here; curator web through curation.apply, docs/25) -------------------------------------

def _curation(curator, reason) -> None:
    if not _principal("curator", curator).startswith("user:"):
        raise ValueError("a curator is a user:")
    if not isinstance(reason, str) or not 1 <= len(reason) <= 500:
        raise ValueError("reason must be 1..500 characters")


def _curated(conn, ref: str, curator: str, columns: str = "seq"):
    """The note row of a curator act; the curator must hold `curate` on its book now (`curate` is never delegated)."""
    book, note_id = parse_ref(ref)
    note = conn.execute(f"SELECT {columns} FROM note WHERE book = %s AND id = %s", (book, note_id)).fetchone()
    if note is None:
        raise NotFound(f"no such note: {ref}")
    if not authz.direct(conn, curator, f"book:{book}", "curate").allowed:
        raise gate.Denied(f"{curator} does not hold curate on book:{book}")
    return note


def _event(conn, note_seq: int, value: str, set_by: str, reason: str, correlation: str, cause=None) -> int:
    return conn.execute("INSERT INTO standing_event (note_seq, value, set_by, cause_seq, reason, correlation_id) "
                        "VALUES (%s, %s, %s, %s, %s, %s) RETURNING seq",
                        (note_seq, value, set_by, cause, reason, correlation)).fetchone()[0]


def set_standing(conn, ref: str, value: str, *, curator: str, reason: str) -> dict:
    """The curator act on the CLI. The caller connects with the owner credential (KUTUPHANE_CURATOR_DSN): the app role
    cannot write Standing. Approving a `rule` note retires the approved predecessors it supersedes with exactly the
    same scope, in the same transaction (§8.3). The rules are those of curation.apply, shared with curator web."""
    from . import curation  # curation imports this module
    if value not in STANDINGS:
        raise ValueError(f"standing must be one of {', '.join(STANDINGS)}")
    with conn.transaction():
        _lock(conn)
        return curation.apply(conn, principal=curator, items=[{"ref": ref, "to": value}], reason=reason)[0]


# --- rollback along derived_from (CLI only, §20) -------------------------------------------------------------

# The root keeps D68: a note that was never accepted is rejected; an out note gets one more event with its value.
# A root that was ever approved (also one reopened to pending since) is retired, never rejected.
ROOT_MOVE = {"approved": "retired", "pending": "rejected", "rejected": "rejected", "retired": "retired"}


def _ever_approved(conn, seq: int) -> bool:
    return conn.execute("SELECT EXISTS (SELECT 1 FROM standing_event WHERE note_seq = %s AND value = 'approved')",
                        (seq,)).fetchone()[0]


def _root_move(conn, seq: int, current: str) -> str:
    return "retired" if _ever_approved(conn, seq) else ROOT_MOVE[current]

_CLOSURE = """
WITH RECURSIVE c(seq) AS (
    SELECT %s::bigint
    UNION
    SELECT l.src FROM note_link l JOIN c ON l.dst_note = c.seq WHERE l.type = 'derived_from' AND l.creation)
SELECT n.seq, n.book || '@' || n.id FROM c JOIN note n ON n.seq = c.seq ORDER BY n.seq
"""

# A delivery item names its Standing event (§11, AT-09); write events log {ref} only, so they never match.
_DELIVERIES = """
SELECT a.id, a.at, a.action, a.principal, a.on_behalf_of, a.correlation_id, a.memory_seq,
       e->>'ref', (e->>'standing_seq')::bigint, ans.id, ans.created_at
  FROM access_event a
 CROSS JOIN LATERAL jsonb_array_elements(CASE WHEN jsonb_typeof(a.items) = 'array' THEN a.items
                                              ELSE '[]'::jsonb END) e
  LEFT JOIN answer ans ON a.action = 'answer' AND ans.correlation_id = a.correlation_id
 WHERE a.allowed AND jsonb_typeof(e) = 'object' AND e ? 'standing_seq' AND e->>'ref' = ANY(%s)
 ORDER BY a.id, ans.id
"""


def rollback(conn, ref: str, *, curator: str, reason: str) -> dict:
    """Retire a note and every note whose own `derived_from` chain reaches it, then report who used them (§20).
    The caller connects with the owner credential. The curator needs `curate` on the root's book only: each derived
    note gets a system event (the system only tightens), `cause_seq` = the root event, in the same transaction."""
    _curation(curator, reason)
    with conn.transaction():
        _lock(conn)
        root = _curated(conn, ref, curator)[0]
        closure = conn.execute(_CLOSURE, (root,)).fetchall()  # creation links point back: the root is first
        was = effective_standing(conn, [s for s, _ in closure], NOW)
        correlation = uuid.uuid4().hex
        root_after = _root_move(conn, root, was[root][0])
        event = _event(conn, root, root_after, curator, reason, correlation)
        writers = _writers(conn, [s for s, _ in closure])
        out = []
        for seq, note_ref in closure:
            before = was[seq][0]
            if seq == root:
                after, moved = root_after, event
            elif before in ("approved", "pending"):
                after = "retired"
                moved = _event(conn, seq, after, "system", f"derived from {ref}", correlation, cause=event)
            else:
                after, moved = before, None  # already out; the notes derived from it are still in the closure
            out.append({"ref": note_ref, "was": before, "standing": after, "event_seq": moved,
                        "writers": writers.get(seq, [])})
        return {"root": ref, "event_seq": event, "notes": out, **_used(conn, [r for _, r in closure])}


def _writers(conn, seqs) -> dict:
    """{note seq: [{principal, on_behalf_of, client_id}]}: the distinct writers of its propose writes, first first."""
    out = {}
    for seq, principal, behalf, client in conn.execute(
            "SELECT note_seq, principal, on_behalf_of, client_id FROM write_record "
            "WHERE action = 'propose' AND note_seq = ANY(%s) GROUP BY note_seq, principal, on_behalf_of, client_id "
            "ORDER BY note_seq, min(seq)", (seqs,)):
        out.setdefault(seq, []).append({"principal": principal, "on_behalf_of": behalf, "client_id": client})
    return out


def _used(conn, refs: list[str]) -> dict:
    """The deliveries, answers and exports that held any of `refs` (§20.2), from the access records (AT-09)."""
    rows = conn.execute(_DELIVERIES, (refs,)).fetchall()
    values = dict(conn.execute("SELECT seq, value FROM standing_event WHERE seq = ANY(%s)",
                               ([r[8] for r in rows if r[8] is not None],)).fetchall())
    order = {r: n for n, r in enumerate(refs)}
    events, answers = {}, {}
    for a_id, at, action, principal, behalf, correlation, w, note_ref, standing_seq, answer_id, answered in rows:
        item = {"ref": note_ref, "standing": values.get(standing_seq, "pending")}
        if answer_id is not None:
            entry = answers.setdefault(answer_id, {"id": answer_id, "at": answered.isoformat(), "principal": principal,
                                                   "on_behalf_of": behalf, "refs": []})
            if note_ref not in entry["refs"]:
                entry["refs"].append(note_ref)
            continue
        entry = events.setdefault(a_id, {"at": at.isoformat(), "action": action, "principal": principal,
                                         "on_behalf_of": behalf, "correlation_id": correlation, "memory_seq": w,
                                         "items": []})
        if item not in entry["items"]:
            entry["items"].append(item)
    for entry in events.values():  # closure order: the root first
        entry["items"].sort(key=lambda i: order[i["ref"]])
    for entry in answers.values():
        entry["refs"].sort(key=order.__getitem__)
    return {"deliveries": [e for e in events.values() if not e["action"].startswith("export")],
            "answers": list(answers.values()),
            "exports": [e for e in events.values() if e["action"].startswith("export")]}


# --- MCP and HTTP (feature hooks, docs/24 §16 P0) ------------------------------------------------------------

def op_propose(dsn, embedder, actor: Actor, args) -> tuple[dict, bool]:
    with db.connect(dsn) as conn:
        return propose(conn, actor, args, embedder)


def op_link(dsn, actor: Actor, body) -> tuple[dict, bool]:
    if not isinstance(body, dict) or set(body) != {"src", "type", "dst"}:
        raise ValueError("JSON object {src, type, dst} required")
    with db.connect(dsn) as conn:
        return link(conn, actor, body["src"], body["type"], body["dst"])


class Scope(TypedDict):
    repo: str
    branch: NotRequired[str]
    paths: NotRequired[list[str]]


class Link(TypedDict):
    type: str
    ref: str


class Decision(TypedDict):
    options: list[str]
    choice: str


def register_mcp(mcp, deps) -> None:
    @mcp.tool()
    @deps.mcp_errors
    async def propose_note(book: str, kind: str, text: str, citations: list[str] = [], scope: Scope | None = None,
                           commit: str | None = None, links: list[Link] = [], class_key: str | None = None,
                           decision: Decision | None = None, origin: str | None = None,
                           idempotency_key: str | None = None) -> dict:
        """Write a note into a journal (needs propose). kind: finding, decision_proposal, dead_end, convention,
        lesson, test_result. citations: passage handles or code citations repo@commit:path:start-end[#symbol].
        links: [{type, ref}] (derived_from, supersedes, same_as, contradicts, about, fixed_by, violates,
        decided_by) to older notes (book@nt_…) or passages. decision (decision_proposal only): {options: the 2..20
        options offered, in order; choice: the one chosen}. The note starts pending; only a curator approves it.
        The same bytes again are the same note (recurrence + 1). Give an idempotency_key to retry safely."""
        args = {"book": book, "kind": kind, "text": text, "citations": citations, "scope": scope, "commit": commit,
                "links": links, "class_key": class_key, "decision": decision, "origin": origin,
                "idempotency_key": idempotency_key}
        receipt, _ = await run_in_threadpool(op_propose, deps.dsn, deps.stages.embedder, deps.mcp_actor(), args)
        return receipt

    @mcp.tool()
    @deps.mcp_errors
    async def link_notes(src: str, type: str, dst: str) -> dict:
        """Link a note (src, book@nt_…; needs propose on its book) to a note or passage (dst; needs read):
        same_as (same book), contradicts, about, fixed_by, violates, decided_by. The same link again is kept once."""
        result, _ = await run_in_threadpool(op_link, deps.dsn, deps.mcp_actor(), {"src": src, "type": type,
                                                                                  "dst": dst})
        return result


async def _body(request: Request):
    try:
        return await request.json()
    except ValueError:
        raise ValueError("JSON body required") from None


def http_routes(deps, endpoint) -> list[Route]:
    async def h_propose(request, actor):
        receipt, retry = await run_in_threadpool(op_propose, deps.dsn, deps.stages.embedder, actor,
                                                 await _body(request))
        return JSONResponse(receipt, status_code=200 if retry else 201)

    async def h_link(request, actor):
        result, created = await run_in_threadpool(op_link, deps.dsn, actor, await _body(request))
        return JSONResponse(result, status_code=201 if created else 200)

    return [Route("/v1/notes", endpoint(h_propose), methods=["POST"]),
            Route("/v1/notes/links", endpoint(h_link), methods=["POST"])]
