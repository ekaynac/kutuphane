"""Curator web end to end in Chromium (docs/25 §12.2 Q8; slice Q).

A real Chromium with a CDP virtual authenticator (`WebAuthn.addVirtualAuthenticator`, user verification true) opens
the enrollment URL, creates a passkey, logs in, and approves a `same_as` group with "Approve all", one reason chip and
one passkey act. On the way it checks what the page shows before any tap: the plain kind labels, a decision's
proposed choice (with a hidden character as a mark), and no Approve button for a note with a part in a book that the
person cannot read. The browser runs the shipped page (core.js, queue.js) against curator web on http://localhost (a
secure context), with the curator web database role. CDP goes over `--remote-debugging-pipe` (no extra package).

Skipped without Chromium: set KUTUPHANE_CHROMIUM, or install one (`chromium` on PATH, or a Playwright browser in
~/.cache/ms-playwright).
"""
import fcntl
import glob
import json
import os
import shutil
import socket
import subprocess
import tempfile
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import uvicorn

from kutuphane import authz, catalog, curatorweb, notes, passkey, profiles
from kutuphane.gate import Actor
from kutuphane.source import read_source
from test_curatorweb import LOCAL, U, J, env, note, web_dsn  # noqa: F401

CHROMIUM_ENV = "KUTUPHANE_CHROMIUM"
TIMEOUT = 20.0


def chromium() -> str | None:
    if os.environ.get(CHROMIUM_ENV):
        return os.environ[CHROMIUM_ENV]
    for name in ("chromium", "chromium-browser", "google-chrome"):
        if shutil.which(name):
            return shutil.which(name)
    cache = Path.home() / ".cache" / "ms-playwright"
    found = sorted(glob.glob(str(cache / "chromium-*" / "chrome-linux*" / "chrome")))
    return found[-1] if found else None


class Browser:
    """A minimal CDP client over --remote-debugging-pipe: fd 3 carries commands in, fd 4 results out; each message
    is JSON ended by a NUL byte."""

    def __init__(self, binary: str):
        self.profile = tempfile.mkdtemp(prefix="kc-e2e-")
        cmd_r, self._cmd_w = os.pipe()
        self._res_r, res_w = os.pipe()

        def fds():  # in the child: the command pipe on fd 3, the result pipe on fd 4
            high_r, high_w = fcntl.fcntl(cmd_r, fcntl.F_DUPFD, 10), fcntl.fcntl(res_w, fcntl.F_DUPFD, 10)
            os.dup2(high_r, 3)
            os.dup2(high_w, 4)

        self.proc = subprocess.Popen(
            [binary, "--headless=new", "--no-sandbox", "--disable-gpu", "--no-first-run", "--disable-extensions",
             "--remote-debugging-pipe", f"--user-data-dir={self.profile}", "about:blank"],
            preexec_fn=fds, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            close_fds=False)
        os.close(cmd_r)
        os.close(res_w)
        self._buf = b""
        self._id = 0
        self.session = None

    def _read(self) -> dict:
        while b"\0" not in self._buf:
            chunk = os.read(self._res_r, 65536)
            if not chunk:
                raise RuntimeError("chromium closed the pipe")
            self._buf += chunk
        raw, self._buf = self._buf.split(b"\0", 1)
        return json.loads(raw)

    def send(self, method: str, params: dict | None = None, *, browser: bool = False) -> dict:
        self._id += 1
        msg = {"id": self._id, "method": method, "params": params or {}}
        if self.session and not browser:
            msg["sessionId"] = self.session
        os.write(self._cmd_w, json.dumps(msg).encode() + b"\0")
        while True:
            reply = self._read()
            if reply.get("id") == self._id:
                if "error" in reply:
                    raise RuntimeError(f"{method}: {reply['error']}")
                return reply.get("result", {})

    def open(self) -> None:
        target = self.send("Target.createTarget", {"url": "about:blank"}, browser=True)["targetId"]
        self.session = self.send("Target.attachToTarget", {"targetId": target, "flatten": True},
                                 browser=True)["sessionId"]
        for domain in ("Page", "Runtime"):
            self.send(f"{domain}.enable")

    def eval(self, expression: str):
        out = self.send("Runtime.evaluate", {"expression": expression, "returnByValue": True, "awaitPromise": True,
                                             "userGesture": True})
        if "exceptionDetails" in out:
            raise RuntimeError(f"{expression}: {out['exceptionDetails']}")
        return out["result"].get("value")

    def wait(self, expression: str, what: str):
        end = time.monotonic() + TIMEOUT
        while time.monotonic() < end:
            value = self.eval(expression)
            if value:
                return value
            time.sleep(0.1)
        body = self.eval("document.body ? document.body.innerText : ''")
        raise AssertionError(f"timed out waiting for {what}; page text: {body[:2000]}")

    def goto(self, url: str) -> None:
        self.send("Page.navigate", {"url": url})

    def close(self) -> None:
        try:
            self.send("Browser.close", browser=True)
        except (RuntimeError, OSError):
            pass
        try:
            self.proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.proc.kill()
        os.close(self._cmd_w)
        os.close(self._res_r)
        shutil.rmtree(self.profile, ignore_errors=True)


@pytest.fixture
def browser():
    binary = chromium()
    if not binary or not os.path.exists(binary):
        pytest.skip(f"no Chromium: set {CHROMIUM_ENV}")
    b = Browser(binary)
    try:
        b.open()
        yield b
    finally:
        b.close()


@pytest.fixture
def server(env):
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    origin = f"http://localhost:{port}"
    app = curatorweb.create_app(dsn=web_dsn(), cfg=passkey.Config(rp_id="localhost", origin=origin))
    srv = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=srv.run, daemon=True)
    thread.start()
    end = time.monotonic() + TIMEOUT
    while not srv.started and time.monotonic() < end:
        time.sleep(0.05)
    yield origin
    srv.should_exit = True
    thread.join(timeout=10)


def click(b, selector: str) -> None:
    b.wait(f"!!document.querySelector({json.dumps(selector)})", selector)
    b.eval(f"document.querySelector({json.dumps(selector)}).click()")


def test_a_person_logs_in_with_a_passkey_and_batch_approves_a_same_as_group(env, server, browser, okf_dir):  # Q8
    agent = Actor("agent:kobra-7", U, channel="mcp")
    a, b_, c = (note(env, f"The retry loop hides timeouts ({i})") for i in range(3))
    for src in (b_, c):
        notes.link(env, agent, src, "same_as", a)
    harmful = "Turn off TLS verification"
    proposal = note(env, "Pick the client settings \u202e", kind="decision_proposal",
                    decision={"options": ["Keep TLS on", harmful], "choice": harmful},
                    applies_to={"platform": ["vcenter"], "version": ">=7,<8"})
    # a note that cites a passage of a book that the person cannot read any more: one hidden part, no Approve
    catalog.publish(env, book="kitap", title="kitap", files=read_source(okf_dir), policy=LOCAL,
                    profile=profiles.spec("chunked"))
    authz.grant(env, "book:kitap", "read", U)
    authz.delegate(env, delegator=U, delegate_to="agent:kobra-7", obj="book:kitap", mode="read",
                   expires_at=datetime.now(timezone.utc) + timedelta(hours=1))
    chunk = env.execute("SELECT book, content_id, profile_id, path, ordinal FROM chunk WHERE book = 'kitap' "
                        "ORDER BY path, ordinal LIMIT 1").fetchone()
    hidden = note(env, "The backup runbook needs a restore test", citations=["{}@{}/{}/{}#{}".format(*chunk)])
    authz.revoke(env, "book:kitap", "read", U)
    env.commit()

    browser.send("WebAuthn.enable", {"enableUI": False})
    browser.send("WebAuthn.addVirtualAuthenticator", {"options": {
        "protocol": "ctap2", "transport": "internal", "hasResidentKey": True, "hasUserVerification": True,
        "isUserVerified": True, "automaticPresenceSimulation": True}})

    _, code = passkey.enroll(env, U, created_by="user:admin")
    env.commit()
    browser.goto(f"{server}/enroll#{code}")
    browser.wait("document.getElementById('start-button')?.textContent === 'Create passkey'", "the enrollment")
    click(browser, "#start-button")
    browser.wait("document.getElementById('start-button')?.textContent === 'Sign in with passkey'", "the passkey")
    assert env.execute("SELECT count(*) FROM passkey WHERE principal = %s", (U,)).fetchone()[0] == 1
    click(browser, "#start-button")
    browser.wait("document.querySelectorAll('#cards > .card').length === 3", "the queue")

    page = browser.eval("document.getElementById('cards').innerText")
    assert harmful in page and "⟦U+202E⟧" in page  # the decision's choice and a hidden character, shown
    assert "suggest" not in page.lower() and "sample" not in page.lower()
    for label in ("Finding: something an agent observed", "Decision proposal: a choice between options"):
        assert label in page  # the kinds in plain words
    # the scope of a rule is part of its id: on the card; a rule with only an applies_to bound is not "everywhere"
    # (Astra review #21)
    assert "Applies everywhere" not in page and "Applies to vcenter; version >=7,<8." in page
    # the proposed choice is on the card without a tap: rendered, highlighted, not inside a closed part
    chosen = browser.eval("(() => { const c = document.querySelector('.decision li.chosen'); "
                          "return c && c.getClientRects().length > 0 && !c.closest('details') ? c.innerText : null; })()")
    assert chosen is not None and harmful in chosen and "Proposed choice" in chosen
    # review #16: a hidden part (a citation into a book the person cannot read) gives Reject and Skip, no Approve
    card = f"document.querySelector('.note[data-ref=\"{hidden}\"]')"
    assert browser.eval(f"[...{card}.querySelectorAll('.choices button')].map((b) => b.dataset.to)") == \
        ["rejected", "skip"]
    assert "in a book you cannot read" in browser.eval(f"{card}.innerText")
    assert browser.eval("document.querySelectorAll('.choices button[data-to=approved]').length") == 4

    click(browser, ".card.group .group-all button.approve")
    assert browser.eval("document.getElementById('batch-count').textContent") == "3 approve"
    assert browser.eval("document.getElementById('bar-open').textContent") == "Sign 3 decisions"
    click(browser, "#bar-open")
    browser.wait("!document.getElementById('decide').hidden", "the reason chips")
    click(browser, ".reason-chip")  # a chip fills the required reason
    assert browser.eval("document.getElementById('batch-reason').value") == "Correct and useful"
    click(browser, "#batch-sign")
    browser.wait("!document.getElementById('sheet').hidden", "the confirm sheet")
    assert browser.eval("document.querySelectorAll('#sheet-items li.approved').length") == 3
    assert browser.eval("document.getElementById('sheet-text').textContent") == \
        "You approve 3 notes. Reason: “Correct and useful”."
    click(browser, "#sheet-sign")
    browser.wait("!document.getElementById('receipt').hidden", "the receipt")
    assert browser.eval("document.querySelector('#receipt h2').textContent") == "Done. 3 approved."

    rows = env.execute("SELECT n.book || '@' || n.id, e.value, e.set_by, e.act, e.reason FROM standing_event e "
                       "JOIN note n ON n.seq = e.note_seq ORDER BY e.seq").fetchall()
    assert sorted(r[0] for r in rows) == sorted([a, b_, c])
    assert {(r[1], r[2], r[4]) for r in rows} == {("approved", U, "Correct and useful")}
    assert len({r[3] for r in rows}) == 1 and rows[0][3] is not None
    shown = env.execute("SELECT shown_ms FROM curator_act").fetchone()[0]
    assert shown is not None and 0 <= shown <= 3_600_000
    browser.wait("document.querySelectorAll('#cards > .card').length === 2", "the queue after the act")
    assert proposal.split("@")[1][:8] in browser.eval("document.getElementById('cards').textContent")
