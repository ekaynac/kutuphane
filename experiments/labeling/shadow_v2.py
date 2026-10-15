"""Shadow labelling for ontology v2 (D44): typed-decision models answer the labeller's questions through LLMDAP
`systemone` routes (#225). Nothing here is shown as a default; the page may show a non-blind document's shadow
answer next to the labeller's own choice.

Usage: KUTUPHANE_LLMDAP_URL=<llmdap> KUTUPHANE_LLMDAP_KEY=<Core subject key> python3 -I shadow_v2.py --route laya
       ... --route jev --model jev-latest   (hosted: ONLY documents the operator labelled `normal` + `cloud_ok`
                                             with no restricted section, and only after that label)
Answers are appended to data/shadow_v2/<route>.jsonl. Documents that already have an answer are skipped, so the
script can run again as labels arrive.
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import v2  # noqa: E402
from server import Store  # noqa: E402

PURPOSE = "shadow-labelling"
# Fail closed: only these routes keep content on this machine. Every other route is treated as hosted, so it
# gets only documents the operator labelled normal + cloud_ok (with no restricted section), after the label.
LOCAL_ROUTES = {"laya"}
DOC_CHARS, SECTION_CHARS = 4000, 3000


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args):
        return None  # a redirect would carry the key elsewhere


OPENER = urllib.request.build_opener(_NoRedirect)


def choice(instructions: str, options: dict) -> dict:
    return {"type": "choice", "instructions": instructions, "criteria": options}


def questions(store: Store) -> tuple[dict, dict]:
    q = store.taxonomy["questions"]
    desc = lambda spec: {k: f"{o['name']}: {o['desc']} {o.get('use', '')}".strip() for k, o in spec["options"].items()}
    doc = {"sensitivity": choice(q["sensitivity"]["instructions"], desc(q["sensitivity"])),
           "egress": choice(q["egress"]["instructions"], desc(q["egress"])),
           "root": choice("Which preset describes this whole document best?", v2.PRESETS)}
    section = {"preset": choice("Which preset describes this section of the document best?", v2.PRESETS)}
    return doc, section


def ask(url: str, key: str, route: str, model: str, state: str, qs: dict, extra: dict) -> dict:
    body = json.dumps({"state": state, "model": model, "questions": qs, **extra}).encode()
    req = urllib.request.Request(f"{url}/bridge/{route}/v1/systemone", data=body, method="POST", headers={
        "content-type": "application/json", "authorization": f"Bearer {key}", "x-llmdap-purpose": PURPOSE,
        "x-llmdap-correlation-id": f"shadow-{route}-{uuid.uuid4().hex[:16]}"})
    with OPENER.open(req, timeout=180) as resp:
        out = json.loads(resp.read())
    return {qid: {"choice": a["choice"], "p": round(a["probabilities"][a["choice"]], 3)}
            for qid, a in out["answers"].items()}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--route", required=True)
    ap.add_argument("--model", default="multilingual")
    ap.add_argument("--data", default=str(HERE / "data"))
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()
    url, key = os.environ["KUTUPHANE_LLMDAP_URL"].rstrip("/"), os.environ["KUTUPHANE_LLMDAP_KEY"]
    store = Store(Path(args.data))
    out_dir = store.data / "shadow_v2"
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / f"{args.route}.jsonl"
    done = {json.loads(line)["id"] for line in out_path.read_text().splitlines()} if out_path.exists() else set()
    hosted = args.route not in LOCAL_ROUTES
    allowed = None
    if hosted:  # operator decision 2026-10-15: a hosted model sees only normal + cloud_ok documents, after the label
        labels = store.latest(store.labels_v2_path)
        allowed = {i for i, r in labels.items() if r["values"]["sensitivity"] == "normal"
                   and r["values"]["egress"] == "cloud_ok" and not r["restricted"]}
    extra = {} if hosted else {"max_len": 1024}
    doc_q, sec_q = questions(store)
    todo = [i for i in store.order if i not in store.excluded and i not in done and (allowed is None or i in allowed)]
    if args.limit:
        todo = todo[:args.limit]
    for n, doc_id in enumerate(todo, 1):
        path = store.manifest[doc_id]["path"]
        doc = store.doc_v2(doc_id)
        full = store.full_text(doc_id)
        if doc is None or full is None:
            continue
        sections = v2.sections(path, full["text"], blind=False)["sections"]
        started = time.time()
        try:
            answer = {"doc": ask(url, key, args.route, args.model, f"Path: {path}\n\n{full['text'][:DOC_CHARS]}",
                                 doc_q, extra),
                      "sections": {str(s["i"]): ask(url, key, args.route, args.model,
                                                    f"Document: {path}\nSection: {s['heading']}\n\n"
                                                    f"{s['text'][:SECTION_CHARS]}", sec_q, extra)["preset"]
                                   for s in sections}}
        except (urllib.error.URLError, OSError, KeyError, ValueError) as exc:
            print(f"{doc_id}: failed ({type(exc).__name__}: {getattr(exc, 'code', '')})", file=sys.stderr)
            continue
        rec = {"id": doc_id, "route": args.route, "model": args.model, **answer,
               "seconds": round(time.time() - started, 1), "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
        with out_path.open("a") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        print(f"{n}/{len(todo)} {doc_id} {answer['doc']['root']['choice']} ({rec['seconds']} s)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
