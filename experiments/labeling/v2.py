"""Labelling v2 (docs/09 §5): one document as sections, with the v2 presets.

A section here is the run of blocks under one heading path, down to level 2. Blocks come from the deterministic
block rule (docs/09 §1.1), and the proposals come from the rule proposer (§5.1); both live in
experiments/ontology/propose.py. Blind documents (D43) show neither the root preset nor the section proposals.
Labels are stored with the block hashes of each section, so unchanged text keeps its ground truth on a new
version (§1.2).
"""
import hashlib
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ontology"))
import propose  # noqa: E402

PRESETS = {
    "reference": "Reference: evidence, no time limit",
    "record": "Record / report: evidence as of a date",
    "proposal": "Proposal / design / plan: a rule that is not accepted",
    "decision": "Decision / canon: a rule",
    "agent": "Agent instruction: needs activate",
    "boilerplate": "Boilerplate: not indexed",
}
SECTION_DEPTH = 2
DATE = re.compile(r"^20\d\d-\d\d-\d\d$")


def block_hash(text: str) -> str:
    return hashlib.sha256(" ".join(text.split()).encode()).hexdigest()


def sections(path: str, text: str, blind: bool) -> dict:
    meta, body = propose.frontmatter(text)
    title = next((ln for ln in body.splitlines() if ln.startswith("# ")), "")
    root, _signal = propose.root_preset(path, meta, title)
    date = propose.DATE.search(Path(path).name)
    out, key = [], None
    for b in propose.blocks(body):
        k = " / ".join(b["heading"].split(" / ")[:SECTION_DEPTH])
        if k != key or not out:
            out.append({"heading": k, "blocks": [], "proposal": propose.block_preset(b["heading"]) or root})
            key = k
        out[-1]["blocks"].append(b["text"])
    return {
        "root": None if blind else root,
        "date": date.group(1) if date else None,
        "sections": [{"i": i, "heading": s["heading"] or "(no heading)", "text": "\n\n".join(s["blocks"]),
                      "n_blocks": len(s["blocks"]), "proposal": None if blind else s["proposal"]}
                     for i, s in enumerate(out)],
        "_hashes": [[block_hash(t) for t in s["blocks"]] for s in out],
    }


def validate(body: dict, doc: dict, sensitivity_options, egress_options) -> dict:
    """The record that labels_v2.jsonl stores. A restricted section makes the document restricted (it tightens,
    docs/09 §2.1); restricted with cloud egress is refused, as in the product."""
    values = body.get("values") or {}
    sens, egress, root = values.get("sensitivity"), values.get("egress"), values.get("root")
    if sens not in sensitivity_options or egress not in egress_options or root not in PRESETS:
        raise ValueError("sensitivity, egress and a root preset are required")
    n = len(doc["sections"])
    overrides = body.get("sections") or {}
    if not isinstance(overrides, dict) or any(not str(k).isdigit() or int(k) >= n or v not in PRESETS
                                              for k, v in overrides.items()):
        raise ValueError("invalid section presets")
    restricted = body.get("restricted") or []
    if not isinstance(restricted, list) or any(not isinstance(i, int) or not 0 <= i < n for i in restricted):
        raise ValueError("invalid restricted sections")
    if restricted:
        sens = "restricted"
    if sens == "restricted" and egress != "local_only":
        raise ValueError("restricted content must stay local")
    as_of = body.get("as_of")
    if as_of is not None and not (isinstance(as_of, str) and DATE.match(as_of)):
        raise ValueError("as_of must be YYYY-MM-DD")
    return {"values": {"sensitivity": sens, "egress": egress, "root": root},
            "sections": {str(k): v for k, v in overrides.items()}, "restricted": sorted(set(restricted)),
            "as_of": as_of, "needs_review": body.get("needs_review") is True,
            "block_hashes": doc["_hashes"], "proposal_shown": doc["root"] is not None}
