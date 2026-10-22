"""Catalog writes and reads. One ingest is one transaction: either the new version is published or
nothing changes."""
from dataclasses import dataclass

from psycopg.types.json import Jsonb

from . import ids, kstd, profiles
from .policy import check_policy
from .source import SourceFile


def whole_profile() -> dict:
    return profiles.spec("whole")


@dataclass(frozen=True)
class Published:
    book: str
    content_id: str
    profile_id: str
    policy_id: str
    new_content: bool
    new_policy: bool


def manifest_of(files: list[SourceFile]) -> list[dict]:
    return [{"path": f.path, "sha256": f.sha256, "size": len(f.data), "media_type": f.media_type,
             "okf_type": f.okf_type} for f in sorted(files, key=lambda f: f.path)]


def publish(conn, *, book: str, title: str, files: list[SourceFile], policy: dict, profile: dict) -> Published:
    if len({f.path for f in files}) != len(files):
        raise ValueError("duplicate file paths: the content id would not cover every stored file")
    policy = check_policy(policy)
    content_id = ids.content_id({f.path: f.sha256 for f in files})
    policy_id = ids.policy_id(policy)
    profile = profiles.check_profile(profile)
    profile_id = ids.profile_id(profile)
    manifest = kstd.validate(files)  # a folder with kstd.yaml follows it; an invalid manifest blocks publication
    searchable = [f for f in files if manifest is None or kstd.allows(kstd.effective(manifest, f.path), "search")]
    chunks = [c for f in searchable for c in profiles.split(profile, f)]
    fts = profile["settings"]["fts"]
    with conn.transaction():
        conn.execute("INSERT INTO book (slug, title) VALUES (%s, %s) ON CONFLICT (slug) DO NOTHING", (book, title))
        current = conn.execute("SELECT current_content, current_policy FROM book WHERE slug = %s FOR UPDATE",
                               (book,)).fetchone()
        for f in files:
            conn.execute("INSERT INTO blob (sha256, data) VALUES (%s, %s) ON CONFLICT DO NOTHING", (f.sha256, f.data))
        conn.execute("INSERT INTO content_version (book, id, manifest) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                     (book, content_id, Jsonb(manifest_of(files))))
        conn.execute("INSERT INTO policy_version (id, doc) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                     (policy_id, Jsonb(policy)))
        conn.execute("INSERT INTO profile_version (id, spec) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                     (profile_id, Jsonb(profile)))
        indexed = conn.execute("SELECT 1 FROM chunk WHERE book = %s AND content_id = %s AND profile_id = %s LIMIT 1",
                               (book, content_id, profile_id)).fetchone()
        if not indexed:
            with conn.cursor() as cur:
                cur.executemany(
                    "INSERT INTO chunk (book, content_id, profile_id, path, ordinal, page, start_char, end_char, text, "
                    "instruction, tsv) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, to_tsvector(%s::regconfig, %s))",
                    [(book, content_id, profile_id, c.path, c.ordinal, c.page, c.start, c.end, c.text, c.instruction,
                      fts, c.text) for c in chunks])
        conn.execute("UPDATE book SET title = %s, current_content = %s, current_profile = %s, current_policy = %s, "
                     "updated_at = now() WHERE slug = %s", (title, content_id, profile_id, policy_id, book))
        conn.execute("INSERT INTO publication (book, content_id, profile_id, policy_id) VALUES (%s, %s, %s, %s)",
                     (book, content_id, profile_id, policy_id))
    return Published(book, content_id, profile_id, policy_id,
                     new_content=current[0] != content_id, new_policy=current[1] != policy_id)


def book_state(conn, book: str) -> dict | None:
    row = conn.execute("SELECT b.slug, b.title, b.current_content, b.current_policy, p.doc, c.manifest, b.current_profile "
                       "FROM book b LEFT JOIN policy_version p ON p.id = b.current_policy "
                       "LEFT JOIN content_version c ON c.book = b.slug AND c.id = b.current_content "
                       "WHERE b.slug = %s", (book,)).fetchone()
    if not row:
        return None
    versions = [r[0] for r in conn.execute("SELECT id FROM content_version WHERE book = %s ORDER BY created_at",
                                           (book,))]
    pubs = [{"content_id": c, "profile_id": pf, "policy_id": pl, "published_at": t.isoformat()}
            for c, pf, pl, t in conn.execute("SELECT content_id, profile_id, policy_id, published_at FROM publication "
                                             "WHERE book = %s ORDER BY id", (book,))]
    return {"book": row[0], "title": row[1], "content_id": row[2], "profile_id": row[6], "policy_id": row[3],
            "policy": row[4], "files": row[5], "content_versions": versions, "publications": pubs}


def current_policy(conn, book: str) -> str | None:
    row = conn.execute("SELECT current_policy FROM book WHERE slug = %s", (book,)).fetchone()
    return row[0] if row else None


def manifest_entry(conn, book: str, content_id: str, path: str) -> dict | None:
    row = conn.execute("SELECT m.entry FROM content_version c "
                       "CROSS JOIN LATERAL jsonb_array_elements(c.manifest) AS m(entry) "
                       "WHERE c.book = %s AND c.id = %s AND m.entry->>'path' = %s", (book, content_id, path)).fetchone()
    return row[0] if row else None


def read_file(conn, book: str, content_id: str, path: str) -> bytes | None:
    """Bytes of one file in a specific content version (old versions stay readable, AT-07)."""
    row = conn.execute("SELECT b.data FROM content_version c "
                       "CROSS JOIN LATERAL jsonb_array_elements(c.manifest) AS m(entry) "
                       "JOIN blob b ON b.sha256 = m.entry->>'sha256' "
                       "WHERE c.book = %s AND c.id = %s AND m.entry->>'path' = %s", (book, content_id, path)).fetchone()
    return bytes(row[0]) if row else None
