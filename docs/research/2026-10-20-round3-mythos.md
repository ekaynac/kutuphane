# Brainstorm round 3 — Mythos

## 1. Thesis

Knowledge management in the age of AI is not the management of documents. It is the management of **accountability for statements that machines will act on**. Knowledge is now cheap to make, costly to trust, and impossible to un-share. Half of new web articles are machine-written, and no detector can prove human authorship. The standard must therefore manage three scarce things: **who stands behind a statement**, **what may be done with it and with everything derived from it**, and **how a change of mind reaches every copy**. The shape is an hourglass: a narrow waist of content-addressed objects and signed records, with formats, models and languages free to change above it, and storage and transport free to change below it. The operations are few: ingest, annotate, resolve, deliver, derive, transfer. Two laws hold the waist together: rights and handling never weaken through derivation, and uncertainty never increases authority.

## 2. Blind spots

Ranked by importance. Each has evidence.

**B1. We have no harvester, and the commons is draining.** Every standard that won had a party that read the data and rewarded the producer. Search engines made schema.org worth the effort ([Google, 2015](https://www.research.google/blog/four-years-of-schemaorg-recent-progress-and-looking-forward/); [W3C list, 2014](https://lists.w3.org/Archives/Public/public-vocabs/2014May/0069.html)). Regulators made SBOMs mandatory, and SPDX followed ([InfoQ, 2026](https://infoq.com/news/2026/03/sbom-viktor-petersson)). Funders made FAIR a condition of grants ([Max Planck report](https://arxiv.org/pdf/2402.18182)). Tool ecosystems made OpenAPI, MCP and AGENTS.md ([Anthropic, Dec 2025](https://www.anthropic.com/news/donating-the-model-context-protocol-and-establishing-of-the-agentic-ai-foundation); [arXiv 2601.20404](https://arxiv.org/html/2601.20404v2)). The ones that died had theory and goodwill: the Semantic Web ([arXiv 2609.14121](https://arxiv.org/pdf/2609.14121)), Solid ([Fast Company](https://www.fastcompany.com/91231379/tim-berners-lee-solid-inrupt-pod-digital-wallet)), TDMRep ([W3C CG report](https://www.w3.org/community/reports/tdmrep/CG-FINAL-tdmrep-20240510/)), and llms.txt, where 97 % of files get zero requests ([Ahrefs via PPC Land](https://ppc.land/llms-txt-adoption-rises-8-8x-but-97-of-files-get-zero-ai-requests/)). Our vision names no consumer that rewards a producer. Worse, the "network of nodes" assumes that organizations share. The evidence runs the other way: Stack Overflow activity fell 16–25 % after ChatGPT ([PNAS Nexus](https://arxiv.org/pdf/2307.07367)), Wikipedia lost 8 % of human views ([Computing, 2025](https://www.computing.co.uk/news/2025/ai/wikipedia-reports-traffic-drop)), and 28 % of the most important web sources closed to crawlers in one year ([Consent in Crisis, NeurIPS 2024](https://arxiv.org/pdf/2407.14933v1)). **Counter:** the harvester must be the agent runtime and the gateway. An agent that reads the manifest must behave better, visibly, on day one. The second harvester is regulation: the standard must emit the AI Act Article 53 training-data summary and an Article 50 provenance record from its own log, the way SPDX emits an SBOM.

**B2. The reference implementation is proprietary.** D10 and D22 make Kütüphane proprietary and keep AGPL out of the core. D55 makes the standard open. No standard in the list above won with a closed reference implementation: Swagger was donated to the Linux Foundation before it became OpenAPI ([history](https://dev.to/mikeralphson/a-brief-history-of-the-openapi-specification-3g27)), and MCP is Apache-2.0. At minimum, the validator, the bundle format and the resolve algorithm must be open source.

**B3. Rights vocabularies are being standardized now, by others.** The IETF AI Preferences working group has a vocabulary at draft 06 ([draft-ietf-aipref-vocab-06](https://www.ietf.org/archive/id/draft-ietf-aipref-vocab-06.html)), with attachment through robots.txt and HTTP headers ([charter](https://datatracker.ietf.org/wg/aipref/about/)). Cloudflare ships `search`, `ai-input`, `ai-train` signals and calls them Article 4 reservations ([Cloudflare](https://blog.cloudflare.com/content-signals-policy/)). RSL 1.0 adds licensing and payment terms ([RSL](https://rslstandard.org/)). The OLG Hamburg held in December 2025 that a natural-language reservation is not machine-readable, with appeal to the BGH admitted ([Open Future](https://openfuture.eu/blog/laion-round-2-machine-readable-but-still-not-actionable/)). Our bespoke "TDM reservation" flag is late. **Counter:** adopt the AIPREF terms as the rights vocabulary and map to Content Signals and RSL.

**B4. Derived artifacts are content, and we have no rule for them.** Text embeddings can be inverted to near-exact text ([vec2text](https://arxiv.org/pdf/2310.06816)). The Munich court held that memorized lyrics inside model weights are a reproduction ([Verfassungsblog](https://verfassungsblog.de/munich-regional-courts-ruling-in-gema-v-open-ai/)). Models already pass KV caches to each other without text ([C2C](https://arxiv.org/html/2510.03215v1); [Latent Cache Flow](https://arxiv.org/pdf/2605.22863)). Our v2 applies Sensitivity to vectors, but the standard has no first-class **derive** operation that records inputs and inherits rights. Without it, laundering is one summary away.

**B5. Revocation does not travel by itself.** Only 5.4 % of citations after a retraction mention the retraction ([PMC9520488](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC9520488/)), and only 3 % of retracted papers are flagged in all four major databases ([Enago](https://www.enago.com/academy/why-retractions-dont-reach-the-papers-that-cite-them/)). Push fails. Certificate Transparency works because receivers check logs and monitors watch them ([monitoring paper](https://arxiv.org/pdf/1711.03952)). **Counter:** status is resolved at use time from the origin node's log, and derived items carry their inputs, so a revocation finds every descendant.

**B6. Provenance cannot be read from content; it can only be signed.** About 50 % of new articles are machine-written and the share has plateaued ([Axios, 2026](https://axios.com/2026/05/15/human-vs-ai-written-articles)). Text watermarks are removable and centralized, and C2PA has no text profile ([Eden AI](https://www.edenai.co/post/beyond-detection-why-the-web-needs-a-standard-to-flag-ai-generated-content)). So "origin" is a claim by the submitting signer, not a fact. The gate belongs on the **accountable signer**, not on the origin value. Origin still changes behavior: training eligibility, because training on model output causes collapse ([Shumailov, Nature 2024](https://oatml.cs.ox.ac.uk/publications/202407_Shumailov_ModelCollapse.html)), and Article 50 labelling.

**B7. A parallel memory standard is forming.** The W3C AI Agent Memory Interoperability Community Group adopted its charter in June 2026, around an IETF draft with encrypted memory units, post-quantum signatures, sharing with revocation and cryptographic erasure ([W3C CG charter](https://www.w3.org/community/ai-agent-memory-interop/2026/07/16/charter-ai-agent-memory-interoperability-community-group-v1-0/)). It overlaps with L1–L3. We must map to it or join it.

**B8. Instruction is not a label; every block is a potential instruction.** Five poisoned documents hijack a RAG answer 90 % of the time ([PoisonedRAG, USENIX 2025](https://www.usenix.org/conference/usenixsecurity25/presentation/zou)). EchoLeak was a zero-click injection through one email ([OWASP MCP06](https://owasp.org/www-project-mcp-top-10/2025/MCP06-2025–Prompt-InjectionviaContextual-Payloads)). A human-labelled `agent instruction = yes/no` facet does not stop this. **Counter:** the **deliver** operation always presents content as typed data, and only a record of role `executable` can be activated. Executable knowledge already has a format: Agent Skills, adopted by 25+ platforms ([agentskills.io](https://agentskills.io)).

**B9. Crypto agility is missing.** NIST plans to deprecate classical signatures by 2030 and disallow them by 2035 ([NIST IR 8547 summary](https://postquantum.com/security-pqc/nist-ir-8547-ipd/)). Records that must stay verifiable until 2035 cannot be Ed25519-only. SWHID became ISO/IEC 18670 with a hash-agnostic Merkle design ([SWHID](https://www.swhid.org/)).

**B10. The legal state of logs is clearer than we think.** The EDPB says hashed identifiers remain personal data and recommends off-chain storage ([CMS on EDPB 02/2025](https://cms.law/en/hrv/legal-updates/edpb-issues-draft-blockchain-guidelines-part-1)). The CJEU held in September 2025 that pseudonymized data may not be personal data for a recipient who cannot re-identify ([Goodwin](https://www.goodwinlaw.com/en/insights/publications/2025/09/alerts-technology-dpc-personal-data-or-not)). So: the log stores salted commitments, the salt stays with the origin node, and erasure destroys the salt and the key. Receivers never hold personal data in the log.

**B11. ODRL has no enforcement semantics.** The recommendation is an ontology only ([OPAL 2025](https://ceur-ws.org/Vol-3977/OPAL2025-6.pdf)), and its conflict rule fires only on the exact same action and asset ([HSBC, W3C workshop 2026](https://www.w3.org/2026/ODRLWS/PP/02-BeyondPermit-HSBC.pdf)). We should serialize to ODRL and keep our own small decision rule normative.

**B12. Regulation moves.** The Digital Omnibus proposes to move high-risk duties to December 2027 and to change the GDPR ([CADE](https://cadeproject.org/updates/eus-digital-omnibus-proposes-major-delay-to-ai-act-high-risk-rules/)). Article references belong in a compliance profile, not in the core.

## 3. The standard's core

### 3.1 The narrow waist

Three transferable types and one local structure. The design copies Git, SWHID and in-toto: few object kinds, content addresses, a signed statement with a typed predicate ([in-toto predicates](https://github.com/in-toto/attestation/blob/v1.0.2/spec/predicates)).

| Type | What it is | Why it exists |
|---|---|---|
| **Object** | Bytes plus a media type, addressed by an agile hash (multihash). Any format: Markdown, PDF, vectors, weights, a skill folder. | Knowledge may leave human language. The waist must not care. |
| **Record** | A signed, content-addressed statement about objects or records: `signer, about[], kind, body, time`. Four closed kinds: `item`, `opinion`, `policy`, `event`. | The smallest unit that travels alone. |
| **Bundle** | A signed manifest plus objects and records, as a plain directory or tar (BagIt-like, [RFC 8493](https://www.rfc-editor.org/rfc/rfc8493.html)). | The transfer unit. Works over USB and data diodes. |
| **Log** | The node's append-only sequence of records and receipts. Every state is a fold over the log. Personal data stays out, by commitment. | Audit, erasure, replay protection. |

An `item` record is the claim envelope of docs/10: it names objects, and carries the intrinsic facts: origin, rights, inputs, personal-data flag. The record hash covers these and nothing local. An `opinion` record is an annotation. A `policy` record is a grant, prohibition, obligation or dispensation from an authority. An `event` record is a transition: approve, contest, retire, supersede, erase, receipt.

**Blocks are not in the waist.** They are a chunking profile of one implementation.

### 3.2 The verbs

| Verb | Does | Gate |
|---|---|---|
| **ingest** | Makes an `item` from objects. Records origin, rights, inputs, signer. | Unknown rights → `no` for every use. |
| **annotate** | Adds an `opinion`, `policy` or `event` record. | Imported opinions are proposals. Looser moves need the named local actor. |
| **resolve** | Computes the effective state for one request: fold the log, apply the trust policy, apply the strictness lattice, check status of inputs. | Uncertainty never raises authority. |
| **deliver** | Gives content to a principal or an agent: as data, as citation, as export, or as an activated executable. | Data is always typed as data. Only `executable` can be activated, and only with a grant. |
| **derive** | Makes a new object and item from inputs: chunk, embed, summarize, consolidate, fine-tune. | The new item's rights and handling are the **meet** of its inputs. Inputs are recorded. Origin is `model` or `composite`. Standing is `pending`. |
| **transfer** | Sends or receives a bundle: verify, quarantine, diff, accept, receipt. | A node never forwards what the receiver's rights do not allow. The receiver signs a receipt. |

Retire and erase are `event` records made by **annotate**. Erase also destroys keys. Consolidation is **derive**, and it is the main loop of agent memory: a new object from old ones, never an edit ([Letta sleep-time compute](https://letta.com/blog/sleep-time-compute)).

### 3.3 Facets and behaviors

**Intrinsic** (inside the `item`, signed by the submitter, travel):

| Facet | Values | Behavior |
|---|---|---|
| **Origin** | `human`, `model`, `composite`, `external` (IPTC Digital Source Type terms, [IPTC](https://cv.iptc.org/newscodes/digitalsourcetype/)) | `model` and `composite`: not used as training or consolidation input without a human approval; output carries an Article 50 mark; never the sole basis of a `rule`. |
| **Rights** | license (SPDX id), holder, use preferences (`search`, `ai-input`, `train` from AIPREF), personal data `yes/no/unknown` | Gates **derive** (`train`, embed), **deliver** (export) and **transfer**. Unknown means no. Personal data `yes` or `unknown`: object encrypted, commitment in the log. |
| **Inputs** | record ids of the sources of a derived item | Revocation propagates to descendants. Rights meet. Blast radius after poisoning. |

**Opinion** (annotations, local, from trusted signers, become proposals when imported):

| Facet | Values | Behavior |
|---|---|---|
| **Role** | `rule`, `evidence`, `executable`, `none` | `rule`: can establish a requirement, highest citation authority. `evidence`: support only. `executable`: delivered only by activation, never as evidence. `none`: not indexed. |
| **Standing** | `approved`, `pending`, `retired` | Only `approved` is current. `retired` names a successor or a terminal reason, and suspends linked grants. A `contest` event marks the item and opens a review, but it does not change standing. |
| **Validity** | `durable`, `window(start, end)` | Current only inside the window. `as_of(t)` is `window(t, t)`. |
| **Scope** | `unbounded`, `bounded(ids, exclusions)` | A bounded `rule` with no request context asks for the context and does not answer with authority. |
| **Handling** | export: `normal`, `restricted`; route: `cloud_ok`, `local_only` | Export is owned by one value, route by the other. Derived objects inherit the stricter value. Before confirmation: `local_only`. |

**Node** (local policy, signed by the node):

| Facet | Behavior |
|---|---|
| **Trust policy** | Which signers' opinions become proposals, which stricter opinions apply at once, key expiry, label expiry. Copies the labeler model of the AT Protocol: the client chooses whom to trust, labels carry source and expiry ([atproto labels](https://atproto.com/guides/labels)). |

Wikidata shows the same pattern at scale: three ranks, and only the best non-deprecated rank is "truthy" ([Wikidata ranks](https://qwikidata.readthedocs.io/en/stable/entity.html)).

### 3.4 State transitions

Every transition is an `event` record. Reversal is a new event. Time is evaluated at each request.

| Transition | Trigger | Actor | Automatic |
|---|---|---|---|
| new → `pending` | ingest or derive | system | yes |
| `pending` → `approved` | review; the author is never the approver; an optional k-of-n quorum | accountable human | no |
| `approved` → `pending` | content or inputs changed; an input was retired or contested | system | yes |
| `approved` → `retired` | supersession in shared scope, or removal | system | yes |
| any → `retired` | rejection with reason | curator | no |
| `retired` → `pending` | reopen | curator | no |
| item → `contested` mark | a `contest` event from a trusted signer | any trusted signer | yes, mark only |
| grant active → suspended | source item retired | system | yes |
| obligation issued → discharged / violated → escalated | receipt or deadline | receiver node / system | discharge needs a signed receipt |
| bundle received → quarantined → accepted / rejected | transfer | system, then a human | accept is human at L2+ |
| object readable → erased | erasure request | administrator | key and salt destroyed; records stay as commitments |

**Status resolution across nodes:** at **resolve**, a receiver checks the status of imported items against the origin node's log, directly or through a cached status feed with a time-to-live. If the status cannot be checked, the item keeps its content but loses `rule` authority until checked.

### 3.5 Conformance levels and where rights go

| Level | Requires | Rights |
|---|---|---|
| **L0 Described** | Files with a manifest: object hashes, origin, rights, personal-data flag. A validator passes. One hour. The dumb-down rule: a tool that ignores every field still reads the file ([Dublin Core](https://www.dublincore.org/resources/glossary/dumb-down_principle/)). | Declared: SPDX id, holder, AIPREF use preferences. |
| **L1 Signed** | Content-addressed objects, signed records, bundles, derive records inputs. Agile hashes and signatures. | Travel inside the signed item. |
| **L2 Governed** | Resolve with the lattice, roles and standing, deliver gates, derive gates, log with commitments, erasure by key destruction, KBOM export (Article 53 summary, Article 50 record). | Enforced on derive and deliver. Policies serialize to ODRL. Unknown term means deny. |
| **L3 Federated** | Transfer with receipts, trust policies, status resolution, revocation to descendants, obligations with state. | Enforced across nodes. The receiver is the enforcement point and must be L2. |

## 4. Reuse

**Compose:**
- **SWHID / ISO/IEC 18670** for content addresses and Merkle directories ([SWHID](https://www.swhid.org/)). Multihash for agility.
- **in-toto Statement** shape for records: signer, subjects, predicate type, predicate. **VC 2.0** as an optional securing profile, with SD-JWT for EUDI compatibility ([W3C, 2025](https://www.w3.org/press-releases/2025/verifiable-credentials-2-0)).
- **BagIt** for bundles ([RFC 8493](https://www.rfc-editor.org/rfc/rfc8493.html)).
- **AIPREF** vocabulary for use preferences, mapped to Cloudflare Content Signals and RSL ([draft-06](https://www.ietf.org/archive/id/draft-ietf-aipref-vocab-06.html)).
- **SPDX** ids for licenses; **IPTC Digital Source Type** for origin.
- **Agent Skills** for `executable` items ([agentskills.io](https://agentskills.io)); **AGENTS.md** for repository-level instructions.
- **AT Protocol labels** as the model for opinions with source and expiry.
- **Zanzibar via OpenFGA** (CNCF incubating, AuthZEN endpoint) for grants ([OpenFGA](https://openfga.dev/project)).
- **PROV-O** and **ODRL** as export serializations only.
- **Croissant** for training-set descriptions when a node emits a KBOM ([Croissant](https://research.google/blog/croissant-a-metadata-format-for-ml-ready-datasets/)).
- **Certificate Transparency** pattern: logs plus monitors, for status feeds.

**Avoid:**
- Mandatory RDF, OWL or SHACL. The signed nanopublication network holds about 80,000 records after ten years ([registry](https://registry.knowledgepixels.com/np/RAtqqKPQFRqGTLyv5gy48hqKXPGQA4Fl3-c151YNxONEk)). The claim shape is right; the stack is not.
- ODRL as the normative decision rule (B11).
- A general DHT or IPFS: content addressing without an index is unusable ([critique](https://fiatjaf.com/0fe2c649.html)).
- ISO 30401 as a model: it is process prose with no machine behavior ([RealKM](https://realkm.com/2018/01/05/critical-eye-iso-30401-draft-standard-knowledge-management-systems/)).
- Machine unlearning as an erasure mechanism: forgotten facts come back after small fine-tunes ([arXiv 2505.16831](https://arxiv.org/abs/2505.16831v1); [NeurIPS 2025](https://arxiv.org/abs/2506.05735v2)).
- Data-space consortia as the federation model: Gaia-X maturity is limited outside Catena-X ([ABB](https://new.abb.com/news/detail/106135/gaia-x)).

## 5. Durability tests

**2027: agents write 80 % of items.** Ingest signs origin `model`; derive records inputs; standing is `pending`. Only `rule` needs a human. Load is handled by quorum and by event-triggered review, not by date. **Holds.** The AI Scientist already produces papers that pass workshop review ([Nature, 2026](https://vectorinstitute.ai/?p=26786)), so the volume is real.

**2028: ten-million-token contexts, no retrieval.** Organizations paste the whole library. **Deliver** still runs at the gateway, and resolve returns a filtered bundle, not chunks. Opinions attach to records, not to chunks. **Holds.** Blocks lose importance, which is why they left the waist.

**2029: agents exchange latent packets.** A KV cache is an object. Derive records its inputs and inherits handling. The data-versus-instruction boundary cannot be enforced inside a latent, so the gate moves to **which inputs may enter the derivation** and to the receiving model's route. **Holds, with one change:** the deliver gate for latents is a pre-derive gate.

**2030: a node fine-tunes on the commons; classical signatures are deprecated.** Training is a derive with inputs. The model is an object with the meet of all input rights and handling. The KBOM is the Article 53 summary. Records are re-signed with ML-DSA; hashes stay valid because identifiers are agile. **Holds.**

**2032: a poisoned bundle is found two years after import.** The inputs graph gives the blast radius, including a fine-tuned model. The model becomes contested, then retired, and the policy is retrain or quarantine, never "unlearn". A status feed tells every receiver. **Holds only if L3 status resolution exists.** Without it, we repeat the retraction record.

## 6. Kill list

- **The block rule, sections, continuity table (docs/09 §1).** Local chunking profile, not standard.
- **Agent instruction facet.** Merged into Role `executable`, with the Agent Skills format.
- **Origin as "metadata, no gate".** Origin gates training and consolidation input and marks outputs. The authority gate is the accountable signer.
- **The bespoke TDM reservation field.** Replaced by the AIPREF vocabulary.
- **Policy as a separate waist type.** It is a `policy` record.
- **Ed25519 as the only signature.** Agile hashes and signatures.
- **Presets K1–K8, the labelling protocol, the blind slice.** Product process, outside the standard.
- **"Nanopublication-style sync" wording.** Keep the pull journal, drop the RDF.
- **D10 as it stands.** A proprietary reference implementation kills an open standard.

## 7. Failure modes

| Failure | Counter-measure |
|---|---|
| **No adoption:** nobody reads the manifest. | Ship the harvester first: LLMDAP and the agent runtime behave visibly better with a manifest. Ship a validator and a one-hour L0 guide. Emit regulatory outputs (KBOM, Article 50 record) from the log. Open-source the core. |
| **Sharing collapses:** nodes take and do not give. | Receipts and obligations make sharing bilateral. A node can require freshness and attribution from the receiver, as dataspaces do. |
| **Poisoning and injection.** | Deliver as typed data; activate only `executable` with a grant; quarantine on import; inputs graph for blast radius; stricter proposals apply at once, looser ones never without a human. |
| **Laundering:** model text enters as human text. | Origin is a signed claim by an accountable signer. The signer's key is the gate. A false origin is a signed lie, with a name on it. |
| **Facet creep.** | The canon rule: a value with no behavior is removed. Closed kinds. A conformance test suite with fixtures. |
| **Law:** logs hold personal data; regulation shifts. | Commitments with a secret salt, erasure by destruction, data minimization in logs. Legal mappings live in a dated compliance profile. |
| **A competing standard wins:** the W3C memory group or the IETF memory protocol. | Map record kinds to their memory units early. Join the group. Position the standard as the knowledge layer beneath agent memory. |
| **Governance capture.** | Foundation home (Agentic AI Foundation or similar), Apache-2.0 code, CC-BY text, public test suite. |

## 8. Questions for the operator

1. Will the standard's core, the validator, the bundle format and the resolve algorithm, be open source despite D10? Without this, I expect the standard to fail.
2. Is LLMDAP the enforcement point for **deliver** and **derive** gates from day one, so that the gateway is the first harvester?
3. Should we join the W3C AI Agent Memory Interoperability group and map to its memory units, or position beneath it?
4. Is the record, not the block, acceptable as the smallest unit? This changes labelling v4.
5. Do you accept Role `executable` as the merge of agent instruction and skills, with the Agent Skills format as its profile?