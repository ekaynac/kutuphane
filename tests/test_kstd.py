"""kstd L0 (docs/11 §7–§8): a folder's kstd.yaml is validated at publication, its rights gate indexing and every
model call, its personal-data flag gates export, and its item information reaches search, citations and answers."""
import hashlib

import pytest
import yaml

from kutuphane import authz, catalog, kstd, packages, profiles, retrieval, signing, vectors
from kutuphane.gate import Actor
from kutuphane.policy import make_policy
from kutuphane.source import read_source
from test_egress_audit import FakeBridge

U = "user:ayse"
POLICY = make_policy(sensitivity="normal", egress="local_only", protection="standard")
QUERY = "yedek geri yükleme kayıtlar saklanır"


@pytest.fixture
def fake():
    f = FakeBridge()
    yield f
    f.server.shutdown()


def digest(path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def write_manifest(root, *, default_ai_input="y", policy_item=None, runbook_item=None, **top):
    doc = {"standard": "kstd/0.2", "issuer": "ACME <kb@acme.example>", "issued": "2026-10-22",
           "rights": {"license": "CC-BY-4.0", "holder": "ACME", "personal_data": "no",
                      "ai_use": {"search": "y", "ai_input": default_ai_input, "train": "n"}},
           "items": [{"path": "runbook/yedek-geri-yukleme.md", "digest": digest(root / "runbook/yedek-geri-yukleme.md"),
                      "origin": "human", "valid_from": "2026-01-01", "applies_to": "Postgres 17",
                      **(runbook_item or {})},
                     {"path": "politika/veri-saklama.md", "digest": digest(root / "politika/veri-saklama.md"),
                      "origin": "model", **(policy_item or {})}]}
    doc.update(top)
    (root / kstd.MANIFEST).write_text(yaml.safe_dump(doc, allow_unicode=True))


def publish(conn, root):
    out = catalog.publish(conn, book="kitap", title="kitap", files=read_source(root), policy=POLICY,
                          profile=profiles.spec("chunked"))
    authz.grant(conn, "book:kitap", "read", U)
    return out


def chunk_paths(conn) -> set:
    return {p for (p,) in conn.execute("SELECT DISTINCT path FROM chunk WHERE book = 'kitap'")}


@pytest.mark.parametrize("change,needle", [
    (lambda m: m["items"][0].update(digest="sha256:" + "0" * 64), "digest does not match"),
    (lambda m: m["rights"].update(license="CC-BY-4.0 WITH Classpath-exception-2.0"), "not an SPDX expression"),
    (lambda m: m["rights"].update(license="Not-A-License"), "not an SPDX expression"),
    (lambda m: m["rights"]["ai_use"].update(train="maybe"), "ai_use takes only"),
    (lambda m: m.update(owner="x"), "unknown field 'owner'"),
    (lambda m: m["items"].append({"path": "missing.md", "digest": "sha256:" + "1" * 64}), "no such file"),
    (lambda m: m["items"][0].update(valid_to="2025-01-01"), "valid_from must be before valid_to"),
    (lambda m: m.update(standard="kstd/9"), "standard must be"),
    (lambda m: m["items"][1].update(origin="assisted"), "assisted needs reviewed_by"),
    (lambda m: m["items"][0].update(reviewed_by="Ayşe"), "only for origin assisted"),
    (lambda m: m["items"][1].update(origin="tool"), "tool needs software_agent"),
    (lambda m: m["items"][1].update(origin="tool", software_agent={"name": "typedoc"}), "tool needs software_agent"),
    (lambda m: m["items"][1].update(origin="tool", software_agent={"name": "typedoc", "version": 1.1}),
     "tool needs software_agent"),
    (lambda m: m["items"][1].update(origin="tool", software_agent={"name": "typedoc", "version": False}),
     "tool needs software_agent"),
    (lambda m: m["items"][0].update(software_agent={"name": "typedoc", "version": "0.26"}), "only for origin tool"),
])
def test_an_invalid_manifest_blocks_publication(conn, okf_dir, change, needle):  # fail closed
    write_manifest(okf_dir)
    doc = yaml.safe_load((okf_dir / kstd.MANIFEST).read_text())
    change(doc)
    (okf_dir / kstd.MANIFEST).write_text(yaml.safe_dump(doc, allow_unicode=True))
    with pytest.raises(kstd.KstdError, match=needle):
        publish(conn, okf_dir)
    assert catalog.book_state(conn, "kitap") is None


def test_valid_manifest_with_extensions_and_compound_license_publishes(conn, okf_dir):
    write_manifest(okf_dir, **{"x-department": "ops"})
    doc = yaml.safe_load((okf_dir / kstd.MANIFEST).read_text())
    doc["rights"]["license"] = "(MIT OR Apache-2.0) AND LicenseRef-acme-internal"
    doc["rights"]["personal_data"] = False  # an unquoted `no` in YAML 1.1
    (okf_dir / kstd.MANIFEST).write_text(yaml.safe_dump(doc, allow_unicode=True))
    files = read_source(okf_dir)
    errors, warnings = kstd.check(kstd.parse((okf_dir / kstd.MANIFEST).read_bytes()), {f.path: f.sha256 for f in files})
    assert errors == [] and any("not listed" in w for w in warnings)        # index.md is not listed
    publish(conn, okf_dir)
    info = kstd.Rights(conn).info("kitap", catalog.book_state(conn, "kitap")["content_id"], "index.md")
    assert info["origin"] == "unknown" and info["listed"] is False and info["personal_data"] == "no"


def test_files_without_search_permission_are_not_indexed(conn, okf_dir):
    write_manifest(okf_dir, policy_item={"rights": {"ai_use": {"search": "n"}}})
    publish(conn, okf_dir)
    assert "politika/veri-saklama.md" not in chunk_paths(conn)
    assert "runbook/yedek-geri-yukleme.md" in chunk_paths(conn)
    assert kstd.MANIFEST not in chunk_paths(conn)


def test_without_a_manifest_nothing_changes(conn, okf_dir):  # opt-in: legacy books follow their book policy
    publish(conn, okf_dir)
    assert {"politika/veri-saklama.md", "runbook/yedek-geri-yukleme.md"} <= chunk_paths(conn)
    assert kstd.Rights(conn).info("kitap", catalog.book_state(conn, "kitap")["content_id"], "index.md") is None


def test_rights_gate_the_new_text_formats_like_markdown(conn, okf_dir, fake):  # G1: the same ai_use gates
    import os
    from kutuphane import server
    (okf_dir / "kayitlar.jsonl").write_text('{"not": "yedek geri yükleme kayıtlar saklanır"}\n', encoding="utf-8")
    (okf_dir / "notlar.txt").write_text("Yedek geri yükleme kayıtlar saklanır.\n", encoding="utf-8")
    write_manifest(okf_dir)
    doc = yaml.safe_load((okf_dir / kstd.MANIFEST).read_text())
    doc["items"] += [
        {"path": "kayitlar.jsonl", "digest": digest(okf_dir / "kayitlar.jsonl"), "rights": {"ai_use": {"search": "n"}}},
        {"path": "notlar.txt", "digest": digest(okf_dir / "notlar.txt"), "rights": {"ai_use": {"ai_input": "n"}}}]
    (okf_dir / kstd.MANIFEST).write_text(yaml.safe_dump(doc, allow_unicode=True))
    publish(conn, okf_dir)
    assert "kayitlar.jsonl" not in chunk_paths(conn) and "notlar.txt" in chunk_paths(conn)
    assert kstd.MANIFEST not in chunk_paths(conn)                                # metadata, now a searched format
    vectors.index(conn, fake.embedder(), "kitap")
    embedded = {p for (p,) in conn.execute("SELECT DISTINCT path FROM chunk_vector")}
    assert "index.md" in embedded and "notlar.txt" not in embedded
    mcp = server.op_search(os.environ["KUTUPHANE_TEST_DSN"], retrieval.Stages(), Actor(U), QUERY, 8, True)
    note = next(h for h in mcp if "/notlar.txt#" in h["citation"])
    assert note["text"] is None and note["withheld"]


def test_passages_without_ai_input_never_reach_a_model(conn, okf_dir, fake):
    from kutuphane import answers
    write_manifest(okf_dir, runbook_item={"rights": {"ai_use": {"search": "y", "ai_input": "n"}}})
    publish(conn, okf_dir)
    vectors.index(conn, fake.embedder(), "kitap")
    embedded = {p for (p,) in conn.execute("SELECT DISTINCT path FROM chunk_vector")}
    assert embedded == {"index.md", "politika/veri-saklama.md"}

    fake.reply = "Kayıtlar saklanır [1]."
    out = answers.ask(conn, fake.bridge(), Actor(U), QUERY + " politika runbook", model="qwen",
                      stages=retrieval.Stages(reranker=fake.reranker()))
    sent = [b for path, b in fake.requests if path.endswith("/chat/completions")]
    reranked = [b for path, b in fake.requests if path.endswith("/rerank")]
    assert "yedek-geri-yukleme" not in sent[-1]["messages"][1]["content"]
    runbook = {t for (t,) in conn.execute("SELECT text FROM chunk WHERE path = 'runbook/yedek-geri-yukleme.md'")}
    assert reranked and not runbook & {d for b in reranked for d in b["documents"]}  # never reranked
    assert out["withheld"] >= 1 and out["status"] == "answered"


def test_item_information_reaches_search_and_citations(conn, okf_dir, monkeypatch):
    import os
    from kutuphane import server
    write_manifest(okf_dir)
    publish(conn, okf_dir)
    dsn = os.environ["KUTUPHANE_TEST_DSN"]
    hits = server.op_search(dsn, retrieval.Stages(), Actor(U), QUERY, 5)
    runbook = next(h for h in hits if "yedek-geri-yukleme" in h["citation"])
    assert runbook["item"]["origin"] == "human" and runbook["item"]["license"] == "CC-BY-4.0"
    assert runbook["item"]["applies_to"] == "Postgres 17" and runbook["item"]["current"] is True
    cited = server.op_citation(dsn, Actor(U), runbook["citation"])
    assert cited["item"]["valid_from"] == "2026-01-01"


def read_package(pkg) -> dict:
    import io, json, tarfile
    return json.loads(tarfile.open(fileobj=io.BytesIO(pkg)).extractfile("MANIFEST.json").read())


def test_export_of_possible_personal_data_needs_a_dpv_legal_basis(conn, okf_dir, tmp_path):
    write_manifest(okf_dir, policy_item={"rights": {"personal_data": "unknown"}})
    publish(conn, okf_dir)
    signing.generate(tmp_path / "a.key")
    key = signing.load_private(tmp_path / "a.key")
    with pytest.raises(packages.PackageError, match="legal basis"):
        packages.export(conn, "kitap", key)
    with pytest.raises(packages.PackageError, match="not valid: GDPR"):  # free text is not a legal basis
        packages.export(conn, "kitap", key, legal_basis="GDPR Art.6")
    pkg = packages.export(conn, "kitap", key, legal_basis="eu-gdpr:A9-2-b, eu-gdpr:A6-1-b")
    assert read_package(pkg)["legal_basis"] == ["eu-gdpr:A6-1-b", "eu-gdpr:A9-2-b"]


def test_tool_made_files_carry_their_generator_and_no_ai_mark(conn, okf_dir, tmp_path):  # docs/17, D63
    write_manifest(okf_dir, policy_item={"origin": "tool", "software_agent": {"name": "policy-render", "version": "2.1"}})
    publish(conn, okf_dir)
    signing.generate(tmp_path / "a.key")
    manifest = read_package(packages.export(conn, "kitap", signing.load_private(tmp_path / "a.key")))
    assert "politika/veri-saklama.md" not in manifest["ai_generated"]
    assert manifest["tool_made"] == {"politika/veri-saklama.md": {"name": "policy-render", "version": "2.1"}}


def test_received_origin_lists_must_follow_the_enclosed_manifest(conn, conn_b, okf_dir, tmp_path):  # Astra #10
    from test_packages import resigned, trust
    write_manifest(okf_dir, policy_item={"origin": "tool", "software_agent": {"name": "policy-render", "version": "2.1"}})
    publish(conn, okf_dir)
    info = signing.generate(tmp_path / "a.key")
    private = signing.load_private(tmp_path / "a.key")
    trust(conn_b, info)
    assert packages.receive(conn_b, packages.export(conn, "kitap", private))["status"] == "verified"
    forged = resigned(packages.export(conn, "kitap", private), private,  # the signer drops the AI mark of a file
                      lambda m: {**m, "ai_generated": [p for p in m["ai_generated"] if p != "index.md"]})
    result = packages.receive(conn_b, forged)
    assert result["status"] == "rejected" and "origin lists" in result["reasons"][0]


def test_synthetic_personal_data_needs_no_legal_basis_and_origin_is_marked(conn, okf_dir, tmp_path):  # D60
    write_manifest(okf_dir, policy_item={"origin": "assisted", "reviewed_by": "Ayşe Yılmaz",
                                         "rights": {"personal_data": "synthetic"}})
    (okf_dir / "notlar.md").write_text("model notu\n")                         # unlisted: origin unknown
    publish(conn, okf_dir)
    signing.generate(tmp_path / "a.key")
    manifest = read_package(packages.export(conn, "kitap", signing.load_private(tmp_path / "a.key")))
    assert "legal_basis" not in manifest
    assert "notlar.md" in manifest["ai_generated"] and "politika/veri-saklama.md" not in manifest["ai_generated"]
    assert "runbook/yedek-geri-yukleme.md" not in manifest["ai_generated"]   # human
    assert manifest["reviewed"] == {"politika/veri-saklama.md": "Ayşe Yılmaz"}


def test_absent_ai_use_is_reported_as_not_stated_but_denies(okf_dir):  # D60: three states
    write_manifest(okf_dir)
    doc = yaml.safe_load((okf_dir / kstd.MANIFEST).read_text())
    del doc["rights"]["ai_use"]["train"]
    info = kstd.effective(doc, "index.md")
    assert "train" not in info["ai_use"] and info["ai_use"]["search"] == "y"
    assert kstd.allows(info, "train") is False and kstd.allows(info, "search") is True


def test_init_writes_a_manifest_that_passes_the_check(okf_dir):
    files = read_source(okf_dir)
    text = kstd.init(files, "ACME <kb@acme.example>")
    errors, warnings = kstd.check(kstd.parse(text.encode()), {f.path: f.sha256 for f in files})
    assert errors == [] and any("no default license" in w for w in warnings)
    info = kstd.effective(kstd.parse(text.encode()), "index.md")
    assert info["license"] == "unknown" and info["personal_data"] == "unknown" and info["ai_use"]["ai_input"] == "n"


def test_init_keeps_turkish_names_readable_and_long_paths_on_one_line(okf_dir):  # pilot radar
    long = "belgeler/" + "çok-uzun-klasör-adı/" * 6 + "yedek.md"
    (okf_dir / long).parent.mkdir(parents=True)
    (okf_dir / long).write_text("# Yedek\n", encoding="utf-8")
    files = read_source(okf_dir)
    text = kstd.init(files, "Kütüphane Ekibi <kb@acme.example>")
    assert 'issuer: "Kütüphane Ekibi <kb@acme.example>"' in text and f'  - path: "{long}"' in text
    assert kstd.check(kstd.parse(text.encode()), {f.path: f.sha256 for f in files})[0] == []


def test_init_and_check_take_the_reviewed_finding_and_leave_no_empty_manifest(okf_dir, capsys):  # pilot radar
    from kutuphane import cli
    (okf_dir / "ornek.md").write_text("Clients send `Authorization: Bearer your-secret`.\n", encoding="utf-8")
    accept = f"ornek.md@sha256:{hashlib.sha256((okf_dir / 'ornek.md').read_bytes()).hexdigest()}:authorization-header"
    init = ["kstd-init", str(okf_dir), "--issuer", "ACME <kb@acme.example>"]
    assert cli.main(init) == 2
    assert "authorization-header" in capsys.readouterr().err
    assert not (okf_dir / kstd.MANIFEST).exists()          # a refused init writes nothing, so it can run again
    assert cli.main([*init, "--accept-finding", accept]) == 0
    assert yaml.safe_load((okf_dir / kstd.MANIFEST).read_text())["items"]
    assert cli.main(["kstd-check", str(okf_dir)]) == 2
    assert cli.main(["kstd-check", str(okf_dir), "--accept-finding", accept]) == 0
    assert "kstd L0: PASS" in capsys.readouterr().out


@pytest.mark.parametrize("text,needle", [
    ("standard: kstd/0.2\nissuer: A\nissued: 2026-10-22\nrights:\n  ai_use: {ai_input: n, ai_input: y}\n", "duplicate key"),
    ("standard: kstd/0.2\nissuer: A\nissued: 2026-10-22\nrights:\n  personal_data: yes\n  personal_data: no\n",
     "duplicate key"),
    ("base: &b {ai_input: n}\nstandard: kstd/0.2\nrights:\n  <<: *b\n", "not allowed"),
    ("standard: kstd/0.2\nx-deep: " + "[" * 5000 + "]" * 5000 + "\n", "nested too deeply|not valid"),
])
def test_yaml_tricks_never_loosen_a_restriction(text, needle):  # Astra review #8
    with pytest.raises(kstd.KstdError, match=needle):
        kstd.parse(text.encode())


@pytest.mark.parametrize("value,ok", [
    ("MIT", True), ("(MIT OR Apache-2.0) AND CC-BY-4.0", True), ("LicenseRef-acme", True), ("unknown", True),
    ("(MIT", False), ("MIT)", False), ("MIT AND", False), ("AND MIT", False), ("MIT WITH Classpath-exception-2.0", False),
    ("", False), ("()", False),
])
def test_license_expressions_follow_the_spdx_grammar(value, ok):
    assert kstd._license_ok(value) is ok


def test_model_readers_never_receive_text_without_ai_input(conn, okf_dir):  # Astra review #8: MCP and agents
    import os
    from datetime import datetime, timedelta, timezone
    from kutuphane import gate, server
    write_manifest(okf_dir, runbook_item={"rights": {"ai_use": {"search": "y", "ai_input": "n"}}})
    publish(conn, okf_dir)
    content_id = catalog.book_state(conn, "kitap")["content_id"]
    dsn = os.environ["KUTUPHANE_TEST_DSN"]
    human = server.op_search(dsn, retrieval.Stages(), Actor(U), QUERY, 8)
    runbook = next(h for h in human if "yedek-geri-yukleme" in h["citation"])
    assert runbook["text"]                                                      # a person reads it
    mcp = server.op_search(dsn, retrieval.Stages(), Actor(U), QUERY, 8, True)
    hidden = next(h for h in mcp if h["citation"] == runbook["citation"])
    assert hidden["text"] is None and "AI input" in hidden["withheld"]
    assert server.op_citation(dsn, Actor(U), runbook["citation"], True)["text"] is None
    authz.delegate(conn, delegator=U, delegate_to="agent:kobra-7", obj="book:kitap", mode="read",
                   expires_at=datetime.now(timezone.utc) + timedelta(hours=1))
    agent = Actor("agent:kobra-7", on_behalf_of=U)                              # an agent over HTTP is a model reader
    assert server.op_citation(dsn, agent, runbook["citation"])["text"] is None
    with pytest.raises(gate.Denied, match="AI input"):
        server.op_file(dsn, Actor(U), "kitap", content_id, "runbook/yedek-geri-yukleme.md", True)
    with pytest.raises(gate.Denied) as other:                                   # a non-reader learns nothing more
        server.op_file(dsn, Actor("user:mehmet"), "kitap", content_id, "runbook/yedek-geri-yukleme.md", True)
    assert "AI input" not in str(other.value)
    data, _ = server.op_file(dsn, Actor(U), "kitap", content_id, "politika/veri-saklama.md", True)
    assert data                                                                 # allowed files still flow


def test_reopened_answers_keep_item_information(conn, okf_dir, fake):  # Astra review #8
    from kutuphane import answers
    write_manifest(okf_dir)
    publish(conn, okf_dir)
    fake.reply = "Kayıtlar iki yıl saklanır [1]."
    out = answers.ask(conn, fake.bridge(), Actor(U), "kayıtlar saklanır", model="qwen")
    assert out["status"] == "answered" and out["citations"][0]["item"]["license"] == "CC-BY-4.0"
    again = answers.reopen(conn, Actor(U), out["id"])
    assert again["evidence"][0]["item"]["license"] == "CC-BY-4.0"


def test_a_validity_timestamp_keeps_its_time():  # Astra review #12: valid_from later today is not current now
    from datetime import datetime, timedelta, timezone

    from kutuphane import search

    def info(valid_from):
        doc = yaml.safe_load(f"issuer: x\nitems:\n  - path: a.md\n    valid_from: {valid_from}\n")
        return kstd.effective(doc, "a.md")
    later = info("2026-10-27T23:59:00Z")
    assert later["valid_from"] == "2026-10-27T23:59:00Z"
    assert not kstd.is_current(later, datetime(2026, 10, 27, 12, 0, tzinfo=timezone.utc))
    assert kstd.is_current(later, datetime(2026, 10, 27, 23, 59, tzinfo=timezone.utc))
    assert info("2026-10-27T23:59:00+03:00")["valid_from"] == "2026-10-27T20:59:00Z"    # kept as UTC
    day = info("2026-10-27")                                                           # a date alone: 00:00 UTC
    assert day["valid_from"] == "2026-10-27" and kstd.is_current(day, datetime(2026, 10, 27, 0, 0, tzinfo=timezone.utc))
    assert info("2026-10-27T00:00:00Z")["valid_from"] == "2026-10-27"
    soon = (datetime.now(timezone.utc) + timedelta(minutes=5)).replace(microsecond=0)
    upcoming = info(soon.isoformat().replace("+00:00", "Z"))
    assert not search.Scope(current_only=True).admits({**upcoming, "origin": "human"})
