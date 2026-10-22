"""AT-01: ingest and version ids (docs/07 §4)."""
import os
import time

import pytest

from conftest import make_pdf
from kutuphane import catalog, db, profiles
from kutuphane.policy import PolicyError, make_policy
from kutuphane.source import SourceError, read_file, read_source

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
    changed = bytearray(original)
    changed[changed.index(b"silinir")] = ord("S")  # exactly one byte
    target.write_bytes(bytes(changed))
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


def test_scanned_pdf_is_quarantined_and_the_rest_publishes(conn, okf_dir):  # G3
    (okf_dir / "tarama.pdf").write_bytes(make_pdf(""))                     # no text layer
    (okf_dir / "bozuk.pdf").write_bytes(b"%PDF-1.4\nthis is not a pdf body\n")
    r = publish(conn, okf_dir)
    assert {q["path"] for q in r.quarantined} == {"tarama.pdf", "bozuk.pdf"} and all(q["reason"] for q in r.quarantined)
    state = catalog.book_state(conn, "kitap")
    assert {"tarama.pdf", "bozuk.pdf", "index.md"} <= {f["path"] for f in state["files"]}  # stored and listed
    assert [q["path"] for q in state["quarantined"]] == ["bozuk.pdf", "tarama.pdf"]
    indexed = {p for (p,) in conn.execute("SELECT DISTINCT path FROM chunk WHERE book = 'kitap'")}
    assert "politika/veri-saklama.md" in indexed and not indexed & {"tarama.pdf", "bozuk.pdf"}
    assert catalog.read_file(conn, "kitap", r.content_id, "tarama.pdf") == make_pdf("")

    (okf_dir / "tarama.pdf").write_bytes(make_pdf("Madde 1 - Tarama metni"))  # a later version fixes it (D53)
    (okf_dir / "bozuk.pdf").unlink()
    fixed = publish(conn, okf_dir)
    assert fixed.quarantined == [] and catalog.book_state(conn, "kitap")["quarantined"] == []
    current = {p for (p,) in conn.execute("SELECT DISTINCT path FROM chunk WHERE book = 'kitap' AND content_id = %s",
                                          (fixed.content_id,))}
    assert "tarama.pdf" in current and "bozuk.pdf" not in {f["path"] for f in catalog.book_state(conn, "kitap")["files"]}


def test_cli_reports_quarantined_files(conn, okf_dir, monkeypatch, capsys):  # G3: a person sees it
    import json
    from kutuphane import cli, llmdap
    monkeypatch.setenv(db.DSN_ENV, os.environ["KUTUPHANE_TEST_DSN"])
    monkeypatch.delenv(llmdap.EMBED_ENV["route"], raising=False)
    (okf_dir / "tarama.pdf").write_bytes(make_pdf(""))
    assert cli.main(["ingest", str(okf_dir), "--book", "kitap", "--sensitivity", "normal", "--egress", "local_only",
                     "--protection", "standard"]) == 0
    out = capsys.readouterr()
    assert [q["path"] for q in json.loads(out.out)["quarantined"]] == ["tarama.pdf"] and "tarama.pdf" in out.err
    assert cli.main(["show", "kitap"]) == 0
    assert [q["path"] for q in json.loads(capsys.readouterr().out)["quarantined"]] == ["tarama.pdf"]


@pytest.mark.parametrize("name,data,reason", [
    ("eski.txt", "Türkçe metin".encode("latin-1") + b"\xff", "UTF-8"),
    ("kayit.json", b'{"a": "\x00"}', "NUL"),
])
def test_text_that_is_not_text_is_quarantined(name, data, reason):  # binary detection: UTF-8 and no NUL
    f = read_file(name, data)
    assert reason in f.quarantine
    assert profiles.split(profiles.spec("chunked"), f) == []


def test_invalid_frontmatter_is_rejected(tmp_path):
    (tmp_path / "bad.md").write_text("---\n- a list\n---\nbody\n", encoding="utf-8")
    with pytest.raises(SourceError, match="mapping"):
        read_source(tmp_path)


def test_hidden_paths_stay_out_but_agent_folders_come_in(okf_dir):  # G5
    never = [".git/config", ".git/hooks/pre-commit", ".env", ".env.local", "alt/.env.production", ".venv/lib/x.py",
             ".claude/settings.local.json", ".claude/settings.json", ".claude/agents/.taslak.md", ".cursor/mcp.json",
             ".github/workflows/ci.yml", ".claude/agents/.cache/x.md", ".DS_Store"]
    wanted = [".claude/agents/denetci.md", ".claude/commands/yayinla.md", ".claude/rules/kurallar.md",
              ".claude/hooks/onay.sh", ".claude/skills/ozet/SKILL.md", ".claude/skills/ozet/references/kaynak.md",
              ".claude/skills/learned/ders.md", ".claude/CLAUDE.md", ".cursor/rules/stil.mdc",
              ".github/copilot-instructions.md", ".github/instructions/py.instructions.md", ".agents/plan.md",
              ".codex/prompts/gozden.md", "alt/.claude/agents/ic.md"]
    for rel in never + wanted:
        (okf_dir / rel).parent.mkdir(parents=True, exist_ok=True)
        (okf_dir / rel).write_text("Ajan notu.\n", encoding="utf-8")
    paths = {f.path for f in read_source(okf_dir)}
    assert set(wanted) <= paths and not paths & set(never)


@pytest.mark.parametrize("rel", [".git/config", ".env", "a/.env", ".claude/settings.local.json", ".vscode/x.json"])
def test_packages_cannot_carry_hidden_paths_either(rel):  # read_file is shared by ingest and package receipt
    with pytest.raises(SourceError, match="hidden"):
        read_file(rel, b"x\n")


def test_symlinks_are_not_followed(okf_dir):
    (okf_dir / "link.md").symlink_to(okf_dir / "index.md")
    with pytest.raises(SourceError, match="symlink"):
        read_source(okf_dir)


@pytest.mark.parametrize("rel,text", [
    ("notlar.md", "AWS anahtarı: AKIAIOSFODNN7EXAMPLE\n"),
    ("ayar/uygulama.yaml", "db_password: s3cr3tW0rd2026\n"),
    ("deploy/run.sh", "export API_TOKEN=ghp_abcdefghijklmnopqrstuvwxyz0123\n"),
    ("kod/istemci.py", 'client = Client(api_key="sk-proj-abcdefghijklmnopqrstuvwx")\n'),
    ("anahtar.txt", "-----BEGIN OPENSSH PRIVATE KEY-----\nb3BlbnNzaC1rZXktdjEAAAAABG5vbmUAAAAE\n"),
    (".claude/agents/baglan.md", "Veritabanı: postgres://app:Gizli-Parola-9@db.internal/app\n"),
    ("credentials.json", "{}\n"),
    ("ayar/settings.local.json", "{}\n"),
    ("prod.env", "X=1\n"),
])
def test_a_secret_blocks_the_whole_book(conn, okf_dir, rel, text):  # security refusals stay book-level (G3)
    (okf_dir / rel).parent.mkdir(parents=True, exist_ok=True)
    (okf_dir / rel).write_text(text, encoding="utf-8")
    with pytest.raises(SourceError, match="credential"):
        publish(conn, okf_dir)
    assert catalog.book_state(conn, "kitap") is None


@pytest.mark.parametrize("text", [
    "token = request.headers.get('Authorization')\n", "api_key: ${API_KEY}\n", "password: <redacted>\n",
    "GATEWAY_AUTH_MODE=subject-keys\n", "author: claude-opus-4-5\n", "Bu belge token: kavramını anlatır.\n",
])
def test_ordinary_text_is_not_a_secret(tmp_path, text):
    (tmp_path / "belge.md").write_text(text, encoding="utf-8")
    assert read_source(tmp_path)


def test_symlinked_directory_is_rejected(okf_dir, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.md").write_text("x")
    (okf_dir / "baglanti").symlink_to(outside, target_is_directory=True)
    with pytest.raises(SourceError, match="symlink"):
        read_source(okf_dir)


def test_nfc_nfd_collision_is_rejected(tmp_path):
    (tmp_path / "ş.md").write_text("a")      # ş precomposed
    (tmp_path / "ş.md").write_text("b")     # s + combining cedilla
    with pytest.raises(SourceError, match="same path"):
        read_source(tmp_path)


@pytest.mark.parametrize("front", [
    "a: &x [1, 2]\nb: *x\n",             # aliases refused (expansion bombs)
    "type:\n  - not\n  - a string\n",   # type must be a short string
])
def test_hostile_frontmatter_is_rejected(tmp_path, front):
    (tmp_path / "x.md").write_text(f"---\n{front}---\nbody\n", encoding="utf-8")
    with pytest.raises(SourceError):
        read_source(tmp_path)


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


def test_pdf_three_ids_and_one_byte(conn, tmp_path):  # AT-01 for PDF
    pdf = tmp_path / "mevzuat.pdf"
    pdf.write_bytes(make_pdf("Madde 1 - Amac"))
    first = publish(conn, pdf, book="mevzuat")
    assert (first.profile_id[:3], first.policy_id[:3]) == ("pf_", "pl_")
    pdf.write_bytes(make_pdf("Madde 1 - Amac."))
    second = publish(conn, pdf, book="mevzuat")
    assert second.content_id != first.content_id
    assert (second.profile_id, second.policy_id) == (first.profile_id, first.policy_id)


@pytest.mark.parametrize("bad", [{}, {"v": 1, "sensitivity": "normal", "egress": "local_only", "protection": "sealed"},
                                 {**POLICY, "extra": 1}, None])
def test_publish_validates_policy_itself(conn, okf_dir, bad):  # AT-16 at the shared boundary
    with pytest.raises(PolicyError):
        catalog.publish(conn, book="kitap", title="kitap", files=read_source(okf_dir), policy=bad,
                        profile=catalog.whole_profile())
    assert conn.execute("SELECT count(*) FROM book").fetchone()[0] == 0


def test_publication_binds_three_ids(conn, okf_dir):  # D26
    first = publish(conn, okf_dir)
    from kutuphane import profiles
    other = profiles.spec("chunked")
    second = catalog.publish(conn, book="kitap", title="kitap", files=read_source(okf_dir), policy=POLICY,
                             profile=other)
    state = catalog.book_state(conn, "kitap")
    assert state["profile_id"] == second.profile_id != first.profile_id
    assert [(p["content_id"], p["profile_id"], p["policy_id"]) for p in state["publications"]] == [
        (first.content_id, first.profile_id, first.policy_id),
        (second.content_id, second.profile_id, second.policy_id)]


@pytest.mark.parametrize("profile", [{"name": "chunked", "components": {}},
                                     {"name": "custom"}, None])
def test_only_canonical_profiles_are_accepted(conn, okf_dir, profile):  # Astra #2: id describes behavior
    with pytest.raises(ValueError, match="unsupported profile"):
        catalog.publish(conn, book="kitap", title="kitap", files=read_source(okf_dir), policy=POLICY, profile=profile)
