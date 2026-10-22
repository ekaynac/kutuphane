# Benchmarks, test data, and regulation and standards bodies: landscape report (2026-10-22)

**Scope:** public data that can test the kstd ontology and decision rule, and the regulation and standards bodies in my slice. I checked every fact below against a primary source on 2026-10-22, unless the text says "not verified".

## 1. Candidate sources for the labelling v4 test set

| Source | What it gives | License | Use in kstd |
|---|---|---|---|
| [Common Pile v0.1](https://huggingface.co/datasets/common-pile/github_archive) (EleutherAI, June 2025) | Each document has its own license in `metadata.license` | Set by each document. Code: [MIT](https://github.com/r-three/common-pile) | Known `rights.license`. The dataset card itself warns about "license laundering". That makes it a good test for `contest`. |
| [Common Corpus](https://huggingface.co/datasets/PleIAs/common_corpus) (Pleias, 2.27T tokens) | Each document has `license`, `date` and a source URL. Pleias says it removed personal data (PII) with Presidio | Set by each document (public domain, CC, MIT, Licence Ouverte) | Rights and dates. The PII removal is a claim we must test, not a fact. |
| [KL3M Data](https://huggingface.co/datasets/alea-institute/kl3m-data-dotgov-www.irs.gov) | Each card has a "Legal Basis" section | CC-BY-4.0 | Tests the legal-basis note |
| [peS2o](https://huggingface.co/datasets/allenai/peS2o) | About 39M papers. The records have no license field for each paper | The collection is ODC-By | Tests that the collection license and the item license stay separate |
| [RAID](https://huggingface.co/datasets/liamdugan/raid) | Human text and text from 11 models | MIT | `origin: human` and `origin: model` |
| [MAGE](https://huggingface.co/datasets/yaful/MAGE) | Human text and model text | Apache-2.0 | `origin` |
| [HC3](https://huggingface.co/datasets/Hello-SimpleAI/HC3) | Human answers and ChatGPT answers | CC-BY-SA-4.0 | `origin`, and a share-alike license |
| [Beemo](https://huggingface.co/datasets/toloka/beemo) | Model text that experts or models then edited | MIT | Mixed origin (a gap, see §3) |
| [M4GT-Bench](https://github.com/mbzuai-nlp/M4GT-Bench) | Labels the boundary between human and model text inside one document | The README states no license | A negative case: the license is `unknown`, so the result must be deny |
| [TAB](https://github.com/NorskRegnesentral/text-anonymization-benchmark) | 1,268 ECHR court cases with identifiers that people marked by hand | MIT | Real personal data with a public-record legal basis |
| [Nemotron-PII](https://huggingface.co/datasets/nvidia/Nemotron-PII) | 100k synthetic records, 55+ PII/PHI categories | CC-BY-4.0 | Synthetic PII |
| [Gretel synthetic PII finance](https://huggingface.co/datasets/gretelai/synthetic_pii_finance_multilingual) | Synthetic PII | Apache-2.0 | Synthetic PII |
| [ai4privacy open-pii-masking-500k](https://huggingface.co/datasets/ai4privacy/open-pii-masking-500k-ai4privacy) | PII | The tag says "other". The card says the Llama Community License applies | A license that is not SPDX, so the result must be deny |
| [presidio-research](https://github.com/microsoft/presidio-research) | Generator and evaluator for PII data | MIT | Tooling |

**Caution:** a dataset license does not always cover the texts inside it. The human texts in RAID and HC3 come from third-party sources. Copy into our public set only items whose license allows it. For all other items, publish only the path, the digest and the statement.

## 2. Test suites for the decision rule

| Suite | Format | License | Overlap with kstd |
|---|---|---|---|
| [Cedar integration tests](https://github.com/cedar-policy/cedar-integration-tests) | JSON. Each request gives the expected `decision`, `reason` and `errors`. Some tests come from fuzzing | Apache-2.0 | Closest to kstd §4: "same result and same reason". Cedar has only Allow and Deny, with no escalate. |
| [OPA Rego cases](https://github.com/open-policy-agent/opa/tree/main/v1/test/cases/testdata) | YAML, 147 case folders in v1 | Apache-2.0 | We can reuse the format |
| [AuthzForce XACML 3.0 conformance tests](https://github.com/authzforce/core/tree/develop/pdp-testutils/src/test/resources/conformance) | Converted from the OASIS XACML 2.0 conformance tests | The repository is Apache-2.0. The license of the original OASIS tests is not verified | XACML `Indeterminate` and `NotApplicable` map to kstd `escalate` and deny-by-default |
| [OpenID AuthZEN Authorization API 1.0](https://openid.net/specs/authorization-api-1_0.html) | Final Specification, approved 2026-01-12. [Interop scenarios and test vectors](https://github.com/openid/authzen) | Under OIDF IPR. The repository has no SPDX license | A transport for permit and deny decisions |
| [ODRL formal-semantics examples](https://github.com/w3c/odrl/tree/master/formal-semantics/examples) | Constraints, refinements, duties | Test contributions use the W3C 3-clause BSD license | Rights evaluation |

## 3. Gaps in kstd that the data shows

1. **Mixed origin.** Beemo, M4GT task 3 and AI Act Art. 50(4) all need text that "a model made and a person reviewed". Art. 50(4) exempts such text when it had human review and editorial responsibility. kstd `origin` has only `human`, `model` and `unknown`.
2. **Synthetic personal data.** kstd has no value for data that looks like PII but describes no real person.
3. **Collection license and item license.** kstd must keep both, as in the peS2o and RAID cases.
4. **Mapping of `escalate`.** The kstd test suite needs a published crosswalk to XACML and Cedar results.

## 4. Bodies

### W3C Web & AI Interest Group
- **Type and status:** W3C Interest Group. Chartered 2025-11-27 to 2027-11-27. Chairs: Fabien Gandon (Inria) and Liang Zeng (ByteDance). Staff contact: Roy Ruoxi Ran. [Charter](https://www.w3.org/2025/10/webai-ig-charter.html), [issues](https://github.com/w3c/webai/issues).
- **Scope:** a landscape of AI and the Web, coordination between groups, and reports. It writes no Recommendations.
- **Open issues:** [#19 Traceability and provenance](https://github.com/w3c/webai/issues/19). The comments there discuss PROV-O plus "bounded authority" and policy decisions. [#22 Standards landscape](https://github.com/w3c/webai/issues/22).
- **New paper:** "[W3C and the State of the Web in the AI Era](https://www.w3.org/2026/10/w3c-and-state-of-web-in-ai-era.html)", finalized 2026-10-20. W3C presents it at TPAC on 2026-10-29. Its recommendation 5 is to "separate disclosure, provenance evidence and training preferences, at resource and fragment level". kstd already keeps origin, rights and `ai_use` apart, so this matches. kstd does not cover fragment level.
- **Other W3C AI events, 2025–2026:**
  - Authentic Web mini-workshops (started March 2025)
  - [Smart Voice Agents](https://www.w3.org/2025/10/smartagents-workshop/report.html) (February 2026)
  - [Future of ODRL](https://www.w3.org/news/2026/w3c-workshop-report-the-future-of-odrl/), London, July 2026. It recommends an ODRL 3.0 Working Group with formal semantics and a conformance test suite.
  - [E-commerce for Humans and AI Agents](https://www.w3.org/2026/ecommerce-agents/), September 2026
  - [AI and Society mini-workshop](https://www.w3.org/events/meetings/94fde174-0fc0-4008-9416-a13739a2ff47/), 2026-10-28
- **How to take part:** you must be a W3C Member or an Invited Expert. Others can contribute on GitHub under the Patent Policy. First step: send our landscape and test-set results to #22 and #19, and feedback to [w3c/webai-roadmap](https://github.com/w3c/webai-roadmap/issues).

### W3C Agent Conformance and Benchmarking CG
- **Status:** [launched 2026-08-30](https://www.w3.org/community/agent-conformance/). The launch post said the group must still choose a chair.
- **Scope:** reproducible conformance suites, versioned benchmark corpora, and crosswalks to the AI Act and ISO/IEC 42001.
- **Overlap:** the same method as the kstd test suite.
- **How to take part:** a free W3C account and the CLA. First step: offer our decision-rule cases as a fixture set.

### EU codes of practice
- **GPAI Code of Practice** ([published 2025-07-10](https://digital-strategy.ec.europa.eu/en/policies/contents-code-gpai)):
  - The Transparency chapter has the Model Documentation Form.
  - In the Copyright chapter, Measure 1.3 says: obey robots.txt and other agreed opt-out protocols.
  - The Commission [consulted on these protocols](https://digital-strategy.ec.europa.eu/en/faqs/stakeholder-consultation-ai-and-copyright-compliance) from 2025-12-01 to 2026-01-23. The candidates were TDMRep, C2PA TDM assertions, AI.txt, the Spawning registry, JPEG Trust, TDM·AI and ODEX.
  - The final list of protocols: not verified as published.
  - There is also a [training-content summary template](https://digital-strategy.ec.europa.eu/en/library/explanatory-notice-and-template-public-summary-training-content-general-purpose-ai-models) (2025-07-24).
- **Code of Practice on AI-generated content (Art. 50):** [final version 2026-06-10](https://digital-strategy.ec.europa.eu/en/policies/code-practice-ai-generated-content). The page says about 190 signatories by the end of July 2026. The obligations apply from 2026-08-02. For systems placed on the market before that date, the [Digital Omnibus (Regulation (EU) 2026/1744)](https://www.europarl.europa.eu/legislative-train/package-digital-package/file-digital-omnibus-on-ai) moves marking to 2026-12-02.
- **How to take part:** through Commission consultations only. Only providers and deployers can sign.

### CEN-CENELEC JTC 21
- **Status:** [EN 18286](https://jtc21.eu/en-18286-becomes-the-first-harmonised-standard-under-the-eu-ai-act/) (quality management system) is the first harmonised standard. Implementing Decision (EU) 2026/2274 cited it on 2026-10-12.
- **Drafts:**
  - [Public enquiries that closed in July and August 2026](https://jtc21.eu/significant-milestone-for-european-ai-standardization/): prEN 18228 (risk management), prEN 18282 (cybersecurity), prEN 18229-1 (logging).
  - prEN 18284 (dataset quality and governance): status not verified.
- **Time limits:** the standardisation request M/613 runs until 2027-02-28. The high-risk rules apply from 2027-12-02 (stand-alone systems) and 2028-08-02 (systems in products).
- **Overlap:** the logging and data-governance drafts touch kstd receipts and inputs.
- **How to take part:** through a [national body](https://jtc21.eu/get-involved/). In Germany this is DIN/DKE NA 043-01-42 GA. Many national bodies do not charge SMEs. Another path is the European DIGITAL SME Alliance liaison.

### ISO/IEC JTC 1/SC 42
- **Status:** the [catalogue](https://www.iso.org/committee/6794475/x/catalogue/p/0/u/1/w/0/d/0) has **no dedicated data-provenance project**.
- **Related items:**
  - ISO/IEC 5259-1 to 5259-5 (2024–2025)
  - TR 5259-6:2026
  - 8183:2023 (data life cycle)
  - CD TR 25523 (data profiles)
  - AWI TS 25569 (de-identification for ML)
  - DTR 42103 (synthetic data)
  - FDIS 24970 (AI system logging)
  - CD 25590 (output data quality of generative AI)
  - AWI TS 26320 (corpus development and maintenance for NLP)
- **How to take part:** through the same DIN committee. ISO sells its standards, so we must pay to read them.

## 5. Ranked importance for us
1. W3C ODRL CG and the proposed ODRL 3.0 WG, because its conformance suite matches the kstd decision rule.
2. W3C Web & AI IG and webai-roadmap.
3. The EU opt-out protocol process and the Art. 50 code (alignment only).
4. The Cedar, OPA and AuthZEN test formats (reuse them, no membership needed).
5. W3C Agent Conformance and Benchmarking CG.
6. CEN-CENELEC JTC 21 through DIN (prEN 18284, 18229).
7. ISO/IEC SC 42.

## 6. Questions to ask them
1. **ODRL CG:** Will the ODRL 3.0 conformance tests require a reason with each result, and a third result like `escalate` or `Indeterminate`? Do you accept external test cases?
2. **Web & AI IG:** Which vocabulary should label text that "a model generated and a person reviewed"? Does disclosure at fragment level fall in scope?
3. **AI Office / EUIPO:** When will you publish the list of agreed opt-out protocols? Will it map to the AIPREF categories (search, AI input, training)?
4. **JTC 21:** Does prEN 18284 require a license, a legal basis and a lineage record for each dataset item? In which format?
5. **Agent Conformance CG:** Will you host external benchmark corpora that carry rights labels for each item? Which license will the fixtures use?

**Open points, not verified:** the status of prEN 18284; the publication of the final EU opt-out protocol list; the license of the original OASIS XACML conformance tests; the M4GT-Bench license.