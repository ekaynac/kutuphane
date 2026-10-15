You are Astra, a co-author of the Kütüphane knowledge ontology. This is a BRAINSTORM, not a code review. Claude (the other co-author) is writing its own proposal at the same time; you do not see it. Later the two proposals are merged and you critique the merge.

Repository (read-only): /home/mega/kobra. Do not change files. Do not use the network or the database.
Do NOT read `experiments/labeling/data/` (it holds internal corpus content that must not leave the host). Everything you need about the corpus is in this brief.

Context to read first:
- docs/02-2026-10-08-brainstorm-ontology.md §2: axes E1–E7 and categories K1–K8.
- docs/01-direction-decisions.md: D24 (9 axes; only E5, E8 and E9 enforced), D25, D28, D36, D37 (K3 activate gate), D52.
- docs/07-m1-definition.md: acceptance tests.
- src/kutuphane/: catalog.py, profiles.py (chunks), authz.py (grants with expiry, delegation), search.py, answers.py. These show what the system can enforce today.

## What happened

Labelling v1 asked, for each whole document:
- one category K1–K8 (human document types) or "Does not fit";
- sensitivity (normal/restricted);
- egress (local_only/cloud_ok).

The corpus is 163 internal documents, mostly from software development: agent instructions, design docs, plans, reviews, run reports, standards, notes and archives. The operator labelled 11 documents (14 labels), then stopped. Findings:

1. One label for each document loses information. Examples, described without their content:
   - a discovery run report that is both a record and a lesson;
   - a long MCP-notes document that holds canonical decisions, operator decisions for the agent (permissions, consents with their own TTL), references and reports;
   - design documents with parts of several types.
2. 5 of 11 went to "Does not fit": designs, plans, proposals. There is no class for "proposed, not decided" or for a "review".
3. Many documents are stale "current state" reports that should be archived. The operator wrote: "document TTL and permission TTL are two different things" — a decision or permission inside a document has its own TTL, and that TTL is not the document's.
4. Sensitivity and egress were easy and useful. One document was normal but local_only, so the two facets are independent.
5. The median was about 2.6 minutes per document, too slow for 150 documents.

## Operator direction (their words, lightly edited)

- "Categories do not need to be human-centric and pre-defined. Define the knowledge system and its tags from a more functional view. We may not foresee the future of agent-to-agent communication. Knowledge may move away from a human-centric language at some point. Sensitivity and egress are much more meaningful than our human-centric categories."
- Unit: either micro-sections inside a document with stored section information, or split documents that keep the master document's information. The operator accepts sections inside the master document, but wants a careful brainstorm on HOW to decide the sections. "Correct labelling becomes crucial."
- CANON: "Knowledge facets must have meaningful behavioral distinctions." A facet value that does not change system behavior does not belong.
- "Facet state changes should be planned carefully beforehand."
- "This knowledge ontology is the core of our system. Implementation is easy and should not be overcomplicated. The ontology and the vision are the core."
- The operator is NOT sure how to handle decisions and permissions found inside documents.

## Hard constraints from the product

- Content is versioned (content id = hash). A citation names book, content id, profile id, path and ordinal. Signed packages carry versions between installations. Authorization is per book: modes discover/read/use/activate, and one-level user→agent delegation with expiry. K3 content (agent instructions) needs `activate`.
- Labels and ground truth must survive new document versions where the text did not change.
- Simplicity: one Python app on Postgres, with the fewest tables and services that keep the governance claims.

## Please give your INDEPENDENT proposal. ASD-STE100 Simplified Technical English, at most ~1800 words.

1. **Sections.**
   - How should the system decide section boundaries? Consider: structural (headings, lists, code blocks), semantic (function changes), facet-driven ("a section ends where a facet value changes"), nesting, minimum and maximum size, and documents without headings.
   - How does a section keep a stable identity across document versions, so that labels carry over? What happens to the labels when a section changes, splits or merges?
   - Who decides the boundary (rule, model, human)? How is it corrected?
2. **Facets.**
   - Propose the facet set. For EACH facet give:
     - the question it answers;
     - its values;
     - the exact system behavior that each value changes (gate, ranking, citation authority, archive, delegation, presentation);
     - closed or open vocabulary;
     - the level it applies at (document or section);
     - who sets it (rule, model, human) and who must confirm it.
   - Remove any value that has no behavioral distinction.
   - Say what happens to E1–E9 and K1–K8.
3. **State changes.**
   - For each facet that has states (for example status or validity), give a transition table: from, to, trigger, who may do it, whether it is automatic, whether it is audited, whether it is reversible.
   - Is a facet change a new version of the content, a new "facet version", or an event?
   - How do time-based changes (snapshot becomes stale) work without a person?
4. **Decisions and permissions inside documents.** Give the options and recommend one. Consider:
   - leave them in the text;
   - extract them as first-class decision records with scope and TTL;
   - map permissions to the existing grant/delegation system;
   - what is the source of truth when a document and a record disagree;
   - who may make a decision executable.
5. **Labelling protocol** for ground truth that is correct, at less than ~45 s per document. What does a human confirm, and what does the system propose?
6. **Agent-to-agent future.** What keeps the ontology useful when the readers and writers are mostly agents?
7. **Risks, and what you would NOT do.**

Be concrete. Do not invent facts about the corpus beyond this brief. Where you are unsure, say so.
