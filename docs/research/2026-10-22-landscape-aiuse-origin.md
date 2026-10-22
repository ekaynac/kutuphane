# Landscape report: AI-use preferences and content origin

Checked on 2026-10-22. The sources are datatracker, W3C CG pages and lists, GitHub, and the specification texts. Where I could not confirm a fact, the report says "not verified".

## 1. IETF AIPREF WG

- **Status.** Active WG in the WIT area, under charter-ietf-aipref-01.
  - Chairs: Mark Nottingham and Suresh Krishnan. Area Director: Mike Bishop. [About](https://datatracker.ietf.org/wg/aipref/about/)
  - **draft-ietf-aipref-vocab-08** (14 Sep 2026). Editors: Keller and Thomson. Intended status: Proposed Standard. WG state: "WG Document". IESG state: "I-D Exists". The draft says "DO NOT REFLECT CONSENSUS". [Draft](https://datatracker.ietf.org/doc/draft-ietf-aipref-vocab/)
  - **draft-ietf-aipref-attach-05** (19 Aug 2026). Editors: Illyes and Thomson. It defines the `Content-Usage` HTTP header and a `Content-Usage` rule in robots.txt, and it updates RFC 9309. [Draft](https://datatracker.ietf.org/doc/html/draft-ietf-aipref-attach)
  - The milestones for both drafts were "Aug 2026", so the WG missed them.
  - An interim meeting took place on 21 Oct 2026. The next session is IETF 127, San Francisco, from 14 Nov 2026. [Interim agenda](https://github.com/ietf-wg-aipref/wg-materials/tree/main/interim-26-10)
- **Scope.** The WG gives a vocabulary of purposes and ways to attach it to content. Enforcement, registries and auditing are out of scope.
  - The vocab-08 labels are `train-ai`, `ai-use` and `search`. The values are `y` or `n`, and the result is allowed, disallowed or unknown.
  - Absent means "unknown", and the draft gives no default.
  - When statements conflict, the most restrictive one wins.
  - `search` overrides the other categories.
  - `train-ai` covers only generative models.
- **Open issues that touch our areas.** [Issue list](https://github.com/ietf-wg-aipref/drafts/issues)
  - [#246](https://github.com/ietf-wg-aipref/drafts/issues/246): caches, embeddings and other derived forms (memory, index).
  - [#245](https://github.com/ietf-wg-aipref/drafts/issues/245): preferences that travel with trained models.
  - [#249](https://github.com/ietf-wg-aipref/drafts/issues/249): does "direct provision" include URLs?
  - [#153](https://github.com/ietf-wg-aipref/drafts/issues/153) and [#154](https://github.com/ietf-wg-aipref/drafts/issues/154): unknown vs. allowed, and defaults (deferred).
  - [#167](https://github.com/ietf-wg-aipref/drafts/issues/167): access vs. use.
  - [#247](https://github.com/ietf-wg-aipref/drafts/issues/247): a separate data model.
- **Related individual drafts.** [Document list](https://datatracker.ietf.org/wg/aipref/documents/)
  - `draft-wallace-aipref-grant-binding-02`: signed grants that lift a preference.
  - `draft-reilly-aipref-compliance-00`: compliance records.
  - `draft-hood-aipref-earmark-00`: signed preferences embedded in content.
  - `draft-zehta-aipref-parameters` and `draft-zehta-aipref-exclusions`.
  - `draft-romm-aipref-contentsignals-00`.
- **Test data.** [amits710/aipref-testbed](https://github.com/amits710/aipref-testbed) (MIT) has 117 conformance vectors for a `<meta name="content-usage">` binding: duplicate keys, non-token values, and others. No WG test suite exists.
- **Overlap with kstd.**
  - **Reuse:** the purpose categories, structured-field parsing, the most-restrictive merge, and "unknown".
  - **Conflicts:**
    - kstd says "absent = n". AIPREF says unknown with no default.
    - kstd keeps the three flags independent. In AIPREF, `search` overrides the others.
    - kstd `train` has no generative/non-generative split.
  - **Gaps in AIPREF that kstd covers:** derived artifacts (kstd `inputs` and `derive`), signed grants (kstd `mandate`), and receipts.
- **How to take part.** No membership is necessary. Accept the IETF Note Well and subscribe to `ai-control@ietf.org`. A datatracker account gives Meetecho access.
- **First contribution.** Comment on #246 and #245. Show how a `derive` statement with `inputs` carries preferences to embeddings and indexes.

## 2. W3C TDMRep CG

- **Status.** Active, but at a slow pace. Chair: Laurent Le Meur (EDRLab). The co-chair is not verified.
  - Final Reports: v1 (2022-02), v2 (2024-04-16) and v3 (published 2024-08-09). [CG page](https://www.w3.org/community/tdmrep/)
  - The last CG blog post is dated 2025-10. The mailing list was active in 2026: a meeting on 2026-03-25, and threads in Sep and Oct 2026. The repo had commits until 2026-09-03.
- **Scope.** TDMRep expresses the EU DSM Art. 4 rights reservation with `tdm-reservation` (0/1) and an ODRL `tdm-policy`. It uses `/.well-known/tdmrep.json`, HTTP headers, HTML meta, EPUB and PDF. [Repo](https://github.com/w3c-cg/tdm-reservation-protocol)
- **Open questions.**
  - The CG must choose: adopt AIPREF, or adopt the Cloudflare labels (`search`, `ai-input`, `ai-train`) as its own fine-grained vocabulary. [Mail of 2026-03-04](https://lists.w3.org/Archives/Public/public-tdmrep/2026Mar/0000.html)
  - [#58](https://github.com/w3c-cg/tdm-reservation-protocol/issues/58): a reservation must not block search indexing.
  - #56 and #57: errors in the PDF metadata clauses.
  - The CG considered the ISO path through the PDF Association.
- **Data.**
  - [docs/use-cases.md](https://github.com/w3c-cg/tdm-reservation-protocol/blob/main/docs/use-cases.md) and adopters.md.
  - Deployment measurement in [#62](https://github.com/w3c-cg/tdm-reservation-protocol/issues/62): `tdmrep.json` on 0.38 % of 7,282 hosts, `/rsl.xml` on 0.78 %, `/ai.txt` on 0.27 %. The data is CC BY 4.0 in [ai-discovery-radar](https://github.com/flober81/ai-discovery-radar). The repo license is not stated.
- **Overlap with kstd.** TDMRep is one coarse bit plus a policy link. It gives the DSM legal basis wording that kstd should map to. The CG says search is out of scope of the opt-out.
- **How to take part.** Get a free W3C account and accept the W3C CLA.
- **First contribution.** Write a kstd `ai_use` ↔ tdm-reservation/ODRL mapping note, and answer the vocabulary question with data.

## 3. Cloudflare Content Signals

- **Status.** Real and deployed by a vendor, launched Sep 2025. The documentation was updated on 2026-10-22. [Cloudflare docs](https://developers.cloudflare.com/bots/additional-configurations/managed-robots-txt/), [contentsignals.org](https://contentsignals.org/)
  - Syntax: a `Content-signal: search=yes, ai-train=no` line in robots.txt.
  - Cloudflare tests an extra `use=immediate|reference|full` field.
  - It was submitted to the IETF as `draft-romm-aipref-contentsignals-00` (2026-04-04).
- **Overlap with kstd.** The kstd names `search`, `ai_input` and `train` copy Content Signals, not AIPREF-08. Absent means "neither grants nor restricts", so it conflicts with kstd "absent = n". The `use=` field has no kstd equivalent (a gap: retention and reuse).
- **How to take part.** No group exists. Comment through the IETF draft.

## 4. RSL (Really Simple Licensing)

- **Status.** RSL 1.0 has the status "Recommendation" from the RSL Technical Steering Committee (TSC), published 2025-12-10. [Specification](https://rslstandard.org/rsl)
  - The editors are from the RSL Collective, Condé Nast, Ziff Davis, Schema.org (Guha), Yahoo, Automattic, O'Reilly and Fastly.
  - There is one GitHub repo, last pushed 2026-03-31, with few issues. [Repo](https://github.com/rslstandard/rsl)
- **Scope.** RSL is an XML license with these usage tokens: `all`, `ai-all`, `ai-train`, `ai-input`, `ai-index` and `search`.
  - It also has user and geo classes, payment and reporting, and `max-age`.
  - It defines three protocols: the Open License Protocol (OLP, OAuth), the Crawler Authorization Protocol (CAP) and the Encrypted Media Standard (EMS).
  - Rules: the most specific declaration wins, then prohibition wins.
- **Overlap with kstd.**
  - RSL `ai-index` covers the memory/index gap.
  - `max-age` is similar to the kstd maximum status age.
  - RSL has payment terms. kstd does not, so it is out of scope.
- **Data.** The site has a validator (not tested).
- **How to take part.** Use the issue tracker. The membership rules of the TSC are not verified.

## 5. ai.txt proposals

Several proposals use this name, and none is established:
- the Spawning `ai.txt` file (0.27 % of hosts in the measurement above);
- `draft-car-ai-txt-wellknown-00`, an individual Independent Submission of 2026-06-12. [Draft](https://datatracker.ietf.org/doc/html/draft-car-ai-txt-wellknown-00)

These proposals are low priority for us.

## 6. C2PA and CAWG

- **Status.** C2PA spec **2.4** is dated 2026-04-01. [Spec 2.4](https://spec.c2pa.org/specifications/specifications/2.4/specs/C2PA_Specification.html) It adds:
  - **A.8**: embedding in unstructured text.
  - **A.9**: embedding in structured text (Markdown/YAML front matter, source code) with an ASCII-armour block.
  - the **`c2pa.ai-disclosure`** assertion, with `humanOversightLevel`: `fully_autonomous`, `prompt_guided` or `human_validated`.
  - `digitalSourceType` on `c2pa.created` actions.
- **Training and Data Mining assertion.** It is now **CAWG** `cawg.training-mining` v1.1, ratified by DIF on 2025-05-16. [Spec](https://cawg.io/training-and-data-mining/1.1/)
  - Entries: `data_mining`, `ai_inference`, `ai_training` and `ai_generative_training`.
  - Values: `allowed`, `notAllowed` or `constrained`. `constrained` counts as `notAllowed`.
- **Data.**
  - [c2pa-org/public-testfiles](https://github.com/c2pa-org/public-testfiles) (CC-BY-SA-4.0) has only 2.2 and legacy folders, last updated 2025-12. I did not find text test vectors in the main branch.
  - Conformance program: [c2pa.org/conformance](https://c2pa.org/conformance).
- **Overlap with kstd.**
  - A.9 can carry a signed origin per Markdown file at kstd L1.
  - CAWG separates generative and non-generative training. kstd does not (a gap).
- **How to take part.** C2PA and CAWG/DIF membership terms are not verified.

## 7. IPTC Digital Source Type, and the PLUS DataMining property

- **Status.** The NewsCodes CV has 20 terms, last modified 2024-10-23, under CC BY 4.0. [CV](https://cv.iptc.org/newscodes/digitalsourcetype/)
  - Photo Metadata Standard 2025.1 adds AI System Used, AI System Version Used, AI Prompt Information and AI Prompt Writer Name.
  - The PLUS `DataMining` property uses these values: `DMI-ALLOWED`, `DMI-PROHIBITED-AIMLTRAINING`, `DMI-PROHIBITED-GENAIMLTRAINING`, `DMI-PROHIBITED-EXCEPTSEARCHENGINEINDEXING`, and others.
  - The AIPREF charter names IPTC and PLUS as liaisons.
- **Mapping for origin.**
  - `human` → `digitalCreation` or `humanEdits`.
  - `model` → `trainedAlgorithmicMedia`.
  - mixed → `compositeWithTrainedAlgorithmicMedia`. kstd has no mixed value.
- **Data.** IPTC has reference images and interoperability tests. Their licenses are not verified.
- **How to take part.** Full membership is paid. Public-comment drafts are open to all.

## 8. W3C AI Content Disclosure CG (it exists)

- **Status.** The CG launched on 2026-02-03 and was proposed by David Weekly. Meeting posts are by Doğu Abaris. The chairs are not verified.
  - The **Final Report is dated 9 Oct 2026**, and its URL resolves. [Final Report](https://www.w3.org/community/reports/ai-content-disclosure/CG-FINAL-ai-content-disclosure-20261009/)
- **Scope.** The report defines an HTML `ai-disclosure` attribute and a `<meta>` tag.
  - Values: `human-only`, `ai-assisted` (human review is required) and `ai-autonomous`. Absent means unknown.
  - Optional attributes: `ai-model`, `ai-provider` and `ai-prompt-url`.
  - The target is EU AI Act Art. 50.
- **Open issues.** [Issue list](https://github.com/w3c-cg/ai-content-disclosure/issues)
  - #49: absence must carry no negative inference. This conflicts with kstd "unknown = model".
  - #48: scope for non-HTML formats. kstd can fill this.
  - #47 and #51: contribution type, and an AI Usage Scale vocabulary.
- **Data.** The repo `tests/` folder has `disclosure.html` and `disclosure.js`, plus examples.
- **Overlap with kstd.** The report has a three-level origin, and its `ai-assisted` level matches the Art. 50(4) human-review exception. kstd `origin` has no such level (a gap).
- **How to take part.** Get a W3C account and accept the CLA.
- **First contribution.** A YAML/Markdown (non-HTML) mapping for #48.

## Mapping summary

| kstd | AIPREF-08 | Content Signals | RSL | CAWG | TDMRep |
|---|---|---|---|---|---|
| `search` | `search` (overrides others) | `search` | `search` | — | outside opt-out |
| `ai_input` | `ai-use` | `ai-input` | `ai-input` (+`ai-index`) | `ai_inference` | `tdm-reservation=1` only |
| `train` | `train-ai` (generative only) | `ai-train` | `ai-train` | `ai_training` + `ai_generative_training` | `tdm-reservation=1` only |
| absent | unknown | no grant, no restriction | conservative | — | unset |

**Recommendation.** Store three states (`y`, `n`, unset). Apply "absent = n" only in the decision rule. When kstd exports to AIPREF, do not write `n` for unset fields. Add an `assisted` origin value, or a profile mapping, for Art. 50(4).

## Ranked importance

1. IETF AIPREF: the normative vocabulary, at IETF 127 next month.
2. W3C AI Content Disclosure CG: it is the closest match to `origin`, and the report is fresh.
3. C2PA 2.4 A.9 and CAWG: signed origin and TDM rules for Markdown/YAML files.
4. W3C TDMRep CG: the DSM Art. 4 legal basis, and it has not yet chosen a vocabulary.
5. Cloudflare Content Signals: kstd names come from it.
6. RSL: it has the `ai-index` token.
7. IPTC.
8. ai.txt proposals.

## Questions to ask

1. AIPREF #246: Must preferences travel to embeddings, indexes and agent memory through recorded inputs? Or does the WG want a new category, like RSL `ai-index`?
2. AIPREF: Will "unknown" ever get a recommended default? Must a statement that does not state a value export as absent?
3. TDMRep: Will the CG adopt AIPREF labels or Content Signals labels? When will it decide?
4. AI Content Disclosure CG: Will a non-HTML binding (front matter, sidecar manifest) be in scope for a next version (#48)?
5. C2PA and CAWG: Will `cawg.training-mining` align its entries with the AIPREF categories? Are A.9 test vectors planned?