## 1. Thesis

Knowledge is a resource that a community can justify using for a stated purpose, under stated conditions. Its form can be text, observations, code, vectors, or model weights. The standard should preserve the link between that resource, its evidence, its permitted uses, and the parties accountable for it. Its core should contain two record types: **artifacts and attestations**—statements by named parties about artifacts. Each node makes local decisions from these records. The main loop is capture, test, authorize use, observe results, and correct or remove. Consolidation is one step in this loop. Durable knowledge management requires clear limits on authority, transfer, and retention.

## 2. Blind spots

Ranked by importance:

1. **The draft promises more control than a network can provide.** Withdrawal of approval, withdrawal of access, correction, and erasure are different actions. None recalls every copy already delivered. Some licenses also remain valid after the publisher changes its mind; Creative Commons explicitly describes this limit. Define each action and its reach. [Creative Commons FAQ](https://creativecommons.org/faq/#what-if-i-change-my-mind-about-using-a-cc-license)

2. **Rights and provenance are claims, not intrinsic facts.** A signature binds a statement to a key; it does not establish ownership, truth, or authority. C2PA makes this distinction. Replace “intrinsic versus opinion” with “artifact identity versus attributed statements.” Preserve disputed statements without making them effective policy. [C2PA explainer](https://spec.c2pa.org/specifications/specifications/1.3/explainer/_attachments/Explainer.pdf)

3. **“Erasure is key destruction” is too strong.** Keys, plaintext, vectors, backups, identifiers, and derivatives can survive separately. The EDPB explains why encrypted and hashed data can remain personal data. Its blockchain guidance supports a narrower design lesson: keep deletable records, minimize permanent metadata, and verify the scope of deletion. [EDPB Guidelines 02/2025](https://www.edpb.europa.eu/documents/guideline/guidelines-022025-on-processing-of-personal-data-through-blockchain_et)

4. **Freshness is a security boundary.** An offline node cannot detect a withheld revocation from signatures alone. Use signed sequence numbers, expiry, and a declared maximum age for authorization evidence. TUF already addresses rollback and freeze attacks. Expiry must stop the affected authoritative use, without claiming that the underlying statement became false. [TUF specification](https://theupdateframework.github.io/specification/latest/index.html)

5. **An instruction label cannot secure agent behavior.** Hostile instructions can occur in evidence, images, or tool descriptions. MCP treats tool annotations as untrusted unless their source is trusted. Govern activation and execution at the host and tool boundary; do not depend on a classifier finding all instructions. [MCP tools](https://modelcontextprotocol.io/specification/2025-11-25/server/tools)

6. **The time model loses useful evidence.** In `docs/09`, `as_of(t) = window(t,t)` removes a dated observation from ordinary use immediately. A 2024 measurement can still support a 2026 analysis. Separate observation time, applicability time, and approval expiry. Wikidata’s qualifiers illustrate why dated statements need context rather than automatic dismissal. [Wikidata qualifiers](https://www.wikidata.org/wiki/Help:Qualifiers)

7. **The commons needs a benefit model.** More sharing does not ensure fair benefit or community control. CARE addresses this gap directly. Start with a clear exchange: contributors receive corrections, tested procedures, attribution, and lower review costs. Sharing remains a separate choice from adoption. [CARE principles](https://www.gida-global.org/careprinciples)

The supplied papers suggest useful mechanisms, but agreement between conceptual papers does not validate them. For example, Jev-Mem reports memory performance on LoCoMo with model-based assessment; that does not establish safe authority transfer, legal compliance, or resistance to poisoning. [Jev-Mem](https://arxiv.org/abs/2609.23986)

## 3. The standard’s core

**The narrow waist: two record types**

| Record | Meaning and behavior |
|---|---|
| **Artifact** | Exact bytes with a media type, format version, and content digest. It can contain a document, dataset, procedure, vector set, or model checkpoint; its digest establishes identity, not meaning or permission. |
| **Attestation** | An issuer’s typed statement about an artifact or another attestation, with scope, time, and supporting references. Provenance, rights declarations, approvals, contests, withdrawals, policies, and use receipts share this form but have distinct validation rules. |

The smallest travelling unit is a **package sufficient to interpret and assess one proposed use**. It contains an artifact, or an exact reference, plus the required context and attestations; unresolved dependencies remain explicit.

There is no universal smallest semantic claim. “Increase pressure to 5” cannot travel safely without units, equipment, conditions, and exceptions.

Hash artifact bytes separately from attestations. Hash a canonical package manifest containing their identifiers; exclude its own identifier and detached signatures. A rights correction changes its attestation and package identity, while the artifact identity stays stable.

**Six operations**

| Verb | Required effect |
|---|---|
| **Register** | Admit an artifact or received record, verify its format and identity, and assign no new authority. |
| **Derive** | Create a new artifact from recorded inputs and a named process. Summarizing, translating, embedding, consolidating, and training are derivations. |
| **Attest** | Add a typed statement: support, approval, policy, contest, correction, or withdrawal. An attestation cannot confer powers its issuer lacks. |
| **Decide** | Evaluate a named action, actor, purpose, destination, and context against current policy. Return `permit`, `deny`, or `needs_review`; only `permit` allows the action. |
| **Deliver** | Release permitted content or metadata to a person, model, tool, or node. Preserve required notices and record the decision used. |
| **Erase** | Remove specified retained data and derivatives under a disposition decision. Record completion, exceptions, and unresolved copies without retaining the erased content. |

Keep action names precise: `read`, `infer`, `derive`, `train`, `forward`, `activate`, and `execute`. Reading a procedure grants no execution right.

**Properties and their behaviors**

| Property | Behavior |
|---|---|
| **Identity and format** | Detect substitution and select a decoder. Unsupported formats cannot acquire usable meaning through a guessed interpretation. |
| **Provenance** | Record inputs, process, responsible principal, and evidence gaps. Drive attribution, dependency review, and restrictions on derivatives; distinguish “used as input” from “supports this conclusion.” |
| **Acceptance** | `pending`: proposal view; `accepted`: eligible for ordinary use; `withdrawn`: history view with reason. Acceptance belongs to an issuer and scope; it does not assert universal truth. |
| **Mandate** | A valid, scoped mandate permits citation as a governing requirement. Without it, an accepted artifact can supply evidence but cannot impose a rule. |
| **Applicability** | Conditions, exclusions, and valid time determine whether use fits the request. Missing required context blocks authoritative use; dated evidence remains available with its limits. |
| **Rights and handling** | Named issuers state legal grounds, allowed actions, duties, destinations, and retention limits. Unknown or conflicting required terms block the affected action; metadata and derived representations receive checks too. |
| **Review conditions** | Expiry, changed dependencies, contradictions, and failed tests trigger review or suspension under declared policy. A review warning and an authorization expiry have different effects. |

Keep descriptive fields outside the closed behavioral vocabulary. They may improve display or search, but cannot silently change a gate.

**Trust and decisions**

Express trust as **issuer × statement type × scope × action**, with expiry and delegation limits. Trusting a node to transport a package does not mean trusting it to approve a safety procedure.

A local policy can accept a trusted issuer’s attestations automatically within those limits. Independent approval and human-only approval belong in risk profiles; making them universal would exclude small teams and overwhelm large agent systems.

Order revisions within an issuer’s statement stream. Do not resolve disagreement between issuers by the latest timestamp. Conflicting mandates require a declared local precedence rule or review.

Every governed use records the artifact, relevant attestations, policy version, actor, and outcome. LLMDAP can supply model-call evidence, but conformance must allow other gateways with equivalent controls.

**State transitions**

| Transition | Trigger and actor | Automatic? | Reversal |
|---|---|---|---|
| New → pending | Import or derivation; system | Yes | Remove under retention policy |
| Pending → accepted | Required evidence passes; authorized approver | Only under explicit delegation | Withdraw approval |
| Accepted → use suspended | Approval expiry, authorized hold, or failed dependency condition; policy engine | Yes, when policy specifies it | Fresh authorization |
| Accepted → withdrawn | Correction, replacement, or withdrawal; authorized issuer | Only under a prior replacement rule | New approval; retain withdrawal history |
| Any retained state → erased | Valid disposition decision; responsible custodian | Execution may be automatic | No guaranteed reversal |

Record actor, trigger, reason, affected scope, and prior record for each transition. A contest alone does not withdraw approval. Untrusted proposals cannot suppress accepted knowledge; authorized emergency holds need an owner and review deadline.

A new artifact starts pending. Carry approval forward only when its stated dependencies and conditions remain valid—not merely because paragraph text matches.

**Conformance and rights**

| Level | Required capability |
|---|---|
| **L0 — Described** | Files plus a small manifest: identity, issuer, applicability, rights basis or `unknown`, and required notices. A format-only implementation makes no enforcement claim; any consuming processor must check supported conditions or refuse the action. Manual checks are permitted. |
| **L1 — Verifiable** | Content digests, stable citations, signed attestations and packages, key handling, and revision checks. Rights declarations remain bound to exact versions. |
| **L2 — Governed** | Enforced decisions, scoped authority, delegation, lifecycle rules, use receipts, and supported duties. Unsupported duties block use. |
| **L3 — Federated** | Capability negotiation, authenticated update streams, bounded freshness, withdrawal delivery, and receipt tracking. Controlled transfers require suitable receiver enforcement; simple public releases need not require an L2 receiver. |

Rights semantics start at **L0**. Enforcement depends on the operation offered, not on a badge that postpones responsibility.

Keep copyright permission, TDM reservation, data-protection basis, and local access policy separate. DSM Article 4 permits rights reservation; Article 3 provides a distinct research exception. Missing license metadata is therefore not a complete legal conclusion: a responsible party may record another applicable basis. [DSM Directive, Articles 3–4](https://eur-lex.europa.eu/legal-content/EN/TXT/?qid=1693830585803&uri=CELEX%3A32019L0790)

An audit log can support GDPR records; it does not automatically contain all Article 30 information. AI Act Article 50 transparency and Article 53 provider duties also need separate mappings. A conformance badge must not claim general legal compliance. [GDPR](https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX%3A32016R0679), [Article 50 guidance](https://digital-strategy.ec.europa.eu/en/faqs/transparency-obligations-under-article-50-ai-act), [GPAI obligations](https://digital-strategy.ec.europa.eu/en/faqs/guidelines-obligations-general-purpose-ai-providers)

## 4. Reuse

These adoption lessons are inferences from the standards’ mechanisms and documented use. A simple “won or died” list would mislead: schema.org itself uses Semantic Web encodings.

| Standards | Reuse and practical lesson |
|---|---|
| **Dublin Core; schema.org** | Reuse familiar descriptive terms and optional extensions. Dublin Core permits simpler views; schema.org connects metadata to applications that consume it. **Give a small contribution an immediate benefit.** Never discard a rights condition as if it were an optional description. [Dublin Core](https://www.dublincore.org/resources/glossary/dumb-down_principle/), [schema.org](https://schema.org/) |
| **RDF/OWL; Wikidata** | Offer mappings, contextual statements, references, and competing values. Avoid mandatory world modelling: OWL’s open-world reasoning is not a substitute for complete authorization checks. [OWL primer](https://www.w3.org/TR/owl2-primer/), [Wikidata ranking](https://www.wikidata.org/wiki/Help:Ranking/en) |
| **SPDX; robots.txt** | Reuse precise license identifiers and easy publication. SPDX can start with one line; robots.txt explicitly supplies no access authorization. **A declaration needs a consumer and an enforcement boundary.** [SPDX](https://spdx.dev/learn/handling-license-info/), [RFC 9309](https://www.rfc-editor.org/rfc/rfc9309.html) |
| **RSS; Git; IPFS** | Reuse stable feeds, local operation, and content identity. Avoid equating identity with persistence, privacy, or recall. A frozen useful core can outlast a more ambitious architecture. [RSS](https://www.rssboard.org/rss-2-0), [Git objects](https://git-scm.com/book/en/v2/Git-Internals-Git-Objects), [IPFS persistence](https://docs.ipfs.tech/concepts/persistence/) |
| **OpenAPI; MCP** | Supply validators, adapters, examples, and working clients. Keep transport replaceable; an interface description does not authorize execution. [OpenAPI tooling](https://tools.openapis.org/), [MCP tools](https://modelcontextprotocol.io/specification/2025-11-25/server/tools) |

Compose a small [PROV](https://www.w3.org/TR/prov-o/) subset for derivation and responsibility, [Web Annotation](https://www.w3.org/TR/annotation-model/) selectors for passages, and [JCS](https://www.rfc-editor.org/rfc/rfc8785) for canonical JSON.

Use a closed [ODRL](https://www.w3.org/TR/odrl-model/) profile with explicit conflict rules. ODRL defines permissions, prohibitions, and duties; a general dispensation mechanism is an extension, not an existing fourth core form.

Map TDM signals to [TDMRep](https://w3c-cg.github.io/tdm-reservation-protocol/spec/). Track [IETF AIPREF](https://datatracker.ietf.org/group/aipref/documents/), which remains draft work as of this research date. Do not create another competing web opt-out syntax.

Avoid mandatory RDF stores, consensus, public identity systems, or general workflow engines.

## 5. Durability tests

These are design tests, not forecasts.

1. **2027: a model reads the whole organization.** Retrieval becomes less important, but access checks remain necessary before context assembly. Session caches and retained memory remain governed derivatives. A larger context window changes delivery, not authority.

2. **2028: agents exchange vectors and learned memory.** Each artifact names its representation, producing model, and compatible decoder. Unknown representations cannot activate behavior. Treat vectors as potentially sensitive: embedding inversion has recovered text and personal information in experiments. [EMNLP study](https://aclanthology.org/2023.emnlp-main.765/)

3. **2029: ten thousand agents repeat one false report.** Derivation links expose the common source; repetitions do not count as independent evidence. Apply source diversity checks and review budgets. Episodic records, semantic summaries, and procedures use the same core, with different profiles.

4. **2030: the commons trains a model.** Record the dataset manifest, rights decisions, training process, and resulting checkpoint. Preserve original observations and test on independent data. Recursive synthetic training has caused collapse in experiments, but this is not proof that all synthetic data fails. [Nature study](https://www.nature.com/articles/s41586-024-07566-y)

5. **2032: a source is erased after a model learned from it.** Trace affected datasets, checkpoints, caches, and recipients. Suspend affected deployment when required; record retraining or measured unlearning without claiming universal removal. Model-native memory makes this boundary more important. [Titans](https://arxiv.org/abs/2501.00663), [MUSE evaluation](https://arxiv.org/abs/2407.06460)

## 6. Kill list

Delete or replace:

- **“Provenance and rights are intrinsic.”** Use attributed, revisable attestations.
- **A universal human/model origin gate.** Evaluate evidence and process; human authorship grants no automatic premium.
- **One strictness order for all facets.** Access, availability, evidence, and authority have different failure costs.
- **`as_of = window(t,t)`.** Separate observation time from applicability.
- **`role=none` disables other restrictions.** Search exclusion must never disable handling controls.
- **Instruction content can never be evidence.** A procedure can be inspected as evidence without being activated.
- **Mandatory claim extraction and block rules in the core.** Keep them in document profiles.
- **Guaranteed one-to-one normalizer migration.** Normalization can merge distinct inputs; require explicit migration evidence.
- **Immutable history forever; erasure equals key destruction.** Use bounded retention and verified disposition.
- **Mandatory human approval for every imported relaxation.** Permit narrow, audited delegation.
- **“Every state is an event-log fold.”** Specify observable behavior; allow simpler conforming storage.

## 7. Failure modes

| Failure | Counter-measure |
|---|---|
| **No adoption:** labeling costs exceed benefit | Start with reliable citations and controlled export. Measure total review time. Require two independent interoperable implementations before freezing v1. |
| **Poisoning and laundering** | Preserve process records, distinguish input from support, detect shared ancestry, and test external outcomes. Signatures alone are insufficient. |
| **Prompt injection through shared knowledge** | Separate inspection, activation, and execution. Pin executable versions, sandbox tools, and enforce narrow capabilities outside the model. |
| **Popularity becomes “truth”** | Measure task success, correction rate, harmful outcomes, and review cost by context. Use counts can change ranking, never authority alone. |
| **Review queues become denial of service** | Limit proposals per issuer, group duplicates, and protect accepted knowledge from unauthorized holds. |
| **Legal claims exceed technical guarantees** | Publish enforcement boundaries and unresolved copies. Track recipient notices and retention exceptions. |
| **Complexity or vendor capture** | Maintain a small normative core, public change control, permissive test tools, and export without a central registry. |

## 8. Questions for the operator

1. Will D10’s proprietary-license decision be formally replaced, with separate licenses for the specification, tests, and reference implementation?
2. Can the core permit bounded automatic approval, while regulated profiles require independent human review?
3. What first shared workflow offers enough benefit to justify contribution and maintenance?
4. What maximum offline age is acceptable before a node must stop authoritative use?
5. Who will build the second independent implementation and share control of the standard?