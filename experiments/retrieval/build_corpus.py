"""M0 public half (D41 b): turn `mtntasci/turkish-legal-rag` (CC BY 4.0, pinned revision) into one markdown file
per law, one `## Madde N` heading per article, so the product's own chunker cuts at article boundaries.

Usage: python -I build_corpus.py <statute_chunks.csv> <out_dir>
Data stays outside git (attribution: mtntasci/turkish-legal-rag, CC BY 4.0; texts: mevzuat.gov.tr, FSEK md. 31).
"""
import csv
import re
import sys
from collections import defaultdict
from pathlib import Path

csv.field_size_limit(sys.maxsize)


def article_key(madde_no: str):
    m = re.match(r"(?i)\s*(ek|geçici)?\s*(\d+)", madde_no)
    return (m.group(1) or "", int(m.group(2))) if m else ("~", 0)


def slug(name: str) -> str:
    table = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")
    return re.sub(r"[^a-z0-9]+", "-", name.translate(table).lower()).strip("-")[:80]


def main(src: str, out: str) -> None:
    laws = defaultdict(dict)
    for row in csv.DictReader(open(src, encoding="utf-8")):
        if row["chunk_strategy"] == "statute_full" and row["context"].strip():
            laws[row["kaynak"]].setdefault(row["madde_no"], row["context"].strip())
    target = Path(out)
    target.mkdir(parents=True, exist_ok=True)
    for law, articles in sorted(laws.items()):
        parts = [f"---\ntype: reference\ntitle: {law}\n---\n", f"# {law}\n"]
        for no in sorted(articles, key=article_key):
            parts.append(f"## Madde {no}\n\n{articles[no]}\n")
        (target / f"{slug(law)}.md").write_text("\n".join(parts), encoding="utf-8")
    print(f"{len(laws)} laws, {sum(len(a) for a in laws.values())} articles -> {target}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
