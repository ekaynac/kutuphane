"""M1c with a fake LLMDAP bridge (real one waits for #222/#223, D49): egress records and the unified audit (AT-09)."""
import hashlib
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from kutuphane import audit, authz, catalog, gate, llmdap
from kutuphane.gate import Actor
from kutuphane.policy import make_policy
from kutuphane.source import read_source

SECRET = "s" * 40
ROUTE = "local"


class FakeBridge:
    """Mimics the LLMDAP bridge contract we rely on (paths, headers, derived correlation id, audit records)."""

    def __init__(self):
        self.audit, self.hits = [], []
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                fake.hits.append((self.path, {k.lower(): v for k, v in self.headers.items()}))
                if self.path.startswith("/redirect"):
                    self.send_response(302)
                    self.send_header("Location", f"http://127.0.0.1:{fake.port}/stolen")
                    self.end_headers()
                    return
                body = json.loads(self.rfile.read(int(self.headers["content-length"])))
                if self.headers.get("x-llmdap-auth") != SECRET:
                    self.send_response(401)
                    self.end_headers()
                    return
                subject, cid = self.headers["x-llmdap-user"].lower(), self.headers["x-llmdap-correlation-id"]
                derived = hashlib.sha256(f"{subject}\0{cid}".encode()).hexdigest()[:16] + ":" + cid
                for seq, kind in enumerate(("llm.authz", "llm.result"), start=len(fake.audit)):
                    fake.audit.append({"seq": seq, "type": kind, "actor": subject, "resource": f"llm/{ROUTE}",
                                       "correlationId": derived, "model": body["model"], "outcome": "allow"})
                answer = json.dumps({"choices": [{"message": {"role": "assistant", "content": "tamam"}}]}).encode()
                self.send_response(200)
                self.send_header("content-type", "application/json")
                self.send_header("x-llmdap-correlation-id-derived", derived)
                self.send_header("content-length", str(len(answer)))
                self.end_headers()
                self.wfile.write(answer)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def bridge(self, secret=SECRET, prefix=""):
        return llmdap.Bridge(f"http://127.0.0.1:{self.port}{prefix}", ROUTE, secret)


@pytest.fixture
def fake():
    f = FakeBridge()
    yield f
    f.server.shutdown()


def ask(conn, bridge, actor):
    return llmdap.chat(conn, bridge, actor, model="qwen", messages=[{"role": "user", "content": "özetle"}],
                       purpose="test")


def test_call_is_recorded_and_joined_with_llmdap_audit(conn, fake, okf_dir):  # AT-09 (Core side)
    r = catalog.publish(conn, book="kitap", title="kitap", files=read_source(okf_dir),
                        policy=make_policy(sensitivity="normal", egress="local_only", protection="standard"),
                        profile=catalog.whole_profile())
    authz.grant(conn, "book:kitap", "read", "user:ayse")
    actor = Actor("user:ayse")
    gate.deliver_file(conn, actor, "kitap", r.content_id, "index.md")
    assert ask(conn, fake.bridge(), actor)["choices"][0]["message"]["content"] == "tamam"

    path, headers = fake.hits[-1]
    assert path == f"/bridge/{ROUTE}/v1/chat/completions"
    assert headers["x-llmdap-correlation-id"] == actor.correlation_id and headers["x-llmdap-purpose"] == "test"

    report = audit.explain(conn, actor.correlation_id, fake.audit)
    assert report["complete"]
    assert [a["action"] for a in report["access"]] == ["read"]
    assert report["access"][0]["policy_id"] == r.policy_id
    (call,) = report["model_calls"]
    assert [e["type"] for e in call["llmdap"]] == ["llm.authz", "llm.result"]


def test_missing_llmdap_record_is_flagged(conn, fake):  # AT-09: never silently complete
    actor = Actor("user:ayse")
    ask(conn, fake.bridge(), actor)
    report = audit.explain(conn, actor.correlation_id, [])
    assert not report["complete"] and report["model_calls"][0]["llmdap_missing"]


def test_delegated_call_names_both_parties(conn, fake):
    actor = Actor("agent:kobra-7", on_behalf_of="user:ayse")
    ask(conn, fake.bridge(), actor)
    headers = fake.hits[-1][1]
    assert (headers["x-llmdap-user"], headers["x-llmdap-for-subject"]) == ("agent:kobra-7", "user:ayse")


def test_refused_and_unreachable_calls_are_recorded(conn, fake):
    actor = Actor("user:ayse")
    with pytest.raises(llmdap.EgressError, match="401"):
        ask(conn, fake.bridge(secret="wrong" * 8), actor)
    with pytest.raises(llmdap.EgressError, match="unreachable"):
        ask(conn, llmdap.Bridge("http://127.0.0.1:9", ROUTE, SECRET), actor)
    rows = conn.execute("SELECT http_status, error FROM model_call WHERE correlation_id = %s ORDER BY id",
                        (actor.correlation_id,)).fetchall()
    assert rows[0] == (401, "http 401") and rows[1][0] is None and rows[1][1]


def test_redirects_are_not_followed(conn, fake):  # the trust secret must not travel to another URL
    with pytest.raises(llmdap.EgressError, match="302"):
        ask(conn, fake.bridge(prefix="/redirect"), Actor("user:ayse"))
    assert all(not path.startswith("/stolen") for path, _ in fake.hits)


@pytest.mark.parametrize("url,route", [("file:///etc/passwd", ROUTE), ("http://x", "../admin")])
def test_bridge_config_is_validated(url, route):
    with pytest.raises(RuntimeError):
        llmdap.Bridge(url, route, SECRET)
