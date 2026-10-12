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
