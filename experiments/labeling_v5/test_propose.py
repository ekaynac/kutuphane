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


def test_rejected_status_is_rejected_not_withdrawn(tmp_path):
    """D68: a source "Rejected" was never accepted, so it is its own state, not `withdrawn`."""
    case, case_dir = make_case(tmp_path, {}, text="Status: Rejected\n\n" + TEXT)
    out = propose.propose(propose.view(case, case_dir))
    assert out["acceptance"]["value"] == "rejected"
    assert out["normative"]["value"] == "history"
    assert propose.status_value("REJECTED") == "rejected"
    assert propose.status_value("Withdrawn") == "withdrawn"


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


def test_auto_set_hides_the_declared_licence_and_a_missing_copy(tmp_path):
    case, case_dir = make_case(tmp_path, {})
    case["files"][0].update(license_item="unknown", copy=False, local_path=None)
    assert "license" not in propose.propose(propose.view(case, case_dir, declared_licence=False))
    case["files"][0].update(license_item="MIT", copy=True, local_path="retries.md")
    assert propose.propose(propose.view(case, case_dir, declared_licence=False))["license"]["value"] == "unknown"
    case["files"][0]["license_item"] = propose.UNDER_TEST
    assert propose.view(case, case_dir)["files"][0]["license_item"] is None


def test_approval_without_remarks_is_not_substantive(tmp_path):
    ev = {"pr": {"author": "Copilot", "author_type": "Bot", "merged_by": "alice"},
          "commits": [{"sha": "s1", "author_login": "Copilot", "message": "Add page"}],
          "reviews": [{"user": "alice", "user_type": "User", "state": "APPROVED", "commit_id": "s1", "body": ""}],
          "review_comments": [], "issue_comments": [{"user": "alice", "user_type": "User", "body": "LGTM"}]}
    case, case_dir = make_case(tmp_path, ev)
    out = propose.propose(propose.view(case, case_dir))
    assert out["review"]["value"] == "approval-only"
    assert out["origin"]["value"] == "model"


def escaping_cases(tmp_path: Path) -> tuple[list, Path, str]:
    """Astra review #12: cases whose local_path points outside the case folder, or at a file that may not be copied."""
    secret = "GOLD-SECRET acceptance=rejected"
    (tmp_path / "pool.gold.jsonl").write_text(secret)
    (tmp_path / "cases").mkdir()
    case, case_dir = make_case(tmp_path / "cases", {"repo": "org/repo", "commit": "abc"}, text=secret)
    (case_dir / "link.md").symlink_to(tmp_path / "pool.gold.jsonl")
    variants = [{"local_path": "../../pool.gold.jsonl"}, {"local_path": "../t-1/retries.md"},
                {"local_path": str(tmp_path / "pool.gold.jsonl")}, {"local_path": "link.md"},
                {"local_path": "retries.md", "copy": False}, {"local_path": "retries.md", "copy": None},
                {"local_path": "."}, {"local_path": ["retries.md"]}]
    cases = [{**case, "files": [{**case["files"][0], **v}]} for v in variants]
    return cases, case_dir, secret


def test_view_reads_no_file_outside_the_case_folder_or_without_copy(tmp_path):
    cases, case_dir, secret = escaping_cases(tmp_path)
    for case in cases:
        v = propose.view(case, case_dir)
        assert v["files"][0]["text"] is None and secret not in json.dumps(v), case["files"][0]
    ok = {**cases[0], "files": [{"copy": True, "local_path": "retries.md"}]}
    assert propose.view(ok, case_dir)["files"][0]["text"] == secret
