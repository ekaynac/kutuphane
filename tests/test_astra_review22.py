"""Astra review #22 (docs/08): the regressions of findings 1-5."""
from datetime import datetime, timedelta, timezone

import psycopg
import pytest
from psycopg.types.json import Jsonb

from kutuphane import catalog, curatorqueue, decisions, ids, journalexport, passkey, profiles, source
from kutuphane.gate import Actor
from kutuphane.source import read_source
from test_journal_export import M, make, note
from test_note_import import PRIVATE
from test_notes import LOCAL, U, allow, env, handle  # noqa: F401


# Finding 1: the D73 tables are history; the decider read functions are gone.
@pytest.mark.parametrize("table", ["note_suggestion", "curate_delegation", "delegation_use", "delegation_end"])
def test_d73_tables_take_no_new_rows(conn, table):
    with pytest.raises(psycopg.errors.RaiseException, match="history"):
        conn.execute(f"INSERT INTO {table} DEFAULT VALUES")


def test_decider_functions_are_dropped(conn):
    assert conn.execute("SELECT count(*) FROM pg_proc WHERE proname IN ('decider_notes', 'delegation_next')"
                        ).fetchone()[0] == 0


# Finding 3: a stored delegate or end_delegation act still has an effect check.
class _Rows:
    def __init__(self, rows):
        self.rows = rows

    def execute(self, *_):
        return self

    def fetchall(self):
        return self.rows


def test_historical_delegation_acts_have_effect_checks():
    assert passkey.EFFECTS["delegate"](_Rows([(True,)]), 1, {}) is True
    assert passkey.EFFECTS["end_delegation"](_Rows([("dl_1", "revoked")]), 1, {"delegation": "dl_1"}) is True
    assert passkey.EFFECTS["end_delegation"](_Rows([("dl_2", "revoked")]), 1, {"delegation": "dl_1"}) is False
    assert "delegate" not in passkey.ACTIONS and "end_delegation" not in passkey.ACTIONS


# Finding 4: a path that no passage handle can name is refused at ingestion.
@pytest.mark.parametrize("path", ["a\tb.md", "a\nb.md", "docs/x\x7f.txt"])
def test_control_character_path_is_refused(path):
    with pytest.raises(source.SourceError, match="control character"):
        source.read_file(path, b"text\n")


# Finding 5: a historical model approval is not counted as a system event.
def test_report_keeps_delegated_approvals_apart(env):
    now = datetime.now(timezone.utc)
    decided = curatorqueue.report(env, now - timedelta(days=1), now + timedelta(minutes=1))["decided_by"]
    assert set(decided) == {"people_web", "people_cli", "delegations", "system"}


# Finding 2: a source book or the journal that becomes restricted during the export refuses it.
def _restrict(conn, okf_dir):
    catalog.publish(conn, book="kitap", title="kitap", files=read_source(okf_dir), policy=PRIVATE,
                    profile=profiles.spec("chunked"))


def test_journal_export_refused_when_a_source_becomes_restricted(env, okf_dir, monkeypatch):
    make(env)
    allow(env, M, "read", "propose")
    note(env, "Cited", citations=[handle(env, "kitap")])
    original = journalexport._records

    def racing(conn, book, w):
        out = original(conn, book, w)
        _restrict(conn, okf_dir)  # a policy change that commits between the work and the final decision
        return out
    monkeypatch.setattr(journalexport, "_records", racing)
    with pytest.raises(ValueError, match="became restricted"):
        journalexport.export(env, Actor(U), M)


def test_journal_export_refused_when_the_journal_becomes_restricted(env, monkeypatch):
    make(env)
    allow(env, M, "read", "propose")
    note(env, "Plain")
    original = journalexport._records

    def racing(conn, book, w):
        out = original(conn, book, w)
        conn.execute("UPDATE book SET current_policy = (SELECT id FROM policy_version "
                     "WHERE doc->>'sensitivity' = 'restricted' LIMIT 1) WHERE slug = %s", (book,))
        return out
    env.execute("INSERT INTO policy_version (id, doc) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                (ids.policy_id(PRIVATE), Jsonb(PRIVATE)))
    monkeypatch.setattr(journalexport, "_records", racing)
    with pytest.raises(ValueError, match="became restricted"):
        journalexport.export(env, Actor(U), M)


def test_decision_export_refused_when_a_source_becomes_restricted(env, okf_dir, monkeypatch):
    make(env)
    allow(env, M, "read", "propose")
    note(env, "Pick", kind="decision_proposal", citations=[handle(env, "kitap")],
         decision={"options": ["a", "b"], "choice": "a"})
    original = decisions._records

    def racing(conn, actor, books):
        out = original(conn, actor, books)
        _restrict(conn, okf_dir)
        return out
    monkeypatch.setattr(decisions, "_records", racing)
    with pytest.raises(ValueError, match="became restricted"):
        decisions.export(env, Actor(U), [M])
