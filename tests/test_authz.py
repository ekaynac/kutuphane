"""M1b: AT-04 (file path), AT-05, AT-06, AT-12, AT-16 (grants, purpose)."""
from datetime import datetime, timedelta, timezone

import pytest

from kutuphane import agentfiles, authz, catalog, gate, profiles, search
from kutuphane.gate import Actor, Denied
from kutuphane.policy import make_policy
from kutuphane.source import read_source

U, A, ROLE = "user:ayse", "agent:kobra-7", "role:hukuk"
BOOK, OBJ = "kitap", "book:kitap"
DOC, SKILL = "politika/veri-saklama.md", "skills/ozet.md"


def soon(hours=8):
    return datetime.now(timezone.utc) + timedelta(hours=hours)


@pytest.fixture
def book(conn, okf_dir):
    (okf_dir / "skills").mkdir()
    (okf_dir / "skills" / "ozet.md").write_text("---\ntype: skill\n---\nÖzetle.\n", encoding="utf-8")
    r = catalog.publish(conn, book=BOOK, title=BOOK, files=read_source(okf_dir),
                        policy=make_policy(sensitivity="normal", egress="local_only", protection="standard"),
                        profile=profiles.spec("whole"))
    return r.content_id


def events(conn, correlation_id):
    return conn.execute("SELECT action, allowed, reason, grant_ids, delegation_id, policy_id FROM access_event "
                        "WHERE correlation_id = %s ORDER BY id", (correlation_id,)).fetchall()


def test_user_reads_with_direct_grant_and_it_is_logged(conn, book):
    gid = authz.grant(conn, OBJ, "read", U)
    actor = Actor(U)
    assert gate.deliver_file(conn, actor, BOOK, book, DOC).startswith(b"---")
    (action, allowed, reason, grant_ids, _, policy_id), = events(conn, actor.correlation_id)
    assert (action, allowed, reason, grant_ids) == ("read", True, "grant", [gid])
    assert policy_id == catalog.current_policy(conn, BOOK)


def test_role_membership_grants_and_its_revocation_denies(conn, book):
    authz.grant(conn, OBJ, "read", f"{ROLE}#member")
    authz.add_member(conn, ROLE, U)
    assert gate.deliver_file(conn, Actor(U), BOOK, book, DOC)
    authz.revoke(conn, ROLE, "member", U)
    with pytest.raises(Denied):
        gate.deliver_file(conn, Actor(U), BOOK, book, DOC)


def test_agent_reads_through_live_delegation(conn, book):
    authz.grant(conn, OBJ, "read", U)
    did = authz.delegate(conn, delegator=U, delegate_to=A, obj=OBJ, mode="read", expires_at=soon(), purpose="özet")
    actor = Actor(A, on_behalf_of=U)
    assert gate.deliver_file(conn, actor, BOOK, book, DOC)
    assert events(conn, actor.correlation_id)[0][4] == did
    assert conn.execute("SELECT purpose FROM delegation WHERE id = %s", (did,)).fetchone()[0] == "özet"


def test_revoked_delegation_denies_next_request(conn, book):  # AT-04 (read path)
    authz.grant(conn, OBJ, "read", U)
    did = authz.delegate(conn, delegator=U, delegate_to=A, obj=OBJ, mode="read", expires_at=soon())
    authz.revoke_delegation(conn, did)
    actor = Actor(A, on_behalf_of=U)
    with pytest.raises(Denied):
        gate.deliver_file(conn, actor, BOOK, book, DOC)
    assert events(conn, actor.correlation_id)[0][:2] == ("read", False)


def test_revocation_in_flight_stops_delivery(conn, book, monkeypatch):  # AT-04 race
    authz.grant(conn, OBJ, "read", U)
    did = authz.delegate(conn, delegator=U, delegate_to=A, obj=OBJ, mode="read", expires_at=soon())
    real_read = catalog.read_file

    def read_then_revoke(*args):
        data = real_read(*args)
        authz.revoke_delegation(conn, did)  # lands after the first check, before delivery
        return data
    monkeypatch.setattr(catalog, "read_file", read_then_revoke)
    actor = Actor(A, on_behalf_of=U)
    with pytest.raises(Denied, match="revoked before delivery"):
        gate.deliver_file(conn, actor, BOOK, book, DOC)
    assert [e[1] for e in events(conn, actor.correlation_id)] == [False]


def test_delegator_losing_right_disables_delegation(conn, book):  # AT-05
    authz.grant(conn, OBJ, "read", U)
    did = authz.delegate(conn, delegator=U, delegate_to=A, obj=OBJ, mode="read", expires_at=soon())
    authz.revoke(conn, OBJ, "read", U)
    d = authz.authorize(conn, A, U, OBJ, "read")
    assert not d.allowed and d.delegation_id == did
    assert conn.execute("SELECT revoked_at FROM delegation WHERE id = %s", (did,)).fetchone()[0] is None


def test_cannot_delegate_beyond_own_rights(conn, book):  # AT-06
    authz.grant(conn, OBJ, "discover", U)
    with pytest.raises(authz.AuthzError, match="does not hold read"):
        authz.delegate(conn, delegator=U, delegate_to=A, obj=OBJ, mode="read", expires_at=soon())
    with pytest.raises(authz.AuthzError, match="does not hold"):
        authz.delegate(conn, delegator=U, delegate_to=A, obj="book:baska", mode="discover", expires_at=soon())


@pytest.mark.parametrize("delegator,delegate_to", [(A, "agent:other"), ("role:hukuk", A), (U, "user:mehmet")])
def test_only_user_to_agent_one_level(conn, book, delegator, delegate_to):  # AT-06 depth / fake delegator
    with pytest.raises(authz.AuthzError):
        authz.delegate(conn, delegator=delegator, delegate_to=delegate_to, obj=OBJ, mode="read", expires_at=soon())


def test_expired_delegation_denies(conn, book):  # AT-06 expiry
    authz.grant(conn, OBJ, "read", U)
    did = authz.delegate(conn, delegator=U, delegate_to=A, obj=OBJ, mode="read", expires_at=soon())
    conn.execute("UPDATE delegation SET expires_at = now() WHERE id = %s", (did,))  # the expiry instant itself
    assert not authz.authorize(conn, A, U, OBJ, "read").allowed


def test_modes_are_independent(conn, book):  # AT-06 / D24
    authz.grant(conn, OBJ, "read", U)
    assert not authz.authorize(conn, U, None, OBJ, "use").allowed
    assert not authz.authorize(conn, U, None, OBJ, "discover").allowed


def test_mode_is_mandatory(conn, book):  # AT-16
    with pytest.raises(authz.AuthzError, match="E9"):
        authz.grant(conn, OBJ, "write", U)


def test_agent_instruction_needs_activation(conn, book):  # AT-12
    authz.grant(conn, OBJ, "read", U)
    authz.delegate(conn, delegator=U, delegate_to=A, obj=OBJ, mode="read", expires_at=soon())
    agent = Actor(A, on_behalf_of=U)
    with pytest.raises(Denied, match="activate"):
        gate.deliver_file(conn, agent, BOOK, book, SKILL)
    assert gate.deliver_file(conn, Actor(U), BOOK, book, SKILL)  # a person may read it as reference

    authz.grant(conn, OBJ, "activate", U)
    authz.delegate(conn, delegator=U, delegate_to=A, obj=OBJ, mode="activate", expires_at=soon())
    agent = Actor(A, on_behalf_of=U)
    assert gate.deliver_file(conn, agent, BOOK, book, SKILL)
    assert [(e[0], e[1]) for e in events(conn, agent.correlation_id)] == [("read", True), ("activate", True)]


@pytest.mark.parametrize("entry", [
    {"path": "a.md", "okf_type": "Skill"}, {"path": "a.md", "okf_type": " agent_card "},
    {"path": "a.md", "okf_type": "SYSTEM-PROMPT"}, {"path": "x/agents.md", "okf_type": None},
    {"path": "Claude.MD", "okf_type": "reference"}, {"path": "AGENTS.md.hostile", "okf_type": None},
    {"path": "docs/CLAUDE.local.md", "okf_type": None}, {"path": "SKILL.md.bak", "okf_type": None},
    {"path": ".claude/agents/denetci.md", "okf_type": None}, {"path": ".claude/commands/yayinla.md", "okf_type": None},
    {"path": ".claude/rules/kurallar.md", "okf_type": "reference"}, {"path": ".claude/hooks/onay.sh", "okf_type": None},
    {"path": ".claude/skills/learned/ders.md", "okf_type": None}, {"path": "alt/.cursor/rules/stil.md", "okf_type": None},
    {"path": "kurallar/stil.mdc", "okf_type": None}, {"path": ".github/copilot-instructions.md", "okf_type": None},
    {"path": "py.instructions.md", "okf_type": None}, {"path": "gozden.prompt.md", "okf_type": None},
    {"path": ".agents/plan.md", "okf_type": None}, {"path": ".codex/prompts/p.md", "okf_type": None},
])
def test_instruction_spelling_variants_are_caught(entry):
    assert gate.is_instruction(entry)


@pytest.mark.parametrize("path", ["politika/veri.md", "skills/matris.md", "commands/liste.md", "agents-overview.md",
                                  "docs/agents/tarih.md"])
def test_reference_is_not_an_instruction(path):
    assert not gate.is_instruction({"path": path, "okf_type": "policy"})


def test_everything_in_a_skill_folder_is_an_instruction():  # references/, scripts/, assets of a skill
    skills = agentfiles.skill_dirs(["araclar/ozet/SKILL.md", "araclar/ozet/scripts/calistir.py", "notlar.md"])
    for path in ("araclar/ozet/scripts/calistir.py", "araclar/ozet/references/kaynak.md"):
        assert gate.is_instruction({"path": path, "okf_type": None}, skills)
    assert not gate.is_instruction({"path": "araclar/diger.md", "okf_type": None}, skills)
    assert not gate.is_instruction({"path": "notlar.md", "okf_type": None}, skills)


def test_claude_agent_file_is_ingested_as_an_instruction_and_needs_activate(conn, okf_dir):  # G5, AT-12
    for rel, text in ((".claude/agents/denetci.md", "Kayıtları denetle ve raporla.\n"),
                      ("araclar/ozet/SKILL.md", "Özetle.\n"), ("araclar/ozet/scripts/calistir.sh", "echo kayıt\n")):
        (okf_dir / rel).parent.mkdir(parents=True, exist_ok=True)
        (okf_dir / rel).write_text(text, encoding="utf-8")
    r = catalog.publish(conn, book=BOOK, title=BOOK, files=read_source(okf_dir),
                        policy=make_policy(sensitivity="normal", egress="local_only", protection="standard"),
                        profile=profiles.spec("chunked"))
    flags = dict(conn.execute("SELECT DISTINCT path, instruction FROM chunk WHERE book = %s", (BOOK,)).fetchall())
    assert flags[".claude/agents/denetci.md"] and flags["araclar/ozet/scripts/calistir.sh"]
    assert not flags["politika/veri-saklama.md"]
    authz.grant(conn, OBJ, "read", U)
    authz.delegate(conn, delegator=U, delegate_to=A, obj=OBJ, mode="read", expires_at=soon())
    agent = Actor(A, on_behalf_of=U)
    for path in (".claude/agents/denetci.md", "araclar/ozet/scripts/calistir.sh"):
        assert gate.deliver_file(conn, Actor(U), BOOK, r.content_id, path)  # a person reads it as reference
        with pytest.raises(Denied, match="activate"):
            gate.deliver_file(conn, agent, BOOK, r.content_id, path)
    assert not {".claude/agents/denetci.md", "araclar/ozet/scripts/calistir.sh"} & {
        h.citation.path for h in search.search(conn, agent, "kayıt denetle", k=50)}
    authz.grant(conn, OBJ, "activate", U)
    authz.delegate(conn, delegator=U, delegate_to=A, obj=OBJ, mode="activate", expires_at=soon())
    agent = Actor(A, on_behalf_of=U)
    assert gate.deliver_file(conn, agent, BOOK, r.content_id, ".claude/agents/denetci.md")
    assert ".claude/agents/denetci.md" in {h.citation.path for h in search.search(conn, agent, "kayıt denetle", k=50)}


def test_unknown_path_is_denied_before_existence_is_revealed(conn, book):
    with pytest.raises(Denied):
        gate.deliver_file(conn, Actor(U), BOOK, book, "yok.md")


# --- Astra review #1: races across sessions, expiry inside a transaction, impersonation, CRLF, policy log ----

def _revoke_during_fetch(monkeypatch, action):
    real_read = catalog.read_file

    def read_then_act(*args):
        data = real_read(*args)
        action()  # committed by another session after the first decision, before delivery
        return data
    monkeypatch.setattr(catalog, "read_file", read_then_act)


def test_delegation_revoked_by_another_session_stops_delivery(conn, conn2, book, monkeypatch):  # AT-04
    authz.grant(conn, OBJ, "read", U)
    did = authz.delegate(conn, delegator=U, delegate_to=A, obj=OBJ, mode="read", expires_at=soon())
    _revoke_during_fetch(monkeypatch, lambda: authz.revoke_delegation(conn2, did))
    with pytest.raises(Denied, match="revoked before delivery"):
        gate.deliver_file(conn, Actor(A, on_behalf_of=U), BOOK, book, DOC)


def test_delegator_right_revoked_by_another_session_stops_delivery(conn, conn2, book, monkeypatch):  # AT-05
    authz.grant(conn, OBJ, "read", f"{ROLE}#member")
    authz.add_member(conn, ROLE, U)
    authz.delegate(conn, delegator=U, delegate_to=A, obj=OBJ, mode="read", expires_at=soon())
    _revoke_during_fetch(monkeypatch, lambda: authz.revoke(conn2, ROLE, "member", U))
    with pytest.raises(Denied, match="revoked before delivery"):
        gate.deliver_file(conn, Actor(A, on_behalf_of=U), BOOK, book, DOC)


def test_activation_revoked_in_flight_stops_instruction(conn, conn2, book, monkeypatch):  # AT-12
    for mode in ("read", "activate"):
        authz.grant(conn, OBJ, mode, A)  # direct agent grants, no delegation
    _revoke_during_fetch(monkeypatch, lambda: authz.revoke(conn2, OBJ, "activate", A))
    with pytest.raises(Denied, match="activate on book:kitap: revoked before delivery"):
        gate.deliver_file(conn, Actor(A), BOOK, book, SKILL)


def test_direct_agent_grant_still_needs_activate_for_instructions(conn, book):  # AT-12
    authz.grant(conn, OBJ, "read", A)
    assert gate.deliver_file(conn, Actor(A), BOOK, book, DOC)
    with pytest.raises(Denied, match="activate"):
        gate.deliver_file(conn, Actor(A), BOOK, book, SKILL)


def test_expiry_is_wall_clock_even_inside_a_transaction(conn, book):  # AT-06
    import time
    authz.grant(conn, OBJ, "read", U)
    did = authz.delegate(conn, delegator=U, delegate_to=A, obj=OBJ, mode="read", expires_at=soon())
    with conn.transaction():
        conn.execute("UPDATE delegation SET expires_at = clock_timestamp() + interval '300 milliseconds' "
                     "WHERE id = %s", (did,))
        assert authz.authorize(conn, A, U, OBJ, "read").allowed
        time.sleep(0.4)
        assert not authz.authorize(conn, A, U, OBJ, "read").allowed


def test_agent_cannot_borrow_another_users_rights(conn, book):  # AT-06 impersonation
    other = "user:mehmet"
    authz.grant(conn, OBJ, "read", U)
    authz.grant(conn, OBJ, "read", other)
    authz.delegate(conn, delegator=U, delegate_to=A, obj=OBJ, mode="read", expires_at=soon())
    d = authz.authorize(conn, A, other, OBJ, "read")
    assert not d.allowed and d.reason == "no live delegation"


def test_crlf_and_bom_frontmatter_still_marks_instruction(conn, okf_dir):  # AT-12 bypass
    (okf_dir / "crlf.md").write_bytes(b"---\r\ntype: skill\r\n---\r\nYap.\r\n")
    (okf_dir / "bom.md").write_bytes("﻿---\ntype: prompt\n---\nYap.\n".encode())
    r = catalog.publish(conn, book="crlf", title="crlf", files=read_source(okf_dir),
                        policy=make_policy(sensitivity="normal", egress="local_only", protection="standard"),
                        profile=profiles.spec("whole"))
    authz.grant(conn, "book:crlf", "read", A)
    for path in ("crlf.md", "bom.md"):
        with pytest.raises(Denied, match="activate"):
            gate.deliver_file(conn, Actor(A), "crlf", r.content_id, path)
    assert catalog.read_file(conn, "crlf", r.content_id, "crlf.md") == b"---\r\ntype: skill\r\n---\r\nYap.\r\n"


def test_access_log_records_policy_in_force_at_delivery(conn, conn2, book, okf_dir, monkeypatch):
    authz.grant(conn, OBJ, "read", U)
    restricted = make_policy(sensitivity="restricted", egress="local_only", protection="standard")

    def repolicy():
        catalog.publish(conn2, book=BOOK, title=BOOK, files=read_source(okf_dir), policy=restricted,
                        profile=profiles.spec("whole"))
    before = catalog.current_policy(conn, BOOK)
    _revoke_during_fetch(monkeypatch, repolicy)
    actor = Actor(U)
    gate.deliver_file(conn, actor, BOOK, book, DOC)
    logged = events(conn, actor.correlation_id)[0][5]
    assert logged == catalog.current_policy(conn, BOOK) != before


# --- guard_many (docs/24 §6.1): one decision for several books around a write -----------------------------------

OTHER = "book:ikinci"


@pytest.fixture
def two_books(conn, book, okf_dir):
    catalog.publish(conn, book="ikinci", title="ikinci", files=read_source(okf_dir),
                    policy=make_policy(sensitivity="normal", egress="local_only", protection="standard"),
                    profile=profiles.spec("whole"))
    conn.execute("CREATE TABLE probe_write (n integer)")
    authz.grant(conn, OBJ, "read", U)
    authz.grant(conn, OTHER, "read", U)
    return conn


def _writes(conn):
    return conn.execute("SELECT count(*) FROM probe_write").fetchone()[0]


def _logged(conn, actor):
    return conn.execute("SELECT object, mode, allowed, reason, items FROM access_event WHERE correlation_id = %s "
                        "ORDER BY id", (actor.correlation_id,)).fetchall()


def test_guard_many_decides_every_book_and_logs_each(two_books):
    conn = two_books
    actor = Actor(U)
    out = gate.guard_many(conn, actor, {OBJ: {"read"}, OTHER: {"read"}},
                          lambda: conn.execute("INSERT INTO probe_write VALUES (1) RETURNING n").fetchone()[0],
                          action="propose", items={OBJ: ["a"]})
    assert out == 1 and _writes(conn) == 1
    assert [(o, m, ok, items) for o, m, ok, _r, items in _logged(conn, actor)] == \
        [(OTHER, "read", True, None), (OBJ, "read", True, ["a"])]


def test_guard_many_refuses_before_the_work_when_one_book_is_missing(two_books):
    conn = two_books
    authz.revoke(conn, OTHER, "read", U)
    actor, ran = Actor(U), []
    with pytest.raises(Denied, match="no current right on book:ikinci"):
        gate.guard_many(conn, actor, {OBJ: {"read"}, OTHER: {"read"}}, lambda: ran.append(1), action="propose")
    assert ran == [] and _writes(conn) == 0
    assert [(o, ok) for o, _m, ok, _r, _i in _logged(conn, actor)] == [(OTHER, False)]


def test_guard_many_loss_on_the_final_decision_rolls_back_and_logs(two_books, conn2):
    conn = two_books
    did = authz.delegate(conn, delegator=U, delegate_to=A, obj=OTHER, mode="read", expires_at=soon())
    authz.delegate(conn, delegator=U, delegate_to=A, obj=OBJ, mode="read", expires_at=soon())

    def write_then_lose_one_book():
        conn.execute("INSERT INTO probe_write VALUES (1)")
        authz.revoke_delegation(conn2, did)  # committed by another session after the first decision
    actor = Actor(A, on_behalf_of=U)
    with pytest.raises(Denied, match="revoked before delivery"):
        gate.guard_many(conn, actor, {OBJ: {"read"}, OTHER: {"read"}}, write_then_lose_one_book, action="propose")
    assert _writes(conn) == 0                                              # the write was rolled back
    logged = _logged(conn, actor)                                          # the refusal survived the rollback
    assert [(o, ok) for o, _m, ok, _r, _i in logged] == [(OTHER, False)]
    assert logged[0][3].startswith("revoked before delivery")


def test_guard_many_needs_at_least_one_book(conn):
    with pytest.raises(ValueError):
        gate.guard_many(conn, Actor(U), {}, lambda: None, action="propose")


def test_actor_channel_is_checked():
    assert Actor(U).channel == "cli" and Actor(U).client_id is None
    with pytest.raises(ValueError):
        Actor(U, channel="browser")
