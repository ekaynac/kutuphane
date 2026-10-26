"""The auto-set scorer (docs/21). Run: python -m pytest experiments/labeling_v5/test_eval_auto.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import eval_auto  # noqa: E402

GOLD = {
    "auto-pep-0001": {"acceptance": "rejected", "superseded_by": ["auto-pep-0002"], "supersession_scope": "full",
                      "license": "GPL-2.0-only"},
    "auto-pep-0002": {"acceptance": "accepted", "artifact_status": "Draft", "decision_time": "2026-01-01T00:00:00Z"},
    "auto-adr-fxa-0001": {"acceptance": None},
    "auto-np-x": {"case_kind": "retraction-other-key", "contest_mark": True},
    "auto-assist-a-pr1": {"origin": "model"},
}


def test_dangerous_errors_are_counted():
    got = {"auto-pep-0001": {"acceptance": "withdrawn", "license": "MIT"},
           "auto-pep-0002": {"acceptance": "pending"},
           "auto-adr-fxa-0001": {"acceptance": "accepted"},
           "auto-np-x": {"acceptance": "withdrawn"},
           "auto-assist-a-pr1": {"origin": "assisted"}}
    r = eval_auto.score(GOLD, got)
    assert r["errors"]["false_accepted"] == ["auto-adr-fxa-0001"]
    assert r["errors"]["missed_history"] == []  # withdrawn for rejected is wrong, but not a missed history state
    assert r["errors"]["missed_successor"] == ["auto-pep-0001"]
    assert r["errors"]["successor_not_flagged"] == []
    assert r["errors"]["withdrawn_by_other_key"] == ["auto-np-x"]
    assert r["errors"]["false_licence"] == ["auto-pep-0001 (MIT vs GPL-2.0-only)"]
    assert r["errors"]["false_assisted"] == ["auto-assist-a-pr1"]
    assert r["fields"]["acceptance: PEP"]["wrong"] == 1
    # the decision-time copy says Draft: `pending` is right for the text and wrong for the current state
    assert r["fields"]["acceptance vs artifact_status (12 decision-time PEPs)"]["correct"] == 1
    assert r["fields"]["acceptance vs current acceptance (12 decision-time PEPs)"]["wrong"] == 1
    assert r["fields"]["contest mark: nanopub"]["abstained"] == 1


def test_deprecated_spdx_ids_compare_equal():
    assert eval_auto.norm_licence("(GPL-2.0+ OR CC-BY-4.0)") == eval_auto.norm_licence("GPL-2.0-or-later OR CC-BY-4.0")
    assert eval_auto.norm_licence("GPL-2.0") == eval_auto.norm_licence("GPL-2.0-only")
    assert eval_auto.norm_licence("LGPL-2.1-only") == "lgpl-2.1-only"
