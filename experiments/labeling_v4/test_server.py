"""The labelling page server (Astra review #11): CSRF, server-side visibility, derived acceptance, family blindness,
the unauthenticated page shell. Run: python -m pytest experiments/labeling_v4/test_server.py"""
import hashlib
import http.client
import json
import os
import sys
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import server  # noqa: E402

TOKEN = "t" * 24


def item(iid, path, group=None, stratum="R", source="org/repo"):
    return {"id": iid, "stratum": stratum, "source": source, "ref": {"path": path}, "group": group,
            "format": "md", "bytes": 3, "license_item": "MIT"}


ITEMS = [item(f"R-d{d}-f{f}", f"d{d}/f{f}.md") for d in range(10) for f in range(3)] + \
        [item(f"A-g{g}-f{f}", f"skills/g{g}/f{f}.md", group=f"skills/g{g}", stratum="A") for g in range(10) for f in
         range(2)]


@pytest.fixture
def data(tmp_path):
    (tmp_path / "items").mkdir()
    for s in server.STRATA:
        (tmp_path / "items" / f"{s}.jsonl").write_text(
            "".join(json.dumps(i) + "\n" for i in ITEMS if i["stratum"] == s))
    (tmp_path / "proposals.jsonl").write_text("".join(json.dumps(
        {"id": i["id"], "proposals": {"origin": {"value": "model", "confidence": "high", "evidence": "x"},
                                      "license": {"value": "MIT", "confidence": "high", "evidence": "x"}}}) + "\n"
        for i in ITEMS))
    (tmp_path / "proposals_llm.jsonl").write_text("".join(json.dumps(
        {"id": i["id"], "p": {"origin": "human", "personal_data": "no", "instruction": "yes", "hostile": "yes",
                              "acceptance": "pending"}}) + "\n" for i in ITEMS))
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


def post(port, body, ctype="application/json", origin=None, auth=True):
    headers = {"Content-Type": ctype, "Origin": origin or f"http://127.0.0.1:{port}"}
    if auth:
        headers["X-Label-Token"] = TOKEN
    status, _, raw = call(port, "POST", "/api/label", json.dumps(body).encode(), headers)
    return status, json.loads(raw)


def sighted(store, stratum="R"):
    return next(i["id"] for i in ITEMS if i["stratum"] == stratum and not store.is_blind(i["id"]))


def label(iid, mode="basic", shown=None, kept=(), **labels):
    labels = {"kind": "note", "origin": "human", "instruction": "no", "personal_data": "no", **labels}
    return {"id": iid, "labels": labels, "mode": mode, "kept": list(kept),
            "shown": list(shown if shown is not None else labels)}


def saved(data):
    return [json.loads(l) for l in (data / "labels.jsonl").read_text().splitlines()]


def test_page_shell_is_public_and_the_api_is_not(srv):  # reload with sessionStorage only
    _, port = srv
    status, headers, body = call(port, "GET", "/")
    assert status == 200 and body == b"<html>shell</html>" and "Set-Cookie" not in headers
    assert call(port, "GET", "/api/state")[0] == 401
    assert call(port, "GET", "/api/item/R-d0-f0")[0] == 401
    assert call(port, "GET", "/api/state", headers={"X-Label-Token": TOKEN})[0] == 200
    status, headers, _ = call(port, "GET", f"/?t={TOKEN}")
    assert status == 200 and headers["Set-Cookie"].startswith(f"kl4={TOKEN};")
    assert call(port, "GET", "/api/state", headers={"Cookie": f"kl4={TOKEN}"})[0] == 200
    assert "Set-Cookie" not in call(port, "GET", "/?t=wrong-token-0000000000")[1]


def test_label_post_must_be_json_from_the_own_origin(srv, data):
    store, port = srv
    body = label(sighted(store))
    assert post(port, body, ctype="text/plain")[0] == 403
    assert post(port, body, origin="http://127.0.0.1:9999")[0] == 403          # another port of the same host
    assert post(port, body, origin="http://evil.example")[0] == 403
    status, _, _ = call(port, "POST", "/api/label", json.dumps(body).encode(),
                        {"Content-Type": "application/json", "X-Label-Token": TOKEN})  # no Origin
    assert status == 403
    assert post(port, body, auth=False)[0] == 401
    assert not (data / "labels.jsonl").exists()
    assert post(port, body) == (200, {"ok": True})


def test_fields_outside_the_visible_set_are_refused(srv, data):
    store, port = srv
    iid = sighted(store)
    review = label(iid, shown=[], reviewed_by="X", activate="allow", mandate="yes")
    assert post(port, review)[0] == 400                                         # Astra #11 example
    review["shown"] = list(review["labels"])
    status, err = post(port, review)
    assert status == 400 and "activate" in err["error"] and "mandate" in err["error"]
    assert post(port, label(iid, shown=["kind", "origin", "instruction"]))[0] == 400  # a label not shown
    no_required = label(iid)
    del no_required["labels"]["personal_data"]
    no_required["shown"].remove("personal_data")
    assert "required" in post(port, no_required)[1]["error"]
    assert post(port, label(iid, mode="secret"))[0] == 400
    assert post(port, label(iid, bogus="x"))[0] == 400
    assert post(port, label(iid, license_item="MIT"))[0] == 400                 # exception mode only
    assert post(port, label(iid, export="restricted", mode="exception"))[0] == 400  # all mode only
    assert post(port, label(iid, kept=["mandate"]))[0] == 400                    # kept needs a value
    assert not (data / "labels.jsonl").exists()
    assert post(port, label(iid, mode="exception", license_item="MIT"))[0] == 200
    assert post(port, label(iid, mode="all", export="restricted", mandate="yes"))[0] == 200
    assert post(port, label(iid, kind="decision", acceptance="withdrawn", valid_to="2027-01-01"))[0] == 200
    assert post(port, label(iid, origin="tool", software_agent="x 1"))[0] == 200
    assert post(port, label(iid, instruction="yes", activate="deny", kind="instruction", applies_to="*"))[0] == 200
    # kind changed from decision to note after acceptance was entered: kept, and recorded as such
    assert post(port, label(iid, acceptance="withdrawn", kept=["acceptance"]))[0] == 200
    recs = saved(data)
    assert recs[-1]["kept"] == ["acceptance"] and recs[-1]["labels"]["acceptance"] == "withdrawn"
    assert recs[-1]["mode"] == "basic" and "note" not in recs[-1]["labels"]


def test_accepted_proposals_are_derived_by_the_server(srv, data):
    store, port = srv
    iid = sighted(store)
    body = label(iid, origin="model", mode="exception", license_item="MIT", acceptance="pending",
                 instruction="yes", activate="deny", kind="decision", personal_data="no", inputs="a")
    body["accepted_proposals"] = ["mandate", "export", "made-up"]
    assert post(port, body)[0] == 200
    rec = saved(data)[-1]
    # rule: origin=model, license=MIT; Qwen: personal_data, instruction, acceptance, hostile=yes -> activate deny
    assert rec["accepted_proposals"] == ["acceptance", "activate", "instruction", "license_item", "origin",
                                         "personal_data"]
    assert rec["proposal_version"] == {
        "proposals": hashlib.sha256((data / "proposals.jsonl").read_bytes()).hexdigest(),
        "proposals_llm": hashlib.sha256((data / "proposals_llm.jsonl").read_bytes()).hexdigest()}
    assert post(port, label(iid, origin="assisted", reviewed_by="Ayşe", personal_data="yes",
                            instruction="no"))[0] == 200
    assert saved(data)[-1]["accepted_proposals"] == []
    with (data / "proposals_llm.jsonl").open("a") as f:  # the Qwen run goes on: a new version
        f.write(json.dumps({"id": "R-new", "p": {}}) + "\n")
    os.utime(data / "proposals_llm.jsonl", (1, 1))
    assert post(port, label(iid))[0] == 200
    assert saved(data)[-1]["proposal_version"]["proposals_llm"] == \
        hashlib.sha256((data / "proposals_llm.jsonl").read_bytes()).hexdigest()


def test_blindness_is_chosen_per_family(srv, data):
    store, port = srv
    for stratum, n in (("R", 30), ("A", 20)):
        fams = {}
        for i in ITEMS:
            if i["stratum"] == stratum:
                fams.setdefault(server.family(i), set()).add(store.is_blind(i["id"]))
        assert all(len(v) == 1 for v in fams.values())                       # one family, one exposure
        assert sum(store.is_blind(i["id"]) for i in ITEMS if i["stratum"] == stratum) == round(n * 0.3)
    assert server.family(ITEMS[0]) == "org/repo:d0" and server.family(ITEMS[30]) == "skills/g0"
    blind = next(i["id"] for i in ITEMS if store.is_blind(i["id"]))
    status, _, raw = call(port, "GET", f"/api/item/{blind}", headers={"X-Label-Token": TOKEN})
    got = json.loads(raw)
    assert status == 200 and got["blind"] and got["proposals"] == {} and got["llm"] is None
    body = label(blind, origin="model", inputs="x", personal_data="no")
    assert post(port, body)[0] == 200
    rec = saved(data)[-1]
    assert rec["blind"] and rec["family"] == server.family(store.items[blind]) and rec["accepted_proposals"] == []
    assert "needs_split" not in rec["labels"]                                  # missing stays missing
