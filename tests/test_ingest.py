"""AT-01: ingest and version ids (docs/07 §4)."""
import os
import time

import pytest

from conftest import make_pdf
from kutuphane import catalog, db
from kutuphane.policy import PolicyError, make_policy
from kutuphane.source import SourceError, read_source

POLICY = make_policy(sensitivity="normal", egress="local_only", protection="standard")


def publish(conn, path, book="kitap", policy=POLICY):
    return catalog.publish(conn, book=book, title=book, files=read_source(path), policy=policy,
                           profile=catalog.whole_profile())


def test_okf_bundle_gets_three_ids(conn, okf_dir):
    r = publish(conn, okf_dir)
    assert (r.content_id[:3], r.profile_id[:3], r.policy_id[:3]) == ("ct_", "pf_", "pl_")
    state = catalog.book_state(conn, "kitap")
    assert [f["path"] for f in state["files"]] == ["index.md", "politika/veri-saklama.md",
                                                   "runbook/yedek-geri-yukleme.md"]
    assert {f["okf_type"] for f in state["files"]} == {"index", "policy", "runbook"}


def test_reingest_and_timestamps_keep_content_id(conn, okf_dir):
    first = publish(conn, okf_dir)
    later = time.time() + 3600
    for p in okf_dir.rglob("*.md"):
        os.utime(p, (later, later))
    again = publish(conn, okf_dir)
    assert again.content_id == first.content_id and not again.new_content


def test_one_byte_changes_content_id_and_old_version_stays_readable(conn, okf_dir):
    first = publish(conn, okf_dir)
    target = okf_dir / "politika" / "veri-saklama.md"
    original = target.read_bytes()
    target.write_bytes(original.replace("iki y".encode(), "üç y".encode()))
    second = publish(conn, okf_dir)
    assert second.content_id != first.content_id and second.new_content
    assert (second.profile_id, second.policy_id) == (first.profile_id, first.policy_id)
    assert catalog.read_file(conn, "kitap", first.content_id, "politika/veri-saklama.md") == original
    assert catalog.book_state(conn, "kitap")["content_versions"] == [first.content_id, second.content_id]


def test_policy_change_changes_only_policy_id(conn, okf_dir):
    first = publish(conn, okf_dir)
    restricted = make_policy(sensitivity="restricted", egress="local_only", protection="standard")
    second = publish(conn, okf_dir, policy=restricted)
    assert second.policy_id != first.policy_id and second.new_policy
    assert (second.content_id, second.profile_id) == (first.content_id, first.profile_id)
    assert not second.new_content


def test_unknown_frontmatter_keys_survive(conn, okf_dir):
    r = publish(conn, okf_dir)
    data = catalog.read_file(conn, "kitap", r.content_id, "politika/veri-saklama.md")
    assert "x-unknown-key: korunmalı".encode() in data


def test_text_pdf_is_ingested(conn, tmp_path):
    pdf = tmp_path / "mevzuat.pdf"
    pdf.write_bytes(make_pdf("Madde 1 - Bu kanunun amaci kisisel verilerin korunmasidir."))
    r = publish(conn, pdf, book="mevzuat")
    files = catalog.book_state(conn, "mevzuat")["files"]
    assert [(f["path"], f["media_type"]) for f in files] == [("mevzuat.pdf", "application/pdf")]
    assert r.content_id.startswith("ct_")


def test_pdf_without_text_layer_is_rejected(tmp_path):
    pdf = tmp_path / "scan.pdf"
    pdf.write_bytes(make_pdf(""))
    with pytest.raises(SourceError, match="no text layer"):
        read_source(pdf)


def test_invalid_frontmatter_is_rejected(tmp_path):
    (tmp_path / "bad.md").write_text("---\n- a list\n---\nbody\n", encoding="utf-8")
    with pytest.raises(SourceError, match="mapping"):
        read_source(tmp_path)


def test_hidden_files_and_symlinks(tmp_path, okf_dir):
    (okf_dir / ".git").mkdir()
    (okf_dir / ".git" / "config").write_text("x")
    assert all(not f.path.startswith(".") for f in read_source(okf_dir))
    (okf_dir / "link.md").symlink_to(okf_dir / "index.md")
    with pytest.raises(SourceError, match="symlink"):
        read_source(okf_dir)


@pytest.mark.parametrize("kwargs", [
    {"sensitivity": "normal", "egress": "local_only", "protection": "sealed"},
    {"sensitivity": "secret", "egress": "local_only", "protection": "standard"},
    {"sensitivity": "restricted", "egress": "cloud_ok", "protection": "standard"},
])
def test_policy_is_validated(kwargs):
    with pytest.raises(PolicyError):
        make_policy(**kwargs)


def test_failed_publish_leaves_nothing(conn, okf_dir, monkeypatch):
    def boom(_files):
        raise RuntimeError("fail after blobs were written")
    monkeypatch.setattr(catalog, "manifest_of", boom)
    with pytest.raises(RuntimeError):
        publish(conn, okf_dir)
    counts = [conn.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
              for t in ("book", "blob", "content_version", "policy_version", "profile_version")]
    assert counts == [0, 0, 0, 0, 0]


def test_migrate_is_idempotent(conn):
    assert db.migrate(conn) == []
