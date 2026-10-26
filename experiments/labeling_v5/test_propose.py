"""The v5 proposer must not read answers (docs/20 §5, Astra P0). Run: python -m pytest experiments/labeling_v5/test_propose.py"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import propose  # noqa: E402

TEXT = "# Payment retries\n\nThe service retries a failed payment three times.\n"


def make_case(tmp_path: Path, evidence: dict, text: str = TEXT) -> tuple[dict, Path]:
    case = {"id": "t-1", "set": "auto", "group": "supersession", "source": "org/repo", "family": "org/repo:x",
            "operation": "search", "questions": ["Q13"], "why_selected": "Status: Accepted by the council",
            "files": [{"path": "docs/retries.md", "copy": True, "local_path": "retries.md", "license_item": "MIT"}],
            "evidence": evidence,
            "statements": [{"kind": "acceptance", "issuer": "council", "body": {"acceptance": "accepted"}}],
            "known": {"acceptance": "accepted"}, "gold": {"acceptance": "accepted"}}
    case_dir = tmp_path / case["id"]
    case_dir.mkdir()
    (case_dir / "retries.md").write_text(text)
    return case, case_dir


def test_no_status_line_in_evidence_gives_no_acceptance(tmp_path):
    case, case_dir = make_case(tmp_path, {"repo": "org/repo", "commit": "abc"})
    for baseline in (False, True):
        assert "acceptance" not in propose.propose(propose.view(case, case_dir, baseline))


def test_status_line_in_evidence_gives_acceptance(tmp_path):
    case, case_dir = make_case(tmp_path, {"status_line": "Final"})
    assert propose.propose(propose.view(case, case_dir))["acceptance"]["value"] == "accepted"


def test_view_keeps_only_bytes_path_licence_and_evidence(tmp_path):
    case, case_dir = make_case(tmp_path, {"repo": "org/repo"})
    v = propose.view(case, case_dir)
    assert set(v) == {"id", "files", "evidence"}
    assert set(v["files"][0]) == {"path", "role", "license_item", "text"}
    assert "accepted" not in json.dumps(v).lower()
    assert propose.view(case, case_dir, baseline=True)["files"][0]["text"] is None


def test_stale_after_is_not_validity(tmp_path):
    case, case_dir = make_case(tmp_path, {}, text="---\nstale_after: 2026-12-01\n---\n" + TEXT)
    out = propose.propose(propose.view(case, case_dir))
    assert "valid_to" not in out
    assert out["stale_after"]["value"] == "2026-12-01"


def test_approval_without_remarks_is_not_substantive(tmp_path):
    ev = {"pr": {"author": "Copilot", "author_type": "Bot", "merged_by": "alice"},
          "commits": [{"sha": "s1", "author_login": "Copilot", "message": "Add page"}],
          "reviews": [{"user": "alice", "user_type": "User", "state": "APPROVED", "commit_id": "s1", "body": ""}],
          "review_comments": [], "issue_comments": [{"user": "alice", "user_type": "User", "body": "LGTM"}]}
    case, case_dir = make_case(tmp_path, ev)
    out = propose.propose(propose.view(case, case_dir))
    assert out["review"]["value"] == "approval-only"
    assert out["origin"]["value"] == "model"
