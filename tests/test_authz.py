"""M1b: AT-04 (file path), AT-05, AT-06, AT-12, AT-16 (grants, purpose)."""
from datetime import datetime, timedelta, timezone

import pytest

from kutuphane import authz, catalog, gate
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
                        profile=catalog.whole_profile())
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


def test_unknown_path_is_denied_before_existence_is_revealed(conn, book):
    with pytest.raises(Denied):
        gate.deliver_file(conn, Actor(U), BOOK, book, "yok.md")
