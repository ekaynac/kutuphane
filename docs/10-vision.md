# Vision — an open knowledge management standard

**Status:** SKELETON 0.1, 2026-10-20 (D55).
- The sections marked *[research]* wait for the papers that the operator selects from the NotebookLM mind map.
- After them, this document becomes the brief for brainstorm round 3.

**Language:** ASD-STE100 Simplified Technical English.

## 1. What we build

- **The main deliverable is a standard:** an open specification for how knowledge is stored, described, governed and shared by people and agents.
- **Kütüphane is its reference implementation,** and the standard does not depend on it.
- **The standard is part of an ecosystem for agentic AI governance.** LLMDAP governs model calls, egress and identity; the knowledge standard governs what agents and people know, may read and may pass on.

## 2. Two scopes, one model

| Scope | What a deployment does |
|---|---|
| **Organization node** | An organization manages its own knowledge on its own premises: on-prem, air-gapped if necessary, lightweight. |
| **Network of nodes** | Deployments act as abstract **routers** for cumulative human knowledge: they collect, filter, classify and pass on knowledge, under the rights and the trust policy of each node. |

The same object model must serve both scopes. An organization node is a network of one.

## 3. Principles

Kept from the canon (D53, docs/09 §0):
1. Each facet value changes a behavior. A value that changes nothing is removed.
2. State changes are planned before implementation.
3. The ontology is the core; the implementation stays small.
4. Uncertainty never increases authority or access.

New candidates (round 3 tests them):

5. **Compose existing standards; do not invent them.** The new part is the behavioral core and the governance links.
6. **A small closed core and an open periphery.** Gate vocabularies are closed. Descriptive vocabularies are open and mapped (SKOS).
7. **Verbs over nouns.** The ontology is the set of operations that knowledge goes through, not a set of genres.
8. **Local trust over global truth.** An annotation is an opinion with an author. Each node decides which opinions apply.
9. **Origin is first-class.** The system always knows if a person wrote a text or a model derived it, and from which sources.
10. **Rights travel with the content.**
11. **Adoption is gradual.** A small organization can conform at the lowest level in about an hour.

## 4. The narrow waist *[research]*

The minimum that every conforming system shares. Candidates:
- **content object:** bytes with a content address;
- **claim:** the smallest unit that can travel alone, with its source span;
- **annotation:** an opinion about a claim or an object, with its author;
- **policy envelope:** access, egress and rights;
- **event log:** append-only, so that every state is a fold over events.

## 5. Conformance levels (draft)

| Level | Requires | Standards it uses |
|---|---|---|
| **L0 Described** | files + frontmatter metadata; rights *declared* | OKF, SPDX |
| **L1 Versioned** | content-addressed versions, stable citations, signed packages | content addressing, Ed25519 |
| **L2 Governed** | annotation events, facet behavior, policy enforcement, audit | Zanzibar, PROV-O, ODRL |
| **L3 Federated** | routing between nodes, trust policies, claims that travel | nanopublications, VC/C2PA, A2A/MCP |

## 6. Usage rights and compliance (proposal for round 3)

**Proposal:** the rights *declaration* is core at every level; *enforcement* grows with the level. An unknown value is never permissive: unknown rights mean "do not share, do not train".

| Level | Rights |
|---|---|
| L0 | Declare: license (SPDX id or URL), rights holder, text-and-data-mining reservation (EU DSM Directive Art. 4(3)), personal data `yes / no / unknown`. |
| L1 | The declaration is part of the signed version, so it travels with the bytes. A change makes a new version. |
| L2 | Enforce: permitted actions (read, use, derive, train, redistribute) as ODRL policies; purpose limitation (the caller's declared purpose, as in LLMDAP); personal-data handling (lawful basis, retention, erasure through crypto-shredding). The audit log gives the records of processing (GDPR Art. 30). |
| L3 | Routing precondition: a node never forwards an object without rights that allow the action at the receiver. TDM reservations are honored. The provenance chain is required, which supports AI-generated content marking (EU AI Act Art. 50) and copyright compliance of general-purpose model providers (Art. 53). |

## 7. Relation to the work done

- **docs/09 ontology v2** becomes one **profile** at L2: the behavioral facets of an organization node. Round 3 decides what stays core.
- **M1 code** already implements parts of L1 and L2:
  - content-addressed versions;
  - citations;
  - signed packages;
  - authorization;
  - audit through LLMDAP.

## 8. Open questions for round 3 *[research]*

1. What is the smallest unit that travels: block, claim or assertion?
2. How is trust between nodes expressed and computed?
3. How do agent memory types (episodic, semantic, procedural) map to the model, and is consolidation the main loop?
4. How does the standard stay usable when knowledge is no longer in human language (embeddings, agent-to-agent formats)?
5. Which rights fields are core, and which are a profile?
6. How are forgetting, retraction and the right to erasure handled in a network?
7. Which threats are specific to shared knowledge (poisoning, prompt injection, laundering of model text as human text)?

## 9. Process

1. NotebookLM mind map.
2. The operator selects papers.
3. Claude writes a research map.
4. This document, version 0.2.
5. Brainstorm round 3: Claude, Astra and Mythos, with web research, free to go beyond this document.
6. Critique round.
7. Operator decision.
8. Labelling v4.
