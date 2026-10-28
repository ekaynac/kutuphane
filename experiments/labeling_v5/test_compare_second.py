"""The operator vs second-reader comparison (docs/20 §8), on synthetic data only.
Run: python -m pytest experiments/labeling_v5/test_compare_second.py"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import compare_second  # noqa: E402

SELECTION = {"cases": [
    {"id": "r1", "group": "review-evidence", "stratum": "random", "second_reader": True},
    {"id": "r2", "group": "review-evidence", "stratum": "random", "second_reader": True},
    {"id": "r3", "group": "review-evidence", "stratum": "disagreement", "second_reader": True},
    {"id": "r4", "group": "review-evidence", "stratum": "disagreement", "second_reader": True},
    {"id": "p1", "group": "personal-data", "stratum": "random", "second_reader": True},
    {"id": "p2", "group": "personal-data", "stratum": "random", "second_reader": True},
    {"id": "p3", "group": "personal-data", "stratum": "disagreement", "second_reader": True},
    {"id": "c1", "group": "personal-data", "stratum": "calibration", "second_reader": False},
]}


def label(cid, group, value, stage="first"):
    field = compare_second.GROUP_FIELD[group]
    return {"id": cid, "set": "human", "group": group, "stage": stage, "labels": {field: value}}


LABELS = [label("r1", "review-evidence", "substantive"), label("r2", "review-evidence", "substantive"),
          label("r3", "review-evidence", "approval-only"), label("r4", "review-evidence", "substantive"),
          label("p1", "personal-data", "yes"), label("p2", "personal-data", "yes"),
          label("c1", "personal-data", "no"),  # not marked: never compared
          label("p1", "personal-data", "no", stage="revision")]  # a revision after the suggestions
SECOND = [{"id": "r1", "answer": "unknown"},  # replaced by the next line: the latest line counts
          {"id": "r1", "answer": "substantive", "reason": "a real remark", "evidence_pointer": "evidence.reviews"},
          {"id": "r2", "answer": "substantive", "reason": "x", "evidence_pointer": "file 1"},
          {"id": "r3", "answer": "approval-only", "reason": "x", "evidence_pointer": "file 1"},
          {"id": "r4", "answer": "approval-only", "reason": "only LGTM", "evidence_pointer": "evidence.reviews"},
          {"id": "p1", "answer": "yes", "reason": "x", "evidence_pointer": "file 1"},
          {"id": "p2", "answer": "unknown", "reason": "no text", "evidence_pointer": "none"},
          {"id": "c1", "answer": "no", "reason": "x", "evidence_pointer": "file 1"}]


def run(mode="first"):
    op = compare_second.operator_answers(LABELS, mode)
    return compare_second.compare(SELECTION, op, compare_second.second_answers(SECOND))


def test_kappa_known_values():
    # po = 3/4; marginals a:3,b:1 vs a:2,b:2 -> pe = (6 + 2) / 16 = 0.5 -> kappa = 0.5
    assert compare_second.cohen_kappa([("a", "a"), ("a", "a"), ("b", "b"), ("a", "b")]) == pytest.approx(0.5)
    assert compare_second.cohen_kappa([("a", "b"), ("b", "a")]) == pytest.approx(-1.0)
    assert compare_second.cohen_kappa([("a", "a"), ("a", "a")]) is None  # one category only: kappa is not defined
    assert compare_second.cohen_kappa([]) is None


def test_agreement_per_group_and_disagreements():
    r = run()
    assert r["marked"] == 7
    rev = r["groups"]["review-evidence"]
    assert (rev["pairs"], rev["agree"], rev["agreement"]) == (4, 3, 0.75)
    assert rev["kappa"] == pytest.approx(0.5, abs=1e-3)
    pd = r["groups"]["personal-data"]
    # first choices: p1 yes/yes, p2 yes/unknown; p3 has no operator label yet
    assert (pd["pairs"], pd["agree"], pd["decided_pairs"], pd["decided_agreement"]) == (2, 1, 1, 1.0)
    assert (pd["operator_unknown"], pd["second_unknown"]) == (0, 1)
    assert r["overall"]["pairs"] == 6 and r["overall"]["agree"] == 4
    assert r["strata"]["random"]["pairs"] == 4 and "calibration" not in r["strata"]
    assert [(d["id"], d["operator"], d["second"]) for d in r["disagreements"]] == [
        ("p2", "yes", "unknown"), ("r4", "substantive", "approval-only")]
    assert r["missing"] == [{"id": "p3", "group": "personal-data", "missing": ["operator", "second"]}]


def test_latest_uses_the_revision():
    r = run("latest")
    assert ("p1", "no", "yes") in [(d["id"], d["operator"], d["second"]) for d in r["disagreements"]]


def test_cli_reads_the_root(tmp_path, capsys, monkeypatch):
    (tmp_path / "human").mkdir()
    (tmp_path / "human" / "pool.selection.json").write_text(json.dumps(SELECTION))
    (tmp_path / "labels.jsonl").write_text("".join(json.dumps(x) + "\n" for x in LABELS))
    (tmp_path / "second_reader.astra.jsonl").write_text("".join(json.dumps(x) + "\n" for x in SECOND))
    monkeypatch.setattr(sys, "argv", ["compare_second.py", str(tmp_path), "--json"])
    assert compare_second.main() == 0
    out = json.loads(capsys.readouterr().out)
    assert out["overall"]["pairs"] == 6 and len(out["disagreements"]) == 2
    monkeypatch.setattr(sys, "argv", ["compare_second.py", str(tmp_path)])
    assert compare_second.main() == 0
    text = capsys.readouterr().out
    assert "Disagreements (2):" in text and "r4 [review-evidence, disagreement]" in text and "No pair yet (1):" in text
