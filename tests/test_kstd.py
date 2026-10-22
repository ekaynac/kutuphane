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


def test_export_of_possible_personal_data_needs_a_legal_basis(conn, okf_dir, tmp_path):
    write_manifest(okf_dir, policy_item={"rights": {"personal_data": "unknown"}})
    publish(conn, okf_dir)
    signing.generate(tmp_path / "a.key")
    key = signing.load_private(tmp_path / "a.key")
    with pytest.raises(packages.PackageError, match="legal basis"):
        packages.export(conn, "kitap", key)
    pkg = packages.export(conn, "kitap", key, legal_basis="GDPR Art. 6(1)(b), contract 2026-17")
    import io, json, tarfile
    manifest = json.loads(tarfile.open(fileobj=io.BytesIO(pkg)).extractfile("MANIFEST.json").read())
    assert manifest["legal_basis"] == "GDPR Art. 6(1)(b), contract 2026-17"


def test_init_writes_a_manifest_that_passes_the_check(okf_dir):
    files = read_source(okf_dir)
    text = kstd.init(files, "ACME <kb@acme.example>")
    errors, warnings = kstd.check(kstd.parse(text.encode()), {f.path: f.sha256 for f in files})
    assert errors == [] and any("no default license" in w for w in warnings)
    info = kstd.effective(kstd.parse(text.encode()), "index.md")
    assert info["license"] == "unknown" and info["personal_data"] == "unknown" and info["ai_use"]["ai_input"] == "n"
