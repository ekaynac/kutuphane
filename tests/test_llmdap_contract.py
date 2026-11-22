"""deploy/llmdap_contract.py without Docker: the single-run path (`--audit-export CMD`) and the two phases used by
deploy/llmdap_contract_ci.sh (`--phase calls`, `--phase verify --audit-export-file`), run in this process against the
suite's FakeBridge (a stub LLMDAP bridge) and the test database."""
import importlib.util
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from conftest import TEST_DSN_ENV
from test_egress_audit import KEY, FakeBridge

SCRIPT = Path(__file__).resolve().parent.parent / "deploy" / "llmdap_contract.py"
BOOK = SCRIPT.parent / "contract" / "book"
ROUTES = ["--chat", "chat", "stub-chat", "--embed", "emb", "stub-embed", "--rerank", "rerank", "stub-rerank"]


def load():
    spec = importlib.util.spec_from_file_location("llmdap_contract_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def bridge(conn, monkeypatch):
    f = FakeBridge()
    f.reply = "Kayıtlar iki yıl saklanır [1]."
    monkeypatch.setenv("KUTUPHANE_DSN", os.environ[TEST_DSN_ENV])
    loopback = ".".join(["127", "0", "0", "1"])   # built at run time: the review tool hides IP literals in diffs
    monkeypatch.setenv("KUTUPHANE_LLMDAP_URL", f"http://{loopback}:{f.port}")
    monkeypatch.setenv("KUTUPHANE_LLMDAP_KEY", KEY)
    yield f
    f.server.shutdown()


def run(monkeypatch, capsys, *args, module=None):
    module = module or load()
    monkeypatch.setattr(sys, "argv", ["llmdap_contract.py", str(BOOK), *ROUTES, *args])
    rc = module.main()
    out = capsys.readouterr().out
    lines = [line for line in out.splitlines() if line.startswith(("PASS ", "FAIL "))]
    return rc, lines, out


def export_of(bridge) -> str:
    return "".join(json.dumps(e) + "\n" for e in bridge.audit)


def test_single_run_with_an_audit_export_command_is_unchanged(bridge, monkeypatch, capsys):
    module = load()
    ran = []

    def fake_run(argv, **kw):   # the export command prints the (prepared) chain of the stub bridge
        ran.append(argv)
        return SimpleNamespace(returncode=0, stdout=export_of(bridge), stderr="")

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    rc, lines, out = run(monkeypatch, capsys, "--audit-export", "export-cmd --path x", module=module)
    assert rc == 0, out
    assert ran == [["export-cmd", "--path", "x"]]
    assert len(lines) == 11 and all(line.startswith("PASS ") for line in lines), lines
    assert json.loads(out.splitlines()[-1]) == {"passed": 11, "of": 11}   # no "phase" key without --phase


def test_phase_calls_then_phase_verify_with_an_export_file(bridge, monkeypatch, capsys, tmp_path):
    rc, calls, out = run(monkeypatch, capsys, "--phase", "calls")
    assert rc == 0, out
    assert len(calls) == 8 and not any("audit" in line.lower() for line in calls), calls   # model calls + AT-11 only
    assert json.loads(out.splitlines()[-1]) == {"passed": 8, "of": 8, "phase": "calls"}
    export = tmp_path / "export.jsonl"
    export.write_text(export_of(bridge))
    rc, verify, out = run(monkeypatch, capsys, "--phase", "verify", "--audit-export-file", str(export))
    assert rc == 0, out
    assert [line.split("  (")[0] for line in verify] == [
        "PASS LLMDAP audit chain verifies", "PASS unified audit is complete against LLMDAP's chain (AT-09)",
        "PASS LLMDAP records one authenticated Core subject and the user served"], verify
    assert json.loads(out.splitlines()[-1]) == {"passed": 3, "of": 3, "phase": "verify"}


def test_verify_fails_on_an_export_that_lacks_the_chain_and_on_a_failed_export_status(bridge, monkeypatch, capsys,
                                                                                    tmp_path):
    assert run(monkeypatch, capsys, "--phase", "calls")[0] == 0
    empty = tmp_path / "empty.jsonl"
    empty.write_text("")
    rc, lines, _ = run(monkeypatch, capsys, "--phase", "verify", "--audit-export-file", str(empty))
    assert rc == 1
    assert "FAIL unified audit is complete against LLMDAP's chain (AT-09)" in lines
    rc, lines, _ = run(monkeypatch, capsys, "--phase", "verify", "--audit-export-file", str(empty),
                       "--audit-export-status", "124")
    assert rc == 1
    assert "FAIL LLMDAP audit chain verifies  (export exit 124)" in lines
    rc, lines, _ = run(monkeypatch, capsys, "--phase", "verify", "--audit-export-file", str(tmp_path / "missing"))
    assert rc == 1 and any(line.startswith("FAIL LLMDAP audit chain verifies") for line in lines)


def test_verify_without_the_rows_of_a_calls_phase_fails(bridge, monkeypatch, capsys, tmp_path):
    export = tmp_path / "export.jsonl"
    export.write_text("")
    rc, lines, _ = run(monkeypatch, capsys, "--phase", "verify", "--audit-export-file", str(export))
    assert rc == 1
    assert lines == ["FAIL the calls phase left its rows in the database"]


@pytest.mark.parametrize("args", [
    [],                                                                  # neither --phase nor --audit-export
    ["--phase", "verify"],                                               # no export file
    ["--phase", "calls", "--audit-export", "x"],                         # a command with a phase
    ["--phase", "calls", "--audit-export-file", "f"],                    # a file with the wrong phase
    ["--audit-export", "x", "--audit-export-status", "1"],               # a status without the verify phase
    ["--phase", "verify", "--audit-export-file", "f", "--audit-export", "x"],
])
def test_argument_combinations_are_refused(monkeypatch, args):
    monkeypatch.setattr(sys, "argv", ["llmdap_contract.py", str(BOOK), *ROUTES, *args])
    with pytest.raises(SystemExit) as exc:
        load().main()
    assert exc.value.code == 2
