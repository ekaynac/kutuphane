"""M1c with a fake LLMDAP bridge that mimics the real contract (subject-keys mode, LLMDAP #226/#228): egress records,
embeddings and the unified audit (AT-09)."""
import hashlib
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from kutuphane import audit, authz, catalog, gate, llmdap
from kutuphane.gate import Actor
from kutuphane.policy import make_policy
from kutuphane.source import read_source

KEY = "llmdap_sk_" + "k" * 43
SUBJECT = "svc-kutuphane"
ROUTE = "local"


def fake_vector(text: str, dims: int = 16) -> list[float]:
    """Deterministic stand-in embedding: hashed word counts, so texts sharing words are close."""
    v = [0.0] * dims
    for word in text.casefold().split():
        v[int(hashlib.sha256(word.strip(".,:;?!").encode()).hexdigest(), 16) % dims] += 1.0
    return v


class FakeBridge:
    """Mimics the LLMDAP bridge contract we rely on (paths, headers, derived correlation id, audit records)."""

    def __init__(self):
        self.audit, self.hits, self.reply, self.on_request, self.embed_reply = [], [], "tamam", None, None
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
                if fake.on_request:
                    fake.on_request()  # e.g. a revocation landing while the model "thinks"
                if self.path.startswith("/drop"):
                    self.close_connection = True
                    self.connection.close()  # received and (maybe) acted on, but no answer comes back
                    return
                claimed = self.headers.get("x-llmdap-user")  # bound mode: the credential names the subject
                if self.headers.get("authorization") != f"Bearer {KEY}" or (claimed and claimed.lower() != SUBJECT):
                    self.send_response(401)
                    self.end_headers()
                    return
                cid = self.headers["x-llmdap-correlation-id"]
                derived = hashlib.sha256(f"{SUBJECT}\0{cid}".encode()).hexdigest()[:16] + ":" + cid
                for seq, kind in enumerate(("llm.authz", "llm.result"), start=len(fake.audit)):
                    fake.audit.append({"seq": seq, "type": kind, "actor": SUBJECT, "resource": f"llm/{ROUTE}",
                                       "correlationId": derived, "model": body["model"], "outcome": "allow",
                                       "forSubject": self.headers.get("x-llmdap-for-subject")})
                fake.last_body = body
                if self.path.endswith("/v1/embeddings"):
                    data = fake.embed_reply(body["input"]) if fake.embed_reply else \
                        [{"index": i, "embedding": fake_vector(t)} for i, t in enumerate(body["input"])]
                    answer = json.dumps({"data": data}).encode()
                else:
                    answer = json.dumps({"choices": [{"message": {"role": "assistant",
                                                                  "content": fake.reply}}]}).encode()
                if self.path.startswith("/badjson"):
                    answer = b"{not json"
                self.send_response(200)
                self.send_header("content-type", "application/json")
                self.send_header("x-llmdap-correlation-id-derived", derived)
                self.send_header("content-length", str(len(answer)))
                self.end_headers()
                self.wfile.write(answer)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def bridge(self, key=KEY, prefix="", route_class="local"):
        return llmdap.Bridge(f"http://127.0.0.1:{self.port}{prefix}", ROUTE, key, route_class)

    def embedder(self, route_class="local"):
        return llmdap.Embedder(self.bridge(route_class=route_class), "bge-m3")


@pytest.fixture
def fake():
    f = FakeBridge()
    yield f
    f.server.shutdown()


def ask(conn, bridge, actor, books=()):
    return llmdap.chat(conn, bridge, actor, model="qwen", messages=[{"role": "user", "content": "özetle"}],
                       source_books=list(books), purpose="test")


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
    assert headers["x-llmdap-correlation-id"].startswith(actor.correlation_id + ".")
    assert headers["x-llmdap-purpose"] == "test"

    report = audit.explain(conn, actor.correlation_id, fake.audit)
    assert report["complete"]
    assert [a["action"] for a in report["access"]] == ["read"] and report["access"][0]["path"] == "index.md"
    assert report["access"][0]["policy_id"] == r.policy_id
    (call,) = report["model_calls"]
    assert [e["type"] for e in call["llmdap"]] == ["llm.authz", "llm.result"]
    assert call["llmdap_status"] == "complete"


def test_missing_llmdap_record_is_flagged(conn, fake):  # AT-09: never silently complete
    actor = Actor("user:ayse")
    ask(conn, fake.bridge(), actor)
    report = audit.explain(conn, actor.correlation_id, [])
    assert not report["complete"] and report["model_calls"][0]["llmdap_status"] == "missing"


def test_one_llmdap_record_cannot_cover_two_calls(conn, fake):  # Astra review #2
    actor = Actor("user:ayse")
    ask(conn, fake.bridge(), actor)
    ask(conn, fake.bridge(), actor)
    first_authz_only = [fake.audit[0]]
    report = audit.explain(conn, actor.correlation_id, first_authz_only)
    assert [c["llmdap_status"] for c in report["model_calls"]] == ["missing", "missing"]
    assert not report["complete"]


def test_local_only_book_never_reaches_a_cloud_route(conn, fake, okf_dir):  # E5 egress
    for book, egress in (("yerel", "local_only"), ("acik", "cloud_ok")):
        catalog.publish(conn, book=book, title=book, files=read_source(okf_dir),
                        policy=make_policy(sensitivity="normal", egress=egress, protection="standard"),
                        profile=catalog.whole_profile())
    actor = Actor("user:ayse")
    before = len(fake.hits)
    with pytest.raises(llmdap.EgressError, match="yerel"):
        ask(conn, fake.bridge(route_class="cloud"), actor, books=["acik", "yerel"])
    with pytest.raises(llmdap.EgressError, match="bilinmeyen"):
        ask(conn, fake.bridge(route_class="cloud"), actor, books=["bilinmeyen"])
    assert len(fake.hits) == before                      # nothing left the building
    ask(conn, fake.bridge(route_class="cloud"), actor, books=["acik"])
    ask(conn, fake.bridge(route_class="local"), actor, books=["yerel"])
    report = audit.explain(conn, actor.correlation_id, fake.audit)
    assert [c["llmdap_status"] for c in report["model_calls"]] == ["not_sent", "not_sent", "complete", "complete"]


def test_core_authenticates_as_itself_and_names_the_person_served(conn, fake):  # AT-11 (LLMDAP side, contract)
    actor = Actor("agent:kobra-7", on_behalf_of="user:ayse")
    ask(conn, fake.bridge(), actor)
    headers = fake.hits[-1][1]
    assert headers["authorization"] == f"Bearer {KEY}" and "x-llmdap-user" not in headers
    assert "x-llmdap-auth" not in headers and headers["x-llmdap-for-subject"] == "user:ayse"
    assert fake.audit[-1]["actor"] == SUBJECT and fake.audit[-1]["forSubject"] == "user:ayse"
    row = conn.execute("SELECT principal, on_behalf_of FROM model_call WHERE correlation_id = %s",
                       (actor.correlation_id,)).fetchone()
    assert row == ("agent:kobra-7", "user:ayse")       # the agent itself is in our record, joined by call id


def test_refused_and_unreachable_calls_are_recorded(conn, fake):
    actor = Actor("user:ayse")
    with pytest.raises(llmdap.EgressError, match="401"):
        ask(conn, fake.bridge(key="llmdap_sk_" + "x" * 43), actor)
    with pytest.raises(llmdap.EgressError, match="unreachable"):
        ask(conn, llmdap.Bridge("http://127.0.0.1:9", ROUTE, KEY, "local"), actor)
    rows = conn.execute("SELECT http_status, error FROM model_call WHERE correlation_id = %s ORDER BY id",
                        (actor.correlation_id,)).fetchall()
    assert rows[0] == (401, "http 401") and rows[1][0] is None and rows[1][1]


def test_redirects_are_not_followed(conn, fake):  # the credential must not travel to another URL
    with pytest.raises(llmdap.EgressError, match="302"):
        ask(conn, fake.bridge(prefix="/redirect"), Actor("user:ayse"))
    assert all(not path.startswith("/stolen") for path, _ in fake.hits)


@pytest.mark.parametrize("url,route,cls", [("file:///etc/passwd", ROUTE, "local"), ("http://x", "../admin", "local"),
                                           ("http://x", ROUTE, "hybrid")])
def test_bridge_config_is_validated(url, route, cls):
    with pytest.raises(RuntimeError):
        llmdap.Bridge(url, route, KEY, cls)


def test_invalid_answer_keeps_status_and_correlation(conn, fake):  # Astra review #2
    actor = Actor("user:ayse")
    with pytest.raises(llmdap.EgressError, match="JSONDecodeError"):
        ask(conn, fake.bridge(prefix="/badjson"), actor)
    status, derived, error = conn.execute("SELECT http_status, derived_correlation_id, error FROM model_call "
                                          "WHERE correlation_id = %s", (actor.correlation_id,)).fetchone()
    assert status == 200 and derived and error == "uncertain:JSONDecodeError"


def test_connection_lost_after_sending_is_not_proof_of_not_sending(conn, fake):  # Astra #3
    actor = Actor("user:ayse")
    with pytest.raises(llmdap.EgressError):
        ask(conn, fake.bridge(prefix="/drop"), actor)
    (error,) = conn.execute("SELECT error FROM model_call WHERE correlation_id = %s", (actor.correlation_id,)).fetchone()
    assert error.startswith("uncertain:")
    report = audit.explain(conn, actor.correlation_id, fake.audit)
    assert report["model_calls"][0]["llmdap_status"] == "missing" and not report["complete"]


def test_refused_connection_is_not_sent(conn):
    actor = Actor("user:ayse")
    with pytest.raises(llmdap.EgressError):
        ask(conn, llmdap.Bridge("http://127.0.0.1:9", ROUTE, KEY, "local"), actor)
    report = audit.explain(conn, actor.correlation_id, [])
    assert report["model_calls"][0]["llmdap_status"] == "not_sent" and report["complete"]
