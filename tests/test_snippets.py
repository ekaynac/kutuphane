"""#121: `search_library(max_chars=…)` and `GET /v1/search?max_chars=…` give a deterministic snippet per hit around
the match, with `truncated` and the citation handle. The ranking, the default and the gates do not change."""
import asyncio
import json
import os

import pytest
import yaml
from starlette.testclient import TestClient

from kutuphane import authz, catalog, kstd, profiles, retrieval, server, snippets
from kutuphane.gate import Actor
from kutuphane.policy import make_policy
from kutuphane.source import read_source
from test_identity import token
from test_server import PUBLIC, U, bearer, call_tool, keys, verifier  # noqa: F401 (fixtures)

POLICY = make_policy(sensitivity="normal", egress="local_only", protection="standard")
FILLER = " ".join(f"satır{i} dolgu metni burada sürer." for i in range(30))
LONG = f"# Uzun belge\n\n{FILLER} Eski kayıtlar imzalı arşiv paketine taşınır. {FILLER}\n"
QUERY = "arşiv paketine"


def _publish(conn, root, manifest: dict | None = None):
    (root / "politika" / "uzun.md").write_text(LONG)
    if manifest is not None:
        (root / kstd.MANIFEST).write_text(yaml.safe_dump(manifest, allow_unicode=True))
    catalog.publish(conn, book="kitap", title="kitap", files=read_source(root), policy=POLICY,
                    profile=profiles.spec("chunked"))
    authz.grant(conn, "book:kitap", "read", U)


def _search(max_chars=None, model_reader=False, actor=Actor(U)):
    return server.op_search(os.environ["KUTUPHANE_TEST_DSN"], retrieval.Stages(), actor, QUERY, 8, model_reader,
                            max_chars=max_chars)


# --- the window (no database) --------------------------------------------------------------------------------

def _plain(snippet: str) -> str:
    return snippet.removeprefix(snippets.MARK).removesuffix(snippets.MARK)


def test_window_is_around_the_match_at_word_boundaries():
    text = " ".join(f"kelime{i}" for i in range(200))           # 1,689 characters
    start = text.index("kelime120")
    spans = [(start, start + len("kelime120"), "kelime120")]
    out, truncated = snippets.window(text, spans, 100)
    assert truncated and "kelime120" in out and len(out) <= 100
    assert out.startswith(snippets.MARK) and out.endswith(snippets.MARK)
    body = _plain(out)
    at = text.index(body)
    assert text[at - 1] == " " and text[at + len(body)] == " "      # whole words only
    assert snippets.window(text, spans, 100) == (out, True)        # the same bytes again


def test_window_without_a_match_starts_at_the_passage_start():
    text = "başlangıç " + "x" * 300
    out, truncated = snippets.window(text, [], 80)
    assert truncated and out.startswith("başlangıç") and out.endswith(snippets.MARK) and len(out) <= 80


def test_window_prefers_more_distinct_terms_then_more_matches():
    words = ["w"] * 400
    words[50] = "alfa"                                              # one term, alone
    words[300], words[302] = "alfa", "beta"                         # two distinct terms close together
    text = " ".join(words)
    spans = []
    for word in ("alfa", "beta"):
        at = -1
        while (at := text.find(word, at + 1)) >= 0:
            spans.append((at, at + len(word), word))
    out, _ = snippets.window(text, sorted(spans), 80)
    assert "alfa w beta" in out


def test_a_text_that_fits_is_whole_and_a_long_word_is_cut():
    assert snippets.window("kısa metin", [], 80) == ("kısa metin", False)
    word = "y" * 500
    out, truncated = snippets.window(word, [(0, 500, "y")], 80)
    assert truncated and out == "y" * 78 + snippets.MARK


@pytest.mark.parametrize("value", [79, 0, -1, snippets.MAX_CHARS + 1, True, "300", 300.0])
def test_max_chars_bounds_are_checked_before_the_search(value):
    with pytest.raises(ValueError, match="max_chars must be 80.."):
        server.op_search("unused", retrieval.Stages(), Actor(U), QUERY, 8, max_chars=value)


# --- search, HTTP and MCP ---------------------------------------------------------------------------------------

def test_snippets_keep_the_ranking_and_contain_the_match(conn, okf_dir):
    _publish(conn, okf_dir)
    full = _search()
    cut = _search(max_chars=300)
    assert [(h["citation"], h["score"]) for h in cut] == [(h["citation"], h["score"]) for h in full]
    long_hit = next(h for h in cut if "/politika/uzun.md#" in h["citation"])
    assert long_hit["truncated"] is True and len(long_hit["text"]) <= 300
    assert "arşiv paketine" in long_hit["text"] and long_hit["text"].startswith(snippets.MARK)
    assert len(next(h for h in full if h["citation"] == long_hit["citation"])["text"]) > 300
    short = next(h for h in cut if "/politika/veri-saklama.md#" in h["citation"])
    assert short["truncated"] is False
    assert short["text"] == next(h for h in full if h["citation"] == short["citation"])["text"]
    assert all("truncated" not in h for h in full)                              # the default is unchanged
    assert json.dumps(_search(max_chars=300)) == json.dumps(cut)                # the same bytes again
    for bound in (snippets.MIN_CHARS, snippets.MAX_CHARS):
        assert all(len(h["text"]) <= bound for h in _search(max_chars=bound))
    opened = server.op_citation(os.environ["KUTUPHANE_TEST_DSN"], Actor(U), long_hit["citation"])
    assert opened["text"] == next(h for h in full if h["citation"] == long_hit["citation"])["text"]


def test_http_and_mcp_take_max_chars(conn, okf_dir, keys, verifier):
    _publish(conn, okf_dir)
    dsn = os.environ["KUTUPHANE_TEST_DSN"]
    app = server.create_app(dsn=dsn, verifier=verifier, bridge=None, model=None, public_url=PUBLIC)
    expected = _search(max_chars=300)
    with TestClient(app) as client:
        h = bearer(keys)
        r = client.get("/v1/search", params={"q": QUERY, "max_chars": 300}, headers=h)
        assert r.status_code == 200 and r.json()["results"] == expected
        assert all("truncated" not in x for x in client.get("/v1/search", params={"q": QUERY},
                                                             headers=h).json()["results"])
        for bad, message in (("abc", "max_chars must be an integer"), ("79", "max_chars must be 80..")):
            r = client.get("/v1/search", params={"q": QUERY, "max_chars": bad}, headers=h)
            assert r.status_code == 400 and r.json()["error"].startswith(message)
    mcp = server.build_mcp(dsn=dsn, verifier=verifier, bridge=None, model=None, public_url=PUBLIC)
    claims = asyncio.run(server._Verifier(verifier).verify_token(token(keys))).claims
    _content, structured = call_tool(mcp, claims, "search_library", {"query": QUERY, "max_chars": 300})
    assert [(x["citation"], x["text"], x["truncated"]) for x in structured["result"]] == \
        [(x["citation"], x["text"], x["truncated"]) for x in expected]
    with pytest.raises(Exception, match="max_chars must be 80.."):
        call_tool(mcp, claims, "search_library", {"query": QUERY, "max_chars": 79})


def test_a_withheld_passage_gets_no_snippet(conn, okf_dir):
    manifest = {"standard": "kstd/0.2", "issuer": "ACME <kb@acme.example>", "issued": "2026-10-22",
                "rights": {"license": "CC-BY-4.0", "holder": "ACME", "personal_data": "no",
                           "ai_use": {"search": "y", "ai_input": "n", "train": "n"}}}
    _publish(conn, okf_dir, manifest)
    model = _search(max_chars=300, model_reader=True)
    assert model and all(h["text"] is None and h["withheld"] and "truncated" not in h for h in model)
    human = _search(max_chars=300)                                              # a person reads the snippet
    assert [h["citation"] for h in human] == [h["citation"] for h in model]
    assert any(h["truncated"] and "arşiv" in h["text"] for h in human)
    assert _search(max_chars=300, actor=Actor("user:mehmet")) == []             # no read: no hit, no snippet
