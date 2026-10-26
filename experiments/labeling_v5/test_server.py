"""The labelling v5 page server: auth and CSRF (Astra reviews #10/#11), the allowed answers per group, judge first
then reveal (D67), mixed batches, and no gold or held-out mark sent to the page.
Run: python -m pytest experiments/labeling_v5/test_server.py"""
import http.client
import json
import random
import sys
import threading
from collections import Counter
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import server  # noqa: E402

TOKEN = "t" * 24
SECRET = "GOLD-ANSWER-MARKER"
GROUPS = list(server.GROUPS)


def human(n):
    g = GROUPS[n % 4]
    return {"id": f"h-{n:03d}", "set": "human", "group": g, "source": f"org/src{n % 3}", "family": f"fam{n // 6}",
            "operation": "search" if n % 2 else "model-answer", "questions": ["Q12"], "why_selected": f"case {n}",
            "selection_stratum": "random",
            "files": [{"path": "doc.md", "sha256": "0" * 64, "bytes": 9, "copy": True, "local_path": "doc.md",
                       "license_item": "MIT"},
                      {"path": "closed.md", "sha256": "1" * 64, "bytes": 9, "copy": False,
                       "license_item": "unknown"}],
            "evidence": {"status": "Status: Final", "reviews": [{"user": "ayse", "state": "APPROVED"}]},
            "statements": []}


HUMAN = [human(n) for n in range(40)]
SCEN = [{"id": f"sc-core-{b:02d}-{v}", "set": "scenario", "group": "supersession", "operation": "search",
         "family": f"scenario/core:sc-core-{b:02d}", "base_id": f"sc-core-{b:02d}", "variant": v, "heldout": b == 0,
         "why_selected": "x", "files": [{"path": "policy.yaml", "role": "policy", "copy": True,
                                          "local_path": "policy.yaml", "sha256": "2" * 64, "bytes": 3}],
         "statements": [{"kind": "status", "issuer": "k1", "body": {"status": "withdrawn"}}],
         "evidence": {"request": {"operation": "search", "actor": "u"}, "policy": ["p"], "trust": {"k1": "full"},
                      "evaluation_time": "2026-10-26T00:00:00Z"}}
        for b in range(3) for v in ("base", "consequential", "irrelevant")]


@pytest.fixture
def data(tmp_path):
    for s, slice_, cases in (("human", "pool", HUMAN), ("scenario", "core", SCEN)):
        (tmp_path / s).mkdir()
        (tmp_path / s / f"{slice_}.cases.jsonl").write_text("".join(json.dumps(c) + "\n" for c in cases))
        (tmp_path / s / f"{slice_}.gold.jsonl").write_text("".join(
            json.dumps({"id": c["id"], "gold": {"x": SECRET}}) + "\n" for c in cases))
        for c in cases:
            d = tmp_path / s / slice_ / c["id"]
            d.mkdir(parents=True)
            for f in c["files"]:
                if f["copy"]:
                    (d / f["local_path"]).write_text("text\u200b here\n")
    (tmp_path / "secret.txt").write_text(SECRET)
    (tmp_path / "proposals.human.jsonl").write_text("".join(json.dumps(
        {"id": c["id"], "set": "human", "group": c["group"], "proposer_version": "rules-v5.0",
         "proposals": {server.GROUPS[c["group"]]["field"]: {"value": server.GROUPS[c["group"]]["options"][0],
                                                            "confidence": "high", "evidence": "RULE-EVIDENCE"},
                       "license": {"value": "MIT", "confidence": "high", "evidence": "x"}}}) + "\n" for c in HUMAN))
    (tmp_path / "proposals_llm.human.jsonl").write_text("".join(json.dumps(
        {"id": c["id"], "proposer_version": "llm-v5.0",
         "p": {server.GROUPS[c["group"]]["field"]: server.GROUPS[c["group"]]["options"][1],
               "review_evidence": "QWEN-EVIDENCE"}}) + "\n" for c in HUMAN))
    (tmp_path / "proposals.scenario.jsonl").write_text("".join(json.dumps(
        {"id": c["id"], "proposals": {"decision": {"value": "deny", "evidence": "SCENARIO-SUGGESTION"}}}) + "\n"
        for c in SCEN))
    return tmp_path


@pytest.fixture
def srv(data):
    store = server.Store(data)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.make_handler(store, TOKEN, b"<html>shell</html>"))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield store, httpd.server_address[1]
    httpd.shutdown()


def call(port, method, path, body=None, headers=None):
    conn = http.client.HTTPConnection("127.0.0.1", port)
    conn.request(method, path, body=body, headers=headers or {})
    r = conn.getresponse()
    out = r.status, dict(r.getheaders()), r.read()
    conn.close()
    return out


def get(port, path):
    status, _, raw = call(port, "GET", path, headers={"X-Label-Token": TOKEN})
    return status, json.loads(raw)


def post(port, body, ctype="application/json", origin=None, auth=True):
    headers = {"Content-Type": ctype, "Origin": origin or f"http://127.0.0.1:{port}"}
    if auth:
        headers["X-Label-Token"] = TOKEN
    status, _, raw = call(port, "POST", "/api/label", json.dumps(body).encode(), headers)
    return status, json.loads(raw)


def case_of(group):
    return next(c["id"] for c in HUMAN if c["group"] == group)


def first(cid, stage="first", **answer):
    return {"id": cid, "stage": stage, "answer": answer, "ms": 1200}


def saved(data):
    p = data / "labels.jsonl"
    return [json.loads(l) for l in p.read_text().splitlines()] if p.exists() else []


def test_page_shell_is_public_and_the_api_is_not(srv):
    _, port = srv
    status, headers, body = call(port, "GET", "/")
    assert status == 200 and body == b"<html>shell</html>" and "Set-Cookie" not in headers
    assert call(port, "GET", "/api/state")[0] == 401
    assert call(port, "GET", "/api/batches?set=human")[0] == 401
    assert call(port, "GET", "/api/case/h-000")[0] == 401
    assert call(port, "GET", "/api/state", headers={"X-Label-Token": TOKEN})[0] == 200
    status, headers, _ = call(port, "GET", f"/?t={TOKEN}")
    assert status == 200 and headers["Set-Cookie"].startswith(f"kl5={TOKEN};")
    assert "HttpOnly" in headers["Set-Cookie"] and "SameSite=Lax" in headers["Set-Cookie"]
    assert call(port, "GET", "/api/state", headers={"Cookie": f"kl5={TOKEN}"})[0] == 200
    assert "Set-Cookie" not in call(port, "GET", "/?t=wrong-token-0000000000")[1]
    assert call(port, "GET", "/api/state", headers={"X-Label-Token": "wrong-token-0000000000"})[0] == 401


def test_label_post_must_be_json_from_the_own_origin(srv, data):
    _, port = srv
    body = first(case_of("personal-data"), personal_data="no")
    assert post(port, body, ctype="text/plain")[0] == 403
    assert post(port, body, origin="http://127.0.0.1:9999")[0] == 403          # another port of the same host
    assert post(port, body, origin="http://evil.example")[0] == 403
    status, _, _ = call(port, "POST", "/api/label", json.dumps(body).encode(),
                        {"Content-Type": "application/json", "X-Label-Token": TOKEN})  # no Origin
    assert status == 403
    assert post(port, body, auth=False)[0] == 401
    assert saved(data) == []
    assert post(port, body)[0] == 200


@pytest.mark.parametrize("group,good,bad", [
    ("review-evidence", {"review": "approval-only", "reviewed_by": "ayse"},
     [{"review": "safe"}, {"review": "substantive"}, {"personal_data": "no", "review": "unknown"},
      {"review": "unknown", "scope": "x"}, {"review": "unknown", "reviewed_by": 3}]),
    ("instruction-safety", {"activation_risk": "harmful", "evidence_pointer": "line 4"},
     [{"activation_risk": "allow"}, {"activation_risk": "deny"}, {"activation_risk": "safe", "activate": "allow"},
      {"evidence_pointer": "x"}]),
    ("normative-meaning", {"normative": "history", "scope": "all SIGs", "note": "n"},
     [{"normative": "accepted"}, {"normative": "binding", "scope": "x" * 301}, {"normative": "binding", "review": "substantive"}]),
    ("personal-data", {"personal_data": "synthetic"},
     [{"personal_data": "real"}, {"personal_data": "none"}, {"personal_data": "no", "note": "x" * 2001}, {}]),
])
def test_only_the_question_of_the_group_is_accepted(srv, data, group, good, bad):
    _, port = srv
    cid = case_of(group)
    for answer in bad:
        status, err = post(port, first(cid, **answer))
        assert status == 400, (answer, err)
    assert saved(data) == []
    assert post(port, first(cid, **good))[0] == 200
    rec = saved(data)[-1]
    assert rec["labels"] == good and rec["stage"] == "first" and rec["group"] == group and rec["ms"] == 1200


def test_bad_bodies_are_refused(srv, data):
    _, port = srv
    cid = case_of("personal-data")
    assert post(port, first("nope", personal_data="no"))[0] == 400
    assert post(port, first(cid, stage="answer", personal_data="no"))[0] == 400   # a scenario stage
    assert post(port, first(cid, stage="final", personal_data="no"))[0] == 400
    assert post(port, {"id": cid, "stage": "first", "answer": "no"})[0] == 400
    assert post(port, ["x"])[0] == 400
    status, _, _ = call(port, "POST", "/api/label", b"{", {"Content-Type": "application/json", "X-Label-Token": TOKEN,
                                                            "Origin": f"http://127.0.0.1:{port}"})
    assert status == 400
    assert saved(data) == []


def test_judge_first_then_reveal(srv, data):
    store, port = srv
    cid = case_of("review-evidence")
    status, got = get(port, f"/api/case/{cid}")
    raw = json.dumps(got)
    assert status == 200 and got["suggestions"] is None and got["first"] is None
    assert "RULE-EVIDENCE" not in raw and "QWEN-EVIDENCE" not in raw          # nothing of the proposers yet
    assert got["question"] == {"group": "review-evidence", "field": "review",
                               "options": ["substantive", "approval-only", "unknown"]}
    assert post(port, first(cid, stage="revision", review="unknown"))[0] == 409  # no revision before a first choice
    status, out = post(port, first(cid, review="unknown"))
    assert status == 200
    items = {(s["from"], s["field"]): s for s in out["suggestions"]["items"]}
    assert items[("rule", "review")]["value"] == "substantive" and items[("rule", "review")]["evidence"] == "RULE-EVIDENCE"
    assert items[("Qwen", "review")]["value"] == "approval-only" and items[("Qwen", "review")]["evidence"] == "QWEN-EVIDENCE"
    assert not any(s["field"] == "license" for s in out["suggestions"]["items"])  # only the group's fields
    assert post(port, first(cid, review="substantive", reviewed_by="x"))[0] == 409  # the first choice is final
    status, got = get(port, f"/api/case/{cid}")
    assert got["first"] == {"review": "unknown"} and got["suggestions"]["items"]
    assert post(port, first(cid, stage="revision", review="approval-only", reviewed_by="ayse"))[0] == 200
    assert post(port, first(cid, stage="revision", review="approval-only", reviewed_by="ayse"))[0] == 200  # confirm
    one, rev, confirm = saved(data)
    assert one["stage"] == "first" and not one["suggestions_seen"] and one["matches"] == {"rule": False, "Qwen": False}
    assert one["proposal_version"]["rule"] == "rules-v5.0" and one["proposal_version"]["llm"] == "llm-v5.0"
    assert rev["stage"] == "revision" and rev["suggestions_seen"] and rev["first_ts"] == one["ts"]
    assert rev["changed"] == ["review", "reviewed_by"] and rev["matches"] == {"rule": False, "Qwen": True}
    assert rev["correction_ms"] == rev["t_ms"] - one["t_ms"] >= 0
    assert confirm["changed"] == ["review", "reviewed_by"]                     # always against the first choice
    assert get(port, f"/api/case/{cid}")[1]["latest"] == {"review": "approval-only", "reviewed_by": "ayse"}
    reopened = server.Store(data)                                              # the record survives a restart
    assert reopened.first[cid]["labels"] == {"review": "unknown"} and reopened.status(cid) == "done"
    assert reopened.save(first(cid, stage="revision", review="unknown"))["ok"]


def test_scenarios_get_one_answer_and_no_suggestions(srv, data):
    _, port = srv
    cid = SCEN[0]["id"]
    status, got = get(port, f"/api/case/{cid}")
    raw = json.dumps(got)
    assert status == 200 and got["suggestions"] is None and "question" not in got
    assert "SCENARIO-SUGGESTION" not in raw
    assert "heldout" not in raw and "variant" not in got["case"] and "base_id" not in got["case"]  # held-out looks the same
    assert got["case"]["evidence"]["request"] == {"operation": "search", "actor": "u"}
    assert got["case"]["statements"][0]["issuer"] == "k1" and got["files"][0]["role"] == "policy"
    assert post(port, first(cid, stage="answer", decision="deny"))[0] == 400            # the reason is required
    assert post(port, first(cid, stage="answer", decision="allow", reason="r"))[0] == 400
    assert post(port, first(cid, stage="first", decision="deny", reason="r"))[0] == 400
    assert post(port, first(cid, stage="answer", decision="deny", reason="r", personal_data="no"))[0] == 400
    assert post(port, first(cid, stage="answer", decision="deny", reason="r", notices="x" * 1001))[0] == 400
    status, out = post(port, first(cid, stage="answer", decision="escalate", reason=" stale status ",
                                   notices="authority removed"))
    assert status == 200 and out == {"ok": True}
    rec = saved(data)[-1]
    assert rec["labels"] == {"decision": "escalate", "reason": "stale status", "notices": "authority removed"}
    assert "suggestions_seen" not in rec and "matches" not in rec
    assert post(port, first(cid, stage="answer", decision="deny", reason="again"))[0] == 200  # the latest counts
    assert get(port, f"/api/case/{cid}")[1]["latest"]["decision"] == "deny"


def test_no_gold_reaches_the_page(srv, data):
    _, port = srv
    seen = [get(port, "/api/state")[1], get(port, "/api/batches?set=human")[1], get(port, "/api/batches?set=scenario")[1]]
    for c in HUMAN + SCEN:
        seen.append(get(port, f"/api/case/{c['id']}")[1])
    for c in HUMAN:
        g = server.GROUPS[c["group"]]
        answer = {g["field"]: g["options"][-1]}
        seen.append(post(port, first(c["id"], **answer))[1])
    raw = json.dumps(seen)
    assert SECRET not in raw and "selection_stratum" not in raw and "random" not in raw


def test_files_are_shown_only_inside_the_case_folder(srv, data):
    store, port = srv
    got = get(port, "/api/case/h-000")[1]
    shown, closed = got["files"]
    assert shown["text"] == "text⟦U+200B⟧ here\n" and shown["hidden_chars"] == 1 and got["hidden_chars"] == 1
    assert closed["text"] is None and "reference and hash only" in closed["note"] and "local_path" not in closed
    store.cases["h-000"]["files"][0]["local_path"] = "../../../secret.txt"
    got = get(port, "/api/case/h-000")[1]
    assert got["files"][0]["text"] is None and got["files"][0]["note"] == "The copy is missing."
    assert get(port, "/api/case/..%2Fsecret.txt")[0] == 404
    assert get(port, "/api/batches?set=gold")[0] == 400


def check_batches(batches, cases):
    by_id = {c["id"]: c for c in cases}
    ids = [i for b in batches for i in b]
    assert sorted(ids) == sorted(by_id) and len(ids) == len(set(ids))     # every case exactly once
    for b in batches:
        assert len(b) <= server.BATCH
        assert max(Counter(server.family(by_id[i]) for i in b).values()) <= server.PER_FAMILY
    full = [b for b in batches if len(b) == server.BATCH]
    assert full
    groups = {by_id[i].get("group") for i in ids}
    for b in full:
        per_group = Counter(by_id[i]["group"] for i in b)
        assert len(per_group) == len(groups) or len(per_group) >= 3          # mixed groups
        assert max(per_group.values()) <= -(-server.BATCH // len(groups)) + 1


def test_batches_are_mixed_fixed_and_frozen(srv, data):
    store, port = srv
    check_batches(store.batches["human"], HUMAN)
    assert [len(b) for b in store.batches["human"]] == [10, 10, 10, 10]
    shuffled = HUMAN[:]
    random.Random(7).shuffle(shuffled)
    assert server.plan_batches(shuffled) == store.batches["human"]          # the input order does not matter
    sc = store.batches["scenario"]
    assert max(Counter(server.family(next(c for c in SCEN if c["id"] == i)) for i in sc[0]).values()) <= 2
    frozen = json.loads((data / "batches.human.json").read_text())
    assert frozen["batches"] == store.batches["human"] and frozen["seed"] == server.SEED
    listed = get(port, "/api/batches?set=human")[1]["batches"]
    assert [[c["id"] for c in b] for b in listed] == store.batches["human"]
    assert {c["status"] for b in listed for c in b} == {"todo"}
    # new cases arrive later: the frozen batches stay; the new ones form new batches at the end
    more = [human(n) for n in range(40, 52)]
    with (data / "human" / "pool.cases.jsonl").open("a") as f:
        f.write("".join(json.dumps(c) + "\n" for c in more))
    again = server.Store(data).batches["human"]
    assert again[:4] == store.batches["human"] and sorted(i for b in again[4:] for i in b) == [c["id"] for c in more]
    check_batches(again, HUMAN + more)


def test_one_family_alone_cannot_fill_a_batch():
    cases = [{"id": f"x{n}", "group": "personal-data", "family": "one"} for n in range(5)] + \
            [{"id": f"y{n}", "group": "review-evidence", "family": f"f{n}"} for n in range(3)]
    batches = server.plan_batches(cases)
    assert all(Counter(c[0] for c in b)["x"] <= 2 for b in batches)
    assert sorted(i for b in batches for i in b) == sorted(c["id"] for c in cases)


def test_state_counts_done_cases(srv, data):
    _, port = srv
    cid = case_of("personal-data")
    post(port, first(cid, personal_data="no"))
    state = get(port, "/api/state")[1]["sets"]
    assert state["human"] == {"total": 40, "done": 0, "batches": 4}           # a first choice alone is not done
    post(port, first(cid, stage="revision", personal_data="no"))
    post(port, first(SCEN[1]["id"], stage="answer", decision="permit", reason="ok"))
    state = get(port, "/api/state")[1]["sets"]
    # 3 bases of 3 variants, at most 2 variants of one base in a batch: 6 + 3
    assert state["human"]["done"] == 1 and state["scenario"] == {"total": 9, "done": 1, "batches": 2}


def test_unknown_groups_are_skipped(tmp_path):
    (tmp_path / "human").mkdir()
    (tmp_path / "human" / "x.cases.jsonl").write_text(json.dumps({"id": "a", "group": "licence"}) + "\n" +
                                                      json.dumps({"id": "../b", "group": "personal-data"}) + "\n")
    store = server.Store(tmp_path)
    assert store.cases == {} and len(store.skipped) == 2
