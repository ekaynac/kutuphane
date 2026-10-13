"""M0 model measurement (D31, D42): FTS vs dense vs hybrid (RRF) vs hybrid + reranker, on GPU and on CPU.

    HF_HOME=<cache> HF_HUB_OFFLINE=1 KUTUPHANE_DSN=<eval db> \
        python -I eval_models.py run <qa_benchmark_gold.csv> <out_dir> --device cuda|cpu [--rerank-every N]
    python -I eval_models.py compare <out_dir> cuda cpu

Run eval_search.py first: it publishes the corpus into the evaluation database; this script reads those chunks.
`run` measures one device and saves embeddings and reranker scores under <out_dir> (a rerun reuses them), so the
GPU and CPU runs need not happen together on a shared machine. On CPU the rerankers can be measured on every N-th
question only (speed and cross test; quality comes from the full GPU run). `compare` is the cross test: how
closely two devices agree on the same inputs. Weights are local after one download; revisions are recorded.
"""
import argparse
import csv
import json
import sys
import time
from pathlib import Path

import numpy as np
import torch
from huggingface_hub import snapshot_download
from sentence_transformers import CrossEncoder, SentenceTransformer

sys.path.insert(0, str(Path(__file__).resolve().parent))
from eval_search import READER, gold_window, norm, relevant  # noqa: E402

from kutuphane import db, search  # noqa: E402
from kutuphane.gate import Actor  # noqa: E402

EMBEDDERS = {"bge-m3": "BAAI/bge-m3", "qwen3-emb-0.6b": "Qwen/Qwen3-Embedding-0.6B"}
RERANKERS = {"bge-reranker-v2-m3": "BAAI/bge-reranker-v2-m3",
             "qwen3-rerank-0.6b": "tomaarsen/Qwen3-Reranker-0.6B-seq-cls"}
QUERY_PROMPT = {"qwen3-emb-0.6b": "Instruct: Given a Turkish legal question, retrieve the statute article that "
                                  "answers it\nQuery: "}
# Qwen3-Reranker scores a chat-formatted yes/no judgement; without its template the scores are meaningless (first
# run: R@1 0.06). The document is cut by characters so truncation can never remove the closing template.
QWEN_RERANK = ('<|im_start|>system\nJudge whether the Document meets the requirements based on the Query and the '
               'Instruct provided. Note that the answer can only be "yes" or "no".<|im_end|>\n<|im_start|>user\n'
               '<Instruct>: Given a Turkish legal question, retrieve the statute article that answers it\n'
               '<Query>: {q}\n', '<Document>: {d}<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n')
QWEN_DOC_CHARS = 1200
CANDIDATES = 50      # per first-stage list
RERANK_TOP = 30      # hybrid candidates the reranker sees
RRF_K = 60
EMBED_TOKENS = 1024
RERANK_TOKENS = 512
MIN_FREE_GB = 6      # shared machine: refuse to start on the GPU below this much free CUDA memory
CPU_THREADS = 12
WEIGHTS = ["*.json", "*.safetensors", "pytorch_model.bin", "*.txt", "*.model", "tokenizer*", "1_Pooling/*",
           "sentencepiece*"]  # no custom code: trust_remote_code stays off


def free_gb() -> float:
    """Free memory as CUDA sees it (on unified memory, other processes' reservations are already subtracted)."""
    try:
        return torch.cuda.mem_get_info()[0] / 2**30
    except RuntimeError:
        return 0.0


def local(model_id: str) -> tuple[str, str]:
    path = snapshot_download(model_id, allow_patterns=WEIGHTS)  # weights + tokenizer only (no ONNX/ColBERT extras)
    return path, Path(path).name  # snapshot directory name is the commit hash


def load_chunks(conn) -> list[str]:
    rows = conn.execute("SELECT c.text FROM chunk c JOIN book b ON b.slug = c.book "
                        "AND b.current_content = c.content_id WHERE c.book = 'mevzuat' "
                        "ORDER BY c.path, c.ordinal").fetchall()
    return [t for (t,) in rows]


def fts_ranking(conn, questions) -> list[list[int]]:
    index = {(p, o): i for i, (p, o) in enumerate(conn.execute(
        "SELECT c.path, c.ordinal FROM chunk c JOIN book b ON b.slug = c.book AND b.current_content = c.content_id "
        "WHERE c.book = 'mevzuat' ORDER BY c.path, c.ordinal").fetchall())}
    out = []
    for q in questions:
        hits = search.search(conn, Actor(READER), q["soru"][:search.MAX_QUERY_CHARS], k=CANDIDATES)
        out.append([index[(h.citation.path, h.citation.ordinal)] for h in hits])
    return out


def rrf(*rankings) -> list[int]:
    score = {}
    for ranking in rankings:
        for r, i in enumerate(ranking, 1):
            score[int(i)] = score.get(int(i), 0.0) + 1 / (RRF_K + r)
    return sorted(score, key=lambda i: -score[i])


def metrics(ranks: list[int | None]) -> dict:
    n = len(ranks)
    return {"n": n, **{f"r@{c}": round(sum(1 for r in ranks if r and r <= c) / n, 3) for c in (1, 5, 10)},
            "mrr@10": round(sum(1 / r for r in ranks if r) / n, 3)}


def score(rankings, texts, questions, answerable) -> dict:
    ranks = [next((r for r, i in enumerate(ranking[:10], 1) if relevant(texts[i], q["context"])), None)
             for ranking, q in zip(rankings, questions)]
    return {"answerable": metrics([r for r, a in zip(ranks, answerable) if a]), "all": metrics(ranks)}


def dtype(device: str) -> dict:
    return {"torch_dtype": torch.float16} if device == "cuda" else {}


def embed(name, path, device, texts, queries) -> dict:
    model = SentenceTransformer(path, device=device, model_kwargs=dtype(device))
    model.max_seq_length = EMBED_TOKENS
    started = time.time()
    docs = model.encode(texts, batch_size=16, normalize_embeddings=True, convert_to_numpy=True)
    doc_s = time.time() - started
    started = time.time()
    qs = model.encode([QUERY_PROMPT.get(name, "") + q for q in queries], batch_size=16,
                      normalize_embeddings=True, convert_to_numpy=True)
    q_ms = 1000 * (time.time() - started) / len(queries)
    return {"docs": docs.astype(np.float32), "queries": qs.astype(np.float32),
            "docs_per_s": len(texts) / doc_s, "query_ms": q_ms}


def pair(rname: str, question: str, doc: str) -> tuple[str, str]:
    if rname.startswith("qwen3"):
        return QWEN_RERANK[0].format(q=question), QWEN_RERANK[1].format(d=doc[:QWEN_DOC_CHARS])
    return question, doc


def rerank(rname, path, device, questions, candidates, texts, chosen) -> dict:
    """Scores the top RERANK_TOP hybrid candidates of the chosen questions; one row per chosen question."""
    model = CrossEncoder(path, device=device, max_length=RERANK_TOKENS, model_kwargs=dtype(device))
    cand = np.array([candidates[q][:RERANK_TOP] for q in chosen])
    scores, started = [], time.time()
    for q, row in zip(chosen, cand):
        scores.append(model.predict([pair(rname, questions[q]["soru"], texts[i]) for i in row], batch_size=16))
    return {"chosen": np.array(chosen), "candidates": cand, "scores": np.array(scores, dtype=np.float32),
            "query_ms": 1000 * (time.time() - started) / len(chosen)}


def cached(path: Path, compute) -> dict:
    if path.exists():
        return dict(np.load(path))
    result = compute()
    np.savez(path, **result)
    return result


def run(args) -> None:
    if args.device == "cuda" and free_gb() < MIN_FREE_GB:
        sys.exit(f"only {free_gb():.1f} GB free CUDA memory (need {MIN_FREE_GB}); not starting on a shared GPU")
    torch.set_num_threads(CPU_THREADS)
    csv.field_size_limit(sys.maxsize)
    questions = [r for r in csv.DictReader(open(args.qa, encoding="utf-8")) if r["is_active"] == "True"]
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    with db.connect() as conn:
        texts = load_chunks(conn)
        fts = fts_ranking(conn, questions)
    corpus = norm(" ".join(texts))
    answerable = [gold_window(q["context"]) in corpus for q in questions]
    chosen = list(range(0, len(questions), args.rerank_every))
    report = {"device": args.device, "chunks": len(texts), "questions": len(questions),
              "answerable": sum(answerable), "rerank_questions": len(chosen),
              "fts": score(fts, texts, questions, answerable), "revisions": {}, "runs": {}}
    sub_q = [questions[i] for i in chosen]
    sub_a = [answerable[i] for i in chosen]
    for ename in args.embedders.split(","):
        path, report["revisions"][ename] = local(EMBEDDERS[ename])
        e = cached(out / f"{ename}.{args.device}.npz",
                   lambda: embed(ename, path, args.device, texts, [q["soru"] for q in questions]))
        dense = [np.argsort(-(e["docs"] @ q), kind="stable")[:CANDIDATES] for q in e["queries"]]
        hybrid = [rrf(f, d) for f, d in zip(fts, dense)]
        result = {"docs_per_s": round(float(e["docs_per_s"]), 1), "query_ms": round(float(e["query_ms"]), 1),
                  "dense": score(dense, texts, questions, answerable),
                  "hybrid": score(hybrid, texts, questions, answerable),
                  "hybrid_on_rerank_questions": score([hybrid[i] for i in chosen], texts, sub_q, sub_a)}
        for rname in args.rerankers.split(","):
            rpath, report["revisions"][rname] = local(RERANKERS[rname])
            r = cached(out / f"{ename}+{rname}.{args.device}.npz",
                       lambda: rerank(rname, rpath, args.device, questions, hybrid, texts, chosen))
            ranked = [[int(c[j]) for j in np.argsort(-s, kind="stable")] + hybrid[q][RERANK_TOP:]
                      for q, c, s in zip(r["chosen"], r["candidates"], r["scores"])]
            result[rname] = {"query_ms": round(float(r["query_ms"]), 1), **score(ranked, texts, sub_q, sub_a)}
        report["runs"][ename] = result
        print(json.dumps({ename: result}, ensure_ascii=False), file=sys.stderr, flush=True)
    (out / f"report.{args.device}.json").write_text(json.dumps(report, ensure_ascii=False, indent=1))
    print(json.dumps(report, ensure_ascii=False, indent=1))


def compare(args) -> None:
    """Cross test: the same model on two devices, compared on identical inputs."""
    out, a, b = Path(args.out), args.a, args.b
    report = {}
    for ename in EMBEDDERS:
        if not (out / f"{ename}.{b}.npz").exists():
            continue
        ea, eb = np.load(out / f"{ename}.{a}.npz"), np.load(out / f"{ename}.{b}.npz")
        cos = np.sum(ea["docs"] * eb["docs"], axis=1)
        top_a = [set(np.argsort(-(ea["docs"] @ q))[:10]) for q in ea["queries"]]
        top_b = [set(np.argsort(-(eb["docs"] @ q))[:10]) for q in eb["queries"]]
        entry = {"embedding_cosine_min": round(float(cos.min()), 4),
                 "embedding_cosine_mean": round(float(cos.mean()), 5),
                 "dense_top10_overlap": round(float(np.mean([len(x & y) / 10 for x, y in zip(top_a, top_b)])), 3),
                 "speedup_docs": round(float(ea["docs_per_s"] / eb["docs_per_s"]), 1)}
        for rname in RERANKERS:
            if not (out / f"{ename}+{rname}.{b}.npz").exists():
                continue
            ra, rb = np.load(out / f"{ename}+{rname}.{a}.npz"), np.load(out / f"{ename}+{rname}.{b}.npz")
            pairs_a = {(int(q), int(c)): s for q, cs, ss in zip(ra["chosen"], ra["candidates"], ra["scores"])
                       for c, s in zip(cs, ss)}
            shared = [(pairs_a[(int(q), int(c))], s)
                      for q, cs, ss in zip(rb["chosen"], rb["candidates"], rb["scores"])
                      for c, s in zip(cs, ss) if (int(q), int(c)) in pairs_a]
            diff = np.abs(np.array([x - y for x, y in shared]))
            entry[rname] = {"shared_pairs": len(shared), "score_abs_diff_max": round(float(diff.max()), 4),
                            "score_abs_diff_mean": round(float(diff.mean()), 5),
                            "speedup": round(float(rb["query_ms"] / ra["query_ms"]), 1)}
        report[ename] = entry
    print(json.dumps(report, ensure_ascii=False, indent=1))


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("qa")
    r.add_argument("out")
    r.add_argument("--device", choices=["cuda", "cpu"], required=True)
    r.add_argument("--rerank-every", type=int, default=1)
    r.add_argument("--embedders", default=",".join(EMBEDDERS))
    r.add_argument("--rerankers", default=",".join(RERANKERS))
    c = sub.add_parser("compare")
    c.add_argument("out")
    c.add_argument("a")
    c.add_argument("b")
    args = ap.parse_args()
    run(args) if args.cmd == "run" else compare(args)


if __name__ == "__main__":
    main()
