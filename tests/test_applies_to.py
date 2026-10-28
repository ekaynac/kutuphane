"""#137: the Scope facet of a kstd file (docs/09 §2). `applies_to` bounds a file to platforms and a version range;
a request context {platform, version} on search and ask leaves out the files that it contradicts, before ranking.
An unbounded file always matches; a bound that the context does not give keeps the file as evidence, shown with
`scope: needs_context`."""
import json
import os

import pytest
import yaml

from kutuphane import authz, catalog, jobs, kstd, profiles, retrieval, search
from kutuphane.gate import Actor
from kutuphane.source import read_source
from test_kstd import POLICY, U, fake, write_manifest  # noqa: F401 (fake is a fixture)

RUNBOOK, POLICY_FILE = "runbook/yedek-geri-yukleme.md", "politika/veri-saklama.md"
Q = "kayıtlar saklanır yedek geri yükleme politika kitabı"
VCENTER = {"platform": ["vcenter"], "version": ">=7.0,<8"}


def publish(conn, root, runbook=VCENTER, policy=None):
    write_manifest(root, runbook_item={"applies_to": runbook},
                   policy_item={"applies_to": policy or {"platform": ["zabbix"]}})
    catalog.publish(conn, book="kitap", title="kitap", files=read_source(root), policy=POLICY,
                    profile=profiles.spec("chunked"))
    authz.grant(conn, "book:kitap", "read", U)


def found(conn, k=50, **context) -> dict:
    scope = search.Scope.of(context=context or None)
    hits = search.search(conn, Actor(U), Q, k=k, scope=scope)
    rights = kstd.Rights(conn, scope.context)
    return {h.citation.path: rights.info("kitap", h.citation.content_id, h.citation.path)["scope"] for h in hits}


@pytest.mark.parametrize("bound,platform,version,verdict", [
    (None, None, None, "unbounded"), (None, "vcenter", "7.0", "unbounded"),
    (VCENTER, "vcenter", "7.0.3", "match"), (VCENTER, "vcenter", "7", "match"), (VCENTER, "vcenter", "8.0", "mismatch"),
    (VCENTER, "vcenter", "6.7", "mismatch"), (VCENTER, "zabbix", "7.0", "mismatch"), (VCENTER, "zabbix", None, "mismatch"),
    (VCENTER, "vcenter", None, "needs_context"), (VCENTER, None, "7.1", "needs_context"), (VCENTER, None, None, "needs_context"),
    ({"version": "==2.1"}, None, "2.1.0", "match"), ({"version": "2.1"}, None, "2.1.1", "mismatch"),
    ({"version": ">2.1"}, None, "2.1", "mismatch"), ({"version": "<=2.1"}, None, "2.1", "match"),
    ({"version": ">=2.1,<3"}, None, "2.10", "match"), ({"version": ">=2.1,<3"}, None, "3.0.0", "mismatch"),
])
def test_the_scope_verdict(bound, platform, version, verdict):  # docs/09 §2, as notesquery.scope_verdict
    assert kstd.scope_verdict(bound, platform, version) == verdict


def test_the_string_form_names_one_platform():
    assert kstd.applies_to("Postgres 17") == {"platform": ["Postgres 17"]}
    assert kstd.applies_to(None) is None
    assert kstd.applies_to({"platform": ["a"], "site": "x"}) == {"platform": ["a"]}


@pytest.mark.parametrize("value,needle", [
    ("", "non-empty string or a mapping"), (7, "non-empty string or a mapping"),
    ({"platform": "vcenter"}, "list of non-empty strings"), ({"platform": []}, "list of non-empty strings"),
    ({"platform": [""]}, "list of non-empty strings"), ({"version": "7.x"}, "version range"),
    ({"version": ">=7,"}, "version range"), ({"version": 7}, "version range"),
])
def test_a_malformed_applies_to_blocks_publication(conn, okf_dir, value, needle):
    write_manifest(okf_dir, runbook_item={"applies_to": value})
    with pytest.raises(kstd.KstdError, match=needle):
        catalog.publish(conn, book="kitap", title="kitap", files=read_source(okf_dir), policy=POLICY,
                        profile=profiles.spec("chunked"))


def test_an_unknown_applies_to_key_is_a_notice_not_a_block(conn, okf_dir):  # D74: an untrusted claim
    publish(conn, okf_dir, runbook={"platform": ["vcenter"], "site": "kayseri"})
    manifest = yaml.safe_load((okf_dir / kstd.MANIFEST).read_text())
    files = {f.path: f.sha256 for f in read_source(okf_dir)}
    errors, warnings = kstd.check(manifest, files)
    assert not errors and any("applies_to: unknown field 'site' ignored" in w for w in warnings)
    info = kstd.Rights(conn).info("kitap", catalog.book_state(conn, "kitap")["content_id"], RUNBOOK)
    assert info["applies_to"] == {"platform": ["vcenter"]}
    assert any("unknown field 'site'" in n for n in info["notices"])


def test_the_context_leaves_out_contradicted_files_before_ranking(conn, okf_dir):
    publish(conn, okf_dir)
    everything = found(conn)                                  # no context: every file, bounded ones as evidence
    assert everything[RUNBOOK] == everything[POLICY_FILE] == "needs_context" and everything["index.md"] == "unbounded"
    vcenter = found(conn, platform="vcenter", version="7.0.3")
    assert POLICY_FILE not in vcenter and vcenter[RUNBOOK] == "match" and vcenter["index.md"] == "unbounded"
    assert RUNBOOK not in found(conn, platform="vcenter", version="8.0")        # outside the range
    assert found(conn, platform="vcenter")[RUNBOOK] == "needs_context"          # the version is not given
    zabbix = found(conn, platform="zabbix")
    assert RUNBOOK not in zabbix and zabbix[POLICY_FILE] == "match"
    top = found(conn, k=1, platform="nagios")                 # before k: a left-out file never takes a place
    assert top and set(top) <= {p for p, v in everything.items() if v == "unbounded"}


@pytest.mark.parametrize("bad", [{"site": "x"}, {"platform": ""}, {"platform": 3}, {"version": "7.x"},
                                 {"version": ">=7"}, ["vcenter"], {"platform": "a\nb"}])
def test_the_context_is_checked(bad):
    with pytest.raises(ValueError, match="context"):
        search.Scope.of(context=bad)


def test_a_background_job_keeps_the_context():
    scope = search.Scope.of(["kitap"], context={"platform": "vcenter", "version": "7.0"})
    assert jobs._scope(json.loads(json.dumps(jobs._scope_doc(scope)))) == scope
    plain = search.Scope.of(["kitap"])
    assert "context" not in jobs._scope_doc(plain) and jobs._scope(jobs._scope_doc(plain)) == plain


def test_http_mcp_and_cli_take_the_context(conn, okf_dir, monkeypatch, capsys):
    from kutuphane import cli, db, llmdap, server
    publish(conn, okf_dir)
    dsn = os.environ["KUTUPHANE_TEST_DSN"]
    scope = search.Scope.of(context={"platform": "zabbix"})
    hits = server.op_search(dsn, retrieval.Stages(), Actor(U), Q, 50, scope=scope)
    shown = {h["citation"].split("/", 2)[2].rsplit("#", 1)[0]: h["item"]["scope"] for h in hits}
    assert RUNBOOK not in shown and shown[POLICY_FILE] == "match"
    monkeypatch.setenv(db.DSN_ENV, dsn)
    for env in (llmdap.EMBED_ENV, llmdap.RERANK_ENV):
        monkeypatch.delenv(env["route"], raising=False)
    assert cli.main(["search", U, Q, "--platform", "vcenter", "--version", "7.2"]) == 0
    paths = {h["citation"].split("/", 2)[2].rsplit("#", 1)[0] for h in json.loads(capsys.readouterr().out)}
    assert RUNBOOK in paths and POLICY_FILE not in paths
    assert cli.main(["search", U, Q, "--version", "seven"]) == 2


def test_ask_evidence_follows_the_context(conn, okf_dir, fake):  # noqa: F811
    from kutuphane import answers
    publish(conn, okf_dir)
    out = answers.ask(conn, fake.bridge(), Actor(U), Q, model="qwen",
                      scope=search.Scope.of(context={"platform": "vcenter", "version": "7.0"}))
    sent = [b for path, b in fake.requests if path.endswith("/chat/completions")][-1]["messages"][1]["content"]
    assert "veri-saklama" not in sent and "yedek-geri-yukleme" in sent
    assert all(c["item"] is None or c["item"]["scope"] in ("match", "unbounded") for c in out["citations"])
