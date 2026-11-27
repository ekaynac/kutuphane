"""deploy/release_check.sh: the tag, version and changelog checks and the stop/build/resume plan of the release job.

`gh` and `docker` are fakes on PATH; nothing here touches a network."""
import os
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "deploy" / "release_check.sh"

CHANGELOG = "# Changelog\n\n## Unreleased\n\n## v1.0.0 (2026-11-27)\n\nBody one.\n\n### Part\n\nBody two.\n\n## 2026-10-27\n\nOld.\n"
PYPROJECT = '[project]\nname = "kutuphane"\nversion = "1.0.0"\n'

# The fakes read the state from FAKE_RELEASE, FAKE_CORE, FAKE_MODELS: "yes", "no" or a failure kind (see below).
FAKE_GH = """#!/bin/sh
case "$FAKE_RELEASE" in
  yes) echo "title: v1.0.0"; exit 0 ;;
  no) echo "release not found" >&2; exit 1 ;;
  other-message) echo "release not found in this repository" >&2; exit 1 ;;
  forbidden) echo "HTTP 403: Resource not accessible by integration" >&2; exit 1 ;;
  *) echo "HTTP 502: bad gateway" >&2; exit 1 ;;
esac
"""
FAKE_DOCKER = """#!/bin/sh
echo "$@" >> "$FAKE_LOG"
case "$*" in *kutuphane-models:*) state="$FAKE_MODELS" ;; *) state="$FAKE_CORE" ;; esac
case "$state" in
  yes) echo "Name: $4"; exit 0 ;;
  no) echo "ERROR: $4: not found" >&2; exit 1 ;;
  other-ref) echo "ERROR: ghcr.io/other/image:v9: not found" >&2; exit 1 ;;
  credential-helper) echo "error getting credentials - err: exec: docker-credential-x: executable file not found in path" >&2; exit 1 ;;
  not-found-127) echo "docker-buildx: command not found" >&2; exit 127 ;;
  forbidden) echo "ERROR: failed to authorize: 403 Forbidden" >&2; exit 1 ;;
  *) echo "ERROR: dial tcp: lookup ghcr.io: no such host" >&2; exit 1 ;;
esac
"""


@pytest.fixture
def repo(tmp_path):
    (tmp_path / "docs" / "guide").mkdir(parents=True)
    (tmp_path / "pyproject.toml").write_text(PYPROJECT)
    (tmp_path / "docs" / "guide" / "changelog.md").write_text(CHANGELOG)
    bindir = tmp_path / "bin"
    bindir.mkdir()
    for name, body in (("gh", FAKE_GH), ("docker", FAKE_DOCKER)):
        (bindir / name).write_text(body)
        (bindir / name).chmod(0o755)
    return tmp_path


def run(repo, *args, release="no", core="no", models="no"):
    env = {**os.environ, "ROOT": str(repo), "PATH": f"{repo / 'bin'}:{os.environ['PATH']}",
           "FAKE_RELEASE": release, "FAKE_CORE": core, "FAKE_MODELS": models, "FAKE_LOG": str(repo / "docker.log"),
           "GITHUB_REPOSITORY": "o/r", "IMAGE": "ghcr.io/o/core", "MODELS_IMAGE": "ghcr.io/o/kutuphane-models"}
    return subprocess.run(["bash", str(SCRIPT), *args], env=env, capture_output=True, text=True)


def test_valid_tag(repo):
    assert run(repo, "v1.0.0").returncode == 0


@pytest.mark.parametrize("tag", ["v1.0.0rc1", "v01.0.0", "v1.0", "1.0.0", "v1.0.0+x", "v1.0.0-rc.1", "v1.0.0.1", "v1.00.0", ""])
def test_refused_tags(repo, tag):
    r = run(repo, tag)
    assert r.returncode != 0
    assert r.stderr


def test_pyproject_mismatch(repo):
    (repo / "pyproject.toml").write_text(PYPROJECT.replace("1.0.0", "1.0.1"))
    r = run(repo, "v1.0.0")
    assert r.returncode == 1 and "pyproject.toml" in r.stderr


def test_pyproject_version_is_not_a_regex(repo):
    (repo / "pyproject.toml").write_text(PYPROJECT.replace("1.0.0", "1x0x0"))
    assert run(repo, "v1.0.0").returncode == 1


def test_changelog_heading_missing(repo):
    (repo / "docs" / "guide" / "changelog.md").write_text(CHANGELOG.replace("## v1.0.0 (", "## v1.0.1 ("))
    r = run(repo, "v1.0.0")
    assert r.returncode == 1 and "changelog.md" in r.stderr


def test_changelog_heading_is_not_a_regex(repo):
    (repo / "docs" / "guide" / "changelog.md").write_text(CHANGELOG.replace("## v1.0.0 (", "## v1x0x0 ("))
    assert run(repo, "v1.0.0").returncode == 1


def test_notes_are_the_section(repo):
    r = run(repo, "--notes", "v1.0.0")
    assert r.returncode == 0
    assert "Body one." in r.stdout and "### Part" in r.stdout and "Body two." in r.stdout
    assert "Old." not in r.stdout and "Unreleased" not in r.stdout


def test_plan_stops_when_release_exists(repo):
    for core, models in (("no", "no"), ("yes", "yes")):
        r = run(repo, "--plan", "v1.0.0", release="yes", core=core, models=models)
        assert r.returncode == 1 and r.stdout == ""


def test_plan_build_when_nothing_exists(repo):
    r = run(repo, "--plan", "v1.0.0")
    assert (r.returncode, r.stdout.strip()) == (0, "build")


def test_plan_resume_when_images_exist(repo):
    r = run(repo, "--plan", "v1.0.0", core="yes", models="yes")
    assert (r.returncode, r.stdout.strip()) == (0, "resume")


@pytest.mark.parametrize("core,models", [("yes", "no"), ("no", "yes")])
def test_plan_stops_when_one_image_exists(repo, core, models):
    r = run(repo, "--plan", "v1.0.0", core=core, models=models)
    assert r.returncode == 1 and r.stdout == ""


FAILURES = [{"release": k} for k in ("other-message", "forbidden", "network")] + \
    [{key: k} for key in ("core", "models") for k in ("other-ref", "credential-helper", "not-found-127", "forbidden", "network")]


@pytest.mark.parametrize("kw", FAILURES)
def test_plan_other_failure_is_not_absence(repo, kw):
    r = run(repo, "--plan", "v1.0.0", **kw)
    assert r.returncode == 2 and r.stdout == "" and r.stderr


@pytest.mark.parametrize("missing", ["gh", "docker"])
def test_plan_needs_both_tools(repo, missing):
    (repo / "bin" / missing).unlink()
    # a PATH with only the fake bin dir and the basic tools of the script; the other real tool is not reachable
    tools = repo / "tools"
    tools.mkdir()
    for name in ("awk", "sed", "tr", "tail", "grep", "dirname", "cat"):
        (tools / name).symlink_to(subprocess.run(["which", name], capture_output=True, text=True).stdout.strip())
    env = {"ROOT": str(repo), "PATH": f"{repo / 'bin'}:{tools}", "FAKE_RELEASE": "no", "FAKE_CORE": "no",
           "FAKE_MODELS": "no", "FAKE_LOG": str(repo / "docker.log"), "GITHUB_REPOSITORY": "o/r",
           "IMAGE": "ghcr.io/o/core", "MODELS_IMAGE": "ghcr.io/o/kutuphane-models"}
    r = subprocess.run([subprocess.run(["which", "bash"], capture_output=True, text=True).stdout.strip(),
                        str(SCRIPT), "--plan", "v1.0.0"], env=env, capture_output=True, text=True)
    assert r.returncode == 2 and r.stdout == "" and missing in r.stderr


def test_plan_checks_the_tag_first(repo):
    r = run(repo, "--plan", "v1.0.0rc1")
    assert r.returncode == 1 and not (repo / "docker.log").exists()


def run_public(repo, **kw):
    env = {**os.environ, "ROOT": str(repo), "PATH": f"{repo / 'bin'}:{os.environ['PATH']}",
           "FAKE_CORE": kw.get("core", "yes"), "FAKE_MODELS": kw.get("models", "yes"), "FAKE_LOG": str(repo / "docker.log"),
           "DOCKER_CONFIG": str(repo / "real-config"), "IMAGE": "ghcr.io/o/core", "MODELS_IMAGE": "ghcr.io/o/kutuphane-models"}
    return subprocess.run(["bash", str(SCRIPT), "--public", "v1.0.0"], env=env, capture_output=True, text=True)


def test_public_both_readable(repo):
    r = run_public(repo)
    assert r.returncode == 0
    # no login is used: the DOCKER_CONFIG of the user is replaced by an empty directory
    for line in (repo / "docker.log").read_text().splitlines():
        assert "imagetools inspect" in line


def test_public_uses_an_empty_docker_config(repo):
    (repo / "bin" / "docker").write_text('#!/bin/sh\n[ -d "$DOCKER_CONFIG" ] && [ -z "$(ls -A "$DOCKER_CONFIG")" ] '
                                         '&& [ "$DOCKER_CONFIG" != "$REAL" ] || exit 1\n')
    env = {**os.environ, "ROOT": str(repo), "PATH": f"{repo / 'bin'}:{os.environ['PATH']}", "REAL": "/x",
           "DOCKER_CONFIG": "/x", "IMAGE": "a", "MODELS_IMAGE": "b"}
    r = subprocess.run(["bash", str(SCRIPT), "--public", "v1.0.0"], env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


@pytest.mark.parametrize("core,models,named", [("forbidden", "yes", "ghcr.io/o/core:v1.0.0"),
                                               ("yes", "forbidden", "ghcr.io/o/kutuphane-models:v1.0.0")])
def test_public_names_the_unreadable_image(repo, core, models, named):
    r = run_public(repo, core=core, models=models)
    assert r.returncode == 1 and named in r.stderr
    other = "ghcr.io/o/kutuphane-models:v1.0.0" if "core" in named else "ghcr.io/o/core:v1.0.0"
    assert other not in r.stderr


def test_public_both_unreadable(repo):
    r = run_public(repo, core="forbidden", models="forbidden")
    assert r.returncode == 1 and "core:v1.0.0" in r.stderr and "kutuphane-models:v1.0.0" in r.stderr
