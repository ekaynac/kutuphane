"""AT-01: ingest and version ids (docs/07 §4)."""
import hashlib
import os
import time

import pytest

from conftest import make_pdf
from kutuphane import catalog, db, profiles
from kutuphane.policy import PolicyError, make_policy
from kutuphane.source import AcceptedFinding, SourceError, read_file, read_source

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
    ("config.json", '{"password": "A9b8C7d6E5f4G3h2"}\n'),                       # Astra #9: quoted JSON key
    (".codex/config.json", '{"pass\\u0077ord": "\\u0041\\u0039b8C7d6E5f4G3h2"}\n'),  # escaped key and value
    ("kayitlar.jsonl", '{"id": 1}\n{"api_key": "Zq9!x.y-Uzun-Gizli"}\n'),         # a JSONL record
    ("config.py", 'password = "aB3!very.secret-password"\n'),                    # a literal with punctuation
    ("sayfa.html", "<p>api_key: &#115;k-proj-abcdefghijklmnopqrstuvwx</p>\n"),   # decoded only by extraction
])
def test_a_secret_blocks_the_whole_book(conn, okf_dir, rel, text):  # security refusals stay book-level (G3)
    (okf_dir / rel).parent.mkdir(parents=True, exist_ok=True)
    (okf_dir / rel).write_text(text, encoding="utf-8")
    with pytest.raises(SourceError, match="credential"):
        publish(conn, okf_dir)
    assert catalog.book_state(conn, "kitap") is None


@pytest.mark.parametrize("name,text", [
    ("belge.md", "token = request.headers.get('Authorization')\n"), ("belge.md", "api_key: ${API_KEY}\n"),
    ("belge.md", "password: <redacted>\n"), ("belge.md", "GATEWAY_AUTH_MODE=subject-keys\n"),
    ("belge.md", "author: claude-opus-4-5\n"), ("belge.md", "Bu belge token: kavramını anlatır.\n"),
    ("ayar.yaml", "token: refresh_token\n"), ("ayar.yaml", "password: ${PASSWORD}\n"),   # Astra #9: semantic
    ("ayar.yaml", "api_key: <your-key>\n"), ("ayar.yaml", "secret: changeme\n"),         # constants, placeholders
    ("oauth.json", '{"grant_type": "refresh_token", "token": "refresh_token", "tokenizer": "./models/tok"}\n'),
    ("istemci.py", 'auth = "https://login.example.com/oauth"\npassword = "Parolanızı girin"\n'),
])
def test_ordinary_text_is_not_a_secret(tmp_path, name, text):
    (tmp_path / name).write_text(text, encoding="utf-8")
    assert read_source(tmp_path)


def test_a_finding_names_path_line_and_rule_never_the_value():  # Astra #9
    with pytest.raises(SourceError) as raised:
        read_file("ayar/config.json", b'{\n  "user": "app",\n  "password": "A9b8C7d6E5f4G3h2"\n}\n')
    assert "ayar/config.json: " in str(raised.value) and "line 3 (assigned-credential)" in str(raised.value)
    assert "A9b8C7d6E5f4G3h2" not in str(raised.value)
    with pytest.raises(SourceError) as raised:
        read_file("sayfa.html", b"<h1>Kurulum</h1>\n<p>api_key: &#115;k-proj-abcdefghijklmnopqrstuvwx</p>\n")
    assert "of the extracted text (api-key)" in str(raised.value) and "abcdefghijklmnop" not in str(raised.value)


SECRET_DOC = "Örnek anahtar: AKIAIOSFODNN7EXAMPLE\ndb_password: s3cr3tW0rd2026\n"  # aws-access-key, assigned-credential


def _accept(path, data, rule):
    return AcceptedFinding.parse(f"{path}@sha256:{hashlib.sha256(data).hexdigest()}:{rule}")


def test_accepted_finding_is_narrow_and_on_record(conn, okf_dir):  # Astra #9: a reviewed, auditable exception
    doc = okf_dir / "belgeler" / "ornek.md"
    doc.parent.mkdir()
    doc.write_text(SECRET_DOC, encoding="utf-8")
    data = doc.read_bytes()
    aws, assigned = (_accept("belgeler/ornek.md", data, r) for r in ("aws-access-key", "assigned-credential"))
    with pytest.raises(SourceError, match=r"line 2 \(assigned-credential\)"):  # one rule accepted, not the other
        read_source(okf_dir, [aws])
    with pytest.raises(SourceError, match="matches no finding"):               # a rule that does not fire
        read_source(okf_dir, [aws, assigned, _accept("belgeler/ornek.md", data, "jwt")])
    with pytest.raises(SourceError, match="matches no finding"):               # another file's acceptance
        read_source(okf_dir, [aws, assigned, _accept("index.md", data, "jwt")])
    files = read_source(okf_dir, [aws, assigned])
    r = catalog.publish(conn, book="kitap", title="kitap", files=files, policy=POLICY, profile=catalog.whole_profile())
    record = [{"path": "belgeler/ornek.md", "sha256": hashlib.sha256(data).hexdigest(), "rule": rule}
              for rule in ("assigned-credential", "aws-access-key")]
    assert r.accepted_findings == record
    assert catalog.book_state(conn, "kitap")["publications"][-1]["accepted_findings"] == record

    doc.write_text(SECRET_DOC + "Yeni satır.\n", encoding="utf-8")            # a changed file needs a new review
    with pytest.raises(SourceError, match=r"belgeler/ornek\.md: looks like it holds a credential: line 1"):
        read_source(okf_dir, [aws, assigned])


@pytest.mark.parametrize("spec", ["a.md@sha256:abc:jwt", "a.md:jwt", f"a.md@sha256:{'0' * 64}:password",
                                  f"../a.md@sha256:{'0' * 64}:jwt"])
def test_accept_finding_syntax_is_strict(spec):
    with pytest.raises(ValueError):
        AcceptedFinding.parse(spec)


def test_cli_accept_finding(conn, okf_dir, monkeypatch, capsys):  # Astra #9: on stdout, stderr and in `show`
    import json
    from kutuphane import cli, llmdap
    monkeypatch.setenv(db.DSN_ENV, os.environ["KUTUPHANE_TEST_DSN"])
    monkeypatch.delenv(llmdap.EMBED_ENV["route"], raising=False)
    (okf_dir / "ornek.md").write_text("Örnek anahtar: AKIAIOSFODNN7EXAMPLE\n", encoding="utf-8")
    digest = hashlib.sha256((okf_dir / "ornek.md").read_bytes()).hexdigest()
    base = ["ingest", str(okf_dir), "--book", "kitap", "--sensitivity", "normal", "--egress", "local_only",
            "--protection", "standard"]
    assert cli.main(base) == 2
    err = capsys.readouterr().err
    assert "ornek.md: looks like it holds a credential: line 1 (aws-access-key)" in err and "AKIA" not in err
    assert cli.main([*base, "--accept-finding", f"ornek.md@sha256:{digest}:aws-access-key"]) == 0
    out = capsys.readouterr()
    expected = [{"path": "ornek.md", "sha256": digest, "rule": "aws-access-key"}]
    assert json.loads(out.out)["accepted_findings"] == expected and f"ornek.md@sha256:{digest}" in out.err
    assert cli.main(["show", "kitap"]) == 0
    assert json.loads(capsys.readouterr().out)["publications"][-1]["accepted_findings"] == expected


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
