"""AT-15: runbook feedback is bound to the exact content version; a new version does not inherit it."""
import pytest

from kutuphane import authz, catalog, feedback, profiles
from kutuphane.gate import Actor, Denied, NotFound
from kutuphane.policy import make_policy
from kutuphane.source import read_source

U = "user:ayse"
RUNBOOK = "runbook/yedek-geri-yukleme.md"


def publish(conn, okf_dir):
    return catalog.publish(conn, book="kitap", title="kitap", files=read_source(okf_dir),
                           policy=make_policy(sensitivity="normal", egress="local_only", protection="standard"),
                           profile=profiles.spec("chunked"))


def test_feedback_is_per_version(conn, okf_dir):
    v1 = publish(conn, okf_dir)
    authz.grant(conn, "book:kitap", "read", U)
    for outcome, note in (("worked", None), ("changed", "3. adımda komut değişti")):
        feedback.record(conn, Actor(U), book="kitap", content_id=v1.content_id, path=RUNBOOK, outcome=outcome,
                        tested_on="postgres-17", note=note)
    rb = okf_dir / RUNBOOK
    rb.write_text(rb.read_text(encoding="utf-8").replace("Geri yükle", "pg_restore ile geri yükle"), encoding="utf-8")
    v2 = publish(conn, okf_dir)
    old = feedback.for_version(conn, Actor(U), book="kitap", content_id=v1.content_id, path=RUNBOOK)
    new = feedback.for_version(conn, Actor(U), book="kitap", content_id=v2.content_id, path=RUNBOOK)
    assert [(f["outcome"], f["tested_on"], f["principal"]) for f in old] == [
        ("worked", "postgres-17", U), ("changed", "postgres-17", U)]
    assert new == []


def test_feedback_needs_read_and_a_real_file(conn, okf_dir):
    v1 = publish(conn, okf_dir)
    with pytest.raises(Denied):
        feedback.record(conn, Actor(U), book="kitap", content_id=v1.content_id, path=RUNBOOK, outcome="worked")
    authz.grant(conn, "book:kitap", "read", U)
    with pytest.raises(NotFound):
        feedback.record(conn, Actor(U), book="kitap", content_id=v1.content_id, path="yok.md", outcome="worked")


@pytest.mark.parametrize("kwargs", [dict(outcome="maybe"), dict(outcome="worked", tested_on=" "),
                                    dict(outcome="worked", note="x" * 2001)])
def test_feedback_input_is_validated(conn, okf_dir, kwargs):
    v1 = publish(conn, okf_dir)
    with pytest.raises(ValueError):
        feedback.record(conn, Actor(U), book="kitap", content_id=v1.content_id, path=RUNBOOK, **kwargs)


def test_feedback_written_while_rights_vanish_is_rolled_back(conn, conn2, okf_dir, monkeypatch):  # security review
    from kutuphane import authz as az
    v1 = publish(conn, okf_dir)
    az.grant(conn, "book:kitap", "read", U)
    real = az.decide
    calls = []

    def decide_then_revoke(*args):
        calls.append(1)
        if len(calls) == 2:  # the final decision, after the insert ran inside the transaction
            az.revoke(conn2, "book:kitap", "read", U)
        return real(*args)
    monkeypatch.setattr(az, "decide", decide_then_revoke)
    with pytest.raises(Denied, match="revoked before delivery"):
        feedback.record(conn, Actor(U), book="kitap", content_id=v1.content_id, path=RUNBOOK, outcome="worked")
    assert conn.execute("SELECT count(*) FROM runbook_feedback").fetchone()[0] == 0
    (allowed,) = conn.execute("SELECT allowed FROM access_event WHERE action = 'feedback'").fetchone()
    assert allowed is False  # the refusal itself survived the rollback
