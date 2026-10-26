**Yes: stop the current sequential labelling queue and curate first.** Your three-part direction is sound. The main correction is that **declared metadata, human judgments and authorized decisions are three different targets**.

I read the requested files and verified external sources. I did not read `experiments/labeling/data` or `research/`, and changed nothing.

1. **P0 — Keep three sets, with separate scores.**  
   Use automatic gold for extracting source declarations; scenarios for decision-rule conformance; human review for interpreting evidence. Never combine their accuracies. A source’s `status: accepted` is extractable gold; accepting it locally requires a policy and an authorized issuer. Likewise, signatures establish attribution and integrity, not truth or local trust. “Automatic gold” still needs an independently checked source adapter, but no repetitive operator confirmation.

2. **P0 — Correct the unit without banning records or configuration.**  
   The evaluation unit should be **one meaningful task with sufficient evidence**: a document, a skill package, a replacement chain, or a record with its provenance. Keep file digests and rights underneath that unit. A radar record can be meaningful—the pilot actually retrieves them—but 120 identical model-field confirmations add little. A skill folder should be one activation case, retaining each file’s licence. Group copies, derivatives, revisions and clean/hostile twins into one family for splitting and reporting.

3. **P0 — Repair measurement before collecting more labels.**  
   In [propose.py](/home/mega/kobra/experiments/labeling_v4/propose.py:176), `known.acceptance` can become the prediction and then the evaluation target. That measures copying supplied state, not independent inference. Separate raw evidence, reference answers and policy inputs. Give both proposers identical evidence and score the same items; docs/16 currently reports different denominators. Measure extraction accuracy, abstention, unsupported assertions, missed restrictions, false authority and false denials separately. Include a metadata-only baseline. Hiding metadata should test appropriate abstention, not demand impossible provenance detection.

4. **P0 — Resolve ontology ambiguities before calling answers gold.**  
   Four issues already matter:
   - [§4 rule 6](/home/mega/kobra/docs/11-standard-draft.md:63) removes rule authority for stale imported status; §6 also lists stale status as a suspension trigger. Specify when each applies.
   - `stale_after` is a freshness deadline, not automatically `valid_to`; [the proposer currently conflates them](/home/mega/kobra/experiments/labeling_v4/propose.py:190).
   - A named approver, merge or upstream reviewer does not establish substantive review of this exact output.
   - Radar’s third-party inputs and missing generator versions remain unresolved in [G24–G25](/home/mega/kobra/docs/18-pilot-radar.md:117). Those outputs are not yet reliable `tool` gold.

5. **P0 — Make question coverage an admission requirement.**  
   Each case needs: research question, operation, evidence available, fact under test, expected result/reason, and what finding would challenge the ontology. Cover index, model input, export, activation, authority, supersession, trust and erasure—including successful uses, not merely denials. Separate questions about **frequency**, **predictability**, **conformance** and **whether the rule is desirable**. These need different evidence.  
   Docs/16 §3 reproduces only ten themes; the full Q1–Q27 list is in excluded research material. A complete numbered coverage claim therefore remains unverified.

6. **P1 — Prefer sources with explicit relationships; preserve their semantics.**  
   Start with PEPs, KEPs, REUSE and signed nanopublication chains. Keep `Updates`, `Obsoletes`, retraction and supersession distinct. Do not convert publication dates into validity dates, listed reviewers into completed reviews, or citations into complete derivation lineage. OKF and C2PA add useful interoperability cases, but their example files are examples, not evidence of real organizational governance. No listed source automatically supplies your node’s trust configuration, mandate, activation permission or processing-specific legal basis.

7. **P1 — Build 72 scenario requests from 24 base cases.**  
   Each base has three variants: a baseline, one consequential change, and one irrelevant change. Supply artifacts, signed statements, policy, trust configuration, evaluation time and one request. Include transitive restricted inputs, missing ancestors, cycles, partial supersession, expired delegations, key rotation, untrusted loosening versus untrusted withdrawal, synthetic-person claims, quoted attacks versus executable instructions, access-tag changes and incomplete erasure. Assert notices and resulting state as well as `permit/deny/escalate`. Split by base family; keep held-out cases sealed.

8. **P1 — Separate conformance answers from judgments about the rule.**  
   A domain owner first records the desired operational outcome and rationale without seeing engine output. A second reviewer independently derives the result from the written specification. The implementer must not generate expected answers with the implementation under test. Disagreement becomes a specification issue, not a forced label. Use external protocol fixtures, harmless mutations and invariants—such as irrelevant filename changes preserving decisions. Conformance is necessarily relative to the specification; independent operational judgments test whether that specification is useful.

9. **P1 — Limit the first human round to 120 complete cases.**  
   Allocate 30 each to review evidence, instruction safety, normative meaning/scope, and personal-data identifiability. Within each group select **5 calibration + 15 disagreement/uncertainty + 10 randomly sampled cases**: 20 calibration, 60 challenge, 40 probability-sampled overall. Freeze selection and proposer versions. All first judgments are blind; reveal suggestions afterward to measure correction time. Have a second person independently label the 40 random cases plus 20 difficult cases; adjudicate disagreements. This is a diagnostic pilot, not evidence of a near-zero dangerous-error rate. Humans assess available evidence; they cannot infer undocumented review or prove a person fictitious from prose alone.

10. **P0 — Replace the page’s queue and authorization language.**  
    Show the operation, complete document/package, relevant provenance and the reason the case was selected. Ask only unresolved questions; provide “insufficient evidence” and an evidence pointer. Replace the compulsory activation choice with an **activation-risk annotation**; actual authorization belongs elsewhere. Keep source status visible independently of “rule?”. Separate reference answers from evidence: [the API currently hides answer-bearing fields only for S](/home/mega/kobra/experiments/labeling_v4/server.py:175). Replace [stratum/group sorting](/home/mega/kobra/experiments/labeling_v4/server.py:158) with fixed, mixed batches of ten, capped at two cases per source family. Preserve whole-family blind assignment, but report its actual coverage: oversized families can be excluded by the current allocation algorithm.

11. **P1 — Use the pilot to test value, not just labels.**  
    Attach a small set of real radar tasks to the evaluation: retrieve the requested source, distinguish current guidance from history, explain a withheld passage, and trace a brief to its inputs. Measure whether the labels change the correct passage, notice or decision. This is the missing check that the ontology improves library use. Keep annotation speed and proposal acceptance as workflow measures, not substitutes for correctness.

**Proposed first composition: 364 cases — 172 automatic, 72 scenario requests, 120 human.** Counts are curation targets, not a claim that these exact items have already been selected. Automatic coverage below means *source declarations and verified relationships*, unless an explicit mapping supplies more.

| Source | Role | Count | kstd fields covered | Licence |
|---|---|---:|---|---|
| Radar records and complete derivation bundles | Auto gold | 24 | Declared `origin`, model/generator evidence, recorded `inputs`; generator version only when evidenced | MIT for repository-owned material; preserve third-party exceptions |
| [Python PEPs](https://peps.python.org/pep-0001/) | Auto gold | 24 | `Status`, `Replaces`, `Superseded-By`, `Created`, `Python-Version`, `Resolution` → lifecycle/scope evidence; item rights | New PEPs: public domain + CC0-1.0; check each older PEP |
| [Kubernetes KEPs](https://github.com/kubernetes/enhancements/blob/master/keps/sig-node/753-sidecar-containers/kep.yaml) | Auto gold | 20 | Status, authors, reviewers, approvers, creation/update dates, milestones, replacement links; **no automatic `reviewed_by`** | [Apache-2.0](https://github.com/kubernetes/enhancements/blob/master/LICENSE), subject to file exceptions |
| [IETF RFC chains](https://www.rfc-editor.org/rfc/rfc9110.html) | Auto gold | 16 | `Obsoletes`, `Updates`, category, authors, publication date → replacement and status evidence | [IETF Trust terms](https://trustee.ietf.org/documents/trust-legal-provisions/); code-component licence is separate |
| [FSFE REUSE tool files and declarations](https://github.com/fsfe/reuse-tool/blob/main/REUSE.toml) | Auto gold | 24 | File licence expressions, holders, explicit path coverage and precedence → item rights | Per file: GPL-3.0-or-later, CC-BY-SA-4.0, CC0-1.0 and declared combinations |
| [Nanopublication chains](https://pmc.ncbi.nlm.nih.gov/articles/PMC7959648/) | Auto gold | 20 | Signer/key, signature, creation time, `npx:retracts`, `npx:supersedes`, `dct:license` → issuer and lifecycle evidence | Per nanopub; verified examples include [CC0](https://registry.nanodash.net/np/RA2uqDOyv8sv6rbzw6AG1AXUuMMZbKOm_flkDyDspjR8w) and [CC-BY-4.0](https://registry.petapico.org/np/RAM5zmbkctjoWZRFD2EKlKjfcrN5AnJtAN7XjUrIPUcBA); absent remains unknown |
| [OKF repository samples](https://github.com/GoogleCloudPlatform/open-knowledge-format/blob/main/SPEC.md) | Auto gold | 8 | `generated.by/at`, `verified.by/at`, `status`, `stale_after`, `sources` → provenance/freshness evidence | [Apache-2.0](https://github.com/GoogleCloudPlatform/open-knowledge-format/blob/main/LICENSE.md); referenced sources separate |
| [C2PA public test files](https://github.com/c2pa-org/public-testfiles) | Auto gold | 8 | Signed claims, asset binding, ingredients, action/software assertions → provenance verification; no automatic truth or authority | [CC-BY-SA-4.0](https://github.com/c2pa-org/public-testfiles/blob/main/LICENSE) |
| [TAB whole court documents](https://github.com/NorskRegnesentral/text-anonymization-benchmark) | Auto gold | 16 | Entity spans, direct/quasi-identifiers, real-case context → personal-data evidence; no legal basis | MIT as released by TAB |
| [Beemo output/edit pairs](https://github.com/Toloka/beemo) | Auto gold | 12 | Model provenance and paired edits → origin/review evidence; **not automatically `assisted`** | Human prompts/text: CC-BY-NC-4.0; generated text: model-specific terms; expert edits: MIT subject to stated underlying terms |
| Independently reviewed, invented cases | Scenario | 72 | All decision inputs, operations, notices and state transitions | Proposed: Apache-2.0 fixtures; CC0 metadata |
| Complete documents plus review histories | Human | 30 | Substantive review evidence, responsibility, `reviewed_by`, insufficient evidence | Per artifact; review comments checked separately |
| Complete skill packages, benign security instructions and published harmless attack fixtures | Human | 30 | Instruction intent, scope, activation risk | Per file/fixture; no blanket package assumption |
| Policies, procedures and decisions with context | Human | 30 | Normative meaning and applicability; acceptance/mandate evidence remains separate | Per document |
| Whole documents with ambiguous identifiers and real/synthetic provenance | Human | 30 | Personal-data identifiability and evidential uncertainty | Per document |
| **Total** | | **364** | | |

Three candidate-source adjustments:

- **Rust RFCs: reserve, not first priority.** Their [template](https://github.com/rust-lang/rfcs/blob/master/0000-template.md) supplies start date, RFC PR and tracking issue, but not a uniform IETF-style supersession structure. The [repository also explicitly describes incomplete historical relicensing](https://github.com/rust-lang/rfcs); do not blanket-label every old RFC MIT/Apache.
- **ADRs and Claude-associated PRs: human evidence candidates.** A real [ADR replacement example](https://github.com/nofuturekid/nova/blob/main/docs/adr/0021-relicense-to-gpl-3.md) records status, date and predecessor, under a declared GPL-3.0-only transition. However, I did not establish a specific PR meeting all your proposed review criteria. A Claude trailer plus an approval is insufficient automatic `assisted` gold.
- **Add SLSA/in-toto provenance when expanding lineage coverage.** [SLSA provenance](https://slsa.dev/spec/v1.2/build-provenance) exposes artifact digests, builder identity, build type and resolved dependencies. These are stronger inputs for testing recorded lineage than free-text citations; they still do not prove complete lineage or absence of model involvement.

**Questions for the operator**

1. Which two operations matter first: search, model answers, export, activation or current-rule authority? Give three concrete tasks you want the library to handle.
2. Can we replace the 1,063-item confirmation queue with the proposed 120-case human pilot, retaining existing labels as historical annotations?
3. Who can supply factual attestations about substantive review, generator versions and source lineage?
4. Who is the second reviewer and who resolves disagreements about desired operational outcomes?
5. Which error is most costly in each operation, and how much unnecessary withholding is acceptable?
6. Should stale imported status remove only authority by default, with suspension requiring a separate explicit policy?
7. Can the complete Q1–Q27 list be provided outside the excluded research material so the coverage matrix can be finished?
8. Must the benchmark redistribute all content, or can cases with unresolved rights publish references, hashes and annotations only?