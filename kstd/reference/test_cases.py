"""Runs the kstd decision cases against the reference rule: `pytest kstd/reference`."""
from pathlib import Path

import pytest
import yaml

from decide import decide

CASES = yaml.safe_load((Path(__file__).parent.parent / "tests" / "decision" / "cases.yaml").read_text())["cases"]


def flatten(statements):
    """A case may extend the base list as [*base, [extra, ...]]."""
    out = []
    for s in statements:
        out.extend(flatten(s) if isinstance(s, list) else [s])
    return out


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_case(case):
    case = {**case, "statements": flatten(case["statements"])}
    got = decide(case)
    assert {k: got[k] for k in ("result", "authority", "reasons", "notices")} == case["expect"]
