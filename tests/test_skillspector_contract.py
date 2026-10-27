"""D71 contract test: the pinned SkillSpector behaves as skillscan.py expects. It runs only when
KUTUPHANE_SKILLSPECTOR_BIN names an installed SkillSpector (deploy/skillspector/install.sh); the upstream fixtures
come from PREFIX/share/skillspector/fixtures, the harmless sample from tests/fixtures/skills.

Checked: the version, the JSON keys that skillscan.py reads, the exit codes and the verdicts, and a stable report
digest through the adapter (with its minimal environment)."""
import json
import os
import subprocess
import tempfile
from pathlib import Path

import pytest

from kutuphane import skillscan

BIN = os.environ.get(skillscan.BIN_ENV)  # read at collection: conftest removes it from every test's environment
PROXY = os.environ.get(skillscan.PROXY_ENV)
pytestmark = pytest.mark.skipif(not BIN, reason=f"{skillscan.BIN_ENV} not set (deploy/skillspector/install.sh)")

UPSTREAM = Path(BIN).resolve().parent.parent / "share" / "skillspector" / "fixtures" if BIN else None
HARMLESS = Path(__file__).parent / "fixtures" / "skills" / "harmless-summary"
CASES = [("upstream", "safe_skill", "SAFE", 0), ("upstream", "malicious_skill", "DO_NOT_INSTALL", 1),
         ("ours", "harmless-summary", "SAFE", 0)]


@pytest.fixture(autouse=True)
def configured(monkeypatch):
    monkeypatch.setenv(skillscan.BIN_ENV, BIN)
    if PROXY:
        monkeypatch.setenv(skillscan.PROXY_ENV, PROXY)


def folder(where: str, name: str) -> Path:
    return (UPSTREAM if where == "upstream" else HARMLESS.parent) / name


def files_of(path: Path) -> dict[str, bytes]:
    return {p.relative_to(path).as_posix(): p.read_bytes() for p in sorted(path.rglob("*")) if p.is_file()}


def test_the_installed_version_is_the_tested_one():
    assert skillscan.probe().version == skillscan.TESTED_VERSION


@pytest.mark.parametrize("where, name, recommendation, exit_code", CASES)
def test_json_keys_exit_codes_and_verdicts(where, name, recommendation, exit_code):
    with tempfile.TemporaryDirectory() as home:
        out = subprocess.run([BIN, "scan", str(folder(where, name)), "--no-llm", "--format", "json"],
                             env=skillscan._env(home), cwd=home, capture_output=True, timeout=300, check=False)
    assert out.returncode == exit_code, out.stderr.decode(errors="replace")[-2000:]
    report = json.loads(out.stdout)
    assert {"skill", "risk_assessment", "components", "issues", "analysis_completeness", "metadata"} <= set(report)
    assert report["metadata"]["skillspector_version"] == skillscan.TESTED_VERSION
    assert report["metadata"]["llm_requested"] is False
    assert report["risk_assessment"]["recommendation"] == recommendation
    assert isinstance(report["risk_assessment"]["score"], int)
    assert report["analysis_completeness"]["status"] == "complete"
    for issue in report["issues"]:
        assert {"id", "finding_id", "severity", "location"} <= set(issue)


@pytest.mark.parametrize("where, name, recommendation, exit_code", CASES)
def test_the_adapter_records_a_stable_proposal(where, name, recommendation, exit_code):
    tool = skillscan.probe()
    files = files_of(folder(where, name))
    one, two = skillscan.run(tool, "beceri", files), skillscan.run(tool, "beceri", files)
    assert (one.status, one.recommendation, one.completeness) == ("scanned", recommendation, "complete")
    assert one.blocking == (recommendation == "DO_NOT_INSTALL")
    assert one.report_digest == two.report_digest and one.findings == two.findings
    assert all("finding_id" not in issue for issue in one.findings)
