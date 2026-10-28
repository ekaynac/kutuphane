"""Compare the operator with the blind second reader (Astra) on the 60 cases of the v5 human set that
human/pool.selection.json marks `second_reader: true` (docs/20 §3.3, §8, D67). Run it only when the operator has
finished: it reads the operator labels.

    python compare_second.py <root> [--operator first|latest] [--json]

<root> is research/labelling-v5. Inputs: <root>/labels.jsonl (the operator), <root>/second_reader.astra.jsonl (Astra,
the latest line per id counts) and <root>/human/pool.selection.json (which cases, their group and stratum).
`--operator first` (the default) uses the operator's first choice: it was made before the suggestions were shown, so
both readers judged blind. `latest` uses the revision.

Per group and overall: the number of pairs, the agreement, Cohen's kappa (with "unknown" as one more category; no kappa
when the expected agreement is 1, i.e. both readers used one and the same category), and the agreement on the pairs
where neither reader said "unknown". Then the list of disagreements and the marked cases that still have no pair.
"""
import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

GROUP_FIELD = {"review-evidence": "review", "instruction-safety": "activation_risk", "normative-meaning": "normative",
               "personal-data": "personal_data"}
UNKNOWN = "unknown"


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()] if path.exists() else []


def operator_answers(rows: list[dict], mode: str) -> dict:
    """{case id: value} from labels.jsonl: the first `first` record, or the latest record of the case."""
    out = {}
    for r in rows:
        if r.get("set") != "human" or r.get("group") not in GROUP_FIELD:
            continue
        value = (r.get("labels") or {}).get(GROUP_FIELD[r["group"]])
        if value is None:
            continue
        if mode == "first":
            if r.get("stage") == "first" and r["id"] not in out:
                out[r["id"]] = value
        else:
            out[r["id"]] = value
    return out


def second_answers(rows: list[dict]) -> dict:
    """{case id: row} from second_reader.astra.jsonl; the latest line per id counts."""
    return {r["id"]: r for r in rows if isinstance(r.get("answer"), str)}


def cohen_kappa(pairs: list[tuple]) -> float | None:
    """Cohen's kappa of (a, b) pairs, or None when it is not defined (no pairs, or an expected agreement of 1)."""
    n = len(pairs)
    if not n:
        return None
    po = sum(a == b for a, b in pairs) / n
    ca, cb = Counter(a for a, _ in pairs), Counter(b for _, b in pairs)
    pe = sum(ca[k] * cb[k] for k in ca.keys() | cb.keys()) / (n * n)
    return None if pe >= 1 else (po - pe) / (1 - pe)


def stats(pairs: list[tuple]) -> dict:
    decided = [(a, b) for a, b in pairs if UNKNOWN not in (a, b)]
    k = cohen_kappa(pairs)
    return {"pairs": len(pairs), "agree": sum(a == b for a, b in pairs),
            "agreement": round(sum(a == b for a, b in pairs) / len(pairs), 3) if pairs else None,
            "kappa": round(k, 3) if k is not None else None,
            "decided_pairs": len(decided),
            "decided_agreement": round(sum(a == b for a, b in decided) / len(decided), 3) if decided else None,
            "operator_unknown": sum(a == UNKNOWN for a, _ in pairs), "second_unknown": sum(b == UNKNOWN for _, b in pairs)}


def compare(selection: dict, operator: dict, second: dict) -> dict:
    marked = [c for c in selection["cases"] if c.get("second_reader")]
    by_group, by_stratum, all_pairs = defaultdict(list), defaultdict(list), []
    disagreements, missing = [], []
    for c in sorted(marked, key=lambda c: (c["group"], c["id"])):
        a, s = operator.get(c["id"]), second.get(c["id"])
        if a is None or s is None:
            missing.append({"id": c["id"], "group": c["group"],
                            "missing": [n for n, v in (("operator", a), ("second", s)) if v is None]})
            continue
        pair = (a, s["answer"])
        by_group[c["group"]].append(pair)
        by_stratum[c.get("stratum")].append(pair)
        all_pairs.append(pair)
        if pair[0] != pair[1]:
            disagreements.append({"id": c["id"], "group": c["group"], "stratum": c.get("stratum"), "operator": a,
                                  "second": s["answer"], "second_reason": s.get("reason"),
                                  "second_evidence": s.get("evidence_pointer")})
    return {"marked": len(marked), "groups": {g: stats(p) for g, p in sorted(by_group.items())},
            "strata": {k: stats(p) for k, p in sorted(by_stratum.items())}, "overall": stats(all_pairs),
            "disagreements": disagreements, "missing": missing}


def show(r: dict, mode: str) -> str:
    def fmt(x):
        return "—" if x is None else f"{x:.3f}" if isinstance(x, float) else str(x)
    head = ("", "pairs", "agree", "agreement", "kappa", "decided", "dec. agree", "op unk", "2nd unk")
    lines = [f"Operator ({mode} choice) vs second reader: {r['overall']['pairs']} pairs of {r['marked']} marked cases",
             "  ".join(f"{h:>20}" if i == 0 else f"{h:>10}" for i, h in enumerate(head))]
    for name, s in [*r["groups"].items(), *((f"stratum {k}", v) for k, v in r["strata"].items()), ("overall", r["overall"])]:
        vals = (s["pairs"], s["agree"], s["agreement"], s["kappa"], s["decided_pairs"], s["decided_agreement"],
                s["operator_unknown"], s["second_unknown"])
        lines.append(f"{name:>20}  " + "  ".join(f"{fmt(v):>10}" for v in vals))
    lines.append(f"\nDisagreements ({len(r['disagreements'])}):")
    for d in r["disagreements"]:
        lines.append(f"  {d['id']} [{d['group']}, {d['stratum']}] operator={d['operator']} second={d['second']}"
                     f" — {d['second_reason']} ({d['second_evidence']})")
    if r["missing"]:
        lines.append(f"\nNo pair yet ({len(r['missing'])}):")
        lines.extend(f"  {m['id']} [{m['group']}]: no {' and no '.join(m['missing'])} answer" for m in r["missing"])
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("root")
    ap.add_argument("--operator", choices=("first", "latest"), default="first")
    ap.add_argument("--second", help="default: <root>/second_reader.astra.jsonl")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    root = Path(args.root)
    selection = json.loads((root / "human" / "pool.selection.json").read_text())
    operator = operator_answers(read_jsonl(root / "labels.jsonl"), args.operator)
    second = second_answers(read_jsonl(Path(args.second) if args.second else root / "second_reader.astra.jsonl"))
    r = compare(selection, operator, second)
    print(json.dumps(r, ensure_ascii=False, indent=1) if args.json else show(r, args.operator))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
