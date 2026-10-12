"""M1d: profiles (AT-02), pre-filtered search (AT-04 search path), citations across versions (AT-07)."""
from datetime import datetime, timedelta, timezone

import pytest

from kutuphane import authz, catalog, ids, profiles, search
from kutuphane.gate import Actor, Denied
from kutuphane.policy import make_policy
from kutuphane.source import read_file, read_source

U, A = "user:ayse", "agent:kobra-7"
POLICY = make_policy(sensitivity="normal", egress="local_only", protection="standard")
LONG = "\n\n".join([
    "---\ntype: reference\n---",
    "# Birinci bölüm",
    "Paragraf bir. " * 40,
    "Paragraf iki. " * 40,
    "## İkinci bölüm",
    "Kısa paragraf.",
]) + "\n"


def publish(conn, path, book="kitap", profile="chunked"):
    return catalog.publish(conn, book=book, title=book, files=read_source(path), policy=POLICY,
                           profile=profiles.spec(profile))


def soon():
    return datetime.now(timezone.utc) + timedelta(hours=8)


def test_chunked_profile_cuts_at_headings_and_size():  # AT-02
    f = read_file("uzun.md", LONG.encode())
    chunks = profiles.split(profiles.spec("chunked"), f)
    full = LONG
    assert all(c.text == full[c.start:c.end] for c in chunks)
    assert all(a.end <= b.start for a, b in zip(chunks, chunks[1:]))           # no overlap, in order
    assert [c.text.splitlines()[0] for c in chunks if c.text.startswith("#")] == ["# Birinci bölüm",
                                                                                   "## İkinci bölüm"]
    assert all(len(c.text) <= profiles.TARGET_CHARS or "\n\n" not in c.text for c in chunks)
    assert "type: reference" not in "".join(c.text for c in chunks)            # frontmatter is not a passage


def test_whole_profile_is_the_full_text():  # AT-02
    f = read_file("uzun.md", LONG.encode())
    (only,) = profiles.split(profiles.spec("whole"), f)
    assert only.text == LONG and (only.start, only.end) == (0, len(LONG))


def test_chunker_version_changes_profile_id_not_content_id(monkeypatch):  # AT-02
    before = ids.profile_id(profiles.spec("chunked"))
    monkeypatch.setattr(profiles, "CHUNKER_VERSION", profiles.CHUNKER_VERSION + 1)
    assert ids.profile_id(profiles.spec("chunked")) != before


def test_search_finds_stemmed_turkish_and_cites(conn, okf_dir):
    r = publish(conn, okf_dir)
    authz.grant(conn, "book:kitap", "read", U)
    hits = search.search(conn, Actor(U), "kayıtlar ne kadar saklanır?")
    assert hits and hits[0].citation.path == "politika/veri-saklama.md"
    assert (hits[0].citation.content_id, hits[0].citation.profile_id) == (r.content_id, r.profile_id)


def test_search_never_shows_unauthorized_books(conn, okf_dir, tmp_path):  # AT-04 search path
    publish(conn, okf_dir, book="acik")
    publish(conn, okf_dir, book="gizli")
    authz.grant(conn, "book:acik", "read", U)
    hits = search.search(conn, Actor(U), "kayıtlar saklanır", k=50)
    assert hits and {h.citation.book for h in hits} == {"acik"}
    assert search.search(conn, Actor("user:mehmet"), "kayıtlar saklanır") == []


def test_agent_search_needs_delegation_and_activate_for_instructions(conn, okf_dir):  # AT-04, AT-12
    (okf_dir / "skill.md").write_text("---\ntype: skill\n---\nKayıtları özetle ve sakla.\n", encoding="utf-8")
    publish(conn, okf_dir)
    authz.grant(conn, "book:kitap", "read", U)
    agent = Actor(A, on_behalf_of=U)
    assert search.search(conn, agent, "kayıt") == []                            # no delegation yet
    did = authz.delegate(conn, delegator=U, delegate_to=A, obj="book:kitap", mode="read", expires_at=soon())
    assert "skill.md" not in {h.citation.path for h in search.search(conn, agent, "kayıt", k=50)}
    assert "skill.md" in {h.citation.path for h in search.search(conn, Actor(U), "kayıt", k=50)}
    authz.grant(conn, "book:kitap", "activate", U)
    authz.delegate(conn, delegator=U, delegate_to=A, obj="book:kitap", mode="activate", expires_at=soon())
    assert "skill.md" in {h.citation.path for h in search.search(conn, agent, "kayıt", k=50)}
    authz.revoke_delegation(conn, did)
    assert search.search(conn, agent, "kayıt") == []


def test_revocation_between_prefilter_and_delivery_drops_hits(conn, conn2, okf_dir, monkeypatch):  # AT-04
    publish(conn, okf_dir)
    authz.grant(conn, "book:kitap", "read", U)
    real = authz.allowed_objects

    def prefilter_then_revoke(*args):
        out = real(*args)
        authz.revoke(conn2, "book:kitap", "read", U)
        return out
    monkeypatch.setattr(authz, "allowed_objects", prefilter_then_revoke)
    actor = Actor(U)
    assert search.search(conn, actor, "kayıtlar") == []
    (allowed,) = conn.execute("SELECT allowed FROM access_event WHERE correlation_id = %s AND action = 'search'",
                              (actor.correlation_id,)).fetchone()
    assert allowed is False


def test_old_citation_opens_old_passage_with_current_rights(conn, okf_dir):  # AT-07
    publish(conn, okf_dir)
    authz.grant(conn, "book:kitap", "read", U)
    (hit, *_) = search.search(conn, Actor(U), "kayıtlar saklanır")
    target = okf_dir / "politika" / "veri-saklama.md"
    target.write_text(target.read_text(encoding="utf-8").replace("iki yıl", "üç yıl"), encoding="utf-8")
    publish(conn, okf_dir)
    assert "üç yıl" in search.search(conn, Actor(U), "kayıtlar saklanır")[0].text
    reopened = search.open_citation(conn, Actor(U), hit.citation)
    assert reopened.text == hit.text and "iki yıl" in reopened.text
    authz.revoke(conn, "book:kitap", "read", U)
    with pytest.raises(Denied):
        search.open_citation(conn, Actor(U), hit.citation)


def test_search_input_is_bounded(conn):
    for bad in ("", "  ", "x" * (search.MAX_QUERY_CHARS + 1)):
        with pytest.raises(ValueError):
            search.search(conn, Actor(U), bad)
    with pytest.raises(ValueError):
        search.search(conn, Actor(U), "kayıt", k=search.MAX_K + 1)
