"""Postgres connection and a minimal forward-only migration runner."""
import os
from importlib.resources import files

import psycopg

DSN_ENV = "KUTUPHANE_DSN"


def connect(dsn: str | None = None) -> psycopg.Connection:
    """Autocommit, so every `conn.transaction()` block is a real transaction (not a savepoint inside an
    implicit one) and commits or rolls back on its own."""
    dsn = dsn or os.environ.get(DSN_ENV)
    if not dsn:
        raise RuntimeError(f"{DSN_ENV} is not set")
    return psycopg.connect(dsn, autocommit=True)


def _scripts():
    return sorted((f for f in files("kutuphane.migrations").iterdir() if f.name.endswith(".sql")), key=lambda f: f.name)


def pending(conn: psycopg.Connection) -> list[str]:
    exists = conn.execute("SELECT to_regclass('schema_migration')").fetchone()[0]
    done = {r[0] for r in conn.execute("SELECT name FROM schema_migration")} if exists else set()
    return [s.name for s in _scripts() if s.name not in done]


def migrate(conn: psycopg.Connection) -> list[str]:
    """Apply pending migrations in name order, each in its own transaction; return the applied names."""
    conn.execute("CREATE TABLE IF NOT EXISTS schema_migration (name text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())")
    done = {r[0] for r in conn.execute("SELECT name FROM schema_migration")}
    applied = []
    for script in _scripts():
        if script.name in done:
            continue
        with conn.transaction():
            conn.execute(script.read_text())
            conn.execute("INSERT INTO schema_migration (name) VALUES (%s)", (script.name,))
        applied.append(script.name)
    return applied
