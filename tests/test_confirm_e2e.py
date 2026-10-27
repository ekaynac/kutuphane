"""Smoke test of D70 R3 end to end (docs/25 §7, slice R): a headless Chromium with a CDP virtual authenticator.

An agent proposes for Ayşe with `origin: human`; `confirm_origin` (MCP, 2026-07-28, URL elicitation) gives the
curator web URL; Ayşe enrolls a passkey, signs in and confirms "verbatim" on the real page; the note then shows
`human` with `entered_by`; one changed byte is a new note that shows `model`.

Chromium talks CDP over `--remote-debugging-pipe` (no extra Python package). The test is skipped without a
Chromium: set KUTUPHANE_CHROMIUM, or install one with Playwright (`~/.cache/ms-playwright`).
"""
import fcntl
import glob
import json
import os
import select
import socket
import subprocess
import tempfile
import threading
import time
from pathlib import Path

import pytest
import uvicorn
from starlette.testclient import TestClient

from kutuphane import confirm, curatorweb, notesquery, passkey, server
from kutuphane.gate import Actor
from test_curatorweb import A, J, U, env, web_dsn  # noqa: F401
from test_server import MODERN, PUBLIC, bearer, keys, mcp_rpc, verifier  # noqa: F401

PATTERNS = ("~/.cache/ms-playwright/chromium_headless_shell-*/chrome-headless-shell-*/chrome-headless-shell",
            "~/.cache/ms-playwright/chromium-*/chrome-linux*/chrome")


def _chromium() -> str | None:
    if os.environ.get("KUTUPHANE_CHROMIUM"):
        return os.environ["KUTUPHANE_CHROMIUM"]
    found = sorted(p for pattern in PATTERNS for p in glob.glob(os.path.expanduser(pattern)))
    return found[-1] if found else None


class Browser:
    """A minimal CDP client over the debugging pipe: fd 3 (commands to Chromium), fd 4 (replies), NUL-framed."""

    def __init__(self, binary: str):
        to_chrome, self._send = os.pipe()
        self._recv, from_chrome = os.pipe()

        def fds():  # in the child: fd 3 and fd 4, inheritable (the pipe ends are close-on-exec)
            high = [fcntl.fcntl(fd, fcntl.F_DUPFD, 10) for fd in (to_chrome, from_chrome)]
            os.dup2(high[0], 3)
            os.dup2(high[1], 4)

        self.profile = tempfile.TemporaryDirectory()
        self.proc = subprocess.Popen(
            [binary, "--headless", "--remote-debugging-pipe", "--no-sandbox", "--disable-gpu", "--no-first-run",
             f"--user-data-dir={self.profile.name}", "about:blank"],
            close_fds=False, preexec_fn=fds, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        os.close(to_chrome)
        os.close(from_chrome)
        self._id, self._buf, self.session = 0, b"", None

    def call(self, method: str, params: dict | None = None, *, session: bool = True, timeout: float = 20) -> dict:
        self._id += 1
        msg = {"id": self._id, "method": method, "params": params or {}}
        if session and self.session:
            msg["sessionId"] = self.session
        os.write(self._send, json.dumps(msg).encode() + b"\0")
        deadline = time.monotonic() + timeout
        while True:
            while b"\0" in self._buf:
                raw, self._buf = self._buf.split(b"\0", 1)
                reply = json.loads(raw)
                if reply.get("id") == self._id:
                    if "error" in reply:
                        raise RuntimeError(f"{method}: {reply['error']}")
                    return reply.get("result", {})
            left = deadline - time.monotonic()
            if left <= 0 or not select.select([self._recv], [], [], left)[0]:
                raise TimeoutError(method)
            chunk = os.read(self._recv, 1 << 16)
            if not chunk:
                raise RuntimeError("Chromium closed the pipe")
            self._buf += chunk

    def open(self) -> None:
        target = self.call("Target.createTarget", {"url": "about:blank"}, session=False)["targetId"]
        self.session = self.call("Target.attachToTarget", {"targetId": target, "flatten": True},
                                 session=False)["sessionId"]
        self.call("Runtime.enable")
        self.call("Page.enable")

    def go(self, url: str) -> None:
        self.call("Page.navigate", {"url": url})

    def js(self, expression: str):
        out = self.call("Runtime.evaluate", {"expression": expression, "awaitPromise": True, "returnByValue": True,
                                             "userGesture": True})
        if "exceptionDetails" in out:
            raise RuntimeError(out["exceptionDetails"])
        return out["result"].get("value")

    def wait(self, expression: str, timeout: float = 20):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                value = self.js(expression)
            except RuntimeError:
                value = None
            if value:
                return value
            time.sleep(0.1)
        raise TimeoutError(f"{expression} -> {self.js('document.body && document.body.innerText')!r}")

    def close(self) -> None:
        try:
            self.call("Browser.close", session=False, timeout=5)
        except Exception:  # noqa: BLE001 — it may already be gone
            pass
        self.proc.wait(timeout=10)
        os.close(self._send)
        os.close(self._recv)
        self.profile.cleanup()


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def chromium():
    binary = _chromium()
    if not binary or not Path(binary).exists():
        pytest.skip("no Chromium (set KUTUPHANE_CHROMIUM or install one with Playwright)")
    b = Browser(binary)
    try:
        b.open()
        yield b
    finally:
        b.close()


@pytest.fixture
def web(env, monkeypatch):
    """Curator web on localhost (a secure context for WebAuthn and `__Host-` cookies), as the curator web role."""
    port = _free_port()
    origin = f"http://localhost:{port}"
    monkeypatch.setenv(confirm.URL_ENV, origin)
    cfg = passkey.Config(rp_id="localhost", origin=origin)
    srv = uvicorn.Server(uvicorn.Config(curatorweb.create_app(dsn=web_dsn(), cfg=cfg), host="127.0.0.1", port=port,
                                        log_level="warning"))
    thread = threading.Thread(target=srv.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not srv.started and time.monotonic() < deadline:
        time.sleep(0.05)
    yield origin
    srv.should_exit = True
    thread.join(timeout=10)


MSG = "document.getElementById('msg').textContent"


@pytest.fixture
def core(env, verifier):
    env.commit()  # the journal and the rights, for Core and curator web (their own connections)
    app = server.create_app(dsn=os.environ["KUTUPHANE_TEST_DSN"], verifier=verifier, bridge=None, model=None,
                            public_url=PUBLIC)
    with TestClient(app, base_url=PUBLIC) as c:
        yield c


def test_an_agent_proposes_and_the_person_confirms_on_the_page(env, web, chromium, core, keys):  # smoke
    agent = bearer(keys, act={"sub": "kobra-7"})
    caps = {"io.modelcontextprotocol/clientCapabilities": {"elicitation": {"url": {}}}}
    text = "Kayıtlar iki yıl saklanır."
    _, sent = mcp_rpc(core, agent, "tools/call", {"name": "propose_note", "arguments": {
        "book": J, "kind": "finding", "text": text, "origin": "human"}}, version=MODERN)
    receipt = json.loads(sent["result"]["content"][0]["text"])
    assert receipt["origin"] == "model" and receipt["origin_notice"] == "origin-claim-refused"
    _, asked = mcp_rpc(core, agent, "tools/call", {"name": "confirm_origin", "arguments": {"ref": receipt["ref"]}},
                       version=MODERN, meta=caps)
    (request,) = asked["result"]["inputRequests"].values()
    url = request["params"]["url"]
    assert request["params"]["mode"] == "url" and url.startswith(web + "/c/")

    chromium.call("WebAuthn.enable")
    chromium.call("WebAuthn.addVirtualAuthenticator", {"options": {
        "protocol": "ctap2", "transport": "internal", "hasResidentKey": True, "hasUserVerification": True,
        "isUserVerified": True, "automaticPresenceSimulation": True}})
    _, code = passkey.enroll(env, U, created_by="user:admin")
    env.commit()
    chromium.go(f"{web}/enroll#{code}")
    chromium.wait("document.getElementById('start-button').textContent === 'Create passkey'")
    chromium.js("document.getElementById('start-button').click()")
    chromium.wait(f"{MSG}.startsWith('Passkey saved')")
    chromium.js("document.getElementById('start-button').click()")   # sign in with the new passkey
    chromium.wait("location.pathname === '/' && document.getElementById('who').textContent.includes('user:ayse')")

    chromium.go(url)  # the URL that confirm_origin gave the agent
    chromium.wait("document.getElementById('claim-human') !== null")
    assert chromium.js("document.querySelector('pre').textContent") == text
    chromium.js("document.getElementById('claim-human').click()")
    chromium.js("document.getElementById('confirm-sign').click()")
    chromium.wait("!document.getElementById('sheet').hidden")
    chromium.js("document.getElementById('sheet-sign').click()")
    assert chromium.wait(f"{MSG}.startsWith('Confirmed') && {MSG}") == "Confirmed: origin human (entered by " \
                                                                       "agent:kobra-7)"

    items = {i["ref"]: i for i in notesquery.query_notes(env, Actor(U), for_model=False, book=[J],
                                                         sets=["open"])["items"]}
    assert (items[receipt["ref"]]["origin"], items[receipt["ref"]]["entered_by"],
            items[receipt["ref"]]["confirmed_by"]) == ("human", A, U)
    assert passkey.verify_acts(env, passkey.Config(rp_id="localhost", origin=web))["problems"] == []

    # one changed byte: a new note, with the write-path origin
    _, sent = mcp_rpc(core, agent, "tools/call", {"name": "propose_note", "arguments": {
        "book": J, "kind": "finding", "text": text[:-1] + "!", "origin": "human"}}, version=MODERN)
    changed = json.loads(sent["result"]["content"][0]["text"])["ref"]
    items = {i["ref"]: i for i in notesquery.query_notes(env, Actor(U), for_model=False, book=[J],
                                                         sets=["open"])["items"]}
    assert changed != receipt["ref"] and items[changed]["origin"] == "model" and "entered_by" not in items[changed]
    assert items[receipt["ref"]]["origin"] == "human"
