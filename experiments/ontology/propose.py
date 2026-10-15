"""Ontology v2: the block rule and the rule-based proposer, with their first measurement (docs/09 §1.1, §5.1, §5.7).

Usage: python -I propose.py <labeling data dir>

Local only: rules, no model. Each document of the labelling corpus is split by the block rule; each block gets a
preset from rules (path, frontmatter, file name, heading words); the document's root preset is compared with
(a) the operator's v1 labels and (b) the v1 drafts, after mapping K1–K8 to v2 preset classes. Prints counts only,
never document text.
"""
import json
import re
import sys
from collections import Counter
from pathlib import Path
from statistics import median

MAX_BLOCK = 4000
ID_ROW = re.compile(r"^\|\s*[A-Za-zÇĞİÖŞÜçğıöşü]{0,6}-?\d+[a-z]?\s*\|")
DATE = re.compile(r"(20\d\d-\d\d-\d\d)")

# Signals (casefolded words of path parts, file name, frontmatter type, headings). Turkish and English.
INSTRUCTION_FILES = {"claude.md", "agents.md", "skill.md", "gemini.md"}
INSTRUCTION_WORDS = {"skill", "skills", "prompt", "prompts", "instructions", "mandate", "mandates", "brief", "persona"}
RECORD_WORDS = {"report", "reports", "review", "reviews", "notes", "note", "handover", "handoff", "evidence", "run",
                "runs", "log", "logs", "retro", "postmortem", "status", "findings", "summary", "analysis", "scan",
                "closure", "recheck", "audit"}
PROPOSAL_WORDS = {"design", "plan", "plans", "proposal", "proposals", "rfc", "spec", "specs", "brainstorm", "draft",
                  "öneri", "oneri", "tasarım", "tasarim", "taslak", "scratchpad", "todo", "roadmap"}
DECISION_WORDS = {"decision", "decisions", "adr", "canon", "standard", "standards", "policy", "rules", "register",
                  "obligations"}
# Turkish words carry suffixes ("incelemesi", "önerisi", "kararları"): match these stems as prefixes.
STEMS = {"record": ("rapor", "incelem", "devir", "durum", "bulgu", "özet", "ozet", "analiz", "not"),
         "proposal": ("öneri", "oneri", "tasarı", "tasari", "taslak", "plan"),
         "decision": ("karar", "kural", "kanon", "standart")}
RUNBOOK_WORDS = {"runbook", "runbooks", "procedure", "howto", "how-to", "sop", "playbook", "guide", "kılavuz"}

# v2 preset classes -> (instruction, role, time kind, standing); docs/09 §2.5
PRESETS = {
    "agent": ("yes", None, None, None),
    "record": ("no", "evidence", "as_of", None),
    "proposal": ("no", "rule", "durable", "pending"),
    "decision": ("no", "rule", "durable", "approved"),
    "reference": ("no", "evidence", "durable", None),   # also runbook
}
# v1 category -> v2 class (v1 had no decision class: decisions sat in K5/K1, so "decision" compares as "reference")
V1 = {"K3": "agent", "K5": "record", "NONE": "proposal", "K1": "reference", "K2": "reference", "K4": "reference",
      "K6": "reference", "K7": "reference", "K8": "reference"}


def words(text: str) -> set[str]:
    return {w for w in re.split(r"[^0-9a-zçğıöşü]+", text.casefold()) if w}


def has(sig: set[str], vocabulary: set[str], kind: str) -> bool:
    return bool(sig & vocabulary) or any(w.startswith(STEMS.get(kind, ())) for w in sig if len(w) > 3)


def frontmatter(text: str) -> tuple[dict, str]:
    if text.startswith("---\n"):
        end = text.find("\n---", 4)
        if end > 0:
            meta = {}
            for line in text[4:end].splitlines():
                key, _, value = line.partition(":")
                if value:
                    meta[key.strip().casefold()] = value.strip().strip("'\"").casefold()
            return meta, text[end + 4:]
    return {}, text


def blocks(text: str) -> list[dict]:
    """docs/09 §1.1: heading starts a block; inside a heading section one block per paragraph run, list group,
    table (rows when the first column holds ids), and code fence together with the paragraph before it."""
    out, heading, buf, kind = [], [], [], None

    def flush():
        nonlocal buf, kind
        body = "\n".join(buf).strip()
        if body:
            for part in _split_long(body):
                out.append({"heading": " / ".join(heading), "kind": kind, "text": part})
        buf, kind = [], None

    lines, i = text.splitlines(), 0
    while i < len(lines):
        line = lines[i]
        m = re.match(r"^(#{1,6})\s+(.*)", line)
        if m:
            flush()
            level = len(m.group(1))
            heading = heading[:level - 1] + [m.group(2).strip()]
            out.append({"heading": " / ".join(heading), "kind": "heading", "text": line})
        elif line.startswith("```"):
            explain = ""
            if kind == "paragraph":  # the paragraph immediately before the fence joins it (§1.1)
                paras = "\n".join(buf).strip().split("\n\n")
                explain = paras.pop()
                buf = ["\n\n".join(paras)] if paras else []
            flush()
            fence = [line]
            i += 1
            while i < len(lines) and not lines[i].startswith("```"):
                fence.append(lines[i])
                i += 1
            fence.append(lines[i] if i < len(lines) else "")
            text_ = (explain + "\n" if explain else "") + "\n".join(fence)
            out.append({"heading": " / ".join(heading), "kind": "code", "text": text_})
        elif line.lstrip().startswith("|"):
            new = "table"
            if kind != new:
                flush()
                kind = new
            buf.append(line)
            if i + 1 >= len(lines) or not lines[i + 1].lstrip().startswith("|"):
                for k, part in _table_blocks(buf):  # id table: header + one block per row; else row-bounded parts
                    out.append({"heading": " / ".join(heading), "kind": k, "text": part})
                buf, kind = [], None
        elif re.match(r"^\s*([-*+]|\d+[.)])\s+", line) or (kind == "list" and line.startswith("  ") and line.strip()):
            if kind != "list":
                flush()
                kind = "list"
            buf.append(line)
        elif not line.strip():
            if kind == "list" or (kind == "paragraph" and not heading):  # no heading: each paragraph is a block
                flush()
            elif kind == "paragraph":
                buf.append("")
        else:
            if kind not in (None, "paragraph"):
                flush()
            kind = "paragraph"
            buf.append(line)
        i += 1
    flush()
    return out


def _table_blocks(rows: list[str]) -> list[tuple[str, str]]:
    sep = next((k for k, r in enumerate(rows) if re.match(r"^\s*\|[\s:|-]+\|\s*$", r)), -1)
    head, data = rows[:sep + 1], rows[sep + 1:]
    ids = [r.split("|")[1].strip() for r in data]
    if len(data) >= 2 and all(ID_ROW.match(r.strip()) for r in data) and len(set(ids)) == len(ids):
        return ([("table-head", "\n".join(head))] if head else []) + [("row", r) for r in data]
    parts, cur = [], []
    for r in rows:  # an ordinary table: one block, split at row boundaries when long
        if cur and len("\n".join(cur + [r])) > MAX_BLOCK:
            parts.append(("table", "\n".join(cur)))
            cur = head[:] if head and r not in head else []
        cur.append(r)
    return parts + ([("table", "\n".join(cur))] if cur else [])


def _split_long(body: str) -> list[str]:
    if len(body) <= MAX_BLOCK:
        return [body]
    parts, cur = [], ""
    for para in body.split("\n\n"):
        if cur and len(cur) + len(para) > MAX_BLOCK:
            parts.append(cur)
            cur = ""
        cur = f"{cur}\n\n{para}" if cur else para
    return parts + ([cur] if cur else [])


def root_preset(path: str, meta: dict, title: str) -> tuple[str, str]:
    """Document root default from path, file name, frontmatter type and title. Returns (class, signal)."""
    p = Path(path)
    name, parts = p.name.casefold(), {x.casefold() for x in p.parts[:-1]}
    sig = words(" ".join(p.parts[-6:])) | words(meta.get("type", "")) | words(title)
    if name in INSTRUCTION_FILES or sig & INSTRUCTION_WORDS or meta.get("type") in {"skill", "agent", "prompt"}:
        return "agent", "instruction"
    if has(sig, PROPOSAL_WORDS, "proposal"):
        return "proposal", "proposal-word"
    if has(sig, RECORD_WORDS, "record"):
        return "record", "record-word"
    if has(sig, DECISION_WORDS, "decision"):
        return "decision", "decision-word"
    if sig & RUNBOOK_WORDS:
        return "reference", "runbook-word"
    if DATE.search(name):  # a dated file with no other signal is a snapshot of its date
        return "record", "dated-file"
    return "reference", "default"


def block_preset(heading: str) -> str | None:
    """A heading word overrides the root default for its blocks (docs/09 §5.1); None = inherit."""
    for level in reversed(heading.split(" / ")):  # the nearest heading decides; parents only when it is silent
        w = words(level)
        if has(w, {"decision", "decisions", "rule", "rules"}, "decision"):
            return "decision"
        if has(w, {"proposal", "plan", "design", "next", "todo", "options"}, "proposal"):
            return "proposal"
        if has(w, {"status", "findings", "results", "report", "log"}, "record"):
            return "record"
    return None


def main(data: Path) -> None:
    manifest = {d["id"]: d for d in json.loads((data / "manifest.json").read_text())["docs"]}
    drafts = {x["id"]: x for f in sorted((data / "drafts").glob("batch-*.json")) for x in json.loads(f.read_text())}
    labels = {}
    for line in (data / "labels.jsonl").read_text().splitlines():
        r = json.loads(line)
        if r.get("task") == "doc" and not r.get("skip"):
            labels[r["id"]] = r  # latest wins
    per_doc, n_blocks, mixed, explicit, rows, long_code, signals = {}, [], 0, 0, 0, 0, Counter()
    archived = 0
    for doc_id, m in manifest.items():
        try:
            text = Path(m["path"]).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        meta, body = frontmatter(text)
        title = next((ln for ln in body.splitlines() if ln.startswith("# ")), "")
        root, signal = root_preset(m["path"], meta, title)
        signals[signal] += 1
        archived += "archive" in {x.casefold() for x in Path(m["path"]).parts}
        bl = blocks(body)
        n_blocks.append(len(bl))
        classes = {root}
        for b in bl:
            override = block_preset(b["heading"])
            explicit += override is not None
            rows += b["kind"] == "row"
            long_code += b["kind"] == "code" and len(b["text"]) > MAX_BLOCK
            classes.add(override or root)
        mixed += len(classes) > 1
        per_doc[doc_id] = root

    def agreement(ref: dict, subset=None) -> dict:
        pairs = [(V1[r], per_doc[i]) for i, r in ref.items() if i in per_doc and (subset is None or i in subset)]
        pred = lambda p: "reference" if p == "decision" else p  # v1 cannot tell decision from reference
        ok = sum(1 for want, got in pairs if want == pred(got))
        confusion = Counter(f"{want}->{pred(got)}" for want, got in pairs if want != pred(got))
        return {"n": len(pairs), "agree": round(ok / len(pairs), 3) if pairs else None,
                "misses": dict(confusion.most_common(6))}

    blind = {i for i, m in manifest.items() if m["blind"]}
    report = {
        "documents": len(per_doc),
        "blocks_per_doc_median": median(n_blocks), "blocks_total": sum(n_blocks),
        "id_table_rows": rows, "oversized_code_blocks": long_code,
        "blocks_with_heading_override": explicit,
        "docs_with_more_than_one_class": mixed, "docs_in_archive_paths": archived,
        "root_signal": dict(signals.most_common()),
        "root_class": dict(Counter(per_doc.values()).most_common()),
        "vs_operator_labels": agreement({i: r["values"]["category"] for i, r in labels.items()}),
        "vs_drafts_all": agreement({i: d["category"] for i, d in drafts.items()}),
        "vs_drafts_blind": agreement({i: d["category"] for i, d in drafts.items()}, blind),
    }
    print(json.dumps(report, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main(Path(sys.argv[1]))
