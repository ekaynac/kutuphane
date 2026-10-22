# Landscape report: personal data, legal basis, usage rights and policies

I checked every item below against primary sources on 2026-10-22. "Not verified" means that I did not find a primary source.

## 1. W3C Data Privacy Vocabularies and Controls CG (DPVCG)

**1. Type and status.** This is a W3C Community Group. The chairs are Beatriz Esteves and Harshvardhan J. Pandit ([group](https://www.w3.org/groups/cg/dpvcg)). The group is active:
- It has weekly calls. The last call was on 21 Oct 2026 ([list](https://lists.w3.org/Archives/Public/public-dpvcg/2026Oct/)).
- The latest release is **DPV 2.3**, a Final CG Report of 25 Feb 2026 ([release](https://github.com/w3c-cg/dpv/releases/tag/dpv-2.3)).
- The group planned DPV 2.4 for July 2026. It is not released; only a "2.4-dev" draft exists. Issues for v2.5 are also open.
- The repo moved to [w3c-cg/dpv](https://github.com/w3c-cg/dpv) and has 122 open issues.
- License: W3C Software and Document License.

**2. Scope.** DPV gives ontologies and taxonomies for the processing of personal data and non-personal data, and for technologies. It has these parts:
- **Core** ([w3id.org/dpv](https://w3id.org/dpv), 1,130 `dpv:` terms in 2.3): purposes, processing operations, legal bases, entities, rules (`dpv:Permission`, `Prohibition`, `Obligation`) and statuses.
- **Extensions:** [PD](https://w3id.org/dpv/pd) (personal data categories), [TECH](https://w3id.org/dpv/tech), [AI](https://w3id.org/dpv/ai), [RISK](https://w3id.org/dpv/risk) and [LEGAL](https://w3id.org/dpv/legal) for 40+ jurisdictions. LEGAL includes [GDPR](https://w3id.org/dpv/legal/eu/gdpr), [AI Act](https://w3id.org/dpv/legal/eu/aiact), DGA and EHDS.
- **Guides:** an [ISO/IEC 27560 consent guide](https://w3id.org/dpv/guides/consent-27560) (Final Report, 15 Feb 2026) and a [DPV-ODRL guide](https://dev.dpvcg.org/guides/dpv-odrl). The DPV-ODRL guide is a work in progress.
- **Mappings:** a [DPV→ODRL mapping](https://w3id.org/dpv/mappings/odrl), in machine-readable form.

**3. Open issues in our areas.**
- [#221](https://github.com/w3c-cg/dpv/issues/221): use DPV as CSV or JSON without RDF. Users ask for "one file, like the SPDX license list". This is our L0 YAML case.
- [#476](https://github.com/w3c-cg/dpv/issues/476) and [#130](https://github.com/w3c-cg/dpv/issues/130): automatic DPV-ODRL mapping and alignment with ODRL.
- [#216](https://github.com/w3c-cg/dpv/issues/216): alignment with PROV.
- [#232](https://github.com/w3c-cg/dpv/issues/232): document status concepts.
- [#94](https://github.com/w3c-cg/dpv/issues/94): datasheets and model cards.
- [#492](https://github.com/w3c-cg/dpv/issues/492): versioned namespaces. Our permits are bound to exact versions, so this issue is relevant.
- [#454](https://github.com/w3c-cg/dpv/issues/454) and [#456](https://github.com/w3c-cg/dpv/issues/456): a dispute with Kantara ANCR members. The dispute is about whether a controller-side log can be a "consent receipt". It has no consensus.

**4. Test material.**
- 88 example files in [`examples/`](https://github.com/w3c-cg/dpv/tree/master/examples), with the [examples report](https://w3id.org/dpv/examples).
- [Use cases and requirements](https://w3id.org/dpv/use-cases).
- License: W3C Document License / CG Final Specification Agreement (FSA).
- No conformance test suite exists.

**5. Overlap with kstd.**
- **Reuse:**
  - `legal_basis`: use `dpv:hasLegalBasis` with `eu-gdpr:A6-1-a`…`A6-1-f` and `A9-2-a`…`A9-2-j`.
  - `personal_data`: use `dpv:PersonalData`, `dpv:NonPersonalData`, `dpv:AnonymisedData`, `dpv:PseudonymisedData`, `dpv:InferredPersonalData` and `dpv:DerivedPersonalData`, and use PD for categories.
  - Erasure: use `dpv:Erase`.
  - Consent status: use `dpv:ConsentGiven`, `ConsentWithdrawn` and `ConsentExpired`.
- **Gap:** DPV has `ConsentUnknown`, `LawfulnessUnknown` and `ComplianceUnknown`. It has **no "personal data presence unknown"** concept, so our `personal_data: unknown (= yes)` has no match.
- **Gap:** DPV has no `activate` (run an item as an instruction) and no `ai_input` action.
- **Gap:** DPV AI has `ai:ModelTraining` and `ai:hasTrainingData`, but it has no rights term for training.
- **Conflict:** our `receipt` is a use receipt, not a consent receipt. We must use a different name.

**6. How to take part.** You need a free W3C account, and you must join the CG and accept the W3C CLA. Calls are open; ask the chairs for the call details.

Most useful first contribution: comment on #221 with our `kstd.yaml` L0 example. Also propose a concept for "personal data presence unknown".

## 2. W3C ODRL CG → proposed "Digital Policy" Working Group (ODRL 3.0)

**1. Type and status.**
- The ODRL 2.2 Recommendations date from 15 Feb 2018.
- The CG chairs are Nicoletta Fornara, Renato Iannella and Víctor Rodríguez-Doncel ([group](https://www.w3.org/groups/cg/odrl)).
- The CG has monthly calls. The last call was on 5 Oct 2026 and the next is on 2 Nov 2026 ([minutes](https://github.com/w3c/odrl/blob/master/meetings/2026/meeting-2026-10-05.md)).
- The **[W3C Workshop on the Future of ODRL](https://www.w3.org/2026/ODRLWS/) took place on 20–21 July 2026 in London**, hosted by JP Morgan Chase. Its [report](https://www.w3.org/2026/ODRLWS/report.html) shows consensus for a new WG for ODRL 3.0.
- On 5 Oct the CG approved the **[draft Digital Policy WG charter](https://w3c.github.io/odrl/w3c-wg-draft-charter-2026/dpwg-draft-charter.html)**, with a proposed start of 1 Jan 2027. It is not yet in AC review: the group page `w3.org/groups/wg/dp` returns 404. The plan was to present the charter at TPAC 2026 in Dublin.

**2. Scope and deliverables.** The draft charter lists five normative documents:
- ODRL 3.0 Semantic Model (Q4 2027)
- Vocabulary and Registry (Q4 2027)
- Profile Declaration (Q1 2028)
- **Conformance Evaluation of processors** (Q2 2028)
- Architecture and Protocols (Q3 2028)

The tentative profiles are:
- **DPV profile**
- **AI/Data Governance profile**
- Data Spaces profile
- Market Data profile
- PLUS image profile

The charter also asks for bindings to DPV, DCAT, DID and VC, and it makes provenance of policies "first-class".

The CG has these input drafts:
- [Formal Semantics](https://w3c.github.io/odrl/formal-semantics/): evaluator behaviour for active, violated and fulfilled rules, in access-control and monitoring scenarios.
- [AI Vocabulary profile](https://w3c.github.io/odrl/ai-vocab/): `data-mining`, `ai-training`, `gen-ai`, `ai-augment`, `search`, `index`. The draft maps these terms to AIPREF, CAWG, PLUS and RSL.
- [Best Practices](https://w3c.github.io/odrl/bp/) and the [Community Vocabulary](https://w3c.github.io/odrl/community-vocab/).

**3. Open issues in our areas.**
- AI terms: [#156](https://github.com/w3c/odrl/issues/156) (Search), [#157](https://github.com/w3c/odrl/issues/157) (the wording "similar semantics" in the mappings to opt-out vocabularies), [#159](https://github.com/w3c/odrl/issues/159) (TDMRep).
- Agents: [#112](https://github.com/w3c/odrl/issues/112) (agent delegation) and [#113](https://github.com/w3c/odrl/issues/113) (evaluation request and response with AuthZEN).
- Semantics: [#118](https://github.com/w3c/odrl/issues/118) (state of the world), [#151](https://github.com/w3c/odrl/issues/151) and [#74](https://github.com/w3c/odrl/issues/74).
- WG name: [#167](https://github.com/w3c/odrl/issues/167).
- The HSBC workshop [paper](https://www.w3.org/2026/ODRLWS/PP/02-BeyondPermit-HSBC.pdf) says that ODRL has "interoperable syntax, not interoperable semantics". It proposes `odrl-prov` and `odrl-cr` (conflict resolution as in XACML).

**4. Test material.**
- [odrl-force/ODRL-Test-Suite](https://github.com/odrl-force/ODRL-Test-Suite) (MIT): 68 test cases (policy + request + state → expected report).
- [ODRL-Evaluator](https://github.com/odrl-force/ODRL-Evaluator) (MIT).
- [Compliance Report Model](https://github.com/odrl-force/ODRL-Compliance-Report-Model) and the [FORCE](https://w3id.org/force) specification (both CC-BY-4.0).
- [odrl-validator-benchmark](https://github.com/odrl-force/odrl-validator-benchmark): no license found.
- [use-cases](https://github.com/odrl-force/use-cases) (CC-BY-SA-4.0): delegation and medical-purpose cases.
- The examples of the CG Formal Semantics draft: constraints, refinements and duties.
- [ODRL2SHACL](https://github.com/paolo7/ODRL2SHACL) (Apache-2.0).
- [SDS2026 DPV-ODRL mapping](https://github.com/besteves4/SDS2026-DPV-ODRL-mapping) (CC-BY-SA-4.0).

**5. Overlap with kstd.**
- **Reuse:** ODRL Permission and Prohibition; `odrl:read`, `derive` and `distribute`; the AI profile actions for `ai_use`:
  - `train` → `ai-training`
  - `ai_input` → `ai-augment`
  - `search` → `search`

  Use `odrl:purpose` with DPV purposes.
- **Conflict:** ODRL 2.2 conflict handling is `perm`/`prohibit`/`invalid`. ODRL has no **`escalate`** outcome. Our rule "unknown required term → deny" has no equivalent in ODRL.
- **Gap:** ODRL has no `activate` action, no trust-per-issuer rule and no status freshness.
- **Shared goal:** the workshop asked for deterministic evaluation, multi-level conformance and request→result test cases. These are the same as our §4 and L0–L3. **This is our best entry point.**

**6. How to take part.**
- Now: join the CG (free W3C account and the CLA). File GitHub issues; comments on the charter are open.
- Later: the WG needs W3C Membership or Invited Expert status, and you must agree to the Patent Policy.

Most useful first contribution: give our decision-rule cases as ODRL-Test-Suite cases, plus a use case for `escalate` and `activate`, to the conformance work.

## 3. Consent receipts and purpose limitation (W3C, IETF, related)

- **ISO/IEC TS 27560:2023** (Consent record information structure) is being replaced by **[ISO/IEC CD 27560.2](https://www.iso.org/standard/91775.html)** ("Structure of PII Processing Records"). Its CD comment period closed on 6 Jun 2026 (stage 30.60). This is not W3C work. The DPV guide implements the TS. A paid ISO license applies.
- **Kantara ANCR WG** ([repo](https://github.com/KantaraInitiative/ancr-wg)) works on the "Consent Receipt V2". I did not verify its current status.
- **W3C Privacy WG:** [Global Privacy Control](https://www.w3.org/TR/gpc/) is a Working Draft of 24 Sep 2026. It is an opt-out signal only, with no DPV or ODRL terms. The draft DP charter plans to coordinate with this group.
- **W3C [Privacy Principles](https://www.w3.org/TR/privacy-principles/)** is a W3C Statement of 15 May 2025. It defines purpose and purpose limitation in plain text only.
- **IETF:** no WG works on consent receipts or purpose limitation. Related individual drafts:
  - [draft-howe-vcon-lawful-basis-02](https://datatracker.ietf.org/doc/draft-howe-vcon-lawful-basis/) (expires 2026-12-01) has its own list of the six GDPR bases. It does not use DPV, and it uses SCITT receipts.
  - [draft-vcon-consent](https://datatracker.ietf.org/doc/draft-vcon-consent/) (expired) and [draft-ietf-vcon-privacy-primer](https://datatracker.ietf.org/doc/draft-ietf-vcon-privacy-primer/).
  - [draft-das-purpose-execution-finality](https://datatracker.ietf.org/doc/draft-das-purpose-execution-finality/) (Sep 2026). I did not verify its content.
- **Overlap with kstd:** for consent, use ISO 27560 through DPV. Our receipt can carry a SCITT-style transparency receipt. The vCon drafts show that a reusable legal-basis code list is missing at the IETF; DPV IRIs could fill this gap.

## Ranked importance for us

1. **ODRL CG → Digital Policy WG.** It plans a conformance test suite, deterministic semantics, an AI profile and a DPV profile. The work starts in 2027, so our input can still change it.
2. **DPVCG.** Use it as the code list for `personal_data`, `legal_basis` and purposes. The group is very active, and #221 matches our need for formats without RDF.
3. **odrl-force (FORCE, Test Suite, Evaluator).** This is the only open ODRL test corpus (MIT). We can reuse its format for our cases.
4. **ISO/IEC 27560.2 and Kantara ANCR.** Monitor them for consent and processing records.
5. **IETF vCon individual drafts and W3C GPC.** Watch only.

## Questions to ask

1. ODRL 3.0: will conformance define a third outcome (indeterminate or `escalate`) and a fixed default precedence (deny-overrides)? Will it accept outside test cases in the Compliance Report format?
2. ODRL AI profile: what is the relation between `ai-augment` and the AIPREF / RSL `ai-input` terms? Is an action for "run as an instruction or skill" (`activate`) in scope?
3. DPV: can 2.5 add a concept for "personal data presence unknown"? Can it publish a flat JSON or CSV list of legal bases and purposes, the same as the SPDX list (#221)?
4. DPV + ODRL: which versioned IRIs must a policy use so that it is bound to exact vocabulary versions (#492)?
5. ISO 27560.2 / DPV: can a processing record or receipt refer to artifact digests, so that it can record the use of content in AI input and training?