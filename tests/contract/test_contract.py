# CONTRACT SNAPSHOT (#242). This test fails when the MCP tools, the HTTP routes or the error texts that consumers
# depend on change. Changing tests/contract/*.json (`python -m tests.contract.snapshot --write`) does NOT authorise
# the change: a PR that changes them needs the approval a contract change needs (SCOPE.md: Enes).
import json

import pytest

from contract import snapshot

MESSAGE = ("a contract changed: update tests/contract/*.json only with the approval a contract change needs "
           "(SCOPE.md: Enes). Regenerate with `python -m tests.contract.snapshot --write`.")


@pytest.fixture(scope="module")
def built():
    return snapshot.build()


@pytest.mark.parametrize("name", ["tools.json", "http.json", "errors.json"])
def test_the_contract_is_unchanged(built, name):
    stored = json.loads((snapshot.HERE / name).read_text(encoding="utf-8"))
    current = json.loads(snapshot.dump(built[name]))
    assert current == stored, f"{name}: {MESSAGE}"
