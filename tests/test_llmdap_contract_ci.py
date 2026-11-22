"""Regression tests of deploy/llmdap_contract_ci.sh (the LLMDAP contract runner, #243) on its error paths.

The script runs with a fake `docker` first on PATH: a small bash script that logs its arguments and, by the
environment variable FAKE_FAIL, fails one query. No Docker, no database and no network are needed; each case takes
seconds. Skipped only if bash is missing."""
import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "deploy" / "llmdap_contract_ci.sh"
BASH = shutil.which("bash")
pytestmark = pytest.mark.skipif(BASH is None, reason="bash is missing")

FAKE_DOCKER = r'''#!/usr/bin/env bash
# fake docker: logs every call; FAKE_STATE is a directory (created / removed markers)
echo "$*" >>"$FAKE_LOG"
args=" $* "
st="$FAKE_STATE"
before() { [ ! -e "$st/network" ]; }   # before `network create`
case "$1" in
  compose)
    case "$args" in
      *" version "*) exit 0 ;;
      *" up "*) touch "$st/containers"; exit 0 ;;
      *" --phase calls"*) echo "PASS calls one"; exit 0 ;;
      *" --phase verify"*)
        cp "$CONTRACT_EXPORT_DIR/export.jsonl" "$st/verify_saw"
        if [ -f "$st/child.pid" ] && kill -0 "$(cat "$st/child.pid")" 2>/dev/null; then echo alive >"$st/child_alive_at_verify"; fi
        case "$args" in *" --audit-export-status 0 "*) echo "PASS verify one"; exit 0 ;; esac
        echo "FAIL verify one (export failed)"; exit 1 ;;   # like the real contract: a failed export fails the check
      *" --entrypoint python "*) exit 0 ;;   # the bridge probe
    esac
    exit 0 ;;
  ps)
    if before; then [ "$FAKE_FAIL" = pre_ps ] && { echo "fake: cannot connect" >&2; exit 1; }; exit 0; fi
    [ "$FAKE_FAIL" = td_ps ] && { echo "fake: cannot connect" >&2; exit 1; }
    [ -e "$st/containers" ] && echo aaaaaaaaaaaa
    exit 0 ;;
  volume)
    case "$2" in
      ls) if before; then [ "$FAKE_FAIL" = pre_vol ] && { echo "fake: cannot connect" >&2; exit 1; }; fi; exit 0 ;;
      rm) exit 0 ;;
    esac ;;
  network)
    case "$2" in
      ls) if before; then [ "$FAKE_FAIL" = pre_net ] && { echo "fake: cannot connect" >&2; exit 1; }; exit 0; fi
          [ -e "$st/network" ] && echo bbbbbbbbbbbb; exit 0 ;;
      create) touch "$st/network"; exit 0 ;;
      rm) rm -f "$st/network"; exit 0 ;;
      inspect) exit 0 ;;
      disconnect) exit 0 ;;
    esac ;;
  rm) rm -f "$st/containers"; exit 0 ;;
  inspect) exit 0 ;;
esac
exit 0
'''


@pytest.fixture
def run(tmp_path):
    fakebin = tmp_path / "bin"
    fakebin.mkdir()
    docker = fakebin / "docker"
    docker.write_text(FAKE_DOCKER)
    docker.chmod(0o755)
    state = tmp_path / "state"
    state.mkdir()
    log = tmp_path / "docker.log"
    log.write_text("")

    def go(export, fail="", extra=(), timeout=60):
        env = {**os.environ, "PATH": f"{fakebin}:{os.environ['PATH']}", "FAKE_LOG": str(log), "FAKE_STATE": str(state),
               "FAKE_FAIL": fail, "KUTUPHANE_LLMDAP_URL": "http://llmdap:8787", "KUTUPHANE_LLMDAP_KEY": "k",
               "STATE": str(state)}
        proc = subprocess.run([BASH, str(SCRIPT), "--image", "x", "--audit-export", export, *extra], env=env,
                              capture_output=True, text=True, timeout=timeout)
        return proc, log.read_text().splitlines(), state

    return go


def alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def test_teardown_listing_fails_removes_nothing_and_exits_3(run):
    proc, calls, _ = run("echo x", fail="td_ps")
    assert proc.returncode == 3, proc.stderr
    assert "teardown failed" in proc.stderr
    # no removal with an argument that is not an id: here no removal at all
    assert not [c for c in calls if c.startswith(("rm ", "volume rm"))], calls
    assert not any("fake: cannot connect" in c for c in calls)


def test_good_run_removes_its_containers_by_id_and_exits_0(run):
    proc, calls, state = run("echo x")
    assert proc.returncode == 0, proc.stderr
    assert "PASS calls one" in proc.stdout and "PASS verify one" in proc.stdout
    assert '{"passed": 2, "of": 2}' in proc.stdout
    assert "rm -f -v aaaaaaaaaaaa" in calls
    assert not (state / "network").exists()


@pytest.mark.parametrize("fail", ["pre_ps", "pre_vol", "pre_net"])
def test_each_precheck_query_failing_exits_2_and_creates_nothing(run, fail):
    proc, calls, _ = run("echo x", fail=fail)
    assert proc.returncode == 2, proc.stderr
    assert not [c for c in calls if c.startswith("network create")], calls
    assert not [c for c in calls if c.startswith(("rm ", "network rm", "volume rm"))], calls


def test_export_group_is_ended_before_verify_and_the_file_stays(run):
    # the leader prints and exits; its background child would append `late` after 3 s
    export = "sh -c '{ sleep 3; echo late; } & echo $! >\"$STATE/child.pid\"; echo x'"
    proc, calls, state = run(export)
    assert proc.returncode == 0, proc.stderr
    pid = int((state / "child.pid").read_text())
    assert not (state / "child_alive_at_verify").exists(), "a member of the group lived when verify started"
    assert not alive(pid)
    saw = (state / "verify_saw").read_text()
    assert saw == "x\n"
    time.sleep(3.5)   # a surviving child would have written by now
    assert saw == "x\n"
    # the file of the run is gone with its directory; the content verify read was the leader's output only


def test_timeout_kills_the_whole_group(run):
    export = "sh -c 'sleep 30 & echo $! >\"$STATE/child.pid\"; sleep 30'"
    proc, calls, state = run(export, extra=("--export-timeout", "1"), timeout=60)
    assert proc.returncode == 1, proc.stderr
    assert "ran longer than 1s and was killed" in proc.stderr
    assert any("--audit-export-status 124" in c for c in calls), calls
    assert not (state / "child_alive_at_verify").exists()
    assert not alive(int((state / "child.pid").read_text()))
