"""Security review #17 (docs/08): the regressions of findings 2 and 3 on curator slice R.

Curator web connects as its role, with the deploy grants (deploy/db-roles*.sql), as in a deployment; the owner (the
test) only sets up the data.
"""
import psycopg

from kutuphane import authz
from kutuphane.gate import Actor
from test_confirm import CONFIRM, _curator_url, _refused, _signed, act, person, propose, seq_of, shown  # noqa: F401
from test_curatorweb import H, WEB_ROLE, A, J, M, U, env, note  # noqa: F401  (env: a fixture)


# --- #2: only the confirmer replaces a live confirmation -----------------------------------------------------------

def test_another_person_cannot_replace_a_live_confirmation(env):
    r = propose(env, "Ayşe's own words.")
    c, auth = person(env)
    assert act(c, auth, {"action": "confirm", "ref": r["ref"], "claim": "human"}).status_code == 200
    authz.grant(env, f"book:{J}", "read", M)
    authz.grant(env, f"book:{J}", "curate", M)
    env.commit()
    cm, am = person(env, M)
    page = cm.get(f"/api/requests/{r['ref'].replace('@', '/')}").json()
    assert page["claims"] == [] and page["withdraw"] is None   # nothing offered over Ayşe's confirmation
    refused = act(cm, am, {"action": "confirm", "ref": r["ref"], "claim": "assisted"})
    assert refused.status_code == 403 and "only that person withdraws it" in refused.json()["error"]
    assert shown(env, r["ref"]) == ("human", A, U)
    # the database refuses it too, for the curator web role
    seq, nid = seq_of(env, r["ref"]), r["ref"].split("@")[1]
    write = env.execute("SELECT seq FROM write_record WHERE note_seq = %s", (seq,)).fetchone()[0]
    by_m = _signed(env, M, "confirm", {"item": {"ref": r["ref"], "id": nid, "write": write}, "claim": "assisted",
                                       "entered_by": A})
    env.commit()
    _refused(env, CONFIRM, (seq, J, nid, write, "assisted", A, M, by_m), psycopg.errors.RaiseException, WEB_ROLE)
    # after Ayşe withdraws, Mehmet may confirm
    assert act(c, auth, {"action": "withdraw", "ref": r["ref"]}).status_code == 200
    assert act(cm, am, {"action": "confirm", "ref": r["ref"], "claim": "assisted"}).status_code == 200
    assert shown(env, r["ref"]) == ("assisted", A, M)


def test_a_new_request_is_no_path_to_take_over_a_live_confirmation(env):
    text = "Words that Ayşe confirmed."
    r = propose(env, text)
    c, auth = person(env)
    assert act(c, auth, {"action": "confirm", "ref": r["ref"], "claim": "human"}).status_code == 200
    reader_agent = "agent:kobra-8"
    for mode in ("read", "propose"):
        authz.grant(env, f"book:{J}", mode, M)
        authz.delegate(env, delegator=M, delegate_to=reader_agent, obj=f"book:{J}", mode=mode,
                       expires_at=env.execute("SELECT now() + interval '1 hour'").fetchone()[0])
    env.commit()
    again = propose(env, text, actor=Actor(reader_agent, M, channel="mcp"))   # the same bytes, "human" for Mehmet
    assert again["ref"] == r["ref"] and again["origin_notice"] == "origin-claim-refused"
    cm, am = person(env, M)
    page = cm.get(f"/api/requests/{r['ref'].replace('@', '/')}").json()
    assert page["claims"] == []
    refused = act(cm, am, {"action": "confirm", "ref": r["ref"], "claim": "human"})
    assert refused.status_code == 403, refused.text
    assert shown(env, r["ref"]) == ("human", A, U)


# --- #3: the page and the act options check `read` before any lookup ---------------------------------------------

def test_a_person_without_read_gets_one_refusal_for_every_note_state(env):
    absent = f"{J}@nt_{'0' * 64}"
    plain = note(env, "A note with no request")
    requested = propose(env, "A note with an open request")["ref"]
    confirmed = propose(env, "A note with a live confirmation")["ref"]
    c, auth = person(env)
    assert act(c, auth, {"action": "confirm", "ref": confirmed, "claim": "human"}).status_code == 200
    env.commit()
    cm, _ = person(env, M)   # enrolled, no right on the book
    seen = set()
    for ref in (absent, plain, requested, confirmed):
        for r in (cm.get(f"/api/requests/{ref.replace('@', '/')}"),
                  cm.post("/api/act/options", json={"action": "confirm", "ref": ref, "claim": "assisted"}, headers=H),
                  cm.post("/api/act/options", json={"action": "withdraw", "ref": ref}, headers=H)):
            seen.add((r.status_code, r.json()["error"]))
    assert seen == {(403, f"{M} does not hold read on book:{J}")}
