# Landscape report: provenance, signed statements, identity and trust

All facts below were checked on 2026-10-22 against W3C group pages, the IETF datatracker, GitHub (`gh api`) and the specification texts. Where a fact was not checked, the text says so.

## 1. W3C Verifiable Credentials WG (VCWG)
- **Type and status:** W3C Working Group. The charter runs from 11 Mar 2026 to 31 Mar 2028 ([charter](https://www.w3.org/2026/03/vc-wg-charter.html)). The chairs are Phil Archer (GS1) and Brent Zundel (Yubico).
  - These were published as Recommendations on 15 May 2025: VCDM 2.0, Data Integrity 1.0, Bitstring Status List (BSL) 1.0 and Controlled Identifiers 1.0.
  - The publications page dates VC-JOSE-COSE (a Recommendation) at 13 Oct 2026.
  - These Working Drafts are recent: VCDM 2.1 (22 Oct 2026), BSL 1.1 (21 Oct 2026), [Recognized Entities 1.0](https://www.w3.org/TR/vc-recognized-entities-1.0/) (6 Sep 2026) and Forgery Defense (25 Aug 2026).
  - Source: the [publications page](https://www.w3.org/groups/wg/vc/publications/).
- **Scope:** The group writes a data model for issuer-signed claims, how to secure them and their status. It does not define new cryptography and does not require a ledger.
- **Open issues that touch our areas:**
  - [vc-data-model#1657](https://github.com/w3c/vc-data-model/issues/1657): which bytes `digestMultibase` hashes. This touches our artifact identity.
  - [#1600](https://github.com/w3c/vc-data-model/issues/1600) and [#1616](https://github.com/w3c/vc-data-model/issues/1616): status checks that contact the issuer ("phone home").
  - [BSL#206](https://github.com/w3c/vc-bitstring-status-list/issues/206) and [#218](https://github.com/w3c/vc-bitstring-status-list/issues/218): status privacy. The privacy protection of a list becomes weaker over time.
  - Recognized Entities: [#140](https://github.com/w3c/vc-recognized-entities/issues/140) (what the spec is for), [#116](https://github.com/w3c/vc-recognized-entities/issues/116) (OpenID Federation) and [#120](https://github.com/w3c/vc-recognized-entities/issues/120) (no test suite yet).
- **Test suites:**
  - [vc-data-model-2.0-test-suite](https://w3c.github.io/vc-data-model-2.0-test-suite/): W3C test-suite license plus a second license.
  - [vc-bitstring-status-list-test-suite](https://w3c.github.io/vc-bitstring-status-list-test-suite/): license not stated in the repository.
  - vc-di-eddsa and vc-di-ecdsa test suites: BSD-3-Clause.
  - The shared harness is [vc-test-suite-implementations](https://github.com/w3c/vc-test-suite-implementations) (BSD-3-Clause). Each implementer registers HTTP endpoints, and the reports are published again and again. **This is the model to follow for the kstd conformance suite.**
  - [VC Use Cases](https://www.w3.org/TR/vc-use-cases/) (Note, 18 Mar 2026).
- **Overlap with kstd:**
  - *Reuse:*
    - BSL status purposes: `revocation` cannot be reversed, `suspension` can be reversed, and there are also `refresh`, `ttl` and `statusMessage`. These map to kstd withdrawn, suspended and the maximum age.
    - Recognized Entities: "entity X is recognized by Y to do action A, for a schema, with `validFrom`/`validUntil`". This is close to our trust policy of issuer × kind × scope × action with an expiry.
    - Controlled Identifiers can carry issuer keys.
    - VCDM fields `termsOfUse`, `evidence` and `relatedResource` with a digest.
  - *Conflict:* Data Integrity canonicalizes RDF or JSON before it signs. kstd uses DSSE over raw bytes, which is closer to JOSE/COSE. BSL holds one bit per credential index. It has no reason and no successor field.
  - *Gap:* VCs have no rights, no `ai_use` field and no derivation inputs.
- **How to take part:** Full participation needs W3C membership or Invited Expert status. GitHub issues are open to all.
  - **First contribution:** a Recognized Entities use case, "recognized to issue statement kind K in scope S". After that, offer to help with the test suite in #120.

## 2. W3C Credentials Community Group (CCG)
- **Status:** Active. The chairs are Will Abramson, Mahmoud Alkhraishi and Denken Chen. The mailing list is [public-credentials](https://lists.w3.org/Archives/Public/public-credentials/).
- **Scope:** The group incubates work for the VCWG.
- **Work items that matter to us:**
  - [zcap-spec](https://github.com/w3c-ccg/zcap-spec) (authorization capabilities): a model for kstd delegation.
  - [did-cel-spec](https://github.com/w3c-ccg/did-cel-spec) (cryptographic event logs): a model for status streams.
  - The VC-API issuer and verifier test suites.
  - [mocha-w3c-interop-reporter](https://github.com/w3c-ccg/mocha-w3c-interop-reporter): we can reuse it for our reports.
  - VCALM moved to the WG. The CCG repository is archived.
- **How to take part:** A free W3C account and the W3C Community Contributor License Agreement (CLA). This is the easiest way into the VC family.
  - **First contribution:** a short presentation on a weekly call: "status freshness for air-gapped nodes".

## 3. W3C PROV
- **Status:** The PROV Recommendations date from 30 Apr 2013 ([PROV-O](https://www.w3.org/TR/prov-o/)). The Working Group is closed. I found no active W3C group (not verified that none exists).
  - [w3c/prov](https://github.com/w3c/prov) was re-imported in Jun 2026, with no new content. It contains a `testcases/` folder (PROV-CONSTRAINTS).
  - Current community work is in academic papers, for example [PROV-AGENT](https://arxiv.org/abs/2508.02866), which uses PROV with MCP for agent workflows.
- **Overlap with kstd:** `wasDerivedFrom`, `used` and `wasGeneratedBy` map to *derive* and *inputs*. `wasAttributedTo` maps to *origin*. kstd already lists PROV-O as a profile.
- **Gap:** PROV has no signatures, no status and no rights.
- **How to take part:** There is no group to join. Publish the PROV-O mapping profile together with test data.

## 4. Nanopublications (Knowledge Pixels and the nanopub network)
- **Status:** [Nanopublication Guidelines](https://nanopub.net/guidelines/working_draft/), Working Draft of 30 Sep 2026. This is a community document, not a W3C document. I found no W3C CG.
  - The second-generation network uses Nanopub Registry and Nanopub Query.
  - The [ecosystem paper](https://knowledgepixels.com/nanopub-ecosystem-paper/) (changed 17 Jul 2026) describes the IDEBT trust algorithm. It also gives a snapshot: 79,672 nanopublications from 616 agents (2026-05-04).
- **Scope:** A nanopublication has an assertion, its provenance and its publication info. Each is an RDF named graph. A Trusty URI (a content hash) is the identifier, and the publication is signed with RSA.
  - Retractions and supersessions are new nanopublications. A registry only marks the target as *invalidated*. Deletion happens only at one registry, for example when the law requires it.
  - Each registry publishes a *setting* (its trust seed). A key that two or more agents claim is marked *contested*.
- **Test suite:** [nanopub-testsuite](https://github.com/Nanopublication/nanopub-testsuite) (MIT), with valid, invalid and transform cases. There are connectors for Java, Python and JavaScript.
- **Overlap with kstd:**
  - *Reuse:* their unit of knowledge maps to `item`; retraction and supersession map to withdrawal with a successor; contested maps to `contest`.
  - *Conflict:* trust is a computed score, not an explicit grant. Records are public and cannot be changed, which conflicts with `erase` and personal data. Identity uses RDF canonicalization.
  - *Gap:* nanopublications have no rights and no `ai_use` field.
- **First contribution:** Map the kstd statement kinds to nanopub types, and run the test suite against that mapping.

## 5. W3C Linked Web Storage WG (LWS, the standardization of Solid)
- **Status:** The charter started on 9 Sep 2024 and was extended to 8 Jan 2027. A [draft recharter](https://w3c.github.io/lws-wg-charter/) plans a Candidate Recommendation in Q2 2027 and a Recommendation in Q2 2028.
  - The chairs are Coburn (Inrupt), Debackere and Prud'hommeaux.
  - Working Drafts: [LWS Protocol 1.0](https://www.w3.org/TR/lws10-core/) (19 Oct 2026) and the authentication suites for OpenID, SAML and SSI-CID (15 Oct 2026).
  - Notes: [Use Cases](https://www.w3.org/TR/lws-ucs/) and Vocabulary.
- **Scope:** A protocol to store and access data on storage that the user selects. New data formats and new identity mechanisms are out of scope.
- **Open issues:** [#196](https://github.com/w3c/lws-protocol/issues/196) (LWS mapped to ODRL), [#143](https://github.com/w3c/lws-protocol/issues/143) (ODRL profile for access requests) and [#278](https://github.com/w3c/lws-protocol/issues/278) (requirements for an agent identity scheme).
- **Overlap with kstd:** LWS sits *below* our waist, as storage and transport. It is a binding target and not a competitor. It does not cover statements, status or rights.
- **First contribution:** A use case in [lws-ucs](https://github.com/w3c/lws-ucs): "statements travel with resources; decide before deliver". Then comment on #278.

## 6. in-toto Attestation Framework and DSSE
- **Status:** in-toto became a CNCF graduated project on 23 Apr 2025 ([CNCF](https://www.cncf.io/announcements/2025/04/23/cncf-announces-graduation-of-in-toto-security-framework-enhancing-software-supply-chain-integrity-across-industries)). [Attestation v1.2.0](https://github.com/in-toto/attestation/tree/main/spec) was released on 18 Mar 2026 (Apache-2.0). DSSE protocol v1.0.2 uses PAE.
- **Scope:** The layers are Predicate, Statement (subject digests plus `predicateType`), Envelope (DSSE) and Bundle. Registered predicates include VSA, SCAI, test-result, release and reference.
- **Open issues:**
  - [#67 attestation revocation](https://github.com/in-toto/attestation/issues/67), open since 2021. A comment of 2026-10-02 says: "valid revocation statement ≠ authority to revoke". This is kstd rules 4 and 8.
  - [#604](https://github.com/in-toto/attestation/issues/604): human/AI attribution for each range of lines in a file. This is our *origin*.
  - [#565](https://github.com/in-toto/attestation/issues/565): eval-result predicate.
  - [#594](https://github.com/in-toto/attestation/issues/594): capability predicate. This is close to our *activation*.
  - [#600](https://github.com/in-toto/attestation/issues/600): agentic process evidence.
- **Overlap with kstd:** A kstd statement is almost an in-toto Statement in DSSE, with `kind` as the `predicateType`. **Reuse it directly.**
  - *Gap:* in-toto has no status and no revocation.
- **First contribution:** A comment on #67 with our rules. Then register kstd predicate types.

## 7. Sigstore / Rekor (OpenSSF)
- **Status:** Rekor v2 is the tile-based log ([rekor-tiles](https://github.com/sigstore/rekor-tiles)): v2.0.0 was released on 10 Oct 2025 and v2.3.0 in Jun 2026.
  - [sigstore-conformance](https://sigstore.github.io/sigstore-conformance) publishes a client report every day.
  - [model-transparency](https://github.com/sigstore/model-transparency) (Apache-2.0, v1.1.1) signs ML models.
- **Overlap with kstd:** This fits our transparency-witness profile and the L2 tamper-evident audit.
- **Conflict:** A public log does not fit air-gapped nodes or personal data. Log only digests.

## 8. SLSA (OpenSSF)
- **Status:** [v1.2](https://slsa.dev/spec/v1.2/), with a Build track and a Source track. The git tag v1.2 points to a commit of 24 Nov 2025. The specification uses the Community Specification License 1.0.
- **Reuse:** the levels pattern, and the VSA. A VSA is a signed, short-lived decision result. It maps to our `permit` with an expiry (rule 7).

## 9. TUF (The Update Framework)
- **Status:** Specification [v1.0.37](https://theupdateframework.github.io/specification/latest/) of 8 Oct 2026. [tuf-conformance](https://theupdateframework.github.io/tuf-conformance/) v2.5.0 (MIT).
- **Reuse:** a short timestamp expiry and checks against freeze attacks. These map to our status maximum age. TUF delegates roles by path, with thresholds. This maps to trust per scope.
- **Gap:** TUF sees only files. It knows nothing about rights.

## 10. IETF SCITT WG (related to this slice)
- **Status:** [RFC 9943](https://datatracker.ietf.org/doc/rfc9943/) (architecture, Jun 2026). [RFC 9942](https://datatracker.ietf.org/doc/rfc9942/) (COSE Receipts, Jun 2026, from the COSE WG). SCRAPI is in the RFC Editor queue. The chairs are Jon Geater and Nicole Bates.
- **Individual drafts:**
  - [statement identification: requirements and test cases](https://datatracker.ietf.org/doc/draft-gruszka-scitt-statement-identification/).
  - [AI Act Art. 50 receipts](https://datatracker.ietf.org/doc/draft-dawkins-scitt-ai-article50/).
  - Many profiles for AI agents.
- **Overlap with kstd:** Issuer, Signed Statement and Registration Policy map to our *register* and acceptance policy.
- **Conflict:** In SCITT, a **"Receipt" is a proof that a statement is in a log**. A kstd `receipt` is a use or outcome record. **Rename ours**, for example to `use_record`.
- **How to take part:** Open. Join the mailing list. No membership is necessary.

## Ranking for kstd
1. **VCWG**: BSL, Recognized Entities and a test-suite model.
2. **in-toto Attestation and DSSE**: the statement envelope and revocation in #67.
3. **IETF SCITT**: signed statements, receipts, and the term conflict.
4. **Nanopublications**: the nearest "unit of knowledge" with retraction and trust.
5. **TUF**: the freshness model.
6. **CCG**: an easy way in, and work on delegation and event logs.
7. **LWS**: a binding below the waist.
8. **Sigstore**.
9. **SLSA**.
10. **PROV**: a mapping only.

## Questions to ask them
1. **VCWG (BSL):** Can a status entry carry a reason and a successor? Can a status list travel offline in a package, with `ttl` as the maximum age?
2. **VCWG (Recognized Entities):** Can `recognizedTo` express "statement kind × scope × action" for issuers that are not credential issuers?
3. **in-toto (#67):** Is the authority to revoke a policy question or a predicate field? Will you accept a generic predicate for status and withdrawal?
4. **Nanopub:** Will you accept an explicit per-issuer trust grant next to the IDEBT scores? How do you plan to handle personal data and erasure in records that cannot be changed?
5. **SCITT:** Does a Registration Policy result carry permit, deny or escalate? Do you agree on separate terms for a log inclusion receipt and a usage record?