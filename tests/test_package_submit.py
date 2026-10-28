"""#139 (option 2): a consumer application submits a signed package over HTTP or MCP; the same verification as CLI
`receive` runs; a person approves with the CLI (`approve-import`); only changed passages embed again. The submitter
needs `propose` on the target book (no new grant mode); the issuer is the verified signature (D74); the submitter is
recorded from the verified token (D70)."""
import asyncio
import base64
import json
import os

import pytest
from starlette.testclient import TestClient

from kutuphane import authz, catalog, packages, profiles, server, signing, vectors
from kutuphane.policy import make_policy
from kutuphane.source import read_source
from test_identity import token
from test_kstd import write_manifest
from test_server import PUBLIC, call_tool, keys, verifier  # noqa: F401
from test_egress_audit import FakeBridge
from test_vectors import current_texts, embedded_inputs

AGENT = "agent:inframedic"
POLICY = make_policy(sensitivity="normal", egress="local_only", protection="standard")


@pytest.fixture
def fake():
    f = FakeBridge()
    yield f
    f.server.shutdown()


@pytest.fixture
def signer(tmp_path):
    info = signing.generate(tmp_path / "a.key")
    return signing.load_private(tmp_path / "a.key"), info


@pytest.fixture
def b_dsn(conn_b):
    return os.environ["KUTUPHANE_TEST_DSN"] + "?options=-csearch_path%3Dinstall_b,public"


@pytest.fixture
def setup(conn, conn_b, okf_dir, signer, verifier, b_dsn):
    """Installation A (the consumer, e.g. InfraMedic) signs its book; installation B trusts A's key."""
    private, info = signer
    write_manifest(okf_dir)
    catalog.publish(conn, book="runbooks", title="Runbooks", files=read_source(okf_dir), policy=POLICY,
                    profile=profiles.spec("chunked"))
    pem = open(info["public_key"], "rb").read()
    packages.trust(conn_b, pem, expected_fingerprint=info["fingerprint"], name="InfraMedic", by="user:admin")
    app = server.create_app(dsn=b_dsn, verifier=verifier, bridge=None, model=None, public_url=PUBLIC)
    return app, packages.export(conn, "runbooks", private), info["fingerprint"]


def agent_auth(keys):  # noqa: F811
    return {"Authorization": "Bearer " + token(keys, sub="inframedic", azp="inframedic",
                                               **{"kutuphane/principal_type": "agent"})}


def test_submit_needs_propose_on_the_book_and_stores_nothing_without_it(setup, keys, conn_b):  # noqa: F811
    app, pkg, _ = setup
    with TestClient(app) as client:
        r = client.post("/v1/packages", content=pkg, headers=agent_auth(keys))
    assert r.status_code == 403
    assert conn_b.execute("SELECT count(*) FROM package_import").fetchone()[0] == 0
    assert conn_b.execute("SELECT allowed, mode, object FROM access_event WHERE action = 'submit_package'"
                          ).fetchall() == [(False, "propose", "book:runbooks")]


def test_submit_over_http_then_a_person_approves_and_only_changed_passages_embed(setup, keys, conn, conn_b,  # noqa: F811
                                                                                okf_dir, signer, fake):
    app, pkg, issuer = setup
    authz.grant(conn_b, "book:runbooks", "propose", AGENT)
    authz.grant(conn_b, "book:runbooks", "read", AGENT)  # the diff names catalog files: it needs read
    with TestClient(app) as client:
        auth = agent_auth(keys)
        r = client.post("/v1/packages", content=pkg, headers={**auth, "content-type": "application/x-tar"})
        assert r.status_code == 201, r.text
        receipt = r.json()
        assert receipt["status"] in ("received", "findings") and receipt["book"] == "runbooks"
        assert receipt["issuer"] == issuer and receipt["diff"]["added"]
        assert catalog.book_state(conn_b, "runbooks") is None                    # nothing published yet
        assert client.get(f"/v1/packages/{receipt['id']}", headers=auth).json() == receipt
        other = {"Authorization": "Bearer " + token(keys, sub="mehmet")}
        assert client.get(f"/v1/packages/{receipt['id']}", headers=other).status_code == 404
        assert conn_b.execute("SELECT issuer, submitted_by, submitted_for, submitted_channel, submitted_client_id "
                              "FROM package_import WHERE id = %s", (receipt["id"],)).fetchone() == (
            issuer, AGENT, None, "http", "inframedic")

        # approve-import stays a human CLI act: no route approves
        assert client.post(f"/v1/packages/{receipt['id']}", headers=auth).status_code in (404, 405)
        first = packages.approve(conn_b, receipt["id"], by="user:admin", policy=POLICY)
        vectors.index(conn_b, fake.embedder(), "runbooks")
        assert client.get(f"/v1/packages/{receipt['id']}", headers=auth).json()["status"] == "approved"

        # a new version with one changed file: only its passages embed again (G17)
        changed = "runbook/yedek-geri-yukleme.md"
        with open(okf_dir / changed, "a", encoding="utf-8") as f:
            f.write("\n5. Geri yükleme süresini olay kaydına yaz.\n")
        write_manifest(okf_dir)
        catalog.publish(conn, book="runbooks", title="Runbooks", files=read_source(okf_dir), policy=POLICY,
                        profile=profiles.spec("chunked"))
        second = client.post("/v1/packages", content=packages.export(conn, "runbooks", signer[0]), headers=auth).json()
        assert second["status"] in ("received", "findings")
        assert second["diff"]["changed"] == ["kstd.yaml", changed]
        authz.grant(conn_b, "book:runbooks", "read", "user:ayse")
        reader = {"Authorization": "Bearer " + token(keys)}

        def found():
            hits = client.get("/v1/search", params={"q": "geri yükleme süresini olay kaydına"}, headers=reader)
            return any("olay kaydına" in h["text"] for h in hits.json()["results"])
        assert not found()                                                       # pending: search does not see it
        since = len(fake.requests)
        published = packages.approve(conn_b, second["id"], by="user:admin", policy=POLICY)
        assert published.content_id != first.content_id
        result = vectors.index(conn_b, fake.embedder(), "runbooks")
        rows, sent = current_texts(conn_b, "runbooks"), embedded_inputs(fake, since)
        assert sent and set(sent) <= {t for p, _, t in rows if p == changed}
        assert result.embedded == len(sent) and result.reused == len(rows) - len(sent) > 0
        assert found()                                                           # approved: search sees it


def test_propose_without_read_gets_no_catalog_diff(setup, keys, conn_b):  # noqa: F811
    """Astra review #20: the diff lists the receiving catalog's files (removed) and is an equality oracle (changed):
    `propose` alone gets the status without it; a current `read` shows it."""
    app, pkg, _ = setup
    authz.grant(conn_b, "book:runbooks", "propose", AGENT)
    with TestClient(app) as client:
        auth = agent_auth(keys)
        receipt = client.post("/v1/packages", content=pkg, headers=auth).json()
        assert receipt["status"] in ("received", "findings") and receipt["diff"] is None
        assert client.get(f"/v1/packages/{receipt['id']}", headers=auth).json()["diff"] is None
        authz.grant(conn_b, "book:runbooks", "read", AGENT)
        assert client.get(f"/v1/packages/{receipt['id']}", headers=auth).json()["diff"]["added"]


def test_a_failed_verification_is_kept_and_reported_refused(setup, keys, conn_b):  # noqa: F811
    app, pkg, _ = setup
    authz.grant(conn_b, "book:runbooks", "propose", AGENT)
    with TestClient(app) as client:
        auth = agent_auth(keys)
        first = client.post("/v1/packages", content=pkg, headers=auth)
        assert first.status_code == 201
        packages.approve(conn_b, first.json()["id"], by="user:admin", policy=POLICY)
        again = client.post("/v1/packages", content=pkg, headers=auth)
        assert again.status_code == 201 and client.get(f"/v1/packages/{again.json()['id']}",
                                                       headers=auth).json() == again.json()
    assert again.json()["status"] == "refused" and "replay" in again.json()["reasons"][0]
    assert again.json()["issuer"] is None                                  # a refused package proves no issuer


def test_size_limit_and_unreadable_input(setup, keys, conn_b, monkeypatch):  # noqa: F811
    app, pkg, _ = setup
    monkeypatch.setattr(packages, "MAX_PACKAGE_BYTES", len(pkg) - 1)
    with TestClient(app) as client:
        assert client.post("/v1/packages", content=pkg, headers=agent_auth(keys)).status_code == 413
        monkeypatch.undo()
        assert client.post("/v1/packages", content=b"not a tar", headers=agent_auth(keys)).status_code == 400
    assert conn_b.execute("SELECT count(*) FROM package_import").fetchone()[0] == 0


def test_a_journal_is_never_a_package_target(setup, keys, conn_b, okf_dir, signer, conn):  # noqa: F811
    from kutuphane import notes
    app, _, _ = setup
    notes.create_journal(conn_b, book="runbooks", title="j", search=True, ai_input=True, policy=POLICY,
                         by="user:admin")
    authz.grant(conn_b, "book:runbooks", "propose", AGENT)
    with TestClient(app) as client:
        r = client.post("/v1/packages", content=packages.export(conn, "runbooks", signer[0]), headers=agent_auth(keys))
    assert r.status_code == 400 and "journal" in r.json()["error"]


def test_submit_package_and_package_status_over_mcp(setup, keys, verifier, conn_b, b_dsn):  # noqa: F811
    _app, pkg, issuer = setup
    authz.grant(conn_b, "book:runbooks", "propose", AGENT)
    mcp = server.build_mcp(dsn=b_dsn, verifier=verifier, bridge=None, model=None, public_url=PUBLIC)
    claims = asyncio.run(server._Verifier(verifier).verify_token(
        token(keys, sub="inframedic", azp="inframedic", **{"kutuphane/principal_type": "agent"}))).claims
    content, _ = call_tool(mcp, claims, "submit_package", {"package_base64": base64.b64encode(pkg).decode()})
    out = json.loads(content[0].text)
    assert out["status"] in ("received", "findings") and out["issuer"] == issuer
    content, _ = call_tool(mcp, claims, "package_status", {"import_id": out["id"]})
    assert json.loads(content[0].text) == out
    assert conn_b.execute("SELECT submitted_channel FROM package_import").fetchone()[0] == "mcp"
    with pytest.raises(Exception, match="not base64"):
        call_tool(mcp, claims, "submit_package", {"package_base64": "***"})
