"""D70 R3 "my words" confirmation and R7 withdrawal (docs/25 §7; slice R): R1–R8, the 024 part of C9, and M1.

The person signs a `confirm` or `withdraw` act with the software authenticator (tests/softauthn.py) in curator web,
which connects as the curator web role with the deploy grants. Core's `confirm_origin` runs through /mcp as a client
of each protocol era.
"""
import json
import os
import secrets
from datetime import datetime, timedelta, timezone

import psycopg
import pytest
from psycopg.types.json import Jsonb
from starlette.testclient import TestClient

from kutuphane import (authz, confirm, curatorweb, db, decisions, kstd, notes, notesquery, origin, packages, passkey,
                       server)
from kutuphane.gate import Actor

from conftest import WRITE_PATH_COLUMNS
from softauthn import SoftAuthenticator
from test_curatorweb import (CFG, H, ORIGIN, WEB_ROLE, A, J, M, U, enroll, env, login,  # noqa: F401
                             submit, web_dsn)
from test_server import LEGACY, MODERN, PUBLIC, bearer, keys, mcp_rpc, verifier  # noqa: F401

CURATOR_URL = "https://kutuphane-curator.example.ts.net"
AGENT_FOR_AYSE = Actor(A, U, channel="mcp", client_id="kobra-cli")


@pytest.fixture(autouse=True)
def _curator_url(monkeypatch):
    monkeypatch.setenv(confirm.URL_ENV, CURATOR_URL)
    monkeypatch.delenv(confirm.HOURS_ENV, raising=False)


def propose(conn, text, actor=AGENT_FOR_AYSE, origin="human", **kw) -> dict:
    receipt = notes.propose(conn, actor, {"book": J, "kind": "finding", "text": text, "origin": origin, **kw})[0]
    conn.commit()
    return receipt


def seq_of(conn, ref) -> int:
    return conn.execute("SELECT seq FROM note WHERE book || '@' || id = %s", (ref,)).fetchone()[0]


def person(conn, principal=U, **auth_kw):
    """A second browser: its own cookie jar, the person's own passkey."""
    c = TestClient(curatorweb.create_app(dsn=web_dsn(), cfg=CFG), base_url=ORIGIN)
    auth = SoftAuthenticator(ORIGIN, **auth_kw)
    assert enroll(conn, c, auth, principal).status_code == 200
    assert login(c, auth).status_code == 200
    return c, auth


def act(c, auth, body, **get_kw):
    o = c.post("/api/act/options", json=body, headers=H)
    if o.status_code != 200:
        return o
    return submit(c, o.json(), auth.get(o.json()["publicKey"], **get_kw))


def shown(conn, ref, w=None):
    seq = seq_of(conn, ref)
    return origin.shown(conn, [seq], w)[seq]


def _json(message) -> dict:
    """The tool's JSON result, from its text block."""
    (block,) = message["result"]["content"]
    return json.loads(block["text"])


def query(conn, actor=Actor(U), **kw) -> dict:
    out = notesquery.query_notes(conn, actor, for_model=False, book=[J], sets=["open"], **kw)
    return {i["ref"]: i for i in out["items"]}


# --- R1: the agent proposes for Ayşe, Ayşe confirms "verbatim" ----------------------------------------------------

def test_agent_proposes_human_and_the_person_confirms_verbatim(env):  # R1
    r = propose(env, "Kayıtlar iki yıl saklanır; denetim bunu ister.")
    assert r["origin"] == "model" and r["origin_notice"] == "origin-claim-refused"
    book, nid = r["ref"].split("@")
    assert r["confirmation"]["url"] == f"{CURATOR_URL}/c/{book}/{nid}" and r["confirmation"]["expires_at"]
    c, auth = person(env)
    listed = c.get("/api/requests").json()["items"]
    assert [i["ref"] for i in listed] == [r["ref"]]
    page = c.get(f"/api/requests/{book}/{nid}").json()
    assert page["text"] == "Kayıtlar iki yıl saklanır; denetim bunu ister." and page["integrity"] is None
    assert page["request"]["entered_by"] == A and page["request"]["client_id"] == "kobra-cli"
    assert page["request"]["requested"] == "human"
    assert [x["claim"] for x in page["claims"]] == ["human", "assisted"]
    assert page["claims"][0]["words"] == "These are my words, verbatim (I wrote or dictated them)."
    assert page["claims"][1]["words"] == "A model wrote or reworded this. I reviewed it in substance."
    assert env.execute("SELECT count(*) FROM origin_confirmation").fetchone()[0] == 0  # a view stores nothing
    done = act(c, auth, {"action": "confirm", "ref": r["ref"], "claim": "human", "write": page["request"]["write"]})
    assert done.status_code == 200, done.text
    assert done.json()["origin"] == "human" and done.json()["confirmed_by"] == U
    item = query(env)[r["ref"]]
    assert (item["origin"], item["entered_by"], item["confirmed_by"]) == ("human", A, U)
    assert query(env, origin=["human"]).keys() == {r["ref"]} and query(env, origin=["model"]) == {}
    assert env.execute("SELECT origin FROM write_record WHERE note_seq = %s",
                       (seq_of(env, r["ref"]),)).fetchone()[0] == "model"     # the write record never changes
    info = notes.item_info(env, seq_of(env, r["ref"]))
    assert (info["origin"], info["entered_by"], info["confirmed_by"]) == ("human", A, U)
    assert passkey.verify_acts(env, CFG)["problems"] == []
    assert c.get("/api/requests").json()["items"] == []   # confirmed: no longer waiting


def test_kstd_carries_entered_by_and_confirmed_by_for_human():  # R1 (the kstd export)
    item = {"path": "a.md", "origin": "human", "entered_by": A, "confirmed_by": U}
    claim, notices = kstd._claims(item, "kstd.yaml a.md")
    assert (claim["origin"], claim["entered_by"], claim["confirmed_by"]) == ("human", A, U) and notices == []
    claim, notices = kstd._claims({"path": "b.md", "origin": "human"}, "kstd.yaml b.md")
    assert claim["origin"] == "human" and claim["entered_by"] is None and notices == []   # optional
    claim, notices = kstd._claims({"path": "c.md", "origin": "model", "confirmed_by": U}, "kstd.yaml c.md")
    assert claim["confirmed_by"] is None and notices == ["kstd.yaml c.md: confirmed_by ignored: it is only for "
                                                         "origin human"]
    claim, _ = kstd._claims({"path": "d.md", "origin": "assisted", "reviewed_by": U}, "kstd.yaml d.md")
    assert claim["reviewed_by"] == U   # assisted keeps reviewed_by = the confirmer
    infos = {"a.md": {"origin": "human", "reviewed_by": None, "software_agent": None, "entered_by": A,
                      "confirmed_by": U},
             "b.md": {"origin": "human", "reviewed_by": None, "software_agent": None, "entered_by": None,
                      "confirmed_by": None},
             "d.md": {"origin": "assisted", "reviewed_by": U, "software_agent": None, "entered_by": None,
                      "confirmed_by": None}}
    marks = packages.origin_marks(infos)
    assert marks["human_confirmed"] == {"a.md": {"entered_by": A, "confirmed_by": U}}
    assert marks["reviewed"] == {"d.md": U}
    assert "human_confirmed" not in packages.origin_marks({"b.md": infos["b.md"]})   # the lists of before


def test_the_decision_export_shows_the_confirmed_origin(env):  # R1, §7.6
    r = propose(env, "Postgres 17 over 16", kind="decision_proposal", decision={"options": ["16", "17"],
                                                                                   "choice": "17"})
    c, auth = person(env)
    assert act(c, auth, {"action": "confirm", "ref": r["ref"], "claim": "assisted"}).status_code == 200
    records, _ = decisions.export(env, Actor(U), [J])
    assert records[0]["actor"]["origin"] == "assisted"
    assert (records[0]["actor"]["entered_by"], records[0]["actor"]["confirmed_by"]) == (A, U)
    assert notes.item_info(env, seq_of(env, r["ref"]))["reviewed_by"] == U


# --- R2: another person ----------------------------------------------------------------------------------------

def test_another_person_cannot_confirm_human_and_assisted_needs_curate(env):  # R2
    r = propose(env, "Mehmet did not write this")
    authz.grant(env, f"book:{J}", "read", M)
    env.commit()
    c, auth = person(env, M)
    assert c.get("/api/requests").json()["items"] == []
    page = c.get(f"/api/requests/{r['ref'].replace('@', '/')}").json()
    assert page["claims"] == []
    for claim in ("human", "assisted"):
        refused = act(c, auth, {"action": "confirm", "ref": r["ref"], "claim": claim})
        assert refused.status_code == 403, refused.text
    authz.grant(env, f"book:{J}", "curate", M)
    env.commit()
    assert [x["claim"] for x in c.get(f"/api/requests/{r['ref'].replace('@', '/')}").json()["claims"]] == ["assisted"]
    assert act(c, auth, {"action": "confirm", "ref": r["ref"], "claim": "human"}).status_code == 403
    done = act(c, auth, {"action": "confirm", "ref": r["ref"], "claim": "assisted"})
    assert done.status_code == 200, done.text
    assert shown(env, r["ref"]) == ("assisted", A, M)


# --- R3: MCP confirm_origin -----------------------------------------------------------------------------------

def test_confirm_origin_uses_url_elicitation_only(env, keys, verifier):  # R3
    r = propose(env, "Bunu ben yazdım.")
    app = server.create_app(dsn=os.environ["KUTUPHANE_TEST_DSN"], verifier=verifier, bridge=None, model=None,
                            public_url=PUBLIC)
    agent = bearer(keys, act={"sub": "kobra-7"})
    call = {"name": "confirm_origin", "arguments": {"ref": r["ref"]}}
    url_caps = {"io.modelcontextprotocol/clientCapabilities": {"elicitation": {"url": {}}}}
    with TestClient(app, base_url=PUBLIC) as client_:
        _, first = mcp_rpc(client_, agent, "tools/call", call, version=MODERN, meta=url_caps)
        result = first["result"]
        assert result["resultType"] == "input_required" and result["requestState"]
        (key, request), = result["inputRequests"].items()
        assert request["method"] == "elicitation/create" and request["params"]["mode"] == "url"
        assert request["params"]["url"] == r["confirmation"]["url"] and "requestedSchema" not in request["params"]
        # the retry: an `accept` only means "the URL was opened"; it confirms nothing
        retry = {**call, "inputResponses": {key: {"action": "accept"}}, "requestState": result["requestState"]}
        _, again = mcp_rpc(client_, agent, "tools/call", retry, version=MODERN, meta=url_caps)
        out = _json(again)
        assert out["origin"] == "model" and out["confirmation"]["state"] == "open"
        assert env.execute("SELECT count(*) FROM origin_confirmation").fetchone()[0] == 0
        # a 2026-07-28 client without the URL capability, and a 2025-11-25 client: the URL in the result
        for version, meta in ((MODERN, None), (LEGACY, None)):
            _, plain = mcp_rpc(client_, agent, "tools/call", call, version=version, meta=meta)
            got = _json(plain)["confirmation"]
            assert got["state"] == "open" and got["url"] == r["confirmation"]["url"], version
        # HTTP, and the read right decided by the gate
        book, nid = r["ref"].split("@")
        h = client_.get(f"/v1/notes/{book}/{nid}/confirmation", headers=bearer(keys))
        assert h.status_code == 200 and h.json()["confirmation"]["state"] == "open"
        assert client_.get(f"/v1/notes/{book}/{nid}/confirmation", headers=bearer(keys, sub="mehmet")).status_code \
            == 403
    c, auth = person(env)
    assert act(c, auth, {"action": "confirm", "ref": r["ref"], "claim": "human"}).status_code == 200
    out = confirm.confirmation(env, Actor(A, U, channel="mcp"), r["ref"])
    assert out["origin"] == "human" and out["confirmation"] == {"state": "confirmed", "claim": "human",
                                                                "entered_by": A, "confirmed_by": U}
    assert confirm.confirmation(env, Actor(A, U, channel="mcp"),
                                propose(env, "no claim", origin=None)["ref"])["confirmation"] == {"state": "none"}


# --- R4: one changed byte -------------------------------------------------------------------------------------

def test_one_changed_byte_is_another_note_and_the_confirmation_does_not_move(env):  # R4
    r = propose(env, "The retry budget is three.")
    c, auth = person(env)
    assert act(c, auth, {"action": "confirm", "ref": r["ref"], "claim": "human"}).status_code == 200
    changed = propose(env, "The retry budget is three!", origin=None)
    assert changed["ref"] != r["ref"] and shown(env, changed["ref"]) == ("model", None, None)
    successor = propose(env, "The retry budget is four.", origin=None, links=[{"type": "supersedes",
                                                                                 "ref": r["ref"]}])
    assert shown(env, successor["ref"]) == ("model", None, None)
    assert shown(env, r["ref"]) == ("human", A, U)


# --- R5: the request expires ---------------------------------------------------------------------------------

def test_the_request_expires_after_24_hours_and_a_new_proposal_opens_a_new_one(env):  # R5
    r = propose(env, "Old words")
    env.execute("UPDATE write_record SET at = at - interval '25 hours' WHERE note_seq = %s", (seq_of(env, r["ref"]),))
    env.commit()
    c, auth = person(env)
    assert c.get("/api/requests").json()["items"] == []
    page = c.get(f"/api/requests/{r['ref'].replace('@', '/')}").json()
    assert page["claims"] == [] and page["request"]["open"] is False
    refused = act(c, auth, {"action": "confirm", "ref": r["ref"], "claim": "human"})
    assert refused.status_code == 400 and "request-expired" in refused.json()["error"]
    assert confirm.confirmation(env, Actor(U), r["ref"])["confirmation"]["state"] == "expired"
    again = propose(env, "Old words")
    assert again["ref"] == r["ref"] and again["confirmation"]["url"]
    assert confirm.confirmation(env, Actor(U), r["ref"])["confirmation"]["state"] == "open"
    assert act(c, auth, {"action": "confirm", "ref": r["ref"], "claim": "human"}).status_code == 200


def test_an_expiry_between_options_and_act_refuses(env):  # R5, §5.4 step 7
    r = propose(env, "Late words")
    c, auth = person(env)
    o = c.post("/api/act/options", json={"action": "confirm", "ref": r["ref"], "claim": "human"}, headers=H).json()
    env.execute("UPDATE write_record SET at = at - interval '25 hours' WHERE note_seq = %s", (seq_of(env, r["ref"]),))
    env.commit()
    refused = submit(c, o, auth.get(o["publicKey"]))
    assert refused.status_code == 400 and "request-expired" in refused.json()["error"]
    assert env.execute("SELECT count(*) FROM origin_confirmation").fetchone()[0] == 0


# --- R6: two confirmations, a withdrawal ---------------------------------------------------------------------

def test_withdrawal_of_the_latest_confirmation_never_brings_back_an_older_one(env):  # R6
    r = propose(env, "My own sentence.")
    c, auth = person(env)
    assert act(c, auth, {"action": "confirm", "ref": r["ref"], "claim": "human"}).status_code == 200
    assert act(c, auth, {"action": "confirm", "ref": r["ref"], "claim": "assisted"}).status_code == 200
    assert shown(env, r["ref"]) == ("assisted", A, U)
    before = notesquery.watermark(env)
    authz.grant(env, f"book:{J}", "read", M)
    authz.grant(env, f"book:{J}", "curate", M)
    env.commit()
    cm, am = person(env, M)
    refused = act(cm, am, {"action": "withdraw", "ref": r["ref"]})
    assert refused.status_code == 403 and "only the confirmer" in refused.json()["error"]
    page = c.get(f"/api/requests/{r['ref'].replace('@', '/')}").json()
    assert page["withdraw"] is not None
    done = act(c, auth, {"action": "withdraw", "ref": r["ref"]})
    assert done.status_code == 200, done.text
    assert done.json()["origin"] == "model" and shown(env, r["ref"]) == ("model", None, None)
    assert shown(env, r["ref"], before) == ("assisted", A, U)          # as_of before the withdrawal
    assert query(env, as_of=before)[r["ref"]]["origin"] == "assisted"
    assert "entered_by" not in query(env)[r["ref"]]
    changed = notesquery.query_notes(env, Actor(U), for_model=False, book=[J], sets=["open"], since=before)
    assert [i["ref"] for i in changed["items"]] == [r["ref"]]           # `since` sees the withdrawal
    assert act(c, auth, {"action": "withdraw", "ref": r["ref"]}).status_code == 400   # nothing live
    assert passkey.verify_acts(env, CFG)["problems"] == []


# --- R7: an agent on its own rights ----------------------------------------------------------------------------

def test_an_agent_on_its_own_rights_has_no_person_and_a_curator_gives_assisted(env):  # R7
    for mode in ("read", "propose"):
        authz.grant(env, f"book:{J}", mode, A)
    env.commit()
    r = propose(env, "An agent's own finding", actor=Actor(A, None, channel="mcp"))
    assert r["confirmation"]["url"]
    assert env.execute("SELECT person FROM write_record WHERE note_seq = %s",
                       (seq_of(env, r["ref"]),)).fetchone()[0] is None
    c, auth = person(env)   # Ayşe is a curator of the book
    page = c.get(f"/api/requests/{r['ref'].replace('@', '/')}").json()
    assert [x["claim"] for x in page["claims"]] == ["assisted"]
    assert act(c, auth, {"action": "confirm", "ref": r["ref"], "claim": "human"}).status_code == 403
    assert act(c, auth, {"action": "confirm", "ref": r["ref"], "claim": "assisted"}).status_code == 200
    assert shown(env, r["ref"]) == ("assisted", A, U)


def test_a_tool_claim_or_no_claim_opens_no_request(env):  # §7.1
    assert "confirmation" not in propose(env, "tool output", origin="tool")
    assert "confirmation" not in propose(env, "plain", origin=None)


# --- R8: user verification ---------------------------------------------------------------------------------------

def test_a_confirm_act_without_user_verification_is_refused(env):  # R8
    r = propose(env, "Needs UV")
    c, auth = person(env)
    refused = act(c, auth, {"action": "confirm", "ref": r["ref"], "claim": "human"}, uv=False)
    assert refused.status_code == 403 and "user-verification-missing" in refused.json()["error"]
    assert shown(env, r["ref"]) == ("model", None, None)
    assert env.execute("SELECT count(*) FROM origin_confirmation").fetchone()[0] == 0


def test_a_changed_note_is_not_shown_for_signing(env):  # §5.2 for confirm
    other = propose(env, "target", origin=None)
    r = propose(env, "Integrity")
    seq = seq_of(env, r["ref"])
    write = env.execute("SELECT seq FROM write_record WHERE note_seq = %s AND creates", (seq,)).fetchone()[0]
    with env.transaction():  # a part written before migration 039 (its trigger off, as then)
        env.execute("SET LOCAL session_replication_role = replica")
        env.execute("INSERT INTO note_link (src, src_book, type, dst_note, dst_note_book, creation, write_seq) "
                    "VALUES (%s, %s, 'about', %s, %s, true, %s)", (seq, J, seq_of(env, other["ref"]), J, write))
    c, auth = person(env)
    page = c.get(f"/api/requests/{r['ref'].replace('@', '/')}").json()
    assert page["integrity"] == "note-integrity" and page["claims"] == []
    refused = act(c, auth, {"action": "confirm", "ref": r["ref"], "claim": "human"})
    assert refused.status_code == 403 and "note-integrity" in refused.json()["error"]


# --- C9 (024): the database rules, as hostile inserts --------------------------------------------------------------

def _signed(conn, principal, action, payload) -> int:
    """An act row as the curator web role would write it (a trusted-base row: the signature is not checked here)."""
    handle = secrets.token_bytes(32)
    conn.execute("INSERT INTO curator_person VALUES (%s, %s) ON CONFLICT DO NOTHING", (principal, handle))
    handle = conn.execute("SELECT user_handle FROM curator_person WHERE principal = %s", (principal,)).fetchone()[0]
    eid = "en_" + secrets.token_hex(16)
    conn.execute("INSERT INTO curator_enrollment (id, principal, code_sha256, created_by, expires_at) VALUES "
                 "(%s, %s, %s, 'user:admin', now() + interval '15 minutes')", (eid, principal, secrets.token_bytes(32)))
    cred, sid, cid = secrets.token_bytes(16), secrets.token_bytes(32), "ch_" + secrets.token_hex(16)
    conn.execute("INSERT INTO passkey (credential_id, principal, user_handle, enrollment, public_key, sign_count, "
                 "backup_eligible) VALUES (%s, %s, %s, %s, 'k', 0, true)", (cred, principal, handle, eid))
    conn.execute("INSERT INTO curator_session (id_sha256, principal, login, enrollment, expires_at) VALUES "
                 "(%s, %s, 'enrollment', %s, now() + interval '1 hour')", (sid, principal, eid))
    conn.execute("INSERT INTO curator_challenge (id, session, principal, action, payload, challenge, expires_at) "
                 "VALUES (%s, %s, %s, %s, %s, %s, now() + interval '5 minutes')",
                 (cid, sid, principal, action, Jsonb(payload), secrets.token_bytes(32)))
    return conn.execute("INSERT INTO curator_act (challenge, principal, action, credential_id, authenticator_data, "
                        "client_data_json, signature, backup_state) VALUES (%s, %s, %s, %s, 'a', 'c', 's', true) "
                        "RETURNING seq", (cid, principal, action, cred)).fetchone()[0]


CONFIRM = ("INSERT INTO origin_confirmation (note_seq, book, note_id, write_seq, claim, entered_by, confirmed_by, act) "
           "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING seq")


def _refused(conn, sql, params, error, role=None):
    with pytest.raises(error):
        with conn.transaction():
            if role:
                conn.execute(f"SET LOCAL ROLE {role}")
            conn.execute(sql, params)


def test_the_database_refuses_confirmations_outside_the_rules(env):  # C9 (024)
    r = propose(env, "probe words")
    plain = propose(env, "no request", origin=None)
    seq, nid = seq_of(env, r["ref"]), r["ref"].split("@")[1]
    write = env.execute("SELECT seq FROM write_record WHERE note_seq = %s", (seq,)).fetchone()[0]
    item = {"ref": r["ref"], "id": nid, "write": write}
    statement = {"item": item, "claim": "human", "entered_by": A}
    by_mehmet = _signed(env, M, "confirm", statement)
    by_ayse = _signed(env, U, "confirm", statement)
    standing_act = _signed(env, U, "standing", statement)
    env.commit()
    # human by anyone but the request's person: the human_by key
    _refused(env, CONFIRM, (seq, J, nid, write, "human", A, M, by_mehmet), psycopg.errors.ForeignKeyViolation,
             WEB_ROLE)
    # a confirmation other than its statement: another claim, another writer: the trigger
    _refused(env, CONFIRM, (seq, J, nid, write, "assisted", A, U, by_ayse), psycopg.errors.RaiseException, WEB_ROLE)
    _refused(env, CONFIRM, (seq, J, nid, write, "human", U, U, by_ayse), psycopg.Error, WEB_ROLE)
    # a write that is no request; an act of another action; a confirmer who is not the signer
    pw = env.execute("SELECT seq FROM write_record WHERE note_seq = %s", (seq_of(env, plain["ref"]),)).fetchone()[0]
    _refused(env, CONFIRM, (seq_of(env, plain["ref"]), J, plain["ref"].split("@")[1], pw, "human", A, U, by_ayse),
             psycopg.Error, WEB_ROLE)
    _refused(env, CONFIRM, (seq, J, nid, write, "human", A, U, standing_act), psycopg.errors.ForeignKeyViolation,
             WEB_ROLE)
    # the app role (Core) writes nothing
    _refused(env, CONFIRM, (seq, J, nid, write, "human", A, U, by_ayse), psycopg.errors.InsufficientPrivilege,
             "kutuphane_app_test")
    with env.transaction():
        env.execute(f"SET LOCAL ROLE {WEB_ROLE}")
        conf = env.execute(CONFIRM, (seq, J, nid, write, "human", A, U, by_ayse)).fetchone()[0]
    _refused(env, CONFIRM, (seq, J, nid, write, "human", A, U, by_ayse), psycopg.errors.UniqueViolation, WEB_ROLE)
    # R7: only the confirmer withdraws, with a withdraw act of their own
    withdraw_m = _signed(env, M, "withdraw", {"confirmation": conf, "item": {"ref": r["ref"], "id": nid}})
    withdraw_u = _signed(env, U, "withdraw", {"confirmation": conf, "item": {"ref": r["ref"], "id": nid}})
    env.commit()
    wd = "INSERT INTO origin_withdrawal (confirmation, withdrawn_by, act) VALUES (%s, %s, %s)"
    _refused(env, wd, (conf, M, withdraw_m), psycopg.errors.ForeignKeyViolation, WEB_ROLE)
    _refused(env, wd, (conf, U, by_mehmet), psycopg.errors.ForeignKeyViolation, WEB_ROLE)
    _refused(env, wd, (conf, U, withdraw_u), psycopg.errors.InsufficientPrivilege, "kutuphane_app_test")
    with env.transaction():
        env.execute(f"SET LOCAL ROLE {WEB_ROLE}")
        env.execute(wd, (conf, U, withdraw_u))
    _refused(env, wd, (conf, U, withdraw_u), psycopg.errors.UniqueViolation, WEB_ROLE)
    assert env.execute("SELECT count(*) FROM origin_confirmation", ()).fetchone()[0] == 1
    with env.transaction():
        env.execute("SET LOCAL ROLE kutuphane_app_test")  # the app role still reads both (shown origin)
        assert env.execute("SELECT count(*) FROM origin_withdrawal").fetchone()[0] == 1


def test_the_withdrawal_and_confirmation_keep_their_seq_order(env):  # §4: memory_seq covers both
    r = propose(env, "seq order")
    c, auth = person(env)
    assert act(c, auth, {"action": "confirm", "ref": r["ref"], "claim": "human"}).status_code == 200
    w = notesquery.watermark(env)
    assert w == env.execute("SELECT max(seq) FROM origin_confirmation").fetchone()[0]
    assert datetime.now(timezone.utc) - env.execute("SELECT at FROM origin_confirmation").fetchone()[0] \
        < timedelta(minutes=5)


def test_the_curator_url_is_optional_and_the_hours_are_configurable(env, monkeypatch):  # §7.5, §10.2
    monkeypatch.delenv(confirm.URL_ENV)
    monkeypatch.setenv(confirm.HOURS_ENV, "2")
    r = propose(env, "no url")
    assert r["confirmation"]["url"] is None
    at = env.execute("SELECT at FROM write_record WHERE note_seq = %s", (seq_of(env, r["ref"]),)).fetchone()[0]
    expires = datetime.fromisoformat(r["confirmation"]["expires_at"].replace("Z", "+00:00"))
    assert expires - at == timedelta(hours=2)
    state = confirm.confirmation(env, Actor(U), r["ref"])["confirmation"]
    assert state["state"] == "open" and "url" not in state
    monkeypatch.setenv(confirm.HOURS_ENV, "x")
    with pytest.raises(RuntimeError):
        confirm.hours()


# --- M1: 024 on a database with notes ------------------------------------------------------------------------------

def test_024_applies_to_a_database_with_requests_and_keeps_the_origins(conn):  # M1 (024)
    from importlib.resources import files
    from kutuphane.policy import make_policy
    conn.execute("DROP SCHEMA public CASCADE")
    conn.execute("CREATE SCHEMA public")
    conn.execute("CREATE TABLE schema_migration (name text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())")
    for script in sorted((f for f in files("kutuphane.migrations").iterdir() if f.name.endswith(".sql")),
                         key=lambda f: f.name):
        if script.name >= "024" and script.name not in WRITE_PATH_COLUMNS:
            continue
        conn.execute(script.read_text())
        conn.execute("INSERT INTO schema_migration (name) VALUES (%s)", (script.name,))
    notes.create_journal(conn, book=J, title=J, search=True, ai_input=True,
                         policy=make_policy(sensitivity="normal", egress="local_only", protection="standard"),
                         by="user:admin")
    for mode in ("read", "propose"):
        authz.grant(conn, f"book:{J}", mode, U)
        authz.delegate(conn, delegator=U, delegate_to=A, obj=f"book:{J}", mode=mode,
                       expires_at=datetime.now(timezone.utc) + timedelta(hours=1))
    asked = notes.propose(conn, AGENT_FOR_AYSE, {"book": J, "kind": "finding", "text": "old request",
                                                "origin": "human"})[0]["ref"]
    direct = notes.propose(conn, Actor(U, channel="http"), {"book": J, "kind": "finding", "text": "typed"})[0]["ref"]
    applied = db.migrate(conn)
    assert applied[0] == "024_origin_confirmation.sql"
    rows = {s: (p, c) for s, p, c in conn.execute("SELECT note_seq, person, confirmable FROM write_record")}
    assert rows[seq_of(conn, asked)] == (U, True) and rows[seq_of(conn, direct)] == (U, None)
    assert shown(conn, asked) == ("model", None, None) and shown(conn, direct) == ("unknown", None, None)
    assert confirm.confirmation(conn, Actor(U), asked)["confirmation"]["state"] == "open"
