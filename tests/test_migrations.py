"""Upgrades from older schemas with real-looking data (Astra review #3: 006 must not fail on legacy rows)."""
from importlib.resources import files

from kutuphane import db


def _scripts():
    return sorted((f for f in files("kutuphane.migrations").iterdir() if f.name.endswith(".sql")), key=lambda f: f.name)


def test_upgrade_from_005_with_duplicate_correlations(conn):
    conn.execute("DROP SCHEMA public CASCADE")
    conn.execute("CREATE SCHEMA public")
    conn.execute("CREATE TABLE schema_migration (name text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())")
    for script in _scripts():
        if script.name >= "006":
            break
        conn.execute(script.read_text())
        conn.execute("INSERT INTO schema_migration (name) VALUES (%s)", (script.name,))
    for _ in range(2):  # the old client sent one correlation id for every call of a request
        conn.execute("INSERT INTO model_call (correlation_id, principal, route, model, derived_correlation_id) "
                     "VALUES ('req-1', 'user:ayse', 'local', 'qwen', 'abcd:req-1')")
    applied = db.migrate(conn)
    assert "006_audit_detail.sql" in applied
    rows = conn.execute("SELECT call_id, derived_correlation_id FROM model_call ORDER BY id").fetchall()
    assert len({r[0] for r in rows}) == 2 and all(r[0].startswith("req-1.legacy-") for r in rows)
    assert {r[1] for r in rows} == {"abcd:req-1"}  # what LLMDAP recorded is kept


def test_upgrade_to_011_marks_legacy_agent_chunks_as_instructions(conn):  # G5: the K3 rule, also for stored rows
    from psycopg.types.json import Jsonb
    from kutuphane import agentfiles
    conn.execute("DROP SCHEMA public CASCADE")
    conn.execute("CREATE SCHEMA public")
    db.migrate(conn)
    applied = [s.name for s in _scripts() if s.name >= "011"]
    conn.execute("DROP TABLE quarantine")
    conn.execute("ALTER TABLE chunk DROP COLUMN line")
    conn.execute("DELETE FROM schema_migration WHERE name = ANY(%s)", (applied,))
    paths = ["index.md", "AGENTS.md.hostile", "docs/claude.local.md", "kurallar/stil.mdc", "py.instructions.md",
             ".claude/agents/x.md", "alt/.codex/p.md", "araclar/ozet/SKILL.md", "araclar/ozet/scripts/run.sh",
             "araclar/ozetler.md", "skills/matris.md", "araclar_ozet/x.md"]
    conn.execute("INSERT INTO profile_version (id, spec) VALUES ('pf_old', '{}')")
    conn.execute("INSERT INTO book (slug, title) VALUES ('eski', 'eski')")
    conn.execute("INSERT INTO content_version (book, id, manifest) VALUES ('eski', 'ct_old', %s)",
                 (Jsonb([{"path": p, "okf_type": None} for p in paths]),))
    for p in paths:
        conn.execute("INSERT INTO chunk (book, content_id, profile_id, path, ordinal, start_char, end_char, text, "
                     "instruction, tsv) VALUES ('eski', 'ct_old', 'pf_old', %s, 0, 0, 1, 'x', false, ''::tsvector)", (p,))
    assert db.migrate(conn) == applied
    flags = dict(conn.execute("SELECT path, instruction FROM chunk").fetchall())
    skills = agentfiles.skill_dirs(paths)
    assert flags == {p: agentfiles.is_instruction({"path": p}, skills) for p in paths}
    assert {p for p, v in flags.items() if not v} == {"index.md", "araclar/ozetler.md", "skills/matris.md",
                                                      "araclar_ozet/x.md"}
