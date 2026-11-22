# CONTRACT SNAPSHOT (#242). This test fails when the MCP tools, the HTTP routes, the error texts or the shape of the
# results that consumers depend on change. Changing tests/contract/*.json does NOT authorise the change: a PR that
# changes them needs the approval a contract change needs (SCOPE.md: Enes).
# The result files are built from a fixture in a real database: set KUTUPHANE_TEST_DSN (a `_test` database; it is
# reset). To regenerate: `python -m tests.contract.snapshot --write` with the same variable set.
import json
import os

import pytest

from contract import matrix, snapshot

MESSAGE = ("a contract changed: update tests/contract/*.json only with the approval a contract change needs "
           "(SCOPE.md: Enes). Regenerate with `python -m tests.contract.snapshot --write`.")


@pytest.fixture(scope="module")
def static():
    return snapshot.build_static()


@pytest.fixture(scope="module")
def results():
    dsn = os.environ.get(snapshot.DSN_ENV)
    if not dsn:
        pytest.skip(f"{snapshot.DSN_ENV} not set")
    return snapshot.build_results(dsn)


def check(name, built):
    stored = json.loads((snapshot.HERE / name).read_text(encoding="utf-8"))
    assert json.loads(snapshot.dump(built[name])) == stored, f"{name}: {MESSAGE}"


@pytest.mark.parametrize("name", ["tools.json", "http.json", "errors.json", "matrix.json"])
def test_the_listed_contract_is_unchanged(static, name):
    check(name, static)


@pytest.mark.parametrize("name", snapshot.RESULTS)
def test_the_shape_of_the_results_is_unchanged(results, name):
    check(name, results)


def test_every_tool_and_route_is_covered_and_coverage_does_not_shrink(static, results):
    per_era = [outcome["tools"] for outcome in results["results_http.json"]["MOUNT / [ok (tools/list)]"].values()]
    assert all(listed == per_era[0] for listed in per_era), "the protocol eras list different tools"
    tools = [t["name"] for t in per_era[0]]
    found = matrix.problems(tools, static["http.json"], results["results_mcp.json"], results["results_http.json"])
    assert not found, "the case matrix and the recorded cases disagree:\n" + "\n".join(found)
