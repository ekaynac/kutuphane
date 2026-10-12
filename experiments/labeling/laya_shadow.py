"""Laya shadow run over the labelling corpus (D44): offline, local weights, CPU, no network egress
after the one-time weight download. Predictions go to data/laya-shadow.jsonl and are never
served to the labelling page.

Usage: LAYA_THREADS=16 <laya-venv>/bin/python -I laya_shadow.py [--data DIR] [--batch 8]
"""
import argparse
import json
import os
import platform
import sys
import time
from pathlib import Path

os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")

import laya  # noqa: E402  (env must be set first)
from laya.revisions import PINNED_REVISIONS  # noqa: E402

HERE = Path(__file__).resolve().parent
MODEL_ID = "convaiinnovations/laya-multilingual"
MAX_LEN = 1024


def build_questions(taxonomy: dict) -> dict:
    return {
        key: {
            "type": "choice",
            "instructions": spec["instructions"],
            "criteria": {opt: f"{o['name']}: {o['desc']}" for opt, o in spec["options"].items()},
        }
        for key, spec in taxonomy["questions"].items()
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(HERE / "data"))
    ap.add_argument("--batch", type=int, default=8)
    args = ap.parse_args()
    data = Path(args.data)
    taxonomy = json.loads((HERE / "taxonomy.json").read_text())
    docs = json.loads((data / "docs.json").read_text())
    questions = build_questions(taxonomy)
    revision = PINNED_REVISIONS[MODEL_ID]

    t0 = time.time()
    agent = laya.load(MODEL_ID, device="cpu", revision=revision)
    load_s = time.time() - t0

    # The labeller sees path + excerpt first; give the model the same view.
    states = [{"path": d["path"], "text": d["excerpt"]} for d in docs]
    t1 = time.time()
    results = agent.predict_batch(states, questions, batch_size=args.batch, max_len=MAX_LEN, lang="tr")
    infer_s = time.time() - t1

    run = {
        "model": MODEL_ID, "revision": revision, "laya": laya.__version__, "device": "cpu",
        "threads": os.environ.get("LAYA_THREADS"), "machine": platform.machine(), "max_len": MAX_LEN,
        "taxonomy_version": taxonomy["version"], "docs": len(docs), "load_s": round(load_s, 1),
        "infer_s": round(infer_s, 1), "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }
    out = data / "laya-shadow.jsonl"
    with out.open("w") as f:
        f.write(json.dumps({"run": run}, ensure_ascii=False) + "\n")
        for d, r in zip(docs, results):
            answers = r.get("answers", r)
            f.write(json.dumps({"id": d["id"], "answers": {
                k: {"choice": a.get("choice"), "probabilities": a.get("probabilities"),
                    "confidence": a.get("confidence")} for k, a in answers.items() if k in questions
            }}, ensure_ascii=False) + "\n")
    print(json.dumps(run), file=sys.stderr)


if __name__ == "__main__":
    main()
