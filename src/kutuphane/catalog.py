"""Catalog writes and reads (M1a). One ingest is one transaction: either the new version is published or
nothing changes."""
from dataclasses import dataclass
from importlib.metadata import version

from psycopg.types.json import Jsonb

from . import ids
from .source import SourceFile

READER_VERSION = 1  # bump when source.py's validation/recording semantics change


def whole_profile() -> dict:
    """The M1a default profile: documents served whole. Chunked profiles arrive with search (M1d)."""
    return {"name": "whole", "components": {"reader": f"kutuphane.source@{READER_VERSION}",
                                            "pdf": f"pypdf@{version('pypdf')}"}}


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
    content_id = ids.content_id({f.path: f.sha256 for f in files})
    policy_id = ids.policy_id(policy)
    profile_id = ids.profile_id(profile)
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
        conn.execute("UPDATE book SET title = %s, current_content = %s, current_policy = %s, updated_at = now() "
                     "WHERE slug = %s", (title, content_id, policy_id, book))
    return Published(book, content_id, profile_id, policy_id,
                     new_content=current[0] != content_id, new_policy=current[1] != policy_id)


def book_state(conn, book: str) -> dict | None:
    row = conn.execute("SELECT b.slug, b.title, b.current_content, b.current_policy, p.doc, c.manifest "
                       "FROM book b LEFT JOIN policy_version p ON p.id = b.current_policy "
                       "LEFT JOIN content_version c ON c.book = b.slug AND c.id = b.current_content "
                       "WHERE b.slug = %s", (book,)).fetchone()
    if not row:
        return None
    versions = [r[0] for r in conn.execute("SELECT id FROM content_version WHERE book = %s ORDER BY created_at",
                                           (book,))]
    return {"book": row[0], "title": row[1], "content_id": row[2], "policy_id": row[3], "policy": row[4],
            "files": row[5], "content_versions": versions}


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
