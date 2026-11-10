"""#200: `kutuphane agent add` gives an agent its journals in one call: each named journal exists (a new one gets the
private defaults), the agent gets propose + read on each, the curator gets curate + read on each. It needs the owner
credential, it is all or nothing, and a second run adds only what is missing."""
import json
import os

import pytest

from kutuphane import authz, catalog, cli, db, profiles
from kutuphane.policy import make_policy
from kutuphane.source import read_source

CURATOR = "user:ekaynac"


@pytest.fixture
def owner(conn, monkeypatch):
    monkeypatch.setenv(db.DSN_ENV, os.environ["KUTUPHANE_TEST_DSN"])
    monkeypatch.setenv(db.CURATOR_DSN_ENV, os.environ["KUTUPHANE_TEST_DSN"])
    monkeypatch.delenv("KUTUPHANE_DEV", raising=False)
    return conn


def add(capsys, *args) -> tuple[int, dict | str]:
    code = cli.main(["agent", "add", *args])
    out = capsys.readouterr()
    return code, (json.loads(out.out) if code == 0 else out.err)


def live_grants(conn) -> set:
    return set(conn.execute("SELECT object, relation, subject FROM grant_tuple WHERE revoked_at IS NULL").fetchall())


def journals(conn) -> dict:
    return {r[0]: r[1:] for r in conn.execute(
        "SELECT j.book, j.search, j.ai_input, j.train, j.created_by, p.doc FROM journal j JOIN book b ON b.slug = j.book "
        "JOIN policy_version p ON p.id = b.current_policy").fetchall()}


def test_four_calls_give_the_omp_setup(owner, capsys):  # the acceptance of #200: nobetci-mcp/ops/README.md
    for name in ("nobetci-supervisor", "omp-kutuphane", "omp-adc"):
        assert add(capsys, name, "--journal", "--shared", "omp-shared", "--curator", CURATOR)[0] == 0
    code, out = add(capsys, "omp-default", "--shared", "omp-shared", "--curator", CURATOR)
    assert code == 0 and out["principal"] == "agent:omp-default"
    assert out["journals"] == [{"book": "omp-shared", "created": False}]
    own = {"nobetci-supervisor", "omp-kutuphane", "omp-adc"}
    expected = {(f"book:{p}", m, f"agent:{p}") for p in own for m in ("propose", "read")}
    expected |= {("book:omp-shared", m, f"agent:{p}") for p in own | {"omp-default"} for m in ("propose", "read")}
    expected |= {(f"book:{b}", m, CURATOR) for b in own | {"omp-shared"} for m in ("curate", "read")}
    assert live_grants(owner) == expected
    private = {"v": 1, "sensitivity": "restricted", "egress": "local_only", "protection": "standard"}
    assert journals(owner) == {b: (True, True, False, CURATOR, private) for b in own | {"omp-shared"}}


def test_a_second_run_adds_only_what_is_missing(owner, capsys):
    code, first = add(capsys, "omp-kutuphane", "--journal", "--curator", CURATOR)
    assert code == 0 and first["journals"] == [{"book": "omp-kutuphane", "created": True}]
    authz.revoke(owner, "book:omp-kutuphane", "propose", "agent:omp-kutuphane")
    code, again = add(capsys, "omp-kutuphane", "--journal", "--curator", CURATOR)
    assert code == 0 and again["journals"] == [{"book": "omp-kutuphane", "created": False}]
    ids = {(g["object"], g["mode"], g["subject"]): g["id"] for g in first["grants"]}
    changed = [g for g in again["grants"] if ids[(g["object"], g["mode"], g["subject"])] != g["id"]]
    assert [(g["mode"], g["subject"]) for g in changed] == [("propose", "agent:omp-kutuphane")]
    assert len(live_grants(owner)) == 4


def test_it_needs_the_owner_credential(owner, monkeypatch, capsys):
    monkeypatch.delenv(db.CURATOR_DSN_ENV)
    code, err = add(capsys, "omp-kutuphane", "--journal", "--curator", CURATOR)
    assert code == 2 and db.CURATOR_DSN_ENV in err
    assert journals(owner) == {} and live_grants(owner) == set()


def test_a_refusal_writes_nothing(owner, okf_dir, capsys):
    catalog.publish(owner, book="kitap", title="kitap", files=read_source(okf_dir),
                    policy=make_policy(sensitivity="normal", egress="local_only", protection="standard"),
                    profile=profiles.spec("chunked"))
    code, err = add(capsys, "omp-x", "--journal", "--shared", "kitap", "--curator", CURATOR)
    assert code == 2 and "kitap is not a journal" in err
    assert add(capsys, "omp-x", "--journal", "--curator", "agent:omp-boss")[0] == 2   # curate is for people only
    assert "--journal or --shared" in add(capsys, "omp-x", "--curator", CURATOR)[1]
    assert journals(owner) == {} and live_grants(owner) == set()


def test_the_token_line_follows_the_machine(owner, monkeypatch, capsys):
    _, out = add(capsys, "omp-x", "--journal", "--curator", CURATOR)
    assert "dev-token" not in out["token"] and "without an IdP" in out["token"]
    monkeypatch.setenv("KUTUPHANE_DEV", "1")
    monkeypatch.setenv("KUTUPHANE_OIDC_ISSUER", "http://127.0.0.1:8091/dev")
    _, out = add(capsys, "omp-x", "--journal", "--curator", CURATOR)
    assert out["token"] == ("KUTUPHANE_DEV=1 kutuphane dev-token omp-x --agent --client-id omp-x "
                            "--private-key <dev-private.pem> --issuer http://127.0.0.1:8091/dev")
