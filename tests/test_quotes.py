"""G23 (docs/18 §7): a passage that repeats a whole field value of a JSONL record points to that record; `ask` puts
the record into the evidence before its copy. Synthetic fixtures only."""
import hashlib
import json
from importlib.resources import files

import pytest

from kutuphane import answers, authz, catalog, profiles, quotes, search
from kutuphane.gate import Actor
from kutuphane.policy import make_policy
from kutuphane.source import read_source
from test_egress_audit import FakeBridge

U = "user:ayse"
POLICY = make_policy(sensitivity="normal", egress="local_only", protection="standard")
ADVISORY = "Engine Kestrel fixed a remote code execution flaw in its model loader; patch every node now."
FORMAT = "Engine Plover ships a new   quantization format\tfor older accelerators and small edge devices."
RECORDS = [{"id": "n-1", "summary": ADVISORY, "model": "m-1", "tags": ["security"]},
           {"id": "n-2", "summary": "Too short to count.", "model": "m-1"},
           {"id": "n-3", "summary": FORMAT, "model": "m-1",
            "nested": {"note": "x", "links": ["https://example.org/synthetic/a-long-link-that-counts-as-a-value"]}}]
BRIEF = {"week": "2030-W01", "rings": "Move falcon-runtime to pilot after the latency check passed twice.",
         "items": [{"news": "n-1", "text": ADVISORY}]}
DIGEST = ("# Digest 2030-W01\n\nRing moves and counts only.\n\n"
          "- Engine Plover ships a new quantization format for older accelerators and small edge devices.\n")


@pytest.fixture
def fake():
    f = FakeBridge()
    yield f
    f.server.shutdown()


def _publish(conn, root, book, profile="chunked"):
    return catalog.publish(conn, book=book, title=book, files=read_source(root), policy=POLICY,
                           profile=profiles.spec(profile))


def _kstd(root, ai_input: str) -> None:
    digest = hashlib.sha256((root / "news.jsonl").read_bytes()).hexdigest()
    (root / "kstd.yaml").write_text(
        "standard: kstd/0.3\nissuer: \"Test <t@example.org>\"\n"
        f"rights: {{license: MIT, ai_use: {{search: y, ai_input: {ai_input}}}, personal_data: synthetic}}\n"
        f"items:\n  - path: news.jsonl\n    digest: sha256:{digest}\n    origin: model\n", encoding="utf-8")


@pytest.fixture
def books(conn, tmp_path):
    """`news`: one JSONL file of records; `briefs`: a JSON brief and a markdown digest that repeat two summaries."""
    news, briefs = tmp_path / "news", tmp_path / "briefs"
    news.mkdir()
    briefs.mkdir()
    (news / "news.jsonl").write_text("".join(json.dumps(r) + "\n" for r in RECORDS), encoding="utf-8")
    (briefs / "brief.json").write_text(json.dumps(BRIEF, indent=1), encoding="utf-8")
    (briefs / "digest.md").write_text(DIGEST, encoding="utf-8")
    _publish(conn, news, "news")
    _publish(conn, briefs, "briefs")
    return news, briefs


def _hit(conn, path, query):
    (hit,) = [h for h in search.search(conn, Actor(U), query, k=20) if h.citation.path == path]
    return hit


def _record(conn, ordinal):
    return conn.execute("SELECT book, content_id, profile_id, path, ordinal FROM chunk WHERE book = 'news' AND "
                        "ordinal = %s", (ordinal,)).fetchone()


def test_record_values_and_passage_units_match_after_white_space_folding():
    record = json.dumps(RECORDS[2])
    assert quotes.digest(" ".join(FORMAT.split())) in quotes.record_values(record)
    assert len(quotes.record_values(record)) == 2                          # values at any depth, also in lists
    assert quotes.record_values(json.dumps(RECORDS[1])) == set()          # under MIN_CHARS: a label, not a quote
    assert quotes.record_values("[1, 2]") == set() and quotes.record_values("{broken") == set()
    assert quotes.digest(" ".join(FORMAT.split())) in quotes.units(DIGEST)  # a whole line of the digest, less "- "
    assert quotes.record_values(json.dumps(RECORDS[0])) <= quotes.units(json.dumps(BRIEF, indent=1))  # a JSON string


def test_a_search_hit_points_to_the_record_it_repeats(conn, books):
    authz.grant(conn, "book:news", "read", U)
    authz.grant(conn, "book:briefs", "read", U)
    brief, digest = _hit(conn, "brief.json", "falcon latency pilot"), _hit(conn, "digest.md", "ring moves counts")
    record = _hit(conn, "news.jsonl", "remote code execution")
    found = quotes.quoted(conn, Actor(U), [brief, digest, record])
    assert [tuple(vars(h.citation).values()) for h in found[brief.citation]] == [_record(conn, 0)]
    assert [h.citation.ordinal for h in found[digest.citation]] == [2]
    assert record.citation not in found                                   # a record is never a copy


def test_no_pointer_into_an_unreadable_or_filtered_book(conn, books):
    authz.grant(conn, "book:briefs", "read", U)
    brief = _hit(conn, "brief.json", "falcon latency pilot")
    assert quotes.quoted(conn, Actor(U), [brief]) == {}                   # news is not readable
    authz.grant(conn, "book:news", "read", U)
    assert quotes.quoted(conn, Actor(U), [brief])
    for scope in (search.Scope.of(books=["briefs"]), search.Scope.of(path="brief"),
                  search.Scope.of(origins=["human"])):
        assert quotes.quoted(conn, Actor(U), [brief], scope) == {}, scope


def test_cli_search_shows_quoted_records(conn, books, monkeypatch, capsys):
    import os

    from kutuphane import cli, db, llmdap
    monkeypatch.setenv(db.DSN_ENV, os.environ["KUTUPHANE_TEST_DSN"])
    for env in (llmdap.EMBED_ENV, llmdap.RERANK_ENV):
        monkeypatch.delenv(env["route"], raising=False)
    authz.grant(conn, "book:news", "read", U)
    authz.grant(conn, "book:briefs", "read", U)
    assert cli.main(["search", U, "falcon latency pilot", "--book", "briefs"]) == 0
    (hit,) = json.loads(capsys.readouterr().out)
    assert hit["citation"].startswith("briefs@") and hit["quoted_records"] == []   # the book filter holds
    assert cli.main(["search", U, "falcon latency pilot"]) == 0
    (hit,) = json.loads(capsys.readouterr().out)
    assert hit["quoted_records"] == [search.Citation(*_record(conn, 0)).handle]


def test_http_and_mcp_search_show_quoted_records(conn, books):
    import os

    from kutuphane import retrieval, server
    authz.grant(conn, "book:news", "read", U)
    authz.grant(conn, "book:briefs", "read", U)
    out = server.op_search(os.environ["KUTUPHANE_TEST_DSN"], retrieval.Stages(), Actor(U), "ring moves counts", 5,
                           model_reader=True, max_chars=80)
    (digest,) = [h for h in out if "/digest.md#" in h["citation"]]
    assert digest["quoted_records"] == [search.Citation(*_record(conn, 2)).handle]


def test_ask_puts_the_record_before_its_copy(conn, books, fake):
    authz.grant(conn, "book:news", "read", U)
    authz.grant(conn, "book:briefs", "read", U)
    fake.reply = "Kestrel fixed a code execution flaw [1]; the brief repeats it [2]."
    result = answers.ask(conn, fake.bridge(), Actor(U), "What does the falcon latency pilot brief say?",
                         model="qwen", k=1)
    prompt = fake.last_body["messages"][1]["content"]
    assert "[1] (news/news.jsonl)" in prompt and "[2] (briefs/brief.json; repeats [1])" in prompt
    assert prompt.index("[1] (news/news.jsonl)") < prompt.index("[2] (briefs/brief.json")
    handle = search.Citation(*_record(conn, 0)).handle
    record, copy = result["citations"]
    assert record["path"] == "news.jsonl" and record["quoted_records"] == []
    assert copy["path"] == "brief.json" and copy["quoted_records"] == [handle]
    shown = answers.reopen(conn, Actor(U), result["id"])
    assert [e["quoted_records"] for e in shown["evidence"]] == [[], [handle]]


def test_ask_adds_no_record_that_the_caller_cannot_read_or_send_to_a_model(conn, books, fake):
    authz.grant(conn, "book:briefs", "read", U)
    fake.reply = "The brief moves falcon to pilot [1]."
    question = "What does the falcon latency pilot brief say?"
    result = answers.ask(conn, fake.bridge(), Actor(U), question, model="qwen", k=1)
    assert [c["path"] for c in result["citations"]] == ["brief.json"]
    assert "repeats" not in fake.last_body["messages"][1]["content"]
    news, _ = books
    _kstd(news, "n")                                                     # searchable, never model input
    _publish(conn, news, "news")
    authz.grant(conn, "book:news", "read", U)
    answers.ask(conn, fake.bridge(), Actor(U), question, model="qwen", k=1)
    assert "news.jsonl" not in fake.last_body["messages"][1]["content"]


def test_migration_backfill_gives_the_values_of_publication(conn, books, tmp_path):
    whole = tmp_path / "whole"
    whole.mkdir()
    (whole / "news.jsonl").write_text("".join(json.dumps(r) + "\n" for r in RECORDS), encoding="utf-8")
    _publish(conn, whole, "whole", profile="whole")                       # one passage, several records: none
    query = "SELECT book, path, ordinal, sha256 FROM record_value ORDER BY 1, 2, 3, 4"
    published = conn.execute(query).fetchall()
    assert {(b, o) for b, _, o, _ in published} == {("news", 0), ("news", 2)}
    conn.execute("DELETE FROM record_value")
    script = next(f for f in files("kutuphane.migrations").iterdir() if f.name == "037_record_value.sql")
    text = script.read_text()
    conn.execute(text[text.index("-- backfill"):])
    assert conn.execute(query).fetchall() == published
