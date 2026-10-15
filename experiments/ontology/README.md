# Ontology v2: rule proposer measurement (docs/09 §5.7)

`propose.py` contains:
- the deterministic **block rule** (docs/09 §1.1);
- the **rule-based proposer** (§5.1): document root preset from path, file name, frontmatter `type` and title, plus a block override from heading words.

It runs locally and uses no model. It prints counts only, never document text.

```sh
python -I propose.py ../labeling/data
```

**Mapping.** v1 labels are mapped to v2 preset classes:
- K3 → agent;
- K5 → record;
- "Does not fit" → proposal;
- every other category → reference.

v1 has no decision class, so a proposed `decision` compares as `reference`.

## Results — 2026-10-15 (163 documents, development corpus)

| Compared with | n | Agreement |
|---|---|---|
| Operator labels (latest per document) | 12 | **0.92** (1 miss: reference → proposal) |
| v1 drafts, all | 163 | 0.80 |
| v1 drafts, blind slice | 49 | 0.75 |

**Corpus counts:**
- Blocks: 5,485 in total, median 19 per document. 676 are id-table rows. The counts are after the block-rule fixes of Astra review #7 (see the end of this file).
- Root signals:
  - record word: 73;
  - proposal word: 50;
  - decision word: 13;
  - instruction: 11;
  - dated file: 9;
  - **no signal (left for the model): 7**.
- **73 of 163 documents (45 %)** contain more than one class by their heading words. This is the mixed-document finding of the operator, now measured.

**What changed from the first run** (0.75 / 0.60 / 0.47):
- two bugs fixed:
  - hyphenated file names were one word;
  - only the last three path parts were read;
- Turkish stems are matched as prefixes (`incelemesi`, `önerisi`, `kararları`);
- a dated file with no other signal is a snapshot (`as_of`).

The rules were kept generic: none was fitted to a single document.

**Limits:**
- The v1 drafts are model guesses, not ground truth.
- The operator set is 12 documents.
- The development corpus has strong path conventions, so another corpus can score lower.
- The real measure is the v2 blind slice, after labelling.
- The most common remaining miss is reference ↔ record (11 documents): undated notes and descriptive documents.

**Block-rule fixes after Astra review #7** (they match docs/09 §1.1):
- a code fence takes the paragraph immediately before it;
- an id table needs every data row to have a unique id, and it keeps its header as its own block;
- an ordinary long table splits at row boundaries and repeats its header;
- a document without headings has one block for each paragraph;
- the nearest heading decides the block proposal.

The root-preset agreement did not change.
