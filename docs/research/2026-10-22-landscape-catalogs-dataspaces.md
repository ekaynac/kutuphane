# Landscape slice: catalogs, dataset description, data spaces, knowledge organization

Status on 2026-10-22. I fetched each claim from the linked primary source unless the text says "not verified".

## 1. W3C Dataset Exchange WG (DXWG): DCAT 3 and VVD
- **Type and status:** W3C Working Group, active. The new charter runs from 2026-04-24 to 2028-04-27 ([charter](https://www.w3.org/2026/04/dx-wg-charter.html)). The chairs are Franck Cotton, Antoine Isaac and Albert Meroño-Peñuela. The group has calls every two weeks on Thursday, and a VVD task force met on 2026-10-20 ([list](https://lists.w3.org/Archives/Public/public-dxwg-wg/)).
- **Scope:**
  - The new deliverable is the Variable Description Vocabulary (VVD). Its first public draft is due at START+11M.
  - The group also maintains [DCAT 3](https://www.w3.org/TR/vocab-dcat-3/) (Recommendation, 2024-08-22) and the RDF Data Cube vocabulary.
  - DCAT work moved to [w3c/dx-dcat](https://github.com/w3c/dx-dcat) ([dxwg#1648](https://github.com/w3c/dxwg/issues/1648)).
- **Open issues that touch our areas:**
  - [dx-dcat#7](https://github.com/w3c/dx-dcat/issues/7): DCAT checksums depend on SPDX 2 URIs, and SPDX 3 does not support them. This touches our digests.
  - [dx-dcat#10](https://github.com/w3c/dx-dcat/issues/10): versioning.
  - [dxwg#1652](https://github.com/w3c/dxwg/issues/1652): how to document use cases.
  - I found no open issue on AI-use terms or on model origin.
- **Datasets and test kits:** none that is specific to our rule. [DCAT-AP 3.0.1](https://github.com/SEMICeu/DCAT-AP) (SEMIC) has SHACL shapes. Their license is not verified.
- **Overlap with kstd:**
  - Reuse: `dcat:Dataset` and `dcat:Distribution` for items, `spdx:checksum` for digests, `dct:license` and `odrl:hasPolicy` for rights, and the version properties.
  - Gaps: no acceptance, withdrawal, contest or signed status, no `ai_use`, and no personal-data flag.
- **How to take part:** you must be a W3C Member or an Invited Expert. Anyone can comment on GitHub under the W3C Patent Policy.
- **First contribution:** a use case under dxwg#1652, plus a kstd `item` → DCAT mapping note.

## 2. schema.org (and the W3C "Schema.org for datasets" CG)
- **Status:**
  - schema.org: release [30.1, 2026-09-16](https://schema.org/docs/releases.html).
  - The [schemaorg4datasets CG](https://www.w3.org/community/schemaorg4datasets/) shows no visible activity after its 2016 call for participation. It looks dormant, but this is not verified.
- **Scope:** a general web vocabulary. The useful parts for us are `Dataset`, `license`, `usageInfo`, and `digitalSourceType` (the IPTC values, added in v24).
- **Open issues:**
  - [#3397](https://github.com/schemaorg/schemaorg/issues/3397): a `dataMining` field. It is open since 2023, and the last activity is an inactivity nudge.
  - [#4569](https://github.com/schemaorg/schemaorg/issues/4569): a proposed `Policy` type.
- **Overlap with kstd:** `digitalSourceType` covers our `origin` value. Nothing covers `ai_use`.
- **How to take part:** GitHub issues.
- **First contribution:** a comment on #3397 with an AIPREF/`ai_use` mapping.

## 3. MLCommons Croissant 1.1 and Croissant RAI
- **Type and status:** MLCommons working group, active.
  - [Croissant 1.1](https://docs.mlcommons.org/croissant/docs/croissant-spec-1.1.html) was published on 2026-01-29.
  - The [RAI spec stays at 1.0](https://github.com/mlcommons/croissant/blob/main/docs/croissant-rai-spec.md) (2024-03-06).
  - The chairs are Elena Simperl, Omar Benjelloun and Joaquin Vanschoren. The RAI workstream leads are Albert Meroño-Peñuela (also a DXWG chair) and Joan Giner-Miguelez.
  - The group meets every Wednesday ([WG page](https://mlcommons.org/working-groups/data/croissant/)).
  - MLCommons says 700K datasets carry Croissant metadata ([blog](https://mlcommons.org/2026/02/croissant-1-1-standard/)).
- **Scope:** JSON-LD dataset metadata on top of schema.org. It has:
  - `license` (an SPDX URL is recommended);
  - a `sha256` value on each FileObject;
  - PROV-O provenance at dataset, field and value level;
  - `usageInfo` with DUO/ODRL;
  - `rai:personalSensitiveInformation` (free text).
- **Open issues:**
  - [#808](https://github.com/mlcommons/croissant/issues/808): legal basis, controllership and personal data. The DPV editors joined the discussion.
  - [#1057](https://github.com/mlcommons/croissant/pull/1057): DUO/ODRL example fixes.
  - [#80](https://github.com/mlcommons/croissant/issues/80): check SHA-256 or MD5. In the 1.1 spec, some example values in the `sha256` field have only 32 hex characters, which is the MD5 length.
- **Datasets:**
  - The [repo examples in `datasets/1.1`](https://github.com/mlcommons/croissant/tree/main/datasets/1.1) include a Common Crawl draft and the Data Provenance Initiative. The repo is Apache-2.0; each dataset keeps its own license.
  - The Hugging Face endpoint `/api/datasets/<id>/croissant` returns Croissant 1.1 for each dataset. For example, `stanfordnlp/imdb` returns the license `…/licenses/other/`, which is a real "unknown" case.
  - The CroissantMiner benchmark ([arXiv 2610.07132](https://arxiv.org/html/2610.07132v1)) has 602 papers, 102 of them with gold annotations. Its license is not verified.
- **Overlap with kstd:**
  - Reuse: license, sha256 and PROV-O for `inputs`.
  - Gaps: no train / ai_input / search terms, no legal basis, no statuses, no signatures.
  - Conflict: the spec text is CC BY-ND 4.0, so a profile must link to it and must not copy it.
- **How to take part:** the [subscription form](https://mlcommons.org/community/subscribe/) and a Google account. To contribute code, send your GitHub ID through the same form.
- **First contribution:** a RAI-workstream proposal for `ai_use` (AIPREF-aligned) and a DPV legal basis, which builds on #808.

## 4. Dataspace Protocol (DSP): EDWG, IDSA, ISO
- **Status:**
  - IDSA released versions 0.8 and 2024-1. Since then the [Eclipse project](https://github.com/eclipse-dataspace-protocol-base/DataspaceProtocol) owns the protocol. The current version is 2025-1, errata 2 ([#274](https://github.com/eclipse-dataspace-protocol-base/DataspaceProtocol/issues/274)).
  - The protocol is now [ISO/IEC FDIS 26450](https://www.iso.org/standard/93502.html): stage 50.00 since 2026-10-13, with the FDIS ballot next ([EF release](https://newsroom.eclipse.org/news/announcements/eclipse-dataspace-working-group-edwg-advances-two-open-protocols-toward-global)).
- **Scope:** DSP has three parts:
  - a Catalog that reuses DCAT 3; each Dataset MUST have an ODRL Offer;
  - Contract Negotiation, which ends in an immutable ODRL Agreement;
  - a Transfer Process with the states REQUESTED, STARTED, SUSPENDED, COMPLETED and TERMINATED.

  The data plane is out of scope.
- **Open issues:**
  - [#256](https://github.com/eclipse-dataspace-protocol-base/DataspaceProtocol/issues/256): "Contract Agreement Events", that is, events after an agreement is made.
  - [#277–#279](https://github.com/eclipse-dataspace-protocol-base/DataspaceProtocol/issues): JSON-LD context defects.
- **Test kit:** [dsp-tck](https://github.com/eclipse-dataspacetck/dsp-tck) v1.0.2 (2026-09-04, Apache-2.0). It is a good model for our request → result kit.
- **Overlap with kstd:**
  - Our transfer (`deliver` → `register` → `receipt`) maps to Negotiation + Transfer.
  - Our `permit` maps to an Agreement.
  - Gaps: no item-level origin or `ai_use`, no withdrawal that reaches derivatives, no offline or package binding (DSP is HTTPS only).
- **How to take part:** an Eclipse account and the free ECA, then GitHub Discussions. EDWG membership has fees; the amounts are not verified.

## 5. Eclipse Dataspace Components (EDC): usage policies
- **Status:** active; it is the DSP reference implementation.
- **Scope:** EDC binds ODRL rules to scopes: `catalog`, `contract.negotiation`, `transfer.process`, and others. CEL expressions are experimental ([docs](https://eclipse-edc.github.io/_print/documentation/for-adopters/control-plane/policy-engine/)).
- **Conflict with kstd rule 3:** the EDC docs say that "unbound rules are filtered and ignored", and that a restricted CEL expression "is skipped silently". kstd says that an unknown required term means `deny`.
- **How to take part:** the ECA and GitHub.
- **First contribution:** propose a fail-closed option, and add our decision cases as tests.

## 6. W3C Dataspaces CG
- **Status:** W3C CG, created on 2024-05-27 (proposed by Pieter Colpaert). The [repo](https://github.com/w3c-cg/dataspaces) was last pushed on 2026-05-11. It has a `challenges.bs` document.
- **Open issues:**
  - [#20](https://github.com/w3c-cg/dataspaces/issues/20): "Roadmap 2027: benchmark solutions".
  - [#17](https://github.com/w3c-cg/dataspaces/issues/17): compile-time governance.
  - [#3](https://github.com/w3c-cg/dataspaces/issues/3): interoperable policy engines (closed).
- **How to take part:** a free W3C account and the CG CLA.
- **First contribution:** our decision-rule cases as input to #20.

## 7. SKOS and current knowledge-organization work
- **Status:**
  - [SKOS](https://www.w3.org/TR/skos-reference/) is a Recommendation from 2009-08-18. No W3C group maintains it.
  - The [public-esw-thes list](https://lists.w3.org/Archives/Public/public-esw-thes/) has had no posts since 2024-12. Its last open question was SKOS versioning and deprecation, with "no consensus".
  - I found no current W3C work on knowledge organization in my slice.
- **Overlap with kstd:** use SKOS concept schemes for `applies_to` values and for the versioned `ai_use` mapping. SKOS has no rights, origin or status.

## 8. Open Knowledge Format (OKF)
- **Verified identity:**
  - OKF is maintained by Google Cloud under Apache-2.0. Spec v0.2 is in [GoogleCloudPlatform/open-knowledge-format](https://github.com/GoogleCloudPlatform/open-knowledge-format/blob/main/SPEC.md); the repo was created 2026-08-11 and has 1,063 stars.
  - The spec moved there from [knowledge-catalog/okf](https://github.com/GoogleCloudPlatform/knowledge-catalog/tree/main/okf).
  - okf.md, openknowledgeformat.com and the CRAN `okf` package are third-party. Their relation to Google is not verified.
- **Scope:** a bundle is a directory of markdown files with YAML frontmatter. The fields are:
  - `type` (the only required field);
  - `sources` (provenance);
  - `generated.by`, with actors `human:` or `<agent>/<version>`;
  - `verified`, from which a consumer derives trust tiers that are "advisory, not access control";
  - `status` (draft / stable / deprecated);
  - `stale_after`.
- **Open issues that match kstd:**
  - [#11](https://github.com/GoogleCloudPlatform/open-knowledge-format/issues/11): deletion semantics (our disposition).
  - [#13](https://github.com/GoogleCloudPlatform/open-knowledge-format/issues/13): `refuted`.
  - [#15](https://github.com/GoogleCloudPlatform/open-knowledge-format/issues/15): an `imported` concept "without inheriting its trust" (our rule 4).
  - [#22](https://github.com/GoogleCloudPlatform/open-knowledge-format/issues/22): `supersedes` / `contested_by`, with 9 comments.
  - [#32](https://github.com/GoogleCloudPlatform/open-knowledge-format/issues/32): source visibility across a trust boundary.
  - [knowledge-catalog#52](https://github.com/GoogleCloudPlatform/knowledge-catalog/issues/52): add `license`, author and publisher. It is open, and I found no rights fields in v0.2.
- **Datasets:** the sample bundles `ga4`, `stackoverflow`, `crypto_bitcoin` and `acme_retail` are Apache-2.0. A Gemini agent made them, so their origin is `model` and they list sources. The Stack Overflow source is CC BY-SA; the version depends on the post date, which I did not verify. This makes a test case for the rights of a derivative.
- **Overlap with kstd:**
  - OKF is the closest match to kstd L0. `sources` = `inputs`, `generated.by` = `origin`, `status` ≈ acceptance, and `stale_after` ≈ maximum age.
  - Gaps: no digests, no licenses or `ai_use`, no personal data, no signatures.
- **How to take part:** the Google CLA. For a spec change, open an issue first.
- **First contribution:** a `rights` frontmatter family proposal that links knowledge-catalog#52.

## Public test sets with known rights and origin
- **[Common Pile](https://huggingface.co/common-pile)** (63 datasets; [paper](https://arxiv.org/abs/2506.05209)). It has a license for each document in `metadata.license`. The DPI-filtered subset excludes model-generated text, so its origin is `human`. The card warns about "license laundering".
- **The Croissant examples and the Hugging Face Croissant endpoint.** They give real licenses, which include "other" and unknown.
- **The OKF sample bundles.** They are model-made and have sources.
- **dsp-tck.** It is a model for the structure of a conformance kit.

## Ranked importance for us
1. OKF: same shape as L0, active, and its open trust issues match our model.
2. Croissant, including the RAI workstream: rights, provenance and datasets.
3. DSP/EDWG + TCK: transfer, agreements, and the ISO track.
4. DXWG/DCAT: the catalog base.
5. W3C Dataspaces CG: its 2027 benchmark roadmap.
6. EDC.
7. schema.org.
8. SKOS.

## Questions to ask them
1. **OKF:** Will you accept a `rights` family (SPDX license, `ai_use`, `personal_data`) and a content digest in the core? Or must these stay in a profile? What does an absent value permit?
2. **Croissant RAI:** Do you plan train / ai_input / search terms aligned with IETF AIPREF, and a DPV legal basis (#808)? When will RAI go to 1.1?
3. **DSP/EDWG:** After an Agreement is FINALIZED, how does a provider withdraw or narrow it, and how does the consumer learn of the change (#256)? Is an offline (package or data diode) binding in scope?
4. **EDC:** Can the policy engine deny on an unknown or unbound constraint, and not skip it silently?
5. **DXWG:** Must DCAT express withdrawal or supersession and model-generated origin, or must profiles do this?