# Brainstorm round 3 — brief

**You are a lead researcher in a paradigm study: *what knowledge is, and how it must be managed, in the age of AI*.** You are a co-author of the result, not a reviewer of our draft. Two other lead researchers receive the same brief and work independently: Claude (Anthropic) and one more model. The operator merges the three results.

## 1. Our intent

We want to create an **open knowledge-management standard and framework** for humans and AI agents. It must be:
- **distilled:** a small, uncomplicated core that people understand in one sitting;
- **meaningful:** every concept in it changes what a system does;
- **durable:** it continues to work while AI changes. Models will change, agents will multiply, context windows will grow, and knowledge may move away from human language.

**Two scopes, one model.**
1. **Organization node.** An organization manages its own knowledge on its own premises: on-prem, local models, air-gapped if necessary, lightweight to adopt.
2. **Network of nodes.** Deployments act as abstract **routers of cumulative human knowledge**: they collect, filter, classify and pass on knowledge between organizations and communities, under the rights and the trust policy of each node.

**Ecosystem.** The standard is one part of an open-source ecosystem for agentic AI governance:
- **LLMDAP:** a governed gateway for every model call, with egress control, caller identity and a signed audit chain.
- **Kütüphane:** the reference implementation of this knowledge standard. It already exists, and it is small: content-addressed versions, citations, Zanzibar-style grants and delegation, signed packages between installations, hybrid search, and an audit joined with LLMDAP.

**The deliverable is the standard,** not the product (decision D55).

## 2. Fixed constraints (the operator's canon)

1. **Every value in the ontology must change a system behavior** (gate, ranking, citation authority, archive, delegation, presentation, routing). A value that changes nothing is removed.
2. **State transitions are planned before implementation:** trigger, actor, automatic or not, audit, reversal.
3. **The ontology is the core; the implementation stays small.** No heavy infrastructure is required to conform at the lowest level.
4. **Uncertainty never increases authority or access.**
5. **Open source, on-prem possible, no dependency on one vendor or one cloud.**

**Everything else is open.** This includes our current model (docs/09 ontology v2, docs/10 vision 0.2). You may keep it, change it or discard it. Tell us why.

## 3. Inputs (read-only)

- `docs/10-vision.md`: our vision draft, including the conformance levels L0–L3 and a proposal for usage rights.
- `docs/09-ontology-v2.md`: our current behavioral facets.
- `docs/01-direction-decisions.md`: the decision record (D1–D55), for context.
- `docs/research/2026-10-20-research-map.md`: our distilled reading of 11 papers.
- `research/papers/*.pdf` and `research/text/*.txt`: the 11 papers.
  - **They are idea sources, not truth.** Most of them are 2026 preprints with conceptual or synthetic evaluation.
  - Do not plan around them. Use what is solid, and say what is weak.
- **Do not read `experiments/labeling/data/`:** it is a private corpus.
- **Do not change any file.**

## 4. Your research mandate

- **Use web research.** Go beyond our documents and these papers. Cite each source with a link.
- **Find what we do not see.** We expect you to say clearly where we are wrong, naive or late.
- **Name the tricks: the practical lessons that decide success.** Learn from the standards that won and the standards that died:
  - Dublin Core, schema.org, RDF/OWL and the Semantic Web, Wikidata, SPDX, robots.txt, RSS, Git, IPFS, OpenAPI, MCP;
  - why some were adopted and others were not.
- **Think about the evolution of AI,** for example:
  - model-native and parametric memory;
  - very long contexts;
  - multi-agent societies;
  - knowledge in embeddings or other non-human formats;
  - models trained on the commons that this standard creates;
  - machine-generated knowledge that exceeds human-written knowledge;
  - regulation (EU AI Act, GDPR, copyright and the text-and-data-mining opt-out).
- **Questions to consider.** They are not a limit:
  1. What is the smallest unit of knowledge that can travel alone?
  2. What are the irreducible operations that knowledge goes through?
  3. How is trust expressed between sources, labellers and nodes, with no global truth?
  4. How do origin and provenance stay honest when models write most of the text?
  5. How are usage rights declared and enforced, and at which conformance level?
  6. How do forgetting, retraction and erasure work in a network with immutable logs?
  7. How do agent memory types map to shared knowledge, and is *consolidation* the main loop?
  8. What makes knowledge *executable* (skills, procedures, tools), and how is that governed?
  9. How is the value or fitness of knowledge measured over time?
  10. Why would an organization adopt this standard, and why would it share knowledge?
  11. Which threats are specific to shared knowledge (poisoning, prompt injection, laundering of model text as human text)?

## 5. Deliverable

**Format.**
- Markdown, at most about 3,000 words.
- ASD-STE100 Simplified Technical English.
- Sources as links.

**Sections, in this order:**
1. **Thesis** (at most 150 words): the paradigm in one paragraph.
2. **Blind spots:** what we missed, ranked by importance, each with its evidence.
3. **The standard's core:**
   - the narrow waist (the object model);
   - the minimal set of operations (verbs);
   - the facets or properties, each with its behaviors;
   - the state transitions;
   - the conformance levels, including where usage rights go.

   Keep it small. Explain each element in one or two sentences.
4. **Reuse:** existing standards to compose, with links; and what to avoid, with the reason.
5. **Durability tests:** 3–5 concrete scenarios between 2027 and 2032. Show how the core still works, or what must change.
6. **Kill list:** what in our current model to delete, and why.
7. **Failure modes:** how this standard could fail (adoption, security, complexity, law) and the counter-measure for each.
8. **Questions for the operator:** at most 5.
