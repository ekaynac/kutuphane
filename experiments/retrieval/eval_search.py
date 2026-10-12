"""M0 baseline: the product's own search path (pre-filter, ranking, citations) on hand-checked Turkish legal QA.

Usage: KUTUPHANE_DSN=<eval db> python -I eval_search.py <corpus_dir> <qa_benchmark_gold.csv> [--k 10]
Publishes the corpus as one book in a dedicated evaluation database, grants an evaluation reader, then runs every
active gold question through `search.search` and reports recall@1/5/10 and MRR@10. A hit is relevant when it
contains the gold passage (normalized), so the score measures finding the right article, not wording.
"""
import argparse
import csv
import json
import re
import sys
import time
from pathlib import Path

from kutuphane import authz, catalog, db, profiles, search
from kutuphane.gate import Actor
from kutuphane.policy import make_policy
from kutuphane.source import read_source

csv.field_size_limit(sys.maxsize)
READER = "user:eval"
WINDOW = 80  # characters of the gold article body (after "Madde N-") that must appear in a relevant hit


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.casefold()).strip()


def gold_window(gold: str) -> str:
    """Gold passages carry section headings ("ÜÇÜNCÜ BÖLÜM ... Madde 6- ..."); compare the article body."""
    g = norm(gold)
    m = re.search(r"madde \S+?-\s*", g)
    return (g[m.end():] if m else g)[:WINDOW]


def relevant(hit_text: str, gold: str) -> bool:
    return gold_window(gold) in norm(hit_text)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("corpus")
    ap.add_argument("qa")
    ap.add_argument("--k", type=int, default=10)
    args = ap.parse_args()
    with db.connect() as conn:
        db.migrate(conn)
        pub = catalog.publish(conn, book="mevzuat", title="Mevzuat (değerlendirme)", files=read_source(Path(args.corpus)),
                              policy=make_policy(sensitivity="normal", egress="local_only", protection="standard"),
                              profile=profiles.spec("chunked"))
        authz.grant(conn, "book:mevzuat", "read", READER)
        questions = [r for r in csv.DictReader(open(args.qa, encoding="utf-8")) if r["is_active"] == "True"]
        corpus = norm(" ".join(f.data.decode() for f in read_source(Path(args.corpus))))
        answerable = [gold_window(q["context"]) in corpus for q in questions]  # gold text exists in our corpus
        ranks, started = [], time.time()
        for q in questions:
            hits = search.search(conn, Actor(READER), q["soru"][:search.MAX_QUERY_CHARS], k=args.k)
            rank = next((i for i, h in enumerate(hits, 1) if relevant(h.text, q["context"])), None)
            ranks.append(rank)
        elapsed = time.time() - started
    def metrics(sel):
        n = len(sel)
        return {"questions": n,
                **{f"recall@{c}": round(sum(1 for r in sel if r and r <= c) / n, 3) for c in (1, 5, 10) if c <= args.k},
                "mrr@k": round(sum(1 / r for r in sel if r) / n, 3)}
    report = {"k": args.k, "profile_id": pub.profile_id, "content_id": pub.content_id,
              "all": metrics(ranks), "answerable": metrics([r for r, a in zip(ranks, answerable) if a]),
              "ms_per_query": round(1000 * elapsed / len(ranks), 1)}
    print(json.dumps(report, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
