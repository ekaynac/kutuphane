# Labelling v4 — plan

**Status:** PLAN 1.0, approved by the operator on 2026-10-22 (D59). §6 records the decisions.
**Basis:** the kstd draft 0.2 (`docs/11`), its L0 manifest (PR #42), and the experience of labelling v1/v2.
**Language:** ASD-STE100 Simplified Technical English.

## 1. Purpose

Labelling v4 gives **ground truth** for the facts that kstd needs. With this ground truth we can measure the systems that *propose* these facts automatically: rules, Laya, Jev, and an LLM. The goal is that an organization writes its L0 manifest and its statements in minutes, from proposals, and only confirms them.

v1 and v2 labelled human categories and facets. v4 labels only the **kstd fields that change a decision** (canon D53).

## 2. What is labelled (per file = per kstd item)

| Field | Values | Why it matters | Who can propose it |
|---|---|---|---|
| **origin** | human, model, unknown | notice; training profiles | rules (path, frontmatter, tool markers), System-One models |
| **personal_data** | yes, no, unknown | export gate; erasure scope | rules (patterns: e-mail, phone, ID numbers), models |
| **ai_use** | search, ai_input, train: y/n | index and model gates | rules from path and handling; mostly an organization policy |
| **handling** | export normal/restricted; route cloud_ok/local_only | the existing gates (v1/v2 measured these well) | rules, models |
| **acceptance** | accepted, pending, withdrawn | eligibility for ordinary use | rules (status words, archive paths, dates), models |
| **mandate** | rule authority yes/no | citation as a requirement | rules (canon, policy, decision headings), models |
| **valid time** | valid_from / valid_to, or open | "not current" | rules (dates in names and text), models |
| **applies_to** | free text, optional | applicability | models (extraction) |

**The license is not labelled.** It is an organization decision. It is set once for a folder and not inferred from content.

**Mixed files** (45 % of the corpus mixes section types; v2 measurement): the labeller can mark "this file needs to be split". In kstd a split is a **profile** decision, not a core decision. The mark only measures how often a split is necessary. The labeller does not draw boundaries.

## 3. Method

1. **Blind first answer.** About 30 % of the files show no proposals (D43). For the other files, the page selects the rule proposal, and it shows the Laya proposal beside it (operator decision, 2026-10-15).
2. **One screen per file:** the file text, the 8 fields, and a "needs split" mark. Target: below 45 s for each file.
3. **Proposers measured after labelling:** rules, Laya (local), Jev (hosted, only `normal` + `cloud_ok` files after their label), and one local LLM through LLMDAP.
4. **Measures for each field:**
   - agreement with the human label;
   - on the gate fields (personal_data, handling, ai_input): **missed restrictions**, which must be close to zero;
   - false authority (`accepted` + mandate when the human said otherwise);
   - time for each file.
5. **Output:** a proposed `kstd.yaml` for each folder. It is checked with `kstd-check` and compared with the human labels.

## 4. Corpus

- The same 163-document corpus (149 served). The labels from v1 and v2 stay stored and are mapped where possible: handling maps directly; the v2 root presets give a first proposal for acceptance and mandate.
- New: a small public set with **known** rights and origin (for example CC-BY documents, and model-generated texts that are known to be model-generated). It measures the origin and rights proposers on facts that are not opinions.

## 5. Work and order

1. Rule proposer v4 for the 8 fields, measured on the v1/v2 labels (no new page).
2. Labelling page v4 (from v2: same server, same blind logic; new form).
3. The operator labels. Shadow runs for Laya and Jev, as in v2.
4. Report: proposer quality for each field, and a recommendation of which proposals can be accepted automatically under a delegation (D56), and which must always be confirmed by a person.

## 6. Operator decisions (2026-10-22)

1. **Scope:** the 8 fields in §2 are correct.
2. **Granularity:** one label set per file, with a "needs split" mark. Agreed.
3. **Public set with known facts:** yes. Add a small public test set.
4. **Local LLM proposer:** `RadixArk/Qwen3.8-27B-NVFP4` on the Spark. It is already served by the local vLLM (port 8000), so no new GPU process is needed. LLMDAP gets a chat route to it. The route must reach the host from the `models` network; that change goes in the labelling v4 compose work.
5. **New input before labelling starts:** the W3C community-group landscape (D59, `docs/13`). `docs/13` §5 proposes field changes (origin `assisted`, personal data `synthetic`, "not stated" kept apart from `n`, a DPV legal-basis list) and lists the public test set candidates. These wait for the operator. The page is built after that decision.
