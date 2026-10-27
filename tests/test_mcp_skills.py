"""#80: MCP Skills (SEP-2640) for activated skill folders, and the handling labels in `_meta` of the read tools.
Every check runs through /mcp, for a 2025-11-25 client and a 2026-07-28 client."""
import hashlib
import json
import os
from datetime import datetime, timedelta, timezone

import pytest
from starlette.testclient import TestClient

from kutuphane import authz, catalog, gate, handling, notes, profiles, server, skills
from kutuphane.policy import make_policy
from kutuphane.source import read_source
from test_server import LEGACY, MCP_HEADERS, MODERN, PUBLIC, bearer, fake, keys, mcp_rpc, verifier  # noqa: F401

U, A = "user:ayse", "agent:kobra-7"
BOOK, OBJ = "kitap", "book:kitap"
SKILL = "araclar/ozet"
SKILL_MD, REF = f"{SKILL}/SKILL.md", f"{SKILL}/references/kaynak.md"
SKILL_URI, REF_URI = f"skill://{BOOK}/{SKILL_MD}", f"skill://{BOOK}/{REF}"
SKILL_TEXT = ("---\nname: ozet\ndescription: Bir metni kısaca özetle; kaynakları references/kaynak.md içinde.\n"
              "metadata:\n  version: \"1\"\n---\n\n# Özet\n\nÜç ana noktayı bul ve her biri için bir cümle yaz.\n")
REF_TEXT = "# Kaynaklar\n\nYalnız kullanıcının verdiği metin.\n"
DECLARE = {"io.modelcontextprotocol/clientCapabilities": {"extensions": {skills.EXTENSION_ID: {}}}}
VERSIONS = [LEGACY, MODERN]


def soon():
    return datetime.now(timezone.utc) + timedelta(hours=1)


def write(root, rel: str, text: str) -> None:
    (root / rel).parent.mkdir(parents=True, exist_ok=True)
    (root / rel).write_text(text, encoding="utf-8")


@pytest.fixture
def env(conn, okf_dir, verifier, fake):
    write(okf_dir, SKILL_MD, SKILL_TEXT)
    write(okf_dir, REF, REF_TEXT)
    write(okf_dir, "araclar/yanlis/SKILL.md", "---\nname: baska\ndescription: Adı klasörüyle aynı değil.\n---\nx\n")
    r = catalog.publish(conn, book=BOOK, title=BOOK, files=read_source(okf_dir),
                        policy=make_policy(sensitivity="normal", egress="local_only", protection="standard"),
                        profile=profiles.spec("chunked"))
    authz.grant(conn, OBJ, "read", U)
    authz.delegate(conn, delegator=U, delegate_to=A, obj=OBJ, mode="read", expires_at=soon())
    app = server.create_app(dsn=os.environ["KUTUPHANE_TEST_DSN"], verifier=verifier, bridge=fake.bridge(),
                            model="qwen", public_url=PUBLIC)
    return app, r


def activate(conn) -> None:
    authz.grant(conn, OBJ, "activate", U)
    authz.delegate(conn, delegator=U, delegate_to=A, obj=OBJ, mode="activate", expires_at=soon())


def agent(keys) -> dict:
    return bearer(keys, act={"sub": "kobra-7"})


def rpc(client, auth: dict, method: str, params: dict | None = None, *, version: str, declare: bool = True) -> dict:
    """One JSON-RPC message; a 2026-07-28 `resources/read` names its URI in the `Mcp-Name` header."""
    named = {"Mcp-Name": params["uri"]} if version == MODERN and method == "resources/read" else None
    status, msg = mcp_rpc(client, auth, method, params, version=version,
                          meta=DECLARE if declare and version == MODERN else None, headers=named)
    assert status == 200 or (status == 400 and "error" in msg), msg  # 2026-07-28: an error has HTTP 400
    return msg


def tool(client, auth: dict, name: str, args: dict, *, version: str) -> dict:
    result = rpc(client, auth, "tools/call", {"name": name, "arguments": args}, version=version)["result"]
    assert not result.get("isError"), result
    return result


def events(conn, action: str | None = None) -> list[tuple]:
    return conn.execute("SELECT action, mode, allowed, reason, path, items FROM access_event "
                        "WHERE %(a)s::text IS NULL OR action = %(a)s ORDER BY id", {"a": action}).fetchall()


def block(conn, content_id: str, skill_path: str = SKILL) -> None:
    """A failed scan of the skill: it blocks `activate` on every file of the folder (D71) until a curator clears it."""
    conn.execute("INSERT INTO skill_scan (book, content_id, skill_path, status, input_digest, tool_version, mode, "
                 "reason) VALUES (%s, %s, %s, 'failed', %s, '2.13.1', 'no-llm', 'test: the scan failed')",
                 (BOOK, content_id, skill_path, "0" * 64))


# --- skills/list, skills/get, resources/read -------------------------------------------------------------------

@pytest.mark.parametrize("version", VERSIONS)
def test_a_skill_is_served_only_to_a_principal_with_activate(env, keys, conn, version):
    app, published = env
    with TestClient(app, base_url=PUBLIC) as client:
        for auth in (agent(keys), bearer(keys)):  # a person with `read` too: a skill is for a model to load
            assert rpc(client, auth, "skills/list", version=version)["result"]["skills"] == []
        for method, params in (("skills/get", {"uri": SKILL_URI}), ("resources/read", {"uri": SKILL_URI})):
            error = rpc(client, agent(keys), method, params, version=version)["error"]
            assert error["code"] == -32602 and error["message"] == "forbidden"
        assert ("activate", "activate", False) in [e[:3] for e in events(conn)]  # the refusal is on record

        activate(conn)
        listed = rpc(client, agent(keys), "skills/list", version=version)["result"]
        assert [s["uri"] for s in listed["skills"]] == [SKILL_URI]  # `yanlis` does not conform: not served
        entry = listed["skills"][0]
        assert entry["frontmatter"] == {"name": "ozet", "description": "Bir metni kısaca özetle; kaynakları "
                                        "references/kaynak.md içinde.", "metadata": {"version": "1"}}
        assert [r["uri"] for r in entry["resources"]] == [SKILL_URI, REF_URI]  # manifest order: by path
        assert entry["_meta"]["kutuphane/source"] == {"book": BOOK, "content_id": published.content_id,
                                                      "path": SKILL_MD}
        assert ("ttlMs" in listed) == (version == MODERN)
        got = rpc(client, agent(keys), "skills/get", {"uri": SKILL_URI}, version=version)["result"]["skill"]
        assert got == entry
        read = rpc(client, agent(keys), "resources/read", {"uri": SKILL_URI}, version=version)["result"]
        assert read["contents"][0]["text"] == SKILL_TEXT and read["contents"][0]["mimeType"] == "text/markdown"
        assert [s["uri"] for s in rpc(client, bearer(keys), "skills/list", version=version)["result"]["skills"]] \
            == [SKILL_URI]
    assert [e[:3] + (e[5],) for e in events(conn, skills.LIST_ACTION)] == [(skills.LIST_ACTION, "read", True,
                                                                            [SKILL_URI])] * 2
    assert [e[:3] for e in events(conn, skills.GET_ACTION)] == [(skills.GET_ACTION, "read", True)]


@pytest.mark.parametrize("version", VERSIONS)
def test_the_digests_are_the_sha256_of_the_bytes_and_of_the_content_manifest(env, keys, conn, version):
    app, published = env
    activate(conn)
    with TestClient(app, base_url=PUBLIC) as client:
        entry = rpc(client, agent(keys), "skills/get", {"uri": SKILL_URI}, version=version)["result"]["skill"]
        for resource in entry["resources"]:
            path = skills.parse(resource["uri"])[1]
            content = rpc(client, agent(keys), "resources/read", {"uri": resource["uri"]},
                          version=version)["result"]["contents"][0]
            data = content["text"].encode("utf-8")
            assert resource["digest"] == f"sha256:{hashlib.sha256(data).hexdigest()}"
            assert resource["size"] == len(data)
            manifest = catalog.manifest_entry(conn, BOOK, published.content_id, path)
            assert resource["digest"] == f"sha256:{manifest['sha256']}" and resource["size"] == manifest["size"]
            assert content["_meta"][handling.KEY]["books"] == {BOOK: {"sensitivity": "normal",
                                                                      "egress": "local_only"}}


@pytest.mark.parametrize("version", VERSIONS)
def test_a_blocked_skill_never_appears_and_its_files_are_refused(env, keys, conn, version):
    app, published = env
    activate(conn)
    block(conn, published.content_id)
    with TestClient(app, base_url=PUBLIC) as client:
        assert rpc(client, agent(keys), "skills/list", version=version)["result"]["skills"] == []
        for method, uri in (("skills/get", SKILL_URI), ("resources/read", SKILL_URI), ("resources/read", REF_URI)):
            error = rpc(client, agent(keys), method, {"uri": uri}, version=version)["error"]
            assert error["code"] == -32602 and error["message"] == "forbidden"
        result = rpc(client, agent(keys), "tools/call", {"name": "read_document", "arguments": {
            "book": BOOK, "content_id": published.content_id, "path": SKILL_MD}}, version=version)["result"]
        assert result["isError"]  # the other path refuses it too
    refused = [e for e in events(conn) if e[:3] == ("activate", "activate", False)]
    assert refused and all(e[3] == gate.SKILL_BLOCKED for e in refused)
    assert {e[4] for e in refused} == {SKILL_MD, REF}  # the list names its SKILL.md; reads name their file


def test_a_skill_that_holds_a_blocked_nested_skill_is_not_served(env, keys, conn, okf_dir):
    app, _ = env
    write(okf_dir, "araclar/SKILL.md", "---\nname: araclar\ndescription: Araçlar.\n---\nAlt beceriler.\n")
    r = catalog.publish(conn, book=BOOK, title=BOOK, files=read_source(okf_dir),
                        policy=make_policy(sensitivity="normal", egress="local_only", protection="standard"),
                        profile=profiles.spec("chunked"))
    activate(conn)
    outer = f"skill://{BOOK}/araclar/SKILL.md"
    with TestClient(app, base_url=PUBLIC) as client:
        listed = rpc(client, agent(keys), "skills/list", version=MODERN)["result"]["skills"]
        assert [s["uri"] for s in listed] == [outer, SKILL_URI]
        assert SKILL_URI in [x["uri"] for x in listed[0]["resources"]]  # complete: the nested files too
        block(conn, r.content_id)
        assert [s["uri"] for s in rpc(client, agent(keys), "skills/list", version=MODERN)["result"]["skills"]] == []
        for uri in (outer, SKILL_URI):
            assert rpc(client, agent(keys), "resources/read", {"uri": uri}, version=MODERN)["error"]["code"] == -32602


@pytest.mark.parametrize("version", VERSIONS)
def test_skill_files_are_not_sent_ahead_of_need(env, keys, conn, version):
    app, _ = env
    activate(conn)
    with TestClient(app, base_url=PUBLIC) as client:
        listed = rpc(client, agent(keys), "skills/list", version=version)["result"]
        rpc(client, agent(keys), "skills/get", {"uri": SKILL_URI}, version=version)
    assert "Üç ana noktayı" not in json.dumps(listed, ensure_ascii=False)
    assert all(set(r) == {"uri", "digest", "size"} for s in listed["skills"] for r in s["resources"])
    assert not [e for e in events(conn) if e[0] == "read"]  # no file was delivered


def test_skills_need_the_declaration_when_the_client_states_its_capabilities(env, keys, conn):
    app, _ = env
    activate(conn)
    with TestClient(app, base_url=PUBLIC) as client:
        found = rpc(client, agent(keys), "server/discover", version=MODERN)["result"]["capabilities"]
        assert skills.EXTENSION_ID in found["extensions"] and "resources" in found
        for method, params in (("skills/list", None), ("skills/get", {"uri": SKILL_URI})):
            error = rpc(client, agent(keys), method, params, version=MODERN, declare=False)["error"]
            assert error["code"] == -32021
        # 2025-11-25 has no `extensions` capability on the wire: the call itself is the declaration
        assert rpc(client, agent(keys), "skills/list", version=LEGACY)["result"]["skills"]
        # resources/read is the baseline of SEP-2640: no declaration, the same gate
        read = rpc(client, agent(keys), "resources/read", {"uri": REF_URI}, version=MODERN, declare=False)
        assert read["result"]["contents"][0]["text"] == REF_TEXT


@pytest.mark.parametrize("uri", [f"skill://{BOOK}/araclar/ozet/../ozet/SKILL.md",
                                 f"skill://{BOOK}/araclar%2Fozet/SKILL.md", f"skill://{BOOK}/araclar/yanlis/SKILL.md",
                                 f"skill://{BOOK}/index.md", f"skill://Kitap/{SKILL_MD}", f"skill://{BOOK}/{SKILL}",
                                 "skill:///SKILL.md"])
def test_only_files_of_a_served_skill_are_skill_resources(env, keys, conn, uri):
    app, _ = env
    activate(conn)
    with TestClient(app, base_url=PUBLIC) as client:
        for method in ("skills/get", "resources/read"):
            error = rpc(client, agent(keys), method, {"uri": uri}, version=MODERN)["error"]
            assert error["code"] == -32602 and error["message"] == "not found"


# --- `_meta` handling labels -----------------------------------------------------------------------------------

@pytest.mark.parametrize("version", VERSIONS)
def test_the_read_tools_carry_the_handling_labels(env, keys, conn, version):
    app, published = env
    activate(conn)
    notes.create_journal(conn, book="defter", title="defter", search=True, ai_input=True, by="user:admin",
                         policy=make_policy(sensitivity="restricted", egress="local_only", protection="standard"))
    authz.grant(conn, "book:defter", "read", U)
    authz.delegate(conn, delegator=U, delegate_to=A, obj="book:defter", mode="read", expires_at=soon())
    from test_notes_query import note
    conn.execute("INSERT INTO profile_version (id, spec) VALUES ('pf_journal', '{}') ON CONFLICT DO NOTHING")
    note(conn, "defter", "Bir bulgu.")
    kitap = {BOOK: {"sensitivity": "normal", "egress": "local_only"}}
    with TestClient(app, base_url=PUBLIC) as client:
        found = tool(client, agent(keys), "search_library", {"query": "kayıtlar saklanır"}, version=version)
        labels = found["_meta"][handling.KEY]
        assert labels["books"] == kitap and (labels["sensitivity"], labels["egress"]) == ("normal", "local_only")
        assert found["structuredContent"]["result"]  # the result itself is unchanged

        handle = found["structuredContent"]["result"][0]["citation"]
        cited = tool(client, agent(keys), "open_citation", {"handle": handle}, version=version)
        assert cited["_meta"][handling.KEY]["books"] == kitap and "structuredContent" not in cited

        doc = tool(client, agent(keys), "read_document", {"book": BOOK, "content_id": published.content_id,
                                                         "path": SKILL_MD}, version=version)
        assert doc["structuredContent"]["result"] == SKILL_TEXT
        scan_id = conn.execute("SELECT id FROM skill_scan WHERE skill_path = %s", (SKILL,)).fetchone()[0]
        assert doc["_meta"][handling.KEY]["skill_scans"] == [{
            "book": BOOK, "content_id": published.content_id, "skill_path": SKILL, "scan_id": scan_id,
            "status": "not_scanned", "recommendation": None, "blocking": False}]

        queried = tool(client, agent(keys), "query_notes", {"sets": ["open"]}, version=version)
        labels = queried["_meta"][handling.KEY]
        assert labels["books"] == {"defter": {"sensitivity": "restricted", "egress": "local_only"}}
        assert labels["sensitivity"] == "restricted"
        ref = json.loads(queried["content"][0]["text"])["items"][0]["ref"]
        opened = tool(client, agent(keys), "open_citation", {"handle": ref}, version=version)
        assert opened["_meta"][handling.KEY]["sensitivity"] == "restricted"

        empty = tool(client, agent(keys), "search_library", {"query": "hiçbiryerdeolmayankelime"}, version=version)
        assert empty["_meta"][handling.KEY] == {"books": {}}  # no content: no claim
        if version == MODERN:  # the SDK's serverInfo stamp stays beside ours
            assert "io.modelcontextprotocol/serverInfo" in found["_meta"]


def test_the_strictest_policy_labels_a_result_of_several_books(conn):
    assert handling.build({"a": {"sensitivity": "normal", "egress": "cloud_ok"},
                           "b": {"sensitivity": "normal", "egress": "local_only"}}, []) == {
        "books": {"a": {"sensitivity": "normal", "egress": "cloud_ok"},
                  "b": {"sensitivity": "normal", "egress": "local_only"}},
        "sensitivity": "normal", "egress": "local_only"}
    assert handling.build({"a": {"sensitivity": "normal", "egress": "cloud_ok"}}, [])["egress"] == "cloud_ok"
    assert handling.build({}, []) == {"books": {}}
