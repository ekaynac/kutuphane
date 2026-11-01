"""Catalog writes and reads. One ingest is one transaction: either the new version is published or
nothing changes.

Quarantine (G3): a file that source.py could not extract is stored and listed but not indexed. It is recorded per
(content version, profile), like the chunks, so `book_state` and the publish result report the files of the
version being served. A later version that fixes the file (new bytes), or a reader that can extract it (new
profile), indexes it, and the quarantine of the old version no longer applies: nothing is carried over.

Accepted credential findings (`--accept-finding`, source.AcceptedFinding) are part of the publication record:
[{path, sha256, rule}] for this publication, shown by `book_state`. The matched text is never recorded.

Personal-data and fleet-data findings (datascan.py, G35) are a labelling question: the open ones (no acceptance)
are recorded in the publication as `data_findings` [{path, sha256, rule, lines}]. Publication refuses them only
when the book policy sends passages to cloud models (`_check_personal_data`, here, so every path that publishes
applies it: ingest and package approval, Astra review #19); an accepted one is in `accepted_findings`, like a
credential finding.

Skill scans (D71, skillscan.py): the skill folders are scanned before the transaction (a subprocess must not hold
the book lock); the records are written in it, so a block is in force as soon as the version is.

Publication facts (#160, migration 045): each publication records who stood behind it, `approved_by` and `channel`
(`ingest`, or `import` with its package_import row: the issuer key and the sequence). `publications` reads them for
the book list, the file list and citations; a publication from before migration 045 shows them as null."""
from dataclasses import dataclass, field

from psycopg.types.json import Jsonb

from . import agentfiles, authz, ids, kstd, passagemap, profiles, skillscan
from .policy import check_policy
from .source import SourceFile


@dataclass(frozen=True)
class Published:
    book: str
    content_id: str
    profile_id: str
    policy_id: str
    new_content: bool
    new_policy: bool
    quarantined: list[dict] = field(default_factory=list)  # [{path, reason}]: stored, listed, not indexed
    accepted_findings: list[dict] = field(default_factory=list)  # [{path, sha256, rule}]: reviewed scan findings
    data_findings: list[dict] = field(default_factory=list)  # [{path, sha256, rule, lines}]: open datascan findings
    skill_scans: list[dict] = field(default_factory=list)  # skillscan.summary() of the scans recorded + blocks carried
    passage_map: dict = field(default_factory=dict)  # passagemap.map_book() counts: the references that follow (#140)


def manifest_of(files: list[SourceFile]) -> list[dict]:
    return [{"path": f.path, "sha256": f.sha256, "size": len(f.data), "media_type": f.media_type,
             "okf_type": f.okf_type} for f in sorted(files, key=lambda f: f.path)]


def data_findings(files: list[SourceFile]) -> list[dict]:
    """The open datascan findings of the files, per path and rule; `text: extracted` when only the extracted text
    (HTML's visible text, a PDF's text layer) has them. Lines and rules only, never the matched text."""
    out = {}
    for f in sorted(files, key=lambda f: f.path):
        for where, finding in f.data_findings:
            entry = out.setdefault((f.path, finding.rule), {"path": f.path, "sha256": f.sha256, "rule": finding.rule,
                                                            "lines": []} | ({"text": "extracted"} if where else {}))
            entry["lines"].append(finding.line)
    return [out[k] for k in sorted(out)]


def _check_personal_data(files: list[SourceFile], policy: dict, manifest) -> None:
    """The cloud gate (G35): a `cloud_ok` book sends passages to cloud models, so an open personal-data finding in a
    file that can go to a model (no kstd.yaml, or `ai_use.ai_input: y`) refuses it until the operator reviews it.
    A `local_only` book only records the findings: personal data is a labelling question there."""
    if policy["egress"] != "cloud_ok":
        return
    refused = [f"{f.path}: personal-data findings in a cloud_ok book: "
               + ", ".join(f"line {d.line}{where} ({d.rule})" for where, d in sorted(f.data_findings,
                                                                                  key=lambda x: (x[1], x[0])))
               for f in sorted(files, key=lambda f: f.path)
               if f.data_findings and (manifest is None or kstd.allows(kstd.effective(manifest, f.path), "ai_input"))]
    if refused:
        example = refused[0].split(":", 1)[0]
        raise ValueError("; ".join(refused) + f"; the passages go to cloud models: review each finding, then accept "
                         f"it (--accept-finding {example}@sha256:<file digest>:<rule>), set ai_use.ai_input: n for "
                         f"the file in kstd.yaml, or publish with --egress local_only")


def publish(conn, *, book: str, title: str, files: list[SourceFile], policy: dict, profile: dict,
            approved_by: str | None = None, package_import: int | None = None) -> Published:
    """`approved_by`: the principal who publishes (`ingest`) or approves the package `package_import` (#160)."""
    if approved_by is not None and not authz.PRINCIPAL.match(approved_by):
        raise ValueError(f"approved_by must be a principal such as user:<name>, not {approved_by!r}")
    channel = None if approved_by is None else "import" if package_import is not None else "ingest"
    if len({f.path for f in files}) != len(files):
        raise ValueError("duplicate file paths: the content id would not cover every stored file")
    policy = check_policy(policy)
    content_id = ids.content_id({f.path: f.sha256 for f in files})
    policy_id = ids.policy_id(policy)
    profile = profiles.check_profile(profile)
    profile_id = ids.profile_id(profile)
    manifest = kstd.validate(files)  # a folder with kstd.yaml follows it; an invalid manifest blocks publication
    _check_personal_data(files, policy, manifest)  # before any write, on every publication path
    searchable = [f for f in files if f.path != kstd.MANIFEST and not f.quarantine
                  and (manifest is None or kstd.allows(kstd.effective(manifest, f.path), "search"))]
    skills = agentfiles.skill_dirs(f.path for f in files)
    chunks = [c for f in searchable for c in profiles.split(profile, f, skills)]
    quarantined = [{"path": f.path, "reason": f.quarantine} for f in sorted(files, key=lambda f: f.path)
                   if f.quarantine]
    accepted = [{"path": f.path, "sha256": f.sha256, "rule": rule} for f in sorted(files, key=lambda f: f.path)
                for rule in f.accepted]
    found = data_findings(files)
    fts = profile["settings"]["fts"]
    scans = skillscan.plan(conn, book, content_id, files)
    with conn.transaction():
        conn.execute("INSERT INTO book (slug, title) VALUES (%s, %s) ON CONFLICT (slug) DO NOTHING", (book, title))
        current = conn.execute("SELECT current_content, current_policy FROM book WHERE slug = %s FOR UPDATE",
                               (book,)).fetchone()
        if conn.execute("SELECT 1 FROM journal WHERE book = %s", (book,)).fetchone():
            # docs/24 §3, §23: a journal holds notes only; a content version would replace its profile and policy
            raise ValueError(f"{book} is a journal: it has notes, never a published content version")
        for f in files:
            conn.execute("INSERT INTO blob (sha256, data) VALUES (%s, %s) ON CONFLICT DO NOTHING", (f.sha256, f.data))
        conn.execute("INSERT INTO content_version (book, id, manifest) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                     (book, content_id, Jsonb(manifest_of(files))))
        from . import quotes, skills  # here: both import gate (via search), which imports this module
        skills.store(conn, book, content_id, files)  # the validated SKILL.md frontmatter (review #18)
        carried = skillscan.store(conn, book, content_id, scans, files)
        conn.execute("INSERT INTO policy_version (id, doc) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                     (policy_id, Jsonb(policy)))
        conn.execute("INSERT INTO profile_version (id, spec) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                     (profile_id, Jsonb(profile)))
        indexed = conn.execute("SELECT 1 FROM chunk WHERE book = %s AND content_id = %s AND profile_id = %s LIMIT 1",
                               (book, content_id, profile_id)).fetchone()
        if not indexed:
            with conn.cursor() as cur:
                cur.executemany(
                    "INSERT INTO chunk (book, content_id, profile_id, path, ordinal, page, line, start_char, end_char, "
                    "text, instruction, tsv) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, to_tsvector(%s::regconfig, %s))",
                    [(book, content_id, profile_id, c.path, c.ordinal, c.page, c.line, c.start, c.end, c.text,
                      c.instruction, fts, c.text) for c in chunks])
                cur.executemany(  # G23: the values a passage of another file can repeat (quotes.py)
                    "INSERT INTO record_value (book, content_id, profile_id, path, ordinal, sha256) "
                    "VALUES (%s, %s, %s, %s, %s, %s)", quotes.rows(book, content_id, profile_id, chunks))
                cur.executemany(
                    "INSERT INTO quarantine (book, content_id, profile_id, path, reason) VALUES (%s, %s, %s, %s, %s) "
                    "ON CONFLICT DO NOTHING", [(book, content_id, profile_id, q["path"], q["reason"])
                                               for q in quarantined])
        conn.execute("UPDATE book SET title = %s, current_content = %s, current_profile = %s, current_policy = %s, "
                     "updated_at = now() WHERE slug = %s", (title, content_id, profile_id, policy_id, book))
        mapped = passagemap.map_book(conn, book)  # #140: cited and linked passages of earlier versions follow to it
        conn.execute("INSERT INTO publication (book, content_id, profile_id, policy_id, accepted_findings, "
                     "data_findings, approved_by, channel, package_import) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                     (book, content_id, profile_id, policy_id, Jsonb(accepted), Jsonb(found), approved_by, channel,
                      package_import))
    return Published(book, content_id, profile_id, policy_id, new_content=current[0] != content_id,
                     new_policy=current[1] != policy_id, quarantined=quarantined, accepted_findings=accepted,
                     data_findings=found, skill_scans=skillscan.summary(scans) + carried, passage_map=mapped)


def book_state(conn, book: str) -> dict | None:
    row = conn.execute("SELECT b.slug, b.title, b.current_content, b.current_policy, p.doc, c.manifest, b.current_profile "
                       "FROM book b LEFT JOIN policy_version p ON p.id = b.current_policy "
                       "LEFT JOIN content_version c ON c.book = b.slug AND c.id = b.current_content "
                       "WHERE b.slug = %s", (book,)).fetchone()
    if not row:
        return None
    versions = [r[0] for r in conn.execute("SELECT id FROM content_version WHERE book = %s ORDER BY created_at",
                                           (book,))]
    pubs = [{"content_id": c, "profile_id": pf, "policy_id": pl, "published_at": t.isoformat(), "accepted_findings": a,
             "data_findings": d, "approved_by": by, "channel": ch}
            for c, pf, pl, t, a, d, by, ch in conn.execute("SELECT content_id, profile_id, policy_id, published_at, "
                                                           "accepted_findings, data_findings, approved_by, channel "
                                                           "FROM publication WHERE book = %s ORDER BY id", (book,))]
    quarantined = [{"path": p, "reason": r} for p, r in conn.execute(
        "SELECT path, reason FROM quarantine WHERE book = %s AND content_id = %s AND profile_id = %s ORDER BY path",
        (book, row[2], row[6]))]
    return {"book": row[0], "title": row[1], "content_id": row[2], "profile_id": row[6], "policy_id": row[3],
            "policy": row[4], "files": row[5], "quarantined": quarantined, "content_versions": versions,
            "publications": pubs}


def publications(conn, keys) -> dict:
    """{(book, content_id, profile_id): publication facts} of the latest publication of each version (#160)."""
    keys = sorted(set(keys))
    rows = conn.execute(
        "SELECT DISTINCT ON (p.book, p.content_id, p.profile_id) p.book, p.content_id, p.profile_id, p.published_at, "
        "p.channel, p.approved_by, i.issuer, i.sequence FROM publication p "
        "JOIN unnest(%s::text[], %s::text[], %s::text[]) AS k(book, content_id, profile_id) "
        "ON (p.book, p.content_id, p.profile_id) = (k.book, k.content_id, k.profile_id) "
        "LEFT JOIN package_import i ON i.id = p.package_import "
        "ORDER BY p.book, p.content_id, p.profile_id, p.id DESC",
        ([k[0] for k in keys], [k[1] for k in keys], [k[2] for k in keys]))
    return {(b, c, pf): {"content_id": c, "published_at": t.isoformat(), "channel": ch, "approved_by": by,
                         "issuer_key": key, "sequence": seq}
            for b, c, pf, t, ch, by, key, seq in rows}


def books(conn, slugs) -> list[dict]:
    """The book list entries (#159) of `slugs`, by slug: a journal has no content version and no publication."""
    rows = conn.execute("SELECT b.slug, b.title, j.book IS NOT NULL, b.current_content, b.current_profile, "
                        "b.current_policy FROM book b LEFT JOIN journal j ON j.book = b.slug "
                        "WHERE b.slug = ANY(%s) ORDER BY b.slug", (list(slugs),)).fetchall()
    pubs = publications(conn, [(r[0], r[3], r[4]) for r in rows if r[3] is not None])
    return [{"book": slug, "title": title, "kind": "journal" if journal else "book", "content_id": content,
             "profile_id": profile, "policy_id": policy, "publication": pubs.get((slug, content, profile))}
            for slug, title, journal, content, profile, policy in rows]


def files_page(conn, book: str, content_id: str, profile_id: str, cursor: str | None, limit: int) -> list[dict]:
    """Up to `limit` manifest entries of one version after the path `cursor`, by path, each with its passage count
    in `profile_id` (0: not indexed)."""
    rows = conn.execute(
        "SELECT m.entry->>'path', m.entry->>'sha256', (m.entry->>'size')::bigint, m.entry->>'media_type', "
        "(SELECT count(*) FROM chunk k WHERE k.book = c.book AND k.content_id = c.id AND k.profile_id = %s "
        " AND k.path = m.entry->>'path') "
        "FROM content_version c CROSS JOIN LATERAL jsonb_array_elements(c.manifest) AS m(entry) "
        "WHERE c.book = %s AND c.id = %s AND (%s::text IS NULL OR m.entry->>'path' COLLATE \"C\" > %s) "
        "ORDER BY m.entry->>'path' COLLATE \"C\" LIMIT %s",
        (profile_id, book, content_id, cursor, cursor, limit))
    return [{"path": p, "sha256": s, "size": n, "media_type": t, "passages": k} for p, s, n, t, k in rows]


def current_policy(conn, book: str) -> str | None:
    row = conn.execute("SELECT current_policy FROM book WHERE slug = %s", (book,)).fetchone()
    return row[0] if row else None


def manifest_entry(conn, book: str, content_id: str, path: str) -> dict | None:
    row = conn.execute("SELECT m.entry FROM content_version c "
                       "CROSS JOIN LATERAL jsonb_array_elements(c.manifest) AS m(entry) "
                       "WHERE c.book = %s AND c.id = %s AND m.entry->>'path' = %s", (book, content_id, path)).fetchone()
    return row[0] if row else None


def skill_dirs(conn, book: str, content_id: str) -> frozenset[str]:
    """agentfiles.skill_dirs() of one content version: the K3 rule needs the whole file list, not one entry."""
    rows = conn.execute("SELECT m.entry->>'path' FROM content_version c "
                        "CROSS JOIN LATERAL jsonb_array_elements(c.manifest) AS m(entry) "
                        "WHERE c.book = %s AND c.id = %s", (book, content_id))
    return agentfiles.skill_dirs(p for (p,) in rows)


def skill_files(conn, book: str, content_id: str, path: str) -> list[str]:
    """The paths of the innermost skill folder (K3: a folder with a SKILL.md) that holds `path`, nested skills
    included: the whole skill that one of its files stands for (review #18, the rule of skills.py). `[path]` when
    the file is in no skill folder."""
    paths = [p for (p,) in conn.execute("SELECT m.entry->>'path' FROM content_version c "
                                        "CROSS JOIN LATERAL jsonb_array_elements(c.manifest) AS m(entry) "
                                        "WHERE c.book = %s AND c.id = %s", (book, content_id))]
    holders = [d for d in agentfiles.skill_dirs(paths) if agentfiles.relative(d, path) is not None]
    if not holders:
        return [path]
    folder = max(holders, key=lambda d: -1 if d == "." else d.count("/"))
    return sorted(p for p in paths if agentfiles.relative(folder, p) is not None)


def read_file(conn, book: str, content_id: str, path: str) -> bytes | None:
    """Bytes of one file in a specific content version (old versions stay readable, AT-07)."""
    row = conn.execute("SELECT b.data FROM content_version c "
                       "CROSS JOIN LATERAL jsonb_array_elements(c.manifest) AS m(entry) "
                       "JOIN blob b ON b.sha256 = m.entry->>'sha256' "
                       "WHERE c.book = %s AND c.id = %s AND m.entry->>'path' = %s", (book, content_id, path)).fetchone()
    return bytes(row[0]) if row else None
