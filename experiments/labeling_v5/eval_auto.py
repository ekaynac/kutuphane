"""Score the v5 proposers on the auto set (docs/21). It reads the gold (<root>/auto/*.gold.jsonl) only here, after
the proposers ran; the proposers never import this file.

    python eval_auto.py <root> [--rules FILE] [--baseline FILE] [--llm FILE] [--llm-version llm-v5.2] [--details]

For each field: n, correct, abstained, wrong, and the dangerous errors (docs/21 §2):
false `accepted`, a missed `withdrawn`/`rejected`, a missed successor, a false licence, a false `assisted`.
"""
import argparse
import json
import re
from collections import Counter
from pathlib import Path

ABSTAIN = None
HISTORY_STATES = {"withdrawn", "rejected"}
# the 12 decision-time PEP copies say `Draft`: the text is the one that was decided (auto/docs README §5.6)
ARTIFACT_STATE = {"draft": "pending"}
SOURCES = (("auto-pep-", "PEP"), ("auto-rfc-", "RFC"), ("auto-kep-", "KEP"), ("auto-adr-", "ADR"),
           ("auto-np-", "nanopub"), ("auto-assist-", "assisted PR"), ("auto-tab-", "TAB"),
           ("auto-radar-", "radar brief"))


def source(case_id: str) -> str:
    return next((name for prefix, name in SOURCES if case_id.startswith(prefix)), "REUSE/SPDX")


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def load_gold(root: Path) -> dict:
    return {g["id"]: g.get("gold") or {} for f in sorted((root / "auto").glob("*.gold.jsonl")) for g in read_jsonl(f)}


def answers(path: Path, version: str | None) -> dict:
    """{case id: {field: value}} from a rules/baseline file (`proposals`) or an LLM file (`p`; the latest valid line
    of `version` counts). `unknown` is the LLM's way to abstain, except for the licence, where it is a value."""
    out = {}
    for r in read_jsonl(path):
        if version and r.get("proposer_version") != version:
            continue
        if "proposals" in r:
            out[r["id"]] = {k: v.get("value") for k, v in r["proposals"].items()}
        elif isinstance(r.get("p"), dict):
            out[r["id"]] = {k: (None if v == "unknown" else v) for k, v in r["p"].items()}
    return out


DEPRECATED_ID = re.compile(r"\b((?:A|L)?GPL-\d\.\d|GFDL-1\.[123])(\+?)(?![\w.+-])")


def norm_licence(value) -> str | None:
    """An SPDX expression in one comparable form: deprecated GNU ids as `-only`/`-or-later` (as the gold does,
    auto/rights README), no outer parentheses, one space, no case."""
    if not isinstance(value, str):
        return None
    v = DEPRECATED_ID.sub(lambda m: m.group(1) + ("-or-later" if m.group(2) else "-only"), value)
    v = re.sub(r"\s+", " ", v).strip()
    if v.startswith("(") and v.endswith(")") and v.count("(") == 1:
        v = v[1:-1].strip()
    return v.casefold()


def expected_acceptance(case_id: str, gold: dict) -> tuple[bool, str | None]:
    """(scored?, expected acceptance). A docs case with no declared status expects no claim (`None`; `pending`
    also counts as correct, the kstd default). A nanopub expects `withdrawn` for a same-key retraction or
    supersession; a retraction by another key is only a contest mark, so the item keeps no declared state."""
    if "case_kind" in gold:
        return True, None if gold["case_kind"] == "retraction-other-key" else "withdrawn"
    if "acceptance" in gold:
        return True, gold["acceptance"]
    return False, None


def score(gold: dict, got: dict) -> dict:
    """Counters per field, the case ids of the wrong answers, and the dangerous errors."""
    fields, wrong = {}, {}
    errors = {k: [] for k in ("false_accepted", "missed_history", "missed_successor", "successor_not_flagged",
                              "withdrawn_by_other_key", "false_licence", "false_assisted")}

    def tally(field: str, ok: bool, value, cid: str):
        c = fields.setdefault(field, Counter())
        c["n"] += 1
        c["correct" if ok else "abstained" if value is ABSTAIN else "wrong"] += 1
        if not ok and value is not ABSTAIN:
            wrong.setdefault(field, []).append(f"{cid}={value}")

    for cid, g in sorted(gold.items()):
        a = got.get(cid, {})
        src = source(cid)
        acc = a.get("acceptance")
        scored, exp = expected_acceptance(cid, g)
        if scored and "decision_time" in g:  # the 12 decision-time PEPs: two separate scores
            art = ARTIFACT_STATE.get(str(g.get("artifact_status")).casefold())
            tally("acceptance vs artifact_status (12 decision-time PEPs)", acc == art, acc, cid)
            tally("acceptance vs current acceptance (12 decision-time PEPs)", acc == exp, acc, cid)
        elif scored:
            if exp is None:  # no declared state: no claim and the kstd default `pending` are both correct
                tally(f"acceptance: {src}", acc in (ABSTAIN, "pending"), acc, cid)
            else:
                tally(f"acceptance: {src}", acc == exp, acc, cid)
            if acc == "accepted" and exp != "accepted":
                errors["false_accepted"].append(cid)
            if exp in HISTORY_STATES and acc not in HISTORY_STATES:
                errors["missed_history"].append(f"{cid} ({exp}→{acc})")
            if g.get("case_kind") == "retraction-other-key" and acc in HISTORY_STATES:
                errors["withdrawn_by_other_key"].append(cid)  # docs/11 §4 rule 8: only a contest mark
        if g.get("superseded_by"):
            if not a.get("superseded_by"):
                errors["missed_successor"].append(cid)
            # a successor that ends the item (not `other-scope`) must at least show the item as history
            if g.get("supersession_scope") != "other-scope" and "decision_time" not in g and acc not in HISTORY_STATES:
                errors["successor_not_flagged"].append(cid)
        if "license" in g:
            lic = a.get("license")
            tally(f"license: {src}", norm_licence(lic) == norm_licence(g["license"]), lic, cid)
            if lic is not ABSTAIN and norm_licence(lic) not in ("unknown", norm_licence(g["license"])):
                errors["false_licence"].append(f"{cid} ({lic} vs {g['license']})")
        if "personal_data" in g:
            tally(f"personal_data: {src}", a.get("personal_data") == g["personal_data"], a.get("personal_data"), cid)
        if isinstance(g.get("origin"), str):
            tally(f"origin: {src}", a.get("origin") == g["origin"], a.get("origin"), cid)
            if a.get("origin") == "assisted" and g["origin"] == "model":
                errors["false_assisted"].append(cid)
        if "contest_mark" in g:  # the rules propose `contest: yes` or nothing; nothing is correct when no mark is due
            mark = a.get("contest") == "yes"
            tally("contest mark: nanopub", mark == g["contest_mark"], "yes" if mark else ABSTAIN, cid)
        if g.get("valid_to"):
            tally(f"valid_to: {src}", a.get("valid_to") == g["valid_to"], a.get("valid_to"), cid)
    return {"fields": fields, "wrong": wrong, "errors": errors}


def table(results: dict[str, dict]) -> str:
    names = list(results)
    fields = sorted({f for r in results.values() for f in r["fields"]})
    head = "| field | n | " + " | ".join(f"{n} correct / abstained / wrong" for n in names) + " |"
    lines = [head, "|---|---|" + "---|" * len(names)]
    for f in fields:
        n = next(r["fields"][f]["n"] for r in results.values() if f in r["fields"])
        cells = []
        for name in names:
            c = results[name]["fields"].get(f)
            cells.append(f"{c['correct']} / {c['abstained']} / {c['wrong']}" if c else "—")
        lines.append(f"| {f} | {n} | " + " | ".join(cells) + " |")
    lines += ["", "| dangerous error | " + " | ".join(names) + " |", "|---|" + "---|" * len(names)]
    for e in next(iter(results.values()))["errors"]:
        lines.append(f"| {e} | " + " | ".join(str(len(r["errors"][e])) for r in results.values()) + " |")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("root")
    ap.add_argument("--rules")
    ap.add_argument("--baseline")
    ap.add_argument("--llm")
    ap.add_argument("--llm-version", help="score only the lines of this proposer version (the LLM file appends)")
    ap.add_argument("--details", action="store_true", help="also print the case ids of each error")
    args = ap.parse_args()
    root = Path(args.root)
    gold = load_gold(root)
    files = {"rules": args.rules or root / "proposals.auto.jsonl",
             "baseline": args.baseline or root / "proposals_baseline.auto.jsonl",
             "Qwen": args.llm or root / "proposals_llm.auto.jsonl"}
    results = {name: score(gold, answers(Path(path), args.llm_version if name == "Qwen" else None))
               for name, path in files.items()}
    print(table(results))
    if args.details:
        for name, r in results.items():
            print(f"\n## {name}")
            for e, ids in r["errors"].items():
                print(f"- {e} ({len(ids)}): {', '.join(ids)}")
            for f, ids in sorted(r["wrong"].items()):
                print(f"- wrong {f}: {', '.join(ids)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
