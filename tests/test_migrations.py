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
