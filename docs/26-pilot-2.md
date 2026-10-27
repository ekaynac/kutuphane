# Pilot 2 — a private canon as a book, local only

Real-use pilot 2 (`docs/15` §4, step 4). Date: 2026-10-27. Branch: `docs/pilot-2`.

**Privacy.** The source is a private repository. This page gives only measurements and gaps. It names no source
file, customer, site or device. The full report (file names, questions, answers, note texts and the operator
questions) is on this machine only, in the git-ignored `research/pilot-2/`.

## 1. Setup

- **Source:** a local copy (outside this repository) of one release of the private inframedic project: the 20
  shipped canon documents (design notes and operator documents) and the 13 platform rule files (one diagnostic rule
  per file, with a source header). 33 Markdown files, 0.5 MB. The release held back 11 other canon documents, so
  they are not in the book.
- **Kütüphane:** the CLI and the server on the host, main database `kutuphane`. Ingest, questions and MCP calls ran
  on `355b1c7`; the main checkout moved to `c9fa3eb` (migration 027) during the run, so the curator CLI calls ran on
  `c9fa3eb`.
- **Models (all local):** as in Pilot 1 (`docs/18` §1): LLMDAP routes `chat` (Qwen3.8-27B-NVFP4 on the host vLLM),
  `emb` (bge-m3, CPU), `rerank` (bge-reranker-v2-m3, CPU). The host CLI reached LLMDAP at its container address,
  because LLMDAP has no host port.
- **Book:** `inframedic-canon`, `--sensitivity normal --egress local_only --protection standard`.
- **Journal:** `inframedic-memory` (`--search y --ai-input y`, train `n`, `local_only`).
- **Principals:** `agent:inframedic-orch` (an orchestrator: `propose` and `read` on the journal, `read` on the book)
  through MCP 2026-07-28 with a development token; `user:pilot` (curator) through the CLI.

## 2. kstd values

| Field | Value | Evidence |
|---|---|---|
| License | `unknown` | The repository has no license file. Question to the operator. |
| Holder, issuer | the operator | The operator owns the repository. |
| `ai_use` | `search: y`, `ai_input: y`, `train: n` | Search and AI input as the operator allowed. Training was not stated, so the safe value `n` is used. |
| Personal data | default `no`; 1 rule file `unknown` | A scan for IPv4 and e-mail addresses found one private IPv4 address (in a rule file's source header) and loopback addresses only. |
| Origin | `model` for 33 of 33 files | 66 of 66 commits that touch these files have a `Co-Authored-By: Claude` trailer. No reviewer is named, so no file is `assisted`. |
| `valid_from` | the date in the file name (15 notes) | |
| `applies_to` | `platform <name>` (13 rule files) | the folder name |

`kstd-init`: 0.3 s, all 33 items `origin: unknown`, no secret finding. `kstd-check`: PASS (33 files) with one
warning: "no default license: derivation and forwarding need a license for each file".

**Open questions for the operator** (details in the private report): the license; `train`; whether customer and
site names and the private address are personal data or fleet data; whether a doctrine that the operator ratified
in writing is `assisted` with the operator as `reviewed_by`.

## 3. Load results

| Book | Files | Passages | Ingest with indexing | Notes |
|---|---|---|---|---|
| `inframedic-canon` | 33 | 668 (mean 741 characters, min 4, max 4,786) | 581 s (about 1.15 passages/s) | 668 vectors added, 0 failed, 0 quarantined, 0 findings |

- Rule files: 35 passages (mean 535 characters). Documents: 633 passages (mean 753 characters).
- 33 passages are shorter than 50 characters (a heading alone or `---`), and 71 are shorter than 120 characters
  (G27).
- In all 13 rule files, passage `#0` is only the source header (vendor document and URL). No later passage holds
  the source (G28).

## 4. Agent memory

The orchestrator searched the book, proposed notes with passage citations, linked a duplicate, read its memory and
recorded an outcome. All calls went through MCP.

| Step | Count | Time per call |
|---|---|---|
| `propose_note` | 9 notes (5 `finding`, 1 `convention`, 1 `decision_proposal`, 1 `lesson`, 1 `dead_end`; one finding is a reworded duplicate), 12 passage citations, 1 `derived_from` link to a passage; 2 more calls with the same bytes | 0.23–0.52 s (new), 0.06–0.08 s (same bytes again) |
| `link_notes` (`same_as`) | 1 | 0.05 s |
| `query_notes` (`current`, `open`, `since`, `text`) | 5 | 0.03–0.11 s |
| `open_citation`, `neighbours` | 2, 3 | 0.03–0.04 s |
| `record_outcome` | 1 | 0.05 s |

- **Duplicates:** a reworded finding got a `vector` candidate with similarity 0.948. The agent linked it with
  `same_as`. The same bytes proposed again gave `status: existing` and `recurrence: 3` (the cluster).
- **Curation (CLI, `note standing`):** 4 changes (3 `approved`, 1 `rejected` as a duplicate), 0.24–0.28 s each. To
  check a note, the curator read 1–2 cited passages (1,109–1,659 characters). The curator found the pending refs
  with the agent's `query_notes`, because the CLI cannot list them (G36).
- After the curation, `query_notes` (`current`) gives 3 notes: 2 findings and 1 convention. With the convention
  approved, `guard_due` is `false` for its class.

## 5. Questions

Nine questions, all through MCP `ask_library` (no filter), then `search_library` (`k` 8) with the same text.
Questions 1–6 are the use cases of the private fit report (`docs/15` §4), in a form that an orchestrator or a
technician asks. Questions 7–8 are in Turkish. Question 9 is a control question. Each answer was checked against
its passages and against the source repository.

| # | Kind | Language | Expected evidence | Result | `ask` | `search` |
|---|---|---|---|---|---|---|
| 1 | Is a host with a given monitor state down? | EN | 1 rule file | Correct; 1 citation. The source header (rank 2 in the evidence) is not cited (G28). | 29 s | 27 s |
| 2 | Which source supports a fault classification, and can we use it? | EN | a design note | Correct: the classification, its source and its ratification; 3 citations. "Can we use it" is answered as the decision status; the license (`unknown`) is only in the item information. | 35 s | 18 s |
| 3 | Which check covers a device wear signal, and did it work on device model M? | EN | 1 rule file | Correct for the signal (2 passages). It says correctly that the passages do not show the result on model M: runbook results are not files. | 40 s | 16 s |
| 4 | What does section S of a held-back design document require? | EN | none (held back) | Partly correct, second-hand. Another document quotes section S. The answer presents these quotes as the section, and gives a proposed amendment from that document as a rule of S. It does not say that the document is not in the library (G29). | 19 s | 15 s |
| 5 | Which artifact is the template for a new platform? | EN | 1 design note | Partly wrong. Passage 1 of the evidence names the template. The answer gives a general description and ends with a grouped "Sources: [3], [4], [6]" (G30). | 19 s | 14 s |
| 6 | How does an isolated site import and approve the signed canon package? | EN | none (held back) | Wrong topic. It describes another signed bundle (model releases) as the canon package (G29). | 33 s | 15 s |
| 7 | Is a vendor warning status a failure, and must we open a case? | TR | 1 rule file | Correct; 1 citation. | 40 s | 23 s |
| 8 | Is an appliance that sends no alerts healthy? | TR | 1 rule file | Correct; 2 citations. | 38 s | 41 s |
| 9 | A vendor default setting that is not in the book | EN | none | `not_in_library` — correct. | 17 s | 30 s |

**Quality:** 5 correct (1, 2, 3, 7, 8), 2 partly wrong (4, 5), 1 wrong (6), 1 correct `not_in_library` (9). Every
listed citation supports the words of its sentence; the errors in 4–6 are in what the answer claims about the
question. Both questions whose evidence is held back (4, 6) got an answer instead of `not_in_library`. No passage
was withheld.

### 5.1 Time per stage

Seconds, from the end times of the model calls of each answer (`model_call`): query embedding / rerank (with the
hybrid search) / chat (the answer; for 2, 7 and 8 also the question translation).

| # | Embedding | Rerank | Chat | Total |
|---|---|---|---|---|
| 1 | cached | 24.6 | 4.2 | 28.9 |
| 2 | 0.5 | 23.7 | 10.7 | 34.9 |
| 3 | 0.5 | 33.7 | 5.9 | 40.1 |
| 4 | 0.2 | 14.4 | 3.9 | 18.5 |
| 5 | 0.1 | 12.8 | 5.9 | 18.8 |
| 6 | 0.3 | 25.9 | 6.4 | 32.6 |
| 7 | 0.6 | 24.3 | 15.6 | 40.5 |
| 8 | 0.5 | 17.7 | 20.1 | 38.3 |
| 9 | 0.3 | 14.9 | 1.8 | 17.1 |

`ask`: mean 30.0 s, median 32.6 s (Pilot 1 v2: mean 63 s on 10,206 passages). The CPU reranker takes 46–87 % of
each answer (G26 stays open). `search_library`: 13.7–40.5 s, also mostly rerank; 5.0 s for a repeated question with
a path filter.

## 6. Gaps found

Continuing `docs/15` §3 and `docs/18` §5. No code was changed in this pilot.

| # | Gap | Evidence | Effect | Size |
|---|---|---|---|---|
| G27 | **A heading alone becomes a passage.** The chunker cuts before a heading even when the section body goes to the next passage. | 33 of 668 passages are shorter than 50 characters (for example `## 5. Authority`, `---`); 71 are shorter than 120. None was in the 72 evidence slots of the 9 answers. | Embedding calls for no content; the next passage loses its heading. | small |
| G28 | **A source header is a separate passage.** The source line of each rule file (an HTML comment with the vendor document and URL) is passage `#0`; the rule is `#1` and later. | 13 of 13 rule files; no later passage contains the source. Answers 1, 7 and 8 cite the rule passage only; in answer 1 the header was evidence rank 2 and was not cited. | A citation of a rule does not carry its vendor source. "Which source supports X?" depends on retrieving `#0` too. | small (attach a leading source comment to the next passage, or keep it as item information) |
| G29 | **Near-topic evidence gives a confident answer.** When the document that the question names is not in the library, the answer uses another document that quotes it or a similar topic, and does not say so. | Question 4: second-hand quotes, and a proposed amendment given as a rule of the section. Question 6: a different signed bundle described as the asked package. Both evidence sets have no passage of the named document. | The agent cannot see that the source is absent; a held-back document seems to be in the library. | medium (answer step: name the asked source; say when the evidence is only a reference to it) |
| G30 | **The answer misses the decisive top passage.** | Question 5: evidence passage 1 names the template; the answer is general and cites 3 other passages in one grouped line at the end. | A direct question gets an indirect answer. | medium (answer quality; measure with more questions) |
| G31 | **`guard_due` counts the rule notes of a class.** `class_count` counts every `same_as` cluster with the `class_key`, also the `convention` and `decision_proposal` that answer the problem. | One finding, then its convention with the same `class_key`: `class_count: 2`, `guard_due: true`. Then a decision proposal: `class_count: 3`. Only one finding cluster existed. | The guard signal fires on the first finding when the orchestrator follows the guide (propose the convention with the `class_key`). | small (count `evidence` clusters only) |
| G32 | **A citation is not a link.** `neighbours` from a passage finds notes with `about` or `derived_from` links only (as documented in `guide/mcp.md` §5.14). | `neighbours` (`current` and `open`) of a rule passage that 4 notes cite (2 approved, 1 pending, 1 rejected): 0 nodes. The passage with a `derived_from` link: 1 node. | An orchestrator cannot go from a passage to the notes that cite it, unless it sends each citation again as an `about` link. | small |
| G33 | **The guide does not say that notes are not searched.** Notes are not in `search_library` or `ask_library` (R1 operator decision, `docs/24`). | `search_library` with `book: [inframedic-memory]` returns an empty list (0.3 s) with no notice. Question 1 could not use the approved convention for the same case. | An agent reads the empty result as "no notes". | small (guide); decision (notes as evidence in answers) |
| G34 | **`kstd-init` on a copy loses the origin evidence (G6).** `docs/15` says to run `kstd-init` on a copy, and the copy has no git history. | 33 of 33 files `origin: unknown`, although 66 of 66 commits have a model trailer. A separate script read the source repository to set `model`. | Every file of a copy starts as `unknown`; the origin labels need the source repository. | medium (part of G6: let the proposer read a source repository and commit) |
| G35 | **No personal-data or fleet-data scan at ingest.** Ingest scans for credentials only. | The shipped set passed the release's own detectors, but 3 files (11 passages) name a customer, rule headers and notes name site devices, and 1 rule file has a private IPv4 address. The rule files have no detector verdict in the release manifest. A manual scan found them. | `personal_data` depends on a manual check. | medium (detectors like private IPv4, e-mail and names, as findings for `kstd-init`) |
| G36 | **The curator CLI cannot list pending notes.** `note` has `standing`, `rollback` and `import` only. | The curator found the refs and the cited passages through the agent's `query_notes` and `open_citation`. | Curation needs a token or another tool. | small (the D72 curator queue covers it) |
| G37 | **A `license: unknown` source does not limit derivation.** `kstd-check` warns that "derivation and forwarding need a license"; the guide says the license is only shown. | A note with a `derived_from` link to a passage of this book (license `unknown`) was created with no notice. | The warning and the behavior do not agree. | decision (what derivation needs at L0) |

## 7. Recommendations

1. Answer step (G29, G30): when the question names a document or a section, check that the evidence contains it;
   else answer `not_in_library` or say that the evidence only refers to it. Add questions 4–6 to the answer test
   set.
2. Fix the small chunking gaps (G27, G28) before the next markdown book with source headers.
3. Count only `evidence` clusters for `guard_due` (G31), and let `neighbours` follow citations, or say in the
   guide that an `about` link is needed (G32, G33).
4. Extend the G6 rule proposer to read a source repository (G34), and add personal-data and fleet-data findings to
   `kstd-init` (G35).
5. Decide G37 with the operator's license question.
6. Then run the shadow comparison with inframedic's own retrieval over MCP (`docs/15` §4).

## 8. After the fixes

Branch `fix/pilot2-gaps` ([#118](https://github.com/ekaynac/kutuphane/pull/118)). Each fix has a regression test
that failed on `main` first. G34 and G35 are not in this branch; `kutuphane curator queue` (#117) closes G36. G37
stays open: it needs the operator's decision.

| Gap | Change | Test |
|---|---|---|
| G27 | A markdown cut that holds only headings or `---` joins the passage after it (the passage before it at the end of a file). A heading is an ATX heading outside a code fence, so `#41` and a `#` comment in a fence are text. Every other passage keeps its text, so its vector is copied: a vector is now copied from any profile of the same book. Chunker version 5. | `test_a_heading_alone_is_not_a_passage`, `test_attaching_a_heading_changes_no_other_passage`, `test_a_new_chunker_reuses_the_vectors_of_unchanged_passages` |
| G28 | Choice: a leading source comment joins the passage after it (not item information), so the rule passage holds its source. An HTML comment alone is handled as a heading alone. | `test_a_heading_alone_is_not_a_passage` |
| G31 | `class_count` counts clusters of evidence notes only (`finding`, `lesson`, `dead_end`, `test_result`). | `test_class_count_counts_evidence_clusters_only` |
| G32 | `neighbours` from a passage also gives the notes that cite it (edge `cites`), with the same gates as links. Migration 028 adds an index. | `test_neighbours_of_a_passage_follow_its_citations` |
| G33 | The guide says that notes are not in `search_library` or `ask_library`. A readable journal in the `book` filter gives the error `journal: use query_notes …`. | `test_a_journal_in_the_search_filter_gives_a_notice` |
| G29 | Before the model call, a document (a file name or a name before `§`) and a section (`§5.3`, `section 5.3`) that the question names are checked against the passage paths and the line starts of the passages. A missing one is named in the prompt. The prompt says: answer only from the named document or section, or say that the passages only refer to it. | `test_a_named_source_is_checked_against_the_evidence` |
| G30 | The prompt says: read passage `[1]` first and base the answer on it when it answers the question; put each `[n]` after its claim; answer the part that the passages answer. | `test_the_prompt_asks_for_the_top_passage_and_inline_sources` |

**Answers (G29, G30).** The 9 questions of section 5 again, through `ask_library`'s code path on the main database,
same book and local models, `main` and the branch on the same day. The model is not deterministic, so questions 3–6
also ran 3 to 5 more times with each code. Counts only; the answers are in the private report.

| Measure | `main` | Branch |
|---|---|---|
| Full runs of the 9 questions: acceptable answers (correct, or a correct `not_in_library`) | 6 of 9, 6 of 9 | 8 of 9, 7 of 9 |
| Question 4 (a named section of a held-back document): acceptable | 0 of 5 | 5 of 5 (1 `not_in_library`, 4 "the passages only refer to it") |
| Question 6 (a similar, other bundle): acceptable | 0 of 5 | 0 of 5 |
| Question 5 (the top passage names the template): the answer names it | 4 of 7 | 4 of 7 |
| Question 3: a false `not_in_library` | 3 of 7 | 3 of 7 |
| An answer that ends with a grouped "Sources" line | 0 of 31 answers | 0 of 31 answers |

- G29 is closed for a question that names the document or the section: the check finds it before the model call.
  It stays open for a question that names a similar thing without a document name (question 6): the prompt rule
  alone did not stop the answer about the other bundle.
- G30: no measured effect. The template was named in 4 of 7 runs with both prompts. Question 3's false
  `not_in_library` is the same on `main`: model variance, not this change.
- **Pilot 1, English question 2** (`docs/18`): the evidence is the same with both codes and has no passage that
  gives the reason. `main` answers "the passages do not state why"; the branch gives the same content (twice) or
  `not_in_library` (twice, with an earlier prompt wording). The gap is in retrieval (G19), not in the answer step.

**Re-index (not done).** No book of the main database was ingested again. A read-only comparison of the stored
content with chunker 5:

| Book | Files that change | Passages | Shorter than 50 characters | Vectors to embed (others copied) |
|---|---|---|---|---|
| `inframedic-canon` | 26 of 33 | 668 → 585 | 33 → 0 | 77 of 585 |
| radar documents | 57 of 83 | 2,601 → 2,321 | 102 → 1 (a one-line file) | 481 of 2,321 |
| radar briefs, radar news, `ornek` | 0 | the same | 0 | 0 |

An ingest of any book gives a new profile id, so every passage handle changes; old handles still open. The 12
passage citations of the journal stay on the old passages, so `neighbours` from a new handle does not find those
notes. The longest new passage is 4,825 characters: a heading can make a passage longer than `MAX_CHUNK_CHARS`
(4,800) by its own length.
