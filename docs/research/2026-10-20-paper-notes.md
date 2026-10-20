# Paper notes for brainstorm round 3

Written by six independent readers on 2026-10-20. The papers are idea sources, not truth. The full texts are in `research/` (git-ignored).


---

# Note: Jørgensen & Ma (2026), *Governing Agentic AI in Enterprise Workflows*

**1. Citation.** Bo Nørregaard Jørgensen, Zheng Grace Ma. "Governing Agentic AI in Enterprise Workflows: A Bounded-Autonomy Framework for Delegated Authority and Controlled Execution." *Information* (MDPI) 17, 923, 2026, doi 10.3390/info17090923. It is a peer-reviewed journal article, not a preprint. **Evidence level: conceptual.** The method is a design-science study that starts from a literature review. The authors test the framework with one constructed shopping case and ten failure scenarios. No implementation exists. §8.7 says that this traceability is only an internal consistency check.

**2. Core idea.** An agent can only *propose*. Independent semantic, process, policy and authority controls must accept a proposal before a controlled tool changes state. The process engine gives the agent a structured **task envelope**, and the agent returns a typed **output contract**. A governed knowledge graph keeps the epistemic status and the source authority of each statement, so the system never treats relevance or confidence as authority.

**3. Mechanisms worth reusing.**
- **Two independent axes (§5.3).**
  - *Epistemic status:* asserted, observed, inferred, proposed or invalidated. The paper says "at least five", so the list is open.
  - *Evidential authority of the source:* authoritative system record, attributed external evidence, analytical service output or agent output.
  - Governed metadata assigns source authority. Content, storage location and agent confidence never set it. Each assignment is versioned, auditable, revocable and valid only for a stated purpose. "Authoritative" does not mean "infallible".
- **Conflicts (§5.3, S3).** The system keeps conflicting statements with their provenance. It does not resolve them automatically. A rejected proposal stays in the provenance record and does not enter the set of accepted facts.
- **Task envelope (§6.2–6.3).** It has these fields:
  - process instance, activity, objective, initiating actor and agent role;
  - the authorised context view;
  - the permitted capability classes, with read-only and state-changing classes kept separate;
  - the output schema;
  - completion criteria and escalation conditions;
  - the versions of the ontology, policy and process that apply;
  - freshness rules or event triggers.

  If a bound version is revoked, or a newer version changes the control decision, the task stops. It continues only after the versions are bound again and revalidated.
- **Output contract (§6.2).**
  - Response types: classification, artefact, ranked alternatives, proposed decision, plan, **evidence request** or escalation request.
  - The rationale is kept apart from the fields that deterministic services read.
  - A proposed action gives its target, capability, preconditions, expected effect, evidence and self-reported uncertainty. The paper says the uncertainty is not calibrated.
  - The paper says that "Schema conformance establishes neither correctness nor authority."
- **Lifecycle (§6.5).** proposed → validated → authorised → executed → observed. Each transition writes an event and a provenance record. A correction never erases an earlier attempt (§6.6).
- **Action-bound authorisation (§6.4).** An approval is bound to one action, target, instance, actor, time interval and set of preconditions. The system checks it again when the tool runs. After a denial, the agent must not try other tools to get the same result.
- **Two-sided responsibility table (Table 6).** For each component, the table gives what it does and also what authority it must not take.
- **Ten failure and attack scenarios (Table 9, §6.7).** These can be reused as conformance tests.
- **Staging.** The paper does not define staging. It only cites [86], which holds every proposed change for human review. In its own model, the proposal state and a risk-based human task do this job.

**4. What it means for our standard.**
- *Trust and annotation (L2):* the two axes are a clear way to separate "what kind of statement this is" from "who stands behind it".
- *Provenance (L1–L2):* the source class should be recorded at ingest.
- *Lifecycle (L2):* the five action states map onto grant enactment (docs/09 §4).
- *Memory (L2):* §8.6 warns that agent output stored as memory can later be read as evidence. Consolidation must keep the status of each statement.
- *Rights (L2):* context is a query bound to purpose, role and classification. When policies conflict, the system blocks and escalates.
- *Federation (L3):* a claim from another node is "attributed external evidence". Each node assigns source authority itself, which fits principle 8.
- *Threats (L2–L3):* poisoned statements, prompt injection, tool substitution and stale approvals.

**5. Where it challenges our current model.**
- **Origin has no gate (docs/09 §2.4).** The paper says that status *together with* source authority decides what a statement can support. In our model, a model-derived block that a curator approves has the same authority as a human canon block. We should either give Origin, or a node trust policy, a gate on `rule` authority, or record why we do not.
- **Role and Standing cannot express observed versus inferred versus asserted.** The canon allows these values only if each one changes a behavior. The paper gives no rule that maps each combination to a behavior, so we cannot copy the values yet.
- **The current model has no "observed" state.** The drift view finds text drift but never checks that an enacted grant had the expected effect.
- **Envelope versus our model.** Our Agent instruction facet and `activate` govern instruction *text*. They do not govern the *delegation context*. The envelope suggests one standard object that holds the purpose, the context view, the bound event and policy versions, and the freshness rules. Part of this exists already in AT-09 (the ids of the events in force) and in LLMDAP purpose.
- **Our model is already aligned on four points:** no automatic conflict resolution, proposals from models only, append-only history, and suspension when a block is retired.

**6. Weaknesses: do not copy.**
- The framework is not implemented and has no metrics. The authors produced both the requirements and the failure scenarios, so the traceability between them proves only internal consistency.
- The stack is heavy: OWL, SHACL, BPMN, DMN, policy services, a runtime and PROV. This conflicts with a small implementation and with "conform to L0 in about an hour". Do not require BPMN or OWL.
- The paper names the two axes but gives no combination rule and no closed vocabulary.
- The uncertainty field cannot be a gate. Rule R1 already forbids this.
- Multi-hop delegation and federation are explicitly left open (§8.6–8.7). Automation bias in human review is also unsolved.

**7. Open questions.**
- Is evidential authority a facet on the content, or a node-local trust policy on sources?
- Which status × authority pairs permit which behaviors: citing as a rule, citing as evidence, or enacting a grant?
- Is "evidence request" a valid answer from a node that only answers and executes no actions?
- How do freshness triggers map to Time-basis windows?
- How does a source-authority assignment travel between nodes, for example as a Verifiable Credential?
---

# Note: The Living Data Genome (Eren, 2026)

## 1. Citation
Haluk Eren, *The Living Data Genome: Ledger-Governed Evidence Lifecycles for Accountable AI Under Limited Observability*. *Systems* (MDPI) 14, 1221, 2026. doi:10.3390/systems14101221. Journal article with one author. The author used Claude for help with the analysis scripts.

**Evidence level: conceptual and synthetic.** Proposition P1 and P3–P5 have proofs in the supplement, and P2′ is a conditional result. The supplement was not available to me. All data comes from one synthetic generator. The paper itself says that the "healthcare" case is the same generator with different parameters, not an independent domain (§4). Federation uses four simulated nodes. Attestations use keyed hashes as a stand-in for public-key signatures (§3.7).

## 2. Core idea
Evidence has an internal, revisable state ("DNA") and a released artifact ("RNA"). Only the artifact crosses a release gate. Revocation after release ("apoptosis") is a signed event, not a deletion. A corrected successor ("regeneration") goes through the same gate and links to its predecessor. A "protocol reliability" score measures whether a package went through the declared lifecycle. It does not measure whether the claim is true.

## 3. Mechanisms worth reusing
- **Package with four parts (Eq. 4):** claim, artifact, explanation and lineage. Each part is checked separately.
- **Closed event alphabet (Eq. 3):** `accept`, `certify`, `contest`, `revoke`, `regenerate`. The lineage is an ordered list of signed events (§2.6). A `regenerate` event holds a reference to its predecessor.
- **Release gate (Eq. 2, 10, 15):** release requires all of these tests:
  - the internal state is feasible;
  - the artifact is admissible;
  - the explanation discloses no more than policy permits;
  - stability is at least τ.

  "No release" is a recorded governed outcome, not an error.
- **One-way witness (Eq. 8):** each release must have a witness that the regime was satisfied. A witness alone does not permit release.
- **Lineage predicate (§2.6, §3.6):**
  - timestamps increase and are signed;
  - mandatory events are present;
  - no accept/revoke pair contradicts another;
  - each regeneration has an ancestry link;
  - a `revoke` with no successor and no explicit terminal-disposition event is a violation.

  A review that changes nothing writes no event. The test of a revocation predicate and the certification of the revocation are separate steps.
- **Reasons recorded at release (§3.4):** six fields go into the digest: the binding constraint, its slack, the minimum coverage, the stability, the context label and the regime version. Median size is about 170–190 bytes. The contesting party gets enough to challenge the decision but does not get the reconstruction.
- **Design contract (Table 2):** each constant names the role that may declare it. It also records how its value was set: institutional, experimental, data-derived, or declared but not evaluated.
- **Routing (Eq. 14):** four routes: proceed, context review, quarantine/repair, inadmissible. The system never changes a declared context label itself. A human makes that change, and the lineage records it.
- **Federation (§3.7):** nodes exchange only binary admissibility decisions, not evidence. Commit needs a quorum of three of four attestations. A Merkle inclusion proof is 576 bytes at 262k events.
- **Validity test for any score (§3.10):** a valid score must go down under the failure modes it targets. It must stay unchanged under transformations that change no institutional fact.

## 4. What it means for our standard
- **Unit of knowledge:** it supports the "claim" in the narrow waist, if the claim travels with a pointer to its source, the reasons and the lineage (L1/L3).
- **Provenance:** reasons recorded at release map onto AT-09 (the event ids in force), plus the policy version and the profile version (L2).
- **Lifecycle:** genesis → `pending`; mutation and repair → work before approval; expression → approval or package; apoptosis → `retired`; regeneration → `supersedes`. Our model already has most of this.
- **Trust:** the validity test (§3.10) should apply to every trust score between nodes (L3).
- **Federation and threats:** a revocation must travel to the nodes that received the package (L3). Silent deletion, leaks through explanations and tampering with revocations are named threats.

## 5. Where it challenges our current model
1. **Retire vs revoke.** `retired` is local to one node. We have no revocation notice that follows a package to its receivers. **Proposal:** a signed `revoke` event in the package protocol (L3).
2. **Terminal disposition.** Today a block can be retired "with a link to the successor if one exists". Under the paper's rule, a retirement must name a successor or an explicit terminal reason, or it fails conformance.
3. **Contest.** We have no contest. Under canon 1, a `contest` value must change a behavior, for example a warning in answers and an entry in the curator queue. I recommend an event type, not a new Standing value.
4. **Release as an event.** Signed packages do not record a reasons digest per release. Add one at L1.
5. **Declared constants.** Profile constants (the N files for `none`, the 4,000-character block split, the 30 % blind slice) must name the role that declares them (L2).

## 6. Weaknesses: what we must NOT copy
- **How much mathematics is necessary:** the reusable core is indicator gates, a closed alphabet, a boolean lineage predicate and a weakest-link rule (a minimum is sufficient). The rest is not necessary for us:
  - the four-gene ℝ⁴ coordinate;
  - JSD and CKA;
  - the 12 stages in four layers (the main text does not list them);
  - the projection geometry of P1. The implementation breaks P1 for about 1 candidate in 6 (P2′).
  - the "density matrix" reading in §2.8. Its flag goes into no reported quantity.
  - the Shapley analysis (P5, C2).
- **The Rel score is weak:**
  - triadic alignment and transition stability mostly report the declared noise constants, not the data, as the author admits (§2).
  - governance coherence is a placeholder, or exactly 1 − revoke rate.
  - the weights are a default.
  - the score is an order of magnitude less sensitive to instability than to loss of releasability.
  - a floor of 10⁻⁶ softens the weakest-link property.

  0.789 has no meaning outside the protocol.
- **The biological metaphors add no mechanism.**
- **Table 1 overclaims.** It says PROV cannot withdraw validity. PROV-DM has Invalidation and `wasRevisionOf`. The paper does not cite VC status lists or nanopublication retraction [INFERENCE: both give withdrawal without erasure].
- **Adversaries are not tested.** There is no adaptive adversary, key compromise, network partition or liveness test.

## 7. Open questions
- Who may revoke in a network: only the issuer, or a receiver for its own node?
- Does `contest` change a behavior enough to be core?
- How do we propagate a revocation to answers and grants already derived from a package (D23, AT-09)?
- Can nodes share only admissibility decisions for text claims, and does that resist poisoning?
- Is the lineage predicate a pass/fail conformance test or a score? I recommend pass/fail.
---

I wrote both notes from the full text of each paper. I did not inspect the Metis code on GitHub, and I could not see the figures because the text extraction drops them.

---

# Note 1 — Tacit Fragments

## 1. Citation
- **Paper:** "Tacit Fragments: Operationalising Tacit Knowledge as a Governed Memory Layer for Agentic AI"
- **Authors:** A. Shahid, G. Suttie, P. Black (Brightbeam AI) and A. Garzón-Vico (UCD).
- **Venue:** Preprints.org, 13 Aug 2026, doi:10.20944/preprints202608.0927.v1. It is **not peer-reviewed**.
- **Evidence level:** conceptual. The paper reports no evaluation, and it says that the endogenous pathway is untested (§5.5). A reference implementation (Metis) is published. The paper uses CHAP, which is the authors' own protocol.

## 2. Core idea
A "tacit fragment" is a partial, typed record of situated practice. It is not tacit knowledge itself. Each fragment always carries its provenance, its conditions of applicability, its confidence, its authority and its validation state. The authors call this governed store a "fourth memory stratum". Its governance contract, not its data, makes it different from procedural, semantic and episodic memory.

## 3. Mechanisms worth reusing
- **Tuple (§3.2, Eq. 1, p. 8):** `f = ⟨content, provenance, conditions, confidence, authority, validation-state⟩`. The content can be non-textual: an exemplar, an image or an audio segment.
- **Minimum record (Table 2, p. 16):**
  - conditions of applicability, which include **exclusion conditions**;
  - lineage: the prompt, the response, the reviewers and each state change;
  - attribution and **consent and withdrawal**;
  - validity: review date, **expiry triggers**, supersession links;
  - revocation status: active, superseded, withdrawn, rejected or under re-elicitation, with the reasons kept.
- **Authority ladder (§4.5, Fig. 4b):**
  - **Evidence** has no operational influence.
  - **Advisory** is conditional decision support. A fragment gets to Advisory only through the Tier-2 gate.
  - **Controlled** means the fragment is in procedures. A fragment gets to Controlled only through change control.
  - Each move is recorded, justified and reversible.
- **Validation (§4.4):**
  - **Tier 1, fidelity:** the source person confirms that the record matches what they meant.
  - **Tier 2:** reviewers check relevance and normative alignment *separately* (P9). The review gives one outcome: promote, hold, reject or re-elicit.
  - **Rejection never deletes** the fragment. The fragment stays as evidence of what the organization denied.
- **Separation of duties (§4.1):** capture, validation and enforcement sit in different units. No unit can both create a fragment and give it authority.
- **Two origins (§2.3):**
  - **Exogenous:** from human practice.
  - **Endogenous:** `Δ = enacted ⊖ specified`, over episodes that match on task and conditions. A candidate is made only when a deviation recurs and stays stable.
  - Endogenous fragments stay in the Evidence layer. They are never promoted automatically, and they must meet a higher evidence bar (§5.2).
- **Retrieval (§4.6, P5):** the system checks conditions **before** any similarity ranking. If a request is outside the conditions, the system sends it to a human. It does not return a precedent.
- **Detection and elicitation (§4.2):** cheap continuous detection triggers rare, deep interviews.

## 4. What it means for our standard
- **Unit of knowledge:** a fragment is a claim with its annotations. It is not a block. This supports the "claim" in the narrow waist. **L0/L2.**
- **Provenance and origin:** origin decides how much evidence an item needs. **L2.**
- **Trust and annotation:** the source person confirms fidelity, and a different person approves. **L2.**
- **Lifecycle:** reviews can be triggered by events, not only by time. **L2.**
- **Memory and consolidation:** Δ is a precise trigger for consolidation (vision Q3). The paper defines a memory type by its governance contract, not by where it is stored.
- **Rights and policy:** consent, withdrawal, and a purpose limit (decision support, not compliance monitoring). These fit the ODRL purpose rules. **L2.**
- **Federation:** authority is local. The receiving node should assign its own layer. **L3.**
- **Threats:**
  - contaminated agent traces;
  - expert overconfidence outside their usual conditions (§5.4);
  - surveillance of workers.

## 5. Where it challenges our current model
- **Scope** has no exclusion list and no typed context dimensions (equipment, mode, risk class). Our model has **no escalation behavior** when a request is outside scope. Today it only asks for context, and only for a bounded `rule`.
- **Origin** "has no gate of its own" (docs/09 §2.4). The paper gives origin a gate: a model-derived item needs a higher evidence bar. Human-only `curate` blocks automatic promotion, but nothing marks the difference for the curator.
- **Standing `approved`** is one event. The paper separates the source's fidelity confirmation from approval, and relevance from normative review. We have no "author ≠ approver" rule.
- **Time basis** `review_by` uses only a date. The paper also uses event triggers, for example a change of equipment.
- **Evidence/Advisory/Controlled** maps roughly to `evidence+pending`, `evidence+approved` and `rule+approved`. This supports our Role × Standing split. One ordered ladder would break R2 if we kept Role as well.

## 6. Weaknesses — do NOT copy
- The **record has three overlapping status fields**: validation-state, authority layer and revocation status. The paper never gives one state machine. Demotion, the duration of "hold", and the link between the review outcomes and the validation-state values are unclear.
- **Confidence** has no scale and no computation. As a facet it changes no behavior, so it fails our canon.
- The **K1–K17 taxonomy** and the Spender mapping only choose a capture method. They are human genres, not runtime behavior. The name also collides with our old K1–K8.
- **Capture Cell, Mission Group and Orchestrator** are organizational roles. They are not data structures.
- **"Whispers"** carry a high surveillance risk. The many regulatory citations are decoration.
- The **Δ operator** is described only in prose.

## 7. Open questions
- Is an exclusion condition part of Scope, or a separate gate?
- Should a fragment with no document source become a book, or a new unit?
- How does a worker's withdrawal reach copies that other nodes already hold?
- Which origin values change the evidence bar?

---

# Note 2 — Decision Integrity and Knowledge Provenance

## 1. Citation
- **Paper:** "Beyond Workflow Design: Decision Integrity in Agentic AI Systems"
- **Author:** anonymized for double-blind review. Two key references are the author's own withheld papers.
- **Venue and year:** SSRN preprint (as the task states; the text shows no venue), 2026.
- **Evidence level:** conceptual. The paper uses no data, and it says that it used AI for editing. It discloses a competing interest but withholds the details.

## 2. Core idea
Agentic systems fail mainly because the expertise in their workflows was transferred badly, not because of the model. A "fidelity error" is a correct execution of a workflow that does not represent what experts actually do. "Knowledge provenance" should record whose expertise a workflow encodes, who validated it, and how current it is.

## 3. Mechanisms worth reusing
- **Decision integrity (§7)** has four properties:
  - traceable;
  - reproducible;
  - contextually appropriate;
  - faithful to expert intent, which the paper calls the core.
- **Workflow fidelity** is different from **workflow correctness**: one asks if the specification was right, the other asks if the workflow runs as specified (§8).
- **Knowledge-provenance record (§10, §16):**
  - the designer and their qualification;
  - the experts consulted and the exceptions they named;
  - what was validated, by whom, and against which ground truth;
  - how current it was at transfer;
  - assumptions and **conditions of inapplicability**.
  - The paper proposes this as a W3C PROV extension (expert, qualification, validation event, ground truth, condition of inapplicability). It gives no schema.
- **Loss pathway (§12, Fig. 2):** SME reasoning → workflow → AI specification → prompt → tool selection → inter-agent messages → execution → decision.
  - The loss is cumulative.
  - The largest losses occur at the transitions that have the least instrumentation.
  - The correction is re-elicitation and re-validation, not retraining (Fig. 1).
- **Measures (§13):**
  - **provenance completeness**: the share of decisions that trace to a source that is identified, qualified and dated;
  - exception-capture rate;
  - divergence from an expert panel.
- **Governance artefacts (§14):** a register of what stays with human judgement, and why.

## 4. What it means for our standard
- **Provenance and origin (L2):** our AT-09 access record (the event ids in force) is *decision* provenance. Knowledge provenance needs more:
  - the qualification of the approver;
  - the validation method or ground truth;
  - **derivation links** from operational artefacts back to the rule blocks they encode.
- **Lifecycle:** content-addressed block refs already give "currency at transfer".
- **Federation (L3):** signatures prove origin, not fidelity. Qualification claims could travel as Verifiable Credentials. The receiver decides if it trusts them.
- **Threats:**
  - The fidelity error is invisible to integrity checks.
  - Specifications that an LLM elicits are fluent, so people challenge them less (§15). This applies to our labelling-model proposals.
  - The curator can become a "moral crumple zone": the human who takes the blame (§14).

## 5. Where it challenges our current model
- **Agent-instruction blocks** are where expertise becomes prompts, which is the step with the least instrumentation. `activate` controls authorization only.
  - The same mechanism as grants applies: a **structured source column** to the `rule` blocks.
  - When a source block retires, the system automatically suspends the instruction.
  - The drift view should extend to instructions.
- **`curate`** is a right, not a competence. The paper ties validity to the approver's *qualification*. That fits only if a qualification changes a behavior, for example federated trust.
- **Scope** should be able to state where a rule does *not* apply (a "condition of inapplicability"). The paper puts this in provenance; that is a category error.
- **Provenance completeness** could be a measurable L2 conformance test.

## 6. Weaknesses — do NOT copy
- The central claim (experts matter more than the model) is asserted. The paper does not show it.
- The paper treats experts as right and as one voice. It does not discuss expert disagreement or expert error. Note 1 (§5.4) argues the opposite.
- The property lists are inconsistent: Table 1 says "accountable" where §7 says "contextually appropriate".
- Some citations do not fit the claims they support:
  - Alavi 2001 and Grant 1996 are cited as "contemporary" work;
  - Amershi 2019 is cited for LLM expert studies;
  - Herschel 2017 is cited for "source-verified architectures".
- The paper does not discuss reproducibility with non-deterministic LLMs.
- The **maturity model** measures organizational capability. Do not use it as conformance levels. Do not use the term "expert hallucination".

## 7. Open questions
- What is the smallest PROV-O profile that gives provenance completeness?
- How does an air-gapped node express qualifications without a credential issuer?
- Who certifies fidelity across nodes?
- Can we detect a fidelity error at runtime, or only with a panel of experts?
---

# Note 1: Nanopublications (Kuhn et al., 2016)

**1. Citation.** Kuhn, Chichester, Krauthammer, Queralt-Rosinach, Verborgh, Giannakopoulos, Ngonga Ngomo, Viglianti and Dumontier. *Decentralized provenance-aware publishing with nanopublications.* PeerJ Computer Science 2:e78, 2016. This is an extended journal version of an ISWC 2015 paper.
- **Evidence level:** empirical system evaluation on a live network (15 instances on 10 sites) with real datasets (more than 5 M nanopublications, about 200 M triples).
- **Limits of the evidence:**
  - The replication test used only 3 servers.
  - The load test used one site.
  - The authors say that the comparison with SPARQL is "not a fair one".
  - There is no adversarial test.

**2. Core idea.** A nanopublication is a small RDF container: an atomic assertion, its provenance and metadata about the publication. A hash in the identifier (the trusty URI) makes each container immutable and verifiable. An unstructured peer-to-peer network of simple servers replicates the containers, and the only lookup is by identifier; query services are a separate, higher layer.

**3. Mechanisms worth reusing**
- **Four named graphs (p.3, p.14):** head → `hasAssertion`, `hasProvenance` (about the assertion), `hasPublicationInfo` (about the whole container: creator, date). This is a clean split between claim, origin and envelope.
- **Trusty URI (p.5–6, p.9):**
  - The last 45 characters are a hash of the normalized content (statements sorted).
  - The client computes the hash before it publishes.
  - A link to a trusty URI lets the reader verify the target. This applies again to each trusty link in the target, so you can verify the whole reference tree.
- **Server state (p.10):** a key-value store keyed by the artifact code, plus a **journal**. The journal has a journal id and an ordered list of identifiers in pages of 1,000. The server also keeps:
  - gzipped packages of the pages;
  - a URI pattern and a hash pattern (which subset it replicates);
  - a peer list, with the last-seen journal id and count for each peer.
- **Pull sync (p.11–12, 9 steps):**
  1. Fetch the peer's info and merge its peer list.
  2. Skip the peer if the two patterns do not overlap.
  3. Resume from the last count. If the journal id changed, start again from 0.
  4. Fetch the new journal pages. Use a bulk package if there are more than 5 new items.
  5. Verify each hash. Ignore invalid items.
  6. Append the valid items to the local journal.
- **Indexes (p.12–14):** "reference instead of containment". An index is itself a nanopublication, with at most 1,000 references. It has three relations: *element*, *sub-index* and *appends-to*. A dataset or a citation is one index URI.
- **Layering (p.7–8):** a minimal archive layer, then core services (backlinks, by author), then advanced services (SPARQL). Immutability makes caching trivial. The upper layers can be private.
- **Two kinds of trust (p.3):** "fit for purpose" against "is this the exact version". Only the second is technical.
- **Lifecycle (p.9):** there is no deletion. A new nanopublication marks an old one as retracted or superseded.

**4. What it means for our standard**
- **Unit of knowledge (L1, L3):** this is direct input for vision §8 Q1. A travelling unit is a *claim envelope*, not a structural block.
- **Provenance and origin (L2, L3):** provenance is a required part of the unit, not an option.
- **Trust and annotation (L2):** an annotation can be a separate signed object that refers to the target by hash. This fits principle 8.
- **Lifecycle (L1):** append-only plus supersession matches "reversal is a new event".
- **Federation (L3):** journal-offset pull with subset filters is simple. It is resumable, and it works for air-gapped nodes, because the administrator can load files from disk (p.11).
- **Threats:** the paper gives integrity only.

**5. Where it challenges our current model**
- **Block reference:** `book@content_id/profile/path#ordinal` is a local location. A federated claim needs a self-verifying global id. `block_hash` is close, but it hashes only the text.
- **What the hash covers.** A trusty URI covers provenance and pubinfo. Vision §6 L1 (rights inside the signed version) agrees with that. But **Standing, Role and the other local facets must stay outside** the hashed envelope. Otherwise a local curator decision creates a new global identity.
- **Origin** is now "recorded, not labelled, no gate" (§2.4). At L3, a required provenance part makes Origin a mandatory envelope field.
- **Package against reference:** the identity of a set is an index of references. Transport can still be a bundle (journal packages). Our signed packages should separate these two roles.
- **Retirement:** "block removed → retired" cannot delete remote copies. In a network, retirement can only be an event that travels.

**6. Weaknesses: what we must NOT copy**
- **No signatures in this paper.** A trusty URI proves integrity, not authorship. Anybody can write any ORCID in `pav:createdBy`.
- **"Cannot unpublish"** conflicts with GDPR erasure and with a leak of confidential data. Do not use it on organization nodes.
- **RDF canonicalization** (sorting, Skolemization) ties identity to RDF. Do not make RDF mandatory.
- **Atomization is unsolved:** "best practices … still have to emerge" (p.6). Do not force atomic claims at L0–L2.
- **Limits:** the limits (1,000 references, 1,200 triples, 1 MB) are arbitrary, and the authors say so.
- **Deferred work:** the vocabulary for versions, retraction and review is future work (p.24). The paper does not define it.
- **Public base layer:** the lowest layer is public by design (p.8). It has no rights, no license and no access control.
- **No spam defense:** proof-of-work is only an idea (p.24).

**7. Open questions**
- Who may retract a nanopublication: only the author, or anybody? The paper does not say.
- What do we hash: the bytes, the claim, or the claim plus the rights declaration?
- How do the replication filters become rights filters and trust filters, not URI-prefix or hash filters?
- How does an immutable archive work together with crypto-shredding?

---

# Note 2: Bluesky and the AT Protocol (Kleppmann et al., 2024)

**1. Citation.** Kleppmann, Frazee, Gold, Graber, Holmgren, Ivy, Johnson, Newbold and Volpert. *Bluesky and the AT Protocol: Usable Decentralized Social Media.* ACM CoNEXT-2024 Workshop DIN '24. This note uses the extended arXiv version, 2402.03239v2.
- **Evidence level:** conceptual architecture plus a deployment report (more than 10 M users).
- **Limits of the evidence:**
  - There is no formal or empirical evaluation. The only number is a cost for a full replica ($153 per month, from a blog post).
  - Eight of the nine authors work for Bluesky Social PBC.

**2. Core idea.** Each user publishes into one signed repository, which a replaceable host (PDS) keeps. Identity comes from a DID, so the user can move to a different host. Neutral services (Relay, AppView) aggregate and index the public data, and separate "opinionated" services (labelers, feed generators) make judgements. Users and operators select those services. The design goal is "credible exit": every role can have competing operators.

**3. Mechanisms worth reusing**
- **Repository (§3.1):**
  - Records are DAG-CBOR objects, typed by a namespaced **lexicon**.
  - Media and cross-repo references go by CID (hash).
  - **A user writes only their own repository.** A follow, like or reply is a record in the actor's repository, so the backlinks need an index.
  - After each change, the user signs the root of a Merkle Search Tree. This gives a proof of inclusion, and after an update or deletion, a **proof that the record is absent**.
- **PDS (§3.2):**
  - It has an HTTP API and a WebSocket change stream.
  - To migrate, you copy the repository and update the DID document.
  - If the PDS dies, you restore from a backup.
- **Relay (§3.3.1):**
  - It verifies the signatures and proofs, keeps a replica and emits a "firehose" that includes the proofs.
  - It crawls again after an interruption.
  - It does not interpret records, so a new lexicon needs no change in the Relay.
- **AppView (§3.3.2):** an index for one lexicon (threads, counts, timelines). It is also the **enforcement point**: it drops interactions that a block forbids. For this reason, blocks must be public.
- **Labelers (§3.4, §2.1):** a stream of judgements ("this post is spam"). AppViews or PDSes use the stream to filter content. Feed generators return selected IDs. Mute lists and block lists are subscribable.
- **Who selects trust:**
  - Users and PDS/AppView operators choose labelers and feeds.
  - A client can use a different index, or combine more than one.
  - Some filters apply "regardless of user preferences" (§2.1).
  - The paper describes **no** trust computation. Trust is a subscription list.
- **Identity (§3.5):**
  - A DNS handle maps to a DID. The DID document holds the handle, the PDS URL and the signing key. The handle must link in both directions, and the AppView checks it at intervals.
  - `did:plc` is the hash of the genesis document. The key in the previous version must sign each update. The directory returns the full chain, so a malicious directory can only omit versions or choose a fork. A transparency log is planned.

**4. What it means for our standard**
- **Provenance and origin (L1):** the signed per-author repository gives "who published this, in which state". It says nothing about derivation.
- **Trust and annotation (L2, L3):**
  - Labelers are principle 8 in practice.
  - The rule "write only your own repository" means that an annotation about a remote claim lives with the annotator, not with the target.
  - The neutral transport is separate from the opinionated judgement.
- **Lifecycle (L1):** deletion is first-class, and it has a proof of absence. This is input for vision Q6.
- **Federation (L3):**
  - The node, the router and the policy point are three separable roles.
  - A DID with a key-rotation chain fits identities for nodes and authors, and the rotation of our Ed25519 keys.
- **Threats:**
  - censorship by omission;
  - a fork chosen by the directory;
  - DNS poisoning;
  - custodial keys.

**5. Where it challenges our current model**
- **Imported facets.** Our Standing and Role assume one curator authority. At L3, the Standing of a remote node is better modelled as a **label from a named labeler**. Local policy then maps the trusted labelers to local proposals. Under R1 and R3, an imported looser value stays a proposal until a local human confirms it.
- **Two classes of facet.** "Filters always applied" against "subscribable labels" maps to our gate facets (Sensitivity, Egress, Agent instruction), which are local and not negotiable, against ranking and descriptive facets, which can compose.
- **Where enforcement happens.** ATProto enforces at the reader index and trusts the AppView to be honest. Our L3 precondition ("never forward without rights") enforces at the source. Keep ours.
- **Distribution by default.** The firehose sends everything to everybody. This is the opposite of `restricted`. Route by grant, not by broadcast.
- **Origin and custodial keys.** A key that the PDS holds proves that the host signed, not the person. This weakens any "human wrote it" claim.

**6. Weaknesses: what we must NOT copy**
- **Public only.** Private state is minimal, and DMs are centralized. The paper does not cover confidential knowledge.
- **Concentrated in practice:** one PLC directory, one Relay, one main AppView. "Credible exit" is a claim, not a test result.
- **Lexicons** are open namespaces with no semantic mapping. We would get schema sprawl. Use SKOS mapping instead.
- **Label format and conflicts.** The paper does not define the label format, the label semantics or how conflicting labels resolve (it refers to Proposal 0002). These are unclear from this text.
- **The "neutral" Relay** also filters spam and illegal content. This is a hidden policy.
- **Offline use.** DNS handles, `did:web` and `plc.directory` need the network. An air-gapped node cannot resolve them. The self-certifying `did:plc` chain could transfer if the full chain travels with the package.

**7. Open questions**
- How does a node sign as an organization, while each human or agent author is still identified separately?
- How far does a deletion propagate through replicas, and how can we prove it?
- Can enforcement work without policies that everybody can see? Blocks became public for this reason.
- How do we express a labeler's scope and authority as an ODRL or Zanzibar policy, and not as a client checkbox?

---

**Summary: what transfers and what does not**

| Transfers | Does not transfer |
|---|---|
| Claim, provenance and envelope split; hash-addressed references; index by reference; journal pull sync with subset filters | No unpublish; RDF-only canonical hashing; public-only base layer; forced atomization |
| Signed per-author repository with a proof of absence; DID key-rotation chain; neutral transport separate from labelers; trust that the consumer selects | Firehose by default; custodial signing as proof of origin; enforcement at the reader; DNS or central-directory identity on air-gapped nodes |

The output is only this message. I wrote no files, because the brief asked for two notes and gave no path for them.
---

Below are the three notes. I read the full text of each paper and §1–§8 of docs/09. Where a claim comes from my own knowledge of ODRL 2.2 or Zanzibar and not from the paper, I mark it **[external]**. Where a point is my own conclusion, I mark it **[INFERENCE]**.

---

# Note 1 — Deontic Policies for Runtime Governance of Agentic AI Systems

**1. Citation.** A. Joshi, T. Finin, K. Joshi, L. Kagal. *Deontic Policies for Runtime Governance of Agentic AI Systems.* IEEE ICWS 2026, pp. 1255–1262, DOI 10.1109/ICWS72778.2026.00159. **Evidence level: conceptual plus a prototype.** There are worked policy examples. The only measurement is latency: below 10 ms end to end on one host. The paper does not measure correctness or coverage. Credential checks are *simulated*. The authors used generative AI to help write the prototype code (Acknowledgments).

**2. Core idea.** Allow/deny engines (OPA, Cedar, XACML) cannot express the full structure of governance. Rei, a deontic language written in OWL, has four first-class modalities: permission, prohibition, obligation and dispensation. It also has meta-policies that decide which rule wins in a conflict. AgenticRei applies these rules at each tool call and each A2A message, outside the LLM. Every internal failure gives default-deny.

**3. Mechanisms worth reusing.**
- **Extract–evaluate–apply** (§III). The tool call is already validated against its schema. The system turns it into a ⟨subject, action, resource⟩ triple. The verdict is `PERMIT | PROHIBIT | DEFAULT-DENY`, plus any obligations attached to the permit. Exceptions, timeouts and missing rules all give `DEFAULT-DENY`.
- **Obligation through `deontic:provision`** (P2). The duty exists *because* the action was permitted. An ObligationManager gives it a deadline and calls an escalation callback if nobody discharges it.
- **Dispensation** (P5). A dispensation releases an actor from one obligation. It is different from overriding a prohibition.
- **Named priority** (P3, P5). `metapolicy:RulePriority(greater, lesser)` is a policy object in its own right, and a higher authority can govern it. It replaces the order of evaluation or an integer priority.
- **The policy names the trusted issuer** (P3). An override needs a credential from the issuer that the policy names. A credential that only carries the attribute is not sufficient.
- **The audit record holds a hash of the policy KB** (§III). It also holds the matched rule, the issuers and the attribute *names*, not their values.
- **Discharge evidence as a Verifiable Credential** (§VII). A receipt VC closes the obligation.

**4. What it means for our standard.**
- *Rights and policy* (L2): the policy envelope needs explicit prohibitions and obligations, not only grants.
- *Trust and annotation* (L3): a trust policy should name issuers, not attributes. This fits principle 8, "local trust".
- *Lifecycle* (L2): an obligation is a new stateful object, so it needs a state machine (canon 2).
- *Threats* (L2): enforcement at the action boundary does not depend on resistance to injection. This agrees with LLMDAP.
- Our AT-09 record of "event ids in force" already does the job of their KB hash.

**5. Where it challenges our model.**
- **docs/09 §4.6, "prohibitions accepted as a gap".** "No grant" is enough inside one node. It fails when a broader grant exists, for example *read* but *no train*. It also fails when a received package must carry the sender's prohibition. Sensitivity=`restricted` and Egress=`local_only` already work as fixed prohibitions. The standard should make the prohibition a general rule type, so that it is not limited to two facets.
- **No obligations.** Candidates: attribution on *derive*, notification on *export*, delete-by on received objects. `review_by` is already a weak obligation on the curator.
- **Book-level policy only.** The paper's class-level rules suggest that one policy can apply to a class of books or claims.

**6. Weaknesses — do NOT copy.**
- **General override.** Here a permission can override a prohibition. This breaks our monotone rule: "a block can never weaken book restrictions; incomparable restrictions intersect". Keep forbid-overrides-permit. Allow only one exception type: a scoped, expiring, audited **dispensation** from a named issuer, set by the administrator.
- **Open ontology reasoning on gates.** If a subclass link is wrong or removed, the gate loosens silently. This conflicts with principle 6 (closed gates) and with R3. It is not clear whether the KB hash covers the ontology fragments.
- **Obligations are sent to the agent as text in the tool result.** That puts compliance back into the LLM context, which is the problem the paper set out to solve.
- **The examples have gaps.** P5 says the CTR obligation applies only above a threshold, but no threshold is encoded. P5 also uses `RulePriority` for dispensation-over-obligation, which mixes the two concepts. The claims that some policies are "inexpressible" in Cedar or ODRL are too strong. **[external]** ODRL 2.2 has `odrl:conflict` (perm/prohibit/invalid), duties, `consequence` and `remedy`.
- **A single triple loses purpose and data flow.** "Read, then send elsewhere" is not modelled.

**7. Open questions.**
- What are the obligation states: issued → pending → discharged | dispensed | violated → escalated? Who owns each transition?
- Can a sub-authority only *add* restrictions (attenuation)? The paper leaves this open (§VII). Our delegation limit partly answers it.
- What counts as discharge evidence across nodes that have no common root of trust?

---

# Note 2 — Towards Usage Policy Enforcement in Dataspaces

**1. Citation.** A. Krimbacher (nexyo GmbH), T. Dam, S. Neumaier (FH St. Pölten). *Towards Usage Policy Enforcement in Dataspaces.* 2023, a 5-page position paper. The text does not name the venue; the file name suggests an IDSA-related event. **Evidence level: conceptual.** There is no implementation of enforcement and no evaluation. The pattern catalogue is on GitHub (`fhstp/dataspaces-policies`). That catalogue is not in our corpus, so I did not check it.

**2. Core idea.** Dataspace connectors such as Eclipse EDC have no agreed usage-policy patterns that they can enforce, and no way to manage policies. The authors collect patterns from a survey (Akaichi & Kirrane 2022) and write them in ODRL, with a dataspace profile for missing terms. Each pattern names the party that administers it, the party that supplies the information and the party that decides.

**3. Mechanisms worth reusing.**
- **Preventive vs detective enforcement** (§2).
  - *Preventive* actions: allow or deny; revoke on violation; delay a usage until its obligations are fulfilled; update attributes; run actions such as notifying the owner.
  - *Detective* actions apply when prevention is not possible: audit and logs.
- **Roles per pattern** (§3). For each pattern, the PAP, PIP and PDP are assigned to the provider, the consumer or a trusted third party.
- **Two directions of duty** (§3).
  - *Provider-administered*: read, with duties to delete by a date and to anonymize.
  - *Consumer-administered*: the provider must update every 30 s and conform to a SHACL shape.
- **ODRL profile extension** (`w3id.org/dataspaces-policies`) for terms that ODRL does not define.

**4. What it means for our standard.**
- *Rights and policy* (L0 declare, L2 enforce): this supports ODRL as the rights format in vision §6.
- *Federation* (L3): the paper is honest that after transfer the sender can only *detect*, not *prevent*. So enforcement after transfer has two parts **[INFERENCE]**:
  1. the receiving node must be a conformant L2 node and act as the PEP for the received copy;
  2. duties that the sender cannot check (delete-by, anonymize) become detective items: attestations, audit export, and loss of trust when they fail.
- *Threats* (L3): a delete duty that nobody can verify is only a promise. Trust scoring must reflect this.

**5. Where it challenges our model.**
- **Sensitivity=`restricted` is preventive only** ("never in a package"). We have no middle state for "may export *with* duties". The policy envelope needs ODRL duties attached to the export permission. The receiver should bind them as its book policy and must not loosen them (R3).
- **Consumer-administered duties.** A receiving node can also set conditions on the sender, such as freshness or schema conformance. This is relevant when nodes act as routers: subscriptions have contracts in both directions.
- **Book-level policy vs per-asset contract.** In a dataspace, the unit of policy is the *agreement* for each exchange, not a standing attribute of a catalogue entry.

**6. Weaknesses — do NOT copy.**
- **Nothing is enforced.** The Nexyo DataHub stores permissions, obligations and prohibitions *as free text* (§4). The model was right to reject this (docs/09 §4.2).
- **The listings have errors.** The provider example has the IRI `#consumer-administered`. **[external]** In ODRL 2.2, a duty inside a permission is `odrl:duty`, and `odrl:obligation` is for the policy level. The listings also have no policy type (Set/Offer/Agreement), no `uid` and no `target`. The meaning of the delete-by constraint (precondition or deadline?) is unclear.
- **Profile extensions lead to fragmented vocabularies.** If gate terms come from extensions, gates become open. That conflicts with principle 6.
- The paper has no conflict semantics, no state machine for duties and no model of evidence.

**7. Open questions.**
- Which party is the PDP for a duty after transfer, and which evidence closes it (for example a signed deletion receipt)?
- What does a node do with an ODRL term it does not know? Under R1 it must deny. Is that a conformance rule?
- Is the travelling unit a policy (attached to an object) or an agreement (attached to one exchange)?

---

# Note 3 — From Permission to Institutional Authority

**1. Citation.** R. Mikkilineni, W. P. Kelly. *From Permission to Institutional Authority: Governance-Native Agentic AI with Governed Continuity and Authoritative Memory.* Preprints.org, **not peer-reviewed**, 11 Sep 2026, DOI 10.20944/preprints202609.0878.v1. **Evidence level: conceptual plus synthetic.** The authors queried 25 synthetic prior-authorization cases, which they built to exercise each path: 10 accepted, 3 denied, 12 escalated. There is no ground truth and no test of security or continuity. The authors declare a conflict of interest.

**2. Core idea.** Permission (may this identity invoke this?) is not authority (may this action bind the institution now, under which purpose, evidence and version?). Each consequential action gets an **Authorization Warrant** that carries this state. One accepted event history keeps it, through retries, failover and substitution of the model or tool. When the machine's authority ends, *Escalate* is a first-class result that hands custody to a person.

**3. Mechanisms worth reusing.**
- **Six layers** (Table 1): capability, permission, authorization, institutional commitment, consequence obligation, constitutional change.
- **"Authorization is an event; authority is state"** (§3.2).
- **Warrant fields** (Table 2):
  - id, principal, actor/activity, purpose/scope;
  - policy version, evidence/provenance;
  - conditions/expiry, review, obligations;
  - continuity rules, correlation/causation id.
- **Continuity invariants** (Table 3). A retry makes no duplicate commitment. A substituted model or tool "acquires no authority merely from capability".
- **Separate events for proposal and effect** (§5.3).
- **Three dispositions and two closures** (§6.2, §7.2): governance closure (commit or hand over custody) vs business closure (the human decides).
- **The authority chain as the object to protect** (§8.4): principal → delegation → warrant → mediation → action → memory → reality.
- **Four evidence levels** (§6.4): specified, implemented, observed, consequence closed. This is a useful pattern for conformance claims.

**4. What it means for our standard.**
- *Provenance* (L2): a warrant is a PROV activity record plus the authorization context.
- *Rights and policy* (L2): this supports the purpose limitation in vision §6.
- *Federation* (L3) **[INFERENCE]**: a signed warrant could travel with a package. It would prove that the sender had the right to forward, and under which grant, delegation and policy version. This would make "rights travel with the content" checkable.
- *Threats*: the chain list is a good checklist of threats.
- *Lifecycle*: "escalate" is R1 applied to decisions.

**5. Where it challenges our model.**
- **The grant table is truth for behavior** (docs/09 §4.3). The paper says a grant is only *permission*. The enactment source column (block ref + event ids) is already a partial warrant, but it is recorded *per grant*, not *per action*. AT-09 access records come close; they would need purpose, policy version and obligations.
- **Our PDP has only two answers.** A third value, `escalate`, would cover these cases with one mechanism:
  - "bounded rule, no context";
  - agent requests that need `curate`;
  - unknown rights.
- **Their constitutional change maps to our canon.** Their "constitutional change only through ratification" matches `curate` being human-only and administrator policy versions. This supports our model.

**6. Weaknesses — do NOT copy.**
- **Branded, untestable vocabulary.** "Digital Genome", "AMOS", "autopoietic" and "metacognitive" add nothing that can be tested.
- **The formula is not formal.** `LegitimateAction` is a conjunction of undefined predicates.
- **The warrant is underspecified.** The fields have no types, no lifecycle (issued, used, revoked?), no signature and no serialization.
- **The evaluation proves almost nothing.** The cases were built to hit each path, so finding each path proves only that the paths exist.
- **"Across nodes" means only live migration inside one institution.** Nothing covers federation or remote verification.
- **"One authoritative history" assumes one node.** It conflicts with principle 8: in a network, each node has its own history.

**7. Open questions.**
- Is a warrant made for each action, or for each grant together with its uses?
- Can a receiver check a remote warrant without trusting the sender's history?
- Does a warrant carry the evidence itself or only references to it? This matters for privacy and egress.
- What happens to completed actions when a warrant is revoked later?
- Does an escalation time out, and to which state?
---

# Note 1: Jev-Mem

**1. Citation.** Jiang, Li, Li (UT Dallas). *Jev-Mem: System-One-Controlled Agentic Memory for Efficient AI Agents.* arXiv:2609.23986v1, September 2026, preprint. **Evidence: empirical, but thin.** It uses one benchmark, LoCoMo, with an LLM judge (gpt-4o-mini). It reports no ablation and no variance.

**2. Core idea.** Most memory-control decisions are semantic but not generative: typing, relation judgment, routing, scoring and stopping. A "System-One" controller (Jev, from TypeSafe AI) answers these decisions as batched typed probabilities, without text generation. A "System-Two" LLM only writes the final answer, and it makes merges or promotions only when the controller approves them.

**3. Mechanisms worth reusing**
- **Typed decision interface (§3.1, App. B.1).** A *Noul* is a binary proposition. It has an instruction, an explicit `true` criterion and an explicit `false` criterion, and it returns a value in [0,1]. A *Choice* holds mutually exclusive options and returns a label plus a distribution. Each instruction names the state fields that it reads, and a question in a batch does not read the answers of the other questions. The authors say that the scores are **not calibrated**.
- **Memory plane (eq. 4–6).** An observation is `o = (content, timestamp?, provenance)`. Each observation gives one canonical node. Typed edges (`semantic | temporal | causal | entity`) are views over the same nodes, and one pair of nodes can have more than one edge.
- **Deterministic first, model second (§3.2).** A timestamp order makes a temporal edge directly, and an exact shared id makes an entity edge directly. The model only judges the top K_w=10 candidates. An inferred edge needs P ≥ 0.60. The temporal Choice has these values: before, after, during, contains, overlaps, same_time, unknown.
- **Observation time is not event time (B.5, `timestamp_role`).**
- **Non-destructive consolidation (§3.2, B.3).** Every 20 writes, four Nouls check redundancy, contradiction, obsolescence and link usefulness. A Choice then selects `keep_separate | merge | promote | uncertain`. A System-Two summary is made only when merge or promote has p ≥ 0.85 and contradiction is < 0.85. Raw observations always stay.
- **Bounded retrieval (§3.3, B.5).** Retrieval stops when sufficiency ≥ 0.95 and missing < 0.15 and contradiction < 0.15. It also stops when continue_useful < 0.15. Hard caps apply: depth 8, 60 nodes, 2400 edges, 16 controller calls, 15 s.

**4. What it means for our standard**
- *Memory and consolidation (Q3):* consolidation adds a new derived object. It never edits the sources, which agrees with our append-only events. A merge or promotion is a derived object with origin `model` and Standing `pending`. **L2.**
- *Trust and annotation:* the Noul form fits labelling protocol §5. Each closed facet value becomes a Noul with true and false criteria, and a preset becomes a Choice. The output is a **proposal with confidence**, never a confirmation (§8: "confidence as truth" is excluded). **L2.**
- *Unit:* an agent observation can map to a document of one block with origin `agent`.
- *Lifecycle:* "obsolescence" and "contradiction" are candidate triggers for the curator queue.

**Can typed-decision models classify our knowledge?** Yes, but only as proposers, and only on a local route until sensitivity is confirmed (§5.1). The paper does not say whether Jev can run locally or air-gapped. Today it is a black-box vendor service, so it cannot be a normative part of the standard.

**5. Where it challenges our model**
- **Model proposals of a stricter gate value.** By §2.3, an unconfirmed **Standing** proposal applies when it is stricter. An obsolescence classifier that proposes `retired` therefore hides approved blocks at once. That is a denial-of-knowledge path. R1 protects access, but it does not protect availability.
- **Relations.** Our model has `supersedes`, citations and quotation links only. Jev shows a general relation layer. By canon 1, we keep an edge type only if it changes a behavior: `contradicts` sends a block to the curator queue, `supersedes` retires a block, and `duplicates` makes a `none` proposal. Semantic and causal edges are index data. They are not ontology.
- **Memory types.** The four overlapping type scores (episodic, semantic, procedural, preference) **change nothing**. Admission is off, and the scores do not appear in the scoring formula (eq. 23). By canon 1, they fail. This partly answers Q3: memory types are a descriptive periphery, not a facet.

**6. Weaknesses: do not copy**
- The abstract and §4.1 claim two benchmarks, but the paper reports one.
- The text and Table 1 do not agree: multi-hop 0.625 vs 0.623, open-domain 0.610 vs 0.618, single-hop 0.797 vs 0.802. The text says temporal "matches 0.650", but the table gives 0.637.
- There is no ablation, so the gain cannot be attributed to System One rather than to the graph. The adversarial jump (0.742 → 0.962) has no explanation.
- MAGMA, the strongest baseline, comes from the same authors.
- The paper does not describe the controller model at all (size, training, hosting).
- The thresholds are fixed and not justified. A contradiction of 0.84 still allows a merge.
- Provenance μ is stored but is not used anywhere.
- There is no threat analysis. Untrusted content goes into the controller state, so a poisoned memory can get itself scored highly (prompt injection into the controller).
- The reference list contains "(?)" entries and duplicate entries.

**7. Open questions**
- Must a proposal of a stricter *Standing* value need a quorum or confirmation, when other gate facets do not?
- Which edge types have a behavior and must be in the standard? Which stay local index data?
- Do derived edges and consolidations travel in packages? I propose that they never travel as authority.
- Does a "detected contradiction" have a defined user-visible behavior?

---

# Note 2: Decentralised Agentic Governance (Riznyk)

**1. Citation.** V. Riznyk, *Decentralised Agentic Governance: A Methodology for Community-Owned Linguistic Datasets and Knowledge Synthesis.* CERN IdeaSquare Journal of Experimental Innovation 10(2):177–185, 2026, journal article. **Evidence: conceptual.** It shows a hackathon proof-of-concept and a figure prototype, and §3.4 says that this is "not intended as an empirical evaluation".

**2. Core idea.** Three layers work together: an LLM agent (ElizaOS) helps non-experts write structured triples, a DAO validates them with quadratic voting (QV) and reputation, and a ledger records the approved entries. The agent suggests and never approves, so the community is "the final arbiter of meaning". The paper says that all three layers are necessary, but it does not argue this (§1.1).

**3. Mechanisms worth reusing**
- **Entry shape (Fig. 4):** `subject, predicate, object, context, domain` (a language tag such as `fr-CH`), and `evidence = COMMUNITY_VALIDATION`.
- **Ledger record (§1.2, §2.3, Fig. 3):** the triple, contributor attribution, the DAO decision id, the validation round and the schema version.
- **Strict role split (§2.1, §3.2):** the agent proposes, and a human or the community confirms. This independently confirms our rules "model = proposals only" and "`curate` is human-only".
- **Failure-mode list (§3.5):** Sybil attack, collusion, reputation entrenchment, and erasure against immutability. This is a useful threat checklist.
- **Fig. 2** names a revision loop and a dispute/resolution loop, but the text does not define them.

**4. What it means for our standard**
- *Unit:* "triple + context + provenance" is close to a nanopublication (assertion + provenance graph). It supports "claim" as the unit that travels. **L3.**
- *Provenance:* each approved entry links to the decision that approved it, like our records that store the ids of the annotation events in force (AT-09). **L2.**
- *Trust:* approval by a community is a local-trust policy (principle 8). **L3.**
- *Rights:* it uses the CARE principles, and the community keeps authority over licensing (§1.4 v). **L0** rights holder.
- *Threats:* Sybil attacks and collusion against any voting-based approval. **L3.**

**Is the blockchain necessary? No.** The paper uses it only as "an immutable audit trail" (§1.3). The prototype registry is a plain hash chain: "each record's hash includes the previous block's hash" (Fig. 4). There is no consensus between independent parties. Our L1/L2 parts already give the same properties: content addresses, Ed25519-signed packages and an append-only event log. A transparency log (a Merkle tree with signed checkpoints, Certificate-Transparency style) adds public verifiability. It needs no tokens and no consensus, and it works air-gapped. A chain adds three costs: a conflict with on-prem and air-gapped nodes, smart-contract auto-execution that weakens "human final authority", and erasure that cannot be done.

**5. Where it challenges our model**
- **Collective approval.** Our `curate` is one human principal. For a commons or for L3, Standing `approved` can need a **quorum policy** (k-of-n curators) as part of the node trust policy. A vote mechanism is not necessary.
- **The rights holder can be a collective** with authority to control use (CARE). The L0 rights fields must allow this.
- **Erasure.** Our §3 rule "history is never deleted" has the same defect as their ledger. Contributor attribution is personal data even when the content is not. The event log must keep content and actor identity out of the immutable part, by reference to encrypted or pseudonymous stores, and it needs an explicit **erasure event** that destroys keys (crypto-shredding, vision §6). [INFERENCE, outside this paper: EU data-protection guidance on blockchains says that hashes of personal data can still be personal data.]

**6. Weaknesses: do not copy**
- **QV is for preference intensity, not for truth.** A participant with strong conviction can outvote an expert who cares less.
- The paper never defines where voice credits come from, or how QV combines with reputation.
- The cited Buterin et al. 2019 paper is about quadratic *funding*.
- The prototype says contributor identity is "not identity verification", so the prototype has no Sybil resistance.
- In Fig. 4, entries that show 0/10 votes are already in the registry. This is probably a mock-up artifact, but it is unclear.
- §1.4 promises that the community controls access, but the paper defines no access control. A public permanent ledger contradicts that promise.
- Predicates are free text, with no controlled or SKOS-mapped vocabulary.
- The hypergraph clustering algorithm (Fig. 3) is not specified.

**7. Open questions**
- Can the dispute loop map to our `retired → pending` reopen transition?
- Do approval evidence and voter identities travel between nodes, and how is voter privacy kept?
- What is the minimum tamper evidence at L1: a signed hash chain only, or an externally witnessed Merkle log?
- How does a node weigh a remote community's approval against its own curators?