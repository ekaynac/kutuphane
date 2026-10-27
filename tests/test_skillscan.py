"""D71, docs/24 §22: SkillSpector scan records of skill folders, the `activate` block and the curator clearance.
A fake `skillspector` executable prints fixed JSON; tests/test_skillspector_contract.py runs the real one."""
import hashlib
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import psycopg
import pytest

from kutuphane import answers, authz, catalog, cli, db, gate, packages, profiles, search, signing, skillscan
from kutuphane.gate import Actor, Denied
from kutuphane.policy import make_policy
from kutuphane.source import read_source
from test_egress_audit import FakeBridge

U, CURATOR, A = "user:ayse", "user:kurator", "agent:kobra-7"
BOOK, OBJ = "kitap", "book:kitap"
SKILL, REF, OTHER = "araclar/ozet", "araclar/ozet/references/kaynak.md", "politika/veri-saklama.md"
POLICY = make_policy(sensitivity="normal", egress="local_only", protection="standard")
PIN = Path(__file__).parent.parent / "deploy" / "skillspector" / "skillspector.pin"

FAKE = r'''#!{python}
import datetime, json, os, sys, time, uuid
HERE = {here!r}
with open(os.path.join(HERE, "calls.jsonl"), "a") as f:
    f.write(json.dumps({{"args": sys.argv[1:], "env": dict(os.environ)}}) + "\n")
version = open(os.path.join(HERE, "version")).read().strip()
if sys.argv[1:] == ["--version"]:
    print(f"SkillSpector v{{version}}")
    sys.exit(0)
root = sys.argv[2]
text = open(os.path.join(root, "SKILL.md"), encoding="utf-8").read()
verdict = open(os.path.join(HERE, "verdict")).read().strip() if os.path.exists(os.path.join(HERE, "verdict")) else ""
for marker in ("DO_NOT_INSTALL", "CAUTION", "PARTIAL", "CRASH", "SLEEP", "BADJSON", "WRONGVERSION"):
    if "FAKE:" + marker in text:
        verdict = verdict or marker
if verdict == "CRASH":
    sys.exit(2)
if verdict == "SLEEP":
    time.sleep(30)
if verdict == "BADJSON":
    print("not json")
    sys.exit(0)
recommendation = verdict if verdict in ("DO_NOT_INSTALL", "CAUTION") else "SAFE"
issues = [] if recommendation == "SAFE" else [{{"id": "P5", "finding_id": "finding-" + uuid.uuid4().hex,
          "severity": "CRITICAL", "location": {{"file": "SKILL.md", "start_line": 3}}, "finding": "x"}}]
report = {{
    "skill": {{"name": "fake", "source": root, "scanned_at": datetime.datetime.now().isoformat()}},
    "risk_assessment": {{"score": {{"SAFE": 0, "CAUTION": 30, "DO_NOT_INSTALL": 100}}[recommendation],
                         "recommendation": recommendation}},
    "components": [{{"path": p}} for p in sorted(os.listdir(root))],
    "issues": issues,
    "metadata": {{"skillspector_version": "0.0.1" if verdict == "WRONGVERSION" else version}},
    "execution_successful": True,
    "analysis_completeness": {{"status": "partial" if verdict == "PARTIAL" else "complete"}},
}}
print(json.dumps(report))
sys.exit(1 if recommendation == "DO_NOT_INSTALL" else 0)
'''


class Fake:
    def __init__(self, here: Path):
        self.here = here
        self.bin = here / "skillspector"
        self.bin.write_text(FAKE.format(python=sys.executable, here=str(here)), encoding="utf-8")
        self.bin.chmod(0o755)
        self.version = skillscan.TESTED_VERSION

    @property
    def version(self) -> str:
        return (self.here / "version").read_text().strip()

    @version.setter
    def version(self, value: str) -> None:
        (self.here / "version").write_text(value)

    def verdict(self, value: str | None) -> None:
        """Override every scan's verdict (None: the markers in SKILL.md decide)."""
        path = self.here / "verdict"
        path.unlink(missing_ok=True)
        if value:
            path.write_text(value)

    def calls(self) -> list[dict]:
        path = self.here / "calls.jsonl"
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def scans(self) -> int:
        return sum(1 for c in self.calls() if c["args"][:1] == ["scan"])


@pytest.fixture
def fake(tmp_path, monkeypatch):
    here = tmp_path / "fake-skillspector"
    here.mkdir()
    f = Fake(here)
    monkeypatch.setenv(skillscan.BIN_ENV, str(f.bin))
    return f


def soon():
    return datetime.now(timezone.utc) + timedelta(hours=1)


@pytest.fixture
def folder(okf_dir):
    def write(skill_text="Özetle ve kaydet.\n", reference="Kaynak listesi.\n"):
        for rel, text in ((f"{SKILL}/SKILL.md", skill_text), (REF, reference)):
            (okf_dir / rel).parent.mkdir(parents=True, exist_ok=True)
            (okf_dir / rel).write_text(text, encoding="utf-8")
        return okf_dir
    write()
    return write


def publish(conn, path):
    return catalog.publish(conn, book=BOOK, title=BOOK, files=read_source(path), policy=POLICY,
                           profile=profiles.spec("chunked"))


def agent_with(conn, *modes):
    for mode in modes:
        authz.grant(conn, OBJ, mode, U)
        authz.delegate(conn, delegator=U, delegate_to=A, obj=OBJ, mode=mode, expires_at=soon())
    return Actor(A, on_behalf_of=U)


def records(conn):
    return conn.execute("SELECT skill_path, status, recommendation, completeness, tool_version, stale, reason "
                        "FROM skill_scan ORDER BY id").fetchall()


def curate(conn):
    authz.grant(conn, OBJ, "curate", CURATOR)


# --- not configured ---------------------------------------------------------------------------------------

def test_without_skillspector_ingest_works_and_records_not_scanned(conn, folder):
    r = publish(conn, folder())
    assert [(s["skill_path"], s["status"], s["blocking"]) for s in r.skill_scans] == [(SKILL, "not_scanned", False)]
    assert records(conn) == [(SKILL, "not_scanned", None, None, None, False,
                              f"SkillSpector is not configured ({skillscan.BIN_ENV} is not set)")]
    agent = agent_with(conn, "read", "activate")
    assert gate.deliver_file(conn, agent, BOOK, r.content_id, f"{SKILL}/SKILL.md")  # not_scanned does not block
    publish(conn, folder())
    assert len(records(conn)) == 1  # the same version again: no second not_scanned record


def test_a_book_without_skills_never_runs_the_tool(conn, okf_dir, fake):
    assert publish(conn, okf_dir).skill_scans == [] and fake.calls() == []


# --- the block ----------------------------------------------------------------------------------------------

def test_do_not_install_blocks_activate_for_that_skill_at_once(conn, folder, fake):
    r = publish(conn, folder("FAKE:DO_NOT_INSTALL\n"))
    assert [(s["status"], s["recommendation"], s["score"], s["blocking"]) for s in r.skill_scans] == [
        ("scanned", "DO_NOT_INSTALL", 100, True)]
    agent = agent_with(conn, "read", "activate")
    for path in (f"{SKILL}/SKILL.md", REF):  # every file of the skill folder
        with pytest.raises(Denied, match="skill blocked"):
            gate.deliver_file(conn, agent, BOOK, r.content_id, path)
    event = conn.execute("SELECT action, allowed, reason, grant_ids FROM access_event WHERE correlation_id = %s "
                         "ORDER BY id DESC LIMIT 1", (agent.correlation_id,)).fetchone()
    assert event[:3] == ("activate", False, gate.SKILL_BLOCKED) and event[3]  # the overridden grant is on record
    assert gate.deliver_file(conn, agent, BOOK, r.content_id, OTHER)  # outside the skill: unchanged
    assert gate.deliver_file(conn, Actor(U), BOOK, r.content_id, REF)  # a person still reads it as reference
    assert not {h.citation.path for h in search.search(conn, agent, "kaynak listesi", k=50)} & {REF}
    assert REF in {h.citation.path for h in search.search(conn, Actor(U), "kaynak listesi", k=50)}
    chunk = conn.execute("SELECT profile_id, ordinal FROM chunk WHERE book = %s AND path = %s LIMIT 1",
                         (BOOK, REF)).fetchone()
    with pytest.raises(Denied, match="skill blocked"):
        search.open_citation(conn, agent, search.Citation(BOOK, r.content_id, chunk[0], REF, chunk[1]))


@pytest.mark.parametrize("marker, status, reason", [
    ("FAKE:PARTIAL", "scanned", None), ("FAKE:CRASH", "failed", "exit 2"),
    ("FAKE:BADJSON", "failed", "no valid report: JSONDecodeError"),
    ("FAKE:WRONGVERSION", "failed", "the report names version '0.0.1', not 2.13.1")])
def test_partial_coverage_and_failed_scans_block(conn, folder, fake, marker, status, reason):
    r = publish(conn, folder(marker + "\n"))
    assert [(s["status"], s["reason"], s["blocking"]) for s in r.skill_scans] == [(status, reason, True)]
    with pytest.raises(Denied, match="skill blocked"):
        gate.deliver_file(conn, agent_with(conn, "read", "activate"), BOOK, r.content_id, f"{SKILL}/SKILL.md")


def test_a_scan_that_times_out_fails_and_blocks(conn, folder, fake, monkeypatch):
    monkeypatch.setenv(skillscan.TIMEOUT_ENV, "2")
    r = publish(conn, folder("FAKE:SLEEP\n"))
    assert [(s["status"], s["reason"]) for s in r.skill_scans] == [("failed", "timeout after 2 s")]
    assert r.skill_scans[0]["blocking"]


def test_safe_and_caution_grant_nothing(conn, folder, fake):
    r = publish(conn, folder("FAKE:CAUTION\n"))
    assert [(s["recommendation"], s["blocking"]) for s in r.skill_scans] == [("CAUTION", False)]
    with pytest.raises(Denied, match="activate"):  # SAFE or CAUTION never stands in for the grant
        gate.deliver_file(conn, agent_with(conn, "read"), BOOK, r.content_id, f"{SKILL}/SKILL.md")
    assert gate.deliver_file(conn, agent_with(conn, "read", "activate"), BOOK, r.content_id, f"{SKILL}/SKILL.md")


# --- the record ---------------------------------------------------------------------------------------------

def test_the_subprocess_gets_a_minimal_environment(conn, folder, fake, monkeypatch):
    for name in ("OPENAI_API_KEY", "NVIDIA_INFERENCE_KEY", "LANGSMITH_API_KEY", "LANGSMITH_TRACING"):
        monkeypatch.setenv(name, "secret-value")
    monkeypatch.setenv(skillscan.PROXY_ENV, "http://127.0.0.1:9")
    publish(conn, folder())
    calls = fake.calls()
    assert [c["args"][0] for c in calls] == ["--version", "scan"]
    assert calls[1]["args"][2:] == ["--no-llm", "--format", "json"]
    for call in calls:
        env = {k: v for k, v in call["env"].items() if k not in ("PWD", "SHLVL", "_", "LC_CTYPE")}
        assert set(env) == {"PATH", "HOME", "LANG", "NO_COLOR", "SKILLSPECTOR_LOG_LEVEL", "HTTPS_PROXY", "HTTP_PROXY",
                            "ALL_PROXY"}
        assert env["HTTPS_PROXY"] == "http://127.0.0.1:9" and "secret-value" not in env.values()


def test_the_report_is_normalized_and_its_digest_is_stable(conn, folder, fake):
    publish(conn, folder("FAKE:DO_NOT_INSTALL\n"))
    tool = skillscan.probe()
    files = {"SKILL.md": b"FAKE:DO_NOT_INSTALL\n", "references/kaynak.md": "Kaynak listesi.\n".encode()}
    one, two = skillscan.run(tool, SKILL, files), skillscan.run(tool, SKILL, files)
    assert one.report_digest == two.report_digest  # a random finding_id, a clock and a new temporary folder
    assert "finding_id" not in one.findings[0]
    stored = conn.execute("SELECT report_digest, findings, input_digest, mode FROM skill_scan").fetchone()
    assert stored[:2] == (one.report_digest, one.findings) and stored[3] == "no-llm"
    assert stored[2] == skillscan.input_digest({p: hashlib.sha256(d).hexdigest() for p, d in files.items()})


def test_an_unknown_version_is_refused_unless_allowed(conn, folder, fake, monkeypatch):
    fake.version = "2.14.0"
    r = publish(conn, folder())
    assert r.skill_scans[0]["status"] == "not_scanned" and "2.14.0 is not the tested 2.13.1" in \
        r.skill_scans[0]["reason"] and fake.scans() == 0
    monkeypatch.setenv(skillscan.ALLOW_ENV, "2.14.0")
    assert skillscan.rescan(conn, BOOK)[0]["status"] == "scanned"
    assert records(conn)[-1][4] == "2.14.0"


def test_unchanged_skill_bytes_reuse_the_scan_and_keep_the_block(conn, folder, fake, okf_dir):
    first = publish(conn, folder("FAKE:DO_NOT_INSTALL\n"))
    (okf_dir / "yeni.md").write_text("Yeni bir belge.\n", encoding="utf-8")
    second = publish(conn, okf_dir)
    assert second.content_id != first.content_id and fake.scans() == 1  # same bytes, same version: no new run
    with pytest.raises(Denied, match="skill blocked"):
        gate.deliver_file(conn, agent_with(conn, "read", "activate"), BOOK, second.content_id, REF)
    publish(conn, okf_dir)
    assert fake.scans() == 1 and len(records(conn)) == 2  # the same version again: nothing new


# --- curator, staleness, rescan -----------------------------------------------------------------------------

def test_only_a_curator_clears_a_block_and_it_is_recorded(conn, folder, fake):
    r = publish(conn, folder("FAKE:DO_NOT_INSTALL\n"))
    with pytest.raises(PermissionError, match="curate"):
        skillscan.clear(conn, BOOK, SKILL, curator=CURATOR, reason="inceledim")
    with pytest.raises(ValueError, match="user:"):
        skillscan.clear(conn, BOOK, SKILL, curator=A, reason="inceledim")
    curate(conn)
    with pytest.raises(LookupError, match="no block"):
        skillscan.clear(conn, BOOK, "baska/beceri", curator=CURATOR, reason="inceledim")
    out = skillscan.clear(conn, BOOK, SKILL, curator=CURATOR, reason="Bulgu yanlış alarm; metni okudum.")
    assert [c["recommendation"] for c in out["cleared"]] == ["DO_NOT_INSTALL"]
    assert conn.execute("SELECT curator, reason FROM skill_clearance").fetchall() == [
        (CURATOR, "Bulgu yanlış alarm; metni okudum.")]
    agent = agent_with(conn, "read", "activate")
    assert gate.deliver_file(conn, agent, BOOK, r.content_id, REF)
    assert REF in {h.citation.path for h in search.search(conn, agent, "kaynak listesi", k=50)}
    [shown] = skillscan.show(conn, BOOK)
    assert shown["origin"] == "tool" and shown["software_agent"] == {"name": "skillspector", "version": "2.13.1"}
    assert not shown["blocking"] and shown["cleared"][0]["curator"] == CURATOR


def test_a_clearance_covers_only_those_bytes(conn, folder, fake):
    publish(conn, folder("FAKE:DO_NOT_INSTALL\n"))
    curate(conn)
    skillscan.clear(conn, BOOK, SKILL, curator=CURATOR, reason="inceledim")
    r = publish(conn, folder("FAKE:DO_NOT_INSTALL\nyeni satır\n"))  # other bytes: a new proposal, blocked again
    with pytest.raises(Denied, match="skill blocked"):
        gate.deliver_file(conn, agent_with(conn, "read", "activate"), BOOK, r.content_id, REF)


def test_a_new_tool_version_makes_old_records_stale_and_a_looser_scan_never_lifts_a_block(conn, folder, fake,
                                                                                          monkeypatch):
    r = publish(conn, folder("FAKE:DO_NOT_INSTALL\n"))
    fake.version = "2.14.0"
    monkeypatch.setenv(skillscan.ALLOW_ENV, "2.14.0")
    fake.verdict("SAFE")
    publish(conn, folder("FAKE:DO_NOT_INSTALL\n"))  # the same content again: its record of 2.13.1 is not fresh
    assert [(s, rec, v, stale) for s, _, rec, _, v, stale, _ in records(conn)] == [
        (SKILL, "DO_NOT_INSTALL", "2.13.1", True), (SKILL, "SAFE", "2.14.0", False)]
    with pytest.raises(Denied, match="skill blocked"):  # the stale DO_NOT_INSTALL still blocks (R1)
        gate.deliver_file(conn, agent_with(conn, "read", "activate"), BOOK, r.content_id, REF)
    assert skillscan.rescan(conn) == []  # fresh for 2.14.0: nothing to do
    curate(conn)
    skillscan.clear(conn, BOOK, SKILL, curator=CURATOR, reason="2.14.0 SAFE diyor; okudum.")
    assert gate.deliver_file(conn, agent_with(conn, "read", "activate"), BOOK, r.content_id, REF)


def test_cli_rescan_scans_stale_records_and_clear_needs_the_curator_credential(conn, folder, fake, monkeypatch,
                                                                              capsys):
    monkeypatch.setenv(db.DSN_ENV, os.environ["KUTUPHANE_TEST_DSN"])
    publish(conn, folder("FAKE:PARTIAL\n"))
    fake.version = "2.14.0"
    monkeypatch.setenv(skillscan.ALLOW_ENV, "2.14.0")
    assert cli.main(["skill", "rescan", "--book", BOOK]) == 0
    out = capsys.readouterr()
    assert [s["status"] for s in json.loads(out.out)] == ["scanned"] and "skill blocked for agents" in out.err
    assert [r[5] for r in records(conn)] == [True, False]
    assert cli.main(["skill", "show", BOOK]) == 0
    assert [s["blocking"] for s in json.loads(capsys.readouterr().out)] == [True, True]
    args = ["skill", "clear", BOOK, SKILL, "--curator", CURATOR, "--reason", "okudum"]
    monkeypatch.delenv(db.CURATOR_DSN_ENV, raising=False)
    assert cli.main(args) == 2  # never with the app credential
    monkeypatch.setenv(db.CURATOR_DSN_ENV, os.environ["KUTUPHANE_TEST_DSN"])
    assert cli.main(args) == 3 and "does not hold curate" in capsys.readouterr().err
    curate(conn)
    assert cli.main(args) == 0
    assert len(json.loads(capsys.readouterr().out)["cleared"]) == 2  # both versions' blocks, each on record
    assert conn.execute("SELECT count(*) FROM skill_block").fetchone()[0] == 0


def test_the_app_role_cannot_remove_a_scan_or_a_block(conn, folder, fake):
    publish(conn, folder("FAKE:DO_NOT_INSTALL\n"))
    role = "kutuphane_app_test"
    conn.execute(f"DO $$ BEGIN CREATE ROLE {role} NOLOGIN; EXCEPTION WHEN duplicate_object THEN NULL; END $$")
    script = (Path(__file__).parent.parent / "deploy" / "db-roles.sql").read_text(encoding="utf-8")
    conn.execute(script.replace("kutuphane_app", role))
    scan_id = conn.execute("SELECT id, input_digest FROM skill_scan").fetchone()
    try:
        conn.execute(f"SET ROLE {role}")
        for sql in ("DELETE FROM skill_scan", "UPDATE skill_scan SET recommendation = 'SAFE'",
                    "DELETE FROM skill_block", "UPDATE skill_block SET status = 'not_scanned'",
                    f"INSERT INTO skill_clearance (book, input_digest, tool_version, scan_id, curator, reason) "
                    f"VALUES ('{BOOK}', '{scan_id[1]}', '2.13.1', {scan_id[0]}, 'user:x', 'r')"):
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                conn.execute(sql)
        conn.execute("UPDATE skill_scan SET stale = true")  # the only column the app may change
        assert conn.execute("SELECT count(*) FROM skill_block").fetchone()[0] == 1
    finally:
        conn.execute("RESET ROLE")


# --- other paths --------------------------------------------------------------------------------------------

def test_package_receive_shows_the_scan_as_a_proposal(conn, conn_b, folder, fake, tmp_path):
    publish(conn, folder("FAKE:DO_NOT_INSTALL\n"))
    info = signing.generate(tmp_path / "a.key")
    packages.trust(conn_b, open(info["public_key"], "rb").read(), expected_fingerprint=info["fingerprint"],
                   name="A", by="user:admin")
    result = packages.receive(conn_b, packages.export(conn, BOOK, signing.load_private(tmp_path / "a.key")))
    [scan] = [f for f in result["findings"] if f["kind"] == "skill_scan"]
    assert scan == {"path": SKILL, "kind": "skill_scan", "status": "scanned", "blocking": True, "origin": "tool",
                    "software_agent": {"name": "skillspector", "version": "2.13.1"},
                    "recommendation": "DO_NOT_INSTALL", "score": 100, "completeness": "complete", "issues": 1}


def test_an_agent_cannot_reopen_an_answer_built_on_a_skill_blocked_later(conn, folder, fake, monkeypatch):
    bridge = FakeBridge()
    try:
        r = publish(conn, folder("Erişim kayıtlarını özetle.\n", "Erişim kayıtları kaynak listesi.\n"))
        agent = agent_with(conn, "read", "activate")
        bridge.reply = "x"
        probe = answers.ask(conn, bridge.bridge(), agent, "erişim kayıtları", model="qwen")
        sources = conn.execute("SELECT sources FROM answer WHERE id = %s", (probe["id"],)).fetchone()[0]
        n = next(s["n"] for s in sources if s["path"] == REF)
        bridge.reply = f"Kayıtlar listelenir [{n}]."
        result = answers.ask(conn, bridge.bridge(), Actor(A, on_behalf_of=U), "erişim kayıtları", model="qwen")
        assert result["status"] == "answered"
        fake.version = "2.14.0"
        monkeypatch.setenv(skillscan.ALLOW_ENV, "2.14.0")
        fake.verdict("DO_NOT_INSTALL")
        assert skillscan.rescan(conn, BOOK)[0]["blocking"] and r.content_id
        with pytest.raises(Denied, match="skill blocked"):
            answers.reopen(conn, Actor(A, on_behalf_of=U), result["id"])
        assert answers.reopen(conn, Actor(U), result["id"])["body"]  # the person who asked still sees it
    finally:
        bridge.server.shutdown()


def test_the_pin_names_the_tested_version():
    pin = dict(line.split("=", 1) for line in PIN.read_text().splitlines() if line and not line.startswith("#"))
    assert pin["SKILLSPECTOR_VERSION"] == skillscan.TESTED_VERSION
    assert len(pin["SKILLSPECTOR_SHA256"]) == 64 and int(pin["SKILLSPECTOR_SHA256"], 16) >= 0
    assert pin["SKILLSPECTOR_URL"].endswith(f"/v{skillscan.TESTED_VERSION}.tar.gz")
