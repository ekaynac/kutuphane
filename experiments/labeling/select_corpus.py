"""Select a stratified, secret-scanned labelling corpus (D41a) from read-only source repos.

Usage: python3 -I select_corpus.py <candidate_list.txt> <out_dir>
Writes <out_dir>/manifest.json (path, sha256, group, size, blind flag) and
<out_dir>/docs.json (id, path, group, excerpt) for the labelling page.
"""
import hashlib
import json
import random
import re
import sys
from pathlib import Path

SEED = 20261012
EXCERPT_CHARS = 3000
BLIND_SHARE = 0.30
MAX_BYTES = 400_000

# (group, path regex, quota or None for all)
GROUPS = [
    ("agent-instructions", r"/CLAUDE\.md$|/AGENTS\.md$", None),
    ("readme", r"/README\.md$", 14),
    ("standards", r"/inframedic/inframedic/standards/", None),
    ("etc", r"/(nobetci|nobetci-dev)/etc/", None),
    ("evidence-handoff", r"/docs/(evidence|handoff)/|/nobetci/handover/", 12),
    ("ops", r"/ops/obligations/|/docs/lab/", None),
    ("nobetci-docs", r"^/home/mega/nobetci/docs/", 10),
    ("archive", r"/nobetci-dev/docs/archive/", 8),
    ("plans-specs", r"/inframedic/docs/(plans|specs|sources)/|^/home/mega/inframedic/docs/[^/]+\.md$", 12),
    ("scratch-plans", r"/inframedic/scratchpad/", 12),
    ("demo-reports", r"/inframedic/demo/reports/", 10),
    ("notes", r"/inframedic/docs/notes/", 30),
    ("dev-docs", r"^/home/mega/nobetci-dev/docs/[^/]+\.md$", 35),
]
EXCLUDE = re.compile(r"/build/|/dash/ui-src/|/t/fixtures/")
SECRET = re.compile(
    r"(?i)(password|passwd|secret|token|api[_-]?key|bearer)\s*[:=]\s*['\"]?[A-Za-z0-9_\-/+]{12,}"
    r"|-----BEGIN [A-Z ]*PRIVATE KEY-----"
    r"|\b(sk|ghp|gho|github_pat|xox[bp])[-_][A-Za-z0-9_]{16,}"
)


def main(cand_file: str, out_dir: str) -> None:
    rng = random.Random(SEED)
    paths = [p for p in Path(cand_file).read_text().split("\n") if p and not EXCLUDE.search(p)]
    taken, rejected, manifest, docs = set(), [], [], []
    for group, pattern, quota in GROUPS:
        rx = re.compile(pattern)
        pool = sorted(p for p in paths if p not in taken and rx.search(p))
        rng.shuffle(pool)
        picked = 0
        for path in pool:
            if quota is not None and picked >= quota:
                break
            raw = Path(path).read_bytes()
            if len(raw) > MAX_BYTES:
                continue
            text = raw.decode("utf-8", errors="replace")
            if SECRET.search(text):
                rejected.append(path)
                continue
            taken.add(path)
            picked += 1
            doc_id = f"d{len(manifest) + 1:03d}"
            manifest.append({
                "id": doc_id, "path": path, "group": group, "bytes": len(raw),
                "sha256": hashlib.sha256(raw).hexdigest(),
            })
            docs.append({"id": doc_id, "path": path.replace("/home/mega/", ""), "group": group,
                         "chars": len(text), "excerpt": text[:EXCERPT_CHARS]})
    blind = set(rng.sample([m["id"] for m in manifest], round(len(manifest) * BLIND_SHARE)))
    for m in manifest:
        m["blind"] = m["id"] in blind
    for d in docs:
        d["blind"] = d["id"] in blind
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "manifest.json").write_text(json.dumps(
        {"seed": SEED, "blind_share": BLIND_SHARE, "secret_rejected": len(rejected), "docs": manifest},
        ensure_ascii=False, indent=1))
    (out / "docs.json").write_text(json.dumps(docs, ensure_ascii=False))
    print(f"selected={len(manifest)} blind={len(blind)} secret_rejected={len(rejected)}")
    for g, *_ in GROUPS:
        print(g, sum(1 for m in manifest if m["group"] == g))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
