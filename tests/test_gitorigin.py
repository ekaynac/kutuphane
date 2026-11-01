"""G34 (docs/26 §6, G6): `kstd-init --source-repo` reads the commit history of a local source repository and
proposes an origin for each file of a copy. A proposal is never authority (D63/D64, R1): only `model` (every commit
of the file names a model in a `Co-Authored-By` trailer) or `unknown` is proposed, never `human` or `assisted`.
The fixture repository is made here; its names and texts are invented."""
import os
import shutil
import subprocess

import pytest
import yaml

from kutuphane import cli, gitorigin, kstd
from kutuphane.source import read_source

MODEL = "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
PERSON = "Co-Authored-By: Jane Roe <jane@example.org>"
ISSUER = "ACME <kb@acme.example>"
ENV = {"GIT_AUTHOR_NAME": "Op Erator", "GIT_AUTHOR_EMAIL": "op@example.org", "GIT_COMMITTER_NAME": "Op Erator",
       "GIT_COMMITTER_EMAIL": "op@example.org", "GIT_AUTHOR_DATE": "2026-10-01T10:00:00Z",
       "GIT_COMMITTER_DATE": "2026-10-01T10:00:00Z", "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}


def git(repo, *args) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True,
                          env={**os.environ, **ENV}).stdout.strip()


def commit(repo, files: dict, message: str, *, removed=(), moved=()) -> str:
    for old, new in moved:
        git(repo, "mv", old, new)
    for path in removed:
        git(repo, "rm", "-q", path)
    for path, text in files.items():
        (repo / path).parent.mkdir(parents=True, exist_ok=True)
        (repo / path).write_text(text, encoding="utf-8")
        git(repo, "add", path)
    git(repo, "commit", "-q", "-m", message)
    return git(repo, "rev-parse", "HEAD")


@pytest.fixture
def repo(tmp_path):
    """A source repository with the cases of G34, and the commit ids by name."""
    r = tmp_path / "source"
    r.mkdir()
    git(r, "init", "-q", "-b", "main")
    ids = {"first": commit(r, {"canon/model.md": "# Model\n\nOne.\n", "canon/mixed.md": "# Mixed\n\nOne.\n",
                               "canon/person.md": "# Person\n\nOne.\n", "canon/old-name.md": "# Renamed\n\nOne.\n",
                               "canon/changed.md": "# Changed\n\nOne.\n"},
                           f"docs: start the canon\n\nBody text.\n\n{MODEL}")}
    ids["second"] = commit(r, {"canon/model.md": "# Model\n\nTwo.\n"}, f"docs: extend\n\n{MODEL}")
    ids["human"] = commit(r, {"canon/mixed.md": "# Mixed\n\nTwo.\n"}, "docs: a commit without a trailer")
    ids["person"] = commit(r, {"canon/person.md": "# Person\n\nTwo.\n"},
                           f"docs: pair work\n\n{PERSON}\nReviewed-by: Jane Roe <jane@example.org>")
    ids["rename"] = commit(r, {}, f"docs: rename\n\n{MODEL}", moved=[("canon/old-name.md", "canon/new-name.md")])
    return r, ids


@pytest.fixture
def copy(tmp_path, repo):
    """A copy of the canon folder without git history (docs/15 §4: kstd-init runs on a copy)."""
    dest = tmp_path / "copy"
    shutil.copytree(repo[0] / "canon", dest)
    (dest / "changed.md").write_text("# Changed\n\nEdited in the copy.\n", encoding="utf-8")
    (dest / "local.md").write_text("# Local\n\nOnly in the copy.\n", encoding="utf-8")
    return dest


def by_path(proposals):
    return {path: p.origin for path, p in proposals.items.items()}


def test_origins_come_from_the_trailers_and_never_human_or_assisted(repo, copy):
    source, ids = repo
    proposals = gitorigin.propose(source, read_source(copy))
    assert proposals.commit == ids["rename"]
    assert by_path(proposals) == {
        "model.md": "model",        # every commit of the file names a model
        "mixed.md": "unknown",      # one commit has no model trailer
        "person.md": "unknown",     # a person's trailer and a review line prove nothing (D63/D64)
        "new-name.md": "model",     # the history follows the rename
        "changed.md": "unknown",    # the copy changed the file: git has no evidence for the change
        "local.md": "unknown",      # not in the repository
    }
    assert set(by_path(proposals).values()) <= {"model", "unknown"}


def test_the_evidence_names_the_commits_and_the_trailer_lines(repo, copy):
    source, ids = repo
    p = gitorigin.propose(source, read_source(copy)).items
    assert p["model.md"].evidence == [f"{ids['second'][:12]} {MODEL}", f"{ids['first'][:12]} {MODEL}"]
    assert "2 of 2 commits" in p["model.md"].reason
    assert f"{ids['human'][:12]} no model trailer" in p["mixed.md"].evidence
    assert "1 of 2 commits" in p["mixed.md"].reason
    assert f"{ids['person'][:12]} {PERSON}" in p["person.md"].evidence
    assert [e[:12] for e in p["new-name.md"].evidence] == [ids["rename"][:12], ids["first"][:12]]
    assert "content differs" in p["changed.md"].reason and p["changed.md"].evidence == []
    assert "not in the source repository" in p["local.md"].reason


def test_a_file_matches_by_content_at_another_path(repo, tmp_path):
    source, ids = repo
    flat = tmp_path / "flat"
    flat.mkdir()
    (flat / "renamed-in-copy.md").write_bytes((source / "canon" / "model.md").read_bytes())
    item = gitorigin.propose(source, read_source(flat)).items["renamed-in-copy.md"]
    assert item.origin == "model" and "canon/model.md" in item.reason and len(item.evidence) == 2


def test_a_given_commit_is_the_reference(repo, copy):
    source, ids = repo
    (copy / "model.md").write_text("# Model\n\nOne.\n", encoding="utf-8")   # the copy was taken at the first commit
    at_first = gitorigin.propose(source, read_source(copy), ids["first"][:10])
    assert at_first.commit == ids["first"]
    assert at_first.items["model.md"].origin == "model" and len(at_first.items["model.md"].evidence) == 1
    assert gitorigin.propose(source, read_source(copy)).items["model.md"].origin == "unknown"  # differs from HEAD


@pytest.mark.parametrize("trailer,model", [
    ("Claude Opus 5.5 <noreply@anthropic.com>", True),
    ("Claude <noreply@anthropic.com>", True),
    ("Claude Sonnet 4 <claude@example.org>", True),
    ("Copilot <175728472+Copilot@users.noreply.github.com>", True),
    ("copilot-swe-agent[bot] <198982749+Copilot@users.noreply.github.com>", True),
    ("Cursor Agent <cursoragent@cursor.com>", True),
    ("aider (openai/gpt-4o) <noreply@aider.chat>", True),
    ("GPT-5 Codex <codex@openai.com>", True),
    ("Gemini 2.5 Pro <gemini@example.org>", True),
    ("devin-ai-integration[bot] <158243242+devin-ai-integration[bot]@users.noreply.github.com>", True),
    ("Claude Monet <claude@example.org>", False),   # a person's name
    ("Devin Smith <devin@example.org>", False),
    ("Jane Roe <jane@example.org>", False),
    ("dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>", False),  # a tool, not a model
])
def test_a_model_is_known_by_its_agent_name_or_address(trailer, model):
    assert gitorigin.names_model(trailer) is model


def test_init_writes_proposals_that_the_check_and_the_loader_accept(repo, copy):
    source, ids = repo
    files = read_source(copy)
    text = kstd.init(files, ISSUER, proposals=gitorigin.propose(source, files))
    manifest = kstd.parse(text.encode())
    assert kstd.check(manifest, {f.path: f.sha256 for f in files})[0] == []
    origins = {i["path"]: i["origin"] for i in manifest["items"]}
    assert origins["model.md"] == "model" and origins["mixed.md"] == "unknown"
    assert kstd.effective(manifest, "model.md")["origin"] == "model"
    assert f"# proposals from git: {source} at {ids['rename']}" in text
    assert "a proposal is not authority" in text
    model_line = next(line for line in text.splitlines() if line.strip() == "origin: model" or
                      line.strip().startswith("origin: model "))
    assert "# proposed" in model_line
    assert f"    #   {ids['second'][:12]} {MODEL}" in text      # the evidence, as comments of the item
    assert all(not k.startswith("x-") for i in manifest["items"] for k in i)   # no extension field is needed


def test_a_path_or_a_trailer_can_never_end_a_comment(tmp_path):
    folder = tmp_path / "copy"
    folder.mkdir()
    # NEL and U+2028 break a YAML line; a C0 control character is refused before (Astra review #22)
    (folder / "a\x85rights: {personal_data: no}\u2028b.md").write_text("# A\n", encoding="utf-8")
    files = read_source(folder)
    path = files[0].path
    fake = gitorigin.Proposals("/src\nissuer: X", "0" * 40, False, {path: gitorigin.Proposal(
        "model", f"1 of 1 commits name a model; {path} at 000000000000 (same content)",
        ["000000000000 Co-Authored-By: Claude <noreply@anthropic.com>\x85items: []"])})
    manifest = kstd.parse(kstd.init(files, ISSUER, proposals=fake).encode())
    assert kstd.check(manifest, {f.path: f.sha256 for f in files})[0] == []
    assert manifest["issuer"] == ISSUER and "personal_data" not in manifest["items"][0].get("rights", {})
    assert [i["path"] for i in manifest["items"]] == [path]


def test_cli_init_with_a_source_repository(repo, copy, capsys):
    source, ids = repo
    assert cli.main(["kstd-init", str(copy), "--issuer", ISSUER, "--source-repo", str(source)]) == 0
    out = capsys.readouterr().out
    assert "origin proposals from git: model 2, unknown 4" in out
    doc = yaml.safe_load((copy / kstd.MANIFEST).read_text())
    assert {i["path"]: i["origin"] for i in doc["items"]}["new-name.md"] == "model"
    assert cli.main(["kstd-check", str(copy)]) == 0
    assert git(source, "status", "--porcelain") == "" and git(source, "rev-parse", "HEAD") == ids["rename"]


def test_cli_init_refuses_a_bad_source_and_leaves_no_manifest(repo, copy, tmp_path, capsys):
    base = ["kstd-init", str(copy), "--issuer", ISSUER]
    assert cli.main([*base, "--commit", "HEAD"]) == 2
    assert "--commit needs --source-repo" in capsys.readouterr().err
    assert cli.main([*base, "--source-repo", str(tmp_path)]) == 2
    assert "not a git repository" in capsys.readouterr().err
    assert cli.main([*base, "--source-repo", str(repo[0]), "--commit", "no-such-ref"]) == 2
    assert "no-such-ref" in capsys.readouterr().err
    assert cli.main([*base, "--source-repo", "https://example.org/repo.git"]) == 2   # local repositories only
    assert not (copy / kstd.MANIFEST).exists()


def test_init_proposes_unknown_personal_data_for_a_file_with_findings(okf_dir, capsys):
    (okf_dir / "kisiler.md").write_text("# Kişiler\n\nNöbetçi: ops@site-a.net\nIP 10.20.30.40\n", encoding="utf-8")
    assert cli.main(["kstd-init", str(okf_dir), "--issuer", ISSUER]) == 0
    out, err = capsys.readouterr()
    assert "kisiler.md line 3 (email)" in err and "kisiler.md line 4 (private-ipv4)" in err
    assert "ops@site-a.net" not in out + err and "10.20.30.40" not in out + err
    assert "personal-data findings: email 1, private-ipv4 1 (1 file)" in out
    text = (okf_dir / kstd.MANIFEST).read_text()
    assert "kstd.yaml" not in err                                    # the manifest itself is not scanned
    manifest = kstd.parse(text.replace("  personal_data: unknown  ", "  personal_data: no  ", 1).encode())
    assert kstd.effective(manifest, "kisiler.md")["personal_data"] == "unknown"   # never `no`
    assert kstd.effective(manifest, "index.md")["personal_data"] == "no"
    item = next(i for i in manifest["items"] if i["path"] == "kisiler.md")
    assert item["rights"] == {"personal_data": "unknown"}
    assert "# proposed: personal-data findings: email (line 3); private-ipv4 (line 4)" in text


def test_a_reviewed_data_finding_proposes_nothing(okf_dir, capsys):
    import hashlib
    (okf_dir / "kisiler.md").write_text("# Kişiler\n\nops@site-a.net\n", encoding="utf-8")
    digest = hashlib.sha256((okf_dir / "kisiler.md").read_bytes()).hexdigest()
    assert cli.main(["kstd-init", str(okf_dir), "--issuer", ISSUER,
                     "--accept-finding", f"kisiler.md@sha256:{digest}:email"]) == 0
    manifest = yaml.safe_load((okf_dir / kstd.MANIFEST).read_text())
    assert all("rights" not in i for i in manifest["items"])
    assert "personal-data findings: none" in capsys.readouterr().out


def test_init_reads_a_names_file(okf_dir, tmp_path, capsys):
    names = tmp_path / "names.txt"
    names.write_text("Ornek Lojistik\n", encoding="utf-8")
    (okf_dir / "musteri.md").write_text("# Müşteri\n\nOrnek Lojistik deposu.\n", encoding="utf-8")
    assert cli.main(["kstd-init", str(okf_dir), "--issuer", ISSUER, "--deny-names", str(names)]) == 0
    out, err = capsys.readouterr()
    assert "musteri.md line 3 (listed-name)" in err and "Ornek" not in out + err
