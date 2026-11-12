"""#143 (option b, operator decision 2026-10-28): `license: unknown` permits derivation inside this installation, with
a notice; an export (package) of such an item, or of a note derived from it, is refused (docs/11 §4 rule 3, §5.2)."""
import pytest

from kutuphane import catalog, decisions, kstd, notes, packages, profiles, signing
from kutuphane.source import read_source
from test_kstd import POLICY, write_manifest
from test_notes import J, U, allow, http, journal, mcp, propose
from test_outcomes import decide

UNKNOWN_POLICY_FILE = {"rights": {"license": "unknown"}}
PATH = "politika/veri-saklama.md"


@pytest.fixture
def key(tmp_path):
    signing.generate(tmp_path / "a.key")
    return signing.load_private(tmp_path / "a.key")


def publish(conn, root, **manifest):
    write_manifest(root, **manifest)
    out = catalog.publish(conn, book="kitap", title="kitap", files=read_source(root), policy=POLICY,
                          profile=profiles.spec("chunked"))
    allow(conn, "kitap", "read")
    return out


def passage(conn, path) -> str:
    row = conn.execute("SELECT book, content_id, profile_id, path, ordinal FROM chunk WHERE book = 'kitap' "
                       "AND path = %s ORDER BY ordinal LIMIT 1", (path,)).fetchone()
    return f"{row[0]}@{row[1]}/{row[2]}/{row[3]}#{row[4]}"


def test_check_warning_names_the_rule(okf_dir):
    files = read_source(okf_dir)
    text = kstd.init(files, "ACME <kb@acme.example>")
    _errors, warnings = kstd.check(kstd.parse(text.encode()), {f.path: f.sha256 for f in files})
    [warning] = [w for w in warnings if "no default license" in w]
    assert "derived from in this installation" in warning and "never exported" in warning


def test_export_refuses_a_file_with_license_unknown(conn, okf_dir, key):
    publish(conn, okf_dir, policy_item=UNKNOWN_POLICY_FILE)
    with pytest.raises(packages.PackageError, match=f"license unknown.*{PATH}"):
        packages.export(conn, "kitap", key)


def test_export_with_every_license_stated_goes_on(conn, okf_dir, key):
    publish(conn, okf_dir)
    assert packages.export(conn, "kitap", key)


def test_a_note_derived_from_license_unknown_is_written_with_a_notice(conn, okf_dir):
    publish(conn, okf_dir, policy_item=UNKNOWN_POLICY_FILE)
    journal(conn)
    allow(conn, J, "read", "propose")
    cited = propose(conn, mcp(), text="Retention is in the policy", citations=[passage(conn, PATH)])
    assert cited["status"] == "created" and cited["licence_notice"]["paths"] == [f"kitap/{PATH}"]
    derived = propose(conn, mcp(), text="Derived from the note", links=[{"type": "derived_from", "ref": cited["ref"]}])
    assert derived["licence_notice"]["paths"] == [f"kitap/{PATH}"]                  # through the note lineage
    clean = propose(conn, mcp(), text="Runbook says restore weekly",
                    citations=[passage(conn, "runbook/yedek-geri-yukleme.md")])
    assert "licence_notice" not in clean
    assert notes.unknown_licence(conn, []) == {}


def test_the_notice_never_names_a_file_the_caller_cannot_read(conn, okf_dir):
    """Astra review #20: a reader of the journal derives from a note whose source book it cannot read; the notice
    keeps the inherited rule but names no path in that book."""
    publish(conn, okf_dir, policy_item=UNKNOWN_POLICY_FILE)
    journal(conn)
    allow(conn, J, "read", "propose")
    cited = propose(conn, mcp(), text="Retention is in the policy", citations=[passage(conn, PATH)])
    allow(conn, J, "read", "propose", user="user:mehmet", agent=None)
    derived = propose(conn, http("user:mehmet"), text="Derived from the note",
                      links=[{"type": "derived_from", "ref": cited["ref"]}])
    assert derived["licence_notice"]["paths"] == [] and derived["licence_notice"]["unreadable"] == 1
    assert derived["licence_notice"]["note"] == notes.LICENCE_NOTICE


def test_the_decision_export_leaves_out_notes_derived_from_license_unknown(conn, okf_dir):
    publish(conn, okf_dir, policy_item=UNKNOWN_POLICY_FILE)
    journal(conn)
    allow(conn, J, "read", "propose")
    base = propose(conn, mcp(), text="From the policy", citations=[passage(conn, PATH)])
    out = decide(conn, mcp(), "Keep logs 90 days", ["a", "b"], "a",
                 links=[{"type": "derived_from", "ref": base["ref"]}])
    ok = decide(conn, mcp(), "Restore weekly", ["a", "b"], "b",
                citations=[passage(conn, "runbook/yedek-geri-yukleme.md")])
    records, summary = decisions.export(conn, mcp(), [J])
    assert [r["ref"] for r in records] == [ok["ref"]] and out["ref"] != ok["ref"]
    assert summary["licence_unknown"] == 1


# --- #223: content without a kstd.yaml states no license, so it is `unknown` (as for export and pack, #218) -------------

def publish_plain(conn, root):
    out = catalog.publish(conn, book="kitap", title="kitap", files=read_source(root), policy=POLICY,
                          profile=profiles.spec("chunked"))
    allow(conn, "kitap", "read")
    return out


def test_a_note_citing_content_without_kstd_yaml_has_a_notice_and_is_left_out_of_both_exports(conn, okf_dir):
    from kutuphane import journalexport
    from kutuphane.gate import Actor
    from test_journal_export import M, make, note
    from test_notes import U
    publish_plain(conn, okf_dir)
    journal(conn)
    allow(conn, J, "read", "propose")
    cited = propose(conn, mcp(), text="Retention is in the policy", citations=[passage(conn, PATH)])
    assert cited["licence_notice"]["paths"] == [f"kitap/{PATH}"]
    records, summary = journalexport.export(conn, Actor(U), J)
    assert records == [] and summary["licence_unknown"] == 1
    decide(conn, mcp(), "Keep logs 90 days", ["a", "b"], "a", citations=[passage(conn, PATH)])
    records, summary = decisions.export(conn, mcp(), [J])
    assert records == [] and summary["licence_unknown"] == 1


def test_a_note_citing_licensed_content_is_exported(conn, okf_dir):
    from conftest import licensed
    from kutuphane import journalexport
    from kutuphane.gate import Actor
    publish_plain(conn, licensed(okf_dir))
    journal(conn)
    allow(conn, J, "read", "propose")
    cited = propose(conn, mcp(), text="Retention is in the policy", citations=[passage(conn, PATH)])
    assert "licence_notice" not in cited
    records, summary = journalexport.export(conn, Actor(U), J)
    assert len(records) == 1 and summary["licence_unknown"] == 0
    state = catalog.book_state(conn, "kitap")
    assert not kstd.Rights(conn).license_unknown("kitap", state["content_id"], kstd.MANIFEST)  # no license to state
