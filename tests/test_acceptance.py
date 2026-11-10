"""D85 (S1): the acceptance record of a book version and the strict publish gate. `ingest`, `approve-import` and
`reject-import` need the owner credential and `curate` on the book for `--by`; a refused command publishes nothing."""
import getpass
import os

import pytest

from kutuphane import authz, catalog, cli, db, llmdap, packages, profiles, signing
from kutuphane.policy import make_policy
from kutuphane.source import read_source

POLICY = make_policy(sensitivity="normal", egress="local_only", protection="standard")
ME = f"user:{getpass.getuser()}"


@pytest.fixture
def env(conn, okf_dir, monkeypatch):
    """The CLI runs against the test database as the app credential; the owner credential is set per test."""
    monkeypatch.setenv(db.DSN_ENV, os.environ["KUTUPHANE_TEST_DSN"])
    monkeypatch.delenv(db.CURATOR_DSN_ENV, raising=False)
    monkeypatch.delenv(llmdap.EMBED_ENV["route"], raising=False)
    return conn


def owner(monkeypatch):
    monkeypatch.setenv(db.CURATOR_DSN_ENV, os.environ["KUTUPHANE_TEST_DSN"])


def ingest(okf_dir, *by):
    return cli.main(["ingest", str(okf_dir), "--book", "kitap", "--sensitivity", "normal", "--egress", "local_only",
                     "--protection", "standard", *by])


def versions(conn):
    return conn.execute("SELECT count(*) FROM publication").fetchone()[0]


def test_ingest_without_the_owner_credential_is_refused(env, okf_dir, capsys):
    authz.grant(env, "book:kitap", "curate", ME)
    assert ingest(okf_dir) == 2
    assert db.CURATOR_DSN_ENV in capsys.readouterr().err and versions(env) == 0


def test_ingest_without_curate_for_the_person_is_refused_and_names_the_fix(env, okf_dir, monkeypatch, capsys):
    owner(monkeypatch)
    assert ingest(okf_dir, "--by", "user:ayse") == 2
    err = capsys.readouterr().err
    assert "kutuphane grant book:kitap curate user:ayse" in err and db.CURATOR_DSN_ENV in err
    assert versions(env) == 0 and catalog.book_state(env, "kitap") is None
    assert ingest(okf_dir, "--by", "agent:kobra-7") == 2 and versions(env) == 0  # curate is held by users only


def test_ingest_by_a_curator_records_operator_cli_not_legacy(env, okf_dir, monkeypatch):
    owner(monkeypatch)
    authz.grant(env, "book:kitap", "curate", "user:ayse")  # the grant comes first: it is accepted for a new book
    assert ingest(okf_dir, "--by", "user:ayse") == 0
    [pub] = catalog.book_state(env, "kitap")["publications"]
    assert pub["acceptance"] == {"kind": "operator_cli", "by": "user:ayse", "at": pub["published_at"],
                                 "legacy": False}


@pytest.fixture
def received(env, okf_dir, tmp_path, conn_b, monkeypatch):
    """A verified package in installation B (the CLI works on its schema), from a book published at A."""
    authz.grant(env, "book:kitap", "curate", "user:admin")
    catalog.publish(env, book="kitap", title="Kitap", files=read_source(okf_dir), policy=POLICY,
                    profile=profiles.spec("chunked"), approved_by="user:admin")
    info = signing.generate(tmp_path / "a.key")
    packages.trust(conn_b, open(info["public_key"], "rb").read(), expected_fingerprint=info["fingerprint"],
                   name="A", by="user:admin")
    monkeypatch.setenv(db.DSN_ENV, os.environ["KUTUPHANE_TEST_DSN"] + "?options=-csearch_path%3Dinstall_b,public")
    return conn_b, packages.receive(conn_b, packages.export(env, "kitap", signing.load_private(tmp_path / "a.key")))


def approve_args(import_id, by="user:ayse"):
    return ["approve-import", str(import_id), "--by", by, "--sensitivity", "normal", "--egress", "local_only",
            "--protection", "standard"]


def test_approve_import_is_refused_without_the_owner_credential_or_curate_and_can_be_retried(received, monkeypatch,
                                                                                            capsys):
    conn_b, pkg = received
    assert cli.main(approve_args(pkg["id"])) == 2                             # no owner credential
    assert db.CURATOR_DSN_ENV in capsys.readouterr().err
    monkeypatch.setenv(db.CURATOR_DSN_ENV, os.environ[db.DSN_ENV])  # the owner credential, on installation B
    assert cli.main(approve_args(pkg["id"])) == 2                             # no curate for the person
    assert "kutuphane grant book:kitap curate user:ayse" in capsys.readouterr().err
    assert versions(conn_b) == 0 and catalog.book_state(conn_b, "kitap") is None
    assert conn_b.execute("SELECT status FROM package_import WHERE id = %s", (pkg["id"],)).fetchone() == ("verified",)
    authz.grant(conn_b, "book:kitap", "curate", "user:ayse")                  # the fix, then the retry
    assert cli.main(approve_args(pkg["id"])) == 0
    [pub] = catalog.book_state(conn_b, "kitap")["publications"]
    assert pub["acceptance"]["kind"] == "operator_cli" and pub["acceptance"]["by"] == "user:ayse"
    assert pub["acceptance"]["legacy"] is False and pub["channel"] == "import"


def test_reject_import_is_refused_without_the_owner_credential_or_curate(received, monkeypatch, capsys):
    conn_b, pkg = received
    reject = ["reject-import", str(pkg["id"]), "--by", "user:ayse", "--reason", "no"]
    assert cli.main(reject) == 2 and db.CURATOR_DSN_ENV in capsys.readouterr().err
    monkeypatch.setenv(db.CURATOR_DSN_ENV, os.environ[db.DSN_ENV])
    assert cli.main(reject) == 2 and "curate user:ayse" in capsys.readouterr().err
    status = "SELECT status FROM package_import WHERE id = %s"
    assert conn_b.execute(status, (pkg["id"],)).fetchone() == ("verified",)
    authz.grant(conn_b, "book:kitap", "curate", "user:ayse")
    assert cli.main(reject) == 0 and conn_b.execute(status, (pkg["id"],)).fetchone() == ("rejected",)


def test_the_internal_path_without_a_person_records_none_and_checks_nothing(conn, okf_dir):
    catalog.publish(conn, book="kitap", title="Kitap", files=read_source(okf_dir), policy=POLICY,
                    profile=profiles.spec("chunked"))
    assert conn.execute("SELECT acceptance, acceptance_legacy, approved_by FROM publication").fetchone() == (
        "none", False, None)
