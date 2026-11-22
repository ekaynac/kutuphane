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

LOCK_ID, CONTAINER_ID, NETWORK_ID = "c" * 64, "a" * 64, "b" * 64   # `docker create` prints the full id; `ps -q` 12 characters

FAKE_DOCKER = r'''#!/usr/bin/env bash
# fake docker: logs every call. FAKE_STATE is a directory of markers (lock, containers, network).
# FAKE_FAIL names the one call that fails; FAKE_NET_CONTAINERS lists the containers `network inspect` shows.
echo "$*" >>"$FAKE_LOG"
args=" $* "
st="$FAKE_STATE"
cannot() { echo "fake: cannot connect" >&2; exit 1; }
case "$1" in
  create)   # the lock container
    [ "$FAKE_FAIL" = lock ] && { echo "fake: Conflict. The container name is already in use" >&2; exit 1; }
    touch "$st/lock"; printf "c%.0s" $(seq 64); echo; exit 0 ;;
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
    esac
    exit 0 ;;
  ps)
    case "$args" in
      *com.docker.compose.project*) [ "$FAKE_FAIL" = pre_ps ] && cannot; exit 0 ;;
      *) [ "$FAKE_FAIL" = td_ps ] && cannot
         a=aaaaaaaaaaaa c=cccccccccccc   # without --no-trunc: 12 characters, like the real docker
         case "$args" in *" --no-trunc "*) a=$a$a$a$a$a$a; a=${a:0:64}; c=$c$c$c$c$c$c; c=${c:0:64} ;; esac
         [ -e "$st/containers" ] && echo "$a"
         [ -e "$st/lock" ] && echo "$c"
         exit 0 ;;
    esac ;;
  volume)
    case "$2" in
      ls) case "$args" in *com.docker.compose.project*) [ "$FAKE_FAIL" = pre_vol ] && cannot ;; esac; exit 0 ;;
      rm) exit 0 ;;
    esac ;;
  network)
    case "$2" in
      ls) case "$args" in
            *" name="*) [ "$FAKE_FAIL" = pre_net ] && cannot; exit 0 ;;
            *) [ -e "$st/network" ] && echo bbbbbbbbbbbb; exit 0 ;;   # short id: only a presence check
          esac ;;
      create) touch "$st/network"; printf "b%.0s" $(seq 64); echo; exit 0 ;;
      rm) rm -f "$st/network"; exit 0 ;;
      inspect) [ "$FAKE_FAIL" = net_inspect ] && cannot; echo "$FAKE_NET_CONTAINERS"; exit 0 ;;
      disconnect) exit 0 ;;
    esac ;;
  rm)
    case "$args" in *" aaaaaaaaaaaa"*) rm -f "$st/containers" ;; esac
    case "$args" in *" cccccccccccc"*) rm -f "$st/lock" ;; esac
    exit 0 ;;
  inspect)   # aliases of a container, from FAKE_ALIAS_<container id>
    [ "$FAKE_FAIL" = ctr_inspect ] && cannot
    for last; do :; done
    var="FAKE_ALIAS_$last"; echo "${!var:-}"; exit 0 ;;
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

    def go(export="echo x", fail="", extra=(), timeout=90, **env_extra):
        env = {**os.environ, "PATH": f"{fakebin}:{os.environ['PATH']}", "FAKE_LOG": str(log), "FAKE_STATE": str(state),
               "FAKE_FAIL": fail, "KUTUPHANE_LLMDAP_URL": "http://llmdap:8787", "KUTUPHANE_LLMDAP_KEY": "k",
               "STATE": str(state), **env_extra}
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


def removals(calls):
    return [c for c in calls if c.startswith(("rm ", "volume rm", "network rm"))]


def test_good_run_removes_its_resources_by_id_and_exits_0(run):
    proc, calls, state = run()
    assert proc.returncode == 0, proc.stderr
    assert "PASS calls one" in proc.stdout and "PASS verify one" in proc.stdout
    assert '{"passed": 2, "of": 2}' in proc.stdout
    assert f"rm -f -v {CONTAINER_ID}" in calls
    assert f"network rm {NETWORK_ID}" in calls
    # the lock goes last of the removals
    assert removals(calls)[-1] == f"rm -f -v {LOCK_ID}"
    assert len([c for c in removals(calls) if "cccc" in c]) == 1, "the lock (any id length) is removed once, and last"
    assert "teardown failed" not in proc.stderr
    assert not (state / "network").exists() and not (state / "lock").exists()


def test_an_export_command_that_exits_125_is_an_ordinary_failure(run):
    proc, calls, _ = run("sh -c 'echo x; exit 125'")
    assert proc.returncode == 1, proc.stderr
    assert any("--phase verify" in c and "--audit-export-status 125" in c for c in calls), calls   # verify ran
    assert "could not be ended" not in proc.stderr


def test_second_run_cannot_take_the_lock_and_changes_nothing(run):
    proc, calls, _ = run(fail="lock")
    assert proc.returncode == 2, proc.stderr
    assert "cannot take the lock" in proc.stderr
    assert not [c for c in calls if c.startswith("network create")], calls
    assert not removals(calls), calls


@pytest.mark.parametrize("fail", ["pre_ps", "pre_vol", "pre_net"])
def test_each_precheck_query_failing_exits_2_and_creates_nothing(run, fail):
    proc, calls, _ = run(fail=fail)
    assert proc.returncode == 2, proc.stderr
    assert not [c for c in calls if c.startswith("network create")], calls
    # only the lock, which this run holds, is removed
    assert removals(calls) == [f"rm -f -v {LOCK_ID}"], calls


def test_teardown_listing_fails_removes_no_listed_container_and_exits_3(run):
    proc, calls, _ = run(fail="td_ps")
    assert proc.returncode == 3, proc.stderr
    assert "teardown failed: cannot list the run's containers" in proc.stderr
    assert f"rm -f -v {CONTAINER_ID}" not in calls
    assert all(c.split()[-1] in (LOCK_ID, NETWORK_ID) for c in removals(calls)), calls   # by known id only


BRIDGE_ID, OTHER_ID = "d" * 64, "e" * 64


@pytest.mark.parametrize("fail", ["net_inspect", "ctr_inspect"])
def test_a_failed_detach_query_is_a_teardown_failure(run, fail):
    proc, calls, _ = run(fail=fail, FAKE_NET_CONTAINERS=BRIDGE_ID, **{f"FAKE_ALIAS_{BRIDGE_ID}": "llmdap"})
    assert proc.returncode == 3, proc.stderr
    assert "teardown failed: cannot inspect" in proc.stderr
    assert not [c for c in calls if c.startswith("network disconnect")], calls
    assert f"network rm {NETWORK_ID}" in calls   # the removal is still tried


def test_the_bridge_with_the_alias_is_detached_by_ids_and_the_other_container_is_not(run):
    proc, calls, _ = run(FAKE_NET_CONTAINERS=f"{BRIDGE_ID} {OTHER_ID}",
                         **{f"FAKE_ALIAS_{BRIDGE_ID}": "abc llmdap", f"FAKE_ALIAS_{OTHER_ID}": "abc other"})
    assert proc.returncode == 0, proc.stderr
    disconnects = [c for c in calls if c.startswith("network disconnect")]
    assert disconnects == [f"network disconnect -f {NETWORK_ID} {BRIDGE_ID}"], calls


def test_export_group_is_ended_before_verify_and_the_file_stays(run):
    # the leader prints and exits; its background child would append `late` after 3 s
    export = "sh -c '{ sleep 3; echo late; } & echo $! >\"$STATE/child.pid\"; echo x'"
    proc, calls, state = run(export)
    assert proc.returncode == 0, proc.stderr
    pid = int((state / "child.pid").read_text())
    assert not (state / "child_alive_at_verify").exists(), "a member of the group lived when verify started"
    assert not alive(pid)
    assert (state / "verify_saw").read_text() == "x\n"
    time.sleep(3.5)   # a surviving child would have written by now
    assert (state / "verify_saw").read_text() == "x\n"


def test_timeout_kills_the_whole_group(run):
    export = "sh -c 'sleep 30 & echo $! >\"$STATE/child.pid\"; sleep 30'"
    proc, calls, state = run(export, extra=("--export-timeout", "1"))
    assert proc.returncode == 1, proc.stderr
    assert "ran longer than 1s and was killed" in proc.stderr
    assert any("--audit-export-status 124" in c for c in calls), calls
    assert not (state / "child_alive_at_verify").exists()
    assert not alive(int((state / "child.pid").read_text()))


def test_a_group_that_cannot_be_ended_stops_before_verify(run, tmp_path):
    hook = tmp_path / "alive"
    hook.write_text("")   # test hook: the group counts as alive while this file exists
    proc, calls, _ = run(LLMDAP_CONTRACT_CI_TEST_GROUP_ALIVE=str(hook))
    assert proc.returncode == 125, proc.stderr
    assert "could not be ended" in proc.stderr
    assert not [c for c in calls if "--phase verify" in c], calls
    assert "still alive" in proc.stderr   # cleanup tried again and says so


def test_a_leader_that_cannot_be_ended_does_not_block_the_run(run, tmp_path):
    hook = tmp_path / "alive"
    hook.write_text("")   # test hook: leader and group count as alive while this file exists
    export = "sh -c 'trap \"\" TERM; sleep 60'"   # a leader that ignores TERM
    start = time.monotonic()
    proc, calls, _ = run(export, extra=("--export-timeout", "1"), timeout=60,
                         LLMDAP_CONTRACT_CI_TEST_GROUP_ALIVE=str(hook))
    assert proc.returncode == 125, proc.stderr
    assert time.monotonic() - start < 40, "the run waited for the leader"
    assert not [c for c in calls if "--phase verify" in c], calls
    assert "ran longer than 1s and was killed" in proc.stderr and "could not be ended" in proc.stderr
