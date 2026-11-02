"""#161 `kutuphane pack`: a signed package from a folder, with no database. `receive` and `approve-import` take it as
they take an export of the same folder."""
import psycopg
import pytest
import yaml

from kutuphane import catalog, cli, db, kstd, packages, signing
from test_kstd import POLICY, publish, read_package, write_manifest
from test_packages import trust

FLAGS = ["--sensitivity", "normal", "--egress", "local_only", "--protection", "standard"]


def run_pack(monkeypatch, folder, key, out, *extra) -> int:
    """`kutuphane pack` with no DSN set and every connection attempt failing the test."""
    def refuse(*_a, **_k):
        raise AssertionError("pack opened a database connection")
    with monkeypatch.context() as m:
        m.delenv(db.DSN_ENV, raising=False)
        m.delenv(db.CURATOR_DSN_ENV, raising=False)
        m.setattr(db, "connect", refuse)
        m.setattr(psycopg, "connect", refuse)
        return cli.main(["pack", str(folder), "--book", "kitap", "--key", str(key), "--out", str(out), *FLAGS,
                         *extra])


@pytest.fixture
def key(tmp_path):
    info = signing.generate(tmp_path / "a.key")
    return tmp_path / "a.key", info


def test_a_packed_package_is_received_and_approved_like_an_export(conn, conn_b, okf_dir, key, tmp_path, monkeypatch):
    write_manifest(okf_dir, policy_item={"origin": "assisted", "reviewed_by": "Ayşe Yılmaz"})
    source = publish(conn, okf_dir)
    path, info = key
    exported = packages.export(conn, "kitap", signing.load_private(path))  # sequence 1
    out = tmp_path / "kitap.pkg"
    assert run_pack(monkeypatch, okf_dir, path, out, "--title", "kitap", "--sequence", "2") == 0
    packed = out.read_bytes()
    same = lambda m: {k: v for k, v in m.items() if k not in ("sequence", "created_at")}  # noqa: E731
    assert same(read_package(packed)) == same(read_package(exported))  # digests, content id, origin lists, policy
    assert read_package(packed)["sequence"] == 2
    trust(conn_b, info)
    from_export, from_pack = packages.receive(conn_b, exported), packages.receive(conn_b, packed)
    assert from_pack["status"] == "verified"
    assert {k: v for k, v in from_pack.items() if k not in ("id", "sequence")} == \
        {k: v for k, v in from_export.items() if k not in ("id", "sequence")}
    packages.approve(conn_b, from_export["id"], by="user:admin", policy=POLICY)
    published = packages.approve(conn_b, from_pack["id"], by="user:admin", policy=POLICY)
    assert published.content_id == source.content_id
    state = catalog.book_state(conn_b, "kitap")
    assert state["files"] == catalog.book_state(conn, "kitap")["files"]
    here, there = kstd.Rights(conn), kstd.Rights(conn_b)
    for f in state["files"]:
        assert there.info("kitap", source.content_id, f["path"]) == here.info("kitap", source.content_id, f["path"])
    assert packages.receive(conn_b, packed)["reasons"] == ["replay: sequence 2 is not newer than accepted 2"]


def bad_manifest(root):
    write_manifest(root)
    doc = yaml.safe_load((root / kstd.MANIFEST).read_text())
    doc["items"][0]["digest"] = "sha256:" + "0" * 64
    (root / kstd.MANIFEST).write_text(yaml.safe_dump(doc, allow_unicode=True))


@pytest.mark.parametrize("change,needle", [
    (lambda root: (root / "notlar.md").write_text("Örnek anahtar: AKIAIOSFODNN7EXAMPLE\n"), "credential"),
    (bad_manifest, "digest does not match"),
    (lambda root: (root / "a\tb.md").write_text("metin\n"), "control character"),
    (lambda root: write_manifest(root, rights={"license": "unknown", "personal_data": "no"}), "license unknown"),
    (lambda root: write_manifest(root, policy_item={"rights": {"personal_data": "unknown"}}), "legal basis"),
])
def test_pack_refuses_what_ingest_and_export_refuse(okf_dir, key, tmp_path, monkeypatch, capsys, change, needle):
    change(okf_dir)
    out = tmp_path / "kitap.pkg"
    assert run_pack(monkeypatch, okf_dir, key[0], out, "--sequence", "1") == 2
    assert needle in capsys.readouterr().err
    assert not out.exists()


def test_pack_needs_a_sequence_and_a_private_key(okf_dir, key, tmp_path, monkeypatch, capsys):
    with pytest.raises(SystemExit):  # the sending side keeps no counter: the caller names the sequence
        run_pack(monkeypatch, okf_dir, key[0], tmp_path / "a.pkg")
    assert run_pack(monkeypatch, okf_dir, key[0], tmp_path / "a.pkg", "--sequence", "0") == 2
    assert "sequence" in capsys.readouterr().err
    key[0].chmod(0o644)
    assert run_pack(monkeypatch, okf_dir, key[0], tmp_path / "a.pkg", "--sequence", "1") == 2
    assert "chmod 600" in capsys.readouterr().err
    assert not (tmp_path / "a.pkg").exists()
