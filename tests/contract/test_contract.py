# CONTRACT SNAPSHOT (#242). This test fails when the MCP tools, the HTTP routes, the error texts or the shape of the
# results that consumers depend on change. Changing tests/contract/*.json does NOT authorise the change: a PR that
# changes them needs the approval a contract change needs (SCOPE.md: Enes).
# The result files are built from a fixture in a real database: set KUTUPHANE_TEST_DSN (a `_test` database; it is
# reset). To regenerate: `python -m tests.contract.snapshot --write` with the same variable set.
import json
import os
import time
from contextlib import contextmanager

import pytest

from contract import helpers, matrix, snapshot

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


# --- the helpers: a bounded stream probe, and DSNs ----------------------------------------------------------------

STREAM_BOUND = 5.0  # seconds: far more than the 2 ms the probe takes, far less than a hang


def test_the_event_stream_probe_answers_within_a_bound(tmp_path):
    """GET /mcp in the 2025-11-25 era opens an event stream that never ends: the probe must still return."""
    verifier, key = snapshot._verifier(tmp_path)
    headers = {"Authorization": f"Bearer {snapshot.token_for(key)}", "MCP-Protocol-Version": matrix.ERAS[0],
               "Accept": "text/event-stream"}
    from starlette.testclient import TestClient
    with TestClient(snapshot.bare_app(verifier), base_url=snapshot.PUBLIC_URL) as client:
        started = time.monotonic()
        got = helpers.stream_answer(client, "GET", "/mcp", headers, timeout=STREAM_BOUND)
        took = time.monotonic() - started
    assert got["status"] == 200 and got["headers"]["content-type"].startswith("text/event-stream")
    assert got["body"] is None  # the stream was closed, not read
    assert took < STREAM_BOUND


def test_a_probe_that_never_answers_fails_with_a_message():
    class Hangs:
        @contextmanager
        def stream(self, *args, **kwargs):
            time.sleep(30)  # a client that buffers an endless stream
            yield None
    started = time.monotonic()
    with pytest.raises(TimeoutError, match="did not answer within 0.3 s"):
        helpers.stream_answer(Hangs(), "GET", "/mcp", {}, timeout=0.3)
    assert time.monotonic() - started < STREAM_BOUND


@pytest.mark.parametrize("dsn,expected", [
    ("postgresql://u:p%40ss@db:5432/app?sslmode=disable",
     {"user": "u", "password": "p@ss", "host": "db", "port": "5432", "dbname": "app", "sslmode": "disable"}),
    ("postgresql://u:p@db/app", {"user": "u", "password": "p", "host": "db", "dbname": "app"}),
    ("host=db user=u password='a b' dbname=app", {"host": "db", "user": "u", "password": "a b", "dbname": "app"}),
    ("postgresql://u@db/app?options=-cstatement_timeout%3D5s", {"user": "u", "host": "db", "dbname": "app"}),
])
def test_the_schema_goes_into_the_options_and_nothing_else_changes(dsn, expected):
    from psycopg.conninfo import conninfo_to_dict
    parts = conninfo_to_dict(helpers.dsn_with_schema(dsn, "install_b"))
    options = parts.pop("options")
    assert parts == expected  # every other parameter is kept, as parsed
    assert "-csearch_path=install_b,public" in options.split(" ")
    if "statement_timeout" in dsn:
        assert "-cstatement_timeout=5s" in options.split(" ")  # an existing option is kept, not replaced
