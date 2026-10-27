> **Superseded for positioning by `docs/23-vision-v1.md` (D69, 2026-10-27).** This document stays as the history of the standard work.

# Vision — an open knowledge management standard

**Status:** DRAFT 0.2, 2026-10-20 (D55). **Changed by D59 (2026-10-22):** proposing a standard alone is too big. First we find and understand the existing work (`docs/13-landscape.md`). Then we join those communities and contribute. kstd becomes a profile of existing standards, and we propose new parts only where a gap exists. §1 must be read with this change.
- Basis: the research map (`docs/research/2026-10-20-research-map.md`).
- Next: this document is an input for brainstorm round 3 (`docs/research/2026-10-20-round3-brief.md`). Round 3 is free to change any part of it.

**Language:** ASD-STE100 Simplified Technical English.

## 1. What we build

- **The main deliverable is a standard:** an open specification for how knowledge is stored, described, governed and shared by people and agents.
- **Kütüphane is its reference implementation,** and the standard does not depend on it.
- **The standard is part of an ecosystem for agentic AI governance.** LLMDAP governs model calls, egress and identity; the knowledge standard governs what agents and people know, may use and may pass on.

**Our goal:** a **distilled, uncomplicated and meaningful** standard that continues to work while AI changes.

## 2. Two scopes, one model

| Scope | What a deployment does |
|---|---|
| **Organization node** | An organization manages its own knowledge on its own premises: on-prem, local models, air-gapped if necessary, lightweight. |
| **Network of nodes** | Deployments act as abstract **routers of cumulative human knowledge**: they collect, filter, classify and pass on knowledge, under the rights and the trust policy of each node. |

The same object model serves both scopes. An organization node is a network of one.

## 3. Principles

**From the canon (D53):**
1. Each value changes a behavior. A value that changes nothing is removed.
2. State changes are planned before implementation.
3. The ontology is the core; the implementation stays small.
4. Uncertainty never increases authority or access.

**Candidates (round 3 tests them):**
5. **Compose existing standards.** The new part is the behavioral core and the governance links.
6. **A small closed core, an open periphery.** Gate vocabularies are closed; descriptive vocabularies are open and mapped (SKOS).
7. **Verbs over nouns.** The ontology is the set of operations that knowledge goes through.
8. **Intrinsic facts and opinions are separate.** What content *is* travels inside its signed envelope. What a node *thinks* of it is a separate, signed annotation from a named author.
9. **Local trust over global truth.** Each node decides which authors and labelers it trusts. An imported opinion is only a proposal.
10. **Origin has a gate.** Knowledge that a model or an agent derived needs more evidence before it becomes a rule. The author of an item never approves it.
11. **Availability is protected too.** A proposal can tighten access at once, but it cannot hide approved knowledge without a human.
12. **Rights travel with the content,** and an unknown right means "no".
13. **Adoption is gradual.** A small organization conforms at the lowest level in about an hour.

## 4. The narrow waist (draft)

| Element | What it is |
|---|---|
| **Content object** | Bytes with a content address. Personal data stays out of immutable logs, by reference. |
| **Claim envelope** | The unit that travels alone: a claim, its provenance, its origin and its rights, with a self-verifying id. Inside a node, a claim points to its block, the local structural anchor. |
| **Annotation** | A signed opinion about a claim or an object (standing, role, authority, a label, a contest, a revocation), with its author. |
| **Policy** | Permissions, prohibitions, obligations and dispensations (ODRL-compatible). A decision is one of *permit*, *deny* or *escalate*. |
| **Event log** | Append-only. Every state is a fold over events. Erasure is an event that destroys keys. |

## 5. Conformance levels (draft)

| Level | Requires | Standards it uses |
|---|---|---|
| **L0 Described** | files + frontmatter; rights *declared* | OKF, SPDX |
| **L1 Versioned** | content-addressed versions, stable citations, signed packages, claim envelopes | content addressing, Ed25519 |
| **L2 Governed** | annotations, facet behavior, deontic policy enforcement, audit | Zanzibar, PROV-O, ODRL |
| **L3 Federated** | routing between nodes, trust policies, revocations that travel, receivers that enforce | nanopublication-style sync, VC, A2A/MCP |

## 6. Usage rights and compliance (proposal)

The rights *declaration* is core at every level; *enforcement* grows with the level. An unknown value is never permissive.

| Level | Rights |
|---|---|
| L0 | Declare: license (SPDX id or URL), rights holder (a person or a collective), TDM reservation (EU DSM Directive Art. 4(3)), personal data `yes / no / unknown`. |
| L1 | The declaration is inside the signed envelope and travels with it. |
| L2 | Enforce as ODRL policies: permitted actions (read, use, derive, train, redistribute), prohibitions, obligations with a state machine, dispensations from named issuers, purpose limitation, personal-data handling (lawful basis, retention, erasure by key destruction). The audit log gives the records of processing (GDPR Art. 30). |
| L3 | Routing precondition: a node never forwards an object if its rights do not allow the action at the receiver. The receiver must be at least L2 and acts as the enforcement point. Revocations and TDM reservations travel. Provenance supports EU AI Act Art. 50 and Art. 53. |

## 7. Relation to the work done

- **docs/09 (ontology v2)** becomes one **profile** at L2. The research changes it: Origin gets a gate, the proposal rule gets an availability limit, and Scope gets exclusion conditions.
- **M1 code** already implements parts of L1 and L2:
  - content-addressed versions;
  - citations;
  - signed packages;
  - grants and delegation;
  - audit joined with LLMDAP.

## 8. Open questions for round 3

1. Is the claim envelope the right travelling unit? What exactly does its hash cover?
2. What is the smallest closed set of verbs (operations)?
3. How is trust between authors, labelers and nodes expressed and computed?
4. How does the standard stay usable when knowledge is no longer in human language?
5. Which rights fields are core, and which are a profile?
6. How do revocation and erasure work in a network?
7. How is the fitness of knowledge measured over time?
8. How is executable knowledge (skills, procedures, tools) governed?
9. Why would an organization adopt this standard and share knowledge?
10. Which lessons from past standards decide our success?

## 9. Process

1. NotebookLM mind map. **(done)**
2. The operator selects papers. **(done)**
3. Research map. **(done)**
4. This document, version 0.2.
5. Brainstorm round 3: Claude, Astra and Mythos, independently, with web research.
6. Critique round.
7. Operator decision.
8. Labelling v4.
