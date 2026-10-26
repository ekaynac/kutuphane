"""Select the v5 human set (docs/20 §3.3, D67): per group 5 calibration + 15 disagreement/uncertainty + 10 random,
at most 2 cases per family, from a candidate pool that both proposers have already labelled. The choice is seeded
and frozen in <root>/human/pool.selection.json.

    python propose.py <root> --set human --slice pool-candidates --out <root>/proposals.human-candidates.jsonl
    python llm_propose.py <root> --set human --slice pool-candidates --out <root>/proposals_llm.human-candidates.jsonl
    python select_human.py <root>
        # writes human/pool/<id>/, human/pool.cases.jsonl, human/pool.gold.jsonl, human/pool.selection.json,
        # and the frozen suggestions of the 120 cases: proposals.human.jsonl, proposals_llm.human.jsonl

Reference answers (`*.ref.jsonl`: answers that the source itself declares) are used only to pick calibration cases
and go to pool.gold.jsonl; they never enter case.json. `why_selected` never states a proposed or reference value.
"""
import argparse
import hashlib
import json
import random
import shutil
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from llm_propose import MODEL, valid  # noqa: E402

SEED = 20261026
QUOTA = {"calibration": 5, "disagreement": 15, "random": 10}
FAMILY_CAP = 2
QUESTION = {"review-evidence": "review", "instruction-safety": "activation_risk", "normative-meaning": "normative",
            "personal-data": "personal_data"}
ABSTAIN = {"unknown", "n/a", None}


def jsonl(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()] if path.exists() else []


def latest(path: Path) -> dict:
    return {r["id"]: r for r in jsonl(path)}


def uncertainty(field: str, rule: dict | None, llm: dict | None) -> tuple[float, list[str]]:
    """A score for the disagreement stratum, and the reasons (no values: the person sees them before judging)."""
    score, why = 0.0, []
    rv = (rule or {}).get(field, {}).get("value")
    lp = llm.get("p") if llm and valid(llm) else None
    lv = lp.get(field) if lp else None
    if lp is None:
        score += 1.0
        why.append("the local model gave no valid answer")
    if rv is not None and lv not in ABSTAIN and rv != lv:
        score += 3.0
        why.append("the rule proposer and the local model disagree")
    elif rv is None and lv not in ABSTAIN:
        score += 1.0
        why.append("the rule proposer has no signal")
    if lv in ABSTAIN and lp is not None:
        score += 1.5
        why.append("the local model abstains")
    conf = lp.get(f"{field}_confidence") if lp else None
    if conf in ("low", "medium"):
        score += {"low": 2.0, "medium": 1.0}[conf]
        why.append(f"the local model is {conf}-confidence")
    if (rule or {}).get(field, {}).get("confidence") == "low":
        score += 0.5
    return score, why


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("root")
    args = ap.parse_args()
    root = Path(args.root)
    human = root / "human"
    cands = [c for f in sorted(human.glob("pool-candidates.*.cases.jsonl")) for c in jsonl(f)]
    refs = {r["id"]: r for f in sorted(human.glob("pool-candidates.*.ref.jsonl")) for r in jsonl(f)}
    rules = latest(root / "proposals.human-candidates.jsonl")
    llm = latest(root / "proposals_llm.human-candidates.jsonl")
    if not cands:
        sys.exit("no candidates")

    selected, report = [], {}
    by_group = defaultdict(list)
    for c in sorted(cands, key=lambda c: c["id"]):
        by_group[c["group"]].append(c)
    for group, pool in sorted(by_group.items()):
        field = QUESTION[group]
        rng = random.Random(f"{SEED}:{group}")
        fam = Counter()
        taken: dict[str, tuple[str, str]] = {}

        def take(c, stratum, why):
            taken[c["id"]] = (stratum, why)
            fam[c["family"]] += 1

        def free(c):
            return c["id"] not in taken and fam[c["family"]] < FAMILY_CAP

        # 1. calibration: the source declares the answer and both proposers agree with it; else the clearest
        #    agreement of both proposers. Spread over the reference values.
        def agree_ref(c):
            ref = refs.get(c["id"], {}).get("ref", {}).get(field)
            rv = rules.get(c["id"], {}).get("proposals", {}).get(field, {}).get("value")
            lr = llm.get(c["id"])
            lv = lr["p"].get(field) if lr and valid(lr) else None
            return ref, rv, lv, (lr["p"].get(f"{field}_confidence") if lr and valid(lr) else None)

        shuffled = pool[:]
        rng.shuffle(shuffled)
        with_ref = [c for c in shuffled if agree_ref(c)[0]]
        tiers = [[c for c in with_ref if agree_ref(c)[0] == agree_ref(c)[1] == agree_ref(c)[2]],
                 [c for c in with_ref if agree_ref(c)[0] in (agree_ref(c)[1], agree_ref(c)[2])],
                 with_ref,
                 [c for c in shuffled if agree_ref(c)[1] is not None and agree_ref(c)[1] == agree_ref(c)[2]
                  and agree_ref(c)[2] not in ABSTAIN and agree_ref(c)[3] == "high"]]
        seen_values = Counter()
        for tier_no, tier in enumerate(tiers):
            for c in sorted(tier, key=lambda c: seen_values[agree_ref(c)[0] or agree_ref(c)[1]]):
                if sum(1 for s, _ in taken.values() if s == "calibration") >= QUOTA["calibration"]:
                    break
                value = agree_ref(c)[0] or agree_ref(c)[1]
                if free(c) and seen_values[value] < 2:
                    seen_values[value] += 1
                    take(c, "calibration", "Calibration case: " + (
                        "a reference answer exists outside the case (a source declaration or a strict rule on the "
                        "record); use it to check your scale before the hard cases."
                        if tier_no < 3 else "both proposers give the same answer with high confidence; it should be a "
                                            "clear case."))
        for c in shuffled:  # fill when the value spread was too strict
            if sum(1 for s, _ in taken.values() if s == "calibration") >= QUOTA["calibration"]:
                break
            if free(c) and (agree_ref(c)[0] or (agree_ref(c)[1] is not None and agree_ref(c)[1] == agree_ref(c)[2])):
                take(c, "calibration", "Calibration case: the source declares the answer or both proposers agree.")

        # 2. disagreement / uncertainty: highest score first, seeded tie-break
        scored = []
        for c in shuffled:
            s, why = uncertainty(field, rules.get(c["id"], {}).get("proposals"), llm.get(c["id"]))
            scored.append((s, c, why))
        scored.sort(key=lambda t: -t[0])
        n = 0
        for s, c, why in scored:
            if n >= QUOTA["disagreement"] or s <= 0:
                break
            if free(c):
                take(c, "disagreement", "Hard case: " + "; ".join(why) + f" on the {field.replace('_', ' ')} question.")
                n += 1

        # 3. random: a seeded draw from the rest of the pool (family cap still applies)
        rest = [c for c in shuffled if c["id"] not in taken]
        frame = len(rest)
        n = 0
        for c in rest:
            if n >= QUOTA["random"]:
                break
            if free(c):
                take(c, "random", f"Random case: drawn with seed {SEED} from the {frame} candidates that were left.")
                n += 1

        counts = Counter(s for s, _ in taken.values())
        # second reader (Astra, D67): all random cases + the 5 highest-scored disagreement cases per group
        hard = [c["id"] for s, c, _ in scored if taken.get(c["id"], ("",))[0] == "disagreement"][:5]
        report[group] = {"question_field": field, "candidates": len(pool), "families_in_pool": len({c["family"] for c in pool}),
                         "selected": dict(counts), "random_frame": frame, "second_reader": sorted(
                             [i for i, (s, _) in taken.items() if s == "random"] + hard)}
        for c in pool:
            if c["id"] in taken:
                selected.append((c, *taken[c["id"]]))

    out_dir = human / "pool"
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir()
    cases, gold = [], []
    for c, stratum, why in selected:
        src = human / "pool-candidates" / c["id"]
        shutil.copytree(src, out_dir / c["id"])
        case = {**c, "why_selected": why, "selection_stratum": stratum}
        (out_dir / c["id"] / "case.json").write_text(json.dumps(case, ensure_ascii=False, indent=1))
        cases.append(case)
        ref = refs.get(c["id"])
        gold.append({"id": c["id"], "gold": (ref or {}).get("ref", {}),
                     "gold_source": ("source declaration (reference, not a human label): " + ref["ref_source"]) if ref else
                     "none yet: the operator labels first, Astra reads second where listed in pool.selection.json",
                     "notes": "the reference is a source declaration, not a human judgment" if ref else ""})
    (human / "pool.cases.jsonl").write_text("".join(json.dumps(c, ensure_ascii=False) + "\n" for c in cases))
    (human / "pool.gold.jsonl").write_text("".join(json.dumps(g, ensure_ascii=False) + "\n" for g in gold))
    # the proposals that drove the selection are the frozen suggestions of the human set (same view, same versions)
    ids = [c["id"] for c in cases]
    for name, rows in (("proposals.human.jsonl", rules), ("proposals_llm.human.jsonl", llm)):
        (root / name).write_text("".join(json.dumps(rows[i], ensure_ascii=False) + "\n" for i in ids if i in rows))
    digest = hashlib.sha256("".join(sorted(c["id"] for c in cands)).encode()).hexdigest()
    selection = {"frozen_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "seed": SEED, "quota": QUOTA,
                 "family_cap": FAMILY_CAP,
                 "proposers": {"rules": sorted({r["proposer_version"] for r in rules.values()}),
                               "llm": sorted({r["proposer_version"] for r in llm.values()}), "llm_model": MODEL},
                 "candidate_ids_sha256": digest, "candidates": len(cands), "groups": report,
                 "cases": [{"id": c["id"], "group": c["group"], "family": c["family"], "stratum": c["selection_stratum"],
                            "second_reader": c["id"] in report[c["group"]]["second_reader"]} for c in cases]}
    (human / "pool.selection.json").write_text(json.dumps(selection, ensure_ascii=False, indent=1))
    for g, r in report.items():
        print(g, r["candidates"], "candidates →", r["selected"], "second reader", len(r["second_reader"]))
    print(len(cases), "cases selected")
    return 0


if __name__ == "__main__":
    sys.exit(main())
