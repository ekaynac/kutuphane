# Landscape — existing work on knowledge, rights, provenance and agents

**Status:** 0.1, 2026-10-22 (D59). The facts were checked against primary sources on 2026-10-22.
**Basis:** six slice reports in `docs/research/2026-10-22-landscape-*.md`. Each slice report has the links, the issue numbers and the facts that we could not verify. This document contains only the result.
**Language:** ASD-STE100 Simplified Technical English.

## 1. Result in five points

1. **Each part of kstd already exists somewhere. No group has all the parts together.** These groups have each part:
   - **statements:** in-toto, DSSE and SCITT;
   - **status:** VC Bitstring Status List and TUF;
   - **rights signals:** AIPREF, TDMRep, RSL and CAWG;
   - **origin:** IPTC, C2PA and the W3C AI Content Disclosure CG;
   - **personal data and legal basis:** DPV;
   - **policy:** ODRL;
   - **knowledge folders:** OKF and Agent Skills.
2. **Two parts are new, and many groups ask for them:**
   - a **deterministic decision rule with three results** (permit, deny, escalate) and request → result test cases;
   - the **composition**: rights, origin, acceptance, trust and status on one artifact.

   The ODRL 3.0 charter, the Agent Memory CG, in-toto #67, MCP SEP-1913 and OKF #15/#22 ask for parts of this. This is where we can contribute.
3. **So kstd becomes a profile of existing standards, not a new vocabulary.** Where a term exists, we use it (§3). We keep our own terms only where no group has one.
4. **Some groups are still open to input** (§4):
   - **Agent Memory CG:** its use-case catalogue closes on 2026-10-30.
   - **IETF AIPREF:** meets at IETF 127 from 2026-11-14.
   - **ODRL 3.0 WG:** is in the charter phase; its conformance work starts in 2027.
5. **Three gaps in our draft came out of the study:** mixed origin, synthetic personal data, and the difference between "absent" and "no" (§3.2). Two of them change the labelling v4 fields (§5).

## 2. The groups that matter most

| # | Group | Type, state | Why it matters to us | First contribution |
|---|---|---|---|---|
| 1 | ODRL CG → Digital Policy WG (ODRL 3.0) | W3C CG; the WG charter is in draft; work in 2027–2028 | It plans deterministic semantics, a conformance suite, an AI profile and a DPV profile. ODRL has no `escalate` result. | Our decision cases in the odrl-force test format; a use case for `escalate` and `activate` |
| 2 | AI Agent Memory Interoperability CG | W3C CG; started 2026-06; very active | It asks for `derived-from`, citation fields and the rule "imported memory is evidence, not authority". This is our rule 4 and §5. | Two use cases as decision cases, **before 2026-10-30** |
| 3 | IETF AIPREF | IETF WG; vocab-08; IETF 127 on 2026-11-14 | It is the normative source of our `ai_use`. #246 (embeddings, indexes, memory) and #245 (preferences that travel) are open. | A comment on #246/#245: `derive` + `inputs` carries the preferences |
| 4 | DPV CG | W3C CG; DPV 2.3; weekly calls | It is the code list for `personal_data`, `legal_basis` and purposes. Issue #221 asks for a flat format without RDF, which is our L0 case. | A comment on #221 with `kstd.yaml`; a "personal data presence unknown" concept |
| 5 | Open Knowledge Format (OKF, Google) | Apache-2.0 repo; v0.2; active | It has the same shape as our L0 (markdown + YAML). It has no rights, digests or signatures. #15, #22 and #32 are our rules 4, 5 and 8. | A `rights` frontmatter proposal (knowledge-catalog#52) |
| 6 | in-toto Attestation + DSSE | CNCF graduated | A kstd statement is almost an in-toto Statement. #67 (revocation) contains our rules 4 and 8. | Comment on #67; register kstd predicate types |
| 7 | MCP (Agentic AI Foundation) | SEP process | SEP-1913 (trust and sensitivity labels, with block/escalate) is open. MCP is our `deliver` channel. | A typed `_meta` profile for rights and handling, with test cases |
| 8 | W3C AI Content Disclosure CG | Final Report 2026-10-09 | It has three origin levels (`human-only`, `ai-assisted`, `ai-autonomous`). #48 asks for formats that are not HTML. | A YAML/front-matter binding for #48 |
| 9 | W3C Web & AI IG | W3C IG; TPAC talk 2026-10-29 | It coordinates the groups. Recommendation 5 of the 2026-10-20 paper ("separate disclosure, provenance and training preferences") is our design. | Send this landscape and the test set to #19 and #22 |
| 10 | W3C Agent Conformance and Benchmarking CG | W3C CG, started 2026-08-30 | It wants reproducible suites and versioned corpora. | Our decision cases as a fixture set |

Groups to watch, with no contribution now:
- VC WG (Bitstring Status List, Recognized Entities);
- SCITT;
- TUF;
- nanopublications;
- Croissant RAI;
- the Dataspace Protocol and EDC;
- DCAT;
- TDMRep;
- C2PA/CAWG;
- the EU codes of practice;
- CEN-CENELEC JTC 21 and ISO SC 42.

## 3. What changes in the kstd draft

### 3.1 Reuse instead of our own terms (no behavior change)

| kstd element | Use this | Note |
|---|---|---|
| statement envelope | in-toto Statement in DSSE; `kind` → `predicateType` | We already sign with DSSE. |
| `ai_use.search / ai_input / train` | AIPREF vocabulary; the ODRL AI profile actions (`search`, `ai-augment`, `ai-training`) | Our names come from Cloudflare Content Signals. Keep a mapping table. |
| `legal_basis` | DPV IRIs, for example `eu-gdpr:A6-1-b` | Today the field is free text. |
| `personal_data` categories | DPV PD | — |
| `origin` | IPTC Digital Source Type; AI Content Disclosure levels | See §3.2 for the missing level. |
| status: withdrawn / suspended / maximum age | the Bitstring Status List purposes `revocation` / `suspension` / `ttl`; the TUF timestamp expiry | — |
| trust per issuer × kind × scope × action, with an expiry | the VC Recognized Entities model | — |
| `disposition` erasure classes | Agent Memory draft: cryptographic and access-control erasure | — |
| test case format | the formats of Cedar integration tests, odrl-force and the VC test-suite harness | We need a crosswalk: `escalate` ↔ XACML `Indeterminate`. |

### 3.2 Conflicts and gaps (these need a decision)

1. **Name conflict, `receipt`:** in SCITT and DPV, a receipt is a log inclusion proof or a consent record. Ours is a record of use. **Proposal:** rename it to `use_record`.
2. **"Absent" is not "no":**
   - AIPREF, Content Signals and the Disclosure CG say that an absent value is "unknown" and must not be read as a no.
   - Our decision rule treats absent as `n`. That is correct for the decision, because it fails closed.
   - **Proposal:** store three states (`y`, `n`, absent). Apply "absent = n" only in the decision. On export, do not write `n` for an absent value.
3. **Mixed origin:**
   - Beemo, M4GT, AI Act Art. 50(4) and the Disclosure CG all have the level "a model made it and a person reviewed it".
   - The draft has only `human`, `model` and `unknown`.
   - **Proposal:** add `assisted`, which means model output that a named person reviewed and took editorial responsibility for. Behavior: an `assisted` item does not get the AI-generated marking on export (Art. 50(4)). It keeps its review record, and it can become a rule only through acceptance, the same as a model item.
4. **Synthetic personal data:**
   - Nemotron-PII and Gretel contain data that looks like personal data but describes no real person.
   - **Proposal:** add `personal_data: synthetic`. Behavior: export needs no legal basis. Only a trusted issuer can set it; from all other issuers it counts as `unknown`.
5. **Collection license and item license:** peS2o and RAID have a license for the collection, and their items have other licenses or none. **Proposal:** a package license does not replace an item license. An item with no license of its own stays `unknown`.
6. **Generative and non-generative training:**
   - CAWG and AIPREF separate the two kinds; kstd `train` covers both.
   - **Proposal:** no change now, because no behavior in Kütüphane depends on the difference. Note it in the mapping table.
7. **Fail-closed policy:** EDC skips unknown rules without a warning. ODRL has no third result. Our rules 2 and 3 are a real difference. We keep them and offer them as test cases.

## 4. Contribution plan

**Order:** first the time-limited items, then the items with the largest overlap.

| When | Where | What |
|---|---|---|
| before 2026-10-30 | Agent Memory CG use-case catalogue | Two use cases with decision cases. First: an untrusted issuer sends a loosening → `escalate`/`deny`. Second: erasure reaches derived notes through `inputs`. |
| before 2026-11-14 | IETF AIPREF (#246, #245; `ai-control@ietf.org`) | How `derive` + `inputs` carries a preference to embeddings and indexes. One example from Kütüphane. |
| November 2026 | DPV #221, ODRL CG, OKF knowledge-catalog#52, in-toto #67, MCP SEP-1913 | Comments and examples, one per group. |
| Q1 2027 | ODRL 3.0 WG conformance work; Agent Conformance CG | Our decision cases in their format, plus the `escalate` crosswalk. |
| continuous | Web & AI IG #19/#22 | The landscape and the public test set. |

**Prerequisites (operator actions):**
- **W3C account and CLA:** they are needed for every W3C CG. The CLA is a legal agreement, so the operator must accept it, personally or for the company.
- **IETF:** no membership is needed; you subscribe to the list and accept the Note Well.
- **OKF:** the Google CLA. **Eclipse:** the free ECA (only needed for the Dataspace Protocol).
- **Public text:** a contribution must point to public text. The repo is private. Either the repo becomes public, or we publish the kstd draft and the cases on their own.

**Rules for our contributions:**
- Each contribution is small, concrete and has test cases. It does not ask the group to adopt kstd.
- Corpus content never goes into a contribution. Examples use public data or invented text.
- We write in the group's terms (§3.1), not ours.

## 5. Effect on labelling v4 (§6.5 of `docs/12`)

- **origin:** add the value `assisted` (§3.2.3). Without it, a person must label reviewed model text as `human` or `model`, and both are wrong.
- **personal_data:** add the value `synthetic` (§3.2.4). This applies only to the public test set; our own corpus has no synthetic data.
- **ai_use:** the label stores "not stated" separately from `n` (§3.2.2).
- **legal_basis:** a DPV code list replaces free text.
- **license:** this field is not labelled (unchanged). The public set tests that an item without its own license stays `unknown` (§3.2.5).

**Public test set candidates.** Only public data. It is kept apart from `experiments/labeling/data/`.

| Source | Tests | License |
|---|---|---|
| RAID, MAGE | `origin: human` / `model` | MIT, Apache-2.0 |
| Beemo | `origin: assisted` (model text edited by people) | MIT |
| HC3 | origin; a share-alike license | CC-BY-SA-4.0 |
| TAB (ECHR cases) | real personal data with a public-record legal basis | MIT |
| Nemotron-PII | `personal_data: synthetic` | CC-BY-4.0 |
| Common Pile / Common Corpus | a license for each document | per document |
| OKF sample bundles | model-made items with sources; the rights of a derivative | Apache-2.0 |
| M4GT-Bench | no license → `unknown` → deny | none stated |
| ai4privacy open-pii-masking | a license that is not SPDX → deny | non-SPDX |

**Size:** about 40–60 items. A dataset license does not always cover the texts inside it. So we copy only the items whose own license allows it. For all other items, we keep only the source, the digest and our statement.

## 6. Questions that we will ask the groups

1. **ODRL 3.0:** Will conformance define a third result (`Indeterminate`/`escalate`) and a fixed precedence? Will it accept outside test cases?
2. **Agent Memory CG:** Will cells carry rights, origin and legal basis, or point to an external statement layer? Will "imported memory is evidence, not authority" become a conformance rule with test vectors?
3. **AIPREF:** Must a preference travel to embeddings, indexes and agent memory through recorded inputs, or is a new category (like RSL `ai-index`) needed?
4. **DPV:** Can 2.5 add "personal data presence unknown" and publish a flat JSON list of legal bases and purposes?
5. **OKF:** Will the core accept a `rights` family and a content digest? What does an absent value permit?
6. **in-toto #67:** Is the authority to revoke a policy question or a predicate field?
