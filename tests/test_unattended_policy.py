"""#235: the unattended use policy. A curator sets it for one book and one trusted key, with no attester. A clean
package of that key is published with no person and no attestation, recorded as acceptance `policy`
(`approved_by` and `decided_by` are `policy:<id>`). The Q8 exclusions hold as for an attested policy. Excluding
`policy` content is the consumer's selection (the `acceptance` filter of search and ask), not a server gate."""
import json
import os

import pytest
from starlette.testclient import TestClient

from conftest import licensed  # noqa: F401
from kutuphane import authz, catalog, cli, db, gate, packages, profiles, search, server, signing, usepolicy
from kutuphane.policy import make_policy
from kutuphane.source import read_source
from test_server import PUBLIC, bearer, keys, verifier  # noqa: F401 (fixtures)
from test_egress_audit import FakeBridge
from test_use_policy import ATT, CLEAN, SITE, build, run, status, world  # noqa: F401 (fixtures)

POLICY = make_policy(sensitivity="normal", egress="local_only", protection="standard")


def unattended(world, *, by="user:ayse", key=None, book="kitap"):
    conn, _, fp, _ = world
    return usepolicy.add(conn, book, key or fp, [], sensitivity="normal", egress="local_only",
                         protection="standard", by=by, unattended=True)


def test_an_unattended_policy_publishes_a_clean_package_as_policy(world):
    conn = world[0]
    pid = unattended(world)
    got = packages.receive(conn, build(world, CLEAN, accepted_by=None))  # no attestation at all
    assert got["status"] == "verified" and got["findings"] == []
    [result] = run(conn)
    assert result["status"] == "published" and result["use_policy"] == pid
    assert status(conn, got["id"]) == ("published", f"policy:{pid}")
    [pub] = catalog.book_state(conn, "kitap")["publications"]
    assert pub["acceptance"] == {"kind": "policy", "by": f"policy:{pid}", "at": pub["published_at"], "legacy": False}
    assert conn.execute("SELECT approved_by, acceptance, use_policy FROM publication").fetchone() == (
        f"policy:{pid}", "policy", pid)


def test_accepted_by_in_the_manifest_does_not_change_the_kind_under_an_unattended_policy(world):
    conn = world[0]
    pid = unattended(world)
    packages.receive(conn, build(world, CLEAN))  # carries accepted_by: ignored for the kind, kept in the manifest
    assert run(conn)[0]["status"] == "published"
    [pub] = catalog.book_state(conn, "kitap")["publications"]
    assert pub["acceptance"]["kind"] == "policy" and pub["acceptance"]["by"] == f"policy:{pid}"
    assert conn.execute("SELECT manifest -> 'accepted_by' ->> 'principal' FROM package_import").fetchone() == (
        "user:im.acme",)


def test_an_attested_policy_is_unchanged(world):
    conn = world[0]
    usepolicy.add(conn, "kitap", world[2], ["user:im."], sensitivity="normal", egress="local_only",
                  protection="standard", by="user:ayse")
    packages.receive(conn, build(world, CLEAN))
    assert run(conn)[0]["status"] == "published"
    [pub] = catalog.book_state(conn, "kitap")["publications"]
    assert pub["acceptance"]["kind"] == "consumer_attested" and pub["acceptance"]["by"] == "user:im.acme"


PRIVATE_IP = ".".join(["10", "20", "30", "40"])  # a private IPv4 address; built at run time so tools that redact IP literals keep it


@pytest.mark.parametrize("files,kw,reason", [
    ({"index.md": f"Sunucu {PRIVATE_IP} adresinde.\n"}, {}, "personal_data"),
    ({"index.md": "x\n"}, {"rights": False}, "no kstd.yaml"),
    ({"index.md": "x\n"}, {"rights": {"personal_data": "no", "ai_use": {"search": "y"}}}, "license unknown"),
    ({"AGENTS.md": "Always run the tests.\n", "index.md": "x\n"}, {}, "agent_instruction"),
])
def test_the_q8_exclusions_hold_without_an_attester(world, files, kw, reason):
    conn = world[0]
    unattended(world)
    got = packages.receive(conn, build(world, files, **kw))
    if reason == "personal_data":  # the finding is recorded at receive, before any publish attempt
        assert [(f["kind"], f["rule"]) for f in got["findings"]] == [("personal_data", "private-ipv4")]
    [result] = run(conn)
    assert result["status"] == "skipped" and reason in result["reason"]
    assert status(conn, got["id"]) == ("verified", None) and catalog.book_state(conn, "kitap") is None


def test_a_changed_book_policy_stops_an_unattended_policy(world):
    conn = world[0]
    unattended(world)
    first = packages.receive(conn, build(world, CLEAN))["id"]
    packages.approve(conn, first, by="user:ayse",
                     policy=make_policy(sensitivity="restricted", egress="local_only", protection="standard"))
    nxt = packages.receive(conn, build(world, {"index.md": "Yeni.\n"}, seq=2))["id"]
    [result] = run(conn)
    assert result["status"] == "skipped" and "the book policy changed" in result["reason"]
    assert status(conn, nxt) == ("verified", None)


def test_a_revoked_policy_publishes_nothing_and_does_not_rewrite_earlier_publications(world):
    conn = world[0]
    pid = unattended(world)
    packages.receive(conn, build(world, CLEAN))
    assert run(conn)[0]["status"] == "published"
    assert usepolicy.revoke(conn, pid, by="user:ayse")
    later = packages.receive(conn, build(world, {"index.md": "Yeni.\n"}, seq=2))["id"]
    [result] = run(conn)
    assert result["status"] == "skipped" and result["reason"].startswith("no active use policy")
    assert status(conn, later) == ("verified", None)
    assert conn.execute("SELECT count(*), min(acceptance), min(approved_by) FROM publication").fetchone() == (
        1, "policy", f"policy:{pid}")


def test_another_key_waits(world, tmp_path):
    conn, _, _, _ = world
    unattended(world)
    other = signing.generate(tmp_path / "b.key")
    packages.trust(conn, open(other["public_key"], "rb").read(), expected_fingerprint=other["fingerprint"],
                   name="B", by="user:admin")
    pkg = packages.pack(read_source(_folder(tmp_path)), book="kitap", title="Kitap",
                        key=signing.load_private(tmp_path / "b.key"), sequence=1, policy=POLICY)
    got = packages.receive(conn, pkg)
    [result] = run(conn)
    assert result["status"] == "skipped" and result["reason"].startswith("no active use policy")
    assert status(conn, got["id"]) == ("verified", None)


def _folder(tmp_path):
    root = tmp_path / "other"
    root.mkdir(exist_ok=True)
    (root / "index.md").write_text("# Kitap\n\nKayıtlar bir yıl saklanır.\n", encoding="utf-8")
    licensed(root)
    return root


def test_add_refusals_for_the_unattended_form(world, monkeypatch, capsys):
    conn, _, key, _ = world
    base = ["use-policy", "add", "kitap", "--key", key, "--sensitivity", "normal", "--egress", "local_only",
            "--protection", "standard", "--by", "user:ayse"]
    assert cli.main([*base, "--unattended", "--attester", "user:im."]) == 2  # exclusive
    assert "not both" in capsys.readouterr().err
    assert cli.main(base) == 2 and "not neither" in capsys.readouterr().err  # one is required
    assert cli.main([*base[:-1], "user:nobody", "--unattended"]) == 2 and "curate" in capsys.readouterr().err
    restricted = [("restricted" if a == "normal" else a) for a in base]
    assert cli.main([*restricted, "--unattended"]) == 2 and "restricted" in capsys.readouterr().err
    assert conn.execute("SELECT count(*) FROM use_policy").fetchone() == (0,)
    monkeypatch.delenv(db.CURATOR_DSN_ENV)
    assert cli.main([*base, "--unattended"]) == 2 and db.CURATOR_DSN_ENV in capsys.readouterr().err
    monkeypatch.setenv(db.CURATOR_DSN_ENV, os.environ[db.DSN_ENV])
    assert cli.main([*base, "--unattended"]) == 0
    capsys.readouterr()
    assert cli.main(["use-policy", "list", "kitap"]) == 0
    assert json.loads(capsys.readouterr().out)[0]["unattended"] is True
    row = conn.execute("SELECT unattended, attesters FROM use_policy").fetchone()
    assert row == (True, [])


def test_the_database_keeps_attesters_and_the_unattended_flag_together(world):
    import psycopg
    conn = world[0]
    with pytest.raises(psycopg.errors.CheckViolation):
        conn.execute("INSERT INTO use_policy (book, issuer, attesters, policy, created_by, unattended) "
                     "VALUES ('kitap', %s, '{}', '{}', 'user:ayse', false)", (world[2],))
    with pytest.raises(psycopg.errors.CheckViolation):
        conn.execute("INSERT INTO publication (book, content_id, profile_id, policy_id, acceptance, approved_by) "
                     "VALUES ('k', 'c', 'p', 'l', 'policy', 'user:x')")


# --- the read paths: the kind is shown or selected on them, never gated by the server -------------------------------

@pytest.fixture
def published(conn, tmp_path):
    """`kitap` published under an unattended policy and `duz` by a person, on the main schema; both readable by U."""
    info = signing.generate(tmp_path / "a.key")
    packages.trust(conn, open(info["public_key"], "rb").read(), expected_fingerprint=info["fingerprint"], name="A",
                   by="user:admin")
    authz.grant(conn, "book:kitap", "curate", "user:ayse")
    authz.grant(conn, "book:duz", "curate", "user:ayse")
    w = (conn, signing.load_private(tmp_path / "a.key"), info["fingerprint"], tmp_path)
    pid = unattended(w)
    packages.receive(conn, build(w, CLEAN))
    assert run(conn)[0]["status"] == "published"
    catalog.publish(conn, book="duz", title="Duz", files=read_source(_folder(tmp_path)), policy=POLICY,
                    profile=profiles.spec("chunked"), approved_by="user:ayse")
    for book in ("kitap", "duz"):
        authz.grant(conn, f"book:{book}", "read", "user:ayse")
    return pid


def test_search_and_ask_can_select_by_kind(conn, published):
    actor = gate.Actor("user:ayse")

    def books(kinds):
        return {h.citation.book for h in search.search(conn, actor, "Kayıtlar",
                                                       scope=search.Scope.of(acceptances=kinds))}
    assert books(None) == {"kitap", "duz"}
    assert books(["policy"]) == {"kitap"}
    assert books(["curator_passkey", "operator_cli", "consumer_attested"]) == {"duz"}


@pytest.fixture
def client(published, verifier):
    app = server.create_app(dsn=os.environ["KUTUPHANE_TEST_DSN"], verifier=verifier, bridge=None, model=None,
                            public_url=PUBLIC)
    with TestClient(app) as c:
        yield c


def test_http_search_filter_and_the_other_paths_show_the_kind(client, keys, published):
    h = bearer(keys, sub="ayse")
    params = {"q": "Kayıtlar saklanır"}
    kept = client.get("/v1/search", params={**params, "acceptance": "policy"}, headers=h).json()["results"]
    assert kept and all(r["citation"].startswith("kitap@") for r in kept)
    cut = client.get("/v1/search", params={**params, "acceptance": ["consumer_attested", "operator_cli"]},
                     headers=h).json()["results"]
    assert all(not r["citation"].startswith("kitap@") for r in cut)
    assert "acceptance" not in kept[0]  # a hit does not show the kind
    books = {b["book"]: b for b in client.get("/v1/books", headers=h).json()["books"]}
    assert books["kitap"]["publication"]["acceptance"]["kind"] == "policy"
    assert books["duz"]["publication"]["acceptance"]["kind"] == "operator_cli"
    files = client.get("/v1/books/kitap/files", headers=h).json()
    assert files["publication"]["acceptance"]["kind"] == "policy"
    handle = kept[0]["citation"]
    cited = client.get("/v1/citation", params={"handle": handle}, headers=h).json()
    assert cited["publication"]["acceptance"]["kind"] == "policy" and cited["publication"]["acceptance"]["by"] == (
        f"policy:{published}")
    content = files["content_id"]
    doc = client.get(f"/v1/files/kitap/{content}/index.md", headers=h)
    assert doc.status_code == 200 and "acceptance" not in doc.text  # read_document shows nothing of the kind


@pytest.fixture
def fake():
    f = FakeBridge()
    yield f
    f.server.shutdown()


def test_ask_selects_by_kind_before_the_model_sees_a_passage(conn, published, fake):
    from kutuphane import answers
    actor = gate.Actor("user:ayse")
    fake.reply = "Kayıtlar bir yıl saklanır [1]."

    def ask(kinds):
        result = answers.ask(conn, fake.bridge(), actor, "Kayıtlar ne kadar saklanır?", model="qwen",
                             scope=search.Scope.of(acceptances=kinds))
        return result, fake.last_body["messages"][1]["content"]
    result, prompt = ask(["curator_passkey", "operator_cli", "consumer_attested"])
    assert "(duz/" in prompt and "kitap/" not in prompt  # the `policy` book is not in the model input
    assert {c["book"] for c in result["citations"]} == {"duz"}
    result, prompt = ask(["policy"])
    assert "(kitap/" in prompt and "duz/" not in prompt
    assert {c["book"] for c in result["citations"]} == {"kitap"}


def test_a_direct_handle_of_an_old_policy_version_still_says_policy(client, keys, conn, published, tmp_path):
    h = bearer(keys, sub="ayse")
    old = client.get("/v1/search", params={"q": "Kayıtlar saklanır", "acceptance": "policy"},
                     headers=h).json()["results"][0]["citation"]
    root = tmp_path / "v2"
    root.mkdir()
    (root / "index.md").write_text("# Kitap\n\nKayıtlar iki yıl saklanır.\n", encoding="utf-8")
    catalog.publish(conn, book="kitap", title="Kitap", files=read_source(licensed(root)), policy=POLICY,
                    profile=profiles.spec("chunked"), approved_by="user:ayse")  # a person: the current version
    books = {b["book"]: b for b in client.get("/v1/books", headers=h).json()["books"]}
    assert books["kitap"]["publication"]["acceptance"]["kind"] == "operator_cli"
    cited = client.get("/v1/citation", params={"handle": old}, headers=h).json()
    assert cited["publication"]["acceptance"]["kind"] == "policy"
    assert cited["publication"]["acceptance"]["by"] == f"policy:{published}"  # records are not rewritten
    assert conn.execute("SELECT count(*) FROM publication WHERE acceptance = 'policy'").fetchone() == (1,)


@pytest.mark.parametrize("suggestion", [
    {"v": 1, "sensitivity": "normal", "egress": "cloud_ok", "protection": "standard"},
    {"v": 1, "sensitivity": "restricted", "egress": "local_only", "protection": "standard"},
    "restricted",
])
def test_a_package_that_suggests_a_restricted_or_cloud_ok_book_waits_for_a_person(world, suggestion):
    """The receiver would apply the use policy's normal/local_only; the sender holds the content to be more
    sensitive, so a person decides (earliest point: admission, before any write)."""
    conn = world[0]
    unattended(world)
    got = packages.receive(conn, build(world, CLEAN, extra={"policy_suggestion": suggestion}))
    assert got["status"] == "verified"
    [result] = run(conn)
    assert result["status"] == "skipped" and "does not suggest a normal, local_only book" in result["reason"]
    assert status(conn, got["id"]) == ("verified", None) and catalog.book_state(conn, "kitap") is None


def test_a_cloud_ok_book_stops_an_unattended_policy(world):
    conn = world[0]
    unattended(world)
    first = packages.receive(conn, build(world, CLEAN))["id"]
    packages.approve(conn, first, by="user:ayse",
                     policy=make_policy(sensitivity="normal", egress="cloud_ok", protection="standard"))
    nxt = packages.receive(conn, build(world, {"index.md": "Yeni.\n"}, seq=2))["id"]
    [result] = run(conn)
    assert result["status"] == "skipped" and "the book policy changed" in result["reason"]
    assert status(conn, nxt) == ("verified", None)


def test_the_database_refuses_unattended_with_attesters_and_a_policy_publication_of_another_use_policy(world):
    import psycopg
    conn = world[0]
    with pytest.raises(psycopg.errors.CheckViolation):
        conn.execute("INSERT INTO use_policy (book, issuer, attesters, policy, created_by, unattended) "
                     "VALUES ('kitap', %s, '{user:im.}', '{}', 'user:ayse', true)", (world[2],))
    pid = unattended(world)
    with pytest.raises(psycopg.errors.CheckViolation):  # approved_by names another policy than its use_policy
        conn.execute("INSERT INTO publication (book, content_id, profile_id, policy_id, acceptance, approved_by, "
                     "use_policy) VALUES ('k', 'c', 'p', 'l', 'policy', %s, %s)", (f"policy:{pid + 1}", pid))


def test_migration_054_keeps_existing_attested_policies_and_their_publications(conn):
    """Database at 053 (the 054 changes undone): an attested policy and its `consumer_attested` publication stay as
    they are, and the policy is not unattended."""
    from kutuphane import db
    conn.execute("ALTER TABLE publication DROP CONSTRAINT publication_policy_kind, "
                 "DROP CONSTRAINT publication_use_policy, DROP CONSTRAINT publication_approved_by_check")
    conn.execute("ALTER TABLE publication ADD CONSTRAINT publication_approved_by_check "
                 "CHECK (approved_by ~ '^(user|agent|role):[a-z0-9][a-z0-9._@-]{0,121}$'), "
                 "ADD CONSTRAINT publication_use_policy CHECK ((acceptance = 'consumer_attested') = "
                 "(use_policy IS NOT NULL))")
    conn.execute("ALTER TABLE use_policy DROP CONSTRAINT use_policy_unattended, DROP COLUMN unattended")
    conn.execute("ALTER TABLE use_policy ADD CONSTRAINT use_policy_attesters_check CHECK (cardinality(attesters) > 0)")
    conn.execute("DELETE FROM schema_migration WHERE name = '054_unattended_use_policy.sql'")
    conn.execute("INSERT INTO trusted_key (fingerprint, public_key, name, added_by) VALUES ('k', '\\x00', 'A', "
                 "'user:admin')")
    pid = conn.execute("INSERT INTO use_policy (book, issuer, attesters, policy, created_by) VALUES ('kitap', 'k', "
                       "'{user:im.}', '{}', 'user:ayse') RETURNING id").fetchone()[0]
    conn.execute("INSERT INTO profile_version (id, spec) VALUES ('pf_old', '{}')")
    conn.execute("INSERT INTO policy_version (id, doc) VALUES ('pl_old', '{}')")
    conn.execute("INSERT INTO book (slug, title) VALUES ('kitap', 'kitap')")
    conn.execute("INSERT INTO content_version (book, id, manifest) VALUES ('kitap', 'ct_old', '[]')")
    imp = conn.execute("INSERT INTO package_import (status, package) VALUES ('published', '\\x00') "
                       "RETURNING id").fetchone()[0]
    conn.execute("INSERT INTO publication (book, content_id, profile_id, policy_id, acceptance, approved_by, channel, "
                 "package_import, use_policy) VALUES ('kitap', 'ct_old', 'pf_old', 'pl_old', 'consumer_attested', "
                 "'user:im.acme', 'import', %s, %s)", (imp, pid))
    pubs = "SELECT book, acceptance, approved_by, use_policy, acceptance_legacy FROM publication"
    before = conn.execute(pubs).fetchall(), conn.execute("SELECT id, attesters, policy FROM use_policy").fetchall()
    assert db.migrate(conn) == ["054_unattended_use_policy.sql"]
    assert (conn.execute(pubs).fetchall(), conn.execute("SELECT id, attesters, policy FROM use_policy").fetchall()
            ) == before
    assert conn.execute("SELECT unattended FROM use_policy").fetchall() == [(False,)]


@pytest.mark.parametrize("how", [{"drop": ["policy_suggestion"]}, {"extra": {"policy_suggestion": None}},
                                 {"extra": {"policy_suggestion": "normal"}},
                                 {"extra": {"policy_suggestion": {"sensitivity": "normal"}}}])
def test_an_unattended_policy_fails_closed_on_a_missing_null_or_malformed_suggestion(world, how):
    """`receive` does not require `policy_suggestion`, so such a package is verified; the policy must not publish it."""
    conn = world[0]
    unattended(world)
    got = packages.receive(conn, build(world, CLEAN, **how))
    assert got["status"] == "verified"
    [result] = run(conn)
    assert result["status"] == "skipped" and "does not suggest a normal, local_only book" in result["reason"]
    assert status(conn, got["id"]) == ("verified", None) and catalog.book_state(conn, "kitap") is None


@pytest.mark.parametrize("how", [
    {"extra": {"policy_suggestion": {"v": 1, "sensitivity": "normal", "egress": "cloud_ok", "protection": "standard"}}},
    {"extra": {"policy_suggestion": {"v": 1, "sensitivity": "restricted", "egress": "local_only",
                                     "protection": "standard"}}},
    {"drop": ["policy_suggestion"]}, {"extra": {"policy_suggestion": None}},
    {"extra": {"policy_suggestion": "normal"}},
    {"extra": {"policy_suggestion": {"sensitivity": "normal"}}}],
    ids=["cloud_ok", "restricted", "missing", "null", "string", "incomplete"])
def test_an_attested_policy_waits_for_a_person_on_a_suggestion_that_is_not_normal_local_only(world, how):
    """#246: the same rule as for an unattended policy; the sender's request for stricter handling is not dropped."""
    conn = world[0]
    usepolicy.add(conn, "kitap", world[2], ["user:im."], sensitivity="normal", egress="local_only",
                  protection="standard", by="user:ayse")
    got = packages.receive(conn, build(world, CLEAN, **how))
    assert got["status"] == "verified"
    [result] = run(conn)
    assert result["status"] == "skipped" and "does not suggest a normal, local_only book" in result["reason"]
    assert status(conn, got["id"]) == ("verified", None) and catalog.book_state(conn, "kitap") is None


def test_an_attested_policy_publishes_a_package_that_suggests_normal_local_only(world):
    conn = world[0]
    usepolicy.add(conn, "kitap", world[2], ["user:im."], sensitivity="normal", egress="local_only",
                  protection="standard", by="user:ayse")
    packages.receive(conn, build(world, CLEAN))
    assert run(conn)[0]["status"] == "published"
    assert catalog.book_state(conn, "kitap")["policy"] == POLICY
