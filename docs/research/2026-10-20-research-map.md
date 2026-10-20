# Research map — 11 papers, distilled (2026-10-20)

**Inputs:** 8 papers that the operator selected and 3 gap papers that Claude selected. Six independent readers read them critically (full notes: `2026-10-20-paper-notes.md`).

**Rule:** the papers are idea sources, not truth.
- Only two have real empirical evidence: nanopublications (a live network) and the AT Protocol (a large deployment).
- The others are conceptual or synthetic, and most of them are 2026 preprints.

This map keeps the mechanisms that agree across sources, and the points where the sources challenge our current model (docs/09, docs/10).

| Paper | Evidence | Main use for us |
|---|---|---|
| Kuhn et al. 2016, nanopublications | empirical (live network) | the claim envelope; self-verifying ids; simple replication |
| Kleppmann et al. 2024, AT Protocol | deployment report | signed repositories; labelers; local trust; credible exit |
| Jørgensen & Ma 2026, bounded autonomy | conceptual, peer-reviewed | epistemic status vs source authority; propose-only agents |
| Eren 2026, Living Data Genome | synthetic, peer-reviewed | revocation that travels; closed event alphabet; release gate |
| Shahid et al. 2026, Tacit Fragments | conceptual preprint | conditions of applicability; authority ladder; author ≠ approver |
| Decision Integrity 2026 (SSRN) | conceptual preprint | provenance of expertise, not only of data |
| Joshi et al. 2026, deontic policies | prototype | permission, prohibition, obligation, dispensation |
| Krimbacher et al. 2023, dataspaces | position paper | ODRL usage policies; preventive vs detective enforcement |
| Mikkilineni & Kelly 2026, warrants | conceptual preprint | permission ≠ authority; "escalate" as a decision |
| Jiang et al. 2026, Jev-Mem | thin empirical | consolidation as new derived objects; System One models as proposers |
| Riznyk 2026, community commons | conceptual | community approval; GDPR conflict with ledgers |

## 1. Signals that agree across sources

### 1.1 The travelling unit is a claim envelope, not a structural block

Four sources reach the same shape independently:
- nanopublications: assertion + provenance + publication info;
- Tacit Fragments: content + provenance + conditions + authority + state;
- Living Data Genome: claim + artifact + explanation + lineage;
- Riznyk: triple + context + attribution + decision id.

**Consequence:**
- Our *block* stays the local, structural anchor.
- The unit that travels between nodes is a **claim envelope** with a **self-verifying id** (a hash of its content, provenance and rights).
- RDF must not be mandatory; nanopublications tie identity to RDF canonicalization.

### 1.2 Two kinds of facts: what the content *is*, and what a node *thinks* of it

| Kind | Examples | Where it lives | Travels? |
|---|---|---|---|
| **Intrinsic** | the content, its provenance, its origin, its rights | inside the signed, hashed envelope | yes |
| **Opinion** | standing, authority, role, trust, labels | annotations from a named author (a person, a node, a labeler) | yes, as separate signed objects |

- The AT Protocol labelers, Jørgensen ("authority is assigned by governed metadata, never by content") and Tacit Fragments (authority is local) agree.
- **Local opinions must stay outside the hash.** If they are inside, a curator decision creates a new global identity.
- A node maps the opinions of the labelers that it trusts to *proposals*. Under R1 and R3, an imported looser value never applies without a local human.

### 1.3 "What kind of statement" is separate from "who stands behind it"

| Source | Axis 1 | Axis 2 |
|---|---|---|
| Jørgensen & Ma | epistemic status: asserted, observed, inferred, proposed, invalidated | evidential authority: system record, external evidence, analytic output, agent output |
| Tacit Fragments | validation state | authority ladder: evidence → advisory → controlled |
| Ours (docs/09) | Role: rule, evidence, none | Standing: approved, pending, retired |

**Three sources agree that origin must have a gate:** model-derived or agent-derived knowledge needs a higher evidence bar. In docs/09 we made Origin "metadata, no gate". **This is the clearest correction from the research.**

### 1.4 Lifecycle: append-only, supersede, and *revocation that travels*

All sources use append-only history with supersession; nothing is deleted silently. New points:
- **Revocation must follow the content to every receiver** (Living Data Genome, nanopublications). Our `retired` is local to one node.
- **Terminal disposition:** a retirement names a successor, or it gives an explicit terminal reason.
- **Contest** is a distinct event: someone disputes a claim. It is not a new status.
- **Author ≠ approver:** the person who wrote or captured an item cannot approve it. The source person confirms *fidelity*; a different person approves *use* (Tacit Fragments).
- **Event-triggered review:** a review is triggered by events (an expiry trigger, a contradiction, a changed source), not only by a date.
- **Collective approval:** a commons can need a quorum of k-of-n curators (Riznyk). A vote mechanism is not necessary.

### 1.5 Policy: grants are not enough

- **Four deontic forms** (Joshi et al.; ODRL has the same model): permission, prohibition, obligation, dispensation.
  - Our model has permissions (grants) and two fixed prohibitions (`restricted`, `local_only`).
  - "Read but do not train" and "export with duties" cannot be expressed today.
- **Keep forbid-overrides-permit.** The only exception is a scoped, expiring, audited **dispensation** from a named issuer.
- **An obligation is a stateful object,** so it needs a state machine: issued → pending → discharged | dispensed | violated → escalated.
- **After transfer, the sender can only detect, not prevent** (dataspaces). Enforcement after transfer therefore needs a conformant receiver (L2) that acts as the enforcement point, and signed receipts.
- **Escalate is a third decision,** beside permit and deny (Mikkilineni; Tacit: "outside the conditions → a human").
- **An unknown policy term means deny** (R1). This is a conformance rule.

### 1.6 Memory and consolidation

- **Consolidation makes a new derived object; it never edits its sources** (Jev-Mem). A derived object has origin `model` or `agent` and standing `pending`.
- **Memory types (episodic, semantic, procedural) fail the canon as facets.** In Jev-Mem they change nothing. They are a descriptive periphery.
- **Deterministic first, model second:** exact ids and timestamps make links directly; a model judges only the remaining candidates.
- **System One models (Laya, Jev) are useful as proposers** of labels and relations, with probabilities. Their scores are not calibrated, so they never confirm.

### 1.7 Federation

- **Nanopublication pull sync** is simple and works air-gapped: append-only journals, resumable offsets, verification of every hash, subset filters. It needs no consensus and no blockchain.
- **AT Protocol:** each author signs a portable repository; neutral indexes and opinionated labelers are separate roles; every role can have competing operators ("credible exit").
- **Dataspaces:** a contract can bind both directions. A consumer can also set duties on the provider (for example, freshness).
- **Warrants:** a signed record can travel with a package to prove that the sender had the right to forward it.

### 1.8 Privacy and erasure

**Immutable logs conflict with GDPR** (Riznyk, nanopublications).
- Content and actor identity must stay *outside* the immutable part, by reference.
- Erasure is an explicit event that destroys keys (crypto-shredding).
- Hashes of personal data can still be personal data.

### 1.9 Threats

The sources name these threats:
- poisoned statements;
- laundering of model text as human text;
- stale approvals;
- leaks through explanations;
- tampering with revocations.

**New for us: denial of knowledge.** Under R1, a model proposal of a *stricter* standing applies at once, so an obsolescence classifier can hide approved knowledge. **R1 protects access, but it does not protect availability.**

## 2. What the research changes in our model

| # | Change | Sources | Level |
|---|---|---|---|
| C1 | A **claim envelope** with a self-verifying id as the travelling unit. The block stays the local anchor. | nanopub, Tacit, LDG, Riznyk | L1/L3 |
| C2 | **Intrinsic facts in the envelope; opinions as separate signed annotations** from named authors. | AT Proto, Jørgensen | L2/L3 |
| C3 | **Origin gets a gate:** model- or agent-derived items need a higher evidence bar before they become a rule. | Jørgensen, Tacit, Decision Integrity | L2 |
| C4 | **Revocation travels;** retirement needs a successor or a terminal reason; `contest` is an event. | LDG, nanopub | L2/L3 |
| C5 | **Author ≠ approver;** fidelity confirmation is separate from approval; optional quorum. | Tacit, Riznyk | L2 |
| C6 | **Deontic policy:** prohibition, obligation and dispensation join the grants (ODRL); obligations have a state machine. | Joshi, Krimbacher | L2/L3 |
| C7 | **A third decision, `escalate`.** Scope gets *exclusion* conditions. | Mikkilineni, Tacit | L2 |
| C8 | **Availability rule:** a model proposal can tighten *access* at once, but it cannot hide approved knowledge without a human. | Jev-Mem (our inference) | L2 |
| C9 | **Erasure by key destruction;** personal data stays out of the immutable log. | Riznyk, nanopub | L2 |
| C10 | **Consolidation = a new derived object;** memory types are periphery, not facets. | Jev-Mem | L2 |

## 3. What we must not copy

- Heavy mandatory stacks (OWL, SHACL, BPMN, DMN), because of the "L0 in an hour" principle.
- Blockchain, DAO and quadratic voting: they add nothing that a signed append-only log and a quorum do not give.
- Branded vocabulary that cannot be tested ("genome", "autopoietic").
- "Confidence" as a facet without a scale and a behavior.
- Open ontology reasoning on gates: a wrong subclass link loosens a gate silently.
- A general permission-overrides-prohibition rule.
- Mandatory RDF canonicalization; open lexicon namespaces without mapping.
- "Cannot unpublish" on organization nodes.
- Obligations sent to the LLM as text.

## 4. Gaps that the papers do not cover (for round 3 research)

1. **Knowledge beyond human language:** embeddings, model-specific vectors, agent-to-agent formats, parametric memory.
2. **Adoption:** why standards win or die (Dublin Core, schema.org, the Semantic Web, SPDX, robots.txt, MCP).
3. **AI training rights in practice:** the TDM opt-out (EU DSM Art. 4(3)), TDMRep, and AI Act Art. 53.
4. **Incentives:** why an organization shares, and what it gets back.
5. **The fitness of knowledge:** usefulness signals over time, beyond its age.
6. **Identity:** how an organization node signs as a whole while each human or agent author is still identified (DIDs vs OIDC).
7. **Executable knowledge:** how skills, procedures and tools are governed as knowledge.
8. **The minimal profiles of PROV-O and ODRL,** and C2PA for non-text content.
